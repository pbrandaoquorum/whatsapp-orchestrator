"""
Fiscal LLM - Geração de Respostas Dinâmicas
==========================================

O Fiscal é responsável por:
1. Ler o estado canônico do DynamoDB
2. Gerar respostas contextuais via LLM
3. Nunca usar respostas estáticas

Sempre usa temperature=0 para determinismo.
"""

import os
import json
from typing import Dict, Any
from openai import OpenAI
import structlog

logger = structlog.get_logger()

class FiscalLLM:
    """Gerador de respostas via LLM para o Fiscal"""
    
    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        self.client = OpenAI(api_key=api_key)
        self.model = model
    
    def gerar_resposta(self, estado_atual: Dict[str, Any], entrada_usuario: str, codigo_resultado: str = None) -> str:
        """
        Gera resposta contextual baseada no estado atual via LLM
        
        Args:
            estado_atual: Estado completo do DynamoDB
            entrada_usuario: Última mensagem do usuário
            codigo_resultado: Código de resultado do subgrafo executado (opcional)
            
        Returns:
            Resposta curta e contextual para o usuário
        """
        
        # Valida entrada
        if not isinstance(estado_atual, dict):
            logger.error("Estado atual não é dict", tipo=type(estado_atual))
            raise ValueError("Estado atual deve ser um dict")
        
        logger.debug("Gerando resposta via LLM", 
                    entrada=entrada_usuario[:30],
                    estado_keys=list(estado_atual.keys()) if estado_atual else [])
        
        # System prompt robusto com regras de negócio
        system_prompt = self._criar_system_prompt()
        
        # Contexto do estado atual
        contexto_estado = self._formatar_contexto_estado(estado_atual, codigo_resultado)
        
        # User prompt
        user_prompt = f"""ESTADO ATUAL DO SISTEMA:
{contexto_estado}

ÚLTIMA MENSAGEM DO USUÁRIO: "{entrada_usuario}"

Gere uma resposta curta (máximo 2-3 linhas) e contextual para o usuário baseada no estado atual."""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0,
                max_tokens=150
            )
            
            resposta = response.choices[0].message.content.strip()
            
            logger.debug("Resposta gerada pelo Fiscal LLM",
                        entrada=entrada_usuario[:50],
                        resposta=resposta[:50])
            
            return resposta
            
        except Exception as e:
            logger.error("Erro ao gerar resposta via LLM", error=str(e))
            return "Desculpe, houve um erro interno. Tente novamente."
    
    def _criar_system_prompt(self) -> str:
        """Cria system prompt robusto com regras de negócio"""
        
        return """Você é o assistente WhatsApp para cuidadores em plantões médicos.

REGRAS DE NEGÓCIO:
1. SEMPRE seja contextual - analise o estado atual antes de responder
2. Respostas CURTAS (máximo 2-3 linhas)
3. NUNCA use respostas genéricas ou estáticas
4. Priorize ações pendentes (confirmações, dados faltantes)
5. Use linguagem natural e amigável
6. Seja específico sobre o que foi salvo/processado

FLUXOS PRINCIPAIS:
- ESCALA: Confirmação de presença, cancelamentos, consultas
- CLÍNICO: Coleta de vitais (PA, FC, FR, Sat, Temp) + nota clínica
- FINALIZAR: Encerramento do plantão
- AUXILIAR: Ajuda e orientações

ESTADOS IMPORTANTES:
- tem_pendente: Há confirmação aguardando (prioridade máxima)
- fluxo_pendente: Qual fluxo está aguardando confirmação
- vitais: Quais sinais vitais foram coletados
- nota: Se há nota clínica
- faltantes: Quais dados ainda precisam ser coletados
- fluxos_executados: Histórico de ações

CONFIRMAÇÕES:
- Se tem_pendente=true, SEMPRE mencione o que está aguardando
- Seja específico sobre o que será confirmado
- Use linguagem clara: "Confirma salvar os vitais?" 

DADOS PARCIAIS:
- Se dados clínicos incompletos, mencione o que já foi salvo
- Seja específico sobre o que ainda falta
- SEMPRE mencione condição respiratória se não informada
- Exemplo: "Salvei PA e FC. Preciso de FR, Sat, Temp, condição respiratória e nota clínica."

DADOS COMPLETOS:
- Quando todos os dados clínicos estão coletados (vitais + condição respiratória + nota clínica)
- SEMPRE apresente um resumo completo e peça confirmação explícita
- Formato: "Coletei: [lista de vitais], condição respiratória [valor], nota clínica: [valor]. Confirma para salvar?"
- NUNCA pergunte se quer adicionar mais - apenas confirme o salvamento
- Exemplo: "Coletei: PA 120x80, FC 75, FR 18, Sat 97, Temp 36.5, condição respiratória: ar ambiente, nota: sem alterações. Confirma para salvar?"

DADOS SALVOS COM SUCESSO:
- Quando o código de resultado é "CLINICAL_DATA_SAVED"
- Significa que os dados foram confirmados e enviados para o sistema com sucesso
- Estado clínico foi limpo automaticamente após o envio
- Confirme o salvamento e se coloque à disposição
- Formato: "Dados clínicos salvos com sucesso! Se precisar de algo mais, estou à disposição."
- NUNCA peça novos dados ou mencione faltantes após código CLINICAL_DATA_SAVED

CÓDIGOS DE RESULTADO (prioridade máxima):
- "CLINICAL_DATA_SAVED": Dados salvos com sucesso → "Dados clínicos salvos com sucesso! Se precisar de algo mais, estou à disposição."
- "CLINICAL_DATA_CANCELLED": Usuário cancelou → Informe que cancelou e pergunte se quer tentar novamente
- "CLINICAL_DATA_READY_FOR_CONFIRMATION": Dados completos → Apresente resumo e peça confirmação
- "FINALIZATION_PARTIAL_DATA": Dados parciais de finalização → Informe o que foi coletado e peça tópicos faltantes
- "FINALIZATION_READY_FOR_CONFIRMATION": Dados completos → Apresente resumo de finalização e peça confirmação
- "FINALIZATION_COMPLETED": Finalização concluída → "Plantão finalizado com sucesso! Obrigado pelo seu trabalho."
- "FINALIZATION_CANCELLED": Finalização cancelada → "Finalização cancelada. Posso ajudar com mais alguma coisa?"

STATUS DO PLANTÃO:
- "confirmado": Plantão confirmado - permite updates de dados clínicos
- "aguardando resposta": Precisa confirmar presença primeiro
- "cancelado": Plantão cancelado - não permite updates

NUNCA:
- Use "Como posso ajudar?" genericamente
- Repita a mesma resposta para entradas diferentes
- Ignore o contexto atual
- Seja verboso ou repetitivo
- Permita updates quando plantão não confirmado"""

    def _formatar_contexto_estado(self, estado: Dict[str, Any], codigo_resultado: str = None) -> str:
        """Formata o estado atual para o LLM de forma estruturada"""
        
        # Valida estado
        if not estado:
            logger.warning("Estado vazio para formatação")
            return "ESTADO: Vazio"
        
        # Extrai informações principais com validação
        sessao = estado.get("sessao") or {}
        clinico = estado.get("clinico") or {}
        finalizacao = estado.get("finalizacao") or {}
        pendente = estado.get("pendente") or {}
        retomada = estado.get("retomada") or {}
        fluxos_executados = estado.get("fluxos_executados") or []
        
        logger.debug("Formatando contexto", 
                    tem_sessao=bool(sessao),
                    tem_clinico=bool(clinico),
                    tem_finalizacao=bool(finalizacao),
                    tem_pendente=bool(pendente))
        
        # Vitais coletados
        vitais = clinico.get("vitais", {})
        vitais_coletados = {k: v for k, v in vitais.items() if v is not None}
        vitais_faltantes = clinico.get("faltantes", [])
        
        contexto = f"""SESSÃO:
- Telefone: {sessao.get('telefone', 'N/A')}
- Plantão permitido: {sessao.get('turno_permitido', False)}
- Plantão iniciado: {sessao.get('turno_iniciado', False)}
- Status do plantão: {sessao.get('response', 'N/A')}

FLUXOS EXECUTADOS: {', '.join(fluxos_executados) if fluxos_executados else 'Nenhum'}

CONFIRMAÇÃO PENDENTE:
- Tem pendente: {bool(pendente)}
- Fluxo pendente: {pendente.get('fluxo', 'Nenhum')}

DADOS CLÍNICOS:
- Vitais coletados: {', '.join([f'{k}={v}' for k, v in vitais_coletados.items()]) if vitais_coletados else 'Nenhum'}
- Vitais faltantes: {', '.join(vitais_faltantes) if vitais_faltantes else 'Nenhum'}
- Condição respiratória: {clinico.get('supplementaryOxygen') or 'Não informada'}
- Nota clínica: {f'"{clinico.get("nota")}"' if clinico.get('nota') else 'Não informada'}
- Dados completos: {bool(vitais_coletados and clinico.get('supplementaryOxygen') and clinico.get('nota'))}
- RAG: Processado via webhook n8n

DADOS DE FINALIZAÇÃO:
- Notas existentes: {len(finalizacao.get('notas_existentes', []))}
- Tópicos preenchidos: {len([t for t in finalizacao.get('topicos', {}).values() if t is not None])}
- Tópicos faltantes: {', '.join(finalizacao.get('faltantes', [])) if finalizacao.get('faltantes') else 'Nenhum'}
- Finalização completa: {len(finalizacao.get('faltantes', [])) == 0}

RETOMADA:
- Tem retomada: {bool(retomada)}
- Fluxo retomada: {retomada.get('fluxo', 'Nenhum')}

RESULTADO SUBGRAFO:
- Código: {codigo_resultado or 'Nenhum'}"""

        return contexto
