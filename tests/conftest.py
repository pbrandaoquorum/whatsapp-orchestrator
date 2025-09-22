"""
Configurações compartilhadas dos testes
"""
import pytest
from unittest.mock import Mock, MagicMock
import os

from app.graph.state import GraphState
from app.llm.classifier import IntentClassifier
from app.llm.extractor import ClinicalExtractor
from app.infra.http import LambdaHttpClient


@pytest.fixture
def mock_openai_api_key():
    """Mock da API key do OpenAI"""
    return "sk-test-key"


@pytest.fixture
def sample_state():
    """Estado de exemplo para testes"""
    state = GraphState()
    state.sessao.update({
        "session_id": "5511999999999",
        "telefone": "5511999999999",
        "caregiver_id": "caregiver123",
        "schedule_id": "schedule123",
        "patient_id": "patient123",
        "report_id": "report123",
        "data_relatorio": "2024-01-15",
        "turno_permitido": True,
        "turno_iniciado": False,
        "empresa": "Empresa Teste",
        "cooperativa": "Cooperativa Teste",
        "cancelado": False
    })
    state.entrada.update({
        "texto_usuario": "PA 120x80 FC 75",
        "meta": {}
    })
    return state


@pytest.fixture
def mock_intent_classifier(mock_openai_api_key):
    """Mock do classificador de intenção"""
    classifier = Mock(spec=IntentClassifier)
    classifier.classificar_intencao = Mock(return_value="clinico")
    return classifier


@pytest.fixture
def mock_clinical_extractor(mock_openai_api_key):
    """Mock do extrator clínico"""
    extractor = Mock(spec=ClinicalExtractor)
    extractor.extrair_json = Mock(return_value={
        "vitals": {
            "PA": "120x80",
            "FC": 75,
            "FR": None,
            "Sat": None,
            "Temp": None
        },
        "nota": None,
        "rawMentions": {"PA": "120x80", "FC": "75"},
        "warnings": []
    })
    return extractor


@pytest.fixture
def mock_http_client():
    """Mock do cliente HTTP"""
    client = Mock(spec=LambdaHttpClient)
    
    # Mock getScheduleStarted
    client.get_schedule_started = Mock(return_value={
        "scheduleID": "schedule123",
        "reportID": "report123",
        "patientID": "patient123",
        "caregiverID": "caregiver123",
        "reportDate": "2024-01-15",
        "turnoPermitido": True,
        "turnoIniciado": False,
        "empresa": "Empresa Teste"
    })
    
    # Mock updateClinicalData
    client.update_clinical_data = Mock(return_value={
        "message": "Dados clínicos processados com sucesso",
        "scenario": "VITAL_SIGNS_ONLY"
    })
    
    # Mock updateWorkSchedule
    client.update_work_schedule = Mock(return_value={
        "message": "Escala atualizada com sucesso"
    })
    
    # Mock updateReportSummary
    client.update_report_summary = Mock(return_value={
        "message": "Plantão finalizado com sucesso"
    })
    
    return client


@pytest.fixture
def mock_dynamo_manager():
    """Mock do gerenciador DynamoDB"""
    manager = Mock()
    
    def mock_carregar_estado(session_id):
        state = GraphState()
        state.sessao["session_id"] = session_id
        state.sessao["telefone"] = session_id
        return state
    
    manager.carregar_estado = Mock(side_effect=mock_carregar_estado)
    manager.salvar_estado = Mock()
    manager.verificar_tabela = Mock(return_value=True)
    
    return manager


@pytest.fixture
def mock_rag_system():
    """Mock do sistema RAG"""
    rag = Mock()
    rag.processar_nota_clinica = Mock(return_value=[])
    return rag


# Fixtures para variáveis de ambiente de teste
@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch):
    """Configura variáveis de ambiente para testes"""
    test_env = {
        "OPENAI_API_KEY": "sk-test-key",
        "LAMBDA_GET_SCHEDULE": "https://test.amazonaws.com/getSchedule",
        "LAMBDA_UPDATE_CLINICAL": "https://test.amazonaws.com/updateClinical",
        "LAMBDA_UPDATE_SCHEDULE": "https://test.amazonaws.com/updateSchedule",
        "LAMBDA_UPDATE_SUMMARY": "https://test.amazonaws.com/updateSummary",
        "DYNAMODB_TABLE_CONVERSAS": "TestConversas",
        "AWS_REGION": "us-east-1",
        "LOG_LEVEL": "ERROR"  # Reduz logs durante testes
    }
    
    for key, value in test_env.items():
        monkeypatch.setenv(key, value)
