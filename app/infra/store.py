"""
Camada de acesso a dados (DAO/Repository) para DynamoDB
"""
import json
import time
import ulid
from typing import Dict, Any, Optional, List, Tuple
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Key, Attr
from dataclasses import dataclass
from datetime import datetime

from .dynamo_client import (
    get_table, get_current_timestamp, get_ttl_timestamp,
    handle_dynamo_error, is_conditional_check_failed, retry_on_throttle,
    TABLE_SESSIONS, TABLE_PENDING_ACTIONS, TABLE_CONV_BUFFER, 
    TABLE_LOCKS, TABLE_IDEMPOTENCY, SESSION_TTL_SECONDS, 
    BUFFER_TTL_SECONDS, IDEMPOTENCY_TTL_SECONDS, LOCK_TTL_SECONDS
)
from ..infra.logging import obter_logger

logger = obter_logger(__name__)


@dataclass
class PendingAction:
    """Modelo para ação pendente (TPC)"""
    session_id: str
    action_id: str
    flow: str
    description: str
    payload: Dict[str, Any]
    status: str  # staged, confirmed, executed, aborted
    created_at: str
    confirmed_at: Optional[str] = None
    executed_at: Optional[str] = None
    expires_at: int = 0
    idempotency_key: Optional[str] = None


@dataclass
class ConversationMessage:
    """Modelo para mensagem de conversa"""
    session_id: str
    created_at_epoch: int
    role: str  # user, assistant, system
    text: str
    meta: Dict[str, Any]
    ttl: int


class SessionStore:
    """Store para sessões do orquestrador"""
    
    def __init__(self):
        self.table = get_table(TABLE_SESSIONS)
    
    @retry_on_throttle
    def get(self, session_id: str) -> Tuple[Optional[Dict[str, Any]], int]:
        """
        Recupera estado da sessão e versão atual
        
        Returns:
            (state_dict, version) ou (None, 0) se não existe
        """
        try:
            response = self.table.get_item(Key={'sessionId': session_id})
            
            if 'Item' not in response:
                logger.debug("Sessão não encontrada", session_id=session_id)
                return None, 0
            
            item = response['Item']
            state_json = item.get('state', '{}')
            version = item.get('version', 0)
            
            # Deserializar estado
            try:
                state = json.loads(state_json) if isinstance(state_json, str) else state_json
            except json.JSONDecodeError as e:
                logger.error("Erro ao deserializar estado", session_id=session_id, error=str(e))
                return None, 0
            
            logger.debug("Sessão carregada", session_id=session_id, version=version)
            return state, version
            
        except ClientError as e:
            handle_dynamo_error(e, "SessionStore.get", session_id=session_id)
            raise
    
    @retry_on_throttle
    def put(self, session_id: str, state: Dict[str, Any], expected_version: int) -> int:
        """
        Salva estado da sessão com controle de versão otimista (OCC)
        
        Args:
            session_id: ID da sessão
            state: Estado serializado
            expected_version: Versão esperada para OCC
            
        Returns:
            Nova versão após salvamento
            
        Raises:
            ConditionalCheckFailedException: Se versão não confere (conflito)
        """
        new_version = expected_version + 1
        now = get_current_timestamp()
        ttl = get_ttl_timestamp(SESSION_TTL_SECONDS)
        
        # Serializar estado
        state_json = json.dumps(state, ensure_ascii=False)
        
        item = {
            'sessionId': session_id,
            'version': new_version,
            'state': state_json,
            'updatedAt': now,
            'ttl': ttl
        }
        
        try:
            # Condição: versão deve ser a esperada (ou item não existe se expected_version=0)
            if expected_version == 0:
                condition = Attr('sessionId').not_exists()
            else:
                condition = Attr('version').eq(expected_version)
            
            self.table.put_item(
                Item=item,
                ConditionExpression=condition
            )
            
            logger.debug(
                "Sessão salva com sucesso",
                session_id=session_id,
                old_version=expected_version,
                new_version=new_version
            )
            return new_version
            
        except ClientError as e:
            if is_conditional_check_failed(e):
                logger.warning(
                    "Conflito de versão detectado (OCC)",
                    session_id=session_id,
                    expected_version=expected_version
                )
            handle_dynamo_error(e, "SessionStore.put", session_id=session_id)
            raise
    
    @retry_on_throttle
    def update_metadata(self, session_id: str, **kwargs) -> None:
        """
        Atualiza metadados da sessão sem alterar o estado principal
        """
        try:
            update_expression = []
            expression_values = {}
            
            for key, value in kwargs.items():
                if value is not None:
                    update_expression.append(f"{key} = :{key}")
                    expression_values[f":{key}"] = value
            
            if not update_expression:
                return
            
            # Sempre atualizar timestamp
            update_expression.append("updatedAt = :updatedAt")
            expression_values[":updatedAt"] = get_current_timestamp()
            
            self.table.update_item(
                Key={'sessionId': session_id},
                UpdateExpression=f"SET {', '.join(update_expression)}",
                ExpressionAttributeValues=expression_values,
                ConditionExpression=Attr('sessionId').exists()
            )
            
            logger.debug("Metadados da sessão atualizados", session_id=session_id, fields=list(kwargs.keys()))
            
        except ClientError as e:
            handle_dynamo_error(e, "SessionStore.update_metadata", session_id=session_id)
            raise


