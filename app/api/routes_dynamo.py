"""
Novas rotas da API FastAPI usando DynamoDB
"""
import json
import time
from datetime import datetime
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import JSONResponse

from app.api.schemas import (
    WhatsAppMessage, WhatsAppResponse, TemplateSent, TemplateResponse,
    HealthResponse, ReadinessResponse
)
from app.graph.builder import criar_grafo
from app.graph.state import GraphState
from app.infra.state_persistence import get_state_manager, StateManager
from app.infra.locks import acquire_session_lock
from app.infra.idempotency import webhook_idempotent, template_idempotent
from app.infra.memory import add_user_message, add_assistant_message
from app.infra.resume import process_resume_if_pending
from app.infra.dynamo_client import health_check as dynamo_health_check
from app.infra.logging import obter_logger

logger = obter_logger(__name__)

# Router principal
router = APIRouter()


@router.post("/webhook/ingest", response_model=WhatsAppResponse)
@webhook_idempotent
async def webhook_ingest(
    message: WhatsAppMessage, 
    request: Request,
    state_manager: StateManager = Depends(get_state_manager)
):
    """
    Endpoint principal para processar mensagens do usuário com DynamoDB
    """
    request_id = getattr(request.state, 'request_id', 'unknown')
    session_id = state_manager.session_id
    
    logger.info(
        "Processando mensagem via DynamoDB",
        request_id=request_id,
        message_id=message.message_id,
        session_id=session_id,
        phone_number=message.phoneNumber[:4] + "****",  # Mascarar número
        text_length=len(message.text)
    )
    
    try:
        # Adquirir lock da sessão
        async with acquire_session_lock(session_id) as locked:
            if not locked:
                logger.warning("Não foi possível adquirir lock da sessão", session_id=session_id)
                raise HTTPException(
                    status_code=429, 
                    detail="Sessão está sendo processada por outra operação"
                )
            
            # Carregar estado da sessão
            estado = await state_manager.load_state()
            
            # Atualizar texto do usuário
            estado.texto_usuario = message.text
            
            # Adicionar mensagem do usuário ao buffer de conversação
            add_user_message(session_id, message.text, {
                "message_id": message.message_id,
                "origin": "webhook_ingest"
            })
            
            # Verificar se há retomada pendente
            resume_flow = process_resume_if_pending(session_id)
            if resume_flow:
                logger.info("Processando retomada de fluxo", 
                           session_id=session_id, 
                           resume_flow=resume_flow)
                # O router vai detectar a retomada automaticamente
            
            # Executar grafo LangGraph
            grafo = criar_grafo()
            config = {"configurable": {"thread_id": session_id}}
            
            inicio = time.time()
            resultado = grafo.invoke(estado, config=config)
            tempo_execucao = (time.time() - inicio) * 1000
            
            # Extrair resposta
            resposta_texto = resultado.resposta_usuario or "Mensagem processada"
            proximo_no = resultado.proximo_no
            
            # Adicionar resposta do assistente ao buffer
            add_assistant_message(session_id, resposta_texto, {
                "next_node": proximo_no,
                "execution_time_ms": round(tempo_execucao, 2),
                "origin": "langgraph_response"
            })
            
            # Salvar estado (será feito automaticamente pelo StateManager)
            await state_manager.save_state()
            
            logger.info(
                "Mensagem processada com sucesso",
                request_id=request_id,
                session_id=session_id,
                tempo_execucao_ms=round(tempo_execucao, 2),
                proximo_no=proximo_no
            )
            
            return WhatsAppResponse(
                success=True,
                message=resposta_texto,
                session_id=session_id,
                next_action=proximo_no,
                execution_time_ms=round(tempo_execucao, 2)
            )
    
    except HTTPException:
        # Re-raise HTTPExceptions
        raise
    except Exception as e:
        logger.error(
            "Erro ao processar mensagem",
            request_id=request_id,
            session_id=session_id,
            error=str(e),
            exc_info=True
        )
        raise HTTPException(status_code=500, detail="Erro interno do servidor")


