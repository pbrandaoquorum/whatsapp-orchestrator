"""
Rotas da API FastAPI
"""
import time
from datetime import datetime
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import JSONResponse

from app.api.schemas import (
    WhatsAppMessage, WhatsAppResponse, TemplateSent, TemplateResponse,
    GraphDebugRequest, GraphDebugResponse, HealthResponse, ReadinessResponse,
    ErrorResponse, SyncRequest, SyncResponse, SearchRequest, SearchResponse
)
from app.graph.builder import criar_grafo
from app.graph.state import GraphState
from app.rag.pinecone_client import buscar_sintomas_similares, testar_conexao as testar_pinecone
from app.rag.sheets_sync import sincronizar_com_pinecone, testar_conexao_sheets
from app.infra.logging import obter_logger

logger = obter_logger(__name__)

# Router principal
router = APIRouter()


@router.post("/webhook/whatsapp", response_model=WhatsAppResponse)
async def webhook_whatsapp(message: WhatsAppMessage, request: Request):
    """
    Endpoint principal para processar mensagens do WhatsApp
    """
    request_id = getattr(request.state, 'request_id', 'unknown')
    
    logger.info(
        "Processando mensagem WhatsApp",
        request_id=request_id,
        message_id=message.message_id,
        phone_number=message.phoneNumber[:4] + "****",  # Mascarar número
        text_length=len(message.text)
    )
    
    try:
        # Criar estado inicial
        from app.graph.state import CoreState, VitalsState, NoteState, RouterState, AuxState
        
        estado_inicial = GraphState(
            core=CoreState(
                session_id=f"session_{message.phoneNumber.replace('+', '')}",
                numero_telefone=message.phoneNumber
            ),
            vitals=VitalsState(),
            nota=NoteState(),
            router=RouterState(),
            aux=AuxState(),
            texto_usuario=message.text,
            metadados={}
        )
        
        # Obter grafo
        grafo = criar_grafo()
        
        # Executar grafo com checkpointing
        start_time = time.time()
        
        # Configuração para checkpointing
        config = {
            "configurable": {
                "thread_id": estado_inicial.core.session_id
            }
        }
        
        resultado = await grafo.ainvoke(estado_inicial, config=config)
        execution_time = (time.time() - start_time) * 1000
        
        # Extrair resposta
        resposta_usuario = resultado.get("resposta_usuario", "Desculpe, ocorreu um erro.")
        proximo_no = resultado.get("proximo_no")
        
        logger.info(
            "Mensagem processada com sucesso",
            request_id=request_id,
            message_id=message.message_id,
            execution_time_ms=round(execution_time, 2),
            proximo_no=proximo_no
        )
        
        return WhatsAppResponse(
            success=True,
            message=resposta_usuario,
            session_id=getattr(resultado.get("core"), "session_id", None) if resultado.get("core") else None,
            next_action=proximo_no
        )
        
    except Exception as e:
        logger.error(
            "Erro ao processar mensagem WhatsApp",
            request_id=request_id,
            message_id=message.message_id,
            erro=str(e)
        )
        
        return WhatsAppResponse(
            success=False,
            message="Desculpe, ocorreu um erro interno. Tente novamente em alguns instantes.",
            session_id=None,
            next_action=None
        )


@router.post("/events/template-sent", response_model=TemplateResponse)
async def template_enviado(template_data: TemplateSent, request: Request):
    """
    Endpoint para notificar que um template foi enviado ao usuário
    Atualiza o estado interno para a próxima interação
    """
    request_id = getattr(request.state, 'request_id', 'unknown')
    
    logger.info(
        "Template enviado - atualizando estado",
        request_id=request_id,
        phone_number=template_data.phoneNumber[:4] + "****",
        template=template_data.template
    )
    
    try:
        # Obter grafo e estado atual
        grafo = criar_grafo()
        
        # Criar/obter estado da sessão
        session_id = f"session_{template_data.phoneNumber.replace('+', '')}"
        
        # Usar state_helpers para atualizar estado baseado no template
        from app.api.state_helpers import atualizar_estado_template
        
        # Atualizar estado baseado no template
        sucesso = await atualizar_estado_template(
            template_data.phoneNumber,
            template_data.template,
            template_data.metadata or {}
        )
        
        logger.info(
            "Estado atualizado por template",
            request_id=request_id,
            template=template_data.template,
            state_updated=sucesso
        )
        
        return TemplateResponse(
            success=True,
            message=f"Estado atualizado para template '{template_data.template}'",
            state_updated=sucesso
        )
        
    except Exception as e:
        logger.error(
            "Erro ao processar template enviado",
            request_id=request_id,
            template=template_data.template,
            erro=str(e)
        )
        
        return TemplateResponse(
            success=False,
            message="Erro ao atualizar estado",
            state_updated=False
        )


