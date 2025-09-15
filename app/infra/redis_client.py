"""
Cliente Redis para checkpointing do LangGraph e cache
"""
import os
import json
import redis.asyncio as redis
from typing import Optional, Dict, Any, List
from datetime import timedelta

from app.infra.logging import obter_logger
from app.infra.timeutils import agora_br

logger = obter_logger(__name__)

# Configurações Redis
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Cliente global
_redis_client: Optional[redis.Redis] = None


async def obter_cliente_redis() -> redis.Redis:
    """Obtém cliente Redis (singleton)"""
    global _redis_client
    
    if _redis_client is None:
        logger.info("Inicializando cliente Redis", url=REDIS_URL.split('@')[0] + "@***")
        
        _redis_client = redis.from_url(
            REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
            health_check_interval=30
        )
        
        # Testar conexão
        try:
            await _redis_client.ping()
            logger.info("Cliente Redis inicializado com sucesso")
        except Exception as e:
            logger.error(f"Erro ao conectar Redis: {e}")
            _redis_client = None
            raise
    
    return _redis_client


async def fechar_cliente_redis():
    """Fecha conexão Redis"""
    global _redis_client
    
    if _redis_client:
        await _redis_client.close()
        _redis_client = None
        logger.info("Cliente Redis fechado")