@router.post("/hooks/template-fired", response_model=TemplateResponse)
@template_idempotent
async def template_fired(
    template_data: TemplateSent, 
    request: Request,
    state_manager: StateManager = Depends(get_state_manager)
):
    """
    Endpoint chamado quando webhook externo dispara um template
    Atualiza estado no DynamoDB para preparar próxima interação
    """
    request_id = getattr(request.state, 'request_id', 'unknown')
    session_id = state_manager.session_id
    
    logger.info(
        "Template disparado",
        request_id=request_id,
        session_id=session_id,
        template=template_data.template,
        phone_number=template_data.phoneNumber[:4] + "****"
    )
    
    try:
        # Adquirir lock da sessão
        async with acquire_session_lock(session_id) as locked:
            if not locked:
                logger.warning("Não foi possível adquirir lock para template", session_id=session_id)
                raise HTTPException(
                    status_code=429, 
                    detail="Sessão está sendo processada"
                )
            
            # Carregar estado
            estado = await state_manager.load_state()
            
            # Atualizar estado baseado no template
            template_name = template_data.template
            metadata = template_data.metadata or {}
            
            if template_name == "pedir_sinais_vitais":
                estado.aux.ultima_pergunta = "Aguardando sinais vitais..."
                estado.aux.fluxo_que_perguntou = "clinical"
                
                # Se há campos faltantes nos metadados, usar
                if "hint_campos_faltantes" in metadata:
                    estado.vitais.faltantes = metadata["hint_campos_faltantes"]
                
                logger.info("Estado preparado para coleta de sinais vitais", session_id=session_id)
            
            elif template_name == "confirmar_presenca":
                estado.aux.ultima_pergunta = "Aguardando confirmação de presença..."
                estado.aux.fluxo_que_perguntou = "escala"
                
                logger.info("Estado preparado para confirmação de presença", session_id=session_id)
            
            elif template_name == "pedir_nota_clinica":
                estado.aux.ultima_pergunta = "Aguardando nota clínica..."
                estado.aux.fluxo_que_perguntou = "notas"
                
                logger.info("Estado preparado para nota clínica", session_id=session_id)
            
            elif template_name == "finalizar_plantao":
                estado.aux.ultima_pergunta = "Aguardando confirmação para finalizar..."
                estado.aux.fluxo_que_perguntou = "finalizar"
                
                logger.info("Estado preparado para finalização", session_id=session_id)
            
            else:
                logger.warning("Template desconhecido", template=template_name, session_id=session_id)
            
            # Adicionar metadados do template ao estado
            if not estado.metadados:
                estado.metadados = {}
            
            estado.metadados.update({
                "last_template": template_name,
                "template_fired_at": datetime.utcnow().isoformat() + 'Z',
                "template_metadata": metadata
            })
            
            # Salvar estado
            await state_manager.save_state()
            
            # Adicionar ao buffer de conversação
            add_assistant_message(session_id, f"Template '{template_name}' disparado", {
                "template": template_name,
                "metadata": metadata,
                "origin": "template_fired"
            })
            
            logger.info(
                "Template processado com sucesso",
                request_id=request_id,
                session_id=session_id,
                template=template_name
            )
            
            return TemplateResponse(
                success=True,
                message=f"Template '{template_name}' processado",
                session_id=session_id,
                template=template_name,
                updated_state=True
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Erro ao processar template",
            request_id=request_id,
            session_id=session_id,
            template=template_data.template,
            error=str(e),
            exc_info=True
        )
        raise HTTPException(status_code=500, detail="Erro interno do servidor")


@router.get("/healthz", response_model=HealthResponse)
async def health_check():
    """
    Health check básico
    """
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow().isoformat() + 'Z',
        version="2.0.0-dynamo"
    )