class PendingActionsStore:
    """Store para ações pendentes (Two-Phase Commit)"""
    
    def __init__(self):
        self.table = get_table(TABLE_PENDING_ACTIONS)
    
    @retry_on_throttle
    def create(self, session_id: str, flow: str, description: str, 
               payload: Dict[str, Any], expires_at: Optional[int] = None) -> PendingAction:
        """
        Cria nova ação pendente (fase staging do TPC)
        """
        action_id = str(ulid.ULID())
        now = get_current_timestamp()
        
        if expires_at is None:
            expires_at = get_ttl_timestamp(3600)  # 1 hora default
        
        action = PendingAction(
            session_id=session_id,
            action_id=action_id,
            flow=flow,
            description=description,
            payload=payload,
            status="staged",
            created_at=now,
            expires_at=expires_at
        )
        
        try:
            self.table.put_item(
                Item={
                    'sessionId': session_id,
                    'actionId': action_id,
                    'flow': flow,
                    'description': description,
                    'payload': json.dumps(payload, ensure_ascii=False),
                    'status': 'staged',
                    'createdAt': now,
                    'expiresAt': expires_at
                }
            )
            
            logger.info("Ação pendente criada", session_id=session_id, action_id=action_id, flow=flow)
            return action
            
        except ClientError as e:
            handle_dynamo_error(e, "PendingActionsStore.create", session_id=session_id)
            raise
    
    @retry_on_throttle
    def mark_confirmed(self, session_id: str, action_id: str) -> bool:
        """
        Marca ação como confirmada (só se estiver em staged)
        """
        try:
            response = self.table.update_item(
                Key={'sessionId': session_id, 'actionId': action_id},
                UpdateExpression="SET #status = :confirmed, confirmedAt = :now",
                ConditionExpression=Attr('status').eq('staged'),
                ExpressionAttributeNames={'#status': 'status'},
                ExpressionAttributeValues={
                    ':confirmed': 'confirmed',
                    ':now': get_current_timestamp()
                },
                ReturnValues='UPDATED_NEW'
            )
            
            logger.info("Ação confirmada", session_id=session_id, action_id=action_id)
            return True
            
        except ClientError as e:
            if is_conditional_check_failed(e):
                logger.warning("Tentativa de confirmar ação em estado inválido", 
                             session_id=session_id, action_id=action_id)
                return False
            handle_dynamo_error(e, "PendingActionsStore.mark_confirmed", session_id=session_id)
            raise
    
    @retry_on_throttle
    def mark_executed(self, session_id: str, action_id: str) -> bool:
        """
        Marca ação como executada (só se estiver em confirmed)
        """
        try:
            self.table.update_item(
                Key={'sessionId': session_id, 'actionId': action_id},
                UpdateExpression="SET #status = :executed, executedAt = :now",
                ConditionExpression=Attr('status').eq('confirmed'),
                ExpressionAttributeNames={'#status': 'status'},
                ExpressionAttributeValues={
                    ':executed': 'executed',
                    ':now': get_current_timestamp()
                }
            )
            
            logger.info("Ação executada", session_id=session_id, action_id=action_id)
            return True
            
        except ClientError as e:
            if is_conditional_check_failed(e):
                logger.warning("Tentativa de executar ação em estado inválido", 
                             session_id=session_id, action_id=action_id)
                return False
            handle_dynamo_error(e, "PendingActionsStore.mark_executed", session_id=session_id)
            raise
    
    @retry_on_throttle
    def abort(self, session_id: str, action_id: str) -> bool:
        """
        Aborta ação pendente
        """
        try:
            self.table.update_item(
                Key={'sessionId': session_id, 'actionId': action_id},
                UpdateExpression="SET #status = :aborted",
                ConditionExpression=Attr('status').is_in(['staged', 'confirmed']),
                ExpressionAttributeNames={'#status': 'status'},
                ExpressionAttributeValues={':aborted': 'aborted'}
            )
            
            logger.info("Ação abortada", session_id=session_id, action_id=action_id)
            return True
            
        except ClientError as e:
            if is_conditional_check_failed(e):
                logger.warning("Tentativa de abortar ação em estado inválido", 
                             session_id=session_id, action_id=action_id)
                return False
            handle_dynamo_error(e, "PendingActionsStore.abort", session_id=session_id)
            raise
    
    @retry_on_throttle
    def get_by_id(self, action_id: str) -> Optional[PendingAction]:
        """
        Busca ação por ID usando GSI
        """
        try:
            # Implementaria GSI, mas para simplicidade vamos fazer scan
            # Em produção, usar GSI actionId-index
            response = self.table.scan(
                FilterExpression=Attr('actionId').eq(action_id),
                Limit=1
            )
            
            if not response.get('Items'):
                return None
            
            item = response['Items'][0]
            return self._item_to_action(item)
            
        except ClientError as e:
            handle_dynamo_error(e, "PendingActionsStore.get_by_id", action_id=action_id)
            raise
    
    @retry_on_throttle
    def get_current(self, session_id: str) -> Optional[PendingAction]:
        """
        Busca ação pendente atual da sessão (não executada)
        """
        try:
            response = self.table.query(
                KeyConditionExpression=Key('sessionId').eq(session_id),
                FilterExpression=Attr('status').is_in(['staged', 'confirmed']),
                ScanIndexForward=False,  # Mais recente primeiro
                Limit=1
            )
            
            if not response.get('Items'):
                return None
            
            return self._item_to_action(response['Items'][0])
            
        except ClientError as e:
            handle_dynamo_error(e, "PendingActionsStore.get_current", session_id=session_id)
            raise
    
    def _item_to_action(self, item: Dict[str, Any]) -> PendingAction:
        """Converte item DynamoDB para PendingAction"""
        payload = item.get('payload', '{}')
        if isinstance(payload, str):
            payload = json.loads(payload)
        
        return PendingAction(
            session_id=item['sessionId'],
            action_id=item['actionId'],
            flow=item['flow'],
            description=item['description'],
            payload=payload,
            status=item['status'],
            created_at=item['createdAt'],
            confirmed_at=item.get('confirmedAt'),
            executed_at=item.get('executedAt'),
            expires_at=item.get('expiresAt', 0),
            idempotency_key=item.get('idempotencyKey')
        )


