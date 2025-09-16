"""
Fluxo de coleta de sinais vitais e dados clínicos
Implementa coleta incremental e two-phase commit
"""
from typing import Dict, Any, Optional
from app.graph.state import GraphState
from app.graph.clinical_extractor import (
    extrair_sinais_vitais_semanticos, SINAIS_VITAIS_OBRIGATORIOS,
    validar_sinais_vitais_completos, gerar_resumo_sinais_vitais
)
from app.graph.tools import atualizar_dados_clinicos
from app.infra.tpc import (
    criar_acao_pendente, gerar_mensagem_confirmacao,
    acao_pode_ser_executada, marcar_acao_confirmada,
    marcar_acao_executada, limpar_acao_pendente
)
from app.infra.confirm import is_yes_semantic, is_no_semantic, is_yes, is_no
from app.infra.logging import obter_logger

logger = obter_logger(__name__)


async def clinical_flow(estado: GraphState) -> GraphState:
    """
    Fluxo principal de coleta de sinais vitais e dados clínicos com classificação semântica
    """
    logger.info("Iniciando fluxo clínico", session_id=estado.core.session_id)
    
    # Verificar se há ação pendente para executar
    if estado.aux.acao_pendente and acao_pode_ser_executada(estado.aux.acao_pendente):
        return await executar_salvamento_clinico(estado)
    
    # Verificar se é resposta a pergunta de confirmação
    if estado.aux.ultima_pergunta and estado.aux.fluxo_que_perguntou == "clinical":
        return await processar_resposta_confirmacao_clinica(estado)
    
    # Usar classificação semântica para processar entrada do usuário
    await processar_entrada_clinica_semantica(estado)
    
    # Decidir próximo passo baseado no que foi coletado
    return await processar_dados_coletados(estado)


async def processar_entrada_clinica_semantica(estado: GraphState) -> None:
    """Processa entrada clínica usando classificação semântica"""
    texto = estado.texto_usuario or ""
    
    if not texto.strip():
        return
    
    try:
        from app.graph.semantic_classifier import classify_semantic, IntentType
        
        resultado = await classify_semantic(texto, estado)
        
        logger.info(
            "Entrada clínica classificada semanticamente",
            intent=resultado.intent,
            confidence=resultado.confidence,
            session_id=estado.core.session_id
        )
        
        # Processar sinais vitais se detectados
        if resultado.intent == IntentType.SINAIS_VITAIS and resultado.vital_signs:
            # Merge com sinais vitais já coletados
            estado.vitais.processados.update(resultado.vital_signs)
            
            # Recalcular faltantes
            estado.vitais.faltantes = [
                sv for sv in SINAIS_VITAIS_OBRIGATORIOS 
                if sv not in estado.vitais.processados
            ]
            
            logger.info(
                "Sinais vitais processados semanticamente",
                novos_sinais=list(resultado.vital_signs.keys()),
                total_coletados=len(estado.vitais.processados),
                faltantes=len(estado.vitais.faltantes),
                confidence=resultado.confidence
            )
        
        # Processar nota clínica se detectada
        elif resultado.intent == IntentType.NOTA_CLINICA:
            estado.nota.texto_bruto = texto.strip()
            logger.info(
                "Nota clínica detectada semanticamente", 
                tamanho=len(texto),
                confidence=resultado.confidence
            )
        
        # Se classificação não foi específica, tentar fallback
        elif resultado.intent == IntentType.INDEFINIDO:
            await processar_entrada_fallback(estado, texto)
    
    except Exception as e:
        logger.error(f"Erro na classificação semântica clínica: {e}")
        # Usar fallback em caso de erro
        await processar_entrada_fallback(estado, texto)


async def processar_entrada_fallback(estado: GraphState, texto: str) -> None:
    """Processamento fallback quando classificação semântica falha"""
    # Usar extrator semântico como fallback
    resultado_vitais = await extrair_sinais_vitais_semanticos(texto)
    
    if resultado_vitais.processados:
        estado.vitais.processados.update(resultado_vitais.processados)
        estado.vitais.faltantes = [
            sv for sv in SINAIS_VITAIS_OBRIGATORIOS 
            if sv not in estado.vitais.processados
        ]
        
        logger.info(
            "Sinais vitais processados via fallback",
            novos_sinais=list(resultado_vitais.processados.keys())
        )
    
    # Verificar se é nota clínica por heurísticas
    nota_clinica = await extrair_nota_clinica(texto)
    if nota_clinica:
        estado.nota.texto_bruto = nota_clinica
        logger.info("Nota clínica detectada via fallback", tamanho=len(nota_clinica))