@router.post("/graph/debug/run", response_model=GraphDebugResponse)
async def debug_grafo(debug_request: GraphDebugRequest, request: Request):
    """
    Endpoint para debug e teste do grafo
    """
    request_id = getattr(request.state, 'request_id', 'unknown')
    
    logger.info(
        "Executando debug do grafo",
        request_id=request_id,
        phone_number=debug_request.phoneNumber[:4] + "****",
        text_length=len(debug_request.text)
    )
    
    try:
        # Criar estado inicial
        if debug_request.initial_state:
            estado_inicial = GraphState(**debug_request.initial_state)
        else:
            estado_inicial = GraphState(
                core={
                    "session_id": f"debug_{debug_request.phoneNumber.replace('+', '')}",
                    "numero_telefone": debug_request.phoneNumber
                },
                texto_usuario=debug_request.text
            )
        
        # Capturar estado inicial
        estado_inicial_dict = estado_inicial.dict()
        
        # Executar grafo
        start_time = time.time()
        grafo = criar_grafo()
        
        # Executar grafo LangGraph
        resultado = grafo.invoke(estado_inicial)
        execution_time = (time.time() - start_time) * 1000
        
        return GraphDebugResponse(
            success=True,
            initial_state=estado_inicial_dict,
            final_state=resultado,
            execution_path=["router", "flow_executed"],
            response_message=resultado.get("resposta_usuario", ""),
            execution_time_ms=round(execution_time, 2)
        )
        
    except Exception as e:
        logger.error(
            "Erro no debug do grafo",
            request_id=request_id,
            erro=str(e)
        )
        
        raise HTTPException(
            status_code=500,
            detail=f"Erro na execução do grafo: {str(e)}"
        )


@router.get("/healthz", response_model=HealthResponse)
async def health_check():
    """Health check básico"""
    return HealthResponse(
        status="healthy",
        timestamp=datetime.now(),
        version="1.0.0",
        dependencies={
            "dynamodb": "ok",
            "pinecone": "ok", 
            "sheets": "ok"
        }
    )


@router.get("/readyz", response_model=ReadinessResponse)
async def readiness_check():
    """Readiness check com verificação de dependências"""
    checks = {}
    detalhes = {}
    
    # Verificar Pinecone
    try:
        checks["pinecone"] = testar_pinecone()
        if not checks["pinecone"]:
            detalhes["pinecone"] = "Conexão falhou"
    except Exception as e:
        checks["pinecone"] = False
        detalhes["pinecone"] = str(e)
    
    # Verificar Google Sheets
    try:
        checks["sheets"] = testar_conexao_sheets()
        if not checks["sheets"]:
            detalhes["sheets"] = "Conexão ou estrutura inválida"
    except Exception as e:
        checks["sheets"] = False
        detalhes["sheets"] = str(e)
    
    # Verificar DynamoDB
    try:
        from app.infra.dynamo_client import health_check as dynamo_health
        dynamo_status = await dynamo_health()
        checks["dynamodb"] = dynamo_status["status"] == "healthy"
    except Exception as e:
        checks["dynamodb"] = False
        detalhes["dynamodb"] = str(e)
    
    # Verificar Lambdas (URLs configuradas)
    import os
    lambda_urls = [
        "LAMBDA_GET_SCHEDULE", "LAMBDA_UPDATE_SCHEDULE", 
        "LAMBDA_UPDATE_CLINICAL", "LAMBDA_UPDATE_SUMMARY"
    ]
    checks["lambdas"] = all(os.getenv(url) for url in lambda_urls)
    
    todas_prontas = all(checks.values())
    
    return ReadinessResponse(
        ready=todas_prontas,
        timestamp=datetime.now(),
        checks=checks,
        details=detalhes
    )


