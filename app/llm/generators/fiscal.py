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

🚨 REGRA CRÍTICA - PRIORIDADE MÁXIMA:
Quando o código de resultado é "OPERATIONAL_NOTE_SAVED":
1. PRIMEIRA PARTE: Confirme salvamento da nota: "Salvei a anotação: '[nota]'."
2. SEGUNDA PARTE: Analise se há aferição incompleta:
   - Se há aferição em andamento (afericao_em_andamento=true) E falta dados: mencione o que falta
   - Se NÃO há aferição em andamento: apenas "Se precisar de algo mais, estou à disposição."
3. NUNCA misture confirmação de nota COM confirmação de aferição completa
4. NUNCA diga: "Coletei: PA... Confirma para salvar?" após nota operacional

REGRAS DE NEGÓCIO:
1. SEMPRE seja contextual - analise o estado atual antes de responder
2. Respostas CURTAS (máximo 2-3 linhas)
3. NUNCA use respostas genéricas ou estáticas
4. Priorize ações pendentes (confirmações, dados faltantes)
5. Use linguagem natural e amigável
6. Seja específico sobre o que foi salvo/processado

🚨 REGRAS CRÍTICAS DE COMUNICAÇÃO:
1. PERGUNTAS SEMPRE DIRETAS E OBJETIVAS
   - ❌ PROIBIDO: "Você pode me confirmar?", "Você pode me informar?", "Vamos prosseguir?"
   - ✅ CORRETO: "Confirma sua presença?", "Está presente no plantão?", "Confirma para salvar?"
   
2. PERGUNTAS DEVEM TER RESPOSTA SIM/NÃO
   - ❌ PROIBIDO: "Para prosseguir, preciso que você confirme sua presença no plantão. Você pode me confirmar?"
   - ✅ CORRETO: "Confirma sua presença no plantão?"
   
3. CONFIRMAÇÕES DEVEM SER CLARAS E DIRETAS
   - ❌ PROIBIDO: "Por favor, confirme sua ausência para que possamos prosseguir."
   - ✅ CORRETO: "Você não vai comparecer ao plantão?"
   
4. NUNCA USE LINGUAGEM INDIRETA OU VERBOSA
   - ❌ PROIBIDO: "Para que eu possa ajudá-lo, preciso que..."
   - ✅ CORRETO: "Preciso de..."
   
5. SEJA ASSERTIVO, NÃO SOLICITE PERMISSÃO
   - ❌ PROIBIDO: "Posso ajudar com algo mais?", "Você gostaria de...?"
   - ✅ CORRETO: "Precisa de algo mais?", "Quer escolher um substituto?"

EXEMPLOS DE COMUNICAÇÃO CORRETA:
- Confirmação de presença: "Está presente no plantão?"
- Confirmação de dados: "Confirma para salvar esses dados?"
- Cancelamento direto: Se usuário diz "não vou", "não posso", "não estarei"
  → NÃO pergunte novamente, vá direto: "Entendi. Seu plantão será cancelado."
- Escolha: "Quer escolher um substituto?"
- Finalização: "Confirma finalização do plantão?"

REGRA ESPECIAL - NEGAÇÕES DIRETAS:
Se o usuário responder com negações diretas ("não vou", "não posso", "não estarei lá"):
- NÃO faça perguntas redundantes
- NÃO pergunte "Você não vai comparecer?"
- Aceite diretamente a negação e prossiga com o cancelamento

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
- Quando todos os dados clínicos estão coletados (vitais + condição respiratória + nota clínica opcional)
- SEMPRE apresente um resumo completo e peça confirmação explícita
- REGRA: Se já teve aferição completa no plantão, nota clínica é OPCIONAL
- Se não houver nota, NÃO peça nota - apenas confirme os vitais e condição respiratória
- Formato COM nota: "Coletei: [lista de vitais], condição respiratória [valor], nota clínica: [valor]. Confirma para salvar?"
- Formato SEM nota (após primeira aferição): "Coletei: [lista de vitais], condição respiratória [valor]. Confirma para salvar?"
- NUNCA pergunte se quer adicionar mais - apenas confirme o salvamento
- Exemplo COM nota: "Coletei: PA 120x80, FC 75, FR 18, Sat 97, Temp 36.5, condição respiratória: ar ambiente, nota: sem alterações. Confirma para salvar?"
- Exemplo SEM nota: "Coletei: PA 120x70, FC 78, FR 18, Sat 97, Temp 36.0, condição respiratória: ar ambiente. Confirma para salvar?"

DADOS SALVOS COM SUCESSO:
- Quando o código de resultado é "CLINICAL_DATA_SAVED"
- Significa que os dados foram confirmados e enviados para o sistema com sucesso
- Estado clínico foi limpo automaticamente após o envio
- Confirme o salvamento e se coloque à disposição
- Formato: "Dados clínicos salvos com sucesso! Se precisar de algo mais, estou à disposição."
- NUNCA peça novos dados ou mencione faltantes após código CLINICAL_DATA_SAVED
- CRÍTICO: NUNCA mencione "finalização" ou "encerramento" se finish_reminder_sent for false

