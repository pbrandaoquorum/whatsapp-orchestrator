"""
Orquestrador de extração clínica
Combina LLM + validações determinísticas
"""
from typing import Dict, Any, List
import structlog

from app.llm.extractor import ClinicalExtractor

logger = structlog.get_logger(__name__)


# Faixas plausíveis para validação pós-LLM
FAIXAS_VITAIS = {
    "FC": {"min": 20, "max": 220, "nome": "Frequência Cardíaca"},
    "FR": {"min": 5, "max": 50, "nome": "Frequência Respiratória"},
    "Sat": {"min": 50, "max": 100, "nome": "Saturação O2"},
    "Temp": {"min": 30.0, "max": 43.0, "nome": "Temperatura"}
}


def validar_pa(pa_str: str) -> tuple[bool, str]:
    """
    Valida string de pressão arterial no formato SxD
    Retorna (válido, motivo_se_inválido)
    """
    if not pa_str or not isinstance(pa_str, str):
        return False, "PA_vazia"
    
    if 'x' not in pa_str:
        return False, "PA_formato_invalido"
    
    try:
        partes = pa_str.split('x')
        if len(partes) != 2:
            return False, "PA_formato_invalido"
        
        sistolica = int(partes[0])
        diastolica = int(partes[1])
        
        # Faixas plausíveis
        if not (70 <= sistolica <= 260):
            return False, f"PA_sistolica_fora_faixa_{sistolica}"
        
        if not (40 <= diastolica <= 160):
            return False, f"PA_diastolica_fora_faixa_{diastolica}"
        
        if sistolica <= diastolica:
            return False, "PA_sistolica_menor_igual_diastolica"
        
        return True, ""
        
    except ValueError:
        return False, "PA_valores_nao_numericos"


def extrair_clinico_via_llm(texto: str, extractor: ClinicalExtractor) -> Dict[str, Any]:
    """
    Extrai dados clínicos via LLM e aplica validações determinísticas
    
    Returns:
        dict com:
        - vitais: dict com PA, FC, FR, Sat, Temp (valores válidos ou None)
        - nota: string ou None
        - faltantes: list de campos faltantes
        - warnings: list de warnings de validação
        - raw_llm_result: resultado original do LLM
    """
    logger.info("Iniciando extração clínica via LLM", texto=texto[:100])
    
    # 1) Chama LLM
    llm_result = extractor.extrair_json(texto)
    
    # 2) Extrai dados do resultado do LLM
    vitais_llm = llm_result.get("vitals", {})
    nota = llm_result.get("nota")
    supplementary_oxygen = llm_result.get("supplementaryOxygen")
    warnings = list(llm_result.get("warnings", []))
    
    # 3) Valida e normaliza cada vital
    vitais_validados = {}
    
    # PA - validação especial
    pa_raw = vitais_llm.get("PA")
    if pa_raw:
        pa_valida, motivo = validar_pa(pa_raw)
        if pa_valida:
            vitais_validados["PA"] = pa_raw
        else:
            vitais_validados["PA"] = None
            warnings.append(motivo)
            logger.warning("PA inválida", pa_raw=pa_raw, motivo=motivo)
    else:
        vitais_validados["PA"] = None
    
    # FC, FR, Sat, Temp - validação numérica
    for campo in ["FC", "FR", "Sat", "Temp"]:
        valor_raw = vitais_llm.get(campo)
        
        if valor_raw is None:
            vitais_validados[campo] = None
            continue
        
        try:
            # Converte para número
            if isinstance(valor_raw, (int, float)):
                valor_num = float(valor_raw)
            else:
                valor_num = float(valor_raw)
            
            # Valida faixa
            faixa = FAIXAS_VITAIS[campo]
            if faixa["min"] <= valor_num <= faixa["max"]:
                # Valor válido
                if campo in ["FC", "FR", "Sat"]:
                    vitais_validados[campo] = int(valor_num)  # Inteiro para estes
                else:
                    vitais_validados[campo] = valor_num  # Float para temperatura
            else:
                # Fora da faixa
                vitais_validados[campo] = None
                warnings.append(f"{campo}_incoerente_{valor_num}")
                logger.warning("Vital fora da faixa",
                             campo=campo,
                             valor=valor_num,
                             faixa_min=faixa["min"],
                             faixa_max=faixa["max"])
                
        except (ValueError, TypeError):
            # Não é número válido
            vitais_validados[campo] = None
            warnings.append(f"{campo}_nao_numerico_{valor_raw}")
            logger.warning("Vital não numérico", campo=campo, valor_raw=valor_raw)
    
    # 4) Calcula faltantes
    campos_obrigatorios = ["PA", "FC", "FR", "Sat", "Temp"]
    faltantes = [
        campo for campo in campos_obrigatorios
        if vitais_validados.get(campo) is None
    ]
    
    # 5) Log do resultado
    vitais_presentes = [campo for campo, valor in vitais_validados.items() if valor is not None]
    logger.info("Extração clínica concluída",
               vitais_presentes=vitais_presentes,
               faltantes=faltantes,
               tem_nota=bool(nota),
               warnings_count=len(warnings))
    
    return {
        "vitais": vitais_validados,
        "nota": nota,
        "supplementaryOxygen": supplementary_oxygen,
        "faltantes": faltantes,
        "warnings": warnings,
        "raw_llm_result": llm_result
    }
