"""
Módulo Fiscal - Sempre o último
Consolida resposta única baseado no estado e fluxos executados
"""
import structlog

from app.graph.state import GraphState

logger = structlog.get_logger(__name__)


class FiscalProcessor:
    """Processador fiscal - consolida resposta final"""
    
    def __init__(self):
        logger.info("FiscalProcessor inicializado")
    
    def _analisar_contexto(self, state: GraphState) -> dict:
        """Analisa contexto atual do estado"""
        contexto = {
            "fluxos_executados": state.fluxos_executados,
            "tem_pendente": state.tem_pendente(),
            "tem_retomada": state.tem_retomada(),
            "intencao": state.roteador.get("intencao"),
            "vitais_completos": state.get_vitais_completos(),
            "vitais_faltantes": state.get_vitais_faltantes(),
            "turno_permitido": state.sessao.get("turno_permitido"),
            "cancelado": state.sessao.get("cancelado", False)
        }
        
        logger.debug("Contexto fiscal analisado", **contexto)
        return contexto
    
    def _processar_warnings(self, state: GraphState) -> str:
        """Processa warnings e gera sugestões"""
        # Verifica warnings na extração clínica
        warnings_msg = ""
        
        # Exemplo de warning sobre PA ambígua
        if state.meta.get("extraction_warnings"):
            warnings = state.meta["extraction_warnings"]
            for warning in warnings:
                if "PA_ambigua" in warning:
                    warnings_msg += "\n⚠️ PA ficou ambígua. Se for 120 por 80, envie 'PA 120x80'."
                elif "incoerente" in warning:
                    campo = warning.split("_")[0]
                    warnings_msg += f"\n⚠️ {campo} fora da faixa normal, foi ignorado."
        
        return warnings_msg
    
    def _gerar_resposta_escala(self, state: GraphState, contexto: dict) -> str:
        """Gera resposta para fluxo de escala"""
        if contexto["tem_pendente"]:
            return "Aguardando confirmação da ação de escala."
        
        # Escala processada com sucesso
        if state.sessao.get("turno_permitido"):
            return "Presença confirmada. O que mais deseja fazer?"
        else:
            return "Plantão cancelado ou não encontrado."
    
    def _gerar_resposta_clinico(self, state: GraphState, contexto: dict) -> str:
        """Gera resposta para fluxo clínico"""
        if contexto["tem_pendente"]:
            return "Aguardando confirmação para salvar dados clínicos."
        
        # Dados clínicos processados
        clinico = state.clinico
        vitais = clinico.get("vitais", {})
        vitais_validos = {k: v for k, v in vitais.items() if v is not None}
        
        resposta_partes = []
        
        if vitais_validos:
            vitais_str = ", ".join([f"{k} {v}" for k, v in vitais_validos.items()])
            resposta_partes.append(f"Salvei seus vitais ({vitais_str})")
        
        if clinico.get("nota"):
            resposta_partes.append("nota clínica")
        
        if clinico.get("sintomas"):
            resposta_partes.append(f"{len(clinico['sintomas'])} sintomas identificados")
        
        resposta_base = "Salvei: " + ", ".join(resposta_partes) if resposta_partes else "Dados clínicos salvos"
        
        # Verifica se pode finalizar
        if contexto["vitais_completos"]:
            resposta_base += ". Deseja finalizar o plantão?"
        else:
            faltantes = contexto["vitais_faltantes"]
            if faltantes:
                faltantes_str = ", ".join(faltantes)
                resposta_base += f". Faltam: {faltantes_str} para finalizar."
        
        return resposta_base
    
    def _gerar_resposta_operacional(self, state: GraphState, contexto: dict) -> str:
        """Gera resposta para fluxo operacional"""
        # Operacional não tem confirmação, já foi processado
        return "Nota administrativa registrada. O que mais precisa fazer?"
    
    def _gerar_resposta_finalizar(self, state: GraphState, contexto: dict) -> str:
        """Gera resposta para fluxo de finalização"""
        if contexto["tem_pendente"]:
            return "Aguardando confirmação para finalizar o plantão."
        
        if contexto["tem_retomada"] and state.retomada.get("fluxo") == "finalizar":
            # Retomada por falta de vitais
            faltantes = state.retomada.get("faltantes", [])
            faltantes_str = ", ".join(faltantes)
            return f"Para finalizar, preciso dos vitais: {faltantes_str}. Envie agora."
        
        # Finalização concluída
        return "Plantão finalizado com sucesso! Obrigado pelo seu trabalho."
    
    def _gerar_resposta_auxiliar(self, state: GraphState, contexto: dict) -> str:
        """Gera resposta para fluxo auxiliar"""
        # Auxiliar já tem sua própria resposta, apenas passa adiante
        return "Como posso ajudar mais?"
    
    def _gerar_resposta_padrao(self, state: GraphState, contexto: dict) -> str:
        """Gera resposta padrão quando não há fluxo específico"""
        if contexto["cancelado"] or not contexto["turno_permitido"]:
            return "Plantão não disponível. Digite 'ajuda' para mais informações."
        
        return "Olá! Como posso ajudar hoje? Digite 'ajuda' para ver os comandos disponíveis."
    
    def processar_resposta_fiscal(self, state: GraphState, resultado_subgrafo: str = None) -> str:
        """
        Processa resposta fiscal final
        
        Args:
            state: Estado atual do grafo
            resultado_subgrafo: Resultado do subgrafo executado (opcional)
        
        Returns:
            Resposta única e curta para o usuário
        """
        logger.info("Processando resposta fiscal", 
                   fluxos_executados=state.fluxos_executados,
                   resultado_subgrafo=resultado_subgrafo[:50] if resultado_subgrafo else None)
        
        # Analisa contexto
        contexto = self._analisar_contexto(state)
        
        # Se há resultado direto do subgrafo, usa como base
        if resultado_subgrafo:
            resposta_base = resultado_subgrafo
        else:
            resposta_base = ""
        
        # Ajusta resposta baseado no último fluxo executado
        if state.fluxos_executados:
            ultimo_fluxo = state.fluxos_executados[-1]
            
            if ultimo_fluxo == "escala":
                if not resposta_base:
                    resposta_base = self._gerar_resposta_escala(state, contexto)
            elif ultimo_fluxo == "clinico":
                if not resposta_base:
                    resposta_base = self._gerar_resposta_clinico(state, contexto)
            elif ultimo_fluxo == "operacional":
                if not resposta_base:
                    resposta_base = self._gerar_resposta_operacional(state, contexto)
            elif ultimo_fluxo == "finalizar":
                if not resposta_base:
                    resposta_base = self._gerar_resposta_finalizar(state, contexto)
            elif ultimo_fluxo == "auxiliar":
                if not resposta_base:
                    resposta_base = self._gerar_resposta_auxiliar(state, contexto)
        else:
            # Nenhum fluxo executado ainda
            resposta_base = self._gerar_resposta_padrao(state, contexto)
        
        # Adiciona warnings se houver
        warnings = self._processar_warnings(state)
        resposta_final = resposta_base + warnings
        
        # Salva resposta no estado
        state.resposta_fiscal = resposta_final
        
        logger.info("Resposta fiscal gerada",
                   resposta_length=len(resposta_final),
                   tem_warnings=bool(warnings))
        
        return resposta_final
