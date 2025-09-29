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
        """Cria prompt robusto para extração inteligente de tópicos de finalização"""
        
        notas_contexto = ""
        if notas_existentes:
            notas_contexto = f"""
NOTAS EXISTENTES DO PLANTÃO:
{chr(10).join([f"- {nota}" for nota in notas_existentes])}

"""
        
        return f"""Você é um extrator especializado em tópicos de finalização de plantão. Extraia informações do texto de forma inteligente e contextual.

{notas_contexto}TEXTO DO USUÁRIO: "{texto_usuario}"

INSTRUÇÕES GERAIS:
- Responda APENAS JSON válido conforme schema
- Seja inteligente: reconheça informações mesmo quando expressas de forma casual
- Extraia TUDO relevante, mesmo informações implícitas ou contextuais
- Use linguagem natural e preserve o contexto original
- Se não houver informação clara sobre um tópico, use null

TÓPICOS DE FINALIZAÇÃO (reconheça variações naturais):

1. ALIMENTAÇÃO E HIDRATAÇÃO:
   RECONHEÇA: refeições, comida, bebida, apetite, sede, líquidos, sonda, dieta, comer, beber
   FRASES TÍPICAS: "comeu bem", "não quis comer", "tomou água", "almoçou", "jantou", "café da manhã", "lanche", "suco", "leite", "recusou alimentação", "vomitou", "engasgou", "se alimentou", "bebeu"
   EXEMPLOS: "comeu bem no almoço" → "comeu bem no almoço"

2. EVACUAÇÕES (Fezes e Urina):
   RECONHEÇA: fezes, urina, xixi, cocô, evacuação, intestino, bexiga, fralda, vaso, banheiro, evacuar, urinar
   FRASES TÍPICAS: "fez cocô", "urinou", "molhou a fralda", "foi ao banheiro", "intestino preso", "diarreia", "constipação", "incontinência", "segurou xixi", "fezes", "evacuou"
   EXEMPLOS: "fezes estavam avermelhadas" → "fezes estavam avermelhadas"

3. SONO:
   RECONHEÇA: dormir, sono, descanso, cochilo, noite, despertar, insônia, acordar, descansar
   FRASES TÍPICAS: "dormiu bem", "não conseguiu dormir", "acordou várias vezes", "cochilou", "insônia", "sonolento", "descansou", "dormiu normal", "noite tranquila"
   EXEMPLOS: "dormiu bem" → "dormiu bem"

4. HUMOR:
   RECONHEÇA: humor, emoção, comportamento, agitação, calma, irritação, alegria, tristeza, ansiedade, estado emocional
   FRASES TÍPICAS: "estava irritado", "bem humorado", "agitado", "calmo", "ansioso", "triste", "alegre", "conversativo", "quieto", "agressivo", "ficou irritado"
   EXEMPLOS: "ficou irritado durante o dia" → "ficou irritado durante o dia"

5. MEDICAÇÕES:
   RECONHEÇA: remédio, medicamento, comprimido, injeção, soro, gotinha, pomada, administrar, tomar, dar remédio
   FRASES TÍPICAS: "tomou o remédio", "dei dipirona", "recusou medicação", "horário do remédio", "injeção", "não foi administrado", "medicação", "remédio"
   EXEMPLOS: "não foi administrado medicações" → "não foi administrado medicações"

6. ATIVIDADES (físicas e cognitivas):
   RECONHEÇA: exercício, fisioterapia, caminhada, jogo, atividade, movimento, mobilidade, brincadeira, esporte
   FRASES TÍPICAS: "fez fisioterapia", "caminhou", "jogou", "exercício", "movimentou", "atividade física", "brincou", "leu", "assistiu TV", "vôlei", "futebol"
   EXEMPLOS: "jogou vôlei" → "jogou vôlei"

7. INFORMAÇÕES CLÍNICAS ADICIONAIS:
   RECONHEÇA: pressão, temperatura, sintomas, dor, ferida, curativo, intercorrência, sinais vitais, estado geral, clínico
   FRASES TÍPICAS: "pressão estável", "sem febre", "dor no peito", "curativo limpo", "sem alterações", "intercorrência", "sintomas", "estável", "sem intercorrências"
   EXEMPLOS: "pressão estável durante todo o plantão" → "pressão estável durante todo o plantão"

8. INFORMAÇÕES ADMINISTRATIVAS:
   RECONHEÇA: visita, familiar, médico, enfermeiro, procedimento, troca de plantão, documento, administrativo, falta
   FRASES TÍPICAS: "familiar visitou", "médico passou", "troca de plantão", "procedimento realizado", "documentação", "familiar ligou", "falta de fralda", "visitou"
   EXEMPLOS: "troca de plantão realizada com João às 20h" → "troca de plantão realizada com João às 20h"

REGRAS DE INFERÊNCIA INTELIGENTE:
- "sem informações" ou "nada a relatar" para contexto específico → "Sem informações"
- Menções gerais como "tudo normal" → classifique como informações clínicas adicionais
- Informações misturadas → separe por tópico apropriado
- Negativas também são informações válidas ("não comeu", "não urinou")
- Frases compostas → extraia cada parte para o tópico correto
- Contexto implícito → use conhecimento sobre cuidados médicos

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

EXEMPLOS MELHORADOS:

Entrada: "Paciente comeu bem, tomou bastante água. Dormiu a noite toda."
Saída: {{"alimentacao_hidratacao": "comeu bem, tomou bastante água", "sono": "dormiu a noite toda", "evacuacoes": null, "humor": null, "medicacoes": null, "atividades": null, "informacoes_clinicas_adicionais": null, "informacoes_administrativas": null, "topicos_identificados": ["alimentacao_hidratacao", "sono"], "warnings": []}}

Entrada: "Dei dipirona para dor. Fez caminhada e estava alegre. Familiar visitou."
Saída: {{"medicacoes": "dipirona para dor", "atividades": "fez caminhada", "humor": "estava alegre", "informacoes_administrativas": "familiar visitou", "alimentacao_hidratacao": null, "evacuacoes": null, "sono": null, "informacoes_clinicas_adicionais": null, "topicos_identificados": ["medicacoes", "atividades", "humor", "informacoes_administrativas"], "warnings": []}}

Entrada: "Tudo normal, sem intercorrências. Pressão ok."
Saída: {{"informacoes_clinicas_adicionais": "tudo normal, sem intercorrências, pressão ok", "alimentacao_hidratacao": null, "evacuacoes": null, "sono": null, "humor": null, "medicacoes": null, "atividades": null, "informacoes_administrativas": null, "topicos_identificados": ["informacoes_clinicas_adicionais"], "warnings": []}}

Entrada: "fezes avermelhadas, dormiu normal, houve falta de fralda"
Saída: {{"evacuacoes": "fezes avermelhadas", "sono": "dormiu normal", "informacoes_administrativas": "houve falta de fralda", "alimentacao_hidratacao": null, "humor": null, "medicacoes": null, "atividades": null, "informacoes_clinicas_adicionais": null, "topicos_identificados": ["evacuacoes", "sono", "informacoes_administrativas"], "warnings": []}}

Entrada: "o paciente vomitou durante o almoço, ficou irritado, jogou vôlei, não foi administrado medicações"
Saída: {{"alimentacao_hidratacao": "vomitou durante o almoço", "humor": "ficou irritado", "atividades": "jogou vôlei", "medicacoes": "não foi administrado medicações", "evacuacoes": null, "sono": null, "informacoes_clinicas_adicionais": null, "informacoes_administrativas": null, "topicos_identificados": ["alimentacao_hidratacao", "humor", "atividades", "medicacoes"], "warnings": []}}

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
