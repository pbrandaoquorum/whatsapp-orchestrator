"""
Testes do Two-Phase Commit (confirmações)
"""
import pytest
from unittest.mock import Mock

from app.graph.subgraphs.escala import EscalaSubgraph
from app.graph.subgraphs.clinico import ClinicoSubgraph
from app.graph.subgraphs.finalizar import FinalizarSubgraph
from app.graph.state import GraphState


class TestTwoPhaseCommit:
    """Testes do sistema de confirmação (Two-Phase Commit)"""
    
    def test_escala_confirmar_prepara_pendente(self, mock_http_client):
        """Testa que confirmação de escala prepara estado pendente"""
        subgraph = EscalaSubgraph(
            http_client=mock_http_client,
            lambda_update_schedule_url="https://test.com/updateSchedule",
            lambda_get_schedule_url="https://test.com/getSchedule"
        )
        
        state = GraphState()
        state.entrada["texto_usuario"] = "confirmo presença"
        state.sessao.update({
            "schedule_id": "schedule123",
            "caregiver_id": "caregiver123",
            "telefone": "5511999999999"
        })
        
        # Executa
        resultado = subgraph.processar(state)
        
        # Verifica que estado pendente foi criado
        assert state.tem_pendente()
        assert state.pendente["fluxo"] == "escala"
        assert state.pendente["acao"] == "confirmar"
        assert state.pendente["payload"]["action"] == "confirm"
        
        # Verifica mensagem de confirmação
        assert "Confirma sua presença" in resultado
    
    def test_escala_sim_executa_acao_pendente(self, mock_http_client):
        """Testa que resposta 'sim' executa ação pendente de escala"""
        subgraph = EscalaSubgraph(
            http_client=mock_http_client,
            lambda_update_schedule_url="https://test.com/updateSchedule",
            lambda_get_schedule_url="https://test.com/getSchedule"
        )
        
        state = GraphState()
        state.entrada["texto_usuario"] = "sim"
        
        # Configura estado pendente
        state.pendente = {
            "fluxo": "escala",
            "acao": "confirmar",
            "payload": {
                "scheduleID": "schedule123",
                "action": "confirm"
            }
        }
        
        # Configura mocks
        mock_http_client.update_work_schedule.return_value = {"status": "success"}
        mock_http_client.get_schedule_started.return_value = {
            "scheduleID": "schedule123",
            "turnoPermitido": True,
            "turnoIniciado": True
        }
        
        # Executa
        resultado = subgraph.processar(state)
        
        # Verifica que Lambda foi chamado
        mock_http_client.update_work_schedule.assert_called_once()
        
        # Verifica que pendente foi limpo
        assert not state.tem_pendente()
        
        # Verifica resposta de sucesso
        assert "confirmada com sucesso" in resultado
    
    def test_escala_nao_cancela_acao_pendente(self, mock_http_client):
        """Testa que resposta 'não' cancela ação pendente de escala"""
        subgraph = EscalaSubgraph(
            http_client=mock_http_client,
            lambda_update_schedule_url="https://test.com/updateSchedule",
            lambda_get_schedule_url="https://test.com/getSchedule"
        )
        
        state = GraphState()
        state.entrada["texto_usuario"] = "não"
        
        # Configura estado pendente
        state.pendente = {
            "fluxo": "escala",
            "acao": "confirmar",
            "payload": {"scheduleID": "schedule123"}
        }
        
        # Executa
        resultado = subgraph.processar(state)
        
        # Verifica que Lambda NÃO foi chamado
        mock_http_client.update_work_schedule.assert_not_called()
        
        # Verifica que pendente foi limpo
        assert not state.tem_pendente()
        
        # Verifica resposta de cancelamento
        assert "cancelada" in resultado
    
    def test_finalizar_prepara_confirmacao(self, mock_http_client):
        """Testa que finalizar prepara confirmação quando vitais completos"""
        subgraph = FinalizarSubgraph(
            http_client=mock_http_client,
            lambda_update_summary_url="https://test.com/updateSummary"
        )
        
        state = GraphState()
        state.entrada["texto_usuario"] = "finalizar plantão"
        state.sessao.update({
            "report_id": "report123",
            "schedule_id": "schedule123"
        })
        
        # Configura vitais completos
        state.clinico["vitais"] = {
            "PA": "120x80",
            "FC": 75,
            "FR": 18,
            "Sat": 97,
            "Temp": 36.5
        }
        
        # Executa
        resultado = subgraph.processar(state)
        
        # Verifica que preparou confirmação
        assert state.tem_pendente()
        assert state.pendente["fluxo"] == "finalizar"
        assert "Confirma a finalização" in resultado
    
    def test_finalizar_vitais_incompletos_solicita_vitais(self, mock_http_client):
        """Testa que finalizar com vitais incompletos solicita vitais faltantes"""
        subgraph = FinalizarSubgraph(
            http_client=mock_http_client,
            lambda_update_summary_url="https://test.com/updateSummary"
        )
        
        state = GraphState()
        state.entrada["texto_usuario"] = "finalizar plantão"
        
        # Configura vitais incompletos
        state.clinico["vitais"] = {
            "PA": "120x80",
            "FC": 75,
            "FR": None,  # Faltante
            "Sat": None,  # Faltante
            "Temp": 36.5
        }
        
        # Executa
        resultado = subgraph.processar(state)
        
        # Verifica que configurou retomada
        assert state.tem_retomada()
        assert state.retomada["fluxo"] == "finalizar"
        assert state.retomada["motivo"] == "precisa_vitais"
        assert "FR" in state.retomada["faltantes"]
        assert "Sat" in state.retomada["faltantes"]
        
        # Verifica mensagem solicitando vitais
        assert "FR" in resultado
        assert "Sat" in resultado
        assert "Envie-os agora" in resultado
    
    def test_finalizar_sim_executa_finalizacao(self, mock_http_client):
        """Testa que confirmação 'sim' executa finalização"""
        subgraph = FinalizarSubgraph(
            http_client=mock_http_client,
            lambda_update_summary_url="https://test.com/updateSummary"
        )
        
        state = GraphState()
        state.entrada["texto_usuario"] = "sim"
        
        # Configura estado pendente
        state.pendente = {
            "fluxo": "finalizar",
            "payload": {
                "reportID": "report123",
                "action": "finalize"
            }
        }
        
        # Configura mock
        mock_http_client.update_report_summary.return_value = {"status": "success"}
        
        # Executa
        resultado = subgraph.processar(state)
        
        # Verifica que Lambda foi chamado
        mock_http_client.update_report_summary.assert_called_once()
        
        # Verifica que pendente foi limpo
        assert not state.tem_pendente()
        
        # Verifica resposta de sucesso
        assert "finalizado com sucesso" in resultado
        assert "Obrigado" in resultado
    
    def test_operacional_nao_tem_confirmacao(self, mock_http_client):
        """Testa que operacional NÃO tem confirmação (direto)"""
        from app.graph.subgraphs.operacional import OperacionalSubgraph
        
        subgraph = OperacionalSubgraph(
            http_client=mock_http_client,
            lambda_update_clinical_url="https://test.com/updateClinical"
        )
        
        state = GraphState()
        state.entrada["texto_usuario"] = "Paciente dormindo tranquilo"
        state.sessao.update({
            "report_id": "report123",
            "data_relatorio": "2024-01-15"
        })
        
        # Configura mock
        mock_http_client.update_clinical_data.return_value = {"status": "success"}
        
        # Executa
        resultado = subgraph.processar(state)
        
        # Verifica que Lambda foi chamado DIRETAMENTE (sem confirmação)
        mock_http_client.update_clinical_data.assert_called_once()
        
        # Verifica que NÃO criou estado pendente
        assert not state.tem_pendente()
        
        # Verifica resposta direta
        assert "registrada" in resultado
    
    def test_resposta_invalida_para_confirmacao(self, mock_http_client):
        """Testa resposta inválida para confirmação"""
        subgraph = EscalaSubgraph(
            http_client=mock_http_client,
            lambda_update_schedule_url="https://test.com/updateSchedule",
            lambda_get_schedule_url="https://test.com/getSchedule"
        )
        
        state = GraphState()
        state.entrada["texto_usuario"] = "talvez"  # Resposta inválida
        
        # Configura estado pendente
        state.pendente = {
            "fluxo": "escala",
            "acao": "confirmar",
            "payload": {"scheduleID": "schedule123"}
        }
        
        # Executa
        resultado = subgraph.processar(state)
        
        # Verifica que Lambda NÃO foi chamado
        mock_http_client.update_work_schedule.assert_not_called()
        
        # Verifica que pendente permanece
        assert state.tem_pendente()
        
        # Verifica mensagem de orientação
        assert "sim" in resultado
        assert "não" in resultado
