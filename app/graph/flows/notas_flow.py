"""
Fluxo de notas clínicas e identificação de sintomas via RAG
Apenas notas/sintomas, sem sinais vitais
"""
from typing import Dict, Any, List
from app.graph.state import GraphState
from app.graph.tools import atualizar_dados_clinicos
from app.rag.pinecone_client import buscar_sintomas_similares
from app.infra.tpc import (
    criar_acao_pendente, gerar_mensagem_confirmacao,
    acao_pode_ser_executada, marcar_acao_confirmada,
    marcar_acao_executada, limpar_acao_pendente
)
from app.infra.confirm import is_yes, is_no
from app.infra.logging import obter_logger

logger = obter_logger(__name__)


async def processar_entrada_notas_semantica(estado: GraphState) -> None:
    """Processa entrada de notas usando classificação semântica"""
    texto = estado.texto_usuario or ""
    
    if not texto.strip():
        return
    
    try:
        from app.graph.semantic_classifier import classify_semantic, IntentType
        
        resultado = await classify_semantic(texto, estado)
        
        logger.info(
            "Entrada de notas classificada semanticamente",
            intent=resultado.intent,
            confidence=resultado.confidence,
            session_id=estado.core.session_id
        )
        
        # Processar nota clínica se detectada
        if resultado.intent == IntentType.NOTA_CLINICA or resultado.clinical_note:
            nota_clinica = resultado.clinical_note or texto.strip()
            estado.nota.texto_bruto = nota_clinica
            logger.info(
                "Nota clínica detectada semanticamente", 
                tamanho=len(nota_clinica),
                confidence=resultado.confidence
            )
        # Se é texto longo mas não classificado como nota, assumir como nota
        elif len(texto.strip()) > 20:
            estado.nota.texto_bruto = texto.strip()
            logger.info("Texto longo assumido como nota clínica")
    
    except Exception as e:
        logger.error(f"Erro na classificação semântica de notas: {e}")
        # Fallback: se é texto longo, assumir como nota
        if len(texto.strip()) > 20:
            estado.nota.texto_bruto = texto.strip()
            logger.info("Nota clínica detectada via fallback")


async def notas_flow(estado: GraphState) -> GraphState:
    """
    Fluxo principal de notas clínicas e sintomas
    """
    logger.info("Iniciando fluxo de notas", session_id=estado.core.session_id)
    
    # Verificar se há ação pendente para executar
    if estado.aux.acao_pendente and acao_pode_ser_executada(estado.aux.acao_pendente):
        return executar_salvamento_nota(estado)
    
    # Verificar se é resposta a pergunta de confirmação
    if estado.aux.ultima_pergunta and estado.aux.fluxo_que_perguntou == "notas":
        return processar_resposta_confirmacao_nota(estado)
    
    # Usar classificação semântica para processar entrada
    await processar_entrada_notas_semantica(estado)
    
    # Verificar se temos nota suficiente
    if not estado.nota.texto_bruto or len(estado.nota.texto_bruto.strip()) < 10:
        return solicitar_nota_clinica(estado)
    
    # Processar sintomas via RAG
    try:
        sintomas_identificados = await processar_sintomas_via_rag(estado.nota.texto_bruto)
        estado.nota.sintomas_rag = sintomas_identificados
        
        logger.info(
            "Sintomas identificados via RAG",
            num_sintomas=len(sintomas_identificados),
            session_id=estado.core.session_id
        )
        
    except Exception as e:
        logger.error(f"Erro ao processar sintomas via RAG: {e}")
        estado.nota.sintomas_rag = []
    
    # Preparar para salvar
    return preparar_salvamento_nota(estado)