async def extrair_nota_clinica(texto: str) -> Optional[str]:
    """
    Extrai nota clínica do texto usando heurísticas
    """
    if not texto or len(texto.strip()) < 10:
        return None
    
    # Indicadores de nota clínica
    indicadores_nota = [
        "paciente", "observação", "observacao", "relatório", "relatorio",
        "sintoma", "queixa", "comportamento", "estado", "apresenta",
        "refere", "nega", "consciente", "orientado", "deambula"
    ]
    
    texto_lower = texto.lower()
    
    # Se contém indicadores de nota clínica e não é apenas sinais vitais
    if any(indicador in texto_lower for indicador in indicadores_nota):
        # Verificar se não é apenas sinais vitais
        resultado_vitais = await extrair_sinais_vitais_semanticos(texto)
        if not resultado_vitais.processados or len(texto.strip()) > 50:
            return texto.strip()
    
    return None


async def processar_dados_coletados(estado: GraphState) -> GraphState:
    """Processa dados coletados e decide próximo passo"""
    
    tem_vitais = len(estado.vitais.processados) > 0
    vitais_completos = validar_sinais_vitais_completos(estado.vitais.processados)
    tem_nota = bool(estado.nota.texto_bruto)
    
    # Se não tem nada, solicitar dados
    if not tem_vitais and not tem_nota:
        return solicitar_sinais_vitais(estado)
    
    # Se tem sinais vitais parciais, solicitar faltantes
    if tem_vitais and not vitais_completos:
        return solicitar_sinais_vitais_faltantes(estado)
    
    # Se tem dados suficientes, preparar para salvar
    if vitais_completos or tem_nota:
        return await preparar_salvamento_clinico(estado)
    
    # Caso padrão - solicitar dados
    return solicitar_sinais_vitais(estado)


def solicitar_sinais_vitais(estado: GraphState) -> GraphState:
    """Solicita sinais vitais completos do usuário"""
    estado.resposta_usuario = """
🩺 *Sinais Vitais*

Por favor, informe os sinais vitais do paciente:

• *PA* (Pressão Arterial): Ex: 120x80
• *FC* (Frequência Cardíaca): Ex: 78 bpm
• *FR* (Frequência Respiratória): Ex: 18 irpm
• *Sat* (Saturação): Ex: 97%
• *Temp* (Temperatura): Ex: 36.5°C

Você pode enviar todos juntos ou um de cada vez.
""".strip()
    
    # Marcar pergunta pendente para coleta incremental
    estado.aux.ultima_pergunta = "Aguardando sinais vitais"
    estado.aux.fluxo_que_perguntou = "clinical"
    
    return estado


def solicitar_sinais_vitais_faltantes(estado: GraphState) -> GraphState:
    """Solicita apenas os sinais vitais que ainda faltam"""
    faltantes = estado.vitais.faltantes
    coletados = gerar_resumo_sinais_vitais(estado.vitais.processados)
    
    # Mapear nomes amigáveis
    nomes_amigaveis = {
        "PA": "Pressão Arterial (ex: 120x80)",
        "FC": "Frequência Cardíaca (ex: 78 bpm)",
        "FR": "Frequência Respiratória (ex: 18 irpm)",
        "Sat": "Saturação (ex: 97%)",
        "Temp": "Temperatura (ex: 36.5°C)"
    }
    
    lista_faltantes = []
    for sv in faltantes:
        nome_amigavel = nomes_amigaveis.get(sv, sv)
        lista_faltantes.append(f"• *{sv}*: {nome_amigavel}")
    
    faltantes_texto = "\n".join(lista_faltantes)
    
    estado.resposta_usuario = f"""
📊 *Sinais Vitais - Dados Coletados*

*Já coletados:*
{coletados}

*Ainda faltam:*
{faltantes_texto}

Por favor, informe os sinais vitais que ainda faltam.
""".strip()
    
    # Manter pergunta pendente
    estado.aux.ultima_pergunta = f"Aguardando sinais vitais faltantes: {', '.join(faltantes)}"
    estado.aux.fluxo_que_perguntou = "clinical"
    
    return estado


async def preparar_salvamento_clinico(estado: GraphState) -> GraphState:
    """Prepara salvamento dos dados clínicos (staging do two-phase commit)"""
    
    # Determinar o que será salvo
    dados_vitais = estado.vitais.processados if estado.vitais.processados else None
    nota_clinica = estado.nota.texto_bruto
    sintomas_rag = estado.nota.sintomas_rag if estado.nota.sintomas_rag else None
    
    # Criar resumo para confirmação
    resumo_parts = []
    
    if dados_vitais:
        resumo_vitais = gerar_resumo_sinais_vitais(dados_vitais)
        resumo_parts.append(f"*Sinais Vitais:*\n{resumo_vitais}")
    
    if nota_clinica:
        nota_preview = nota_clinica[:100] + "..." if len(nota_clinica) > 100 else nota_clinica
        resumo_parts.append(f"*Nota Clínica:*\n{nota_preview}")
    
    if sintomas_rag:
        num_sintomas = len(sintomas_rag)
        resumo_parts.append(f"*Sintomas Identificados:* {num_sintomas} itens")
    
    resumo_completo = "\n\n".join(resumo_parts)
    
    # Criar ação pendente
    payload = {
        "vitais": dados_vitais,
        "nota": nota_clinica,
        "sintomas": sintomas_rag
    }
    
    descricao = f"Salvar os seguintes dados clínicos?\n\n{resumo_completo}"
    
    acao_pendente = criar_acao_pendente(
        fluxo_destino="clinical_commit",
        payload=payload,
        descricao=descricao
    )
    
    estado.aux.acao_pendente = acao_pendente
    
    # Definir pergunta de confirmação
    mensagem_confirmacao = gerar_mensagem_confirmacao(acao_pendente)
    estado.aux.ultima_pergunta = mensagem_confirmacao
    estado.aux.fluxo_que_perguntou = "clinical"
    
    estado.resposta_usuario = mensagem_confirmacao
    
    return estado


