"""
Configuração global para testes pytest
"""
import pytest
import os
from unittest.mock import patch, MagicMock

# Configurar variáveis de ambiente para testes
os.environ.update({
    "LAMBDA_GET_SCHEDULE": "https://test-lambda-get.example.com",
    "LAMBDA_UPDATE_SCHEDULE": "https://test-lambda-update.example.com", 
    "LAMBDA_UPDATE_CLINICAL": "https://test-lambda-clinical.example.com",
    "LAMBDA_UPDATE_SUMMARY": "https://test-lambda-summary.example.com",
    "REDIS_URL": "redis://localhost:6379/15",  # DB 15 para testes
    "PINECONE_API_KEY": "test-pinecone-key",
    "PINECONE_ENV": "test-env",
    "PINECONE_INDEX": "test-index",
    "GOOGLE_SHEETS_ID": "test-sheets-id",
    "OPENAI_API_KEY": "test-openai-key",
    "LOG_LEVEL": "WARNING"  # Reduzir logs durante testes
})


@pytest.fixture
def mock_redis():
    """Mock do cliente Redis para testes"""
    with patch('app.infra.redis_client.obter_cliente_redis') as mock:
        redis_mock = MagicMock()
        redis_mock.ping.return_value = True
        redis_mock.get.return_value = None
        redis_mock.set.return_value = True
        redis_mock.delete.return_value = 1
        redis_mock.exists.return_value = False
        mock.return_value = redis_mock
        yield redis_mock


@pytest.fixture
def mock_pinecone():
    """Mock do cliente Pinecone para testes"""
    with patch('app.rag.pinecone_client.obter_cliente_pinecone') as mock_client, \
         patch('app.rag.pinecone_client.obter_indice_pinecone') as mock_index, \
         patch('app.rag.pinecone_client.obter_modelo_embeddings') as mock_model:
        
        # Mock cliente
        client_mock = MagicMock()
        mock_client.return_value = client_mock
        
        # Mock índice
        index_mock = MagicMock()
        index_mock.query.return_value = MagicMock(matches=[])
        index_mock.upsert.return_value = None
        index_mock.describe_index_stats.return_value = MagicMock(
            total_vector_count=100,
            dimension=384,
            index_fullness=0.1
        )
        mock_index.return_value = index_mock
        
        # Mock modelo embeddings
        model_mock = MagicMock()
        model_mock.encode.return_value = [[0.1] * 384]  # Embedding fake
        mock_model.return_value = model_mock
        
        yield {
            'client': client_mock,
            'index': index_mock,
            'model': model_mock
        }


@pytest.fixture
def mock_sheets():
    """Mock do cliente Google Sheets para testes"""
    with patch('app.rag.sheets_sync.obter_cliente_sheets') as mock:
        sheets_mock = MagicMock()
        
        # Mock planilha
        planilha_mock = MagicMock()
        worksheet_mock = MagicMock()
        
        worksheet_mock.get_all_records.return_value = [
            {"sintoma": "dor de cabeça", "pontuacao": 3},
            {"sintoma": "febre", "pontuacao": 5},
            {"sintoma": "tosse", "pontuacao": 4}
        ]
        
        planilha_mock.worksheet.return_value = worksheet_mock
        planilha_mock.get_worksheet.return_value = worksheet_mock
        planilha_mock.worksheets.return_value = [
            MagicMock(title="Sintomas")
        ]
        
        sheets_mock.open_by_key.return_value = planilha_mock
        mock.return_value = sheets_mock
        
        yield sheets_mock


@pytest.fixture
def mock_lambdas():
    """Mock dos Lambdas AWS para testes"""
    with patch('httpx.AsyncClient') as mock_client:
        client_instance = MagicMock()
        
        # Mock responses padrão
        response_mock = MagicMock()
        response_mock.status_code = 200
        response_mock.json.return_value = {
            "statusCode": 200,
            "body": {
                "success": True,
                "message": "Test response"
            }
        }
        
        client_instance.__aenter__.return_value = client_instance
        client_instance.__aexit__.return_value = None
        client_instance.post.return_value = response_mock
        
        mock_client.return_value = client_instance
        
        yield client_instance


@pytest.fixture
def sample_graph_state():
    """Estado de exemplo para testes"""
    from app.graph.state import GraphState, CoreState, VitalsState, RouterState, AuxState
    
    return GraphState(
        core=CoreState(
            session_id="test_session_123",
            numero_telefone="+5511999999999",
            caregiver_id="caregiver_123",
            schedule_id="schedule_123",
            patient_id="patient_123",
            report_id="report_123",
            data_relatorio="2025-01-15",
            turno_permitido=True,
            turno_iniciado=False,
            cancelado=False
        ),
        vitais=VitalsState(
            processados={},
            faltantes=["PA", "FC", "FR", "Sat", "Temp"]
        ),
        router=RouterState(),
        aux=AuxState(),
        texto_usuario="",
        metadados={}
    )


@pytest.fixture
def sample_complete_vitals():
    """Sinais vitais completos para testes"""
    return {
        "PA": "120x80",
        "FC": 78,
        "FR": 18,
        "Sat": 97,
        "Temp": 36.5
    }


@pytest.fixture(autouse=True)
def mock_logging():
    """Mock do sistema de logging para reduzir output nos testes"""
    with patch('app.infra.logging.obter_logger') as mock:
        logger_mock = MagicMock()
        logger_mock.info.return_value = None
        logger_mock.warning.return_value = None
        logger_mock.error.return_value = None
        logger_mock.debug.return_value = None
        mock.return_value = logger_mock
        yield logger_mock


@pytest.fixture
def mock_openai():
    """Mock do OpenAI para testes de LLM"""
    with patch('langchain_openai.ChatOpenAI') as mock:
        llm_mock = MagicMock()
        
        # Mock response padrão
        response_mock = MagicMock()
        response_mock.content = '{"intent": "auxiliar", "confidence": 0.8, "rationale": "Teste"}'
        
        llm_mock.invoke.return_value = response_mock
        mock.return_value = llm_mock
        
        yield llm_mock


# Configurações globais do pytest
def pytest_configure(config):
    """Configuração global do pytest"""
    # Registrar marcadores customizados
    config.addinivalue_line(
        "markers", "integration: marca testes de integração"
    )
    config.addinivalue_line(
        "markers", "slow: marca testes lentos"
    )
    config.addinivalue_line(
        "markers", "external: marca testes que dependem de serviços externos"
    )
