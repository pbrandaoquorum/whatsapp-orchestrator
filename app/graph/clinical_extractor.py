"""
Extrator clínico determinístico para sinais vitais
Usa regex e heurísticas, NUNCA LLM
"""
import re
from typing import Dict, Any, List
from dataclasses import dataclass


@dataclass
class VitalsResult:
    """Resultado da extração de sinais vitais"""
    processados: Dict[str, Any]
    faltantes: List[str]


# Sinais vitais obrigatórios
SINAIS_VITAIS_OBRIGATORIOS = ["PA", "FC", "FR", "Sat", "Temp"]

# Padrões regex para extração
PADROES_PA = [
    r'(?:PA|pressão|pressao)\s*:?\s*(\d{2,3})\s*[x/]\s*(\d{2,3})',
    r'(\d{2,3})\s*[x/]\s*(\d{2,3})',  # formato direto 120x80
    r'(?:PA|pressão|pressao)\s*:?\s*(\d{2,3})',  # apenas sistólica
]

PADROES_FC = [
    r'(?:FC|frequencia cardiaca|freq cardiaca|batimentos)\s*:?\s*(\d{2,3})',
    r'(\d{2,3})\s*bpm',
]

PADROES_FR = [
    r'(?:FR|frequencia respiratoria|freq respiratoria|respiracao)\s*:?\s*(\d{1,2})',
    r'(\d{1,2})\s*irpm',
]

PADROES_SAT = [
    r'(?:Sat|saturacao|SpO2|oxigenacao)\s*:?\s*(\d{2,3})',
    r'(\d{2,3})\s*%',
]

PADROES_TEMP = [
    r'(?:Temp|temperatura|temp)\s*:?\s*(\d{2})[,.](\d{1,2})',
    r'(\d{2})[,.](\d{1,2})\s*°?C?',
]


def extrair_pressao_arterial(texto: str) -> Dict[str, Any]:
    """Extrai pressão arterial do texto"""
    texto_limpo = texto.lower().strip()
    
    for padrao in PADROES_PA:
        match = re.search(padrao, texto_limpo)
        if match:
            if len(match.groups()) == 2:
                sistolica, diastolica = match.groups()
                return {"PA": f"{sistolica}x{diastolica}"}
            else:
                sistolica = match.group(1)
                return {"PA": f"{sistolica}x--"}
    
    return {}


def extrair_frequencia_cardiaca(texto: str) -> Dict[str, Any]:
    """Extrai frequência cardíaca do texto"""
    texto_limpo = texto.lower().strip()
    
    for padrao in PADROES_FC:
        match = re.search(padrao, texto_limpo)
        if match:
            fc = int(match.group(1))
            if 40 <= fc <= 200:  # validação básica
                return {"FC": fc}
    
    return {}


def extrair_frequencia_respiratoria(texto: str) -> Dict[str, Any]:
    """Extrai frequência respiratória do texto"""
    texto_limpo = texto.lower().strip()
    
    for padrao in PADROES_FR:
        match = re.search(padrao, texto_limpo)
        if match:
            fr = int(match.group(1))
            if 8 <= fr <= 40:  # validação básica
                return {"FR": fr}
    
    return {}


def extrair_saturacao(texto: str) -> Dict[str, Any]:
    """Extrai saturação de oxigênio do texto"""
    texto_limpo = texto.lower().strip()
    
    for padrao in PADROES_SAT:
        match = re.search(padrao, texto_limpo)
        if match:
            sat = int(match.group(1))
            if 70 <= sat <= 100:  # validação básica
                return {"Sat": sat}
    
    return {}


def extrair_temperatura(texto: str) -> Dict[str, Any]:
    """Extrai temperatura do texto"""
    texto_limpo = texto.lower().strip()
    
    for padrao in PADROES_TEMP:
        match = re.search(padrao, texto_limpo)
        if match:
            if len(match.groups()) == 2:
                inteira, decimal = match.groups()
                temp = float(f"{inteira}.{decimal}")
            else:
                temp = float(match.group(1))
            
            if 30.0 <= temp <= 45.0:  # validação básica
                return {"Temp": temp}
    
    return {}


def extrair_sinais_vitais(texto: str) -> VitalsResult:
    """
    Função principal para extrair todos os sinais vitais do texto
    Retorna VitalsResult com processados e faltantes
    """
    if not texto:
        return VitalsResult(processados={}, faltantes=SINAIS_VITAIS_OBRIGATORIOS.copy())
    
    processados = {}
    
    # Extrair cada sinal vital
    processados.update(extrair_pressao_arterial(texto))
    processados.update(extrair_frequencia_cardiaca(texto))
    processados.update(extrair_frequencia_respiratoria(texto))
    processados.update(extrair_saturacao(texto))
    processados.update(extrair_temperatura(texto))
    
    # Calcular faltantes
    faltantes = [sv for sv in SINAIS_VITAIS_OBRIGATORIOS if sv not in processados]
    
    return VitalsResult(processados=processados, faltantes=faltantes)


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
