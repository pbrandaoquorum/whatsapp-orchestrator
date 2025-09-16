"""
Two-Phase Commit helper para confirmação antes de executar ações críticas
Agora usando DynamoDB como persistência
"""
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from app.infra.timeutils import agora_br
from app.infra.store import PendingActionsStore, PendingAction, SessionStore
from app.infra.logging import obter_logger

logger = obter_logger(__name__)

# Instâncias globais dos stores
_actions_store: Optional[PendingActionsStore] = None
_session_store: Optional[SessionStore] = None


def get_actions_store() -> PendingActionsStore:
    """Retorna instância singleton do PendingActionsStore"""
    global _actions_store
    if _actions_store is None:
        _actions_store = PendingActionsStore()
    return _actions_store


def get_session_store() -> SessionStore:
    """Retorna instância singleton do SessionStore"""
    global _session_store
    if _session_store is None:
        _session_store = SessionStore()
    return _session_store


def criar_acao_pendente(
    session_id: str,
    fluxo_destino: str,
    payload: Dict[str, Any],
    descricao: str,
    duracao_minutos: int = 10
) -> Dict[str, Any]:
    """
    Cria uma ação pendente para two-phase commit e persiste no DynamoDB
    
    Args:
        session_id: ID da sessão
        fluxo_destino: Nome do fluxo que executará a ação após confirmação
        payload: Dados necessários para executar a ação
        descricao: Descrição da ação para o usuário
        duracao_minutos: Tempo limite para confirmação
    
    Returns:
        Dict com dados da ação pendente (formato compatível)
    """
    expires_at = int((datetime.utcnow() + timedelta(minutes=duracao_minutos)).timestamp())
    
    # Criar ação no DynamoDB
    actions_store = get_actions_store()
    action = actions_store.create(
        session_id=session_id,
        flow=fluxo_destino,
        description=descricao,
        payload=payload,
        expires_at=expires_at
    )
    
    # Atualizar sessão com ID da ação pendente
    session_store = get_session_store()
    session_store.update_metadata(
        session_id=session_id,
        pendingActionId=action.action_id,
        lastQuestion=descricao,
        flowWhoAsked=fluxo_destino
    )
    
    logger.info("Ação pendente criada", session_id=session_id, action_id=action.action_id, flow=fluxo_destino)
    
    # Retornar formato compatível com código existente
    return {
        "action_id": action.action_id,
        "fluxo_destino": fluxo_destino,
        "payload": payload,
        "descricao": descricao,
        "criado_em": action.created_at,
        "expira_em": datetime.fromtimestamp(expires_at).isoformat(),
        "confirmado": False,
        "executado": False,
        "cancelado": False,
        "status": action.status
    }


def acao_expirou(acao_pendente: Dict[str, Any]) -> bool:
    """Verifica se a ação pendente expirou"""
    if not acao_pendente or not acao_pendente.get("expira_em"):
        return True
    
    try:
        expira_em = datetime.fromisoformat(acao_pendente["expira_em"])
        return datetime.utcnow() > expira_em
    except (ValueError, TypeError):
        return True


def acao_pode_ser_executada(acao_pendente: Dict[str, Any]) -> bool:
    """Verifica se a ação pode ser executada"""
    if not acao_pendente:
        return False
    
    # Verificar status do DynamoDB se disponível
    if "status" in acao_pendente:
        return acao_pendente["status"] == "confirmed" and not acao_expirou(acao_pendente)
    
    # Fallback para formato antigo
    return (
        acao_pendente.get("confirmado", False) and
        not acao_pendente.get("executado", False) and
        not acao_pendente.get("cancelado", False) and
        not acao_expirou(acao_pendente)
    )


def marcar_acao_confirmada(session_id: str, acao_pendente: Dict[str, Any]) -> Dict[str, Any]:
    """Marca a ação como confirmada pelo usuário no DynamoDB"""
    action_id = acao_pendente.get("action_id")
    if not action_id:
        logger.error("Ação sem action_id para confirmação", session_id=session_id)
        return acao_pendente
    
    actions_store = get_actions_store()
    success = actions_store.mark_confirmed(session_id, action_id)
    
    if success:
        acao_pendente["confirmado"] = True
        acao_pendente["confirmado_em"] = agora_br().isoformat()
        acao_pendente["status"] = "confirmed"
        logger.info("Ação confirmada", session_id=session_id, action_id=action_id)
    else:
        logger.warning("Falha ao confirmar ação", session_id=session_id, action_id=action_id)
    
    return acao_pendente


def marcar_acao_executada(session_id: str, acao_pendente: Dict[str, Any]) -> Dict[str, Any]:
    """Marca a ação como executada no DynamoDB"""
    action_id = acao_pendente.get("action_id")
    if not action_id:
        logger.error("Ação sem action_id para execução", session_id=session_id)
        return acao_pendente
    
    actions_store = get_actions_store()
    success = actions_store.mark_executed(session_id, action_id)
    
    if success:
        acao_pendente["executado"] = True
        acao_pendente["executado_em"] = agora_br().isoformat()
        acao_pendente["status"] = "executed"
        logger.info("Ação executada", session_id=session_id, action_id=action_id)
        
        # Limpar ação pendente da sessão
        session_store = get_session_store()
        session_store.update_metadata(
            session_id=session_id,
            pendingActionId=None,
            lastQuestion=None,
            flowWhoAsked=None
        )
    else:
        logger.warning("Falha ao executar ação", session_id=session_id, action_id=action_id)
    
    return acao_pendente


