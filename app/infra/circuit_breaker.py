"""
Circuit Breaker para proteger chamadas a serviços externos (LLM, Lambdas)
Implementa padrão Circuit Breaker com fallback automático
"""
import time
import asyncio
from typing import Any, Callable, Dict, Optional, Union
from enum import Enum
from dataclasses import dataclass, field
from functools import wraps

from app.infra.logging import obter_logger
from app.infra.timeutils import agora_br

logger = obter_logger(__name__)


class CircuitState(Enum):
    """Estados do Circuit Breaker"""
    CLOSED = "closed"      # Funcionamento normal
    OPEN = "open"          # Circuito aberto, falhas detectadas
    HALF_OPEN = "half_open"  # Teste se serviço voltou


@dataclass
class CircuitBreakerConfig:
    """Configuração do Circuit Breaker"""
    failure_threshold: int = 5  # Número de falhas para abrir circuito
    timeout_seconds: float = 60.0  # Tempo para tentar half-open
    success_threshold: int = 2  # Sucessos para fechar circuito
    max_timeout: float = 30.0  # Timeout máximo para chamadas


@dataclass
class CircuitBreakerStats:
    """Estatísticas do Circuit Breaker"""
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: Optional[float] = None
    last_success_time: Optional[float] = None
    total_calls: int = 0
    total_failures: int = 0
    total_successes: int = 0
    opened_at: Optional[float] = None


class CircuitBreakerError(Exception):
    """Exceção quando circuito está aberto"""
    pass


class CircuitBreaker:
    """
    Implementação de Circuit Breaker para proteger serviços externos
    """
    
    def __init__(self, name: str, config: Optional[CircuitBreakerConfig] = None):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self.stats = CircuitBreakerStats()
        self._lock = asyncio.Lock()
    
    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Executa função protegida pelo circuit breaker
        """
        async with self._lock:
            # Verificar estado atual
            current_state = await self._get_current_state()
            
            if current_state == CircuitState.OPEN:
                logger.warning(
                    "Circuit breaker aberto - rejeitando chamada",
                    circuit_name=self.name,
                    failure_count=self.stats.failure_count
                )
                raise CircuitBreakerError(f"Circuit breaker {self.name} está aberto")
            
            # Executar chamada
            self.stats.total_calls += 1
            start_time = time.time()
            
            try:
                # Aplicar timeout
                result = await asyncio.wait_for(
                    self._execute_function(func, *args, **kwargs),
                    timeout=self.config.max_timeout
                )
                
                # Registrar sucesso
                await self._record_success()
                
                execution_time = (time.time() - start_time) * 1000
                logger.debug(
                    "Circuit breaker - chamada bem-sucedida",
                    circuit_name=self.name,
                    execution_time_ms=round(execution_time, 2)
                )
                
                return result
                
            except asyncio.TimeoutError:
                await self._record_failure("timeout")
                logger.error(
                    "Circuit breaker - timeout na chamada",
                    circuit_name=self.name,
                    timeout_seconds=self.config.max_timeout
                )
                raise
                
            except Exception as e:
                await self._record_failure(str(e))
                logger.error(
                    "Circuit breaker - falha na chamada",
                    circuit_name=self.name,
                    erro=str(e)
                )
                raise
    
    async def _execute_function(self, func: Callable, *args, **kwargs) -> Any:
        """Executa função de forma assíncrona ou síncrona"""
        if asyncio.iscoroutinefunction(func):
            return await func(*args, **kwargs)
        else:
            return func(*args, **kwargs)
    
    async def _get_current_state(self) -> CircuitState:
        """Determina estado atual do circuit breaker"""
        now = time.time()
        
        # Se está aberto, verificar se pode tentar half-open
        if self.stats.state == CircuitState.OPEN:
            if (self.stats.last_failure_time and 
                now - self.stats.last_failure_time >= self.config.timeout_seconds):
                self.stats.state = CircuitState.HALF_OPEN
                logger.info(
                    "Circuit breaker mudando para half-open",
                    circuit_name=self.name
                )
        
        return self.stats.state
    
    async def _record_success(self):
        """Registra sucesso na chamada"""
        now = time.time()
        self.stats.last_success_time = now
        self.stats.total_successes += 1
        
        if self.stats.state == CircuitState.HALF_OPEN:
            self.stats.success_count += 1
            
            # Se atingiu threshold de sucessos, fechar circuito
            if self.stats.success_count >= self.config.success_threshold:
                self.stats.state = CircuitState.CLOSED
                self.stats.failure_count = 0
                self.stats.success_count = 0
                
                logger.info(
                    "Circuit breaker fechado após sucessos",
                    circuit_name=self.name,
                    success_count=self.stats.success_count
                )
        
        elif self.stats.state == CircuitState.CLOSED:
            # Reset contador de falhas em caso de sucesso
            self.stats.failure_count = max(0, self.stats.failure_count - 1)
    
    async def _record_failure(self, error_type: str):
        """Registra falha na chamada"""
        now = time.time()
        self.stats.last_failure_time = now
        self.stats.total_failures += 1
        self.stats.failure_count += 1
        
        # Se atingiu threshold de falhas, abrir circuito
        if (self.stats.failure_count >= self.config.failure_threshold and 
            self.stats.state != CircuitState.OPEN):
            
            self.stats.state = CircuitState.OPEN
            self.stats.opened_at = now
            self.stats.success_count = 0
            
            logger.error(
                "Circuit breaker aberto devido a falhas",
                circuit_name=self.name,
                failure_count=self.stats.failure_count,
                error_type=error_type
            )
    
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas do circuit breaker"""
        return {
            "name": self.name,
            "state": self.stats.state.value,
            "failure_count": self.stats.failure_count,
            "success_count": self.stats.success_count,
            "total_calls": self.stats.total_calls,
            "total_failures": self.stats.total_failures,
            "total_successes": self.stats.total_successes,
            "success_rate": (
                self.stats.total_successes / max(1, self.stats.total_calls) * 100
            ),
            "last_failure_time": self.stats.last_failure_time,
            "last_success_time": self.stats.last_success_time,
            "opened_at": self.stats.opened_at
        }
    
    async def reset(self):
        """Reset manual do circuit breaker"""
        async with self._lock:
            self.stats.state = CircuitState.CLOSED
            self.stats.failure_count = 0
            self.stats.success_count = 0
            self.stats.opened_at = None
            
            logger.info(
                "Circuit breaker resetado manualmente",
                circuit_name=self.name
            )


