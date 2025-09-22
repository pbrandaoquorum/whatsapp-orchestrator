"""
Configuração de logging estruturado em PT-BR
"""
import sys
import structlog
from structlog.processors import TimeStamper, add_log_level, JSONRenderer


def configure_logging(log_level: str = "INFO"):
    """
    Configura logging estruturado com structlog
    Logs em PT-BR e formato JSON para produção
    """
    
    # Processadores do structlog
    processors = [
        # Adiciona timestamp
        TimeStamper(fmt="iso", utc=True),
        # Adiciona nível do log
        add_log_level,
        # Adiciona informações do logger
        structlog.stdlib.add_logger_name,
        # Renderiza como JSON
        JSONRenderer(ensure_ascii=False)
    ]
    
    # Configura structlog
    structlog.configure(
        processors=processors,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    # Configura nível de log
    import logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper())
    )


def get_logger(name: str = None):
    """Retorna logger configurado"""
    return structlog.get_logger(name)
