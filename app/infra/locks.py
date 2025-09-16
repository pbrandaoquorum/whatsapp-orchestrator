"""
Sistema de locks distribuídos usando DynamoDB
"""
import asyncio
import os
import uuid
from contextlib import asynccontextmanager
from typing import Optional, AsyncGenerator
from app.infra.store import LockStore
from app.infra.logging import obter_logger

logger = obter_logger(__name__)

# Instância global do store
_lock_store: Optional[LockStore] = None

# Identificador único da instância
INSTANCE_ID = str(uuid.uuid4())[:8]
PROCESS_ID = str(os.getpid())
LOCK_OWNER = f"{INSTANCE_ID}#{PROCESS_ID}"


def get_lock_store() -> LockStore:
    """Retorna instância singleton do LockStore"""
    global _lock_store
    if _lock_store is None:
        _lock_store = LockStore()
    return _lock_store


@asynccontextmanager
async def acquire_session_lock(session_id: str, timeout_seconds: int = 10) -> AsyncGenerator[bool, None]:
    """
    Context manager para adquirir lock de sessão
    
    Args:
        session_id: ID da sessão
        timeout_seconds: Timeout para adquirir o lock
        
    Yields:
        True se conseguiu adquirir o lock
        
    Example:
        async with acquire_session_lock("session_123") as locked:
            if locked:
                # Código que precisa do lock
                pass
            else:
                # Lock não foi adquirido
                pass
    """
    resource = f"session:{session_id}"
    lock_acquired = False
    
    try:
        # Tentar adquirir o lock
        lock_acquired = await _acquire_lock_with_retry(resource, timeout_seconds)
        
        if lock_acquired:
            logger.debug("Lock de sessão adquirido", session_id=session_id, owner=LOCK_OWNER)
        else:
            logger.warning("Falha ao adquirir lock de sessão", session_id=session_id, timeout=timeout_seconds)
        
        yield lock_acquired
        
    finally:
        if lock_acquired:
            success = await _release_lock(resource)
            if success:
                logger.debug("Lock de sessão liberado", session_id=session_id, owner=LOCK_OWNER)
            else:
                logger.warning("Falha ao liberar lock de sessão", session_id=session_id, owner=LOCK_OWNER)


@asynccontextmanager
async def acquire_resource_lock(resource: str, ttl_seconds: int = 10, timeout_seconds: int = 10) -> AsyncGenerator[bool, None]:
    """
    Context manager para adquirir lock de recurso genérico
    
    Args:
        resource: Nome do recurso
        ttl_seconds: TTL do lock
        timeout_seconds: Timeout para adquirir o lock
        
    Yields:
        True se conseguiu adquirir o lock
    """
    lock_acquired = False
    
    try:
        # Tentar adquirir o lock
        lock_acquired = await _acquire_lock_with_retry(resource, timeout_seconds, ttl_seconds)
        
        if lock_acquired:
            logger.debug("Lock de recurso adquirido", resource=resource, owner=LOCK_OWNER)
        else:
            logger.warning("Falha ao adquirir lock de recurso", resource=resource, timeout=timeout_seconds)
        
        yield lock_acquired
        
    finally:
        if lock_acquired:
            success = await _release_lock(resource)
            if success:
                logger.debug("Lock de recurso liberado", resource=resource, owner=LOCK_OWNER)
            else:
                logger.warning("Falha ao liberar lock de recurso", resource=resource, owner=LOCK_OWNER)


async def _acquire_lock_with_retry(resource: str, timeout_seconds: int, ttl_seconds: int = 10) -> bool:
    """
    Tenta adquirir lock com retry
    
    Args:
        resource: Nome do recurso
        timeout_seconds: Timeout total
        ttl_seconds: TTL do lock
        
    Returns:
        True se conseguiu adquirir o lock
    """
    lock_store = get_lock_store()
    start_time = asyncio.get_event_loop().time()
    retry_delay = 0.1  # Começar com 100ms
    max_retry_delay = 1.0  # Máximo 1s
    
    while True:
        try:
            # Tentar adquirir o lock
            if lock_store.acquire(resource, LOCK_OWNER, ttl_seconds):
                return True
            
            # Verificar timeout
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed >= timeout_seconds:
                logger.debug("Timeout ao tentar adquirir lock", 
                           resource=resource, 
                           elapsed=elapsed, 
                           timeout=timeout_seconds)
                return False
            
            # Aguardar antes de tentar novamente
            await asyncio.sleep(retry_delay)
            
            # Exponential backoff
            retry_delay = min(retry_delay * 1.5, max_retry_delay)
            
        except Exception as e:
            logger.error("Erro ao tentar adquirir lock", 
                        resource=resource, 
                        error=str(e))
            return False


