"""
Fluxo de finalização do plantão com relatório final
Implementa two-phase commit para encerramento seguro
"""
from typing import Dict, Any
from app.graph.state import GraphState
from app.graph.tools import finalizar_relatorio
from app.infra.tpc import (
    criar_acao_pendente, gerar_mensagem_confirmacao,
    acao_pode_ser_executada, marcar_acao_confirmada,
    marcar_acao_executada, limpar_acao_pendente
)
from app.infra.confirm import is_yes, is_no
from app.infra.timeutils import agora_br
from app.infra.logging import obter_logger

logger = obter_logger(__name__)


async def finalizar_flow(estado: GraphState) -> GraphState:
    """
    Fluxo principal de finalização do plantão com classificação semântica
    """
    logger.info("Iniciando fluxo de finalização", session_id=estado.core.session_id)
    
    # Verificar se há ação pendente para executar
    if estado.aux.acao_pendente and acao_pode_ser_executada(estado.aux.acao_pendente):
        return await executar_finalizacao(estado)
    
    # Verificar se é resposta a pergunta de confirmação
    if estado.aux.ultima_pergunta and estado.aux.fluxo_que_perguntou == "finalizar":
        return await processar_resposta_confirmacao_finalizacao(estado)
    
    # Validar pré-requisitos para finalização
    if not validar_prerequisitos_finalizacao(estado):
        return orientar_prerequisitos_faltantes(estado)
    
    # Usar classificação semântica para processar entrada
    await processar_entrada_finalizacao_semantica(estado)
    
    # Preparar finalização
    return await preparar_finalizacao(estado)


async def processar_entrada_finalizacao_semantica(estado: GraphState) -> None:
    """Processa entrada de finalização usando classificação semântica"""
    texto = estado.texto_usuario or ""
    
    if not texto.strip():
        return
    
    try:
        from app.graph.semantic_classifier import classify_semantic, IntentType
        
        resultado = await classify_semantic(texto, estado)
        
        logger.info(
            "Entrada de finalização classificada semanticamente",
            intent=resultado.intent,
            confidence=resultado.confidence,
            session_id=estado.core.session_id
        )
        
        # Se é intenção de finalizar, marcar no estado
        if resultado.intent == IntentType.FINALIZAR_PLANTAO:
            estado.metadados["intencao_finalizar"] = True
            logger.info("Intenção de finalizar confirmada semanticamente")
    
    except Exception as e:
        logger.error(f"Erro na classificação semântica de finalização: {e}")
        # Fallback: se contém palavras de finalização, assumir intenção
        palavras_finalizar = ["finalizar", "encerrar", "terminar", "acabar"]
        if any(palavra in texto.lower() for palavra in palavras_finalizar):
            estado.metadados["intencao_finalizar"] = True
            logger.info("Intenção de finalizar detectada via fallback")


def validar_prerequisitos_finalizacao(estado: GraphState) -> bool:
    """Valida se todos os pré-requisitos para finalização foram atendidos"""
    # Presença deve estar confirmada
    if not estado.metadados.get("presenca_confirmada", False):
        logger.warning("Tentativa de finalizar sem presença confirmada")
        return False
    
    # Sinais vitais devem estar realizados
    if not estado.metadados.get("sinais_vitais_realizados", False):
        logger.warning("Tentativa de finalizar sem sinais vitais")
        return False
    
    # Turno não pode estar cancelado
    if estado.core.cancelado:
        logger.warning("Tentativa de finalizar turno cancelado")
        return False
    
    return True


