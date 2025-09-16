"""
Utilitários para processamento de sinais vitais
Agora usa apenas classificação semântica via LLM
"""
from typing import Dict, Any, List
from dataclasses import dataclass


@dataclass
class VitalsResult:
    """Resultado da extração de sinais vitais"""
    processados: Dict[str, Any]
    faltantes: List[str]


# Sinais vitais obrigatórios
SINAIS_VITAIS_OBRIGATORIOS = ["PA", "FC", "FR", "Sat", "Temp"]


async def extrair_sinais_vitais_semanticos(texto: str) -> VitalsResult:
    """
    Extrai sinais vitais usando classificação semântica via LLM
    """
    if not texto:
        return VitalsResult(processados={}, faltantes=SINAIS_VITAIS_OBRIGATORIOS.copy())
    
    try:
        from app.graph.semantic_classifier import classify_semantic
        from app.graph.state import GraphState, CoreState
        
        # Criar estado mínimo para classificação
        estado_temp = GraphState(
            core=CoreState(session_id="temp", numero_telefone="temp"),
            texto_usuario=texto
        )
        
        # Classificar semanticamente
        resultado = await classify_semantic(texto, estado_temp)
        
        if resultado.intent.value == "sinais_vitais" and resultado.vital_signs:
            processados = resultado.vital_signs
            faltantes = [sv for sv in SINAIS_VITAIS_OBRIGATORIOS if sv not in processados]
            return VitalsResult(processados=processados, faltantes=faltantes)
    
    except Exception:
        # Em caso de erro, retornar vazio
        pass
    
    return VitalsResult(processados={}, faltantes=SINAIS_VITAIS_OBRIGATORIOS.copy())


# Manter função legacy para compatibilidade (agora async)
async def extrair_sinais_vitais(texto: str) -> VitalsResult:
    """Função principal para extrair sinais vitais - agora via LLM semântico"""
    return await extrair_sinais_vitais_semanticos(texto)


def normalizar_sinais_vitais(dados: Dict[str, Any]) -> Dict[str, Any]:
    """Normaliza dados de sinais vitais para formato padrão"""
    normalizados = {}
    
    for chave, valor in dados.items():
        if chave == "PA" and isinstance(valor, str):
            normalizados[chave] = valor
        elif chave in ["FC", "FR", "Sat"] and isinstance(valor, (int, float)):
            normalizados[chave] = int(valor)
        elif chave == "Temp" and isinstance(valor, (int, float)):
            normalizados[chave] = float(valor)
        else:
            normalizados[chave] = valor
    
    return normalizados


def validar_sinais_vitais_completos(dados: Dict[str, Any]) -> bool:
    """Verifica se todos os sinais vitais obrigatórios estão presentes"""
    return all(sv in dados for sv in SINAIS_VITAIS_OBRIGATORIOS)


def gerar_resumo_sinais_vitais(dados: Dict[str, Any]) -> str:
    """Gera resumo textual dos sinais vitais para confirmação"""
    if not dados:
        return "Nenhum sinal vital informado"
    
    resumo_parts = []
    
    if "PA" in dados:
        resumo_parts.append(f"PA: {dados['PA']}")
    if "FC" in dados:
        resumo_parts.append(f"FC: {dados['FC']} bpm")
    if "FR" in dados:
        resumo_parts.append(f"FR: {dados['FR']} irpm")
    if "Sat" in dados:
        resumo_parts.append(f"Sat: {dados['Sat']}%")
    if "Temp" in dados:
        resumo_parts.append(f"Temp: {dados['Temp']}°C")
    
    return ", ".join(resumo_parts)