# Instâncias globais de circuit breakers
_circuit_breakers: Dict[str, CircuitBreaker] = {}


def get_circuit_breaker(name: str, config: Optional[CircuitBreakerConfig] = None) -> CircuitBreaker:
    """Obtém ou cria circuit breaker para um serviço"""
    if name not in _circuit_breakers:
        _circuit_breakers[name] = CircuitBreaker(name, config)
    
    return _circuit_breakers[name]


def circuit_breaker(
    name: str, 
    config: Optional[CircuitBreakerConfig] = None
):
    """
    Decorator para aplicar circuit breaker a funções
    """
    def decorator(func):
        breaker = get_circuit_breaker(name, config)
        
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await breaker.call(func, *args, **kwargs)
        
        return wrapper
    
    return decorator


# Configurações específicas para diferentes serviços
LLM_CIRCUIT_CONFIG = CircuitBreakerConfig(
    failure_threshold=3,
    timeout_seconds=30.0,
    success_threshold=2,
    max_timeout=15.0
)

LAMBDA_CIRCUIT_CONFIG = CircuitBreakerConfig(
    failure_threshold=5,
    timeout_seconds=60.0,
    success_threshold=2,
    max_timeout=30.0
)

PINECONE_CIRCUIT_CONFIG = CircuitBreakerConfig(
    failure_threshold=3,
    timeout_seconds=45.0,
    success_threshold=2,
    max_timeout=10.0
)


def get_all_circuit_breaker_stats() -> Dict[str, Dict[str, Any]]:
    """Retorna estatísticas de todos os circuit breakers"""
    return {name: cb.get_stats() for name, cb in _circuit_breakers.items()}


async def reset_all_circuit_breakers():
    """Reset de todos os circuit breakers"""
    for cb in _circuit_breakers.values():
        await cb.reset()
    
    logger.info("Todos os circuit breakers foram resetados")
