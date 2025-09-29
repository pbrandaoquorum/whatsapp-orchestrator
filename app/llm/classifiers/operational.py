"""
Classificador LLM para notas operacionais
"""
from typing import Optional
import json
import structlog
from openai import OpenAI

logger = structlog.get_logger(__name__)

class OperationalNoteClassifier:
    """Classificador LLM para detectar notas operacionais que devem ser enviadas instantaneamente"""
    
    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        self.client = OpenAI(api_key=api_key)
        self.model = model
        logger.info("OperationalNoteClassifier inicializado", model=model)
    
    def is_operational_note(self, texto: str) -> tuple[bool, Optional[str]]:
        """
        Classifica se o texto é uma nota operacional que deve ser enviada instantaneamente
        
        Args:
            texto: Texto do usuário
            
        Returns:
            (is_operational: bool, operational_note: str|None)
        """
        try:
            prompt = self._create_classification_prompt(texto)
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": prompt}
                ],
                temperature=0,
                max_tokens=200
            )
            
            result_text = response.choices[0].message.content.strip()
            result = json.loads(result_text)
            
            is_operational = result.get("is_operational", False)
            note = result.get("operational_note")
            
            logger.info("Classificação operacional concluída", 
                       texto=texto[:50], 
                       is_operational=is_operational,
                       note=note[:100] if note else None)
            
            return is_operational, note
            
        except Exception as e:
            logger.error("Erro na classificação operacional", error=str(e), texto=texto)
            return False, None
    
    def _create_classification_prompt(self, texto: str) -> str:
        """Cria prompt para classificação operacional"""
        return f"""Analise se o texto do usuário contém uma NOTA OPERACIONAL que deve ser registrada instantaneamente no sistema.

TEXTO: "{texto}"

NOTAS OPERACIONAIS são informações sobre:
- Falta de materiais/medicamentos (ex: "acabou a fralda", "faltou soro", "precisa de gaze")
- Problemas estruturais (ex: "ar condicionado quebrou", "falta luz", "vazamento")
- Intercorrências operacionais (ex: "familiar chegou", "médico visitou", "enfermeira passou")
- Observações sobre equipamentos (ex: "bomba infusora com problema", "monitor desligado")
- Solicitações de materiais/serviços (ex: "precisa trocar lençol", "chamar técnico")

NÃO SÃO NOTAS OPERACIONAIS:
- Dados clínicos (sinais vitais, sintomas, medicações)
- Condições respiratórias (ar ambiente, oxigênio suplementar, ventilação mecânica)
- Confirmações de presença
- Perguntas sobre o sistema
- Conversas gerais

Se for uma nota operacional, extraia apenas a informação relevante, sem dados clínicos.

Responda APENAS JSON válido:
{{
  "is_operational": true/false,
  "operational_note": "texto da nota operacional" ou null
}}

EXEMPLOS:

Entrada: "acabou a fralda do paciente"
Saída: {{"is_operational": true, "operational_note": "acabou a fralda do paciente"}}

Entrada: "PA 120x80 FC 78 e acabou o soro"
Saída: {{"is_operational": true, "operational_note": "acabou o soro"}}

Entrada: "PA 120x80 FC 78 paciente estável"
Saída: {{"is_operational": false, "operational_note": null}}

Entrada: "como você pode me ajudar?"
Saída: {{"is_operational": false, "operational_note": null}}

Entrada: "ar ambiente"
Saída: {{"is_operational": false, "operational_note": null}}

Entrada: "oxigênio suplementar"
Saída: {{"is_operational": false, "operational_note": null}}

Entrada: "ventilação mecânica"
Saída: {{"is_operational": false, "operational_note": null}}

JSON:"""
