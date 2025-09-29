"""
Dependências da API - Configuração e inicialização de componentes
"""
import os
from functools import lru_cache
from dotenv import load_dotenv
import structlog

from app.infra.dynamo_state import DynamoStateManager
from app.infra.http import LambdaHttpClient
from app.infra.logging import configure_logging
from app.llm.classifiers import IntentClassifier, OperationalNoteClassifier
from app.llm.extractors import ClinicalExtractor
# RAG desabilitado - processamento via webhook n8n
from app.graph.router import MainRouter
from app.graph.fiscal import FiscalProcessor
from app.graph.subgraphs.escala import EscalaSubgraph
from app.graph.subgraphs.clinico import ClinicoSubgraph
from app.graph.subgraphs.operacional import OperacionalSubgraph
from app.graph.subgraphs.finalizar import FinalizarSubgraph
from app.graph.subgraphs.auxiliar import AuxiliarSubgraph

# Carrega variáveis de ambiente
load_dotenv()

logger = structlog.get_logger(__name__)


class Settings:
    """Configurações da aplicação"""
    
    def __init__(self):
        # AWS
        self.aws_region = os.getenv("AWS_REGION", "sa-east-1")
        self.aws_access_key_id = os.getenv("AWS_ACCESS_KEY_ID")
        self.aws_secret_access_key = os.getenv("AWS_SECRET_ACCESS_KEY")
        
        # Lambda URLs
        self.lambda_get_schedule = os.getenv("LAMBDA_GET_SCHEDULE")
        self.lambda_update_schedule = os.getenv("LAMBDA_UPDATE_SCHEDULE")
        self.lambda_update_clinical = os.getenv("LAMBDA_UPDATE_CLINICAL")
        self.lambda_update_summary = os.getenv("LAMBDA_UPDATE_SUMMARY")
        self.lambda_get_note_report = os.getenv("LAMBDA_GET_NOTE_REPORT")
        
        # Pinecone
        self.pinecone_api_key = os.getenv("PINECONE_API_KEY")
        self.pinecone_environment = os.getenv("PINECONE_ENVIRONMENT")
        self.pinecone_index = os.getenv("PINECONE_INDEX")
        
        # Google Sheets
        self.google_sheets_id = os.getenv("GOOGLE_SHEETS_ID")
        self.google_credentials_path = os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials/google-credentials.json")
        
        # OpenAI
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.intent_model = os.getenv("INTENT_MODEL", "gpt-4o-mini")
        self.extractor_model = os.getenv("EXTRACTOR_MODEL", "gpt-4o-mini")
        
        # DynamoDB
        self.dynamodb_table_conversas = os.getenv("DYNAMODB_TABLE_CONVERSAS", "ConversationStates")
        
        # Logging
        self.log_level = os.getenv("LOG_LEVEL", "INFO")
        
        # Validações
        self._validate_required_settings()
    
    def _validate_required_settings(self):
        """Valida configurações obrigatórias"""
        required_settings = [
            ("OPENAI_API_KEY", self.openai_api_key),
            ("LAMBDA_GET_SCHEDULE", self.lambda_get_schedule),
            ("LAMBDA_UPDATE_CLINICAL", self.lambda_update_clinical),
        ]
        
        missing = []
        for name, value in required_settings:
            if not value:
                missing.append(name)
        
        if missing:
            raise ValueError(f"Variáveis de ambiente obrigatórias não configuradas: {', '.join(missing)}")


@lru_cache()
def get_settings() -> Settings:
    """Retorna configurações (cached)"""
    return Settings()


# Componentes globais (inicializados uma vez)
_components = {}


def get_dynamo_state_manager() -> DynamoStateManager:
    """Retorna gerenciador de estado DynamoDB"""
    if "dynamo_state_manager" not in _components:
        settings = get_settings()
        _components["dynamo_state_manager"] = DynamoStateManager(
            table_name=settings.dynamodb_table_conversas,
            aws_region=settings.aws_region
        )
    return _components["dynamo_state_manager"]


def get_http_client() -> LambdaHttpClient:
    """Retorna cliente HTTP"""
    if "http_client" not in _components:
        _components["http_client"] = LambdaHttpClient(timeout=30)
    return _components["http_client"]


def get_intent_classifier() -> IntentClassifier:
    """Retorna classificador de intenção"""
    if "intent_classifier" not in _components:
        settings = get_settings()
        _components["intent_classifier"] = IntentClassifier(
            api_key=settings.openai_api_key,
            model=settings.intent_model
        )
    return _components["intent_classifier"]


def get_clinical_extractor() -> ClinicalExtractor:
    """Retorna extrator clínico"""
    if "clinical_extractor" not in _components:
        settings = get_settings()
        _components["clinical_extractor"] = ClinicalExtractor(
            api_key=settings.openai_api_key,
            model=settings.extractor_model
        )
    return _components["clinical_extractor"]


