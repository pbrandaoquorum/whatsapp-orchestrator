"""
Classificador semântico via LLM (GPT-4o-mini) com LLM as a Judge
Substitui detecção por keywords/regex por classificação inteligente
"""
import json
from typing import Dict, Any, Optional, List
from enum import Enum
from dataclasses import dataclass
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field

from app.graph.state import GraphState
from app.infra.logging import obter_logger
from app.infra.timeutils import agora_br
from app.infra.circuit_breaker import circuit_breaker, LLM_CIRCUIT_CONFIG, CircuitBreakerError

logger = obter_logger(__name__)


class IntentType(str, Enum):
    """Tipos de intenção suportados pelo classificador"""
    # Intenções principais
    CONFIRMAR_PRESENCA = "confirmar_presenca"
    CANCELAR_PRESENCA = "cancelar_presenca"
    SINAIS_VITAIS = "sinais_vitais"
    NOTA_CLINICA = "nota_clinica"
    FINALIZAR_PLANTAO = "finalizar_plantao"
    
    # Confirmações genéricas
    CONFIRMACAO_SIM = "confirmacao_sim"
    CONFIRMACAO_NAO = "confirmacao_nao"
    
    # Estados auxiliares
    PEDIR_AJUDA = "pedir_ajuda"
    INDEFINIDO = "indefinido"


@dataclass
class ClassificationResult:
    """Resultado da classificação semântica"""
    intent: IntentType
    confidence: float
    rationale: str
    vital_signs: Optional[Dict[str, Any]] = None
    clinical_note: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class SemanticClassificationRequest(BaseModel):
    """Schema para request de classificação semântica"""
    intent: str = Field(description="Intenção classificada")
    confidence: float = Field(ge=0.0, le=1.0, description="Confiança da classificação (0.0-1.0)")
    rationale: str = Field(description="Justificativa da classificação")
    vital_signs: Optional[Dict[str, Any]] = Field(None, description="Sinais vitais extraídos")
    clinical_note: Optional[str] = Field(None, description="Nota clínica extraída")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Metadados adicionais")


class JudgeValidationRequest(BaseModel):
    """Schema para validação via LLM as a Judge"""
    is_valid: bool = Field(description="Se a classificação está correta")
    confidence: float = Field(ge=0.0, le=1.0, description="Confiança na validação")
    corrections: Optional[Dict[str, Any]] = Field(None, description="Correções sugeridas")
    rationale: str = Field(description="Justificativa da validação")


def criar_prompt_classificador_sistema() -> str:
    """Cria prompt do sistema para classificação semântica"""
    return """
Você é um assistente especializado em classificar intenções de mensagens de cuidadores em plantões domiciliares.

CONTEXTO:
- Cuidadores enviam mensagens via WhatsApp durante plantões
- Sistema precisa entender intenção para orquestrar fluxos corretos
- Foco em precisão e contexto médico/hospitalar

INTENÇÕES DISPONÍVEIS:
1. confirmar_presenca: Confirmar chegada/presença no plantão
   - Exemplos: "cheguei", "estou aqui", "confirmo presença"
   
2. cancelar_presenca: Cancelar/desmarcar plantão
   - Exemplos: "não posso ir", "cancelar", "imprevisto"
   
3. sinais_vitais: Informar dados vitais do paciente
   - Exemplos: "PA 120x80", "FC 78 bpm", "temperatura 36.5"
   - SEMPRE extrair valores em vital_signs: {"PA": "120x80", "FC": 78, "Temp": 36.5}
   
4. nota_clinica: Observações clínicas sobre o paciente
   - Exemplos: "paciente consciente", "queixa de dor", "sem alterações"
   - SEMPRE extrair texto em clinical_note
   
5. finalizar_plantao: Encerrar plantão e enviar relatório
   - Exemplos: "finalizar", "encerrar", "terminar plantão"
   
6. confirmacao_sim: Confirmação positiva genérica
   - Exemplos: "sim", "ok", "confirmo", "pode ser"
   
7. confirmacao_nao: Confirmação negativa genérica
   - Exemplos: "não", "cancelar", "não quero"
   
8. pedir_ajuda: Solicitação de ajuda/orientação
   - Exemplos: "ajuda", "não sei", "como funciona"
   
9. indefinido: Quando não é possível classificar com certeza

REGRAS IMPORTANTES:
1. Analise o CONTEXTO do estado atual (presença confirmada, dados coletados, etc.)
2. Para sinais vitais, SEMPRE extraia os valores em formato estruturado
3. Para notas clínicas, preserve o texto original
4. Seja conservador: prefira "indefinido" se não tiver certeza
5. Confidence >= 0.7 para classificações específicas
6. Confidence >= 0.9 para confirmações sim/não

Responda APENAS com JSON válido no formato especificado.
""".strip()