async def processar_sintomas_via_rag(texto_nota: str) -> List[Dict[str, Any]]:
    """
    Processa nota clínica via RAG Pinecone para identificar sintomas
    """
    if not texto_nota or len(texto_nota.strip()) < 10:
        return []
    
    # Extrair termos relevantes da nota usando LLM semântico
    try:
        termos_extraidos = await extrair_termos_clinicos_semanticos(texto_nota)
    except:
        # Fallback para função legacy
        termos_extraidos = extrair_termos_clinicos(texto_nota)
    
    if not termos_extraidos:
        return []
    
    # Buscar sintomas similares no Pinecone
    sintomas_encontrados = []
    
    for termo in termos_extraidos:
        try:
            resultados = buscar_sintomas_similares(termo, k=3, limiar_score=0.7)
            
            for resultado in resultados:
                # Converter para formato SymptomReport
                symptom_report = {
                    "symptomDefinition": resultado.get("sintoma", ""),
                    "altNotepadMain": termo,
                    "symptomCategory": resultado.get("categoria", "Geral"),
                    "symptomSubCategory": resultado.get("subcategoria", "Geral"),
                    "descricaoComparada": resultado.get("descricao", resultado.get("sintoma", "")),
                    "coeficienteSimilaridade": float(resultado.get("score", 0.0))
                }
                
                sintomas_encontrados.append(symptom_report)
                
        except Exception as e:
            logger.error(f"Erro ao buscar sintomas para termo '{termo}': {e}")
            continue
    
    # Remover duplicatas baseado em symptomDefinition
    sintomas_unicos = []
    sintomas_vistos = set()
    
    for sintoma in sintomas_encontrados:
        definicao = sintoma.get("symptomDefinition", "")
        if definicao and definicao not in sintomas_vistos:
            sintomas_vistos.add(definicao)
            sintomas_unicos.append(sintoma)
    
    # Ordenar por coeficiente de similaridade (maior primeiro)
    sintomas_unicos.sort(key=lambda x: x.get("coeficienteSimilaridade", 0.0), reverse=True)
    
    # Limitar a top 5 sintomas
    return sintomas_unicos[:5]


async def extrair_termos_clinicos_semanticos(texto: str) -> List[str]:
    """
    Extrai termos clínicos relevantes do texto usando LLM semântico
    """
    if not texto or len(texto.strip()) < 10:
        return []
    
    try:
        from app.graph.semantic_classifier import classify_semantic, IntentType
        from app.graph.state import GraphState, CoreState
        
        # Criar estado mínimo para classificação
        estado_temp = GraphState(
            core=CoreState(session_id="temp", numero_telefone="temp"),
            texto_usuario=texto
        )
        
        # Classificar semanticamente
        resultado = await classify_semantic(texto, estado_temp)
        
        if resultado.intent == IntentType.NOTA_CLINICA and resultado.clinical_note:
            # O LLM já extraiu a nota clínica, usar como termo principal
            return [resultado.clinical_note.strip()]
        else:
            # Usar o texto completo como termo
            return [texto.strip()]
    
    except Exception:
        # Fallback: usar o texto completo
        return [texto.strip()]


def extrair_termos_clinicos(texto: str) -> List[str]:
    """DEPRECATED: Use extrair_termos_clinicos_semanticos() - fallback simples apenas"""
    if not texto or len(texto.strip()) < 10:
        return []
    
    # Fallback muito simples - dividir por frases
    frases = [f.strip() for f in texto.split('.') if len(f.strip()) > 5]
    return frases[:3] if frases else [texto.strip()]  # Limitar a 10 termos


def solicitar_nota_clinica(estado: GraphState) -> GraphState:
    """Solicita nota clínica do usuário"""
    estado.resposta_usuario = """
📝 *Nota Clínica*

Por favor, envie suas observações sobre o paciente:

• Estado geral do paciente
• Sintomas observados ou relatados
• Comportamento e orientação
• Queixas específicas
• Outras observações relevantes

Exemplo:
"Paciente consciente e orientado, refere dor abdominal leve, sem febre. Deambula sem auxílio, alimentação preservada."
""".strip()
    
    estado.aux.ultima_pergunta = "Aguardando nota clínica"
    estado.aux.fluxo_que_perguntou = "notas"
    
    return estado


def preparar_salvamento_nota(estado: GraphState) -> GraphState:
    """Prepara salvamento da nota clínica (staging do two-phase commit)"""
    
    nota_clinica = estado.nota.texto_bruto
    sintomas_rag = estado.nota.sintomas_rag
    
    # Criar resumo para confirmação
    resumo_parts = []
    
    if nota_clinica:
        nota_preview = nota_clinica[:150] + "..." if len(nota_clinica) > 150 else nota_clinica
        resumo_parts.append(f"*Nota Clínica:*\n{nota_preview}")
    
    if sintomas_rag:
        sintomas_nomes = [s.get("symptomDefinition", "Sintoma") for s in sintomas_rag[:3]]
        if len(sintomas_rag) > 3:
            sintomas_texto = ", ".join(sintomas_nomes) + f" (e mais {len(sintomas_rag) - 3})"
        else:
            sintomas_texto = ", ".join(sintomas_nomes)
        
        resumo_parts.append(f"*Sintomas Identificados:*\n{sintomas_texto}")
    
    resumo_completo = "\n\n".join(resumo_parts)
    
    # Criar ação pendente
    payload = {
        "nota": nota_clinica,
        "sintomas": sintomas_rag
    }
    
    descricao = f"Salvar nota clínica e sintomas?\n\n{resumo_completo}"
    
    acao_pendente = criar_acao_pendente(
        fluxo_destino="notas_commit",
        payload=payload,
        descricao=descricao
    )
    
    estado.aux.acao_pendente = acao_pendente
    
    # Definir pergunta de confirmação
    mensagem_confirmacao = gerar_mensagem_confirmacao(acao_pendente)
    estado.aux.ultima_pergunta = mensagem_confirmacao
    estado.aux.fluxo_que_perguntou = "notas"
    
    estado.resposta_usuario = mensagem_confirmacao
    
    return estado


