"""
Subgrafo de Escala
Gerencia confirmação/cancelamento de presença
"""
from typing import Dict, Any
import structlog

from app.graph.state import GraphState
from app.infra.http import LambdaHttpClient

logger = structlog.get_logger(__name__)



class EscalaSubgraph:
    """Subgrafo para gestão de escala/presença"""
    
    def __init__(self, 
                 http_client: LambdaHttpClient,
                 lambda_update_schedule_url: str,
                 lambda_get_schedule_url: str):
        self.http_client = http_client
        self.lambda_update_schedule_url = lambda_update_schedule_url
        self.lambda_get_schedule_url = lambda_get_schedule_url
        logger.info("EscalaSubgraph inicializado")
    
    def _identificar_acao_escala(self, texto_usuario: str) -> str:
        """
        Identifica ação relacionada à escala via LLM (sem keywords)
        Returns: 'confirmar', 'cancelar', 'consultar'
        """
        try:
            # Usar LLM para classificar ação
            from app.llm.confirmation_classifier import ConfirmationClassifier
            import os
            
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                logger.warning("OPENAI_API_KEY não encontrada, usando fallback")
                return 'consultar'
            
            classifier = ConfirmationClassifier(
                api_key=api_key,
                model=os.getenv("INTENT_MODEL", "gpt-4o-mini")
            )
            
            return classifier.classificar_acao_escala(texto_usuario)
            
        except Exception as e:
            logger.error("Erro ao classificar ação de escala via LLM", error=str(e))
            return 'consultar'
    
    def _preparar_confirmacao(self, state: GraphState, acao: str) -> str:
        """
        Prepara confirmação para ação de escala
        Returns: mensagem para o usuário
        """
        sessao = state.sessao
        schedule_id = sessao.get("schedule_id")
        
        if not schedule_id:
            return "Erro: Dados da escala não encontrados. Tente novamente."
        
        # CORREÇÃO: Verifica se plantão já está confirmado
        response_status = sessao.get("response", "").lower()
        if response_status == "confirmado":
            # Plantão já confirmado - permite consulta
            return self._consultar_escala(state)
        
        # Plantão não confirmado - sempre pede confirmação (independente da ação)
        payload = {
            "scheduleID": schedule_id,
            "responseValue": "confirmado",
            "caregiverID": sessao.get("caregiver_id"),
            "phoneNumber": sessao.get("telefone")
        }
        mensagem = f"Confirma sua presença no plantão?"
        
        # Salva no estado pendente
        state.pendente = {
            "fluxo": "escala",
            "acao": "confirmar",  # Sempre confirmar quando não confirmado
            "payload": payload
        }
        
        logger.info("Confirmação de presença preparada",
                   schedule_id=schedule_id,
                   response_status=response_status)
        
        return mensagem
    
    def _consultar_escala(self, state: GraphState) -> str:
        """Consulta informações da escala atual"""
        try:
            telefone = state.sessao.get("telefone")
            result = self.http_client.get_schedule_started(
                self.lambda_get_schedule_url,
                telefone
            )
            
            # Atualiza dados da sessão
            state.sessao.update({
                "schedule_id": result.get("scheduleID"),
                "turno_permitido": result.get("shiftAllow", True),
                "turno_iniciado": result.get("scheduleStarted", False),
                "empresa": result.get("company"),
                "data_relatorio": result.get("reportDate")
            })
            
            # Monta resposta informativa
            if result.get("shiftAllow"):
                if result.get("scheduleStarted"):
                    return f"Plantão já iniciado. Empresa: {result.get('company', 'N/A')}"
                else:
                    return f"Plantão agendado. Empresa: {result.get('company', 'N/A')}. Confirme sua presença quando chegar."
            else:
                return "Nenhum plantão encontrado para hoje ou plantão não permitido."
                
        except Exception as e:
            logger.error("Erro ao consultar escala", error=str(e))
            return "Erro ao consultar dados da escala. Tente novamente."
    
    def _executar_acao_confirmada(self, state: GraphState) -> str:
        """Executa ação de escala após confirmação"""
        pendente = state.pendente
        if not pendente or pendente.get("fluxo") != "escala":
            return "Erro: Nenhuma ação de escala pendente."
        
        acao = pendente.get("acao")
        payload = pendente.get("payload")
        
        try:
            logger.info("Executando ação de escala confirmada", acao=acao)
            
            # Chama Lambda
            result = self.http_client.update_work_schedule(
                self.lambda_update_schedule_url,
                payload
            )
            
            # Limpa pendente
            state.limpar_pendente()
            
            # Re-bootstrap após mudança na escala
            try:
                telefone = state.sessao.get("telefone")
                bootstrap_result = self.http_client.get_schedule_started(
                    self.lambda_get_schedule_url,
                    telefone
                )
                state.sessao.update({
                    "schedule_id": bootstrap_result.get("scheduleID"),
                    "turno_permitido": bootstrap_result.get("turnoPermitido", True),
                    "turno_iniciado": bootstrap_result.get("turnoIniciado", False)
                })
            except Exception as e:
                logger.warning("Erro no re-bootstrap após ação de escala", error=str(e))
            
            # Retorna mensagem de sucesso
            if acao == 'confirmar':
                return "Presença confirmada com sucesso! O que deseja fazer agora?"
            elif acao == 'cancelar':
                return "Plantão cancelado com sucesso."
            else:
                return "Ação executada com sucesso."
                
        except Exception as e:
            logger.error("Erro ao executar ação de escala", acao=acao, error=str(e))
            state.limpar_pendente()
            return f"Erro ao {acao} plantão: {str(e)}. Tente novamente."
    
    def processar(self, state: GraphState) -> str:
        """
        Processa subgrafo de escala
        
        Returns:
            Mensagem para ser processada pelo fiscal
        """
        logger.info("Processando subgrafo de escala")
        
        # Adiciona à lista de fluxos executados
        state.adicionar_fluxo_executado("escala")
        
        texto_usuario = state.entrada.get("texto_usuario", "")
        
        # Verifica se é resposta de confirmação
        if state.tem_pendente() and state.pendente.get("fluxo") == "escala":
            try:
                # Usar LLM para classificar confirmação
                from app.llm.confirmation_classifier import ConfirmationClassifier
                import os
                
                api_key = os.getenv("OPENAI_API_KEY")
                if api_key:
                    classifier = ConfirmationClassifier(
                        api_key=api_key,
                        model=os.getenv("INTENT_MODEL", "gpt-4o-mini")
                    )
                    
                    confirmacao = classifier.classificar_confirmacao(texto_usuario)
                    
                    if confirmacao == "sim":
                        return self._executar_acao_confirmada(state)
                    elif confirmacao == "nao":
                        state.limpar_pendente()
                        return "Ação cancelada."
                    else:
                        return "Responda 'sim' para confirmar ou 'não' para cancelar."
                else:
                    # Fallback se não tiver API key
                    return "Responda 'sim' para confirmar ou 'não' para cancelar."
                    
            except Exception as e:
                logger.error("Erro ao classificar confirmação via LLM", error=str(e))
                return "Responda 'sim' para confirmar ou 'não' para cancelar."
        
        # Identifica ação e prepara confirmação
        acao = self._identificar_acao_escala(state.entrada.get("texto_usuario", ""))
        return self._preparar_confirmacao(state, acao)
