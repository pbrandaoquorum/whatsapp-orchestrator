"""
Fluxo auxiliar para orientações, esclarecimentos e mensagens de apoio
Centraliza todas as mensagens de clarificação e prompts
"""
from typing import Dict, Any
from app.graph.state import GraphState
from app.graph.clinical_extractor import SINAIS_VITAIS_OBRIGATORIOS
from app.infra.logging import obter_logger

logger = obter_logger(__name__)


def auxiliar_flow(estado: GraphState) -> GraphState:
    """
    Fluxo principal auxiliar - decide que tipo de orientação fornecer
    """
    logger.info("Iniciando fluxo auxiliar", session_id=estado.core.session_id)
    
    # Verificar contexto específico para orientação direcionada
    
    # Caso 1: Turno cancelado
    if estado.core.cancelado:
        return orientar_turno_cancelado(estado)
    
    # Caso 2: Turno não permitido
    if not estado.core.turno_permitido:
        return orientar_turno_nao_permitido(estado)
    
    # Caso 3: Presença não confirmada
    if not estado.metadados.get("presenca_confirmada", False):
        return orientar_confirmar_presenca(estado)
    
    # Caso 4: Sinais vitais faltantes (coleta incremental)
    if estado.aux.fluxo_que_perguntou == "clinical" and estado.vitais.faltantes:
        return orientar_sinais_vitais_faltantes(estado)
    
    # Caso 5: Two-phase commit cancelado
    if estado.aux.acao_pendente and estado.aux.acao_pendente.get("cancelado", False):
        return orientar_acao_cancelada(estado)
    
    # Caso 6: Orientação geral baseada no estado atual
    return orientar_geral(estado)


def orientar_turno_cancelado(estado: GraphState) -> GraphState:
    """Orienta usuário quando turno está cancelado"""
    estado.resposta_usuario = """
❌ *Plantão Cancelado*

Seu plantão foi cancelado e não é possível realizar atividades clínicas.

*Para reativar seu plantão:*
• Entre em contato com a coordenação
• Verifique sua agenda no sistema
• Aguarde nova atribuição

*Precisa de ajuda?*
• Fale com seu supervisor
• Consulte o manual do cuidador
• Entre em contato com o suporte
""".strip()
    
    return estado


def orientar_turno_nao_permitido(estado: GraphState) -> GraphState:
    """Orienta usuário quando turno não é permitido"""
    estado.resposta_usuario = """
⚠️ *Turno Não Permitido*

Não há plantão agendado para você no momento.

*Verifique:*
• Sua agenda de plantões
• Horário correto do plantão
• Se há plantões pendentes

*Próximos passos:*
• Consulte sua agenda no sistema
• Entre em contato com a coordenação
• Aguarde confirmação de novos plantões

*Precisa de ajuda?*
Digite "ajuda" para mais orientações.
""".strip()
    
    return estado


def orientar_confirmar_presenca(estado: GraphState) -> GraphState:
    """Orienta usuário sobre como confirmar presença"""
    estado.resposta_usuario = """
📍 *Confirme sua Presença*

Para começar o plantão, confirme sua presença primeiro.

*Como confirmar:*
• Digite "Cheguei" ou "Confirmo presença"
• Ou "Confirmo" para abreviar

*Para cancelar:*
• Digite "Cancelar" ou "Não posso ir"

*Após confirmar você poderá:*
• Informar sinais vitais
• Enviar notas clínicas
• Finalizar o plantão

Como deseja proceder?
""".strip()
    
    return estado


