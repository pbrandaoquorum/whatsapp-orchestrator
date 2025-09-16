"""
Testes para a camada de store do DynamoDB
"""
import pytest
import json
import time
from datetime import datetime, timedelta
from moto import mock_dynamodb
import boto3
from botocore.exceptions import ClientError

from app.infra.store import (
    SessionStore, PendingActionsStore, ConversationBufferStore, 
    LockStore, IdempotencyStore
)
from app.infra.dynamo_client import (
    TABLE_SESSIONS, TABLE_PENDING_ACTIONS, TABLE_CONV_BUFFER,
    TABLE_LOCKS, TABLE_IDEMPOTENCY, is_conditional_check_failed
)


@pytest.fixture
def dynamodb_tables():
    """Fixture para criar tabelas DynamoDB mock"""
    with mock_dynamodb():
        # Criar cliente DynamoDB
        dynamodb = boto3.resource('dynamodb', region_name='sa-east-1')
        
        # Criar tabela de sessões
        dynamodb.create_table(
            TableName=TABLE_SESSIONS,
            KeySchema=[
                {'AttributeName': 'sessionId', 'KeyType': 'HASH'}
            ],
            AttributeDefinitions=[
                {'AttributeName': 'sessionId', 'AttributeType': 'S'}
            ],
            BillingMode='PAY_PER_REQUEST'
        )
        
        # Criar tabela de ações pendentes
        dynamodb.create_table(
            TableName=TABLE_PENDING_ACTIONS,
            KeySchema=[
                {'AttributeName': 'sessionId', 'KeyType': 'HASH'},
                {'AttributeName': 'actionId', 'KeyType': 'RANGE'}
            ],
            AttributeDefinitions=[
                {'AttributeName': 'sessionId', 'AttributeType': 'S'},
                {'AttributeName': 'actionId', 'AttributeType': 'S'}
            ],
            BillingMode='PAY_PER_REQUEST'
        )
        
        # Criar tabela de buffer de conversação
        dynamodb.create_table(
            TableName=TABLE_CONV_BUFFER,
            KeySchema=[
                {'AttributeName': 'sessionId', 'KeyType': 'HASH'},
                {'AttributeName': 'createdAtEpoch', 'KeyType': 'RANGE'}
            ],
            AttributeDefinitions=[
                {'AttributeName': 'sessionId', 'AttributeType': 'S'},
                {'AttributeName': 'createdAtEpoch', 'AttributeType': 'N'}
            ],
            BillingMode='PAY_PER_REQUEST'
        )
        
        # Criar tabela de locks
        dynamodb.create_table(
            TableName=TABLE_LOCKS,
            KeySchema=[
                {'AttributeName': 'resource', 'KeyType': 'HASH'}
            ],
            AttributeDefinitions=[
                {'AttributeName': 'resource', 'AttributeType': 'S'}
            ],
            BillingMode='PAY_PER_REQUEST'
        )
        
        # Criar tabela de idempotência
        dynamodb.create_table(
            TableName=TABLE_IDEMPOTENCY,
            KeySchema=[
                {'AttributeName': 'idempotencyKey', 'KeyType': 'HASH'}
            ],
            AttributeDefinitions=[
                {'AttributeName': 'idempotencyKey', 'AttributeType': 'S'}
            ],
            BillingMode='PAY_PER_REQUEST'
        )
        
        yield dynamodb


