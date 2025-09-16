"""
Helpers para manipulação de estado via templates e eventos externos
Usando DynamoDB para persistência
"""
from typing import Optional
from datetime import datetime
from app.graph.state import GraphState, CoreState
from app.infra.state_persistence import StateManager
from app.infra.logging import obter_logger

logger = obter_logger(__name__)


async def carregar_estado_dynamo(phone_number: str) -> GraphState:
    """
    Carrega estado da sessão do DynamoDB para manipulação via templates
    """
    try:
        # Criar session_id a partir do telefone
        session_id = f"session_{phone_number.replace('+', '').replace('-', '').replace(' ', '')}"
        
        # Usar StateManager para carregar estado
        state_manager = StateManager(session_id)
        estado = await state_manager.load_state()
        
        logger.info("Estado carregado do DynamoDB", 
                   session_id=session_id,
                   version=estado.version)
        
        return estado
        
    except Exception as e:
        logger.error(f"Erro ao carregar estado do DynamoDB: {e}", session_id=session_id)
        # Fallback para estado limpo
        return GraphState(
            core=CoreState(
                session_id=f"session_{phone_number.replace('+', '').replace('-', '').replace(' ', '')}",
                numero_telefone=phone_number
            )
        )


async def salvar_estado_dynamo(phone_number: str, estado: GraphState) -> bool:
    """
    Salva estado da sessão no DynamoDB após manipulação via templates
    """
    try:
        session_id = f"session_{phone_number.replace('+', '').replace('-', '').replace(' ', '')}"
        
        # Usar StateManager para salvar estado
        state_manager = StateManager(session_id)
        state_manager.state = estado
        state_manager.version = estado.version
        state_manager._loaded = True
        
        sucesso = await state_manager.save_state()
        
        if sucesso:
            logger.info("Estado salvo no DynamoDB", 
                       session_id=session_id,
                       version=estado.version)
        
        return sucesso
        
    except Exception as e:
        logger.error(f"Erro ao salvar estado no DynamoDB: {e}", session_id=session_id)
        return False


async def atualizar_estado_template(phone_number: str, template: str, metadata: dict) -> bool:
    """
    Atualiza estado baseado no template disparado
    """
    try:
        # Carregar estado atual
        estado = await carregar_estado_dynamo(phone_number)
        
        # Atualizar estado baseado no template
        if template == "pedir_sinais_vitais":
            estado.aux.ultima_pergunta = "Aguardando sinais vitais..."
            estado.aux.fluxo_que_perguntou = "clinical"
            
            # Se há campos faltantes nos metadados, usar
            if "hint_campos_faltantes" in metadata:
                estado.vitais.faltantes = metadata["hint_campos_faltantes"]
                
        elif template == "confirmar_presenca":
            estado.aux.ultima_pergunta = "Aguardando confirmação de presença..."
            estado.aux.fluxo_que_perguntou = "escala"
            
        elif template == "pedir_nota_clinica":
            estado.aux.ultima_pergunta = "Aguardando nota clínica..."
            estado.aux.fluxo_que_perguntou = "notas"
            
        elif template == "finalizar_plantao":
            estado.aux.ultima_pergunta = "Aguardando confirmação para finalizar..."
            estado.aux.fluxo_que_perguntou = "finalizar"
        
        # Adicionar metadados do template
        if not estado.metadados:
            estado.metadados = {}
            
        estado.metadados.update({
            "last_template": template,
            "template_fired_at": datetime.utcnow().isoformat() + 'Z',
            "template_metadata": metadata
        })
        
        # Salvar estado atualizado
        sucesso = await salvar_estado_dynamo(phone_number, estado)
        
        if sucesso:
            logger.info("Estado atualizado via template", 
                       phone_number=phone_number[:4] + "****",
                       template=template)
        
        return sucesso
        
    except Exception as e:
        logger.error(f"Erro ao atualizar estado via template: {e}",
                    phone_number=phone_number[:4] + "****",
                    template=template)
        return False


async def obter_resumo_estado(phone_number: str) -> dict:
    """
    Obtém resumo do estado atual para debug/monitoring
    """
    try:
        estado = await carregar_estado_dynamo(phone_number)
        
        return {
            "session_id": estado.core.session_id,
            "phone_number": phone_number[:4] + "****",
            "version": estado.version,
            "turno_permitido": estado.core.turno_permitido,
            "presenca_confirmada": estado.metadados.get("presenca_confirmada", False),
            "sinais_vitais_coletados": bool(estado.vitais.processados),
            "nota_clinica": bool(estado.nota.texto_bruto),
            "acao_pendente": bool(estado.aux.acao_pendente),
            "ultima_pergunta": estado.aux.ultima_pergunta,
            "fluxo_que_perguntou": estado.aux.fluxo_que_perguntou,
            "timestamp": datetime.utcnow().isoformat() + 'Z'
        }
        
    except Exception as e:
        logger.error(f"Erro ao obter resumo do estado: {e}")
        return {"error": str(e)}


# Aliases para compatibilidade com código existente
carregar_estado_redis = carregar_estado_dynamo
salvar_estado_redis = salvar_estado_dynamo