def get_rag_system():
    """Retorna sistema RAG (mock por enquanto)"""
    if "rag_system" not in _components:
        logger.warning("Usando mock do RAG para demonstração")
        # Mock do RAG que simula o comportamento
        class MockRAGSystem:
            def processar_nota_clinica(self, nota: str):
                # Simula identificação de sintomas baseado na nota
                sintomas_mock = []
                if nota and len(nota.strip()) > 0:
                    # Simula alguns sintomas baseados em palavras-chave
                    if any(word in nota.lower() for word in ['tosse', 'tossir']):
                        sintomas_mock.append({
                            "symptomDefinition": "Tosse seca",
                            "altNotepadMain": nota[:100],
                            "symptomCategory": "Respiratório",
                            "symptomSubCategory": "Tosse",
                            "descricaoComparada": "Identificado via mock RAG",
                            "coeficienteSimilaridade": 0.85
                        })
                    if any(word in nota.lower() for word in ['dor', 'dolorido']):
                        sintomas_mock.append({
                            "symptomDefinition": "Dor generalizada",
                            "altNotepadMain": nota[:100],
                            "symptomCategory": "Dor",
                            "symptomSubCategory": "Generalizada",
                            "descricaoComparada": "Identificado via mock RAG",
                            "coeficienteSimilaridade": 0.75
                        })
                return sintomas_mock
        _components["rag_system"] = MockRAGSystem()
    return _components["rag_system"]


def get_operational_classifier() -> OperationalNoteClassifier:
    """Retorna classificador operacional"""
    if "operational_classifier" not in _components:
        settings = get_settings()
        _components["operational_classifier"] = OperationalNoteClassifier(
            api_key=settings.openai_api_key
        )
    return _components["operational_classifier"]


def get_main_router() -> MainRouter:
    """Retorna router principal"""
    if "main_router" not in _components:
        settings = get_settings()
        _components["main_router"] = MainRouter(
            intent_classifier=get_intent_classifier(),
            operational_classifier=get_operational_classifier(),
            http_client=get_http_client(),
            lambda_get_schedule_url=settings.lambda_get_schedule
        )
    return _components["main_router"]


def get_fiscal_processor() -> FiscalProcessor:
    """Retorna processador fiscal com LLM"""
    if "fiscal_processor" not in _components:
        settings = get_settings()
        _components["fiscal_processor"] = FiscalProcessor(
            dynamo_manager=get_dynamo_state_manager(),
            api_key=settings.openai_api_key,
            model=settings.intent_model
        )
    return _components["fiscal_processor"]


def get_escala_subgraph() -> EscalaSubgraph:
    """Retorna subgrafo de escala"""
    if "escala_subgraph" not in _components:
        settings = get_settings()
        _components["escala_subgraph"] = EscalaSubgraph(
            http_client=get_http_client(),
            lambda_update_schedule_url=settings.lambda_update_schedule,
            lambda_get_schedule_url=settings.lambda_get_schedule
        )
    return _components["escala_subgraph"]


def get_clinico_subgraph() -> ClinicoSubgraph:
    """Retorna subgrafo clínico"""
    if "clinico_subgraph" not in _components:
        settings = get_settings()
        _components["clinico_subgraph"] = ClinicoSubgraph(
            clinical_extractor=get_clinical_extractor(),
            rag_system=get_rag_system(),
            http_client=get_http_client(),
            lambda_update_clinical_url=settings.lambda_update_clinical
        )
    return _components["clinico_subgraph"]


def get_operacional_subgraph() -> OperacionalSubgraph:
    """Retorna subgrafo operacional"""
    if "operacional_subgraph" not in _components:
        settings = get_settings()
        _components["operacional_subgraph"] = OperacionalSubgraph(
            http_client=get_http_client(),
            lambda_update_clinical_url=settings.lambda_update_clinical
        )
    return _components["operacional_subgraph"]


def get_finalizar_subgraph() -> FinalizarSubgraph:
    """Retorna subgrafo de finalização"""
    if "finalizar_subgraph" not in _components:
        settings = get_settings()
        _components["finalizar_subgraph"] = FinalizarSubgraph(
            http_client=get_http_client(),
            lambda_get_note_report_url=settings.lambda_get_note_report,
            lambda_update_summary_url=settings.lambda_update_summary
        )
    return _components["finalizar_subgraph"]


def get_auxiliar_subgraph() -> AuxiliarSubgraph:
    """Retorna subgrafo auxiliar"""
    if "auxiliar_subgraph" not in _components:
        _components["auxiliar_subgraph"] = AuxiliarSubgraph()
    return _components["auxiliar_subgraph"]


def initialize_logging():
    """Inicializa logging"""
    settings = get_settings()
    configure_logging(settings.log_level)
    logger.info("Sistema inicializado", log_level=settings.log_level)