async def processar_resposta_confirmacao_clinica(estado: GraphState) -> GraphState:
    """Processa resposta do usuário à confirmação de salvamento"""
    texto = estado.texto_usuario or ""
    
    if is_yes(texto):
        # Confirmar e executar
        if estado.aux.acao_pendente:
            marcar_acao_confirmada(estado.aux.acao_pendente)
        return await executar_salvamento_clinico(estado)
    
    elif is_no(texto):
        # Cancelar salvamento
        estado.aux.acao_pendente = limpar_acao_pendente()
        estado.aux.ultima_pergunta = None
        estado.aux.fluxo_que_perguntou = None
        
        estado.resposta_usuario = """
❌ *Salvamento Cancelado*

Os dados não foram salvos. 

Você pode:
• Informar novos sinais vitais
• Enviar nota clínica
• Fazer outras alterações
""".strip()
        
        return estado
    
    else:
        # Resposta não reconhecida
        estado.resposta_usuario = """
❓ Não entendi sua resposta.

Digite *sim* para salvar os dados ou *não* para cancelar.
""".strip()
        
        return estado


async def executar_salvamento_clinico(estado: GraphState) -> GraphState:
    """Executa o salvamento dos dados clínicos (commit)"""
    acao = estado.aux.acao_pendente
    
    if not acao or not acao.get("confirmado", False):
        logger.error("Tentativa de executar ação não confirmada")
        estado.resposta_usuario = "Erro interno. Tente novamente."
        return estado
    
    try:
        # Extrair dados da ação
        payload = acao.get("payload", {})
        dados_vitais = payload.get("vitais")
        nota_clinica = payload.get("nota")
        sintomas_rag = payload.get("sintomas")
        
        # Chamar Lambda updateClinicalData
        logger.info("Executando salvamento de dados clínicos")
        resultado = atualizar_dados_clinicos(
            estado, dados_vitais, nota_clinica, sintomas_rag
        )
        
        # Marcar ação como executada
        marcar_acao_executada(acao)
        
        # Atualizar metadados
        if dados_vitais:
            estado.metadados["sinais_vitais_realizados"] = True
        
        if nota_clinica:
            estado.metadados["nota_clinica_enviada"] = True
        
        # Limpar dados da ação
        estado.aux.acao_pendente = limpar_acao_pendente()
        estado.aux.ultima_pergunta = None
        estado.aux.fluxo_que_perguntou = None
        
        # Verificar se deve retomar finalização
        if estado.aux.retomar_apos and estado.aux.retomar_apos.get("flow") == "finalizar":
            estado.resposta_usuario = """
✅ *Dados Salvos com Sucesso*

Dados clínicos salvos! 

Agora vamos finalizar o plantão...
""".strip()
            
            # O router detectará a retomada na próxima interação
        else:
            estado.resposta_usuario = """
✅ *Dados Salvos com Sucesso*

Seus dados clínicos foram salvos com sucesso!

Você pode:
• Enviar mais sinais vitais
• Adicionar notas clínicas
• Finalizar o plantão
""".strip()
        
        logger.info("Salvamento de dados clínicos executado com sucesso")
        
    except Exception as e:
        logger.error(f"Erro ao executar salvamento clínico: {e}")
        
        estado.resposta_usuario = """
❌ *Erro no Salvamento*

Ocorreu um erro ao salvar os dados. 
Tente novamente em alguns instantes.
""".strip()
    
    return estado


def orientar_sobre_dados_clinicos(estado: GraphState) -> GraphState:
    """Orienta usuário sobre como enviar dados clínicos"""
    estado.resposta_usuario = """
🩺 *Dados Clínicos*

Você pode enviar:

*Sinais Vitais:*
• PA, FC, FR, Sat, Temp
• Ex: "PA 120x80, FC 78, Sat 97%"

*Notas Clínicas:*
• Observações sobre o paciente
• Sintomas, comportamento, etc.

Como deseja proceder?
""".strip()
    
    return estado
