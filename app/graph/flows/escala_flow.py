"""
Fluxo de confirmação/cancelamento de presença no plantão
Implementa two-phase commit para todas as ações críticas
"""
from typing import Dict, Any
from app.graph.state import GraphState
from app.graph.tools import atualizar_resposta_turno, obter_dados_turno
from app.graph.router import recuperar_sinais_vitais_do_buffer
from app.infra.tpc import (
    criar_confirmacao_presenca, gerar_mensagem_confirmacao, 
    gerar_mensagem_cancelamento, acao_pode_ser_executada,
    marcar_acao_confirmada, marcar_acao_executada, limpar_acao_pendente
)
from app.infra.confirm import is_yes, is_no
from app.infra.logging import obter_logger

logger = obter_logger(__name__)


async def detectar_intencao_presenca_semantica(texto: str, estado: GraphState) -> str:
    """Detecta intenção de confirmar ou cancelar presença usando classificação semântica"""
    if not texto:
        return "indefinido"
    
    try:
        from app.graph.semantic_classifier import classify_semantic, IntentType
        
        resultado = await classify_semantic(texto, estado)
        
        logger.info(
            "Intenção de presença detectada semanticamente",
            intent=resultado.intent,
            confidence=resultado.confidence,
            rationale=resultado.rationale
        )
        
        # Mapear intenções semânticas para ações de presença
        if resultado.intent == IntentType.CONFIRMAR_PRESENCA:
            return "confirmar"
        elif resultado.intent == IntentType.CANCELAR_PRESENCA:
            return "cancelar"
        elif resultado.intent == IntentType.CONFIRMACAO_SIM:
            # Se há contexto de presença, interpretar como confirmação
            return "confirmar"
        elif resultado.intent == IntentType.CONFIRMACAO_NAO:
            # Se há contexto de presença, interpretar como cancelamento
            return "cancelar"
        else:
            return "indefinido"
    
    except Exception as e:
        logger.error(f"Erro na detecção semântica de presença: {e}")
        
        # Sem fallback - retornar indefinido
        return "indefinido"


def gerar_dados_plantao_para_confirmacao(estado: GraphState) -> Dict[str, Any]:
    """Gera dados do plantão para mensagem de confirmação"""
    return {
        "schedule_id": estado.core.schedule_id,
        "data": estado.core.data_relatorio or "não informada",
        "horario": "horário do plantão",  # Poderia vir dos dados do Lambda
        "nome_paciente": "paciente"  # Poderia vir dos dados do Lambda
    }


async def escala_flow(estado: GraphState) -> GraphState:
    """
    Fluxo principal de confirmação/cancelamento de presença com classificação semântica
    """
    logger.info("Iniciando fluxo de escala", session_id=estado.core.session_id)
    
    # Verificar se há ação pendente para executar
    if estado.aux.acao_pendente and acao_pode_ser_executada(estado.aux.acao_pendente):
        return await executar_confirmacao_presenca(estado)
    
    # Verificar se é resposta a pergunta de confirmação
    if estado.aux.ultima_pergunta and estado.aux.fluxo_que_perguntou == "escala":
        return await processar_resposta_confirmacao(estado)
    
    # Detectar intenção semanticamente no texto do usuário
    intencao = await detectar_intencao_presenca_semantica(estado.texto_usuario or "", estado)
    
    if intencao == "confirmar":
        return await preparar_confirmacao_presenca(estado, "confirmar")
    elif intencao == "cancelar":
        return await preparar_confirmacao_presenca(estado, "cancelar")
    else:
        # Orientar usuário sobre como proceder
        estado.resposta_usuario = """
🕐 *Confirmação de Presença*

Para confirmar sua presença no plantão, digite:
• "Cheguei" ou "Confirmo presença"

Para cancelar o plantão, digite:
• "Cancelar" ou "Não posso ir"

Como deseja proceder?
""".strip()
        
        return estado


async def preparar_confirmacao_presenca(estado: GraphState, acao: str) -> GraphState:
    """Prepara confirmação de presença (staging do two-phase commit)"""
    logger.info(f"Preparando {acao} de presença", session_id=estado.core.session_id)
    
    # Obter dados do plantão
    dados_plantao = gerar_dados_plantao_para_confirmacao(estado)
    
    # Criar ação pendente
    acao_pendente = criar_confirmacao_presenca(acao, dados_plantao)
    estado.aux.acao_pendente = acao_pendente
    
    # Definir pergunta pendente
    mensagem_confirmacao = gerar_mensagem_confirmacao(acao_pendente)
    estado.aux.ultima_pergunta = mensagem_confirmacao
    estado.aux.fluxo_que_perguntou = "escala"
    
    # Resposta ao usuário
    estado.resposta_usuario = mensagem_confirmacao
    
    return estado


