"""
Two-Phase Commit helper para confirmação antes de executar ações críticas
"""
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from app.infra.timeutils import agora_br


def criar_acao_pendente(
    fluxo_destino: str,
    payload: Dict[str, Any],
    descricao: str,
    duracao_minutos: int = 10
) -> Dict[str, Any]:
    """
    Cria uma ação pendente para two-phase commit
    
    Args:
        fluxo_destino: Nome do fluxo que executará a ação após confirmação
        payload: Dados necessários para executar a ação
        descricao: Descrição da ação para o usuário
        duracao_minutos: Tempo limite para confirmação
    
    Returns:
        Dict com dados da ação pendente
    """
    agora = agora_br()
    expira_em = agora + timedelta(minutes=duracao_minutos)
    
    return {
        "fluxo_destino": fluxo_destino,
        "payload": payload,
        "descricao": descricao,
        "criado_em": agora.isoformat(),
        "expira_em": expira_em.isoformat(),
        "confirmado": False,
        "executado": False,
        "cancelado": False
    }


def acao_expirou(acao_pendente: Dict[str, Any]) -> bool:
    """Verifica se a ação pendente expirou"""
    if not acao_pendente or not acao_pendente.get("expira_em"):
        return True
    
    try:
        expira_em = datetime.fromisoformat(acao_pendente["expira_em"])
        return agora_br() > expira_em
    except (ValueError, TypeError):
        return True


def acao_pode_ser_executada(acao_pendente: Dict[str, Any]) -> bool:
    """Verifica se a ação pode ser executada"""
    if not acao_pendente:
        return False
    
    return (
        acao_pendente.get("confirmado", False) and
        not acao_pendente.get("executado", False) and
        not acao_pendente.get("cancelado", False) and
        not acao_expirou(acao_pendente)
    )


def marcar_acao_confirmada(acao_pendente: Dict[str, Any]) -> Dict[str, Any]:
    """Marca a ação como confirmada pelo usuário"""
    acao_pendente["confirmado"] = True
    acao_pendente["confirmado_em"] = agora_br().isoformat()
    return acao_pendente


def marcar_acao_executada(acao_pendente: Dict[str, Any]) -> Dict[str, Any]:
    """Marca a ação como executada"""
    acao_pendente["executado"] = True
    acao_pendente["executado_em"] = agora_br().isoformat()
    return acao_pendente


def marcar_acao_cancelada(acao_pendente: Dict[str, Any]) -> Dict[str, Any]:
    """Marca a ação como cancelada"""
    acao_pendente["cancelado"] = True
    acao_pendente["cancelado_em"] = agora_br().isoformat()
    return acao_pendente


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


def limpar_acao_pendente() -> Optional[Dict[str, Any]]:
    """Retorna None para limpar ação pendente do estado"""
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
