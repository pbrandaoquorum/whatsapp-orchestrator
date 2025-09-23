"""
FastAPI principal - Rotas síncronas
"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, Optional
import structlog

from app.api.deps import (
    get_settings, initialize_logging, get_dynamo_state_manager,
    get_main_router, get_fiscal_processor,
    get_escala_subgraph, get_clinico_subgraph, get_operacional_subgraph,
    get_finalizar_subgraph, get_auxiliar_subgraph
)
from app.infra.dynamo_state import normalizar_session_id
from app.graph.state import GraphState

# Inicializa logging
initialize_logging()
logger = structlog.get_logger(__name__)

# Cria app FastAPI
app = FastAPI(
    title="WhatsApp Orchestrator",
    description="Sistema de orquestração de fluxos WhatsApp usando LangGraph",
    version="1.0.0"
)


# Schemas de request/response
class WebhookRequest(BaseModel):
    message_id: str
    phoneNumber: str
    text: str
    meta: Dict[str, Any] = {}


class WebhookResponse(BaseModel):
    reply: str
    session_id: str
    status: str = "success"


class HealthResponse(BaseModel):
    status: str
    message: str


# Orquestrador principal
class WhatsAppOrchestrator:
    """Orquestrador principal que executa o grafo"""
    
    def __init__(self):
        # Componentes
        self.dynamo_manager = get_dynamo_state_manager()
        self.router = get_main_router()
        self.fiscal = get_fiscal_processor()
        
        # Subgrafos
        self.subgraphs = {
            "escala": get_escala_subgraph(),
            "clinico": get_clinico_subgraph(),
            "operacional": get_operacional_subgraph(),
            "finalizar": get_finalizar_subgraph(),
            "auxiliar": get_auxiliar_subgraph()
        }
        
        logger.info("WhatsAppOrchestrator inicializado")
    
    def executar_grafo(self, phone_number: str, texto_usuario: str, meta: Dict[str, Any]) -> str:
        """
        Executa grafo completo: router → subgrafo → fiscal
        
        Returns:
            Resposta final para o usuário
        """
        # 1. Normaliza session_id
        session_id = normalizar_session_id(phone_number)
        
        logger.info("Executando grafo",
                   session_id=session_id,
                   texto=texto_usuario[:100])
        
        try:
            # 2. Carrega estado
            state = self.dynamo_manager.carregar_estado(session_id)
            
            # Debug: verifica se pendente foi carregado
            logger.info("MAIN: Estado carregado", 
                       session_id=session_id,
                       tem_pendente=state.tem_pendente(),
                       pendente_fluxo=state.pendente.get("fluxo") if state.pendente else None)
            
            # 3. Atualiza entrada
            state.entrada["texto_usuario"] = texto_usuario
            state.entrada["meta"] = meta
            state.sessao["telefone"] = phone_number
            
            # 4. Router decide próximo subgrafo
            proximo_subgrafo = self.router.rotear(state)
            
            logger.info("Router decidiu próximo subgrafo",
                       session_id=session_id,
                       subgrafo=proximo_subgrafo)
            
            # 5. Executa subgrafo
            if proximo_subgrafo not in self.subgraphs:
                raise ValueError(f"Subgrafo não encontrado: {proximo_subgrafo}")
            
            resultado_subgrafo = self.subgraphs[proximo_subgrafo].processar(state)
            
            logger.info("Subgrafo executado",
                       session_id=session_id,
                       subgrafo=proximo_subgrafo,
                       resultado=resultado_subgrafo[:100] if resultado_subgrafo else None)
            
            # 6. Fiscal consolida resposta final
            resposta_final = self.fiscal.processar_resposta_fiscal(state, resultado_subgrafo)
            
            # 7. Salva estado
            self.dynamo_manager.salvar_estado(session_id, state)
            
            logger.info("Grafo executado com sucesso",
                       session_id=session_id,
                       resposta_length=len(resposta_final))
            
            return resposta_final
            
        except Exception as e:
            logger.error("Erro na execução do grafo",
                        session_id=session_id,
                        error=str(e))
            raise


# Instância global do orquestrador
orchestrator = WhatsAppOrchestrator()


@app.post("/webhook/whatsapp", response_model=WebhookResponse)
def webhook_whatsapp(request: WebhookRequest) -> WebhookResponse:
    """
    Webhook principal do WhatsApp
    
    Fluxo:
    - Normalizar session_id = phoneNumber
    - carregar_estado
    - injetar entrada.texto_usuario
    - executar grafo (router → subgrafo → fiscal)
    - salvar_estado
    - retornar {"reply": state.resposta_fiscal, "session_id": "..."}
    """
    try:
        logger.info("Webhook recebido",
                   message_id=request.message_id,
                   phone_number=request.phoneNumber,
                   text=request.text[:100])
        
        # Executa orquestração
        resposta = orchestrator.executar_grafo(
            phone_number=request.phoneNumber,
            texto_usuario=request.text,
            meta=request.meta
        )
        
        session_id = normalizar_session_id(request.phoneNumber)
        
        return WebhookResponse(
            reply=resposta,
            session_id=session_id,
            status="success"
        )
        
    except Exception as e:
        logger.error("Erro no webhook",
                    message_id=request.message_id,
                    phone_number=request.phoneNumber,
                    error=str(e))
        
        # Retorna erro amigável
        return WebhookResponse(
            reply="Desculpe, ocorreu um erro interno. Tente novamente em alguns instantes.",
            session_id=normalizar_session_id(request.phoneNumber),
            status="error"
        )


@app.get("/healthz", response_model=HealthResponse)
def health_check() -> HealthResponse:
    """Health check simples"""
    return HealthResponse(
        status="ok",
        message="WhatsApp Orchestrator está funcionando"
    )


@app.get("/readyz", response_model=HealthResponse)
def readiness_check() -> HealthResponse:
    """
    Readiness check - valida configurações e acesso ao DynamoDB
    """
    try:
        # Valida configurações
        settings = get_settings()
        
        # Testa acesso ao DynamoDB
        dynamo_manager = get_dynamo_state_manager()
        tabela_ok = dynamo_manager.verificar_tabela()
        
        if not tabela_ok:
            raise Exception("Tabela DynamoDB não está acessível")
        
        return HealthResponse(
            status="ready",
            message="Todos os sistemas estão prontos"
        )
        
    except Exception as e:
        logger.error("Readiness check falhou", error=str(e))
        raise HTTPException(
            status_code=503,
            detail=f"Sistema não está pronto: {str(e)}"
        )


@app.get("/")
def root():
    """Endpoint raiz"""
    return {
        "service": "WhatsApp Orchestrator",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "webhook": "/webhook/whatsapp",
            "health": "/healthz",
            "readiness": "/readyz"
        }
    }


# Event handlers
@app.on_event("startup")
def startup_event():
    """Evento de inicialização"""
    logger.info("WhatsApp Orchestrator iniciando...")
    
    try:
        # Valida configurações
        settings = get_settings()
        logger.info("Configurações validadas")
        
        # Testa componentes críticos
        dynamo_manager = get_dynamo_state_manager()
        logger.info("DynamoDB conectado")
        
        logger.info("WhatsApp Orchestrator iniciado com sucesso")
        
    except Exception as e:
        logger.error("Erro na inicialização", error=str(e))
        raise


@app.on_event("shutdown")
def shutdown_event():
    """Evento de finalização"""
    logger.info("WhatsApp Orchestrator finalizando...")