async def _release_lock(resource: str) -> bool:
    """
    Libera lock
    
    Args:
        resource: Nome do recurso
        
    Returns:
        True se conseguiu liberar o lock
    """
    try:
        lock_store = get_lock_store()
        return lock_store.release(resource, LOCK_OWNER)
    except Exception as e:
        logger.error("Erro ao liberar lock", 
                    resource=resource, 
                    error=str(e))
        return False


async def force_release_session_lock(session_id: str) -> bool:
    """
    Força liberação do lock de sessão (usar com cuidado)
    
    Args:
        session_id: ID da sessão
        
    Returns:
        True se conseguiu liberar
    """
    resource = f"session:{session_id}"
    
    try:
        lock_store = get_lock_store()
        
        # Tentar liberar com nosso owner primeiro
        if lock_store.release(resource, LOCK_OWNER):
            logger.info("Lock de sessão liberado forçadamente", session_id=session_id)
            return True
        
        # Se não conseguiu, pode ser que o lock seja de outro processo
        # Em produção, implementar lógica mais sofisticada
        logger.warning("Não foi possível liberar lock de sessão", session_id=session_id)
        return False
        
    except Exception as e:
        logger.error("Erro ao forçar liberação do lock", 
                    session_id=session_id, 
                    error=str(e))
        return False


async def check_session_lock_status(session_id: str) -> dict:
    """
    Verifica status do lock de sessão
    
    Args:
        session_id: ID da sessão
        
    Returns:
        Dict com informações do lock
    """
    resource = f"session:{session_id}"
    
    try:
        # Tentar adquirir para verificar se está livre
        lock_store = get_lock_store()
        temp_owner = f"check_{uuid.uuid4().hex[:8]}"
        
        if lock_store.acquire(resource, temp_owner, 1):  # TTL de 1 segundo
            # Lock estava livre, liberar imediatamente
            lock_store.release(resource, temp_owner)
            return {
                "locked": False,
                "owner": None,
                "resource": resource
            }
        else:
            return {
                "locked": True,
                "owner": "unknown",  # Não temos como saber sem fazer query
                "resource": resource
            }
            
    except Exception as e:
        logger.error("Erro ao verificar status do lock", 
                    session_id=session_id, 
                    error=str(e))
        return {
            "locked": "unknown",
            "error": str(e),
            "resource": resource
        }


class SessionLockManager:
    """Manager para locks de sessão com interface mais simples"""
    
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.resource = f"session:{session_id}"
        self._locked = False
    
    async def acquire(self, timeout_seconds: int = 10, ttl_seconds: int = 10) -> bool:
        """Adquire lock da sessão"""
        if self._locked:
            logger.warning("Tentativa de adquirir lock já adquirido", session_id=self.session_id)
            return True
        
        self._locked = await _acquire_lock_with_retry(self.resource, timeout_seconds, ttl_seconds)
        return self._locked
    
    async def release(self) -> bool:
        """Libera lock da sessão"""
        if not self._locked:
            return True
        
        success = await _release_lock(self.resource)
        if success:
            self._locked = False
        return success
    
    @property
    def is_locked(self) -> bool:
        """Retorna se o lock está adquirido"""
        return self._locked
    
    async def __aenter__(self):
        """Context manager entry"""
        await self.acquire()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        await self.release()


# Função de conveniência para criar lock manager
def create_session_lock_manager(session_id: str) -> SessionLockManager:
    """
    Cria manager de lock para sessão
    
    Args:
        session_id: ID da sessão
        
    Returns:
        SessionLockManager
    """
    return SessionLockManager(session_id)
