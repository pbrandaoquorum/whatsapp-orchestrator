"""
Subgrafo Operacional
Envio direto de notas administrativas (NOTE_ONLY)
Sem confirmação (diferente dos outros subgrafos)
"""
from typing import Dict, Any
import structlog

from app.graph.state import GraphState
from app.infra.http import LambdaHttpClient

logger = structlog.get_logger(__name__)


class OperacionalSubgraph:
    """Subgrafo para notas operacionais/administrativas"""
    
    def __init__(self, 
                 http_client: LambdaHttpClient,
                 lambda_update_clinical_url: str):
        self.http_client = http_client
        self.lambda_update_clinical_url = lambda_update_clinical_url
        logger.info("OperacionalSubgraph inicializado")
    
    def _preparar_payload_note_only(self, state: GraphState) -> Dict[str, Any]:
        """Prepara payload para NOTE_ONLY"""
        sessao = state.sessao
        texto_usuario = state.entrada.get("texto_usuario", "")
        
        payload = {
            "reportID": sessao.get("report_id"),
            "reportDate": sessao.get("data_relatorio"),
            "scheduleID": sessao.get("schedule_id"),
            "caregiverID": sessao.get("caregiver_id"),
            "patientID": sessao.get("patient_id"),
            "clinicalNote": texto_usuario  # Nota administrativa
        }
        
        logger.debug("Payload NOTE_ONLY preparado",
                    report_id=sessao.get("report_id"),
                    nota_length=len(texto_usuario))
        
        return payload
    
    def processar(self, state: GraphState) -> str:
        """
        Processa subgrafo operacional
        
        Diferente dos outros, este fluxo é DIRETO (sem confirmação)
        Envia NOTE_ONLY para updateClinicalData
        
        Returns:
            Mensagem para ser processada pelo fiscal
        """
        logger.info("Processando subgrafo operacional")
        
        # Adiciona à lista de fluxos executados
        state.adicionar_fluxo_executado("operacional")
        
        texto_usuario = state.entrada.get("texto_usuario", "")
        
        if not texto_usuario.strip():
            return "Nenhuma nota administrativa foi fornecida."
        
        # Prepara payload
        payload = self._preparar_payload_note_only(state)
        
        try:
            logger.info("Enviando nota operacional diretamente")
            
            # Chama Lambda diretamente (sem confirmação)
            result = self.http_client.update_clinical_data(
                self.lambda_update_clinical_url,
                payload
            )
            
            logger.info("Nota operacional enviada com sucesso")
            return f"Nota administrativa registrada: '{texto_usuario[:50]}{'...' if len(texto_usuario) > 50 else ''}'"
            
        except Exception as e:
            logger.error("Erro ao enviar nota operacional", error=str(e))
            return f"Erro ao registrar nota administrativa: {str(e)}"