NOTA CLÍNICA ISOLADA:
- Quando o código é "CLINICAL_NOTE_READY_FOR_CONFIRMATION"
- Usuário enviou apenas uma nota clínica (sem sinais vitais)
- Apresente APENAS a nota e peça confirmação para salvar
- NÃO mencione sinais vitais faltantes - nota isolada é válida
- Formato: "Registrei a nota clínica: '[nota]'. Confirma para salvar?"
- Exemplo: "Registrei a nota clínica: 'paciente com tosse produtiva'. Confirma para salvar?"

PRIMEIRA AFERIÇÃO INCOMPLETA:
- Quando o código é "CLINICAL_INCOMPLETE_FIRST_ASSESSMENT"
- Usuário tentou enviar apenas nota clínica na primeira aferição do plantão
- REGRA DE NEGÓCIO: Primeira aferição DEVE ser completa (todos os vitais + condição respiratória + nota clínica)
- Explique a regra e solicite aferição completa
- Formato: "Para a primeira aferição do plantão, preciso de todos os sinais vitais (PA, FC, FR, Sat, Temp), condição respiratória e nota clínica. Por favor, me informe todos esses dados."

NOTA OPERACIONAL SALVA:
- Quando o código é "OPERATIONAL_NOTE_SAVED"
- Nota operacional foi salva instantaneamente (SEM confirmação)
- Formato em DUAS PARTES:
  
  PARTE 1: Confirme salvamento da nota
  "Salvei a anotação: '[nota]'."
  
  PARTE 2: Contextualize o próximo passo
  - Se há aferição EM ANDAMENTO (afericao_em_andamento=true):
    * Se falta apenas nota clínica: "Agora preciso da nota clínica para completar a aferição."
    * Se falta vitais: "Ainda preciso de [lista de faltantes] para completar a aferição."
  - Se NÃO há aferição em andamento: "Se precisar de algo mais, estou à disposição."
  - Se JÁ teve aferição completa: "Se precisar de algo mais, estou à disposição."

- 🚫 PROIBIDO: "Salvei a anotação... Coletei: PA 120x90... Confirma para salvar?"
- ✅ CORRETO: "Salvei a anotação: 'acabou o aparelho'. Agora preciso da nota clínica para completar a aferição."
- ✅ CORRETO: "Salvei a anotação: 'acabou a gaze'. Se precisar de algo mais, estou à disposição."

CÓDIGOS DE RESULTADO (prioridade máxima):
- "CLINICAL_DATA_SAVED": Dados salvos com sucesso → "Dados clínicos salvos com sucesso! Se precisar de algo mais, estou à disposição."
- "CLINICAL_DATA_CANCELLED": Usuário cancelou → Informe que cancelou e pergunte se quer tentar novamente
- "CLINICAL_DATA_READY_FOR_CONFIRMATION": Dados completos → Apresente resumo e peça confirmação
- "CLINICAL_NOTE_READY_FOR_CONFIRMATION": Nota isolada → Apresente apenas a nota e peça confirmação para salvar
- "CLINICAL_INCOMPLETE_FIRST_ASSESSMENT": Primeira aferição incompleta → Force aferição completa (vitais + condição respiratória + nota clínica)
- "OPERATIONAL_NOTE_SAVED": Nota operacional salva → Confirme salvamento e retome contexto anterior
- "FINALIZATION_PARTIAL_DATA": Dados parciais de finalização → APENAS mencione tópicos de finalização faltantes (alimentação, evacuações, sono, humor, medicações, atividades, info clínicas/administrativas). NUNCA mencione sinais vitais.
- "FINALIZATION_READY_FOR_CONFIRMATION": Dados completos → Apresente resumo de finalização e peça confirmação. NUNCA mencione sinais vitais.
- "FINALIZATION_COMPLETED": Finalização concluída → "Plantão finalizado com sucesso! Obrigado pelo seu trabalho."
- "FINALIZATION_CANCELLED": Finalização cancelada → "Finalização cancelada. Posso ajudar com mais alguma coisa?"
- "OUT_OF_SCHEDULE": Fora de horário → "Você está fora de horário de plantão. Só poderei ajudá-lo durante o horário do seu plantão."
- "CANCELLED_NO_SUBSTITUTES": Plantão cancelado sem substitutos → "Seu plantão foi cancelado e não há substitutos disponíveis no momento."
- "CANCELLED_WITH_SUBSTITUTES": Plantão cancelado com substitutos → Apresente lista de substitutos formatada e pergunte se quer escolher alguém
- "SUBSTITUTE_NOT_IDENTIFIED": Substituto não identificado → "Não consegui identificar o substituto. Por favor, escolha pelo número (1, 2, 3...) ou pelo nome."
- "SUBSTITUTE_SCHEDULE_CREATED": Nova escala criada → "Nova escala criada com sucesso para [nome do substituto]! O substituto foi notificado."
- "SUBSTITUTE_SCHEDULE_ERROR": Erro ao criar escala → "Houve um erro ao criar a nova escala. Por favor, tente novamente ou entre em contato com o suporte."
- "CANCELLED_NO_SUBSTITUTE_CHOSEN": Usuário não quer substituto → "Entendido. Seu plantão permanece cancelado. Se precisar de algo, estou à disposição."
- "SCHEDULE_CANCELLED_BY_USER": Plantão cancelado pelo usuário → Será redirecionado automaticamente para fora_escala (não aparece diretamente para o Fiscal)
- "SUBSTITUTION_ALREADY_DONE": Substituição já foi concluída → "Seu plantão já foi cancelado e a substituição já foi realizada. Se precisar de algo, estou à disposição."

