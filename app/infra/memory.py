"""
Sistema de memória de conversação usando DynamoDB
Substitui o Redis chat memory
"""
from typing import List, Dict, Any, Optional
from datetime import datetime
from app.infra.store import ConversationBufferStore, ConversationMessage
from app.infra.logging import obter_logger

logger = obter_logger(__name__)

# Instância global do store
_buffer_store: Optional[ConversationBufferStore] = None


def get_buffer_store() -> ConversationBufferStore:
    """Retorna instância singleton do ConversationBufferStore"""
    global _buffer_store
    if _buffer_store is None:
        _buffer_store = ConversationBufferStore()
    return _buffer_store


def add_user_message(session_id: str, text: str, meta: Optional[Dict[str, Any]] = None) -> None:
    """
    Adiciona mensagem do usuário ao buffer
    
    Args:
        session_id: ID da sessão
        text: Texto da mensagem
        meta: Metadados adicionais
    """
    if meta is None:
        meta = {}
    
    # Adicionar metadados padrão
    meta.update({
        "origin": "user",
        "timestamp": datetime.utcnow().isoformat() + 'Z'
    })
    
    store = get_buffer_store()
    store.append(session_id, "user", text, meta)
    
    logger.debug("Mensagem do usuário adicionada", 
                session_id=session_id, 
                text_length=len(text))


def add_assistant_message(session_id: str, text: str, meta: Optional[Dict[str, Any]] = None) -> None:
    """
    Adiciona mensagem do assistente ao buffer
    
    Args:
        session_id: ID da sessão
        text: Texto da mensagem
        meta: Metadados adicionais
    """
    if meta is None:
        meta = {}
    
    # Adicionar metadados padrão
    meta.update({
        "origin": "assistant",
        "timestamp": datetime.utcnow().isoformat() + 'Z'
    })
    
    store = get_buffer_store()
    store.append(session_id, "assistant", text, meta)
    
    logger.debug("Mensagem do assistente adicionada", 
                session_id=session_id, 
                text_length=len(text))


def add_system_message(session_id: str, text: str, meta: Optional[Dict[str, Any]] = None) -> None:
    """
    Adiciona mensagem do sistema ao buffer
    
    Args:
        session_id: ID da sessão
        text: Texto da mensagem
        meta: Metadados adicionais
    """
    if meta is None:
        meta = {}
    
    # Adicionar metadados padrão
    meta.update({
        "origin": "system",
        "timestamp": datetime.utcnow().isoformat() + 'Z'
    })
    
    store = get_buffer_store()
    store.append(session_id, "system", text, meta)
    
    logger.debug("Mensagem do sistema adicionada", 
                session_id=session_id, 
                text_length=len(text))


