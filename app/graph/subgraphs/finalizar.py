"""
Subgrafo Finalizar
Finalização do plantão com confirmação obrigatória
"""
from typing import Dict, Any
import structlog

from app.graph.state import GraphState
from app.infra.http import LambdaHttpClient

logger = structlog.get_logger(__name__)


class FinalizarSubgraph:
    """Subgrafo para finalização do plantão"""
    
    def __init__(self, 
                 http_client: LambdaHttpClient,
                 lambda_update_summary_url: str):
        self.http_client = http_client
        self.lambda_update_summary_url = lambda_update_summary_url
        logger.info("FinalizarSubgraph inicializado")
    
    def _verificar_vitais_completos(self, state: GraphState) -> tuple[bool, list]:
        """
        Verifica se todos os vitais estão presentes
        Returns: (completos, faltantes)
        """
        vitais_completos = state.get_vitais_completos()
        faltantes = state.get_vitais_faltantes()
        
        return vitais_completos, faltantes
    
    def _preparar_payload_finalizacao(self, state: GraphState) -> Dict[str, Any]:
        """Prepara payload para updatereportsummaryad"""
        sessao = state.sessao
        
        payload = {
            "reportID": sessao.get("report_id"),
            "reportDate": sessao.get("data_relatorio"),
            "scheduleID": sessao.get("schedule_id"),
            "caregiverID": sessao.get("caregiver_id"),
            "patientID": sessao.get("patient_id"),
            "action": "finalize"
        }
        
        logger.debug("Payload finalização preparado",
                    report_id=sessao.get("report_id"),
                    schedule_id=sessao.get("schedule_id"))
        
        return payload
    
    def _executar_finalizacao(self, state: GraphState) -> str:
        """Executa finalização do plantão"""
        pendente = state.pendente
        if not pendente or pendente.get("fluxo") != "finalizar":
            return "Erro: Nenhuma finalização pendente."
        
        payload = pendente.get("payload")
        
        try:
            logger.info("Finalizando plantão")
            
            # Chama Lambda
            result = self.http_client.update_report_summary(
                self.lambda_update_summary_url,
                payload
            )
            
            # Limpa pendente e retomada
            state.limpar_pendente()
            if state.retomada and state.retomada.get("fluxo") == "finalizar":
                state.retomada = None
            
            logger.info("Plantão finalizado com sucesso")
            return "Plantão finalizado com sucesso! Obrigado pelo seu trabalho."
            
        except Exception as e:
            logger.error("Erro ao finalizar plantão", error=str(e))
            state.limpar_pendente()
            return f"Erro ao finalizar plantão: {str(e)}"
    
    def processar(self, state: GraphState) -> str:
        """
        Processa subgrafo de finalização
        
        Verifica se todos os vitais estão presentes antes de finalizar
        Se faltarem vitais, redireciona para clínico
        
        Returns:
            Mensagem para ser processada pelo fiscal
        """
        logger.info("Processando subgrafo finalizar")
        
        # Adiciona à lista de fluxos executados
        state.adicionar_fluxo_executado("finalizar")
        
        texto_usuario = state.entrada.get("texto_usuario", "").lower()
        
        # Verifica se é resposta de confirmação
        if state.tem_pendente() and state.pendente.get("fluxo") == "finalizar":
            if "sim" in texto_usuario or "confirmo" in texto_usuario or "ok" in texto_usuario:
                return self._executar_finalizacao(state)
            elif "não" in texto_usuario or "nao" in texto_usuario or "cancelar" in texto_usuario:
                state.limpar_pendente()
                return "Finalização cancelada."
            else:
                return "Responda 'sim' para confirmar a finalização ou 'não' para cancelar."
        
        # Verifica se todos os vitais estão presentes
        vitais_completos, faltantes = self._verificar_vitais_completos(state)
        
        if not vitais_completos:
            logger.info("Vitais incompletos para finalização", faltantes=faltantes)
            
            # Configura retomada para voltar ao finalizar após coletar vitais
            state.retomada = {
                "fluxo": "finalizar",
                "motivo": "precisa_vitais",
                "faltantes": faltantes
            }
            
            faltantes_str = ", ".join(faltantes)
            return f"Para finalizar o plantão, preciso dos seguintes vitais: {faltantes_str}. Envie-os agora."
        
        # Se chegou até aqui, vitais estão completos
        # Prepara confirmação
        payload = self._preparar_payload_finalizacao(state)
        
        state.pendente = {
            "fluxo": "finalizar",
            "payload": payload
        }
        
        return "Confirma a finalização do plantão? Todos os dados serão enviados."
