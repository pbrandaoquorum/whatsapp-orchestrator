"""
Helpers para manipulação de estado via templates e eventos externos
"""
import pickle
import time
from typing import Optional
from app.graph.state import GraphState, CoreState
from app.infra.redis_client import obter_cliente_redis
from app.infra.logging import obter_logger

logger = obter_logger(__name__)


async def carregar_estado_redis(phone_number: str) -> GraphState:
    """
    Carrega estado da sessão do Redis para manipulação via templates
    """
    try:
        redis_client = obter_cliente_redis()
        session_id = f"session_{phone_number.replace('+', '')}"
        
        # Buscar checkpoint no Redis
        key = f"checkpoint:{session_id}"
        data = await redis_client.get(key)
        
        if data:
            checkpoint_data = pickle.loads(data)
            estado_dict = checkpoint_data.get("checkpoint", {})
            
            logger.info("Estado carregado do Redis", session_id=session_id, 
                       keys=list(estado_dict.keys()))
            
            return GraphState(**estado_dict)
        else:
            # Estado inicial se não existe
            logger.info("Criando estado inicial", session_id=session_id)
            return GraphState(
                core=CoreState(
                    session_id=session_id,
                    numero_telefone=phone_number
                )
            )
            
    except Exception as e:
        logger.error(f"Erro ao carregar estado do Redis: {e}")
        # Fallback para estado inicial
        return GraphState(
            core=CoreState(
                session_id=f"session_{phone_number.replace('+', '')}",
                numero_telefone=phone_number
            )
        )


async def salvar_estado_redis(estado: GraphState) -> bool:
    """
    Salva estado da sessão no Redis após manipulação via templates
    """
    try:
        redis_client = obter_cliente_redis()
        key = f"checkpoint:{estado.core.session_id}"
        
        # Preparar dados para salvar
        data = {
            "checkpoint": estado.dict(),
            "metadata": "updated_by_template",
            "timestamp": time.time()
        }
        
        # Salvar no Redis com TTL de 1 hora
        await redis_client.setex(key, 3600, pickle.dumps(data))
        
        logger.info("Estado salvo no Redis", session_id=estado.core.session_id)
        return True
        
    except Exception as e:
        logger.error(f"Erro ao salvar estado no Redis: {e}")
        return False


def preparar_estado_para_template(estado: GraphState, template: str, metadata: dict) -> GraphState:
    """
    Prepara estado baseado no tipo de template enviado
    """
    if template == "confirmar_presenca":
        # Preparar para confirmação de presença
        estado.aux.ultima_pergunta = "Aguardando confirmação de presença..."
        estado.aux.fluxo_que_perguntou = "escala"
        estado.metadados["template_enviado"] = "confirmar_presenca"
        estado.metadados["aguardando_confirmacao"] = True
        
    elif template == "pedir_sinais_vitais":
        # Preparar para coleta de sinais vitais
        estado.aux.ultima_pergunta = "Aguardando sinais vitais..."
        estado.aux.fluxo_que_perguntou = "clinical"
        estado.metadados["template_enviado"] = "pedir_sinais_vitais"
        estado.metadados["aguardando_sinais_vitais"] = True
        
        # Se há hint de campos faltantes
        if "hint_campos_faltantes" in metadata:
            estado.vitais.faltantes = metadata["hint_campos_faltantes"]
            
    elif template == "pedir_nota_clinica":
        # Preparar para coleta de nota clínica
        estado.aux.ultima_pergunta = "Aguardando nota clínica..."
        estado.aux.fluxo_que_perguntou = "notas"
        estado.metadados["template_enviado"] = "pedir_nota_clinica"
        estado.metadados["aguardando_nota"] = True
        
    elif template == "finalizar_plantao":
        # Preparar para finalização
        estado.aux.ultima_pergunta = "Aguardando confirmação de finalização..."
        estado.aux.fluxo_que_perguntou = "finalizar"
        estado.metadados["template_enviado"] = "finalizar_plantao"
        estado.metadados["aguardando_finalizacao"] = True
        
    else:
        # Template genérico
        estado.metadados["template_enviado"] = template
        estado.metadados["template_metadata"] = metadata
    
    # Marcar timestamp do template
    estado.metadados["template_timestamp"] = time.time()
    
    logger.info("Estado preparado para template", 
               template=template, 
               session_id=estado.core.session_id)
    
    return estado


def limpar_flags_template(estado: GraphState) -> GraphState:
    """
    Limpa flags relacionadas a templates após processamento
    """
    flags_para_limpar = [
        "template_enviado",
        "aguardando_confirmacao", 
        "aguardando_sinais_vitais",
        "aguardando_nota",
        "aguardando_finalizacao",
        "template_timestamp",
        "template_metadata"
    ]
    
    for flag in flags_para_limpar:
        if flag in estado.metadados:
            del estado.metadados[flag]
    
    return estado


def verificar_template_expirado(estado: GraphState, timeout_seconds: int = 600) -> bool:
    """
    Verifica se template expirou (padrão: 10 minutos)
    """
    timestamp = estado.metadados.get("template_timestamp")
    if not timestamp:
        return False
    
    return (time.time() - timestamp) > timeout_seconds
