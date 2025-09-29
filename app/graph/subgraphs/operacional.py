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
    
    def _preparar_payload_operacional(self, state: GraphState) -> Dict[str, Any]:
        """Prepara payload para nota operacional instantânea"""
        sessao = state.sessao
        nota_operacional = state.operacional.get("nota", "")
        
        payload = {
            "reportID": sessao.get("report_id"),
            "reportDate": sessao.get("data_relatorio"),
            "scheduleID": sessao.get("schedule_id"),
            "sessionID": sessao.get("session_id"),
            "caregiverIdentifier": sessao.get("caregiver_id"),
            "patientIdentifier": sessao.get("patient_id"),
            "clinicalNote": nota_operacional,
            "operationalNote": True  # Flag para identificar nota operacional
        }
        
        logger.debug("Payload operacional preparado",
                    report_id=sessao.get("report_id"),
                    nota_length=len(nota_operacional))
        
        return payload
    
    def processar(self, state: GraphState) -> str:
        """
        Processa subgrafo operacional
        
        Diferente dos outros, este fluxo é DIRETO (sem confirmação)
        Envia nota operacional instantânea para webhook n8n
        
        Returns:
            Código para ser processado pelo fiscal
        """
        logger.info("Processando subgrafo operacional")
        
        # Adiciona à lista de fluxos executados
        state.adicionar_fluxo_executado("operacional")
        
        nota_operacional = state.operacional.get("nota", "") or ""
        
        if not nota_operacional.strip():
            return "OPERATIONAL_NO_NOTE"
        
        # Prepara payload para webhook n8n
        payload = self._preparar_payload_operacional(state)
        
        try:
            logger.info("Enviando nota operacional instantânea para n8n")
            
            # URL do webhook n8n (mesmo usado no clínico)
            webhook_url = "https://primary-production-031c.up.railway.app/webhook/8f70cfe8-9c88-403d-8282-0d9bd7b4311d"
            
            # Chama webhook n8n diretamente (sem confirmação)
            result = self.http_client.post(webhook_url, payload)
            
            # Limpa dados operacionais após envio bem-sucedido
            state.operacional = {
                "nota": None,
                "timestamp": None,
                "tipo": None
            }
            
            logger.info("Nota operacional enviada para n8n com sucesso")
            return "OPERATIONAL_NOTE_SENT"
            
        except Exception as e:
            logger.error("Erro ao enviar nota operacional para n8n", error=str(e))
            return "OPERATIONAL_ERROR"