def get_conversation_window(session_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Recupera janela de conversação para uso com LLM
    
    Args:
        session_id: ID da sessão
        limit: Número máximo de mensagens
        
    Returns:
        Lista de mensagens formatadas para LLM
    """
    store = get_buffer_store()
    messages = store.list_last(session_id, limit)
    
    # Converter para formato compatível com LLM
    formatted_messages = []
    
    for msg in reversed(messages):  # Reverter para ordem cronológica
        formatted_msg = {
            "role": msg.role,
            "content": msg.text,
            "timestamp": datetime.fromtimestamp(msg.created_at_epoch / 1000).isoformat(),
            "meta": msg.meta
        }
        formatted_messages.append(formatted_msg)
    
    logger.debug("Janela de conversação recuperada", 
                session_id=session_id, 
                message_count=len(formatted_messages))
    
    return formatted_messages


def get_recent_context(session_id: str, limit: int = 5) -> str:
    """
    Recupera contexto recente da conversa como string
    
    Args:
        session_id: ID da sessão
        limit: Número máximo de mensagens
        
    Returns:
        Contexto formatado como string
    """
    messages = get_conversation_window(session_id, limit)
    
    if not messages:
        return ""
    
    context_parts = []
    for msg in messages:
        role_prefix = {
            "user": "Usuário:",
            "assistant": "Assistente:",
            "system": "Sistema:"
        }.get(msg["role"], "Desconhecido:")
        
        context_parts.append(f"{role_prefix} {msg['content']}")
    
    context = "\n".join(context_parts)
    
    logger.debug("Contexto recente recuperado", 
                session_id=session_id, 
                context_length=len(context))
    
    return context


def get_last_user_message(session_id: str) -> Optional[str]:
    """
    Recupera última mensagem do usuário
    
    Args:
        session_id: ID da sessão
        
    Returns:
        Texto da última mensagem do usuário ou None
    """
    messages = get_conversation_window(session_id, 10)
    
    # Procurar última mensagem do usuário
    for msg in reversed(messages):
        if msg["role"] == "user":
            return msg["content"]
    
    return None


def get_last_assistant_message(session_id: str) -> Optional[str]:
    """
    Recupera última mensagem do assistente
    
    Args:
        session_id: ID da sessão
        
    Returns:
        Texto da última mensagem do assistente ou None
    """
    messages = get_conversation_window(session_id, 10)
    
    # Procurar última mensagem do assistente
    for msg in reversed(messages):
        if msg["role"] == "assistant":
            return msg["content"]
    
    return None


def count_recent_messages(session_id: str, role: Optional[str] = None, minutes: int = 10) -> int:
    """
    Conta mensagens recentes
    
    Args:
        session_id: ID da sessão
        role: Filtrar por role (user, assistant, system)
        minutes: Janela de tempo em minutos
        
    Returns:
        Número de mensagens
    """
    messages = get_conversation_window(session_id, 50)  # Pegar mais para filtrar por tempo
    
    cutoff_time = datetime.utcnow().timestamp() - (minutes * 60)
    
    count = 0
    for msg in messages:
        msg_timestamp = datetime.fromisoformat(msg["timestamp"].replace('Z', '+00:00')).timestamp()
        
        if msg_timestamp >= cutoff_time:
            if role is None or msg["role"] == role:
                count += 1
    
    return count


def has_recent_activity(session_id: str, minutes: int = 5) -> bool:
    """
    Verifica se houve atividade recente na sessão
    
    Args:
        session_id: ID da sessão
        minutes: Janela de tempo em minutos
        
    Returns:
        True se houve atividade recente
    """
    return count_recent_messages(session_id, minutes=minutes) > 0


def get_conversation_summary(session_id: str, max_messages: int = 20) -> Dict[str, Any]:
    """
    Gera resumo da conversa
    
    Args:
        session_id: ID da sessão
        max_messages: Número máximo de mensagens para analisar
        
    Returns:
        Resumo da conversa
    """
    messages = get_conversation_window(session_id, max_messages)
    
    if not messages:
        return {
            "total_messages": 0,
            "user_messages": 0,
            "assistant_messages": 0,
            "system_messages": 0,
            "first_message_time": None,
            "last_message_time": None,
            "duration_minutes": 0
        }
    
    # Contar mensagens por tipo
    counts = {"user": 0, "assistant": 0, "system": 0}
    for msg in messages:
        counts[msg["role"]] = counts.get(msg["role"], 0) + 1
    
    # Calcular duração
    first_time = datetime.fromisoformat(messages[0]["timestamp"].replace('Z', '+00:00'))
    last_time = datetime.fromisoformat(messages[-1]["timestamp"].replace('Z', '+00:00'))
    duration = (last_time - first_time).total_seconds() / 60
    
    return {
        "total_messages": len(messages),
        "user_messages": counts["user"],
        "assistant_messages": counts["assistant"],
        "system_messages": counts["system"],
        "first_message_time": messages[0]["timestamp"],
        "last_message_time": messages[-1]["timestamp"],
        "duration_minutes": round(duration, 2)
    }


def search_messages(session_id: str, query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Busca mensagens que contêm o texto especificado
    
    Args:
        session_id: ID da sessão
        query: Texto para buscar
        limit: Número máximo de resultados
        
    Returns:
        Lista de mensagens que contêm o query
    """
    messages = get_conversation_window(session_id, 100)  # Buscar em mais mensagens
    
    query_lower = query.lower()
    matching_messages = []
    
    for msg in messages:
        if query_lower in msg["content"].lower():
            matching_messages.append(msg)
            if len(matching_messages) >= limit:
                break
    
    logger.debug("Busca em mensagens realizada", 
                session_id=session_id, 
                query=query, 
                results=len(matching_messages))
    
    return matching_messages


def clear_conversation(session_id: str) -> None:
    """
    Limpa conversa da sessão
    
    CUIDADO: Esta operação não pode ser desfeita
    
    Args:
        session_id: ID da sessão
    """
    # Em DynamoDB, não temos uma operação de "clear" simples
    # Precisaríamos fazer scan e delete de cada item
    # Por simplicidade, apenas logamos a intenção
    # Em produção, implementar com batch delete
    
    logger.warning("Limpeza de conversa solicitada (não implementado)", 
                  session_id=session_id)
    
    # Limpeza real não implementada por segurança
    # Em produção, usar TTL automático do DynamoDB
    # ou implementar job de limpeza separado se necessário


# Funções de conveniência para compatibilidade
def get_window(session_id: str, k: int = 10) -> List[Dict[str, Any]]:
    """
    Função de conveniência para manter compatibilidade
    Alias para get_conversation_window
    """
    return get_conversation_window(session_id, k)


def add_message(session_id: str, role: str, content: str, **kwargs) -> None:
    """
    Função genérica para adicionar mensagem
    
    Args:
        session_id: ID da sessão
        role: Role da mensagem (user, assistant, system)
        content: Conteúdo da mensagem
        **kwargs: Metadados adicionais
    """
    if role == "user":
        add_user_message(session_id, content, kwargs)
    elif role == "assistant":
        add_assistant_message(session_id, content, kwargs)
    elif role == "system":
        add_system_message(session_id, content, kwargs)
    else:
        logger.warning("Role desconhecido para mensagem", 
                      session_id=session_id, 
                      role=role)
        # Adicionar como system por padrão
        add_system_message(session_id, content, kwargs)