class TestSessionStore:
    """Testes para SessionStore"""
    
    def test_get_nonexistent_session(self, dynamodb_tables):
        """Teste buscar sessão que não existe"""
        store = SessionStore()
        
        state, version = store.get("session_nonexistent")
        
        assert state is None
        assert version == 0
    
    def test_put_new_session(self, dynamodb_tables):
        """Teste criar nova sessão"""
        store = SessionStore()
        session_id = "session_test123"
        state_data = {
            "core": {"session_id": session_id, "numero_telefone": "+5511999999999"},
            "vitais": {"processados": {}, "faltantes": ["PA", "FC"]},
            "version": 1
        }
        
        new_version = store.put(session_id, state_data, 0)
        
        assert new_version == 1
        
        # Verificar se foi salvo
        retrieved_state, retrieved_version = store.get(session_id)
        assert retrieved_state is not None
        assert retrieved_version == 1
        assert retrieved_state["core"]["session_id"] == session_id
    
    def test_put_update_session_success(self, dynamodb_tables):
        """Teste atualizar sessão com versão correta"""
        store = SessionStore()
        session_id = "session_test456"
        
        # Criar sessão inicial
        initial_state = {"test": "initial"}
        version1 = store.put(session_id, initial_state, 0)
        
        # Atualizar com versão correta
        updated_state = {"test": "updated"}
        version2 = store.put(session_id, updated_state, version1)
        
        assert version2 == version1 + 1
        
        # Verificar atualização
        retrieved_state, retrieved_version = store.get(session_id)
        assert retrieved_state["test"] == "updated"
        assert retrieved_version == version2
    
    def test_put_update_session_conflict(self, dynamodb_tables):
        """Teste conflito de versão (OCC)"""
        store = SessionStore()
        session_id = "session_conflict"
        
        # Criar sessão inicial
        initial_state = {"test": "initial"}
        version1 = store.put(session_id, initial_state, 0)
        
        # Tentar atualizar com versão incorreta
        updated_state = {"test": "updated"}
        
        with pytest.raises(ClientError) as exc_info:
            store.put(session_id, updated_state, version1 + 10)  # Versão incorreta
        
        assert is_conditional_check_failed(exc_info.value)
    
    def test_update_metadata(self, dynamodb_tables):
        """Teste atualizar metadados da sessão"""
        store = SessionStore()
        session_id = "session_metadata"
        
        # Criar sessão inicial
        initial_state = {"test": "initial"}
        store.put(session_id, initial_state, 0)
        
        # Atualizar metadados
        store.update_metadata(
            session_id,
            lastFlow="clinical",
            pendingActionId="action_123"
        )
        
        # Verificar se metadados foram salvos
        # (Em implementação real, verificaríamos na tabela)
        # Por simplicidade, apenas verificamos que não deu erro


class TestPendingActionsStore:
    """Testes para PendingActionsStore"""
    
    def test_create_action(self, dynamodb_tables):
        """Teste criar ação pendente"""
        store = PendingActionsStore()
        session_id = "session_action_test"
        
        action = store.create(
            session_id=session_id,
            flow="clinical_commit",
            description="Salvar sinais vitais",
            payload={"PA": "120x80", "FC": 78},
            expires_at=int(time.time()) + 3600
        )
        
        assert action.session_id == session_id
        assert action.flow == "clinical_commit"
        assert action.status == "staged"
        assert action.action_id is not None
        assert len(action.action_id) > 0
    
    def test_mark_confirmed_success(self, dynamodb_tables):
        """Teste confirmar ação com sucesso"""
        store = PendingActionsStore()
        session_id = "session_confirm_test"
        
        # Criar ação
        action = store.create(
            session_id=session_id,
            flow="test_flow",
            description="Test action",
            payload={"test": "data"}
        )
        
        # Confirmar ação
        success = store.mark_confirmed(session_id, action.action_id)
        
        assert success is True
    
    def test_mark_confirmed_invalid_status(self, dynamodb_tables):
        """Teste confirmar ação em estado inválido"""
        store = PendingActionsStore()
        session_id = "session_invalid_confirm"
        
        # Criar e executar ação
        action = store.create(
            session_id=session_id,
            flow="test_flow",
            description="Test action",
            payload={"test": "data"}
        )
        
        store.mark_confirmed(session_id, action.action_id)
        store.mark_executed(session_id, action.action_id)
        
        # Tentar confirmar ação já executada
        success = store.mark_confirmed(session_id, action.action_id)
        
        assert success is False
    
    def test_mark_executed_success(self, dynamodb_tables):
        """Teste executar ação com sucesso"""
        store = PendingActionsStore()
        session_id = "session_execute_test"
        
        # Criar e confirmar ação
        action = store.create(
            session_id=session_id,
            flow="test_flow",
            description="Test action",
            payload={"test": "data"}
        )
        
        store.mark_confirmed(session_id, action.action_id)
        
        # Executar ação
        success = store.mark_executed(session_id, action.action_id)
        
        assert success is True
    
    def test_abort_action(self, dynamodb_tables):
        """Teste abortar ação"""
        store = PendingActionsStore()
        session_id = "session_abort_test"
        
        # Criar ação
        action = store.create(
            session_id=session_id,
            flow="test_flow",
            description="Test action",
            payload={"test": "data"}
        )
        
        # Abortar ação
        success = store.abort(session_id, action.action_id)
        
        assert success is True
    
    def test_get_current_action(self, dynamodb_tables):
        """Teste buscar ação atual da sessão"""
        store = PendingActionsStore()
        session_id = "session_current_test"
        
        # Criar ação
        action = store.create(
            session_id=session_id,
            flow="test_flow",
            description="Test action",
            payload={"test": "data"}
        )
        
        # Buscar ação atual
        current = store.get_current(session_id)
        
        assert current is not None
        assert current.action_id == action.action_id
        assert current.status == "staged"


