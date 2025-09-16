"""
Sistema de idempotência para endpoints FastAPI usando DynamoDB
"""
import json
import functools
from typing import Optional, Callable, Any, Dict
from fastapi import Request, HTTPException, Response
from fastapi.responses import JSONResponse
from app.infra.store import IdempotencyStore
from app.infra.logging import obter_logger

logger = obter_logger(__name__)

# Instância global do store
_idempotency_store: Optional[IdempotencyStore] = None


def get_idempotency_store() -> IdempotencyStore:
    """Retorna instância singleton do IdempotencyStore"""
    global _idempotency_store
    if _idempotency_store is None:
        _idempotency_store = IdempotencyStore()
    return _idempotency_store


def idempotent(
    header: str = "X-Idempotency-Key",
    ttl: int = 300,
    required: bool = True,
    extract_session_id: Optional[Callable[[Request], str]] = None
):
    """
    Decorador para tornar endpoints idempotentes
    
    Args:
        header: Nome do header com a chave de idempotência
        ttl: TTL em segundos para a chave
        required: Se a chave é obrigatória
        extract_session_id: Função para extrair session_id do request
    
    Returns:
        Decorador
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Encontrar o objeto Request nos argumentos
            request = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
            
            if not request:
                # Se não encontrou Request, executar normalmente
                logger.debug("Request não encontrado, pulando idempotência")
                return await func(*args, **kwargs)
            
            # Extrair chave de idempotência
            idempotency_key = request.headers.get(header)
            
            if not idempotency_key:
                if required:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Header {header} é obrigatório para este endpoint"
                    )
                else:
                    # Se não é obrigatório, executar normalmente
                    return await func(*args, **kwargs)
            
            # Extrair session_id se função foi fornecida
            session_id = "unknown"
            if extract_session_id:
                try:
                    session_id = extract_session_id(request)
                except Exception as e:
                    logger.warning("Erro ao extrair session_id", error=str(e))
            
            # Tentar iniciar operação idempotente
            store = get_idempotency_store()
            
            if not store.begin(idempotency_key, session_id, ttl):
                # Chave já existe, verificar se tem resposta cacheada
                cached_response = store.get_cached(idempotency_key)
                
                if cached_response:
                    logger.info("Retornando resposta cacheada", 
                               key=idempotency_key, 
                               session_id=session_id)
                    
                    try:
                        response_data = json.loads(cached_response)
                        return JSONResponse(
                            content=response_data,
                            status_code=200,
                            headers={"X-Idempotency-Replay": "true"}
                        )
                    except json.JSONDecodeError:
                        # Se não conseguir deserializar, retornar como texto
                        return Response(
                            content=cached_response,
                            media_type="application/json",
                            headers={"X-Idempotency-Replay": "true"}
                        )
                else:
                    # Operação em andamento
                    logger.info("Operação idempotente em andamento", 
                               key=idempotency_key, 
                               session_id=session_id)
                    
                    raise HTTPException(
                        status_code=409,
                        detail="Operação já está sendo processada",
                        headers={"X-Idempotency-Conflict": "true"}
                    )
            
            # Executar função original
            try:
                logger.debug("Executando operação idempotente", 
                           key=idempotency_key, 
                           session_id=session_id)
                
                result = await func(*args, **kwargs)
                
                # Cachear resultado se for JSONResponse
                if isinstance(result, JSONResponse):
                    response_json = json.dumps(result.body.decode() if hasattr(result.body, 'decode') else result.body)
                elif isinstance(result, dict):
                    response_json = json.dumps(result, ensure_ascii=False)
                else:
                    response_json = str(result)
                
                store.end_ok(idempotency_key, response_json)
                
                logger.info("Operação idempotente concluída com sucesso", 
                           key=idempotency_key, 
                           session_id=session_id)
                
                # Adicionar header indicando que foi processado
                if isinstance(result, JSONResponse):
                    result.headers["X-Idempotency-Processed"] = "true"
                elif isinstance(result, Response):
                    result.headers["X-Idempotency-Processed"] = "true"
                
                return result
                
            except Exception as e:
                # Marcar como erro
                store.end_error(idempotency_key)
                
                logger.error("Erro na operação idempotente", 
                           key=idempotency_key, 
                           session_id=session_id, 
                           error=str(e))
                
                # Re-raise a exceção
                raise
        
        return wrapper
    return decorator


def extract_session_from_phone(request: Request) -> str:
    """
    Extrai session_id do phoneNumber no body do request
    
    Args:
        request: Request FastAPI
        
    Returns:
        session_id extraído
    """
    try:
        # Para requests JSON
        if hasattr(request, '_json_body'):
            body = request._json_body
        else:
            # Fallback - tentar ler do state se disponível
            body = getattr(request.state, 'json_body', {})
        
        phone_number = body.get('phoneNumber', '')
        if phone_number:
            # Converter telefone para session_id (remover + e caracteres especiais)
            session_id = phone_number.replace('+', '').replace('-', '').replace(' ', '')
            return f"session_{session_id}"
        
        return "unknown"
        
    except Exception as e:
        logger.warning("Erro ao extrair session_id do telefone", error=str(e))
        return "unknown"


def extract_session_from_path(request: Request) -> str:
    """
    Extrai session_id do path do request
    
    Args:
        request: Request FastAPI
        
    Returns:
        session_id extraído
    """
    try:
        path_params = request.path_params
        return path_params.get('session_id', 'unknown')
    except Exception as e:
        logger.warning("Erro ao extrair session_id do path", error=str(e))
        return "unknown"


def extract_session_from_query(request: Request) -> str:
    """
    Extrai session_id dos query parameters
    
    Args:
        request: Request FastAPI
        
    Returns:
        session_id extraído
    """
    try:
        query_params = request.query_params
        return query_params.get('session_id', 'unknown')
    except Exception as e:
        logger.warning("Erro ao extrair session_id da query", error=str(e))
        return "unknown"


class IdempotencyMiddleware:
    """
    Middleware para adicionar suporte automático à idempotência
    """
    
    def __init__(self, app, header_name: str = "X-Idempotency-Key"):
        self.app = app
        self.header_name = header_name
    
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        # Adicionar lógica de middleware se necessário
        # Por enquanto, apenas passar adiante
        await self.app(scope, receive, send)


def generate_idempotency_key() -> str:
    """
    Gera chave de idempotência única
    
    Returns:
        Chave única
    """
    import uuid
    return str(uuid.uuid4())


def validate_idempotency_key(key: str) -> bool:
    """
    Valida formato da chave de idempotência
    
    Args:
        key: Chave para validar
        
    Returns:
        True se válida
    """
    if not key or not isinstance(key, str):
        return False
    
    # Deve ter entre 1 e 255 caracteres
    if len(key) < 1 or len(key) > 255:
        return False
    
    # Apenas caracteres alfanuméricos, hífens e underscores
    import re
    if not re.match(r'^[a-zA-Z0-9_-]+$', key):
        return False
    
    return True


async def cleanup_expired_keys() -> int:
    """
    Limpa chaves de idempotência expiradas
    
    Returns:
        Número de chaves limpas
    """
    # Esta função seria implementada com um scan da tabela
    # Por simplicidade, não implementando agora
    # Em produção, usar um job/lambda separado para limpeza
    logger.debug("Limpeza de chaves expiradas não implementada")
    return 0


# Decoradores pré-configurados para casos comuns
webhook_idempotent = functools.partial(
    idempotent,
    header="X-Idempotency-Key",
    ttl=600,  # 10 minutos
    required=True,
    extract_session_id=extract_session_from_phone
)

template_idempotent = functools.partial(
    idempotent,
    header="X-Template-Idempotency-Key",
    ttl=300,  # 5 minutos
    required=False,
    extract_session_id=extract_session_from_phone
)
