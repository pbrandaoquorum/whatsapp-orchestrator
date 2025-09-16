"""
Cliente DynamoDB com configuração e retry policies
"""
import os
import boto3
from boto3.dynamodb.types import TypeDeserializer, TypeSerializer
from botocore.config import Config
from botocore.exceptions import ClientError
from typing import Optional, Dict, Any
import time
import logging

logger = logging.getLogger(__name__)

# Configuração de retry para DynamoDB
DYNAMO_CONFIG = Config(
    region_name=os.getenv('AWS_REGION', 'sa-east-1'),
    retries={
        'max_attempts': 3,
        'mode': 'adaptive'
    },
    read_timeout=10,
    connect_timeout=5,
    max_pool_connections=50
)

# Cache de clientes
_dynamo_client: Optional[boto3.client] = None
_dynamo_resource: Optional[boto3.resource] = None

# Nomes das tabelas a partir do ambiente
TABLE_SESSIONS = os.getenv('DDB_TABLE_SESSIONS', 'OrchestratorSessions')
TABLE_PENDING_ACTIONS = os.getenv('DDB_TABLE_PENDING_ACTIONS', 'PendingActions')
TABLE_CONV_BUFFER = os.getenv('DDB_TABLE_CONV_BUFFER', 'ConversationBuffer')
TABLE_LOCKS = os.getenv('DDB_TABLE_LOCKS', 'Locks')
TABLE_IDEMPOTENCY = os.getenv('DDB_TABLE_IDEMPOTENCY', 'Idempotency')

# TTL defaults (em segundos)
SESSION_TTL_SECONDS = int(os.getenv('SESSION_TTL_DAYS', '7')) * 24 * 60 * 60
BUFFER_TTL_SECONDS = int(os.getenv('BUFFER_TTL_DAYS', '7')) * 24 * 60 * 60
IDEMPOTENCY_TTL_SECONDS = int(os.getenv('IDEMPOTENCY_TTL_SECONDS', '600'))
LOCK_TTL_SECONDS = int(os.getenv('LOCK_TTL_SECONDS', '10'))


def get_dynamo_client() -> boto3.client:
    """
    Retorna cliente DynamoDB singleton com configuração otimizada
    """
    global _dynamo_client
    
    if _dynamo_client is None:
        _dynamo_client = boto3.client('dynamodb', config=DYNAMO_CONFIG)
        logger.info("DynamoDB client inicializado", region=DYNAMO_CONFIG.region_name)
    
    return _dynamo_client


def get_dynamo_resource() -> boto3.resource:
    """
    Retorna resource DynamoDB singleton para operações de alto nível
    """
    global _dynamo_resource
    
    if _dynamo_resource is None:
        _dynamo_resource = boto3.resource('dynamodb', config=DYNAMO_CONFIG)
        logger.info("DynamoDB resource inicializado", region=DYNAMO_CONFIG.region_name)
    
    return _dynamo_resource


def get_table(table_name: str):
    """
    Retorna referência para uma tabela DynamoDB
    """
    resource = get_dynamo_resource()
    return resource.Table(table_name)


def serialize_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """
    Serializa item Python para formato DynamoDB
    """
    serializer = TypeSerializer()
    return {k: serializer.serialize(v) for k, v in item.items()}


def deserialize_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deserializa item DynamoDB para formato Python
    """
    deserializer = TypeDeserializer()
    return {k: deserializer.deserialize(v) for k, v in item.items()}


def get_current_timestamp() -> str:
    """
    Retorna timestamp atual em formato ISO8601
    """
    from datetime import datetime
    return datetime.utcnow().isoformat() + 'Z'


def get_ttl_timestamp(ttl_seconds: int) -> int:
    """
    Retorna timestamp TTL (epoch seconds) para TTL do DynamoDB
    """
    return int(time.time()) + ttl_seconds


def handle_dynamo_error(error: ClientError, operation: str, **context) -> None:
    """
    Trata erros específicos do DynamoDB com logging estruturado
    """
    error_code = error.response['Error']['Code']
    error_message = error.response['Error']['Message']
    
    logger.error(
        f"DynamoDB error in {operation}",
        error_code=error_code,
        error_message=error_message,
        **context
    )
    
    # Re-raise com contexto adicional
    raise error


def is_conditional_check_failed(error: ClientError) -> bool:
    """
    Verifica se o erro é ConditionalCheckFailedException
    """
    return error.response['Error']['Code'] == 'ConditionalCheckFailedException'


def is_resource_not_found(error: ClientError) -> bool:
    """
    Verifica se o erro é ResourceNotFoundException
    """
    return error.response['Error']['Code'] == 'ResourceNotFoundException'


def retry_on_throttle(func):
    """
    Decorador para retry em caso de throttling do DynamoDB
    """
    def wrapper(*args, **kwargs):
        max_retries = 3
        base_delay = 0.1
        
        for attempt in range(max_retries + 1):
            try:
                return func(*args, **kwargs)
            except ClientError as e:
                error_code = e.response['Error']['Code']
                
                if error_code in ['ProvisionedThroughputExceededException', 'RequestLimitExceeded']:
                    if attempt < max_retries:
                        delay = base_delay * (2 ** attempt)  # Exponential backoff
                        logger.warning(
                            f"DynamoDB throttled, retrying in {delay}s",
                            attempt=attempt + 1,
                            max_retries=max_retries
                        )
                        time.sleep(delay)
                        continue
                
                raise e
    
    return wrapper


def validate_table_exists(table_name: str) -> bool:
    """
    Valida se a tabela existe no DynamoDB
    """
    try:
        client = get_dynamo_client()
        client.describe_table(TableName=table_name)
        return True
    except ClientError as e:
        if is_resource_not_found(e):
            return False
        raise e


def get_all_table_names() -> list[str]:
    """
    Retorna lista com nomes de todas as tabelas necessárias
    """
    return [
        TABLE_SESSIONS,
        TABLE_PENDING_ACTIONS,
        TABLE_CONV_BUFFER,
        TABLE_LOCKS,
        TABLE_IDEMPOTENCY
    ]


async def health_check() -> Dict[str, Any]:
    """
    Verifica saúde da conexão com DynamoDB
    """
    try:
        client = get_dynamo_client()
        
        # Testa conectividade listando tabelas
        response = client.list_tables(Limit=1)
        
        # Verifica se tabelas necessárias existem
        missing_tables = []
        for table_name in get_all_table_names():
            if not validate_table_exists(table_name):
                missing_tables.append(table_name)
        
        return {
            "status": "healthy" if not missing_tables else "degraded",
            "region": DYNAMO_CONFIG.region_name,
            "missing_tables": missing_tables,
            "timestamp": get_current_timestamp()
        }
        
    except Exception as e:
        logger.error("DynamoDB health check failed", error=str(e))
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": get_current_timestamp()
        }
