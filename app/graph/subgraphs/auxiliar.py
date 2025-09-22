"""
Subgrafo Auxiliar
Dúvidas, ajuda, saudações, outros assuntos
"""
import structlog

from app.graph.state import GraphState

logger = structlog.get_logger(__name__)


class AuxiliarSubgraph:
    """Subgrafo para assuntos auxiliares e ajuda"""
    
    def __init__(self):
        logger.info("AuxiliarSubgraph inicializado")
    
    def _identificar_tipo_ajuda(self, texto_usuario: str) -> str:
        """
        Identifica tipo de ajuda solicitada
        Returns: tipo da ajuda
        """
        texto_lower = texto_usuario.lower()
        
        # Saudações
        if any(palavra in texto_lower for palavra in ['oi', 'olá', 'ola', 'bom dia', 'boa tarde', 'boa noite']):
            return 'saudacao'
        
        # Ajuda/instruções
        if any(palavra in texto_lower for palavra in ['ajuda', 'help', 'como', 'instrução', 'instrucao']):
            return 'instrucoes'
        
        # Problemas técnicos
        if any(palavra in texto_lower for palavra in ['erro', 'problema', 'bug', 'não funciona', 'nao funciona']):
            return 'suporte'
        
        # Dúvidas sobre plantão
        if any(palavra in texto_lower for palavra in ['plantão', 'plantao', 'escala', 'horário', 'horario']):
            return 'plantao'
        
        # Default
        return 'geral'
    
    def _gerar_resposta_ajuda(self, tipo: str, state: GraphState) -> str:
        """Gera resposta baseada no tipo de ajuda"""
        
        if tipo == 'saudacao':
            nome_caregiver = state.sessao.get("caregiver_id", "")
            return f"Olá! Sou seu assistente para o plantão. Como posso ajudar hoje?"
        
        elif tipo == 'instrucoes':
            return """Posso ajudar você com:

📋 ESCALA: "confirmo presença" ou "cancelar plantão"
🏥 CLÍNICO: Envie sinais vitais (PA 120x80, FC 75, etc.) ou notas clínicas
📝 OPERACIONAL: Notas administrativas e observações gerais
✅ FINALIZAR: "finalizar plantão" quando terminar

Exemplos:
• "PA 120x80 FC 75 FR 18 Sat 97 Temp 36.5"
• "Paciente apresenta tosse seca"
• "Confirmo minha presença"
• "Finalizar plantão"

O que precisa fazer?"""
        
        elif tipo == 'suporte':
            return """Se está enfrentando problemas técnicos:

1. Verifique sua conexão com a internet
2. Tente enviar a mensagem novamente
3. Se o problema persistir, entre em contato com o suporte técnico

Para dúvidas sobre o sistema, digite "ajuda"."""
        
        elif tipo == 'plantao':
            turno_permitido = state.sessao.get("turno_permitido")
            if turno_permitido is None:
                return "Digite 'confirmo presença' para verificar seu plantão de hoje."
            elif turno_permitido:
                return "Seu plantão está ativo. Você pode enviar dados clínicos ou finalizar quando terminar."
            else:
                return "Nenhum plantão encontrado para hoje ou plantão não permitido."
        
        else:
            return """Olá! Sou seu assistente para o plantão.

Comandos principais:
• "confirmo presença" - para iniciar plantão
• Enviar sinais vitais - PA, FC, FR, Sat, Temp
• "finalizar plantão" - para encerrar
• "ajuda" - para mais instruções

O que precisa fazer?"""
    
    def processar(self, state: GraphState) -> str:
        """
        Processa subgrafo auxiliar
        
        Returns:
            Mensagem de ajuda para ser processada pelo fiscal
        """
        logger.info("Processando subgrafo auxiliar")
        
        # Adiciona à lista de fluxos executados
        state.adicionar_fluxo_executado("auxiliar")
        
        texto_usuario = state.entrada.get("texto_usuario", "")
        
        # Identifica tipo de ajuda
        tipo = self._identificar_tipo_ajuda(texto_usuario)
        
        logger.info("Tipo de ajuda identificado", tipo=tipo, texto=texto_usuario[:50])
        
        # Gera resposta
        resposta = self._gerar_resposta_ajuda(tipo, state)
        
        return resposta