def criar_prompt_judge_sistema() -> str:
    """Cria prompt do sistema para LLM as a Judge"""
    return """
Você é um juiz especializado em validar classificações de intenções médicas.

SUA TAREFA:
- Avaliar se a classificação de intenção está CORRETA
- Verificar se dados extraídos (sinais vitais, notas) estão PRECISOS
- Sugerir correções se necessário

CRITÉRIOS DE VALIDAÇÃO:
1. PRECISÃO: A intenção classificada corresponde ao texto?
2. COMPLETUDE: Dados importantes foram extraídos corretamente?
3. CONTEXTO: A classificação faz sentido no contexto médico?
4. CONFIANÇA: O nível de confiança é apropriado?

SINAIS VITAIS - FORMATOS VÁLIDOS:
- PA: "120x80", "130/90" → {"PA": "120x80"}
- FC: "78 bpm", "FC 82" → {"FC": 78}
- FR: "18 irpm", "FR 20" → {"FR": 18}  
- Sat: "97%", "saturação 95" → {"Sat": 97}
- Temp: "36.5°C", "temperatura 37.2" → {"Temp": 36.5}

CORREÇÕES COMUNS:
- Sinais vitais mal extraídos ou em formato incorreto
- Intenção muito específica quando deveria ser genérica
- Confiança muito alta para texto ambíguo
- Dados clínicos importantes não capturados

Responda APENAS com JSON válido.
""".strip()


def criar_prompt_usuario_classificacao(texto: str, estado: GraphState) -> str:
    """Cria prompt do usuário para classificação"""
    contexto_partes = []
    
    # Contexto do turno
    if estado.core.cancelado:
        contexto_partes.append("- Turno CANCELADO")
    elif not estado.core.turno_permitido:
        contexto_partes.append("- Turno NÃO PERMITIDO")
    else:
        contexto_partes.append("- Turno ativo")
    
    # Contexto de presença
    presenca_confirmada = estado.metadados.get("presenca_confirmada", False)
    if presenca_confirmada:
        contexto_partes.append("- Presença JÁ CONFIRMADA")
    else:
        contexto_partes.append("- Presença PENDENTE")
    
    # Contexto de sinais vitais
    sv_realizados = estado.metadados.get("sinais_vitais_realizados", False)
    if sv_realizados:
        contexto_partes.append("- Sinais vitais JÁ COLETADOS")
    else:
        sv_parciais = len(estado.vitais.processados)
        if sv_parciais > 0:
            contexto_partes.append(f"- Sinais vitais PARCIAIS ({sv_parciais} coletados)")
        else:
            contexto_partes.append("- Sinais vitais PENDENTES")
    
    # Contexto de pergunta pendente
    if estado.aux.ultima_pergunta:
        contexto_partes.append(f"- Pergunta pendente: {estado.aux.ultima_pergunta[:50]}...")
    
    # Contexto de retomada
    if estado.aux.retomar_apos:
        fluxo_retomar = estado.aux.retomar_apos.get("flow", "desconhecido")
        contexto_partes.append(f"- Deve retomar: {fluxo_retomar}")
    
    contexto = "\n".join(contexto_partes)
    
    return f"""
CONTEXTO ATUAL:
{contexto}

MENSAGEM DO USUÁRIO:
"{texto}"

Classifique a intenção considerando o contexto médico e estado atual.
""".strip()


