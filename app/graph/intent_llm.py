"""
Classificador de intenção via LLM (fallback apenas, temperatura 0)
"""
import json
from typing import Dict, Any
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field

from app.graph.state import GraphState
from app.infra.logging import obter_logger

logger = obter_logger(__name__)


class IntentClassification(BaseModel):
    """Schema para classificação de intenção"""
    intent: str = Field(description="Intenção classificada: escala|sinais_vitais|notas|finalizar|auxiliar")
    confidence: float = Field(description="Confiança da classificação (0.0 a 1.0)")
    rationale: str = Field(description="Justificativa da classificação")


def criar_prompt_sistema() -> str:
    """Cria prompt do sistema para classificação de intenção"""
    return """
Você é um assistente especializado em classificar intenções de mensagens de cuidadores em plantões domiciliares.

INTENÇÕES POSSÍVEIS:
- escala: Confirmação/cancelamento de presença, chegada ao plantão
- sinais_vitais: Informar pressão arterial, frequência cardíaca, respiratória, saturação, temperatura
- notas: Relatos clínicos, observações sobre o paciente, sintomas
- finalizar: Encerrar plantão, enviar relatório final
- auxiliar: Dúvidas, orientações, mensagens não específicas

REGRAS IMPORTANTES:
1. Analise o CONTEXTO do estado atual (presença confirmada, sinais vitais realizados, etc.)
2. Priorize intenções mais específicas sobre genéricas
3. "auxiliar" é apenas para mensagens ambíguas ou pedidos de ajuda
4. Seja conservador: prefira "auxiliar" se não tiver certeza

Responda APENAS com JSON válido no formato especificado.
""".strip()


def criar_prompt_usuario(texto: str, estado: GraphState) -> str:
    """Cria prompt do usuário com contexto do estado"""
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
    
    # Contexto de finalização
    modo_finalizar = estado.metadados.get("modo_finalizar", False)
    if modo_finalizar:
        contexto_partes.append("- Modo FINALIZAÇÃO ativo")
    
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

Classifique a intenção considerando o contexto atual.
""".strip()


def classificar_intencao(texto: str, estado: GraphState) -> str:
    """
    Classifica intenção usando LLM como fallback
    Retorna apenas o nome da intenção
    """
    try:
        # Configurar LLM com temperatura 0 para determinismo
        llm = ChatOpenAI(
            temperature=0.0,
            model="gpt-3.5-turbo",
            max_tokens=200
        )
        
        # Configurar parser JSON
        parser = JsonOutputParser(pydantic_object=IntentClassification)
        
        # Criar mensagens
        system_msg = SystemMessage(content=criar_prompt_sistema())
        human_msg = HumanMessage(content=criar_prompt_usuario(texto, estado))
        
        # Executar classificação
        logger.info(
            "Executando classificação LLM",
            texto_usuario=texto[:100],
            contexto_turno=estado.core.cancelado,
            presenca_confirmada=estado.metadados.get("presenca_confirmada", False)
        )
        
        response = llm.invoke([system_msg, human_msg])
        resultado = parser.parse(response.content)
        
        # Validar resultado
        intencoes_validas = ["escala", "sinais_vitais", "notas", "finalizar", "auxiliar"]
        if resultado.intent not in intencoes_validas:
            logger.warning(
                "Intenção inválida retornada pelo LLM",
                intencao_retornada=resultado.intent,
                usando_fallback="auxiliar"
            )
            return "auxiliar"
        
        logger.info(
            "Classificação LLM concluída",
            intencao=resultado.intent,
            confianca=resultado.confidence,
            justificativa=resultado.rationale
        )
        
        return resultado.intent
        
    except Exception as e:
        logger.error(
            "Erro na classificação LLM",
            erro=str(e),
            usando_fallback="auxiliar"
        )
        # Em caso de erro, retornar intenção segura
        return "auxiliar"


def validar_intencao_com_contexto(intencao: str, estado: GraphState) -> str:
    """
    Valida intenção contra o contexto atual e aplica correções se necessário
    """
    # Se turno cancelado, apenas auxiliar é permitido
    if estado.core.cancelado or not estado.core.turno_permitido:
        if intencao not in ["auxiliar"]:
            logger.info(
                "Intenção bloqueada por turno cancelado",
                intencao_original=intencao,
                intencao_corrigida="auxiliar"
            )
            return "auxiliar"
    
    # Se presença não confirmada, bloquear clínica/notas/finalizar
    presenca_confirmada = estado.metadados.get("presenca_confirmada", False)
    if not presenca_confirmada and intencao in ["sinais_vitais", "notas", "finalizar"]:
        logger.info(
            "Intenção requer presença confirmada",
            intencao_original=intencao,
            intencao_corrigida="escala"
        )
        return "escala"
    
    # Se finalizar sem sinais vitais, exigir sinais vitais primeiro
    if intencao == "finalizar":
        sv_realizados = estado.metadados.get("sinais_vitais_realizados", False)
        if not sv_realizados:
            logger.info(
                "Finalização requer sinais vitais",
                intencao_original=intencao,
                intencao_corrigida="sinais_vitais"
            )
            return "sinais_vitais"
    
    return intencao


def classificar_intencao_com_validacao(texto: str, estado: GraphState) -> str:
    """
    Função principal que classifica intenção e valida com contexto
    """
    # Classificar intenção via LLM
    intencao_bruta = classificar_intencao(texto, estado)
    
    # Validar com contexto
    intencao_final = validar_intencao_com_contexto(intencao_bruta, estado)
    
    if intencao_bruta != intencao_final:
        logger.info(
            "Intenção ajustada pelo contexto",
            intencao_llm=intencao_bruta,
            intencao_final=intencao_final
        )
    
    return intencao_final


# Função de conveniência para manter compatibilidade
def classify_intent(text: str, state: GraphState) -> str:
    """Alias em inglês para compatibilidade com o router"""
    return classificar_intencao_com_validacao(text, state)
