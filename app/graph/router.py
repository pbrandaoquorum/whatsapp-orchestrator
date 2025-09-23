"""
Router principal - Roteamento determinístico + LLM leve
Implementa toda a lógica de gates e despacho
"""
from typing import Dict, Any
import structlog

from app.graph.state import GraphState
from app.llm.classifier import IntentClassifier
from app.infra.http import LambdaHttpClient

logger = structlog.get_logger(__name__)


class MainRouter:
    """Router principal do sistema"""
    
    def __init__(self, 
                 intent_classifier: IntentClassifier,
                 http_client: LambdaHttpClient,
                 lambda_get_schedule_url: str):
        self.intent_classifier = intent_classifier
        self.http_client = http_client
        self.lambda_get_schedule_url = lambda_get_schedule_url
        logger.info("MainRouter inicializado")
    
    def _verificar_dados_sessao(self, state: GraphState) -> bool:
        """Verifica se os dados básicos da sessão estão presentes"""
        sessao = state.sessao
        return bool(
            sessao.get("schedule_id") and 
            sessao.get("report_id") and 
            sessao.get("patient_id") and
            sessao.get("caregiver_id")
        )
    
    def _chamar_get_schedule_started(self, state: GraphState) -> None:
        """Chama getScheduleStarted e preenche dados da sessão"""
        telefone = state.sessao.get("telefone")
        if not telefone:
            logger.error("Telefone não encontrado na sessão")
            raise Exception("Telefone é obrigatório para buscar dados da sessão")
        
        logger.info("Chamando getScheduleStarted", telefone=telefone)
        
        try:
            result = self.http_client.get_schedule_started(
                self.lambda_get_schedule_url, 
                telefone
            )
            
            # Preenche dados da sessão
            state.sessao.update({
                "schedule_id": result.get("scheduleID"),
                "report_id": result.get("reportID"),
                "patient_id": result.get("patientID"),
                "caregiver_id": result.get("caregiverID"),
                "data_relatorio": result.get("reportDate"),
                "turno_permitido": result.get("shiftAllow", True),
                "turno_iniciado": result.get("scheduleStarted", False),
                "empresa": result.get("caregiverCompany"),
                "cooperativa": result.get("caregiverCooperative")
            })
            
            # Debug: mostrar dados extraídos
            logger.info("Dados extraídos do getScheduleStarted",
                       schedule_id=state.sessao.get("schedule_id"),
                       report_id=state.sessao.get("report_id"),
                       patient_id=state.sessao.get("patient_id"),
                       caregiver_id=state.sessao.get("caregiver_id"),
                       turno_permitido=state.sessao.get("turno_permitido"),
                       turno_iniciado=state.sessao.get("turno_iniciado"))
            
            logger.info("Dados da sessão atualizados via getScheduleStarted",
                       schedule_id=state.sessao.get("schedule_id"),
                       report_id=state.sessao.get("report_id"),
                       turno_permitido=state.sessao.get("turno_permitido"))
            
        except Exception as e:
            logger.error("Erro ao chamar getScheduleStarted", telefone=telefone, error=str(e))
            # Em caso de erro, marca como não permitido para forçar fluxo auxiliar
            state.sessao["turno_permitido"] = False
            state.sessao["cancelado"] = True
            raise
    
    def _classificar_intencao(self, state: GraphState) -> str:
        """Classifica intenção usando LLM"""
        texto_usuario = state.entrada.get("texto_usuario", "")
        
        if not texto_usuario:
            logger.warning("Texto do usuário vazio, usando intenção auxiliar")
            return "auxiliar"
        
        intencao = self.intent_classifier.classificar_intencao(texto_usuario)
        state.roteador["intencao"] = intencao
        
        logger.info("Intenção classificada", 
                   texto=texto_usuario[:50],
                   intencao=intencao)
        
        return intencao
    
    def _aplicar_gates_deterministicos(self, state: GraphState, intencao: str) -> str:
        """
        Aplica gates determinísticos APÓS classificação
        Pode modificar a intenção baseado no estado
        """
        sessao = state.sessao
        
        # Gate 1: Se cancelado -> auxiliar
        if sessao.get("cancelado"):
            logger.info("Sessão cancelada, redirecionando para auxiliar")
            return "auxiliar"
        
        # Gate 2: Se turno não permitido -> auxiliar
        if not sessao.get("turno_permitido"):
            logger.info("Turno não permitido, redirecionando para auxiliar")
            return "auxiliar"
        
        # Gate 3: Se intenção é finalizar mas vitais incompletos -> clinico
        if intencao == "finalizar":
            vitais_completos = state.get_vitais_completos()
            if not vitais_completos:
                faltantes = state.get_vitais_faltantes()
                logger.info("Finalizar solicitado mas vitais incompletos",
                           faltantes=faltantes)
                
                # Configura retomada
                state.retomada = {
                    "fluxo": "finalizar",
                    "motivo": "precisa_vitais",
                    "faltantes": faltantes
                }
                
                return "clinico"
        
        # Se chegou até aqui, mantém intenção original
        return intencao
    
    def rotear(self, state: GraphState) -> str:
        """
        Executa roteamento completo
        
        Returns:
            Nome do próximo subgrafo a executar
        """
        logger.info("Iniciando roteamento", 
                   session_id=state.sessao.get("session_id"),
                   tem_retomada=state.tem_retomada())
        
        # 1. Se há confirmação pendente, vai direto para o subgrafo correto
        if state.tem_pendente():
            fluxo_pendente = state.pendente["fluxo"]
            logger.info("ROUTER: Confirmação pendente detectada", 
                       fluxo=fluxo_pendente,
                       session_id=state.sessao.get("session_id"))
            return fluxo_pendente
        
        # 2. Se há retomada, pula classificação e despacha direto
        if state.tem_retomada():
            fluxo_retomada = state.retomada["fluxo"]
            motivo = state.retomada.get("motivo", "")
            logger.info("Retomada detectada", fluxo=fluxo_retomada, motivo=motivo)
            
            # Limpa retomada após usar
            state.retomada = None
            return fluxo_retomada
        
        # 3. Verifica se precisa buscar dados da sessão
        if not self._verificar_dados_sessao(state):
            logger.info("Dados da sessão faltando, chamando getScheduleStarted")
            self._chamar_get_schedule_started(state)
        
        # 4. Classifica intenção via LLM
        intencao = self._classificar_intencao(state)
        
        # 5. Aplica gates determinísticos
        intencao_final = self._aplicar_gates_deterministicos(state, intencao)
        
        # 6. Log do resultado final
        if intencao != intencao_final:
            logger.info("Intenção modificada por gates",
                       intencao_original=intencao,
                       intencao_final=intencao_final)
        
        # 7. Atualiza estado
        state.roteador["intencao"] = intencao_final
        
        logger.info("Roteamento concluído",
                   session_id=state.sessao.get("session_id"),
                   intencao_final=intencao_final)
        
        return intencao_final
