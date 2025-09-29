"""
Extrator de vitais e notas clínicas via LLM
Temperatura 0, saída JSON estrita, sem regex
"""
import json
from typing import Dict, Any
from openai import OpenAI
import structlog

logger = structlog.get_logger(__name__)


class ClinicalExtractor:
    """Extrator de dados clínicos usando LLM"""
    
    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        self.client = OpenAI(api_key=api_key)
        self.model = model
        logger.info("ClinicalExtractor inicializado", model=model)
    
    def _get_extraction_prompt(self, texto_usuario: str) -> str:
        """Monta prompt para extração de dados clínicos"""
        return f"""Extraia sinais vitais, condição respiratória e nota clínica do texto do usuário.

TEXTO: "{texto_usuario}"

INSTRUÇÕES:
- Responda APENAS JSON válido conforme schema
- Não invente valores; em dúvida, use null e adicione warning
- Temperature = 0 (determinístico)

NORMALIZAÇÕES VITAIS:
- PA: aceite "120x80", "120/80", "12x8", "12/8". Se "12/8" normalize para "120x80"
- FC: aceite "fc", "freq card", "batimentos", "bpm" (ex: "fc 78", "78 bpm")
- FR: aceite "fr", "freq resp", "respiração", "irpm" (ex: "fr 18", "18 irpm")  
- Sat: aceite "sat", "spo2", "saturação", "%" (ex: "sat 97", "97%", "spo2 97")
- Temp: aceite "temp", "temperatura", "°C", "graus" (ex: "temp 36.8", "36,2°C")
- Decimais sempre com ponto (37,2 → 37.2)

CONDIÇÃO RESPIRATÓRIA:
- supplementaryOxygen: identifique "ar ambiente", "ventilação mecânica", "oxigênio suplementar", "O2", "cateter nasal", "máscara"
- Se mencionar O2, oxigênio, cateter → "Oxigênio suplementar"
- Se mencionar ventilador, intubado → "Ventilação mecânica"  
- Se mencionar ar ambiente ou nada → "Ar ambiente"

NOTA CLÍNICA:
- nota: QUALQUER texto descritivo sobre o paciente (estado, sintomas, observações)
- Inclua: "estável", "bem", "dormindo", "consciente", "orientado", "sem queixas", "febre", "dor", etc.
- Se houver QUALQUER descrição do paciente, extraia como nota

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

Entrada: "paciente estável, sem alterações"
Saída: {{"vitals":{{"PA":null,"FC":null,"FR":null,"Sat":null,"Temp":null}},"supplementaryOxygen":null,"nota":"paciente estável, sem alterações","rawMentions":{{}},"warnings":[]}}

Entrada: "78 bpm, spo2 97%, paciente consciente em O2"
Saída: {{"vitals":{{"PA":null,"FC":78,"FR":null,"Sat":97,"Temp":null}},"supplementaryOxygen":"Oxigênio suplementar","nota":"paciente consciente","rawMentions":{{"FC":"78 bpm","Sat":"spo2 97%"}},"warnings":[]}}

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