def marcar_acao_cancelada(session_id: str, acao_pendente: Dict[str, Any]) -> Dict[str, Any]:
    """Marca a ação como cancelada no DynamoDB"""
    action_id = acao_pendente.get("action_id")
    if not action_id:
        logger.error("Ação sem action_id para cancelamento", session_id=session_id)
        return acao_pendente
    
    actions_store = get_actions_store()
    success = actions_store.abort(session_id, action_id)
    
    if success:
        acao_pendente["cancelado"] = True
        acao_pendente["cancelado_em"] = agora_br().isoformat()
        acao_pendente["status"] = "aborted"
        logger.info("Ação cancelada", session_id=session_id, action_id=action_id)
        
        # Limpar ação pendente da sessão
        session_store = get_session_store()
        session_store.update_metadata(
            session_id=session_id,
            pendingActionId=None,
            lastQuestion=None,
            flowWhoAsked=None
        )
    else:
        logger.warning("Falha ao cancelar ação", session_id=session_id, action_id=action_id)
    
    return acao_pendente


def obter_acao_pendente_atual(session_id: str) -> Optional[Dict[str, Any]]:
    """Obtém a ação pendente atual da sessão do DynamoDB"""
    actions_store = get_actions_store()
    action = actions_store.get_current(session_id)
    
    if not action:
        return None
    
    # Converter para formato compatível
    expires_at = datetime.fromtimestamp(action.expires_at) if action.expires_at else datetime.utcnow()
    
    return {
        "action_id": action.action_id,
        "fluxo_destino": action.flow,
        "payload": action.payload,
        "descricao": action.description,
        "criado_em": action.created_at,
        "expira_em": expires_at.isoformat(),
        "confirmado": action.status in ["confirmed", "executed"],
        "executado": action.status == "executed",
        "cancelado": action.status == "aborted",
        "status": action.status
    }


def gerar_mensagem_confirmacao(acao_pendente: Dict[str, Any]) -> str:
    """Gera mensagem de confirmação para o usuário"""
    descricao = acao_pendente.get("descricao", "Executar ação")
    
    return f"""
🔔 *Confirmação Necessária*

{descricao}

Confirma esta ação? Digite *sim* para confirmar ou *não* para cancelar.

⏰ Esta confirmação expira em alguns minutos.
""".strip()


def gerar_mensagem_cancelamento() -> str:
    """Gera mensagem quando ação é cancelada"""
    return "❌ Ação cancelada. Como posso ajudar?"


def gerar_mensagem_expirada() -> str:
    """Gera mensagem quando ação expira"""
    return "⏰ Tempo esgotado para confirmação. A ação foi cancelada automaticamente."


def limpar_acao_pendente(session_id: str) -> Optional[Dict[str, Any]]:
    """Limpa ação pendente da sessão e retorna None"""
    session_store = get_session_store()
    session_store.update_metadata(
        session_id=session_id,
        pendingActionId=None,
        lastQuestion=None,
        flowWhoAsked=None
    )
    
    logger.debug("Ação pendente limpa da sessão", session_id=session_id)
    return None


# Templates para diferentes tipos de ação
TEMPLATES_CONFIRMACAO = {
    "confirmar_presenca": "Confirmar presença no plantão de {data} às {horario} para o paciente {paciente}?",
    "cancelar_presenca": "Cancelar presença no plantão de {data} às {horario} para o paciente {paciente}?",
    "salvar_sinais_vitais": "Salvar os seguintes sinais vitais?\n\n{sinais_vitais}",
    "salvar_nota_clinica": "Salvar nota clínica e sintomas identificados?",
    "finalizar_plantao": "Finalizar o plantão e enviar relatório final?",
}


def criar_confirmacao_presenca(acao: str, dados_plantao: Dict[str, Any]) -> Dict[str, Any]:
    """Cria confirmação específica para presença"""
    template_key = f"{acao}_presenca"
    template = TEMPLATES_CONFIRMACAO.get(template_key, "Confirmar ação de presença?")
    
    descricao = template.format(
        data=dados_plantao.get("data", "data não informada"),
        horario=dados_plantao.get("horario", "horário não informado"),
        paciente=dados_plantao.get("nome_paciente", "paciente não identificado")
    )
    
    payload = {
        "scheduleIdentifier": dados_plantao.get("schedule_id"),
        "responseValue": "confirmado" if acao == "confirmar" else "cancelado"
    }
    
    return criar_acao_pendente(
        fluxo_destino="escala_commit",
        payload=payload,
        descricao=descricao
    )


def criar_confirmacao_sinais_vitais(dados_vitais: Dict[str, Any]) -> Dict[str, Any]:
    """Cria confirmação específica para sinais vitais"""
    from app.graph.clinical_extractor import gerar_resumo_sinais_vitais
    
    resumo = gerar_resumo_sinais_vitais(dados_vitais)
    descricao = TEMPLATES_CONFIRMACAO["salvar_sinais_vitais"].format(sinais_vitais=resumo)
    
    return criar_acao_pendente(
        fluxo_destino="clinical_commit",
        payload={"vitais": dados_vitais},
        descricao=descricao
    )


def criar_confirmacao_nota_clinica(texto_nota: str, sintomas: list) -> Dict[str, Any]:
    """Cria confirmação específica para nota clínica"""
    descricao = TEMPLATES_CONFIRMACAO["salvar_nota_clinica"]
    
    payload = {
        "nota": texto_nota,
        "sintomas": sintomas
    }
    
    return criar_acao_pendente(
        fluxo_destino="notas_commit",
        payload=payload,
        descricao=descricao
    )


def criar_confirmacao_finalizacao(dados_relatorio: Dict[str, Any]) -> Dict[str, Any]:
    """Cria confirmação específica para finalização"""
    descricao = TEMPLATES_CONFIRMACAO["finalizar_plantao"]
    
    return criar_acao_pendente(
        fluxo_destino="finalizar_commit",
        payload=dados_relatorio,
        descricao=descricao
    )