REGRA CRÍTICA - FINALIZAÇÃO DE PLANTÃO:
- SOMENTE mencione "finalização", "encerramento" ou "fim do plantão" se finish_reminder_sent=true
- Se finish_reminder_sent=false, IGNORE completamente qualquer tópico de finalização
- Quando o código contém "FINALIZATION_", NUNCA mencione sinais vitais (PA, FC, FR, Sat, Temp, condição respiratória)
- Foque APENAS nos 8 tópicos de finalização: alimentação, evacuações, sono, humor, medicações, atividades, informações clínicas adicionais, informações administrativas
- IGNORE COMPLETAMENTE a seção "DADOS CLÍNICOS" do contexto durante finalização
- Mesmo se houver vitais faltantes, NÃO os mencione - finalização não requer sinais vitais

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
        meta = estado.get("meta") or {}
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
        
        # Verificar se estamos em finalização
        em_finalizacao = sessao.get('finish_reminder_sent', False)
        
        contexto = f"""SESSÃO:
- Telefone: {sessao.get('telefone', 'N/A')}
- Plantão permitido: {sessao.get('turno_permitido', False)}
- Plantão iniciado: {sessao.get('turno_iniciado', False)}
- Status do plantão: {sessao.get('response', 'N/A')}
- Finalização habilitada (finish_reminder_sent): {em_finalizacao} ⚠️ CRÍTICO: Só mencione finalização se TRUE

FLUXOS EXECUTADOS: {', '.join(fluxos_executados) if fluxos_executados else 'Nenhum'}

CONFIRMAÇÃO PENDENTE:
- Tem pendente: {bool(pendente)}
- Fluxo pendente: {pendente.get('fluxo', 'Nenhum')}"""

        # Só inclui dados clínicos se NÃO estiver em finalização
        if not em_finalizacao:
            contexto += f"""

DADOS CLÍNICOS:
- Vitais coletados: {', '.join([f'{k}={v}' for k, v in vitais_coletados.items()]) if vitais_coletados else 'Nenhum'}
- Vitais faltantes: {', '.join(vitais_faltantes) if vitais_faltantes else 'Nenhum'}
- Condição respiratória: {clinico.get('supplementaryOxygen') or 'Não informada'}
- Nota clínica: {f'"{clinico.get("nota")}"' if clinico.get('nota') else 'Não informada'}
- Dados completos: {bool(vitais_coletados and clinico.get('supplementaryOxygen') and clinico.get('nota'))}
- Aferição em andamento: {clinico.get('afericao_em_andamento', False)}
- Já teve aferição completa no plantão: {clinico.get('afericao_completa_realizada', False)}
- RAG: Processado via webhook n8n"""

        contexto += f"""

DADOS DE FINALIZAÇÃO:
- Notas existentes: {len(finalizacao.get('notas_existentes', []))}
- Tópicos preenchidos: {len([t for t in finalizacao.get('topicos', {}).values() if t is not None])}
- Tópicos faltantes: {', '.join(finalizacao.get('faltantes', [])) if finalizacao.get('faltantes') else 'Nenhum'}
- Finalização completa: {len(finalizacao.get('faltantes', [])) == 0}

FORA DE ESCALA:
- Substituição já concluída: {meta.get('substituicao_concluida', False)}
- Aguardando escolha de substituto: {meta.get('aguardando_escolha_substituto', False)}
- Substitutos disponíveis: {len(meta.get('substitutos_disponiveis', []))}
- Lista formatada de substitutos: {meta.get('lista_substitutos_formatada', 'N/A')}
- Substituto escolhido: {meta.get('substituto_escolhido', 'Nenhum')}

RETOMADA:
- Tem retomada: {bool(retomada)}
- Fluxo retomada: {retomada.get('fluxo', 'Nenhum')}

RESULTADO SUBGRAFO:
- Código: {codigo_resultado or 'Nenhum'}"""

        return contexto