def orientar_prerequisitos_faltantes(estado: GraphState) -> GraphState:
    """Orienta usuário sobre pré-requisitos faltantes"""
    faltantes = []
    
    if not estado.metadados.get("presenca_confirmada", False):
        faltantes.append("• Confirmar presença no plantão")
    
    if not estado.metadados.get("sinais_vitais_realizados", False):
        faltantes.append("• Informar sinais vitais do paciente")
    
    if estado.core.cancelado:
        estado.resposta_usuario = """
❌ *Não é Possível Finalizar*

Seu plantão está cancelado. Não é possível finalizar plantões cancelados.

Se houve algum erro, entre em contato com a coordenação.
""".strip()
    else:
        prerequisitos = "\n".join(faltantes)
        estado.resposta_usuario = f"""
⚠️ *Pré-requisitos Faltantes*

Para finalizar o plantão, você precisa:

{prerequisitos}

Complete estes itens primeiro e depois tente finalizar novamente.
""".strip()
    
    return estado


async def preparar_finalizacao(estado: GraphState) -> GraphState:
    """Prepara finalização do plantão (staging do two-phase commit)"""
    logger.info("Preparando finalização do plantão", session_id=estado.core.session_id)
    
    # Coletar dados para o relatório final
    dados_relatorio = coletar_dados_relatorio(estado)
    
    # Criar ação pendente
    acao = criar_acao_pendente(
        fluxo_destino="finalizar_commit",
        payload={
            "reportID": estado.core.report_id,
            "caregiverID": estado.core.caregiver_id,
            **dados_relatorio
        },
        expires_at=(agora_br().timestamp() + 600)  # 10 minutos
    )
    
    estado.aux.acao_pendente = acao
    estado.aux.fluxo_que_perguntou = "finalizar"
    
    # Gerar mensagem de confirmação
    resumo_relatorio = gerar_resumo_relatorio(dados_relatorio)
    estado.aux.ultima_pergunta = f"""
🏁 *Finalizar Plantão*

{resumo_relatorio}

**Confirma finalizar o plantão?** (sim/não)

⚠️ Após confirmar, o relatório será enviado e o plantão será encerrado.
""".strip()
    
    estado.resposta_usuario = estado.aux.ultima_pergunta
    
    return estado


def coletar_dados_relatorio(estado: GraphState) -> Dict[str, Any]:
    """Coleta dados necessários para o relatório final"""
    return {
        "reportSummarySpecification": gerar_especificacao_relatorio(estado),
        "finishDate": agora_br().isoformat(),
        "status": "completed",
        "caregiverNotes": estado.nota.texto_bruto or "Sem observações adicionais",
        "vitalSignsCollected": bool(estado.metadados.get("sinais_vitais_realizados", False)),
        "symptomsIdentified": len(estado.nota.sintomas_rag) if estado.nota.sintomas_rag else 0
    }


def gerar_especificacao_relatorio(estado: GraphState) -> str:
    """Gera especificação do relatório baseada nos dados coletados"""
    especificacao = []
    
    # Presença
    if estado.metadados.get("presenca_confirmada", False):
        especificacao.append("✅ Presença confirmada")
    
    # Sinais vitais
    if estado.metadados.get("sinais_vitais_realizados", False):
        sv_detalhes = []
        for sv, valor in estado.vitals.processados.items():
            sv_detalhes.append(f"{sv}: {valor}")
        especificacao.append(f"🩺 Sinais vitais: {', '.join(sv_detalhes)}")
    
    # Notas clínicas
    if estado.nota.texto_bruto:
        especificacao.append(f"📝 Observações: {estado.nota.texto_bruto[:100]}...")
    
    # Sintomas identificados
    if estado.nota.sintomas_rag:
        num_sintomas = len(estado.nota.sintomas_rag)
        especificacao.append(f"🔍 Sintomas identificados: {num_sintomas}")
    
    return " | ".join(especificacao) if especificacao else "Plantão realizado sem intercorrências"


def gerar_resumo_relatorio(dados_relatorio: Dict[str, Any]) -> str:
    """Gera resumo do relatório para confirmação"""
    return f"""
📋 **Resumo do Plantão:**
• Data/Hora: {dados_relatorio.get('finishDate', 'N/A')}
• Status: {dados_relatorio.get('status', 'N/A')}
• Sinais Vitais: {'✅ Coletados' if dados_relatorio.get('vitalSignsCollected') else '❌ Não coletados'}
• Sintomas: {dados_relatorio.get('symptomsIdentified', 0)} identificados
• Observações: {dados_relatorio.get('caregiverNotes', 'N/A')[:50]}...
""".strip()