def criar_prompt_usuario_judge(
    texto_original: str,
    classificacao: Dict[str, Any],
    estado: GraphState
) -> str:
    """Cria prompt do usuário para validação Judge"""
    return f"""
TEXTO ORIGINAL:
"{texto_original}"

CLASSIFICAÇÃO REALIZADA:
- Intenção: {classificacao.get('intent')}
- Confiança: {classificacao.get('confidence')}
- Justificativa: {classificacao.get('rationale')}
- Sinais Vitais: {classificacao.get('vital_signs')}
- Nota Clínica: {classificacao.get('clinical_note')}

CONTEXTO DO ESTADO:
- Presença Confirmada: {estado.metadados.get('presenca_confirmada', False)}
- SV Realizados: {estado.metadados.get('sinais_vitais_realizados', False)}
- Turno Cancelado: {estado.core.cancelado}

Valide se a classificação está CORRETA e PRECISA.
""".strip()


@circuit_breaker("llm_classifier", LLM_CIRCUIT_CONFIG)
async def _executar_classificacao_llm(texto: str, estado: GraphState) -> Dict[str, Any]:
    """Executa classificação LLM protegida por circuit breaker"""
    # Configurar LLM
    llm = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0.1,  # Baixa temperatura para consistência
        max_tokens=500
    )
    
    # Configurar parser
    parser = JsonOutputParser(pydantic_object=SemanticClassificationRequest)
    
    # Criar mensagens
    system_msg = SystemMessage(content=criar_prompt_classificador_sistema())
    human_msg = HumanMessage(content=criar_prompt_usuario_classificacao(texto, estado))
    
    # Executar classificação
    response = await llm.ainvoke([system_msg, human_msg])
    
    # Parse do resultado
    return parser.parse(response.content)


async def classificar_semanticamente(texto: str, estado: GraphState) -> ClassificationResult:
    """
    Classifica intenção usando LLM semântico com circuit breaker
    """
    if not texto or not texto.strip():
        return ClassificationResult(
            intent=IntentType.INDEFINIDO,
            confidence=0.0,
            rationale="Texto vazio ou inválido"
        )
    
    try:
        inicio = agora_br()
        
        # Executar classificação com circuit breaker
        resultado_raw = await _executar_classificacao_llm(texto, estado)
        
        tempo_execucao = (agora_br() - inicio).total_seconds() * 1000
        
        logger.info(
            "Classificação semântica concluída",
            texto=texto[:50],
            intent=resultado_raw.get("intent"),
            confidence=resultado_raw.get("confidence"),
            tempo_ms=round(tempo_execucao, 2)
        )
        
        # Converter para ClassificationResult
        result = ClassificationResult(
            intent=IntentType(resultado_raw["intent"]),
            confidence=float(resultado_raw["confidence"]),
            rationale=resultado_raw["rationale"],
            vital_signs=resultado_raw.get("vital_signs"),
            clinical_note=resultado_raw.get("clinical_note"),
            metadata=resultado_raw.get("metadata")
        )
        
        # Processar sinais vitais se detectados
        if result.vital_signs:
            result.vital_signs = extrair_sinais_vitais_semanticos(result.vital_signs)
        
        # Validar com LLM as a Judge se confiança for baixa
        if result.confidence < 0.8:
            result = await validar_com_judge(texto, resultado_raw, estado, result)
        
        return result
        
    except CircuitBreakerError:
        logger.warning(
            "Circuit breaker aberto - usando fallback determinístico",
            texto=texto[:50]
        )
        # Fallback para classificação determinística
        return await _fallback_classificacao_deterministica(texto, estado)
        
    except Exception as e:
        logger.error(
            "Erro na classificação semântica",
            texto=texto[:50],
            erro=str(e)
        )
        
        # Fallback seguro
        return ClassificationResult(
            intent=IntentType.INDEFINIDO,
            confidence=0.0,
            rationale=f"Erro na classificação: {str(e)}"
        )


@circuit_breaker("llm_judge", LLM_CIRCUIT_CONFIG)
async def _executar_validacao_judge(
    texto_original: str,
    classificacao_raw: Dict[str, Any],
    estado: GraphState
) -> Dict[str, Any]:
    """Executa validação Judge protegida por circuit breaker"""
    # Configurar LLM Judge
    judge_llm = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0.0,  # Zero temperatura para consistência máxima
        max_tokens=300
    )
    
    # Configurar parser
    parser = JsonOutputParser(pydantic_object=JudgeValidationRequest)
    
    # Criar mensagens para o Judge
    system_msg = SystemMessage(content=criar_prompt_judge_sistema())
    human_msg = HumanMessage(content=criar_prompt_usuario_judge(
        texto_original, classificacao_raw, estado
    ))
    
    # Executar validação
    response = await judge_llm.ainvoke([system_msg, human_msg])
    
    # Parse do resultado
    return parser.parse(response.content)