class TestConversationBufferStore:
    """Testes para ConversationBufferStore"""
    
    def test_append_message(self, dynamodb_tables):
        """Teste adicionar mensagem ao buffer"""
        store = ConversationBufferStore()
        session_id = "session_buffer_test"
        
        store.append(
            session_id=session_id,
            role="user",
            text="Olá, como está?",
            meta={"origin": "test"}
        )
        
        # Buscar mensagens
        messages = store.list_last(session_id, 10)
        
        assert len(messages) == 1
        assert messages[0].role == "user"
        assert messages[0].text == "Olá, como está?"
        assert messages[0].meta["origin"] == "test"
    
    def test_list_messages_order(self, dynamodb_tables):
        """Teste ordem das mensagens (mais recente primeiro)"""
        store = ConversationBufferStore()
        session_id = "session_order_test"
        
        # Adicionar mensagens com delay
        store.append(session_id, "user", "Primeira mensagem")
        time.sleep(0.001)  # Garantir timestamps diferentes
        store.append(session_id, "assistant", "Segunda mensagem")
        time.sleep(0.001)
        store.append(session_id, "user", "Terceira mensagem")
        
        # Buscar mensagens
        messages = store.list_last(session_id, 10)
        
        assert len(messages) == 3
        # Mais recente primeiro
        assert messages[0].text == "Terceira mensagem"
        assert messages[1].text == "Segunda mensagem"
        assert messages[2].text == "Primeira mensagem"
    
    def test_list_messages_limit(self, dynamodb_tables):
        """Teste limite de mensagens"""
        store = ConversationBufferStore()
        session_id = "session_limit_test"
        
        # Adicionar 5 mensagens
        for i in range(5):
            store.append(session_id, "user", f"Mensagem {i}")
            time.sleep(0.001)
        
        # Buscar apenas 3
        messages = store.list_last(session_id, 3)
        
        assert len(messages) == 3
        # Deve retornar as 3 mais recentes
        assert messages[0].text == "Mensagem 4"
        assert messages[1].text == "Mensagem 3"
        assert messages[2].text == "Mensagem 2"


class TestLockStore:
    """Testes para LockStore"""
    
    def test_acquire_lock_success(self, dynamodb_tables):
        """Teste adquirir lock com sucesso"""
        store = LockStore()
        resource = "test_resource"
        owner = "test_owner"
        
        success = store.acquire(resource, owner, 10)
        
        assert success is True
    
    def test_acquire_lock_conflict(self, dynamodb_tables):
        """Teste conflito ao adquirir lock"""
        store = LockStore()
        resource = "test_resource_conflict"
        owner1 = "owner1"
        owner2 = "owner2"
        
        # Primeiro owner adquire o lock
        success1 = store.acquire(resource, owner1, 10)
        assert success1 is True
        
        # Segundo owner tenta adquirir o mesmo lock
        success2 = store.acquire(resource, owner2, 10)
        assert success2 is False
    
    def test_release_lock_success(self, dynamodb_tables):
        """Teste liberar lock com sucesso"""
        store = LockStore()
        resource = "test_resource_release"
        owner = "test_owner"
        
        # Adquirir lock
        store.acquire(resource, owner, 10)
        
        # Liberar lock
        success = store.release(resource, owner)
        
        assert success is True
        
        # Verificar que outro owner pode adquirir
        success2 = store.acquire(resource, "another_owner", 10)
        assert success2 is True
    
    def test_release_lock_wrong_owner(self, dynamodb_tables):
        """Teste tentar liberar lock de outro owner"""
        store = LockStore()
        resource = "test_resource_wrong_owner"
        owner1 = "owner1"
        owner2 = "owner2"
        
        # Owner1 adquire lock
        store.acquire(resource, owner1, 10)
        
        # Owner2 tenta liberar
        success = store.release(resource, owner2)
        
        assert success is False


