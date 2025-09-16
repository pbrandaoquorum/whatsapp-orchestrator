"""
Módulo para gerenciar retomada de fluxos no DynamoDB
"""
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from app.infra.store import SessionStore
from app.infra.logging import obter_logger

logger = obter_logger(__name__)

# Instância global do store
_session_store: Optional[SessionStore] = None


def get_session_store() -> SessionStore:
    """Retorna instância singleton do SessionStore"""
    global _session_store
    if _session_store is None:
        _session_store = SessionStore()
    return _session_store


def set_resume_after(session_id: str, flow: str, payload: Dict[str, Any], ttl_seconds: int = 3600) -> None:
    """
    Configura retomada de fluxo após completar ação atual
    
    Args:
        session_id: ID da sessão
        flow: Nome do fluxo para retomar
        payload: Dados para retomada
        ttl_seconds: TTL para expiração da retomada
    """
    expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)
    
    resume_data = {
        "flow": flow,
        "payload": payload,
        "createdAt": datetime.utcnow().isoformat() + 'Z',
        "expiresAt": expires_at.isoformat() + 'Z'
    }
    
    try:
        session_store = get_session_store()
        session_store.update_metadata(
            session_id=session_id,
            resumeAfter=resume_data
        )
        
        logger.info("Retomada configurada", 
                   session_id=session_id, 
                   flow=flow, 
                   expires_at=expires_at.isoformat())
        
    except Exception as e:
        logger.error("Erro ao configurar retomada", 
                    session_id=session_id, 
                    flow=flow, 
                    error=str(e))
        raise


def get_resume_after(session_id: str) -> Optional[Dict[str, Any]]:
    """
    Recupera configuração de retomada de fluxo
    
    Args:
        session_id: ID da sessão
        
    Returns:
        Dict com dados de retomada ou None se não existe/expirou
    """
    try:
        session_store = get_session_store()
        state, version = session_store.get(session_id)
        
        if not state:
            return None
        
        resume_data = state.get("resumeAfter")
        if not resume_data:
            return None
        
        # Verificar se expirou
        expires_at_str = resume_data.get("expiresAt")
        if expires_at_str:
            try:
                expires_at = datetime.fromisoformat(expires_at_str.replace('Z', '+00:00'))
                if datetime.utcnow().replace(tzinfo=expires_at.tzinfo) > expires_at:
                    logger.debug("Retomada expirada", session_id=session_id)
                    # Limpar retomada expirada
                    clear_resume_after(session_id)
                    return None
            except (ValueError, TypeError) as e:
                logger.warning("Erro ao parsear data de expiração da retomada", 
                             session_id=session_id, 
                             expires_at=expires_at_str, 
                             error=str(e))
                # Se não conseguir parsear, assumir que expirou
                clear_resume_after(session_id)
                return None
        
        logger.debug("Retomada recuperada", 
                    session_id=session_id, 
                    flow=resume_data.get("flow"))
        
        return {
            "flow": resume_data.get("flow"),
            "payload": resume_data.get("payload", {}),
            "created_at": resume_data.get("createdAt"),
            "expires_at": resume_data.get("expiresAt")
        }
        
    except Exception as e:
        logger.error("Erro ao recuperar retomada", 
                    session_id=session_id, 
                    error=str(e))
        return None


def clear_resume_after(session_id: str) -> None:
    """
    Limpa configuração de retomada de fluxo
    
    Args:
        session_id: ID da sessão
    """
    try:
        session_store = get_session_store()
        session_store.update_metadata(
            session_id=session_id,
            resumeAfter=None
        )
        
        logger.debug("Retomada limpa", session_id=session_id)
        
    except Exception as e:
        logger.error("Erro ao limpar retomada", 
                    session_id=session_id, 
                    error=str(e))
        raise


def has_resume_pending(session_id: str) -> bool:
    """
    Verifica se há retomada pendente para a sessão
    
    Args:
        session_id: ID da sessão
        
    Returns:
        True se há retomada pendente válida
    """
    resume_data = get_resume_after(session_id)
    return resume_data is not None


def get_resume_flow(session_id: str) -> Optional[str]:
    """
    Retorna o nome do fluxo para retomada
    
    Args:
        session_id: ID da sessão
        
    Returns:
        Nome do fluxo ou None
    """
    resume_data = get_resume_after(session_id)
    if resume_data:
        return resume_data.get("flow")
    return None


def get_resume_payload(session_id: str) -> Dict[str, Any]:
    """
    Retorna o payload da retomada
    
    Args:
        session_id: ID da sessão
        
    Returns:
        Payload da retomada ou dict vazio
    """
    resume_data = get_resume_after(session_id)
    if resume_data:
        return resume_data.get("payload", {})
    return {}


def set_resume_after_clinical_complete(session_id: str, target_flow: str = "finalizar") -> None:
    """
    Configura retomada após completar dados clínicos
    
    Args:
        session_id: ID da sessão
        target_flow: Fluxo para retomar (default: finalizar)
    """
    payload = {
        "reason": "clinical_completed",
        "timestamp": datetime.utcnow().isoformat() + 'Z'
    }
    
    set_resume_after(session_id, target_flow, payload, ttl_seconds=1800)  # 30 minutos
    
    logger.info("Retomada pós-clínico configurada", 
               session_id=session_id, 
               target_flow=target_flow)


def set_resume_after_presence_required(session_id: str, original_flow: str, original_payload: Dict[str, Any] = None) -> None:
    """
    Configura retomada após confirmar presença
    
    Args:
        session_id: ID da sessão
        original_flow: Fluxo original que foi interrompido
        original_payload: Payload do fluxo original
    """
    if original_payload is None:
        original_payload = {}
    
    payload = {
        "reason": "presence_required",
        "original_flow": original_flow,
        "original_payload": original_payload,
        "timestamp": datetime.utcnow().isoformat() + 'Z'
    }
    
    set_resume_after(session_id, original_flow, payload, ttl_seconds=1800)  # 30 minutos
    
    logger.info("Retomada pós-presença configurada", 
               session_id=session_id, 
               original_flow=original_flow)


def process_resume_if_pending(session_id: str) -> Optional[str]:
    """
    Processa retomada se houver uma pendente
    
    Args:
        session_id: ID da sessão
        
    Returns:
        Nome do fluxo para retomar ou None
    """
    resume_data = get_resume_after(session_id)
    
    if not resume_data:
        return None
    
    flow = resume_data.get("flow")
    payload = resume_data.get("payload", {})
    
    # Limpar retomada (será executada agora)
    clear_resume_after(session_id)
    
    logger.info("Processando retomada", 
               session_id=session_id, 
               flow=flow, 
               reason=payload.get("reason"))
    
    return flow


def cleanup_expired_resumes() -> int:
    """
    Limpa retomadas expiradas (pode ser chamado periodicamente)
    
    Returns:
        Número de retomadas limpas
    """
    # Esta função seria implementada com um scan das sessões
    # Por simplicidade, não implementando agora
    # Em produção, usar um job/lambda separado para limpeza
    logger.debug("Limpeza de retomadas expiradas não implementada")
    return 0
