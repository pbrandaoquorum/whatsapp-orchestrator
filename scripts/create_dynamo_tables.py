#!/usr/bin/env python3
"""
Script para criar tabelas DynamoDB necessárias para o WhatsApp Orchestrator
"""
import boto3
import sys
import os
from botocore.exceptions import ClientError

# Adicionar o diretório pai ao path para importar módulos
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.infra.dynamo_client import (
    TABLE_SESSIONS, TABLE_PENDING_ACTIONS, TABLE_CONV_BUFFER,
    TABLE_LOCKS, TABLE_IDEMPOTENCY, DYNAMO_CONFIG
)


def create_sessions_table(dynamodb):
    """Cria tabela OrchestratorSessions"""
    try:
        table = dynamodb.create_table(
            TableName=TABLE_SESSIONS,
            KeySchema=[
                {
                    'AttributeName': 'sessionId',
                    'KeyType': 'HASH'  # Partition key
                }
            ],
            AttributeDefinitions=[
                {
                    'AttributeName': 'sessionId',
                    'AttributeType': 'S'
                }
            ],
            BillingMode='PAY_PER_REQUEST',
            TimeToLiveSpecification={
                'AttributeName': 'ttl',
                'Enabled': True
            },
            Tags=[
                {
                    'Key': 'Environment',
                    'Value': 'whatsapp-orchestrator'
                },
                {
                    'Key': 'Purpose',
                    'Value': 'session-state'
                }
            ]
        )
        
        print(f"✅ Tabela {TABLE_SESSIONS} criada com sucesso")
        return table
        
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceInUseException':
            print(f"⚠️  Tabela {TABLE_SESSIONS} já existe")
        else:
            print(f"❌ Erro ao criar tabela {TABLE_SESSIONS}: {e}")
            raise


def create_pending_actions_table(dynamodb):
    """Cria tabela PendingActions"""
    try:
        table = dynamodb.create_table(
            TableName=TABLE_PENDING_ACTIONS,
            KeySchema=[
                {
                    'AttributeName': 'sessionId',
                    'KeyType': 'HASH'  # Partition key
                },
                {
                    'AttributeName': 'actionId',
                    'KeyType': 'RANGE'  # Sort key
                }
            ],
            AttributeDefinitions=[
                {
                    'AttributeName': 'sessionId',
                    'AttributeType': 'S'
                },
                {
                    'AttributeName': 'actionId',
                    'AttributeType': 'S'
                },
                {
                    'AttributeName': 'status',
                    'AttributeType': 'S'
                },
                {
                    'AttributeName': 'createdAt',
                    'AttributeType': 'S'
                }
            ],
            GlobalSecondaryIndexes=[
                {
                    'IndexName': 'status-index',
                    'KeySchema': [
                        {
                            'AttributeName': 'status',
                            'KeyType': 'HASH'
                        },
                        {
                            'AttributeName': 'createdAt',
                            'KeyType': 'RANGE'
                        }
                    ],
                    'Projection': {
                        'ProjectionType': 'ALL'
                    }
                },
                {
                    'IndexName': 'actionId-index',
                    'KeySchema': [
                        {
                            'AttributeName': 'actionId',
                            'KeyType': 'HASH'
                        }
                    ],
                    'Projection': {
                        'ProjectionType': 'ALL'
                    }
                }
            ],
            BillingMode='PAY_PER_REQUEST',
            TimeToLiveSpecification={
                'AttributeName': 'expiresAt',
                'Enabled': True
            },
            Tags=[
                {
                    'Key': 'Environment',
                    'Value': 'whatsapp-orchestrator'
                },
                {
                    'Key': 'Purpose',
                    'Value': 'two-phase-commit'
                }
            ]
        )
        
        print(f"✅ Tabela {TABLE_PENDING_ACTIONS} criada com sucesso")
        return table
        
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceInUseException':
            print(f"⚠️  Tabela {TABLE_PENDING_ACTIONS} já existe")
        else:
            print(f"❌ Erro ao criar tabela {TABLE_PENDING_ACTIONS}: {e}")
            raise


def create_conversation_buffer_table(dynamodb):
    """Cria tabela ConversationBuffer"""
    try:
        table = dynamodb.create_table(
            TableName=TABLE_CONV_BUFFER,
            KeySchema=[
                {
                    'AttributeName': 'sessionId',
                    'KeyType': 'HASH'  # Partition key
                },
                {
                    'AttributeName': 'createdAtEpoch',
                    'KeyType': 'RANGE'  # Sort key
                }
            ],
            AttributeDefinitions=[
                {
                    'AttributeName': 'sessionId',
                    'AttributeType': 'S'
                },
                {
                    'AttributeName': 'createdAtEpoch',
                    'AttributeType': 'N'
                }
            ],
            BillingMode='PAY_PER_REQUEST',
            TimeToLiveSpecification={
                'AttributeName': 'ttl',
                'Enabled': True
            },
            Tags=[
                {
                    'Key': 'Environment',
                    'Value': 'whatsapp-orchestrator'
                },
                {
                    'Key': 'Purpose',
                    'Value': 'conversation-memory'
                }
            ]
        )
        
        print(f"✅ Tabela {TABLE_CONV_BUFFER} criada com sucesso")
        return table
        
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceInUseException':
            print(f"⚠️  Tabela {TABLE_CONV_BUFFER} já existe")
        else:
            print(f"❌ Erro ao criar tabela {TABLE_CONV_BUFFER}: {e}")
            raise


