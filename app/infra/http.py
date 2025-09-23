"""
Cliente HTTP síncrono para chamadas às Lambdas AWS
"""
import requests
from typing import Dict, Any, Optional
import structlog

logger = structlog.get_logger(__name__)


class LambdaHttpClient:
    """Cliente HTTP para comunicação com Lambdas AWS"""
    
    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.session = requests.Session()
        # Headers padrão
        self.session.headers.update({
            'Content-Type': 'application/json',
            'User-Agent': 'WhatsAppOrchestrator/1.0'
        })
    
    def _make_request(self, method: str, url: str, **kwargs) -> Dict[str, Any]:
        """Faz requisição HTTP com tratamento de erros"""
        try:
            response = self.session.request(
                method=method,
                url=url,
                timeout=self.timeout,
                **kwargs
            )
            
            # Log da requisição
            logger.info("Requisição HTTP",
                       method=method,
                       url=url,
                       status_code=response.status_code,
                       response_time=response.elapsed.total_seconds())
            
            # Verifica status code
            response.raise_for_status()
            
            # Tenta fazer parse do JSON
            try:
                return response.json()
            except ValueError:
                # Se não for JSON válido, retorna texto
                return {"text": response.text, "status_code": response.status_code}
                
        except requests.exceptions.Timeout:
            logger.error("Timeout na requisição", method=method, url=url, timeout=self.timeout)
            raise Exception(f"Timeout na chamada para {url}")
        
        except requests.exceptions.ConnectionError:
            logger.error("Erro de conexão", method=method, url=url)
            raise Exception(f"Erro de conexão com {url}")
        
        except requests.exceptions.HTTPError as e:
            logger.error("Erro HTTP",
                        method=method,
                        url=url,
                        status_code=e.response.status_code,
                        response_text=e.response.text[:500])
            raise Exception(f"Erro HTTP {e.response.status_code}: {e.response.text[:200]}")
        
        except Exception as e:
            logger.error("Erro inesperado na requisição", method=method, url=url, error=str(e))
            raise Exception(f"Erro inesperado: {str(e)}")
    
    def get_schedule_started(self, url: str, phone_number: str) -> Dict[str, Any]:
        """Chama getScheduleStarted Lambda"""
        payload = {"phoneNumber": phone_number}
        
        logger.info("Chamando getScheduleStarted", phone_number=phone_number, url=url)
        
        result = self._make_request('POST', url, json=payload)
        
        # Debug: mostrar response completo
        logger.info("getScheduleStarted concluído",
                   phone_number=phone_number,
                   success=True,
                   has_schedule_id='scheduleID' in result,
                   response_keys=list(result.keys()),
                   schedule_id_value=result.get('scheduleID'))
        
        return result
    
    def update_work_schedule(self, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Chama updateWorkScheduleResponse Lambda"""
        logger.info("Chamando updateWorkScheduleResponse", 
                   schedule_id=payload.get('scheduleID'),
                   action=payload.get('action'))
        
        result = self._make_request('POST', url, json=payload)
        
        logger.info("updateWorkScheduleResponse concluído",
                   schedule_id=payload.get('scheduleID'),
                   success=True)
        
        return result
    
    def update_clinical_data(self, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Chama updateClinicalData Lambda"""
        logger.info("Chamando updateClinicalData",
                   report_id=payload.get('reportID'),
                   has_vitals=bool(payload.get('vitalSignsData')),
                   has_note=bool(payload.get('clinicalNote')),
                   has_symptoms=bool(payload.get('SymptomReport')))
        
        result = self._make_request('POST', url, json=payload)
        
        logger.info("updateClinicalData concluído",
                   report_id=payload.get('reportID'),
                   success=True)
        
        return result
    
    def update_report_summary(self, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Chama updatereportsummaryad Lambda"""
        logger.info("Chamando updatereportsummaryad",
                   report_id=payload.get('reportID'),
                   schedule_id=payload.get('scheduleID'))
        
        result = self._make_request('POST', url, json=payload)
        
        logger.info("updatereportsummaryad concluído",
                   report_id=payload.get('reportID'),
                   success=True)
        
        return result