def processar_resposta_confirmacao_nota(estado: GraphState) -> GraphState:
    """Processa resposta do usuário à confirmação de salvamento da nota"""
    texto = estado.texto_usuario or ""
    
    if is_yes(texto):
        # Confirmar e executar
        if estado.aux.acao_pendente:
            marcar_acao_confirmada(estado.aux.acao_pendente)
        return executar_salvamento_nota(estado)
    
    elif is_no(texto):
        # Cancelar salvamento
        estado.aux.acao_pendente = limpar_acao_pendente()
        estado.aux.ultima_pergunta = None
        estado.aux.fluxo_que_perguntou = None
        
        estado.resposta_usuario = """
❌ *Salvamento Cancelado*

A nota clínica não foi salva. 

Você pode:
• Enviar uma nova nota clínica
• Fazer alterações na nota atual
• Informar sinais vitais
""".strip()
        
        return estado
    
    else:
        # Resposta não reconhecida
        estado.resposta_usuario = """
❓ Não entendi sua resposta.

Digite *sim* para salvar a nota ou *não* para cancelar.
""".strip()
        
        return estado


def executar_salvamento_nota(estado: GraphState) -> GraphState:
    """Executa o salvamento da nota clínica (commit)"""
    acao = estado.aux.acao_pendente
    
    if not acao or not acao.get("confirmado", False):
        logger.error("Tentativa de executar ação não confirmada")
        estado.resposta_usuario = "Erro interno. Tente novamente."
        return estado
    
    try:
        # Extrair dados da ação
        payload = acao.get("payload", {})
        nota_clinica = payload.get("nota")
        sintomas_rag = payload.get("sintomas")
        
        # Chamar Lambda updateClinicalData (apenas nota/sintomas)
        logger.info("Executando salvamento de nota clínica")
        resultado = atualizar_dados_clinicos(
            estado, dados_vitais=None, nota_clinica=nota_clinica, sintomas_rag=sintomas_rag
        )
        
        # Marcar ação como executada
        marcar_acao_executada(acao)
        
        # Atualizar metadados
        estado.metadados["nota_clinica_enviada"] = True
        
        if sintomas_rag:
            estado.metadados["sintomas_identificados"] = len(sintomas_rag)
        
        # Limpar dados da ação
        estado.aux.acao_pendente = limpar_acao_pendente()
        estado.aux.ultima_pergunta = None
        estado.aux.fluxo_que_perguntou = None
        
        # Gerar resposta de sucesso
        partes_resposta = ["✅ *Nota Clínica Salva*", "", "Sua nota clínica foi salva com sucesso!"]
        
        if sintomas_rag:
            num_sintomas = len(sintomas_rag)
            partes_resposta.append(f"🔍 Foram identificados {num_sintomas} sintoma(s) relevante(s).")
        
        partes_resposta.extend([
            "",
            "Você pode:",
            "• Enviar mais observações",
            "• Informar sinais vitais",
            "• Finalizar o plantão"
        ])
        
        estado.resposta_usuario = "\n".join(partes_resposta)
        
        logger.info(
            "Salvamento de nota clínica executado com sucesso",
            num_sintomas=len(sintomas_rag) if sintomas_rag else 0
        )
        
    except Exception as e:
        logger.error(f"Erro ao executar salvamento de nota: {e}")
        
        estado.resposta_usuario = """
❌ *Erro no Salvamento*

Ocorreu um erro ao salvar a nota clínica. 
Tente novamente em alguns instantes.
""".strip()
    
    return estado


def orientar_sobre_notas_clinicas(estado: GraphState) -> GraphState:
    """Orienta usuário sobre como enviar notas clínicas"""
    estado.resposta_usuario = """
📝 *Notas Clínicas*

Envie suas observações sobre o paciente:

*Exemplos do que incluir:*
• Estado de consciência e orientação
• Sintomas relatados ou observados
• Comportamento e humor
• Alimentação e hidratação
• Mobilidade e independência
• Queixas específicas

*Exemplo de nota:*
"Paciente consciente, orientado, colaborativo. Refere dor lombar moderada. Alimentação preservada, deambula com auxílio. Sem alterações respiratórias."

Como deseja proceder?
""".strip()
    
    return estado