def create_locks_table(dynamodb):
    """Cria tabela Locks"""
    try:
        table = dynamodb.create_table(
            TableName=TABLE_LOCKS,
            KeySchema=[
                {
                    'AttributeName': 'resource',
                    'KeyType': 'HASH'  # Partition key
                }
            ],
            AttributeDefinitions=[
                {
                    'AttributeName': 'resource',
                    'AttributeType': 'S'
                }
            ],
            BillingMode='PAY_PER_REQUEST',
            TimeToLiveSpecification={
                'AttributeName': 'expiresAt',
                'Enabled': True
            },
            Tags=[
                {
                    'Key': 'Environment',
                    'Value': 'whatsapp-orchestrator'
                },
                {
                    'Key': 'Purpose',
                    'Value': 'distributed-locks'
                }
            ]
        )
        
        print(f"✅ Tabela {TABLE_LOCKS} criada com sucesso")
        return table
        
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceInUseException':
            print(f"⚠️  Tabela {TABLE_LOCKS} já existe")
        else:
            print(f"❌ Erro ao criar tabela {TABLE_LOCKS}: {e}")
            raise


def create_idempotency_table(dynamodb):
    """Cria tabela Idempotency"""
    try:
        table = dynamodb.create_table(
            TableName=TABLE_IDEMPOTENCY,
            KeySchema=[
                {
                    'AttributeName': 'idempotencyKey',
                    'KeyType': 'HASH'  # Partition key
                }
            ],
            AttributeDefinitions=[
                {
                    'AttributeName': 'idempotencyKey',
                    'AttributeType': 'S'
                }
            ],
            BillingMode='PAY_PER_REQUEST',
            TimeToLiveSpecification={
                'AttributeName': 'ttl',
                'Enabled': True
            },
            Tags=[
                {
                    'Key': 'Environment',
                    'Value': 'whatsapp-orchestrator'
                },
                {
                    'Key': 'Purpose',
                    'Value': 'idempotency-control'
                }
            ]
        )
        
        print(f"✅ Tabela {TABLE_IDEMPOTENCY} criada com sucesso")
        return table
        
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceInUseException':
            print(f"⚠️  Tabela {TABLE_IDEMPOTENCY} já existe")
        else:
            print(f"❌ Erro ao criar tabela {TABLE_IDEMPOTENCY}: {e}")
            raise


def wait_for_table_active(dynamodb, table_name):
    """Aguarda tabela ficar ativa"""
    print(f"⏳ Aguardando tabela {table_name} ficar ativa...")
    
    waiter = dynamodb.meta.client.get_waiter('table_exists')
    waiter.wait(
        TableName=table_name,
        WaiterConfig={
            'Delay': 2,
            'MaxAttempts': 30
        }
    )
    
    print(f"✅ Tabela {table_name} está ativa")


def main():
    """Função principal"""
    print("🚀 Criando tabelas DynamoDB para WhatsApp Orchestrator")
    print(f"📍 Região: {DYNAMO_CONFIG.region_name}")
    print()
    
    # Criar cliente DynamoDB
    try:
        dynamodb = boto3.resource('dynamodb', config=DYNAMO_CONFIG)
        print("✅ Conexão com DynamoDB estabelecida")
    except Exception as e:
        print(f"❌ Erro ao conectar com DynamoDB: {e}")
        sys.exit(1)
    
    # Lista de tabelas para criar
    tables_to_create = [
        (TABLE_SESSIONS, create_sessions_table),
        (TABLE_PENDING_ACTIONS, create_pending_actions_table),
        (TABLE_CONV_BUFFER, create_conversation_buffer_table),
        (TABLE_LOCKS, create_locks_table),
        (TABLE_IDEMPOTENCY, create_idempotency_table),
    ]
    
    created_tables = []
    
    # Criar tabelas
    print("\n📋 Criando tabelas:")
    for table_name, create_func in tables_to_create:
        try:
            table = create_func(dynamodb)
            if table:
                created_tables.append(table_name)
        except Exception as e:
            print(f"❌ Falha crítica ao criar tabela {table_name}: {e}")
            sys.exit(1)
    
    # Aguardar tabelas ficarem ativas
    if created_tables:
        print(f"\n⏳ Aguardando {len(created_tables)} tabela(s) ficarem ativas...")
        for table_name in created_tables:
            wait_for_table_active(dynamodb, table_name)
    
    print("\n🎉 Todas as tabelas foram criadas/verificadas com sucesso!")
    print("\n📊 Resumo das tabelas:")
    
    # Listar tabelas criadas
    for table_name, _ in tables_to_create:
        try:
            table = dynamodb.Table(table_name)
            table.load()
            
            print(f"  ✅ {table_name}")
            print(f"     Status: {table.table_status}")
            print(f"     Itens: {table.item_count}")
            print(f"     Tamanho: {table.table_size_bytes} bytes")
            
        except Exception as e:
            print(f"  ❌ {table_name}: Erro ao obter informações - {e}")
    
    print("\n🔧 Próximos passos:")
    print("1. Configure as variáveis de ambiente no .env")
    print("2. Execute os testes: pytest tests/test_dynamo_store.py")
    print("3. Inicie a aplicação: uvicorn app.api.main:app --reload")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