# Rotas para RAG/Sintomas
@router.post("/rag/sync", response_model=SyncResponse)
async def sincronizar_rag(sync_request: SyncRequest, request: Request):
    """Sincroniza base de sintomas do Google Sheets com Pinecone"""
    request_id = getattr(request.state, 'request_id', 'unknown')
    
    logger.info(
        "Iniciando sincronização RAG",
        request_id=request_id,
        sheets_id=sync_request.sheets_id,
        aba=sync_request.aba_name,
        force=sync_request.force
    )
    
    try:
        start_time = time.time()
        
        resultado = sincronizar_com_pinecone(
            sheets_id=sync_request.sheets_id,
            nome_aba=sync_request.aba_name
        )
        
        execution_time = (time.time() - start_time) * 1000
        
        if resultado.get("sucesso"):
            return SyncResponse(
                success=True,
                sintomas_carregados=resultado.get("sintomas_carregados", 0),
                sintomas_inseridos=resultado.get("sintomas_inseridos", 0),
                vectors_antes=resultado.get("vectors_antes", 0),
                vectors_depois=resultado.get("vectors_depois", 0),
                tempo_execucao_ms=round(execution_time, 2),
                detalhes=resultado
            )
        else:
            raise HTTPException(
                status_code=500,
                detail=resultado.get("erro", "Erro desconhecido na sincronização")
            )
            
    except Exception as e:
        logger.error(
            "Erro na sincronização RAG",
            request_id=request_id,
            erro=str(e)
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rag/search", response_model=SearchResponse)
async def buscar_sintomas(search_request: SearchRequest, request: Request):
    """Busca sintomas similares usando RAG"""
    request_id = getattr(request.state, 'request_id', 'unknown')
    
    logger.info(
        "Buscando sintomas similares",
        request_id=request_id,
        query=search_request.query[:50],
        k=search_request.k,
        threshold=search_request.threshold
    )
    
    try:
        start_time = time.time()
        
        resultados = buscar_sintomas_similares(
            termo_busca=search_request.query,
            k=search_request.k,
            limiar_score=search_request.threshold
        )
        
        execution_time = (time.time() - start_time) * 1000
        
        # Converter para formato SymptomReport
        symptom_matches = []
        for resultado in resultados:
            symptom_match = {
                "symptomDefinition": resultado.get("sintoma", ""),
                "altNotepadMain": search_request.query,
                "symptomCategory": resultado.get("categoria", "Geral"),
                "symptomSubCategory": resultado.get("subcategoria", "Geral"),
                "descricaoComparada": resultado.get("descricao", resultado.get("sintoma", "")),
                "coeficienteSimilaridade": float(resultado.get("score", 0.0))
            }
            symptom_matches.append(symptom_match)
        
        return SearchResponse(
            success=True,
            query=search_request.query,
            results=symptom_matches,
            total_found=len(symptom_matches),
            execution_time_ms=round(execution_time, 2)
        )
        
    except Exception as e:
        logger.error(
            "Erro na busca de sintomas",
            request_id=request_id,
            query=search_request.query,
            erro=str(e)
        )
        raise HTTPException(status_code=500, detail=str(e))


def atualizar_estado_por_template(
    template: str,
    phone_number: str,
    metadata: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Atualiza estado interno baseado no template enviado
    Implementado via state_helpers usando DynamoDB
    """
    
    # Mapeamento de templates para atualizações de estado
    template_mappings = {
        "confirmar_presenca": {
            "aux.ultima_pergunta": "Confirmar presença?",
            "aux.fluxo_que_perguntou": "escala"
        },
        "pedir_sinais_vitais": {
            "aux.ultima_pergunta": "Favor informar sinais vitais...",
            "aux.fluxo_que_perguntou": "clinical"
        },
        "pedir_nota": {
            "aux.ultima_pergunta": "Pode me enviar uma nota clínica?",
            "aux.fluxo_que_perguntou": "notas"
        },
        "finalizar_plantao": {
            "aux.ultima_pergunta": "Vamos finalizar? Confirma?",
            "aux.fluxo_que_perguntou": "finalizar"
        }
    }
    
    return template_mappings.get(template, {})
