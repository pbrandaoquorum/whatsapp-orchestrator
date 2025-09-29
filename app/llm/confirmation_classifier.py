"""
Classificador de Confirmações via LLM
====================================

Substitui o uso de keywords por classificação LLM para:
- Confirmações (sim/não)
- Ações específicas de cada subgrafo

Sempre usa temperature=0 e saída JSON estrita.
"""

import os
import json
from typing import Dict, Any, Literal
from openai import OpenAI
import structlog

logger = structlog.get_logger()

class ConfirmationClassifier:
    """Classifica confirmações e ações usando LLM em vez de keywords"""
    
    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        self.client = OpenAI(api_key=api_key)
        self.model = model
    
    def classificar_confirmacao(self, texto_usuario: str) -> Literal["sim", "nao", "ambiguo"]:
        """
        Classifica se o texto é uma confirmação (sim), negação (não) ou ambíguo
        
        Returns:
            "sim": Confirmação positiva
            "nao": Negação/cancelamento  
            "ambiguo": Não é claro ou não é confirmação/negação
        """
        
        prompt = f"""Você é um classificador de confirmações em português brasileiro.

Analise o texto do usuário e classifique se é:
- "sim": Confirmação positiva (sim, confirmo, ok, tá bom, pode ser, vamos lá, etc.)
- "nao": Negação/cancelamento (não, nao, não posso, cancela, desisto, etc.)
- "ambiguo": Não é uma confirmação nem negação clara, ou é outra coisa

Texto do usuário: "{texto_usuario}"

Responda APENAS com JSON válido:
{{"classificacao": "sim|nao|ambiguo"}}"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            classificacao = result.get("classificacao", "ambiguo")
            
            if classificacao not in ["sim", "nao", "ambiguo"]:
                logger.warning("Classificação inválida retornada pelo LLM", 
                             classificacao=classificacao, texto=texto_usuario)
                return "ambiguo"
            
            logger.debug("Confirmação classificada via LLM",
                        texto=texto_usuario, classificacao=classificacao)
            
            return classificacao
            
        except Exception as e:
            logger.error("Erro ao classificar confirmação via LLM", 
                        error=str(e), texto=texto_usuario)
            return "ambiguo"
    
    def classificar_acao_escala(self, texto_usuario: str) -> Literal["confirmar", "cancelar", "consultar"]:
        """
        Classifica ação relacionada à escala/presença
        
        Returns:
            "confirmar": Quer confirmar presença
            "cancelar": Quer cancelar/não pode ir
            "consultar": Quer apenas consultar informações
        """
        
        prompt = f"""Você é um classificador de ações de escala/plantão em português brasileiro.

Analise o texto do usuário e classifique a intenção:
- "confirmar": Quer confirmar presença no plantão (confirmo presença, estou chegando, vou trabalhar, etc.)
- "cancelar": Quer cancelar ou não pode comparecer (não posso ir, cancela, estou doente, etc.)
- "consultar": Apenas quer informações sobre a escala (qual meu plantão, que horas, etc.)

Texto do usuário: "{texto_usuario}"

Responda APENAS com JSON válido:
{{"acao": "confirmar|cancelar|consultar"}}"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            acao = result.get("acao", "consultar")
            
            if acao not in ["confirmar", "cancelar", "consultar"]:
                logger.warning("Ação inválida retornada pelo LLM", 
                             acao=acao, texto=texto_usuario)
                return "consultar"
            
            logger.debug("Ação de escala classificada via LLM",
                        texto=texto_usuario, acao=acao)
            
            return acao
            
        except Exception as e:
            logger.error("Erro ao classificar ação de escala via LLM", 
                        error=str(e), texto=texto_usuario)
            return "consultar"
    
    def classificar_tipo_ajuda(self, texto_usuario: str) -> Literal["saudacao", "instrucoes", "comandos", "geral"]:
        """
        Classifica tipo de ajuda/auxiliar solicitado
        
        Returns:
            "saudacao": Saudações simples (oi, olá, bom dia)
            "instrucoes": Quer instruções específicas (como fazer X)
            "comandos": Quer lista de comandos disponíveis
            "geral": Ajuda geral ou não específica
        """
        
        prompt = f"""Você é um classificador de tipos de ajuda em português brasileiro.

Analise o texto do usuário e classifique o tipo de ajuda:
- "saudacao": Saudações simples (oi, olá, bom dia, boa tarde, etc.)
- "instrucoes": Quer instruções específicas (como fazer algo, o que significa X, etc.)
- "comandos": Quer lista de comandos ou funcionalidades (que comandos, o que posso fazer, etc.)
- "geral": Ajuda geral, dúvidas ou não específica

Texto do usuário: "{texto_usuario}"

Responda APENAS com JSON válido:
{{"tipo": "saudacao|instrucoes|comandos|geral"}}"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            tipo = result.get("tipo", "geral")
            
            if tipo not in ["saudacao", "instrucoes", "comandos", "geral"]:
                logger.warning("Tipo de ajuda inválido retornado pelo LLM", 
                             tipo=tipo, texto=texto_usuario)
                return "geral"
            
            logger.debug("Tipo de ajuda classificado via LLM",
                        texto=texto_usuario, tipo=tipo)
            
            return tipo
            
        except Exception as e:
            logger.error("Erro ao classificar tipo de ajuda via LLM", 
                        error=str(e), texto=texto_usuario)
            return "geral"
