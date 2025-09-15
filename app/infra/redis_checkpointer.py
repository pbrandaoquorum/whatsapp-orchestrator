"""
Redis Checkpointer para LangGraph
Implementa persistência de estado usando Redis
"""
import json
import pickle
from typing import Any, Dict, Optional, Tuple
from langgraph.checkpoint import BaseCheckpointSaver
from app.infra.redis_client import obter_cliente_redis
from app.infra.logging import obter_logger

logger = obter_logger(__name__)


class RedisCheckpointer(BaseCheckpointSaver):
    """
    Checkpointer que usa Redis para persistir estado do LangGraph
    """
    
    def __init__(self, redis_client=None, ttl_seconds: int = 3600):
        """
        Args:
            redis_client: Cliente Redis (usa padrão se None)
            ttl_seconds: TTL para chaves no Redis (1 hora padrão)
        """
        self.redis_client = redis_client or obter_cliente_redis()
        self.ttl_seconds = ttl_seconds
        
        if not self.redis_client:
            raise ValueError("Cliente Redis não disponível")
    
    async def aget(self, config: Dict[str, Any]) -> Optional[Tuple[Dict[str, Any], str]]:
        """Recupera checkpoint do Redis"""
        try:
            thread_id = config.get("configurable", {}).get("thread_id")
            if not thread_id:
                return None
            
            key = f"checkpoint:{thread_id}"
            data = await self.redis_client.get(key)
            
            if not data:
                return None
            
            checkpoint_data = pickle.loads(data)
            return checkpoint_data.get("checkpoint"), checkpoint_data.get("metadata", "")
            
        except Exception as e:
            logger.error(f"Erro ao recuperar checkpoint: {e}")
            return None
    
    async def aput(
        self, 
        config: Dict[str, Any], 
        checkpoint: Dict[str, Any], 
        metadata: str = ""
    ) -> None:
        """Salva checkpoint no Redis"""
        try:
            thread_id = config.get("configurable", {}).get("thread_id")
            if not thread_id:
                logger.warning("thread_id não fornecido para checkpoint")
                return
            
            key = f"checkpoint:{thread_id}"
            data = {
                "checkpoint": checkpoint,
                "metadata": metadata,
                "timestamp": self._get_timestamp()
            }
            
            serialized_data = pickle.dumps(data)
            await self.redis_client.setex(key, self.ttl_seconds, serialized_data)
            
            logger.debug(f"Checkpoint salvo: {thread_id}")
            
        except Exception as e:
            logger.error(f"Erro ao salvar checkpoint: {e}")
    
    async def alist(
        self, 
        config: Dict[str, Any], 
        limit: Optional[int] = None
    ) -> list:
        """Lista checkpoints (implementação básica)"""
        try:
            thread_id = config.get("configurable", {}).get("thread_id")
            if not thread_id:
                return []
            
            key = f"checkpoint:{thread_id}"
            exists = await self.redis_client.exists(key)
            
            if exists:
                return [{"thread_id": thread_id, "timestamp": self._get_timestamp()}]
            
            return []
            
        except Exception as e:
            logger.error(f"Erro ao listar checkpoints: {e}")
            return []
    
    def _get_timestamp(self) -> float:
        """Obtém timestamp atual"""
        import time
        return time.time()


def criar_redis_checkpointer(ttl_seconds: int = 3600) -> RedisCheckpointer:
    """Factory para criar RedisCheckpointer"""
    try:
        return RedisCheckpointer(ttl_seconds=ttl_seconds)
    except Exception as e:
        logger.error(f"Erro ao criar Redis checkpointer: {e}")
        raise
