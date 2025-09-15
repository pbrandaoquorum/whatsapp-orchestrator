"""
Sistema de cache inteligente para otimizar chamadas LLM e Lambda
Implementa cache em memória e Redis com TTL e invalidação automática
"""
import json
import hashlib
from typing import Any, Dict, Optional, Union, Callable
from datetime import datetime, timedelta
from functools import wraps
import asyncio

from app.infra.logging import obter_logger
from app.infra.redis_client import obter_cliente_redis
from app.infra.timeutils import agora_br

logger = obter_logger(__name__)


class CacheConfig:
    """Configuração de cache"""
    def __init__(
        self,
        ttl_seconds: int = 300,  # 5 minutos default
        use_redis: bool = True,
        use_memory: bool = True,
        max_memory_entries: int = 1000
    ):
        self.ttl_seconds = ttl_seconds
        self.use_redis = use_redis
        self.use_memory = use_memory
        self.max_memory_entries = max_memory_entries


# Cache em memória (LRU simples)
_memory_cache: Dict[str, Dict[str, Any]] = {}
_memory_cache_access: Dict[str, datetime] = {}


def _gerar_chave_cache(*args, **kwargs) -> str:
    """Gera chave única para cache baseada nos argumentos"""
    # Criar string determinística dos argumentos
    cache_data = {
        "args": args,
        "kwargs": {k: v for k, v in kwargs.items() if k != "estado"}  # Excluir estado completo
    }
    
    # Incluir apenas campos relevantes do estado se presente
    if "estado" in kwargs:
        estado = kwargs["estado"]
        cache_data["estado_key"] = {
            "session_id": getattr(estado.core, "session_id", None),
            "texto_usuario": getattr(estado, "texto_usuario", None),
            "cancelado": getattr(estado.core, "cancelado", False),
            "turno_permitido": getattr(estado.core, "turno_permitido", True)
        }
    
    # Gerar hash MD5 da representação JSON
    cache_str = json.dumps(cache_data, sort_keys=True, default=str)
    return hashlib.md5(cache_str.encode()).hexdigest()


async def _get_from_redis(chave: str) -> Optional[Any]:
    """Recupera valor do cache Redis"""
    try:
        redis_client = obter_cliente_redis()
        if redis_client:
            valor_str = await redis_client.get(f"cache:{chave}")
            if valor_str:
                return json.loads(valor_str)
    except Exception as e:
        logger.warning(f"Erro ao ler cache Redis: {e}")
    
    return None


async def _set_to_redis(chave: str, valor: Any, ttl_seconds: int):
    """Armazena valor no cache Redis"""
    try:
        redis_client = obter_cliente_redis()
        if redis_client:
            valor_str = json.dumps(valor, default=str)
            await redis_client.setex(f"cache:{chave}", ttl_seconds, valor_str)
    except Exception as e:
        logger.warning(f"Erro ao escrever cache Redis: {e}")


def _get_from_memory(chave: str) -> Optional[Any]:
    """Recupera valor do cache em memória"""
    if chave in _memory_cache:
        entrada = _memory_cache[chave]
        
        # Verificar se não expirou
        if datetime.now() < entrada["expires_at"]:
            # Atualizar último acesso para LRU
            _memory_cache_access[chave] = datetime.now()
            return entrada["data"]
        else:
            # Remover entrada expirada
            del _memory_cache[chave]
            if chave in _memory_cache_access:
                del _memory_cache_access[chave]
    
    return None


def _set_to_memory(chave: str, valor: Any, ttl_seconds: int):
    """Armazena valor no cache em memória"""
    # Limpar cache se atingiu limite
    if len(_memory_cache) >= 1000:  # Max entries
        _cleanup_memory_cache()
    
    _memory_cache[chave] = {
        "data": valor,
        "expires_at": datetime.now() + timedelta(seconds=ttl_seconds),
        "created_at": datetime.now()
    }
    _memory_cache_access[chave] = datetime.now()


def _cleanup_memory_cache():
    """Remove entradas antigas do cache em memória (LRU)"""
    if not _memory_cache_access:
        return
    
    # Remover 20% das entradas menos usadas
    sorted_entries = sorted(
        _memory_cache_access.items(),
        key=lambda x: x[1]
    )
    
    entries_to_remove = len(sorted_entries) // 5  # 20%
    
    for chave, _ in sorted_entries[:entries_to_remove]:
        if chave in _memory_cache:
            del _memory_cache[chave]
        if chave in _memory_cache_access:
            del _memory_cache_access[chave]
    
    logger.debug(f"Cache cleanup: removidas {entries_to_remove} entradas")


async def get_cached(chave: str, config: CacheConfig) -> Optional[Any]:
    """Recupera valor do cache (memória -> Redis)"""
    # Tentar cache em memória primeiro
    if config.use_memory:
        valor = _get_from_memory(chave)
        if valor is not None:
            logger.debug(f"Cache hit (memory): {chave[:12]}...")
            return valor
    
    # Tentar cache Redis
    if config.use_redis:
        valor = await _get_from_redis(chave)
        if valor is not None:
            logger.debug(f"Cache hit (redis): {chave[:12]}...")
            
            # Armazenar também em memória para próximas consultas
            if config.use_memory:
                _set_to_memory(chave, valor, config.ttl_seconds)
            
            return valor
    
    logger.debug(f"Cache miss: {chave[:12]}...")
    return None