class ConversationBufferStore:
    """Store para buffer de conversação (memória curta)"""
    
    def __init__(self):
        self.table = get_table(TABLE_CONV_BUFFER)
    
    @retry_on_throttle
    def append(self, session_id: str, role: str, text: str, 
               meta: Optional[Dict[str, Any]] = None, ttl: Optional[int] = None) -> None:
        """
        Adiciona mensagem ao buffer de conversação
        """
        created_at_epoch = int(time.time() * 1000)  # Milliseconds for precision
        
        if ttl is None:
            ttl = get_ttl_timestamp(BUFFER_TTL_SECONDS)
        
        if meta is None:
            meta = {}
        
        try:
            self.table.put_item(
                Item={
                    'sessionId': session_id,
                    'createdAtEpoch': created_at_epoch,
                    'role': role,
                    'text': text,
                    'meta': meta,
                    'ttl': ttl
                }
            )
            
            logger.debug("Mensagem adicionada ao buffer", 
                        session_id=session_id, role=role, text_length=len(text))
            
        except ClientError as e:
            handle_dynamo_error(e, "ConversationBufferStore.append", session_id=session_id)
            raise
    
    @retry_on_throttle
    def list_last(self, session_id: str, limit: int = 30) -> List[ConversationMessage]:
        """
        Lista últimas N mensagens da conversa (mais recentes primeiro)
        """
        try:
            response = self.table.query(
                KeyConditionExpression=Key('sessionId').eq(session_id),
                ScanIndexForward=False,  # Ordem decrescente (mais recente primeiro)
                Limit=limit
            )
            
            messages = []
            for item in response.get('Items', []):
                message = ConversationMessage(
                    session_id=item['sessionId'],
                    created_at_epoch=item['createdAtEpoch'],
                    role=item['role'],
                    text=item['text'],
                    meta=item.get('meta', {}),
                    ttl=item.get('ttl', 0)
                )
                messages.append(message)
            
            logger.debug("Mensagens recuperadas do buffer", 
                        session_id=session_id, count=len(messages))
            return messages
            
        except ClientError as e:
            handle_dynamo_error(e, "ConversationBufferStore.list_last", session_id=session_id)
            raise


