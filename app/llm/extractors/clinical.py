"""
Extrator de vitais e notas clínicas via LLM
Combina LLM + validações determinísticas
Temperatura 0, saída JSON estrita, sem regex
"""
import json
from typing import Dict, Any, List, Tuple
from openai import OpenAI
import structlog

logger = structlog.get_logger(__name__)


# Faixas plausíveis para validação pós-LLM (baseadas no prompt robusto)
FAIXAS_VITAIS = {
    "FC": {"min": 40, "max": 190, "nome": "Frequência Cardíaca"},
    "FR": {"min": 8, "max": 50, "nome": "Frequência Respiratória"},
    "Sat": {"min": 70, "max": 100, "nome": "Saturação O2"},
    "Temp": {"min": 34.0, "max": 41.0, "nome": "Temperatura"}
}


class ClinicalExtractor:
    """Extrator de dados clínicos usando LLM"""
    
    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        self.client = OpenAI(api_key=api_key)
        self.model = model
        logger.info("ClinicalExtractor inicializado", model=model)
    
    def _get_extraction_prompt(self, texto_usuario: str) -> str:
        """Monta prompt para extração de dados clínicos"""
        return f"""Você é um extrator especializado em sinais vitais e dados clínicos. Extraia com precisão todos os dados do texto fornecido.

TEXTO: "{texto_usuario}"

INSTRUÇÕES GERAIS:
- Responda APENAS JSON válido conforme schema
- Não invente valores; em dúvida, use null e adicione warning
- Extraia NÚMEROS exatos do texto (ex: "temperatura está 35" → Temp: 35.0)
- Temperature = 0 (determinístico)

FORMATOS ACEITOS PARA SINAIS VITAIS:

1. FREQUÊNCIA RESPIRATÓRIA (FR):
   - Formatos: FR, fr, freq resp, TR, irpm, respiração, 🫁
   - Exemplos: "fr 18", "respiração 20", "18 irpm"
   - Inferência por valor: números entre 8-50 (quando ambíguo)

2. SATURAÇÃO DE O₂ (Sat):
   - Formatos: Sat, SpO2, satO2, saturação, S, %
   - Exemplos: "sat 97", "97%", "spo2 95", "saturação 98"
   - Inferência por valor: números entre 70-100 (quando ambíguo)

3. PRESSÃO ARTERIAL (PA):
   - Formatos: PA, pressão, PAS/PAD, sistólica/diastólica
   - Aceite: "120/80", "12x8", "12 por 8", "12 8", "13/9", "14 x 8"
   - SEMPRE normalize para formato "PASxPAD":
     * 12/8 → "120x80"
     * 13x9 → "130x90" 
     * 10 por 7 → "100x70"
     * 11.5/7.5 → "115x75"
     * 9.5 por 6.5 → "95x65"

4. FREQUÊNCIA CARDÍACA (FC):
   - Formatos: FC, fc, pulso, batimentos, bpm, 🫀
   - Exemplos: "fc 78", "78 bpm", "pulso 85", "batimentos 90"
   - Inferência por valor: números entre 40-190 (quando ambíguo)

5. TEMPERATURA (Temp):
   - Formatos: T, temp, temperatura, °C, TAX, TX, graus, está, 🌡️
   - Exemplos: "temp 36.8", "36,2°C", "temperatura está 35", "37 graus"
   - Inferência por valor: números decimais entre 34.0-41.0
   - Decimais sempre com ponto (37,2 → 37.2)

CONDIÇÃO RESPIRATÓRIA (supplementaryOxygen):
- Identifique APENAS se explicitamente mencionado
- Formatos aceitos:
  * "ar ambiente", "AA", "ambiente" → "Ar ambiente"
  * "ventilação mecânica", "VM", "ventilador", "intubado", "mecânica" → "Ventilação mecânica"
  * "oxigênio", "O2", "suplementar", "O2 suplementar", "cateter nasal", "máscara" → "Oxigênio suplementar"
- Se NÃO mencionado explicitamente → null (NUNCA assuma)

NOTA CLÍNICA (nota):
- QUALQUER texto descritivo sobre o paciente (estado, sintomas, observações)
- Inclua: "estável", "bem", "dormindo", "consciente", "orientado", "sem queixas", "febre", "dor", "alterações", etc.
- Se houver QUALQUER descrição do paciente, extraia como nota

REGRAS DE INFERÊNCIA POR VALOR (quando sem contexto):
- Se valor decimal 34.0-41.0 → Temperatura
- Se formato "X/Y" ou "XxY" → Pressão Arterial  
- Se número 70-100 → Saturação (se ainda não preenchida)
- Se número 40-190 → FC (se Sat já preenchida)
- Se número 8-50 → FR (se FC já preenchida)

SCHEMA:
{{
  "vitals": {{
    "PA": "string|null",
    "FC": "number|null", 
    "FR": "number|null",
    "Sat": "number|null",
    "Temp": "number|null"
  }},
  "supplementaryOxygen": "string|null",
  "nota": "string|null",
  "rawMentions": {{}},
  "warnings": ["string"]
}}

EXEMPLOS:

Entrada: "pa 120x80 fc 78 fr 18 sat 97 temp 36.8 paciente em ar ambiente com tosse seca"
Saída: {{"vitals":{{"PA":"120x80","FC":78,"FR":18,"Sat":97,"Temp":36.8}},"supplementaryOxygen":"Ar ambiente","nota":"paciente com tosse seca","rawMentions":{{"PA":"120x80","FC":"78","FR":"18","Sat":"97","Temp":"36.8"}},"warnings":[]}}

Entrada: "pressão 12/8, batimentos 85, respiração 21, saturação 95%, temperatura 37,2 graus"
Saída: {{"vitals":{{"PA":"120x80","FC":85,"FR":21,"Sat":95,"Temp":37.2}},"supplementaryOxygen":null,"nota":null,"rawMentions":{{"PA":"12/8","FC":"85","FR":"21","Sat":"95%","Temp":"37,2"}},"warnings":[]}}

Entrada: "13 por 9, fc 90, VM"
Saída: {{"vitals":{{"PA":"130x90","FC":90,"FR":null,"Sat":null,"Temp":null}},"supplementaryOxygen":"Ventilação mecânica","nota":null,"rawMentions":{{"PA":"13 por 9","FC":"fc 90","supplementaryOxygen":"VM"}},"warnings":[]}}

Entrada: "sat 97 fr 21 e temperatura está 35"
Saída: {{"vitals":{{"PA":null,"FC":null,"FR":21,"Sat":97,"Temp":35.0}},"supplementaryOxygen":null,"nota":null,"rawMentions":{{"FR":"fr 21","Sat":"sat 97","Temp":"temperatura está 35"}},"warnings":[]}}

Entrada: "paciente estável, sem alterações"
Saída: {{"vitals":{{"PA":null,"FC":null,"FR":null,"Sat":null,"Temp":null}},"supplementaryOxygen":null,"nota":"paciente estável, sem alterações","rawMentions":{{}},"warnings":[]}}

Entrada: "78 bpm, spo2 97%, paciente consciente em O2"
Saída: {{"vitals":{{"PA":null,"FC":78,"FR":null,"Sat":97,"Temp":null}},"supplementaryOxygen":"Oxigênio suplementar","nota":"paciente consciente","rawMentions":{{"FC":"78 bpm","Sat":"spo2 97%","supplementaryOxygen":"O2"}},"warnings":[]}}

Entrada: "9.5 por 6.5, temp 36,8, AA"
Saída: {{"vitals":{{"PA":"95x65","FC":null,"FR":null,"Sat":null,"Temp":36.8}},"supplementaryOxygen":"Ar ambiente","nota":null,"rawMentions":{{"PA":"9.5 por 6.5","Temp":"temp 36,8","supplementaryOxygen":"AA"}},"warnings":[]}}

JSON:"""
    
    def extrair_json(self, texto_usuario: str) -> Dict[str, Any]:
        """
        Extrai dados clínicos do texto usando LLM
        Retorna dict com vitals, nota, rawMentions, warnings
        """
        try:
            prompt = self._get_extraction_prompt(texto_usuario)
            
            logger.info("Extraindo dados clínicos", texto=texto_usuario[:100])
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "user", "content": prompt}
                ],
                temperature=0,
                max_tokens=500,
                response_format={"type": "json_object"}
            )
            
            # Parse da resposta
            content = response.choices[0].message.content.strip()
            result = json.loads(content)
            
            # Validação do schema básico
            if "vitals" not in result:
                result["vitals"] = {"PA": None, "FC": None, "FR": None, "Sat": None, "Temp": None}
            if "nota" not in result:
                result["nota"] = None
            if "rawMentions" not in result:
                result["rawMentions"] = {}
            if "warnings" not in result:
                result["warnings"] = []
            
            logger.info("Extração concluída",
                       texto=texto_usuario[:50],
                       vitais_encontrados=sum(1 for v in result["vitals"].values() if v is not None),
                       tem_nota=bool(result["nota"]),
                       warnings=len(result["warnings"]))
            
            return result
            
        except json.JSONDecodeError as e:
            logger.error("Erro ao fazer parse do JSON do LLM", 
                        error=str(e),
                        response_content=content if 'content' in locals() else "N/A")
            
            # Retry com instrução mais explícita
            try:
                logger.info("Tentando extração novamente com instrução explícita")
                
                retry_prompt = f"Responda apenas JSON válido para: {texto_usuario}\n\nJSON:"
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": retry_prompt}],
                    temperature=0,
                    max_tokens=300,
                    response_format={"type": "json_object"}
                )
                
                content = response.choices[0].message.content.strip()
                result = json.loads(content)
                
                # Garante schema mínimo
                return {
                    "vitals": result.get("vitals", {"PA": None, "FC": None, "FR": None, "Sat": None, "Temp": None}),
                    "nota": result.get("nota"),
                    "rawMentions": result.get("rawMentions", {}),
                    "warnings": result.get("warnings", ["retry_necessario"])
                }
                
            except Exception:
                logger.error("Retry também falhou, retornando estrutura vazia")
                return {
                    "vitals": {"PA": None, "FC": None, "FR": None, "Sat": None, "Temp": None},
                    "nota": None,
                    "rawMentions": {},
                    "warnings": ["falha_json_llm"]
                }
        
        except Exception as e:
            logger.error("Erro na extração clínica", 
                        texto=texto_usuario[:50],
                        error=str(e))
            return {
                "vitals": {"PA": None, "FC": None, "FR": None, "Sat": None, "Temp": None},
                "nota": None,
                "rawMentions": {},
                "warnings": ["erro_extracao"]
            }
    
    def _validar_pa(self, pa_str: str) -> Tuple[bool, str]:
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
            
            # Faixas plausíveis (baseadas no prompt robusto)
            if not (60 <= sistolica <= 220):
                return False, f"PA_sistolica_fora_faixa_{sistolica}"
            
            if not (40 <= diastolica <= 130):
                return False, f"PA_diastolica_fora_faixa_{diastolica}"
            
            if sistolica <= diastolica:
                return False, "PA_sistolica_menor_igual_diastolica"
            
            return True, ""
            
        except ValueError:
            return False, "PA_valores_nao_numericos"
    
    def extrair_clinico_completo(self, texto: str) -> Dict[str, Any]:
        """
        Extrai dados clínicos via LLM e aplica validações determinísticas
        
        Returns:
            dict com:
            - vitais: dict com PA, FC, FR, Sat, Temp (valores válidos ou None)
            - nota: string ou None
            - supplementaryOxygen: string ou None
            - faltantes: list de campos faltantes
            - warnings: list de warnings de validação
            - raw_llm_result: resultado original do LLM
        """
        logger.info("Iniciando extração clínica completa", texto=texto[:100])
        
        # 1) Chama LLM
        llm_result = self.extrair_json(texto)
        
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
            pa_valida, motivo = self._validar_pa(pa_raw)
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
        logger.info("Extração clínica completa concluída",
                   vitais_presentes=vitais_presentes,
                   faltantes=faltantes,
                   tem_nota=bool(nota),
                   tem_supplementary_oxygen=bool(supplementary_oxygen),
                   warnings_count=len(warnings))
        
        return {
            "vitais": vitais_validados,
            "nota": nota,
            "supplementaryOxygen": supplementary_oxygen,
            "faltantes": faltantes,
            "warnings": warnings,
            "raw_llm_result": llm_result
        }
