#!/usr/bin/env python3
"""
Gerador de Diagrama de Fluxos do WhatsApp Orchestrator
======================================================

Gera um diagrama visual usando matplotlib e PIL
"""

from PIL import Image, ImageDraw, ImageFont
import os

def create_flow_diagram():
    """Cria diagrama visual dos fluxos"""
    
    # Configurações
    width = 2400
    height = 3000
    img = Image.new('RGB', (width, height), color='white')
    draw = ImageDraw.Draw(img)
    
    # Fonte (usa fonte padrão do sistema)
    try:
        title_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 40)
        header_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 30)
        text_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 20)
        small_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 16)
    except:
        title_font = ImageFont.load_default()
        header_font = ImageFont.load_default()
        text_font = ImageFont.load_default()
        small_font = ImageFont.load_default()
    
    # Cores
    COLORS = {
        'title': '#1976D2',
        'header': '#424242',
        'box_gate': '#FFEB3B',
        'box_clinical': '#4CAF50',
        'box_operational': '#FF9800',
        'box_finalization': '#9C27B0',
        'box_scale': '#00BCD4',
        'box_fiscal': '#F44336',
        'text': '#212121',
        'border': '#757575',
        'critical': '#D32F2F',
    }
    
    y_pos = 50
    
    # Título
    draw.text((width//2 - 400, y_pos), "WhatsApp Orchestrator - Fluxos Completos", 
              fill=COLORS['title'], font=title_font)
    y_pos += 80
    
    # Função auxiliar para desenhar caixa
    def draw_box(x, y, w, h, text, color, border_color=None):
        if border_color is None:
            border_color = COLORS['border']
        draw.rectangle([x, y, x+w, y+h], fill=color, outline=border_color, width=3)
        # Texto centralizado
        bbox = draw.textbbox((0, 0), text, font=text_font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        draw.text((x + (w - text_w)//2, y + (h - text_h)//2), 
                 text, fill=COLORS['text'], font=text_font)
    
    # Função para desenhar seta
    def draw_arrow(x1, y1, x2, y2, label=""):
        draw.line([x1, y1, x2, y2], fill=COLORS['border'], width=2)
        # Ponta da seta
        if y2 > y1:  # Seta para baixo
            draw.polygon([(x2-10, y2-15), (x2, y2), (x2+10, y2-15)], fill=COLORS['border'])
        if label:
            draw.text((x1 + 10, (y1+y2)//2 - 10), label, fill=COLORS['header'], font=small_font)
    
    # ===== ENTRADA =====
    draw.text((50, y_pos), "📥 ENTRADA", fill=COLORS['header'], font=header_font)
    y_pos += 50
    draw_box(100, y_pos, 400, 80, "Webhook WhatsApp\n/webhook/whatsapp", '#E3F2FD')
    y_pos += 100
    draw_arrow(300, y_pos - 20, 300, y_pos + 30)
    draw_box(100, y_pos + 30, 400, 80, "MainRouter\nRoteamento Inteligente", '#FFF3E0')
    y_pos += 130
    
    # ===== GATES =====
    draw.text((50, y_pos), "🚦 GATES DETERMINÍSTICOS (Prioridade)", fill=COLORS['header'], font=header_font)
    y_pos += 50
    
    gates = [
        "Gate 0: Nota Operacional?\n(Prioridade Máxima)",
        "Gate 1: Confirmação Pendente?",
        "Gate 2: Retomada?",
        "Gate 3: Dados Sessão?",
        "Gate 4: finishReminderSent=true?\n(Finalização)",
        "Gate 5: LLM Classification"
    ]
    
    gate_y_start = y_pos
    for i, gate in enumerate(gates):
        draw_box(100, y_pos, 500, 70, gate, COLORS['box_gate'])
        if i < len(gates) - 1:
            draw_arrow(350, y_pos + 70, 350, y_pos + 100)
        y_pos += 90
    
    y_pos += 50
    
    # ===== SUBGRAFOS =====
    draw.text((50, y_pos), "🔄 SUBGRAFOS ESPECIALIZADOS", fill=COLORS['header'], font=header_font)
    y_pos += 50
    
    # Linha 1: Operacional, Escala, Clínico
    x_start = 50
    draw_box(x_start, y_pos, 350, 100, "⚡ OPERACIONAL\n(Instantâneo)\nSem Confirmação", COLORS['box_operational'])
    draw_box(x_start + 400, y_pos, 350, 100, "🏥 ESCALA\nConfirmação\nde Presença", COLORS['box_scale'])
    draw_box(x_start + 800, y_pos, 350, 100, "📊 CLÍNICO\nDados Vitais\n+ Notas", COLORS['box_clinical'])
    
    y_pos += 120
    
    # Linha 2: Finalizar, Auxiliar
    draw_box(x_start + 200, y_pos, 350, 100, "📋 FINALIZAR\n8 Tópicos de\nEncerramento", COLORS['box_finalization'])
    draw_box(x_start + 600, y_pos, 350, 100, "❓ AUXILIAR\nAjuda e\nOrientações", '#F3E5F5')
    
    y_pos += 150
    
    # ===== FLUXO CLÍNICO DETALHADO =====
    draw.text((50, y_pos), "📊 FLUXO CLÍNICO DETALHADO", fill=COLORS['header'], font=header_font)
    y_pos += 50
    
    # Primeira Aferição
    draw.rectangle([50, y_pos, 1150, y_pos + 200], fill='#FFEBEE', outline=COLORS['critical'], width=4)
    draw.text((70, y_pos + 10), "🔴 PRIMEIRA AFERIÇÃO (OBRIGATÓRIA COMPLETA)", 
             fill=COLORS['critical'], font=header_font)
    draw.text((70, y_pos + 50), "✅ TODOS os sinais vitais (PA, FC, FR, Sat, Temp)", 
             fill=COLORS['text'], font=text_font)
    draw.text((70, y_pos + 80), "✅ Condição respiratória (Ar ambiente/O2/VM)", 
             fill=COLORS['text'], font=text_font)
    draw.text((70, y_pos + 110), "✅ Nota clínica (OBRIGATÓRIA)", 
             fill=COLORS['text'], font=text_font)
    draw.text((70, y_pos + 140), "🚫 Sistema REJEITA nota isolada na primeira aferição", 
             fill=COLORS['critical'], font=text_font)
    draw.text((70, y_pos + 170), "Flag: afericao_completa_realizada = true", 
             fill=COLORS['text'], font=small_font)
    
    y_pos += 220
    
    # Aferições Subsequentes
    draw.rectangle([50, y_pos, 1150, y_pos + 240], fill='#E8F5E9', outline=COLORS['box_clinical'], width=4)
    draw.text((70, y_pos + 10), "🟢 AFERIÇÕES SUBSEQUENTES (FLEXÍVEIS)", 
             fill=COLORS['box_clinical'], font=header_font)
    
    draw.text((70, y_pos + 50), "OPÇÃO 1: Aferição Completa (com ou sem nota)", 
             fill=COLORS['header'], font=text_font)
    draw.text((90, y_pos + 80), "✅ TODOS os sinais vitais", fill=COLORS['text'], font=small_font)
    draw.text((90, y_pos + 105), "✅ Condição respiratória", fill=COLORS['text'], font=small_font)
    draw.text((90, y_pos + 130), "⚪ Nota clínica (OPCIONAL - default: 'sem alterações')", 
             fill=COLORS['text'], font=small_font)
    
    draw.text((70, y_pos + 160), "OPÇÃO 2: Nota Clínica Isolada", 
             fill=COLORS['header'], font=text_font)
    draw.text((90, y_pos + 190), "📝 Apenas nota clínica (sem vitais)", fill=COLORS['text'], font=small_font)
    draw.text((90, y_pos + 215), "⚡ Processamento direto via webhook n8n", fill=COLORS['text'], font=small_font)
    
    y_pos += 260
    
    # ===== FISCAL PROCESSOR =====
    draw.text((50, y_pos), "🧠 FISCAL PROCESSOR (Orquestrador Central)", fill=COLORS['header'], font=header_font)
    y_pos += 50
    draw_box(100, y_pos, 1000, 100, "FiscalLLM\nRespostas Contextuais Dinâmicas via LLM\nLê Estado Completo do DynamoDB", COLORS['box_fiscal'])
    
    y_pos += 130
    
    # ===== INTEGRAÇÕES =====
    draw.text((50, y_pos), "🔄 INTEGRAÇÕES EXTERNAS", fill=COLORS['header'], font=header_font)
    y_pos += 50
    
    integrations = [
        ("Webhook n8n", "Dados Clínicos + Operacionais"),
        ("Lambda getScheduleStarted", "Dados da Sessão + finishReminderSent"),
        ("Lambda updateWorkScheduleResponse", "Confirmação de Presença"),
        ("Lambda getNoteReport", "Notas Existentes"),
        ("Lambda updatereportsummaryad", "Relatório Final"),
        ("DynamoDB", "Estado Persistente")
    ]
    
    x_col1 = 50
    x_col2 = 650
    for i, (name, desc) in enumerate(integrations):
        x = x_col1 if i % 2 == 0 else x_col2
        y = y_pos + (i // 2) * 70
        draw_box(x, y, 550, 60, f"{name}\n{desc}", '#CFD8DC')
    
    y_pos += (len(integrations) // 2 + 1) * 70 + 30
    
    # ===== REGRAS CRÍTICAS =====
    draw.text((50, y_pos), "⚠️ REGRAS CRÍTICAS", fill=COLORS['critical'], font=header_font)
    y_pos += 50
    
    rules = [
        "🚨 NUNCA mencionar finalização se finishReminderSent=false",
        "🔴 Primeira aferição DEVE ser completa (vitais+cond+nota)",
        "🟢 Aferições subsequentes: nota clínica OPCIONAL",
        "⚡ Notas operacionais: processamento INSTANTÂNEO (sem confirmação)",
        "🎯 Fiscal gera TODAS as respostas via LLM (sem respostas estáticas)",
        "🔄 Estado sempre persistido em DynamoDB após cada interação"
    ]
    
    for rule in rules:
        draw.rectangle([50, y_pos, 1150, y_pos + 50], fill='#FFEBEE', outline=COLORS['critical'], width=2)
        draw.text((70, y_pos + 15), rule, fill=COLORS['text'], font=text_font)
        y_pos += 60
    
    # Salva imagem
    output_path = 'whatsapp_orchestrator_business_flows.png'
    img.save(output_path)
    
    print(f"✅ Diagrama gerado com sucesso: {output_path}")
    print(f"📊 Localização: {os.path.abspath(output_path)}")
    print(f"📐 Dimensões: {width}x{height}px")
    
    return output_path

if __name__ == '__main__':
    try:
        diagram_path = create_flow_diagram()
        print("\n🎉 Diagrama completo criado com sucesso!")
    except Exception as e:
        print(f"\n❌ Erro ao gerar diagrama: {e}")
        import traceback
        traceback.print_exc()

