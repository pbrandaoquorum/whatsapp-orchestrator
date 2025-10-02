#!/usr/bin/env python3
"""
Gerador de Diagrama de Fluxos do WhatsApp Orchestrator
======================================================

Gera um diagrama visual completo mostrando:
- Todos os fluxos de negócio
- Gates determinísticos
- Regras de prioridade
- Integrações externas
"""

from graphviz import Digraph
import os

def create_comprehensive_flow_diagram():
    """Cria diagrama completo do sistema"""
    
    # Configuração do gráfico
    dot = Digraph(comment='WhatsApp Orchestrator - Fluxos Completos', format='png')
    dot.attr(rankdir='TB', size='20,30!', dpi='300')
    dot.attr('node', shape='box', style='rounded,filled', fontname='Arial', fontsize='10')
    dot.attr('edge', fontname='Arial', fontsize='9')
    
    # ===== ENTRADA =====
    with dot.subgraph(name='cluster_entrada') as entrada:
        entrada.attr(label='📥 ENTRADA', style='filled', color='lightgrey')
        entrada.node('webhook', 'Webhook WhatsApp\n/webhook/whatsapp', fillcolor='#E3F2FD')
        entrada.node('router', 'MainRouter\nRoteamento Inteligente', fillcolor='#FFF3E0')
    
    # ===== GATES DETERMINÍSTICOS =====
    with dot.subgraph(name='cluster_gates') as gates:
        gates.attr(label='🚦 GATES DETERMINÍSTICOS (Ordem de Prioridade)', style='filled', color='lightyellow')
        gates.node('gate0', 'Gate 0: Nota Operacional?\n(Prioridade Máxima)', fillcolor='#FFEBEE', shape='diamond')
        gates.node('gate1', 'Gate 1: Confirmação Pendente?', fillcolor='#FCE4EC', shape='diamond')
        gates.node('gate2', 'Gate 2: Retomada?', fillcolor='#F3E5F5', shape='diamond')
        gates.node('gate3', 'Gate 3: Dados Sessão?', fillcolor='#EDE7F6', shape='diamond')
        gates.node('gate4', 'Gate 4: finishReminderSent=true?\n(Finalização)', fillcolor='#E8EAF6', shape='diamond')
        gates.node('gate5', 'Gate 5: LLM Classification', fillcolor='#E3F2FD', shape='diamond')
    
    # Conexões dos Gates
    dot.edge('webhook', 'router')
    dot.edge('router', 'gate0', label='1º')
    dot.edge('gate0', 'gate1', label='Não')
    dot.edge('gate1', 'gate2', label='Não')
    dot.edge('gate2', 'gate3', label='Não')
    dot.edge('gate3', 'gate4', label='Sim')
    dot.edge('gate4', 'gate5', label='Não')
    
    # ===== SUBGRAFOS =====
    with dot.subgraph(name='cluster_subgraphs') as subgraphs:
        subgraphs.attr(label='🔄 SUBGRAFOS ESPECIALIZADOS', style='filled', color='lightgreen')
        
        # Operacional
        subgraphs.node('operacional', '⚡ Operacional\n(Instantâneo)\nSem Confirmação', fillcolor='#E8F5E9')
        
        # Escala
        subgraphs.node('escala', '🏥 Escala\nConfirmação de Presença', fillcolor='#E0F2F1')
        
        # Clínico
        subgraphs.node('clinico', '📊 Clínico\nDados Vitais + Notas', fillcolor='#E1F5FE')
        
        # Finalizar
        subgraphs.node('finalizar', '📋 Finalizar\n8 Tópicos de Encerramento', fillcolor='#FFF9C4')
        
        # Auxiliar
        subgraphs.node('auxiliar', '❓ Auxiliar\nAjuda e Orientações', fillcolor='#F3E5F5')
    
    # Conexões Gates → Subgrafos
    dot.edge('gate0', 'operacional', label='SIM', color='red', penwidth='2')
    dot.edge('gate1', 'escala', label='fluxo=escala')
    dot.edge('gate1', 'clinico', label='fluxo=clinico')
    dot.edge('gate1', 'finalizar', label='fluxo=finalizar')
    dot.edge('gate4', 'finalizar', label='SIM\n(Prioridade)', color='orange', penwidth='2')
    dot.edge('gate5', 'escala', label='intent=escala')
    dot.edge('gate5', 'clinico', label='intent=clinico')
    dot.edge('gate5', 'operacional', label='intent=operacional')
    dot.edge('gate5', 'finalizar', label='intent=finalizar')
    dot.edge('gate5', 'auxiliar', label='intent=auxiliar')
    
    # ===== FLUXO CLÍNICO DETALHADO =====
    with dot.subgraph(name='cluster_clinico_detail') as clinico_detail:
        clinico_detail.attr(label='📊 FLUXO CLÍNICO DETALHADO', style='filled', color='lightblue')
        
        clinico_detail.node('check_first', 'afericao_completa_realizada?', fillcolor='#B3E5FC', shape='diamond')
        clinico_detail.node('first_full', '🔴 PRIMEIRA AFERIÇÃO\n(OBRIGATÓRIA COMPLETA)\n✅ Todos vitais\n✅ Condição resp\n✅ Nota clínica', fillcolor='#FFCDD2')
        clinico_detail.node('subsequent', '🟢 AFERIÇÕES SUBSEQUENTES\n(FLEXÍVEIS)', fillcolor='#C8E6C9')
        clinico_detail.node('opt1', 'Opção 1: Aferição\n✅ Vitais\n✅ Cond resp\n⚪ Nota (opcional)', fillcolor='#DCEDC8')
        clinico_detail.node('opt2', 'Opção 2: Nota Isolada\n📝 Apenas nota', fillcolor='#F0F4C3')
        
    dot.edge('clinico', 'check_first')
    dot.edge('check_first', 'first_full', label='FALSE\n(Primeira)')
    dot.edge('check_first', 'subsequent', label='TRUE\n(Subsequente)')
    dot.edge('subsequent', 'opt1')
    dot.edge('subsequent', 'opt2')
    
    # ===== FISCAL PROCESSOR =====
    with dot.subgraph(name='cluster_fiscal') as fiscal:
        fiscal.attr(label='🧠 FISCAL PROCESSOR (Orquestrador Central)', style='filled', color='#FFF3E0')
        fiscal.node('fiscal_llm', 'FiscalLLM\nRespostas Contextuais\nDinâmicas via LLM', fillcolor='#FFE082')
        fiscal.node('state_context', 'Estado Completo\nDynamoDB', fillcolor='#FFECB3')
    
    # Conexões Subgrafos → Fiscal
    dot.edge('operacional', 'fiscal_llm', label='OPERATIONAL_NOTE_SAVED')
    dot.edge('escala', 'fiscal_llm', label='Códigos de Escala')
    dot.edge('clinico', 'fiscal_llm', label='CLINICAL_DATA_SAVED\nCLINICAL_NOTE_READY\netc.')
    dot.edge('first_full', 'fiscal_llm', label='CLINICAL_DATA_READY')
    dot.edge('opt1', 'fiscal_llm', label='CLINICAL_DATA_READY')
    dot.edge('opt2', 'fiscal_llm', label='CLINICAL_NOTE_READY')
    dot.edge('finalizar', 'fiscal_llm', label='FINALIZATION_COMPLETED')
    dot.edge('auxiliar', 'fiscal_llm', label='Resposta de Ajuda')
    
    dot.edge('state_context', 'fiscal_llm', label='Contexto Completo', style='dashed')
    
    # ===== INTEGRAÇÕES EXTERNAS =====
    with dot.subgraph(name='cluster_integrations') as integrations:
        integrations.attr(label='🔄 INTEGRAÇÕES EXTERNAS', style='filled', color='lightcoral')
        integrations.node('n8n', 'Webhook n8n\n(Dados Clínicos)', fillcolor='#FFCCBC')
        integrations.node('lambda_schedule', 'Lambda\ngetScheduleStarted', fillcolor='#D7CCC8')
        integrations.node('lambda_update_schedule', 'Lambda\nupdateWorkScheduleResponse', fillcolor='#D7CCC8')
        integrations.node('lambda_notes', 'Lambda\ngetNoteReport', fillcolor='#D7CCC8')
        integrations.node('lambda_summary', 'Lambda\nupdatereportsummaryad', fillcolor='#D7CCC8')
        integrations.node('dynamodb', 'DynamoDB\nEstado Persistente', fillcolor='#CFD8DC')
    
    # Conexões com Integrações
    dot.edge('operacional', 'n8n', label='POST (Instantâneo)')
    dot.edge('clinico', 'n8n', label='POST (Confirmado)')
    dot.edge('escala', 'lambda_schedule', label='GET')
    dot.edge('escala', 'lambda_update_schedule', label='POST')
    dot.edge('finalizar', 'lambda_notes', label='GET')
    dot.edge('finalizar', 'lambda_summary', label='POST')
    dot.edge('finalizar', 'n8n', label='POST (Parcial)')
    
    # DynamoDB conexões
    dot.edge('router', 'dynamodb', label='Read/Write', style='dashed', dir='both')
    dot.edge('fiscal_llm', 'dynamodb', label='Read State', style='dashed')
    
    # ===== SAÍDA =====
    with dot.subgraph(name='cluster_output') as output:
        output.attr(label='📤 SAÍDA', style='filled', color='lightgrey')
        output.node('response', 'Resposta WhatsApp\nJSON + texto', fillcolor='#C5E1A5')
    
    dot.edge('fiscal_llm', 'response', label='Resposta Final')
    
    # ===== REGRAS CRÍTICAS =====
    with dot.subgraph(name='cluster_rules') as rules:
        rules.attr(label='⚠️ REGRAS CRÍTICAS', style='filled', color='#FFEBEE')
        rules.node('rule1', '🚨 NUNCA mencionar finalização\nse finishReminderSent=false', fillcolor='#FFCDD2', shape='note')
        rules.node('rule2', '🔴 Primeira aferição DEVE\nser completa (vitais+cond+nota)', fillcolor='#FFCDD2', shape='note')
        rules.node('rule3', '🟢 Aferições subsequentes:\nnota clínica OPCIONAL', fillcolor='#C8E6C9', shape='note')
        rules.node('rule4', '⚡ Notas operacionais:\nprocessamento INSTANTÂNEO', fillcolor='#FFF9C4', shape='note')
    
    # Renderiza o diagrama
    output_path = 'whatsapp_orchestrator_complete_flow'
    dot.render(output_path, cleanup=True)
    
    print(f"✅ Diagrama gerado com sucesso: {output_path}.png")
    print(f"📊 Localização: {os.path.abspath(output_path)}.png")
    
    return dot

if __name__ == '__main__':
    try:
        diagram = create_comprehensive_flow_diagram()
        print("\n🎉 Diagrama completo criado com sucesso!")
    except Exception as e:
        print(f"\n❌ Erro ao gerar diagrama: {e}")
        import traceback
        traceback.print_exc()