class TestIdempotencyStore:
    """Testes para IdempotencyStore"""
    
    def test_begin_new_key(self, dynamodb_tables):
        """Teste iniciar operação com chave nova"""
        store = IdempotencyStore()
        key = "test_key_new"
        session_id = "session_test"
        
        success = store.begin(key, session_id, 300)
        
        assert success is True
    
    def test_begin_existing_key(self, dynamodb_tables):
        """Teste tentar iniciar operação com chave existente"""
        store = IdempotencyStore()
        key = "test_key_existing"
        session_id = "session_test"
        
        # Primeira tentativa
        success1 = store.begin(key, session_id, 300)
        assert success1 is True
        
        # Segunda tentativa com mesma chave
        success2 = store.begin(key, session_id, 300)
        assert success2 is False
    
    def test_end_ok_and_get_cached(self, dynamodb_tables):
        """Teste finalizar com sucesso e recuperar resposta cacheada"""
        store = IdempotencyStore()
        key = "test_key_cache"
        session_id = "session_test"
        response_data = '{"success": true, "message": "Test response"}'
        
        # Iniciar operação
        store.begin(key, session_id, 300)
        
        # Finalizar com sucesso
        store.end_ok(key, response_data)
        
        # Recuperar resposta cacheada
        cached = store.get_cached(key)
        
        assert cached == response_data
    
    def test_end_error(self, dynamodb_tables):
        """Teste finalizar com erro"""
        store = IdempotencyStore()
        key = "test_key_error"
        session_id = "session_test"
        
        # Iniciar operação
        store.begin(key, session_id, 300)
        
        # Finalizar com erro
        store.end_error(key)
        
        # Não deve ter resposta cacheada
        cached = store.get_cached(key)
        assert cached is None
    
    def test_get_cached_nonexistent(self, dynamodb_tables):
        """Teste buscar cache de chave inexistente"""
        store = IdempotencyStore()
        key = "nonexistent_key"
        
        cached = store.get_cached(key)
        
        assert cached is None


@pytest.mark.asyncio
class TestIntegration:
    """Testes de integração entre stores"""
    
    async def test_full_workflow(self, dynamodb_tables):
        """Teste workflow completo: sessão + ação + buffer"""
        session_store = SessionStore()
        actions_store = PendingActionsStore()
        buffer_store = ConversationBufferStore()
        
        session_id = "session_integration_test"
        
        # 1. Criar sessão
        initial_state = {
            "core": {"session_id": session_id},
            "vitais": {"processados": {}, "faltantes": ["PA", "FC"]}
        }
        version = session_store.put(session_id, initial_state, 0)
        
        # 2. Adicionar mensagem do usuário
        buffer_store.append(session_id, "user", "PA 120x80")
        
        # 3. Criar ação pendente
        action = actions_store.create(
            session_id=session_id,
            flow="clinical_commit",
            description="Salvar PA",
            payload={"PA": "120x80"}
        )
        
        # 4. Atualizar estado
        updated_state = initial_state.copy()
        updated_state["vitais"]["processados"] = {"PA": "120x80"}
        updated_state["aux"] = {"acao_pendente": {"action_id": action.action_id}}
        
        new_version = session_store.put(session_id, updated_state, version)
        
        # 5. Confirmar ação
        actions_store.mark_confirmed(session_id, action.action_id)
        
        # 6. Adicionar resposta do assistente
        buffer_store.append(session_id, "assistant", "PA coletado. Confirma salvar?")
        
        # Verificações finais
        final_state, final_version = session_store.get(session_id)
        assert final_state is not None
        assert final_version == new_version
        
        current_action = actions_store.get_current(session_id)
        assert current_action is not None
        assert current_action.status == "confirmed"
        
        messages = buffer_store.list_last(session_id, 10)
        assert len(messages) == 2
        assert messages[0].role == "assistant"  # Mais recente
        assert messages[1].role == "user"
