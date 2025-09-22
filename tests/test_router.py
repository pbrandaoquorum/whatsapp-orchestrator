"""
Testes do router principal
"""
import pytest
from unittest.mock import Mock, patch

from app.graph.router import MainRouter
from app.graph.state import GraphState


class TestMainRouter:
    """Testes do router principal"""
    
    def test_classificacao_intencao_clinico(self, mock_intent_classifier, mock_http_client):
        """Testa classificação de intenção clínica"""
        router = MainRouter(
            intent_classifier=mock_intent_classifier,
            http_client=mock_http_client,
            lambda_get_schedule_url="https://test.com/getSchedule"
        )
        
        state = GraphState()
        state.entrada["texto_usuario"] = "PA 120x80 FC 75"
        state.sessao.update({
            "telefone": "5511999999999",
            "schedule_id": "schedule123",
            "report_id": "report123",
            "patient_id": "patient123",
            "caregiver_id": "caregiver123",
            "turno_permitido": True
        })
        
        # Configura mock
        mock_intent_classifier.classificar_intencao.return_value = "clinico"
        
        # Executa
        resultado = router.rotear(state)
        
        # Verifica
        assert resultado == "clinico"
        assert state.roteador["intencao"] == "clinico"
        mock_intent_classifier.classificar_intencao.assert_called_once_with("PA 120x80 FC 75")
    
    def test_classificacao_intencao_escala(self, mock_intent_classifier, mock_http_client):
        """Testa classificação de intenção de escala"""
        router = MainRouter(
            intent_classifier=mock_intent_classifier,
            http_client=mock_http_client,
            lambda_get_schedule_url="https://test.com/getSchedule"
        )
        
        state = GraphState()
        state.entrada["texto_usuario"] = "confirmo presença"
        state.sessao.update({
            "telefone": "5511999999999",
            "schedule_id": "schedule123",
            "turno_permitido": True
        })
        
        # Configura mock
        mock_intent_classifier.classificar_intencao.return_value = "escala"
        
        # Executa
        resultado = router.rotear(state)
        
        # Verifica
        assert resultado == "escala"
        assert state.roteador["intencao"] == "escala"
    
    def test_gate_cancelado_redireciona_auxiliar(self, mock_intent_classifier, mock_http_client):
        """Testa gate determinístico: cancelado -> auxiliar"""
        router = MainRouter(
            intent_classifier=mock_intent_classifier,
            http_client=mock_http_client,
            lambda_get_schedule_url="https://test.com/getSchedule"
        )
        
        state = GraphState()
        state.entrada["texto_usuario"] = "PA 120x80"
        state.sessao.update({
            "telefone": "5511999999999",
            "schedule_id": "schedule123",
            "cancelado": True  # Cancelado = True
        })
        
        # Configura mock
        mock_intent_classifier.classificar_intencao.return_value = "clinico"
        
        # Executa
        resultado = router.rotear(state)
        
        # Verifica que foi redirecionado para auxiliar
        assert resultado == "auxiliar"
        assert state.roteador["intencao"] == "auxiliar"
    
    def test_gate_turno_nao_permitido_redireciona_auxiliar(self, mock_intent_classifier, mock_http_client):
        """Testa gate determinístico: turno não permitido -> auxiliar"""
        router = MainRouter(
            intent_classifier=mock_intent_classifier,
            http_client=mock_http_client,
            lambda_get_schedule_url="https://test.com/getSchedule"
        )
        
        state = GraphState()
        state.entrada["texto_usuario"] = "PA 120x80"
        state.sessao.update({
            "telefone": "5511999999999",
            "schedule_id": "schedule123",
            "turno_permitido": False  # Turno não permitido
        })
        
        # Configura mock
        mock_intent_classifier.classificar_intencao.return_value = "clinico"
        
        # Executa
        resultado = router.rotear(state)
        
        # Verifica que foi redirecionado para auxiliar
        assert resultado == "auxiliar"
        assert state.roteador["intencao"] == "auxiliar"
    
    def test_gate_finalizar_sem_vitais_redireciona_clinico(self, mock_intent_classifier, mock_http_client):
        """Testa gate determinístico: finalizar sem vitais -> clinico"""
        router = MainRouter(
            intent_classifier=mock_intent_classifier,
            http_client=mock_http_client,
            lambda_get_schedule_url="https://test.com/getSchedule"
        )
        
        state = GraphState()
        state.entrada["texto_usuario"] = "finalizar plantão"
        state.sessao.update({
            "telefone": "5511999999999",
            "schedule_id": "schedule123",
            "turno_permitido": True
        })
        # Vitais vazios (não completos)
        state.clinico["vitais"] = {"PA": None, "FC": None, "FR": None, "Sat": None, "Temp": None}
        
        # Configura mock
        mock_intent_classifier.classificar_intencao.return_value = "finalizar"
        
        # Executa
        resultado = router.rotear(state)
        
        # Verifica que foi redirecionado para clinico
        assert resultado == "clinico"
        assert state.retomada is not None
        assert state.retomada["fluxo"] == "finalizar"
        assert state.retomada["motivo"] == "precisa_vitais"
    
    def test_retomada_pula_classificacao(self, mock_intent_classifier, mock_http_client):
        """Testa que retomada pula classificação LLM"""
        router = MainRouter(
            intent_classifier=mock_intent_classifier,
            http_client=mock_http_client,
            lambda_get_schedule_url="https://test.com/getSchedule"
        )
        
        state = GraphState()
        state.entrada["texto_usuario"] = "PA 120x80"
        state.sessao.update({
            "telefone": "5511999999999",
            "schedule_id": "schedule123",
            "turno_permitido": True
        })
        # Define retomada
        state.retomada = {"fluxo": "finalizar", "motivo": "precisa_vitais"}
        
        # Executa
        resultado = router.rotear(state)
        
        # Verifica que foi direto para finalizar
        assert resultado == "finalizar"
        # Verifica que LLM não foi chamado
        mock_intent_classifier.classificar_intencao.assert_not_called()
        # Verifica que retomada foi limpa
        assert state.retomada is None
    
    def test_chama_get_schedule_started_quando_dados_faltando(self, mock_intent_classifier, mock_http_client):
        """Testa chamada para getScheduleStarted quando dados da sessão estão faltando"""
        router = MainRouter(
            intent_classifier=mock_intent_classifier,
            http_client=mock_http_client,
            lambda_get_schedule_url="https://test.com/getSchedule"
        )
        
        state = GraphState()
        state.entrada["texto_usuario"] = "PA 120x80"
        state.sessao.update({
            "telefone": "5511999999999"
            # schedule_id, report_id, etc. estão faltando
        })
        
        # Configura mocks
        mock_intent_classifier.classificar_intencao.return_value = "clinico"
        mock_http_client.get_schedule_started.return_value = {
            "scheduleID": "schedule123",
            "reportID": "report123",
            "patientID": "patient123",
            "caregiverID": "caregiver123",
            "reportDate": "2024-01-15",
            "turnoPermitido": True,
            "turnoIniciado": False,
            "empresa": "Empresa Teste"
        }
        
        # Executa
        resultado = router.rotear(state)
        
        # Verifica que getScheduleStarted foi chamado
        mock_http_client.get_schedule_started.assert_called_once_with(
            "https://test.com/getSchedule",
            "5511999999999"
        )
        
        # Verifica que dados foram atualizados
        assert state.sessao["schedule_id"] == "schedule123"
        assert state.sessao["report_id"] == "report123"
        assert state.sessao["turno_permitido"] == True
        
        # Verifica resultado
        assert resultado == "clinico"
