"""
Classificador de intenção usando LLM
Temperatura 0, saída JSON estrita
"""
import json
from typing import Dict, Any
from openai import OpenAI
import structlog

logger = structlog.get_logger(__name__)


class IntentClassifier:
    """Classificador de intenção com LLM leve"""
    
    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        self.client = OpenAI(api_key=api_key)
        self.model = model
        logger.info("IntentClassifier inicializado", model=model)
    
    def _get_classification_prompt(self, texto_usuario: str) -> str:
        """Monta prompt para classificação de intenção"""
        return f"""Classifique a intenção do usuário no contexto de um cuidador de saúde domiciliar.

TEXTO DO USUÁRIO: "{texto_usuario}"

INTENÇÕES POSSÍVEIS:
- escala: Confirmar presença, cancelar plantão, questões sobre horário/escala
- clinico: Enviar sinais vitais (PA, FC, FR, Saturação, Temperatura), notas clínicas, condições respiratórias (ar ambiente, oxigênio, ventilação)
- operacional: Notas administrativas, observações gerais sem dados clínicos
- finalizar: Finalizar plantão, encerrar atendimento
- auxiliar: Dúvidas, ajuda, saudações, outros assuntos

INSTRUÇÕES:
- Responda APENAS um JSON válido
- Use temperatura 0 (determinístico)
- Formato: {{"intencao": "escala|clinico|operacional|finalizar|auxiliar"}}

EXEMPLOS:
Entrada: "Confirmando presença"
Saída: {{"intencao": "escala"}}

Entrada: "PA 120x80 FC 75"
Saída: {{"intencao": "clinico"}}

Entrada: "ar ambiente"
Saída: {{"intencao": "clinico"}}

Entrada: "oxigênio suplementar"
Saída: {{"intencao": "clinico"}}

Entrada: "ventilação mecânica"
Saída: {{"intencao": "clinico"}}

Entrada: "paciente estável, sem queixas"
Saída: {{"intencao": "clinico"}}

Entrada: "Paciente dormindo bem"
Saída: {{"intencao": "operacional"}}

Entrada: "Quero finalizar o plantão"
Saída: {{"intencao": "finalizar"}}

Entrada: "Olá, como funciona?"
Saída: {{"intencao": "auxiliar"}}

JSON:"""
    
    def classificar_intencao(self, texto_usuario: str) -> str:
        """
        Classifica intenção do usuário
        Retorna uma das opções: escala, clinico, operacional, finalizar, auxiliar
        """
        try:
            prompt = self._get_classification_prompt(texto_usuario)
            
            logger.info("Classificando intenção", texto=texto_usuario[:100])
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "user", "content": prompt}
                ],
                temperature=0,
                max_tokens=50,
                response_format={"type": "json_object"}
            )
            
            # Parse da resposta
            content = response.choices[0].message.content.strip()
            result = json.loads(content)
            
            intencao = result.get("intencao", "auxiliar")
            
            # Validação
            intencoes_validas = ["escala", "clinico", "operacional", "finalizar", "auxiliar"]
            if intencao not in intencoes_validas:
                logger.warning("Intenção inválida retornada pelo LLM", 
                             intencao=intencao, 
                             usando_fallback="auxiliar")
                intencao = "auxiliar"
            
            logger.info("Intenção classificada", 
                       texto=texto_usuario[:50],
                       intencao=intencao)
            
            return intencao
            
        except json.JSONDecodeError as e:
            logger.error("Erro ao fazer parse do JSON do LLM", 
                        error=str(e),
                        response_content=content if 'content' in locals() else "N/A")
            return "auxiliar"
        
        except Exception as e:
            logger.error("Erro na classificação de intenção", 
                        texto=texto_usuario[:50],
                        error=str(e))
            return "auxiliar"