async def set_cached(chave: str, valor: Any, config: CacheConfig):
    """Armazena valor no cache (memória + Redis)"""
    # Cache em memória
    if config.use_memory:
        _set_to_memory(chave, valor, config.ttl_seconds)
    
    # Cache Redis
    if config.use_redis:
        await _set_to_redis(chave, valor, config.ttl_seconds)
    
    logger.debug(f"Cache set: {chave[:12]}...")


async def invalidate_cache(pattern: str = None, session_id: str = None):
    """Invalida entradas do cache"""
    if session_id:
        # Invalidar cache específico da sessão
        pattern = f"*session_id*{session_id}*"
    
    try:
        # Invalidar Redis
        redis_client = obter_cliente_redis()
        if redis_client and pattern:
            keys = await redis_client.keys(f"cache:*{pattern}*")
            if keys:
                await redis_client.delete(*keys)
                logger.info(f"Cache Redis invalidado: {len(keys)} chaves")
        
        # Invalidar memória
        if pattern:
            chaves_para_remover = []
            for chave in _memory_cache.keys():
                if pattern in chave or (session_id and session_id in chave):
                    chaves_para_remover.append(chave)
            
            for chave in chaves_para_remover:
                if chave in _memory_cache:
                    del _memory_cache[chave]
                if chave in _memory_cache_access:
                    del _memory_cache_access[chave]
            
            logger.info(f"Cache memória invalidado: {len(chaves_para_remover)} chaves")
    
    except Exception as e:
        logger.error(f"Erro ao invalidar cache: {e}")


def cache_result(
    ttl_seconds: int = 300,
    use_redis: bool = True,
    use_memory: bool = True,
    cache_key_func: Optional[Callable] = None
):
    """
    Decorator para cache automático de resultados de funções
    """
    def decorator(func):
        config = CacheConfig(ttl_seconds, use_redis, use_memory)
        
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Gerar chave do cache
            if cache_key_func:
                chave = cache_key_func(*args, **kwargs)
            else:
                chave = f"{func.__name__}:{_gerar_chave_cache(*args, **kwargs)}"
            
            # Tentar recuperar do cache
            resultado_cache = await get_cached(chave, config)
            if resultado_cache is not None:
                return resultado_cache
            
            # Executar função
            if asyncio.iscoroutinefunction(func):
                resultado = await func(*args, **kwargs)
            else:
                resultado = func(*args, **kwargs)
            
            # Armazenar no cache
            await set_cached(chave, resultado, config)
            
            return resultado
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            return asyncio.run(async_wrapper(*args, **kwargs))
        
        # Retornar wrapper apropriado
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


# Configurações específicas para diferentes tipos de cache
LLM_CACHE_CONFIG = CacheConfig(
    ttl_seconds=1800,  # 30 minutos
    use_redis=True,
    use_memory=True
)

LAMBDA_CACHE_CONFIG = CacheConfig(
    ttl_seconds=300,   # 5 minutos
    use_redis=True,
    use_memory=False   # Lambdas não devem usar cache em memória
)

RAG_CACHE_CONFIG = CacheConfig(
    ttl_seconds=3600,  # 1 hora
    use_redis=True,
    use_memory=True
)


async def get_cache_stats() -> Dict[str, Any]:
    """Retorna estatísticas do cache"""
    stats = {
        "memory": {
            "entries": len(_memory_cache),
            "max_entries": 1000,
            "usage_percent": len(_memory_cache) / 1000 * 100
        },
        "redis": {
            "available": False,
            "entries": 0
        }
    }
    
    try:
        redis_client = obter_cliente_redis()
        if redis_client:
            # Contar chaves de cache no Redis
            keys = await redis_client.keys("cache:*")
            stats["redis"]["available"] = True
            stats["redis"]["entries"] = len(keys)
    except Exception as e:
        logger.warning(f"Erro ao obter stats Redis: {e}")
    
    return stats


async def clear_all_cache():
    """Limpa todo o cache (memória + Redis)"""
    # Limpar memória
    global _memory_cache, _memory_cache_access
    _memory_cache.clear()
    _memory_cache_access.clear()
    
    # Limpar Redis
    try:
        redis_client = obter_cliente_redis()
        if redis_client:
            keys = await redis_client.keys("cache:*")
            if keys:
                await redis_client.delete(*keys)
                logger.info(f"Cache Redis limpo: {len(keys)} chaves removidas")
    except Exception as e:
        logger.error(f"Erro ao limpar cache Redis: {e}")
    
    logger.info("Cache completamente limpo")


# Decorators específicos para uso comum
llm_cache = lambda ttl=1800: cache_result(ttl, True, True)
lambda_cache = lambda ttl=300: cache_result(ttl, True, False)
rag_cache = lambda ttl=3600: cache_result(ttl, True, True)