@router.get("/readyz", response_model=ReadinessResponse)
async def readiness_check():
    """
    Readiness check com verificação de dependências
    """
    checks = {}
    overall_status = "ready"
    
    # Verificar DynamoDB
    try:
        dynamo_health = await dynamo_health_check()
        checks["dynamodb"] = dynamo_health
        
        if dynamo_health["status"] != "healthy":
            overall_status = "not_ready"
    except Exception as e:
        checks["dynamodb"] = {"status": "error", "error": str(e)}
        overall_status = "not_ready"
    
    # Verificar OpenAI (se configurado)
    import os
    if os.getenv("OPENAI_API_KEY"):
        checks["openai"] = {"status": "configured"}
    else:
        checks["openai"] = {"status": "not_configured"}
        overall_status = "degraded"
    
    # Verificar Lambdas (básico)
    lambda_urls = [
        "LAMBDA_GET_SCHEDULE",
        "LAMBDA_UPDATE_SCHEDULE", 
        "LAMBDA_UPDATE_CLINICAL",
        "LAMBDA_UPDATE_SUMMARY"
    ]
    
    lambda_status = "configured"
    for url_env in lambda_urls:
        if not os.getenv(url_env):
            lambda_status = "not_configured"
            overall_status = "degraded"
            break
    
    checks["lambdas"] = {"status": lambda_status}
    
    return ReadinessResponse(
        status=overall_status,
        timestamp=datetime.utcnow().isoformat() + 'Z',
        checks=checks
    )


@router.get("/sessions/{session_id}/state")
async def get_session_state(session_id: str):
    """
    Endpoint para debug - retorna estado atual da sessão
    """
    try:
        from app.infra.store import SessionStore
        
        store = SessionStore()
        state_dict, version = store.get(session_id)
        
        if not state_dict:
            raise HTTPException(status_code=404, detail="Sessão não encontrada")
        
        return {
            "session_id": session_id,
            "version": version,
            "state": state_dict,
            "retrieved_at": datetime.utcnow().isoformat() + 'Z'
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Erro ao buscar estado da sessão", session_id=session_id, error=str(e))
        raise HTTPException(status_code=500, detail="Erro interno")


@router.get("/sessions/{session_id}/conversation")
async def get_session_conversation(session_id: str, limit: int = 20):
    """
    Endpoint para debug - retorna histórico de conversação
    """
    try:
        from app.infra.memory import get_conversation_window
        
        messages = get_conversation_window(session_id, limit)
        
        return {
            "session_id": session_id,
            "message_count": len(messages),
            "messages": messages,
            "retrieved_at": datetime.utcnow().isoformat() + 'Z'
        }
        
    except Exception as e:
        logger.error("Erro ao buscar conversa da sessão", session_id=session_id, error=str(e))
        raise HTTPException(status_code=500, detail="Erro interno")


@router.post("/sessions/{session_id}/clear")
async def clear_session(session_id: str):
    """
    Endpoint para debug - limpa estado da sessão (CUIDADO!)
    """
    try:
        from app.infra.store import SessionStore
        
        # Por segurança, apenas marcar como versão 0 (será recriado)
        store = SessionStore()
        
        # Não implementamos delete real por segurança
        # Em produção, implementar com mais cuidados
        
        logger.warning("Solicitação de limpeza de sessão", session_id=session_id)
        
        return {
            "session_id": session_id,
            "action": "clear_requested",
            "note": "Implementação de limpeza não ativa por segurança",
            "timestamp": datetime.utcnow().isoformat() + 'Z'
        }
        
    except Exception as e:
        logger.error("Erro ao limpar sessão", session_id=session_id, error=str(e))
        raise HTTPException(status_code=500, detail="Erro interno")


# Endpoints para debug e monitoramento
@router.get("/debug/dynamo/tables")
async def debug_dynamo_tables():
    """
    Lista status das tabelas DynamoDB
    """
    try:
        from app.infra.dynamo_client import get_all_table_names, validate_table_exists
        
        table_status = {}
        for table_name in get_all_table_names():
            exists = validate_table_exists(table_name)
            table_status[table_name] = {
                "exists": exists,
                "status": "ready" if exists else "missing"
            }
        
        return {
            "tables": table_status,
            "timestamp": datetime.utcnow().isoformat() + 'Z'
        }
        
    except Exception as e:
        logger.error("Erro ao verificar tabelas", error=str(e))
        raise HTTPException(status_code=500, detail="Erro interno")


@router.get("/metrics/sessions")
async def get_session_metrics():
    """
    Métricas básicas das sessões (implementação futura)
    """
    # Em produção, implementar com scan das tabelas
    return {
        "active_sessions": "not_implemented",
        "total_messages_today": "not_implemented", 
        "avg_response_time": "not_implemented",
        "timestamp": datetime.utcnow().isoformat() + 'Z'
    }