async def processar_resposta_confirmacao(estado: GraphState) -> GraphState:
    """Processa resposta do usuário à pergunta de confirmação"""
    texto = estado.texto_usuario or ""
    
    if is_yes(texto):
        # Usuário confirmou - marcar ação como confirmada
        if estado.aux.acao_pendente:
            marcar_acao_confirmada(estado.aux.acao_pendente)
        
        return await executar_confirmacao_presenca(estado)
    
    elif is_no(texto):
        # Usuário cancelou - limpar ação pendente
        estado.aux.acao_pendente = limpar_acao_pendente()
        estado.aux.ultima_pergunta = None
        estado.aux.fluxo_que_perguntou = None
        
        estado.resposta_usuario = gerar_mensagem_cancelamento()
        return estado
    
    else:
        # Resposta não reconhecida - pedir esclarecimento
        estado.resposta_usuario = """
❓ Não entendi sua resposta.

Digite *sim* para confirmar ou *não* para cancelar.
""".strip()
        
        return estado


async def executar_confirmacao_presenca(estado: GraphState) -> GraphState:
    """Executa a confirmação/cancelamento de presença (commit)"""
    acao = estado.aux.acao_pendente
    
    if not acao or not acao.get("confirmado", False):
        logger.error("Tentativa de executar ação não confirmada")
        estado.resposta_usuario = "Erro interno. Tente novamente."
        return estado
    
    try:
        # Extrair dados da ação
        payload = acao.get("payload", {})
        resposta_valor = payload.get("responseValue")  # "confirmado" ou "cancelado"
        
        # Chamar Lambda
        logger.info(f"Executando {resposta_valor} de presença")
        resultado = atualizar_resposta_turno(estado, resposta_valor)
        
        # Marcar ação como executada
        marcar_acao_executada(acao)
        
        # Atualizar estado baseado no resultado
        if resposta_valor == "confirmado":
            estado.metadados["presenca_confirmada"] = True
            estado.core.cancelado = False
            
            # Re-bootstrap para obter dados atualizados
            estado = obter_dados_turno(estado)
            
            # Recuperar sinais vitais do buffer se existirem
            recuperar_sinais_vitais_do_buffer(estado)
            
            estado.resposta_usuario = """
✅ *Presença Confirmada*

Sua presença foi confirmada com sucesso! 

Agora você pode:
• Informar sinais vitais do paciente
• Enviar notas clínicas e observações
• Finalizar o plantão quando concluído
""".strip()
            
        else:  # cancelado
            estado.metadados["presenca_confirmada"] = False
            estado.core.cancelado = True
            
            estado.resposta_usuario = """
❌ *Plantão Cancelado*

Seu plantão foi cancelado conforme solicitado.

Os responsáveis foram notificados automaticamente.
""".strip()
        
        # Limpar dados da ação
        estado.aux.acao_pendente = limpar_acao_pendente()
        estado.aux.ultima_pergunta = None
        estado.aux.fluxo_que_perguntou = None
        
        # Limpar retomada se havia
        if estado.aux.retomar_apos:
            estado.aux.retomar_apos = None
        
        logger.info(
            "Confirmação de presença executada",
            resultado=resposta_valor,
            sucesso=True
        )
        
    except Exception as e:
        logger.error(f"Erro ao executar confirmação de presença: {e}")
        
        estado.resposta_usuario = """
❌ *Erro na Confirmação*

Ocorreu um erro ao processar sua solicitação. 
Tente novamente em alguns instantes.
""".strip()
    
    return estado


def orientar_sobre_presenca(estado: GraphState) -> GraphState:
    """Orienta usuário sobre como confirmar presença quando necessário"""
    if estado.core.cancelado:
        estado.resposta_usuario = """
❌ *Plantão Cancelado*

Seu plantão está cancelado. Para reativar, entre em contato com a coordenação.
""".strip()
    
    elif not estado.core.turno_permitido:
        estado.resposta_usuario = """
⚠️ *Turno Não Permitido*

Não há plantão agendado para você no momento. 
Verifique sua agenda ou entre em contato com a coordenação.
""".strip()
    
    else:
        estado.resposta_usuario = """
📋 *Confirmação de Presença Necessária*

Antes de prosseguir, confirme sua presença no plantão.

Digite:
• "Cheguei" para confirmar
• "Cancelar" se não puder comparecer
""".strip()
    
    return estado