async def processar_resposta_confirmacao_finalizacao(estado: GraphState) -> GraphState:
    """Processa resposta do usuário à confirmação de finalização"""
    texto = estado.texto_usuario or ""
    
    if is_yes(texto):
        # Usuário confirmou - marcar ação como confirmada
        if estado.aux.acao_pendente:
            marcar_acao_confirmada(estado.aux.acao_pendente)
        
        return await executar_finalizacao(estado)
    
    elif is_no(texto):
        # Usuário cancelou - limpar ação pendente
        estado.aux.acao_pendente = limpar_acao_pendente()
        estado.aux.ultima_pergunta = None
        estado.aux.fluxo_que_perguntou = None
        
        estado.resposta_usuario = """
❌ *Finalização Cancelada*

O plantão não foi finalizado. Você pode:

• Continuar realizando atividades do plantão
• Tentar finalizar novamente quando estiver pronto
• Informar dados adicionais se necessário

Como deseja prosseguir?
""".strip()
        
        return estado
    
    else:
        # Resposta não reconhecida - manter pergunta
        estado.resposta_usuario = """
❓ *Resposta Não Reconhecida*

Por favor, responda com **"sim"** para confirmar a finalização ou **"não"** para cancelar.

Confirma finalizar o plantão? (sim/não)
""".strip()
        
        return estado


async def executar_finalizacao(estado: GraphState) -> GraphState:
    """Executa a finalização do plantão (commit)"""
    acao = estado.aux.acao_pendente
    
    if not acao or not acao.get("confirmado", False):
        logger.error("Tentativa de executar finalização não confirmada")
        estado.resposta_usuario = "Erro: ação não foi confirmada. Tente novamente."
        return estado
    
    try:
        logger.info("Executando finalização do plantão", 
                   report_id=estado.core.report_id,
                   caregiver_id=estado.core.caregiver_id)
        
        # Chamar Lambda de finalização
        resultado = await finalizar_relatorio(estado, acao["payload"])
        
        # Marcar ação como executada
        marcar_acao_executada(acao)
        
        # Limpar estado auxiliar
        estado.aux.acao_pendente = limpar_acao_pendente()
        estado.aux.ultima_pergunta = None
        estado.aux.fluxo_que_perguntou = None
        estado.aux.retomar_apos = None
        
        # Marcar plantão como finalizado
        estado.metadados["plantao_finalizado"] = True
        estado.metadados["data_finalizacao"] = agora_br().isoformat()
        
        # Marcar para terminar o fluxo
        estado.terminar_fluxo = True
        
        if resultado.get("sucesso", False):
            estado.resposta_usuario = """
🎉 *Plantão Finalizado com Sucesso!*

✅ Relatório enviado
✅ DailyReport gerado
✅ Sistema atualizado

Obrigado pelo excelente trabalho! 

O relatório foi enviado automaticamente para a coordenação.
""".strip()
        else:
            estado.resposta_usuario = f"""
⚠️ *Plantão Finalizado com Ressalvas*

O plantão foi encerrado, mas houve alguns avisos:
{resultado.get('mensagem', 'Verifique com a coordenação se necessário.')}

Mesmo assim, o relatório foi processado.
""".strip()
        
        logger.info("Finalização executada com sucesso",
                   session_id=estado.core.session_id,
                   resultado=resultado.get("sucesso", False))
        
        return estado
        
    except Exception as e:
        logger.error(f"Erro ao executar finalização: {e}",
                    session_id=estado.core.session_id)
        
        # Em caso de erro, não limpar ação pendente para retry
        estado.resposta_usuario = f"""
❌ *Erro na Finalização*

Ocorreu um erro ao finalizar o plantão: {str(e)}

Tente novamente em alguns instantes ou entre em contato com o suporte.
""".strip()
        
        return estado