async def validar_com_judge(
    texto_original: str,
    classificacao_raw: Dict[str, Any],
    estado: GraphState,
    resultado_original: ClassificationResult
) -> ClassificationResult:
    """
    Valida classificação usando LLM as a Judge com circuit breaker
    """
    try:
        inicio = agora_br()
        
        # Executar validação com circuit breaker
        validacao = await _executar_validacao_judge(texto_original, classificacao_raw, estado)
        
        tempo_execucao = (agora_br() - inicio).total_seconds() * 1000
        
        logger.info(
            "Validação Judge concluída",
            is_valid=validacao.get("is_valid"),
            judge_confidence=validacao.get("confidence"),
            corrections=bool(validacao.get("corrections")),
            tempo_ms=round(tempo_execucao, 2)
        )
        
        # Aplicar correções se necessário
        if not validacao.get("is_valid") and validacao.get("corrections"):
            corrections = validacao["corrections"]
            
            # Aplicar correções na classificação
            if "intent" in corrections:
                resultado_original.intent = IntentType(corrections["intent"])
            
            if "confidence" in corrections:
                resultado_original.confidence = float(corrections["confidence"])
            
            if "vital_signs" in corrections:
                resultado_original.vital_signs = extrair_sinais_vitais_semanticos(corrections["vital_signs"])
            
            if "clinical_note" in corrections:
                resultado_original.clinical_note = corrections["clinical_note"]
            
            # Atualizar rationale
            resultado_original.rationale += f" | Judge: {validacao['rationale']}"
            
            logger.info(
                "Classificação corrigida pelo Judge",
                original_intent=classificacao_raw.get("intent"),
                corrected_intent=resultado_original.intent
            )
        
        return resultado_original
        
    except CircuitBreakerError:
        logger.warning("Circuit breaker Judge aberto - pulando validação")
        return resultado_original
        
    except Exception as e:
        logger.error(
            "Erro na validação Judge",
            erro=str(e)
        )
        
        # Retornar resultado original em caso de erro
        return resultado_original


async def _fallback_classificacao_deterministica(texto: str, estado: GraphState) -> ClassificationResult:
    """
    Fallback determinístico quando LLM não está disponível
    Usa regras simples baseadas em palavras-chave
    """
    texto_lower = texto.lower().strip()
    
    # Detectar confirmação de presença
    palavras_presenca = ["cheguei", "chegei", "confirmo", "presente", "aqui"]
    if any(palavra in texto_lower for palavra in palavras_presenca):
        return ClassificationResult(
            intent=IntentType.CONFIRMAR_PRESENCA,
            confidence=0.7,
            rationale="Fallback determinístico - palavras de confirmação detectadas"
        )
    
    # Detectar cancelamento
    palavras_cancelar = ["cancelar", "não posso", "nao posso", "imprevisto"]
    if any(palavra in texto_lower for palavra in palavras_cancelar):
        return ClassificationResult(
            intent=IntentType.CANCELAR_PRESENCA,
            confidence=0.7,
            rationale="Fallback determinístico - palavras de cancelamento detectadas"
        )
    
    # Detectar sinais vitais (usar extrator determinístico)
    try:
        from app.graph.clinical_extractor import extrair_sinais_vitais
        resultado_vitais = extrair_sinais_vitais(texto)
        
        if resultado_vitais.processados:
            return ClassificationResult(
                intent=IntentType.SINAIS_VITAIS,
                confidence=0.8,
                rationale="Fallback determinístico - sinais vitais detectados",
                vital_signs=resultado_vitais.processados
            )
    except Exception:
        pass
    
    # Detectar finalização
    palavras_finalizar = ["finalizar", "encerrar", "terminar", "acabar"]
    if any(palavra in texto_lower for palavra in palavras_finalizar):
        return ClassificationResult(
            intent=IntentType.FINALIZAR_PLANTAO,
            confidence=0.7,
            rationale="Fallback determinístico - palavras de finalização detectadas"
        )
    
    # Detectar confirmações genéricas
    palavras_sim = ["sim", "ok", "okay", "confirmo", "beleza", "pode"]
    if any(palavra in texto_lower for palavra in palavras_sim):
        return ClassificationResult(
            intent=IntentType.CONFIRMACAO_SIM,
            confidence=0.6,
            rationale="Fallback determinístico - confirmação positiva detectada"
        )
    
    palavras_nao = ["não", "nao", "nunca", "jamais", "negativo"]
    if any(palavra in texto_lower for palavra in palavras_nao):
        return ClassificationResult(
            intent=IntentType.CONFIRMACAO_NAO,
            confidence=0.6,
            rationale="Fallback determinístico - confirmação negativa detectada"
        )
    
    # Se texto for longo (>20 chars), assumir nota clínica
    if len(texto.strip()) > 20:
        return ClassificationResult(
            intent=IntentType.NOTA_CLINICA,
            confidence=0.5,
            rationale="Fallback determinístico - texto longo assumido como nota clínica",
            clinical_note=texto.strip()
        )
    
    # Fallback final
    return ClassificationResult(
        intent=IntentType.INDEFINIDO,
        confidence=0.3,
        rationale="Fallback determinístico - não foi possível classificar"
    )


