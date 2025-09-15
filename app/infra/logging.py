"""
Configuração de logging estruturado em português
"""
import structlog
import logging
import sys
from typing import Any, Dict
from datetime import datetime
from app.infra.timeutils import agora_br_iso


def configurar_logging(nivel: str = "INFO") -> None:
    """Configura logging estruturado"""
    
    # Configurar logging padrão do Python
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, nivel.upper())
    )
    
    # Configurar structlog
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            adicionar_timestamp,
            adicionar_contexto_brasileiro,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(ensure_ascii=False)
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def adicionar_timestamp(logger: Any, method_name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Adiciona timestamp brasileiro aos logs"""
    event_dict["timestamp"] = agora_br_iso()
    return event_dict


def adicionar_contexto_brasileiro(logger: Any, method_name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Adiciona contexto em português aos logs"""
    # Traduzir níveis de log
    nivel_map = {
        "debug": "depuracao",
        "info": "informacao",
        "warning": "aviso",
        "error": "erro",
        "critical": "critico"
    }
    
    if "level" in event_dict:
        event_dict["nivel"] = nivel_map.get(event_dict["level"], event_dict["level"])
    
    return event_dict


def obter_logger(nome: str) -> structlog.stdlib.BoundLogger:
    """Obtém logger estruturado"""
    return structlog.get_logger(nome)


class LoggerContexto:
    """Context manager para adicionar contexto aos logs"""
    
    def __init__(self, logger: structlog.stdlib.BoundLogger, **contexto):
        self.logger = logger
        self.contexto = contexto
        self.logger_com_contexto = None
    
    def __enter__(self):
        self.logger_com_contexto = self.logger.bind(**self.contexto)
        return self.logger_com_contexto
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.logger_com_contexto.error(
                "Exceção capturada no contexto",
                tipo_excecao=exc_type.__name__,
                mensagem_excecao=str(exc_val)
            )


def log_request(
    logger: structlog.stdlib.BoundLogger,
    metodo: str,
    url: str,
    payload: Dict[str, Any] = None,
    headers: Dict[str, str] = None
) -> None:
    """Log padronizado para requests"""
    log_data = {
        "evento": "requisicao_enviada",
        "metodo_http": metodo,
        "url": url,
    }
    
    if payload:
        # Remover dados sensíveis
        payload_limpo = remover_dados_sensiveis(payload)
        log_data["payload"] = payload_limpo
    
    if headers:
        # Remover headers sensíveis
        headers_limpos = {k: v for k, v in headers.items() 
                         if k.lower() not in ["authorization", "x-api-key"]}
        log_data["headers"] = headers_limpos
    
    logger.info("Enviando requisição", **log_data)


def log_response(
    logger: structlog.stdlib.BoundLogger,
    status_code: int,
    response_data: Dict[str, Any] = None,
    tempo_resposta_ms: float = None
) -> None:
    """Log padronizado para responses"""
    log_data = {
        "evento": "resposta_recebida",
        "status_code": status_code,
        "sucesso": 200 <= status_code < 300
    }
    
    if tempo_resposta_ms:
        log_data["tempo_resposta_ms"] = tempo_resposta_ms
    
    if response_data:
        # Remover dados sensíveis
        response_limpo = remover_dados_sensiveis(response_data)
        log_data["response"] = response_limpo
    
    if 200 <= status_code < 300:
        logger.info("Resposta recebida com sucesso", **log_data)
    elif 400 <= status_code < 500:
        logger.warning("Erro do cliente na resposta", **log_data)
    else:
        logger.error("Erro do servidor na resposta", **log_data)


def log_fluxo(
    logger: structlog.stdlib.BoundLogger,
    nome_fluxo: str,
    estado_inicial: Dict[str, Any],
    estado_final: Dict[str, Any] = None,
    sucesso: bool = True
) -> None:
    """Log padronizado para execução de fluxos"""
    log_data = {
        "evento": "execucao_fluxo",
        "nome_fluxo": nome_fluxo,
        "sucesso": sucesso
    }
    
    # Adicionar dados relevantes do estado (sem dados sensíveis)
    if estado_inicial:
        log_data["estado_inicial"] = extrair_dados_estado_para_log(estado_inicial)
    
    if estado_final:
        log_data["estado_final"] = extrair_dados_estado_para_log(estado_final)
    
    if sucesso:
        logger.info("Fluxo executado com sucesso", **log_data)
    else:
        logger.error("Falha na execução do fluxo", **log_data)


def remover_dados_sensiveis(data: Dict[str, Any]) -> Dict[str, Any]:
    """Remove dados sensíveis dos logs"""
    campos_sensiveis = {
        "password", "senha", "token", "api_key", "secret", "authorization",
        "cpf", "rg", "telefone", "email", "endereco"
    }
    
    if not isinstance(data, dict):
        return data
    
    data_limpo = {}
    for key, value in data.items():
        if key.lower() in campos_sensiveis:
            data_limpo[key] = "***REMOVIDO***"
        elif isinstance(value, dict):
            data_limpo[key] = remover_dados_sensiveis(value)
        elif isinstance(value, list):
            data_limpo[key] = [remover_dados_sensiveis(item) if isinstance(item, dict) else item 
                              for item in value]
        else:
            data_limpo[key] = value
    
    return data_limpo


def extrair_dados_estado_para_log(estado: Dict[str, Any]) -> Dict[str, Any]:
    """Extrai dados relevantes do estado para log"""
    dados_relevantes = {}
    
    # Campos importantes para rastreamento
    campos_importantes = [
        "session_id", "numero_telefone", "schedule_id", "report_id",
        "intencao", "ultimo_fluxo", "turno_permitido", "cancelado"
    ]
    
    for campo in campos_importantes:
        if campo in estado:
            dados_relevantes[campo] = estado[campo]
    
    # Adicionar contadores úteis
    if "vitais" in estado and "processados" in estado["vitais"]:
        dados_relevantes["vitais_coletados"] = len(estado["vitais"]["processados"])
        dados_relevantes["vitais_faltantes"] = len(estado["vitais"].get("faltantes", []))
    
    if "metadados" in estado:
        metadados = estado["metadados"]
        dados_relevantes["presenca_confirmada"] = metadados.get("presenca_confirmada", False)
        dados_relevantes["sv_realizados"] = metadados.get("sinais_vitais_realizados", False)
    
    return dados_relevantes
