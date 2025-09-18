"""
Integração mínima com Langfuse baseada no guia oficial:
https://langfuse.com/guides/cookbook/integration_langgraph

Uso principal: adicionar callbacks do Langfuse às invocações do LangGraph.
"""

from typing import Optional, Dict, Any
import os

from app.infra.logging import obter_logger

logger = obter_logger(__name__)

# Importação condicional para não quebrar em ambientes sem a lib
try:
    from langfuse import get_client  # type: ignore
    from langfuse.langchain import CallbackHandler  # type: ignore
    _LF_AVAILABLE = True
except Exception:  # pragma: no cover - ambiente sem langfuse
    get_client = None  # type: ignore
    CallbackHandler = None  # type: ignore
    _LF_AVAILABLE = False


class _Langfuse:
    def __init__(self) -> None:
        self.enabled: bool = False
        self.callback_handler: Optional["CallbackHandler"] = None  # type: ignore
        self._init()

    def _has_credentials(self) -> bool:
        return bool(
            os.getenv("LANGFUSE_PUBLIC_KEY")
            and os.getenv("LANGFUSE_SECRET_KEY")
        )

    def _init(self) -> None:
        if not _LF_AVAILABLE:
            logger.info("Langfuse não instalado; callbacks desabilitados")
            return
        if not self._has_credentials():
            logger.info("Credenciais Langfuse ausentes; callbacks desabilitados")
            return
        try:
            client = get_client()
            if client.auth_check():
                self.callback_handler = CallbackHandler()
                self.enabled = True
                logger.info("Langfuse habilitado para callbacks do LangGraph")
            else:
                logger.warning("Falha na autenticação Langfuse; callbacks desabilitados")
        except Exception as e:
            logger.error(f"Erro ao inicializar Langfuse: {e}")

    def get_callback_config(self) -> Dict[str, Any]:
        if self.enabled and self.callback_handler is not None:
            return {"callbacks": [self.callback_handler]}
        return {}


_lf = _Langfuse()


def is_langfuse_enabled() -> bool:
    return _lf.enabled


def get_langfuse_callback_config() -> Dict[str, Any]:
    """Retorna {"callbacks": [CallbackHandler]} quando habilitado, senão {}."""
    return _lf.get_callback_config()