class LockStore:
    """Store para locks distribuídos"""
    
    def __init__(self):
        self.table = get_table(TABLE_LOCKS)
    
    @retry_on_throttle
    def acquire(self, resource: str, owner: str, ttl_seconds: int = LOCK_TTL_SECONDS) -> bool:
        """
        Tenta adquirir lock distribuído
        
        Returns:
            True se adquiriu o lock, False caso contrário
        """
        expires_at = get_ttl_timestamp(ttl_seconds)
        now_epoch = int(time.time())
        
        try:
            self.table.put_item(
                Item={
                    'resource': resource,
                    'owner': owner,
                    'expiresAt': expires_at
                },
                ConditionExpression=(
                    Attr('resource').not_exists() | 
                    Attr('expiresAt').lt(now_epoch)
                )
            )
            
            logger.debug("Lock adquirido", resource=resource, owner=owner, ttl=ttl_seconds)
            return True
            
        except ClientError as e:
            if is_conditional_check_failed(e):
                logger.debug("Lock já existe ou não expirou", resource=resource, owner=owner)
                return False
            handle_dynamo_error(e, "LockStore.acquire", resource=resource)
            raise
    
    @retry_on_throttle
    def release(self, resource: str, owner: str) -> bool:
        """
        Libera lock distribuído (só se for o dono)
        
        Returns:
            True se liberou o lock, False se não era o dono
        """
        try:
            self.table.delete_item(
                Key={'resource': resource},
                ConditionExpression=Attr('owner').eq(owner)
            )
            
            logger.debug("Lock liberado", resource=resource, owner=owner)
            return True
            
        except ClientError as e:
            if is_conditional_check_failed(e):
                logger.debug("Tentativa de liberar lock de outro dono", resource=resource, owner=owner)
                return False
            handle_dynamo_error(e, "LockStore.release", resource=resource)
            raise


class IdempotencyStore:
    """Store para controle de idempotência"""
    
    def __init__(self):
        self.table = get_table(TABLE_IDEMPOTENCY)
    
    @retry_on_throttle
    def begin(self, key: str, session_id: str, ttl_seconds: int = IDEMPOTENCY_TTL_SECONDS) -> bool:
        """
        Inicia operação idempotente
        
        Returns:
            True se pode prosseguir, False se já está sendo processada ou foi concluída
        """
        now = get_current_timestamp()
        ttl = get_ttl_timestamp(ttl_seconds)
        
        try:
            self.table.put_item(
                Item={
                    'idempotencyKey': key,
                    'sessionId': session_id,
                    'firstSeenAt': now,
                    'status': 'processing',
                    'ttl': ttl
                },
                ConditionExpression=Attr('idempotencyKey').not_exists()
            )
            
            logger.debug("Operação idempotente iniciada", key=key, session_id=session_id)
            return True
            
        except ClientError as e:
            if is_conditional_check_failed(e):
                logger.debug("Chave idempotente já existe", key=key)
                return False
            handle_dynamo_error(e, "IdempotencyStore.begin", key=key)
            raise
    
    @retry_on_throttle
    def end_ok(self, key: str, response_json: str) -> None:
        """
        Marca operação como concluída com sucesso
        """
        try:
            self.table.update_item(
                Key={'idempotencyKey': key},
                UpdateExpression="SET #status = :done, cachedResponse = :response",
                ExpressionAttributeNames={'#status': 'status'},
                ExpressionAttributeValues={
                    ':done': 'done',
                    ':response': response_json
                }
            )
            
            logger.debug("Operação idempotente concluída com sucesso", key=key)
            
        except ClientError as e:
            handle_dynamo_error(e, "IdempotencyStore.end_ok", key=key)
            raise
    
    @retry_on_throttle
    def end_error(self, key: str) -> None:
        """
        Marca operação como concluída com erro
        """
        try:
            self.table.update_item(
                Key={'idempotencyKey': key},
                UpdateExpression="SET #status = :error",
                ExpressionAttributeNames={'#status': 'status'},
                ExpressionAttributeValues={':error': 'error'}
            )
            
            logger.debug("Operação idempotente concluída com erro", key=key)
            
        except ClientError as e:
            handle_dynamo_error(e, "IdempotencyStore.end_error", key=key)
            raise
    
    @retry_on_throttle
    def get_cached(self, key: str) -> Optional[str]:
        """
        Recupera resposta cacheada se operação foi concluída com sucesso
        """
        try:
            response = self.table.get_item(Key={'idempotencyKey': key})
            
            if 'Item' not in response:
                return None
            
            item = response['Item']
            if item.get('status') == 'done':
                return item.get('cachedResponse')
            
            return None
            
        except ClientError as e:
            handle_dynamo_error(e, "IdempotencyStore.get_cached", key=key)
            raise