def orientar_sinais_vitais_faltantes(estado: GraphState) -> GraphState:
    """Orienta sobre sinais vitais que ainda faltam"""
    
    # Mapear nomes amigáveis
    nomes_amigaveis = {
        "PA": "Pressão Arterial (ex: 120x80)",
        "FC": "Frequência Cardíaca (ex: 78 bpm)", 
        "FR": "Frequência Respiratória (ex: 18 irpm)",
        "Sat": "Saturação (ex: 97%)",
        "Temp": "Temperatura (ex: 36.5°C)"
    }
    
    faltantes = estado.vitais.faltantes
    
    if not faltantes:
        # Não deveria chegar aqui, mas por segurança
        estado.resposta_usuario = """
✅ *Sinais Vitais Completos*

Todos os sinais vitais foram coletados!
Você pode prosseguir com outras atividades.
""".strip()
        return estado
    
    # Criar lista dos faltantes
    lista_faltantes = []
    for sv in faltantes:
        nome_amigavel = nomes_amigaveis.get(sv, sv)
        lista_faltantes.append(f"• *{sv}*: {nome_amigavel}")
    
    faltantes_texto = "\n".join(lista_faltantes)
    
    # Mostrar o que já foi coletado
    coletados = estado.vitais.processados
    if coletados:
        from app.graph.clinical_extractor import gerar_resumo_sinais_vitais
        resumo_coletados = gerar_resumo_sinais_vitais(coletados)
        
        estado.resposta_usuario = f"""
📊 *Sinais Vitais - Faltam Dados*

*Já coletados:*
{resumo_coletados}

*Ainda faltam:*
{faltantes_texto}

*Exemplo de como informar:*
"FR 18, Sat 97, Temp 36.8"

Por favor, informe os dados que ainda faltam.
""".strip()
    else:
        estado.resposta_usuario = f"""
🩺 *Sinais Vitais Necessários*

Para prosseguir, informe os seguintes sinais vitais:

{faltantes_texto}

*Exemplo completo:*
"PA 120x80, FC 78, FR 18, Sat 97%, Temp 36.5°C"

Você pode enviar todos juntos ou um de cada vez.
""".strip()
    
    return estado


def orientar_acao_cancelada(estado: GraphState) -> GraphState:
    """Orienta quando uma ação foi cancelada"""
    estado.resposta_usuario = """
❌ *Ação Cancelada*

A ação anterior foi cancelada conforme solicitado.

*Você pode:*
• Tentar a ação novamente
• Escolher uma ação diferente
• Continuar com outras atividades

*Opções disponíveis:*
• Informar sinais vitais
• Enviar notas clínicas  
• Finalizar plantão
• Solicitar ajuda

Como deseja proceder?
""".strip()
    
    return estado


def orientar_geral(estado: GraphState) -> GraphState:
    """Orientação geral baseada no estado atual"""
    
    # Montar orientação baseada no que já foi feito
    opcoes_disponiveis = []
    status_atual = []
    
    # Verificar status da presença
    if estado.metadados.get("presenca_confirmada", False):
        status_atual.append("✅ Presença confirmada")
    else:
        opcoes_disponiveis.append("• Confirmar presença no plantão")
    
    # Verificar status dos sinais vitais
    if estado.metadados.get("sinais_vitais_realizados", False):
        status_atual.append("✅ Sinais vitais coletados")
    else:
        opcoes_disponiveis.append("• Informar sinais vitais do paciente")
    
    # Verificar status da nota clínica
    if estado.metadados.get("nota_clinica_enviada", False):
        status_atual.append("✅ Nota clínica enviada")
        
        num_sintomas = estado.metadados.get("sintomas_identificados", 0)
        if num_sintomas > 0:
            status_atual.append(f"✅ {num_sintomas} sintoma(s) identificado(s)")
    else:
        opcoes_disponiveis.append("• Enviar notas clínicas e observações")
    
    # Verificar se pode finalizar
    pode_finalizar = (
        estado.metadados.get("presenca_confirmada", False) and
        estado.metadados.get("sinais_vitais_realizados", False)
    )
    
    if pode_finalizar:
        opcoes_disponiveis.append("• Finalizar o plantão")
    
    # Sempre disponível
    opcoes_disponiveis.extend([
        "• Solicitar ajuda ou orientações",
        "• Ver comandos disponíveis"
    ])
    
    # Montar resposta
    partes_resposta = ["🤖 *Como posso ajudar?*", ""]
    
    if status_atual:
        partes_resposta.append("*Status atual:*")
        partes_resposta.extend(status_atual)
        partes_resposta.append("")
    
    partes_resposta.append("*Você pode:*")
    partes_resposta.extend(opcoes_disponiveis)
    
    # Adicionar dicas contextuais
    if not estado.metadados.get("presenca_confirmada", False):
        partes_resposta.extend([
            "",
            "💡 *Dica:* Digite 'Cheguei' para confirmar sua presença."
        ])
    elif not estado.metadados.get("sinais_vitais_realizados", False):
        partes_resposta.extend([
            "",
            "💡 *Dica:* Envie os sinais vitais, ex: 'PA 120x80, FC 78, Sat 97%'"
        ])
    
    estado.resposta_usuario = "\n".join(partes_resposta)
    
    return estado


