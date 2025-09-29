"""
Extrator de tópicos de finalização via LLM
Identifica informações sobre os 8 tópicos de finalização de plantão
"""
import json
from typing import Dict, Any, List
from openai import OpenAI
import structlog

logger = structlog.get_logger(__name__)


class FinalizacaoExtractor:
    """Extrator de tópicos de finalização usando LLM"""
    
    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        self.client = OpenAI(api_key=api_key)
        self.model = model
        logger.info("FinalizacaoExtractor inicializado", model=model)
    
    def _get_extraction_prompt(self, texto_usuario: str, notas_existentes: List[str] = None) -> str:
        """Monta prompt para extração de tópicos de finalização"""
        
        notas_contexto = ""
        if notas_existentes:
            notas_contexto = f"""
NOTAS EXISTENTES DO PLANTÃO:
{chr(10).join([f"- {nota}" for nota in notas_existentes])}

"""
        
        return f"""Você é um extrator especializado em relatórios de finalização de plantão. Extraia informações sobre os tópicos de finalização do texto fornecido.

{notas_contexto}TEXTO DO USUÁRIO: "{texto_usuario}"

TÓPICOS DE FINALIZAÇÃO:

1. ALIMENTAÇÃO E HIDRATAÇÃO:
   - Aceitação alimentar, quantidade ingerida, dificuldades para comer
   - Hidratação, ingestão de líquidos
   - Uso de sonda, dietas especiais

2. EVACUAÇÕES (Fezes e Urina):
   - Frequência e características das evacuações
   - Uso de fraldas, incontinência
   - Dificuldades urinárias ou intestinais

3. SONO:
   - Qualidade do sono, duração
   - Despertares noturnos, inquietação
   - Medicações para dormir

4. HUMOR:
   - Estado emocional, humor geral
   - Agitação, ansiedade, depressão
   - Interação social, comunicação

5. MEDICAÇÕES:
   - Medicamentos administrados
   - Horários, dosagens
   - Reações adversas, recusas

6. ATIVIDADES (físicas e cognitivas):
   - Exercícios realizados
   - Atividades cognitivas, jogos
   - Mobilidade, fisioterapia

7. INFORMAÇÕES CLÍNICAS ADICIONAIS:
   - Sinais vitais especiais
   - Sintomas observados
   - Intercorrências clínicas

8. INFORMAÇÕES ADMINISTRATIVAS:
   - Visitas médicas, familiares
   - Procedimentos administrativos
   - Observações gerais do plantão

INSTRUÇÕES:
- Extraia APENAS informações explicitamente mencionadas
- Se não houver informação sobre um tópico, use null
- Seja específico e detalhado nas extrações
- Use as notas existentes como contexto adicional

SCHEMA:
{{
  "alimentacao_hidratacao": "string|null",
  "evacuacoes": "string|null",
  "sono": "string|null",
  "humor": "string|null",
  "medicacoes": "string|null",
  "atividades": "string|null",
  "informacoes_clinicas_adicionais": "string|null",
  "informacoes_administrativas": "string|null",
  "topicos_identificados": ["string"],
  "warnings": ["string"]
}}

EXEMPLOS:

Entrada: "Paciente se alimentou bem no almoço, tomou 500ml de água. Dormiu 6 horas seguidas."
Saída: {{"alimentacao_hidratacao": "se alimentou bem no almoço, tomou 500ml de água", "sono": "dormiu 6 horas seguidas", "evacuacoes": null, "humor": null, "medicacoes": null, "atividades": null, "informacoes_clinicas_adicionais": null, "informacoes_administrativas": null, "topicos_identificados": ["alimentacao_hidratacao", "sono"], "warnings": []}}

Entrada: "Administrei dipirona às 14h para dor. Paciente fez fisioterapia e estava bem humorado."
Saída: {{"medicacoes": "administrei dipirona às 14h para dor", "atividades": "paciente fez fisioterapia", "humor": "estava bem humorado", "alimentacao_hidratacao": null, "evacuacoes": null, "sono": null, "informacoes_clinicas_adicionais": null, "informacoes_administrativas": null, "topicos_identificados": ["medicacoes", "atividades", "humor"], "warnings": []}}

JSON:"""
    
    def extrair_topicos(self, texto_usuario: str, notas_existentes: List[str] = None) -> Dict[str, Any]:
        """
        Extrai tópicos de finalização do texto usando LLM
        
        Args:
            texto_usuario: Texto fornecido pelo usuário
            notas_existentes: Notas já existentes do plantão (opcional)
            
        Returns:
            dict com tópicos extraídos e metadados
        """
        try:
            prompt = self._get_extraction_prompt(texto_usuario, notas_existentes)
            
            logger.info("Extraindo tópicos de finalização", 
                       texto=texto_usuario[:100],
                       tem_notas_existentes=bool(notas_existentes))
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "user", "content": prompt}
                ],
                temperature=0,
                max_tokens=800,
                response_format={"type": "json_object"}
            )
            
            # Parse da resposta
            content = response.choices[0].message.content.strip()
            result = json.loads(content)
            
            # Validação do schema básico
            topicos_obrigatorios = [
                "alimentacao_hidratacao", "evacuacoes", "sono", "humor",
                "medicacoes", "atividades", "informacoes_clinicas_adicionais",
                "informacoes_administrativas"
            ]
            
            for topico in topicos_obrigatorios:
                if topico not in result:
                    result[topico] = None
            
            if "topicos_identificados" not in result:
                result["topicos_identificados"] = []
            if "warnings" not in result:
                result["warnings"] = []
            
            topicos_encontrados = len([t for t in topicos_obrigatorios if result[t] is not None])
            
            logger.info("Extração de tópicos concluída",
                       texto=texto_usuario[:50],
                       topicos_encontrados=topicos_encontrados,
                       topicos_identificados=result["topicos_identificados"],
                       warnings=len(result["warnings"]))
            
            return result
            
        except json.JSONDecodeError as e:
            logger.error("Erro ao fazer parse do JSON do LLM", 
                        error=str(e),
                        response_content=content if 'content' in locals() else "N/A")
            
            # Retry com instrução mais explícita
            try:
                logger.info("Tentando extração novamente com instrução explícita")
                
                retry_prompt = f"Responda apenas JSON válido para extração de tópicos de finalização: {texto_usuario}\n\nJSON:"
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": retry_prompt}],
                    temperature=0,
                    max_tokens=500,
                    response_format={"type": "json_object"}
                )
                
                content = response.choices[0].message.content.strip()
                result = json.loads(content)
                
                # Garante schema mínimo
                topicos_base = {
                    "alimentacao_hidratacao": None,
                    "evacuacoes": None,
                    "sono": None,
                    "humor": None,
                    "medicacoes": None,
                    "atividades": None,
                    "informacoes_clinicas_adicionais": None,
                    "informacoes_administrativas": None,
                    "topicos_identificados": [],
                    "warnings": ["retry_necessario"]
                }
                
                # Merge com resultado do retry
                for key, value in result.items():
                    if key in topicos_base and value is not None:
                        topicos_base[key] = value
                
                return topicos_base
                
            except Exception:
                logger.error("Retry também falhou, retornando estrutura vazia")
                return {
                    "alimentacao_hidratacao": None,
                    "evacuacoes": None,
                    "sono": None,
                    "humor": None,
                    "medicacoes": None,
                    "atividades": None,
                    "informacoes_clinicas_adicionais": None,
                    "informacoes_administrativas": None,
                    "topicos_identificados": [],
                    "warnings": ["falha_json_llm"]
                }
        
        except Exception as e:
            logger.error("Erro na extração de tópicos de finalização", 
                        texto=texto_usuario[:50],
                        error=str(e))
            return {
                "alimentacao_hidratacao": None,
                "evacuacoes": None,
                "sono": None,
                "humor": None,
                "medicacoes": None,
                "atividades": None,
                "informacoes_clinicas_adicionais": None,
                "informacoes_administrativas": None,
                "topicos_identificados": [],
                "warnings": ["erro_extracao"]
            }
    
    def analisar_completude(self, topicos: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analisa quais tópicos estão completos e quais faltam
        
        Args:
            topicos: Dicionário com os tópicos atuais
            
        Returns:
            dict com análise de completude
        """
        topicos_obrigatorios = [
            "alimentacao_hidratacao", "evacuacoes", "sono", "humor",
            "medicacoes", "atividades", "informacoes_clinicas_adicionais",
            "informacoes_administrativas"
        ]
        
        preenchidos = []
        faltantes = []
        
        for topico in topicos_obrigatorios:
            if topicos.get(topico):
                preenchidos.append(topico)
            else:
                faltantes.append(topico)
        
        return {
            "preenchidos": preenchidos,
            "faltantes": faltantes,
            "completo": len(faltantes) == 0,
            "progresso": f"{len(preenchidos)}/{len(topicos_obrigatorios)}"
        }
