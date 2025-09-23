"""
Persistência de estado no DynamoDB
Operações síncronas para carregar/salvar GraphState
"""
import json
from datetime import datetime, timezone
from typing import Optional
import boto3
from botocore.exceptions import ClientError
import orjson
import structlog

from app.graph.state import GraphState

logger = structlog.get_logger(__name__)


class DynamoStateManager:
    """Gerenciador de estado no DynamoDB"""
    
    def __init__(self, table_name: str, aws_region: str = "sa-east-1"):
        self.table_name = table_name
        self.dynamodb = boto3.client('dynamodb', region_name=aws_region)
        logger.info("DynamoStateManager inicializado", table_name=table_name, region=aws_region)
    
    def _serialize_state(self, state: GraphState) -> str:
        """Serializa GraphState para JSON string usando orjson"""
        try:
            # Converte para dict e serializa como string
            state_dict = state.model_dump()
            return orjson.dumps(state_dict).decode('utf-8')
        except Exception as e:
            logger.error("Erro ao serializar estado", error=str(e))
            raise
    
    def _deserialize_state(self, data: str) -> GraphState:
        """Deserializa JSON string para GraphState"""
        try:
            state_dict = orjson.loads(data.encode('utf-8'))
            return GraphState(**state_dict)
        except Exception as e:
            logger.error("Erro ao deserializar estado", error=str(e))
            raise
    
    def carregar_estado(self, session_id: str) -> GraphState:
        """
        Carrega estado do DynamoDB
        Se não existir, retorna GraphState vazio com session_id preenchido
        """
        try:
            response = self.dynamodb.get_item(
                TableName=self.table_name,
                Key={
                    'session_id': {'S': session_id}
                }
            )
            
            if 'Item' not in response:
                # Estado não existe, cria novo
                logger.info("Estado não encontrado, criando novo", session_id=session_id)
                state = GraphState()
                state.sessao["session_id"] = session_id
                return state
            
            # Deserializa estado existente
            # Tenta primeiro como String (S), depois como Binary (B) para compatibilidade
            if 'S' in response['Item']['estado']:
                estado_str = response['Item']['estado']['S']
                state = self._deserialize_state(estado_str)
            elif 'B' in response['Item']['estado']:
                # Compatibilidade com versão anterior (Binary)
                estado_bytes = response['Item']['estado']['B']
                estado_str = estado_bytes.decode('utf-8') if isinstance(estado_bytes, bytes) else str(estado_bytes)
                state = self._deserialize_state(estado_str)
            else:
                logger.error("Formato de estado não reconhecido", session_id=session_id)
                raise ValueError("Estado em formato inválido")
            
            logger.info("Estado carregado com sucesso", 
                       session_id=session_id,
                       fluxos_executados=len(state.fluxos_executados))
            return state
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            logger.error("Erro do DynamoDB ao carregar estado", 
                        session_id=session_id,
                        error_code=error_code,
                        error_message=e.response['Error']['Message'])
            
            if error_code == 'ResourceNotFoundException':
                logger.warning("Tabela não encontrada, criando estado vazio", session_id=session_id)
                state = GraphState()
                state.sessao["session_id"] = session_id
                return state
            
            raise
        except Exception as e:
            logger.error("Erro inesperado ao carregar estado", session_id=session_id, error=str(e))
            raise
    
    def salvar_estado(self, session_id: str, state: GraphState) -> None:
        """Salva estado no DynamoDB"""
        try:
            # Atualiza session_id no estado
            state.sessao["session_id"] = session_id
            
            # Serializa estado
            estado_str = self._serialize_state(state)
            
            # Timestamp atual
            agora = datetime.now(timezone.utc).isoformat()
            
            # Salva no DynamoDB
            self.dynamodb.put_item(
                TableName=self.table_name,
                Item={
                    'session_id': {'S': session_id},
                    'estado': {'S': estado_str},  # Mudou de 'B' para 'S' (String)
                    'atualizadoEm': {'S': agora}
                }
            )
            
            logger.info("Estado salvo com sucesso",
                       session_id=session_id,
                       tamanho_bytes=len(estado_str),
                       fluxos_executados=len(state.fluxos_executados))
            
        except ClientError as e:
            logger.error("Erro do DynamoDB ao salvar estado",
                        session_id=session_id,
                        error_code=e.response['Error']['Code'],
                        error_message=e.response['Error']['Message'])
            raise
        except Exception as e:
            logger.error("Erro inesperado ao salvar estado", session_id=session_id, error=str(e))
            raise
    
    def verificar_tabela(self) -> bool:
        """Verifica se a tabela existe e está acessível"""
        try:
            response = self.dynamodb.describe_table(TableName=self.table_name)
            status = response['Table']['TableStatus']
            logger.info("Tabela verificada", table_name=self.table_name, status=status)
            return status == 'ACTIVE'
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                logger.warning("Tabela não encontrada", table_name=self.table_name)
                return False
            logger.error("Erro ao verificar tabela", 
                        table_name=self.table_name,
                        error=e.response['Error']['Message'])
            return False
        except Exception as e:
            logger.error("Erro inesperado ao verificar tabela", table_name=self.table_name, error=str(e))
            return False


def normalizar_session_id(phone_number: str) -> str:
    """
    Normaliza número de telefone para usar como session_id
    Remove caracteres especiais e padroniza formato
    """
    # Remove todos os caracteres não numéricos
    digits = ''.join(filter(str.isdigit, phone_number))
    
    # Se começar com 55 (código do Brasil), mantém
    # Caso contrário, assume que já está no formato local
    if len(digits) >= 13 and digits.startswith('55'):
        return digits
    elif len(digits) >= 11:
        return f"55{digits}"
    else:
        # Número muito curto, retorna como está
        return digits or phone_number