def mapear_intencao_para_fluxo(intent: IntentType) -> str:
    """Mapeia intenção semântica para fluxo do LangGraph"""
    mapeamento = {
        IntentType.CONFIRMAR_PRESENCA: "escala",
        IntentType.CANCELAR_PRESENCA: "escala",
        IntentType.SINAIS_VITAIS: "clinical",
        IntentType.NOTA_CLINICA: "notas",
        IntentType.FINALIZAR_PLANTAO: "finalizar",
        IntentType.CONFIRMACAO_SIM: "auxiliar",  # Depende do contexto
        IntentType.CONFIRMACAO_NAO: "auxiliar",  # Depende do contexto
        IntentType.PEDIR_AJUDA: "auxiliar",
        IntentType.INDEFINIDO: "auxiliar"
    }
    
    return mapeamento.get(intent, "auxiliar")


def extrair_sinais_vitais_semanticos(vital_signs: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Processa sinais vitais extraídos semanticamente para formato padrão
    """
    if not vital_signs:
        return {}
    
    processados = {}
    
    # Normalizar formatos
    for chave, valor in vital_signs.items():
        chave_upper = chave.upper()
        
        if chave_upper == "PA":
            # Pressão arterial - garantir formato XxY
            if isinstance(valor, str):
                # Normalizar formatos como "120/80" para "120x80"
                valor_norm = valor.replace("/", "x").replace(" ", "")
                processados["PA"] = valor_norm
            
        elif chave_upper in ["FC", "FR", "SAT"]:
            # Frequências e saturação - garantir int
            if isinstance(valor, (int, float)):
                processados[chave_upper] = int(valor)
            elif isinstance(valor, str):
                try:
                    # Extrair número da string
                    import re
                    numeros = re.findall(r'\d+', valor)
                    if numeros:
                        processados[chave_upper] = int(numeros[0])
                except:
                    pass
        
        elif chave_upper == "TEMP":
            # Temperatura - garantir float
            if isinstance(valor, (int, float)):
                processados["Temp"] = float(valor)
            elif isinstance(valor, str):
                try:
                    # Extrair número decimal da string
                    import re
                    match = re.search(r'\d+[.,]\d+|\d+', valor)
                    if match:
                        temp_str = match.group().replace(',', '.')
                        processados["Temp"] = float(temp_str)
                except:
                    pass
    
    return processados


# Função de conveniência para manter compatibilidade
async def classify_semantic(texto: str, estado: GraphState) -> ClassificationResult:
    """Função principal para classificação semântica"""
    return await classificar_semanticamente(texto, estado)


def map_intent_to_flow(intent: IntentType) -> str:
    """Alias para mapeamento de intenção"""
    return mapear_intencao_para_fluxo(intent)