class RedisCheckpointer:
    """Checkpointer para LangGraph usando Redis"""
    
    def __init__(self, redis_client: Optional[redis.Redis] = None):
        self.redis_client = redis_client
        self.prefix = "langgraph:checkpoint:"
        self.ttl = timedelta(hours=24)  # TTL padrão de 24 horas
    
    async def _get_client(self) -> redis.Redis:
        """Obtém cliente Redis"""
        if self.redis_client:
            return self.redis_client
        return await obter_cliente_redis()
    
    def _make_key(self, session_id: str, checkpoint_id: Optional[str] = None) -> str:
        """Cria chave Redis para checkpoint"""
        if checkpoint_id:
            return f"{self.prefix}{session_id}:{checkpoint_id}"
        return f"{self.prefix}{session_id}:current"
    
    async def save_checkpoint(
        self,
        session_id: str,
        state: Dict[str, Any],
        checkpoint_id: Optional[str] = None
    ) -> str:
        """Salva checkpoint do estado"""
        try:
            client = await self._get_client()
            
            # Gerar ID se não fornecido
            if not checkpoint_id:
                checkpoint_id = str(int(agora_br().timestamp() * 1000))
            
            # Preparar dados
            checkpoint_data = {
                "state": state,
                "checkpoint_id": checkpoint_id,
                "session_id": session_id,
                "timestamp": agora_br().isoformat(),
                "version": "1.0"
            }
            
            # Serializar
            data_json = json.dumps(checkpoint_data, ensure_ascii=False, default=str)
            
            # Salvar
            key = self._make_key(session_id, checkpoint_id)
            current_key = self._make_key(session_id)
            
            # Pipeline para atomicidade
            pipe = client.pipeline()
            pipe.setex(key, self.ttl, data_json)
            pipe.setex(current_key, self.ttl, data_json)
            await pipe.execute()
            
            logger.debug(
                "Checkpoint salvo",
                session_id=session_id,
                checkpoint_id=checkpoint_id,
                size_bytes=len(data_json)
            )
            
            return checkpoint_id
            
        except Exception as e:
            logger.error(
                "Erro ao salvar checkpoint",
                session_id=session_id,
                checkpoint_id=checkpoint_id,
                erro=str(e)
            )
            raise
    
    async def load_checkpoint(
        self,
        session_id: str,
        checkpoint_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Carrega checkpoint do estado"""
        try:
            client = await self._get_client()
            
            # Determinar chave
            key = self._make_key(session_id, checkpoint_id)
            
            # Carregar dados
            data_json = await client.get(key)
            
            if not data_json:
                logger.debug(
                    "Checkpoint não encontrado",
                    session_id=session_id,
                    checkpoint_id=checkpoint_id
                )
                return None
            
            # Deserializar
            checkpoint_data = json.loads(data_json)
            
            logger.debug(
                "Checkpoint carregado",
                session_id=session_id,
                checkpoint_id=checkpoint_data.get("checkpoint_id"),
                timestamp=checkpoint_data.get("timestamp")
            )
            
            return checkpoint_data.get("state")
            
        except Exception as e:
            logger.error(
                "Erro ao carregar checkpoint",
                session_id=session_id,
                checkpoint_id=checkpoint_id,
                erro=str(e)
            )
            return None
    
    async def list_checkpoints(self, session_id: str) -> List[Dict[str, Any]]:
        """Lista checkpoints de uma sessão"""
        try:
            client = await self._get_client()
            
            # Buscar todas as chaves da sessão
            pattern = f"{self.prefix}{session_id}:*"
            keys = await client.keys(pattern)
            
            checkpoints = []
            
            for key in keys:
                if key.endswith(":current"):
                    continue  # Pular chave current
                
                data_json = await client.get(key)
                if data_json:
                    checkpoint_data = json.loads(data_json)
                    checkpoints.append({
                        "checkpoint_id": checkpoint_data.get("checkpoint_id"),
                        "timestamp": checkpoint_data.get("timestamp"),
                        "session_id": checkpoint_data.get("session_id")
                    })
            
            # Ordenar por timestamp
            checkpoints.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
            
            return checkpoints
            
        except Exception as e:
            logger.error(
                "Erro ao listar checkpoints",
                session_id=session_id,
                erro=str(e)
            )
            return []
    
    async def delete_checkpoint(
        self,
        session_id: str,
        checkpoint_id: Optional[str] = None
    ) -> bool:
        """Deleta checkpoint"""
        try:
            client = await self._get_client()
            
            if checkpoint_id:
                # Deletar checkpoint específico
                key = self._make_key(session_id, checkpoint_id)
                deleted = await client.delete(key)
            else:
                # Deletar todos os checkpoints da sessão
                pattern = f"{self.prefix}{session_id}:*"
                keys = await client.keys(pattern)
                if keys:
                    deleted = await client.delete(*keys)
                else:
                    deleted = 0
            
            logger.info(
                "Checkpoint(s) deletado(s)",
                session_id=session_id,
                checkpoint_id=checkpoint_id,
                deleted_count=deleted
            )
            
            return deleted > 0
            
        except Exception as e:
            logger.error(
                "Erro ao deletar checkpoint",
                session_id=session_id,
                checkpoint_id=checkpoint_id,
                erro=str(e)
            )
            return False


class RedisCache:
    """Cache genérico usando Redis"""
    
    def __init__(self, redis_client: Optional[redis.Redis] = None, prefix: str = "cache:"):
        self.redis_client = redis_client
        self.prefix = prefix
        self.default_ttl = timedelta(minutes=30)
    
    async def _get_client(self) -> redis.Redis:
        """Obtém cliente Redis"""
        if self.redis_client:
            return self.redis_client
        return await obter_cliente_redis()
    
    def _make_key(self, key: str) -> str:
        """Cria chave Redis com prefix"""
        return f"{self.prefix}{key}"
    
    async def get(self, key: str) -> Optional[Any]:
        """Obtém valor do cache"""
        try:
            client = await self._get_client()
            redis_key = self._make_key(key)
            
            data = await client.get(redis_key)
            
            if data:
                return json.loads(data)
            
            return None
            
        except Exception as e:
            logger.error(f"Erro ao obter do cache: {e}", key=key)
            return None
    
    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[timedelta] = None
    ) -> bool:
        """Define valor no cache"""
        try:
            client = await self._get_client()
            redis_key = self._make_key(key)
            ttl = ttl or self.default_ttl
            
            data = json.dumps(value, ensure_ascii=False, default=str)
            
            await client.setex(redis_key, ttl, data)
            
            return True
            
        except Exception as e:
            logger.error(f"Erro ao definir no cache: {e}", key=key)
            return False
    
    async def delete(self, key: str) -> bool:
        """Remove valor do cache"""
        try:
            client = await self._get_client()
            redis_key = self._make_key(key)
            
            deleted = await client.delete(redis_key)
            
            return deleted > 0
            
        except Exception as e:
            logger.error(f"Erro ao deletar do cache: {e}", key=key)
            return False
    
    async def exists(self, key: str) -> bool:
        """Verifica se chave existe no cache"""
        try:
            client = await self._get_client()
            redis_key = self._make_key(key)
            
            return await client.exists(redis_key)
            
        except Exception as e:
            logger.error(f"Erro ao verificar existência no cache: {e}", key=key)
            return False


# Instâncias globais
checkpointer = RedisCheckpointer()
cache = RedisCache()


async def testar_conexao_redis() -> bool:
    """Testa conexão com Redis"""
    try:
        client = await obter_cliente_redis()
        await client.ping()
        
        # Teste de escrita/leitura
        test_key = "test:connection"
        test_value = {"timestamp": agora_br().isoformat()}
        
        await client.setex(test_key, timedelta(seconds=10), json.dumps(test_value))
        result = await client.get(test_key)
        
        if result:
            data = json.loads(result)
            if data.get("timestamp"):
                await client.delete(test_key)
                logger.info("Teste de conexão Redis bem-sucedido")
                return True
        
        return False
        
    except Exception as e:
        logger.error(f"Erro no teste de conexão Redis: {e}")
        return False