def orientar_comandos_disponiveis(estado: GraphState) -> GraphState:
    """Mostra lista de comandos disponíveis"""
    estado.resposta_usuario = """
📋 *Comandos Disponíveis*

*Confirmação de Presença:*
• "Cheguei" / "Confirmo presença"
• "Cancelar" / "Não posso ir"

*Sinais Vitais:*
• "PA 120x80, FC 78, FR 18, Sat 97%, Temp 36.5"
• Pode enviar um de cada vez também

*Notas Clínicas:*
• Descreva observações sobre o paciente
• Ex: "Paciente consciente, refere dor abdominal"

*Finalização:*
• "Finalizar" / "Encerrar plantão"

*Ajuda:*
• "Ajuda" / "Como funciona"
• "Status" / "Situação atual"

*Cancelamento:*
• "Não" / "Cancelar" (durante confirmações)

Digite qualquer comando para começar!
""".strip()
    
    return estado


def orientar_como_funciona(estado: GraphState) -> GraphState:
    """Explica como funciona o sistema"""
    estado.resposta_usuario = """
ℹ️ *Como Funciona o Sistema*

*1. Confirmação de Presença*
Primeiro, confirme que chegou ao plantão

*2. Coleta de Dados*
Informe sinais vitais e observações clínicas

*3. Finalização*
Encerre o plantão quando terminar

*Recursos Importantes:*
• ✅ Confirmação antes de salvar dados
• 🔄 Coleta incremental (pode enviar aos poucos)
• 🤖 Identificação automática de sintomas
• 📊 Relatórios automáticos

*Segurança:*
• Sempre pedimos confirmação antes de ações importantes
• Seus dados são salvos automaticamente
• Sistema detecta e previne erros

*Dúvidas?*
Digite "ajuda" a qualquer momento!
""".strip()
    
    return estado


def orientar_status_atual(estado: GraphState) -> GraphState:
    """Mostra status atual detalhado do plantão"""
    
    # Dados básicos
    info_basica = []
    if estado.core.schedule_id:
        info_basica.append(f"📋 Plantão: {estado.core.schedule_id}")
    if estado.core.data_relatorio:
        info_basica.append(f"📅 Data: {estado.core.data_relatorio}")
    
    # Status detalhado
    status_detalhado = []
    
    # Presença
    if estado.metadados.get("presenca_confirmada", False):
        status_detalhado.append("✅ Presença confirmada")
    else:
        status_detalhado.append("❌ Presença pendente")
    
    # Sinais vitais
    if estado.metadados.get("sinais_vitais_realizados", False):
        status_detalhado.append("✅ Sinais vitais completos")
    else:
        num_coletados = len(estado.vitais.processados)
        total_obrigatorios = len(SINAIS_VITAIS_OBRIGATORIOS)
        status_detalhado.append(f"⏳ Sinais vitais: {num_coletados}/{total_obrigatorios}")
    
    # Nota clínica
    if estado.metadados.get("nota_clinica_enviada", False):
        status_detalhado.append("✅ Nota clínica enviada")
        
        num_sintomas = estado.metadados.get("sintomas_identificados", 0)
        if num_sintomas > 0:
            status_detalhado.append(f"🔍 {num_sintomas} sintoma(s) identificado(s)")
    else:
        status_detalhado.append("⏳ Nota clínica pendente")
    
    # Finalização
    if estado.metadados.get("plantao_finalizado", False):
        status_detalhado.append("🎉 Plantão finalizado")
    else:
        pode_finalizar = (
            estado.metadados.get("presenca_confirmada", False) and
            estado.metadados.get("sinais_vitais_realizados", False)
        )
        if pode_finalizar:
            status_detalhado.append("✅ Pronto para finalizar")
        else:
            status_detalhado.append("⏳ Aguardando dados para finalizar")
    
    # Montar resposta
    partes_resposta = ["📊 *Status do Plantão*", ""]
    
    if info_basica:
        partes_resposta.extend(info_basica)
        partes_resposta.append("")
    
    partes_resposta.extend(status_detalhado)
    
    # Próximos passos
    proximos_passos = []
    if not estado.metadados.get("presenca_confirmada", False):
        proximos_passos.append("1. Confirmar presença")
    elif not estado.metadados.get("sinais_vitais_realizados", False):
        proximos_passos.append("1. Completar sinais vitais")
    elif estado.metadados.get("presenca_confirmada", False) and estado.metadados.get("sinais_vitais_realizados", False):
        proximos_passos.append("1. Finalizar plantão")
    
    if proximos_passos:
        partes_resposta.extend(["", "*Próximo passo:*"])
        partes_resposta.extend(proximos_passos)
    
    estado.resposta_usuario = "\n".join(partes_resposta)
    
    return estado
