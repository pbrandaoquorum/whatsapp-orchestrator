#!/usr/bin/env python3
"""
Script para criar tabelas DynamoDB necessárias para o WhatsApp Orchestrator
"""
import boto3
import os
import sys
from botocore.exceptions import ClientError
from dotenv import load_dotenv

# Carrega variáveis de ambiente
load_dotenv()


def get_dynamodb_client():
    """Cria cliente DynamoDB"""
    region = os.getenv("AWS_REGION", "sa-east-1")
    
    # Configurações AWS
    session = boto3.Session(
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        region_name=region
    )
    
    return session.client('dynamodb')


def create_conversation_state_table(dynamodb_client, table_name="ConversationStates"):
    """
    Cria tabela para armazenar estados das conversações do LangGraph
    
    Schema:
    - PK: session_id (String) - ID da sessão (telefone normalizado)
    - estado (Binary) - GraphState serializado em JSON
    - atualizadoEm (String) - timestamp ISO da última atualização
    """
    
    try:
        print(f"🚀 Criando tabela {table_name}...")
        
        response = dynamodb_client.create_table(
            TableName=table_name,
            KeySchema=[
                {
                    'AttributeName': 'session_id',
                    'KeyType': 'HASH'  # Partition key
                }
            ],
            AttributeDefinitions=[
                {
                    'AttributeName': 'session_id',
                    'AttributeType': 'S'  # String
                }
            ],
            BillingMode='PAY_PER_REQUEST',  # On-demand pricing
            Tags=[
                {
                    'Key': 'Project',
                    'Value': 'WhatsAppOrchestrator'
                },
                {
                    'Key': 'Purpose',
                    'Value': 'LangGraphState'
                },
                {
                    'Key': 'Environment',
                    'Value': os.getenv('ENVIRONMENT', 'development')
                }
            ]
        )
        
        print(f"✅ Tabela {table_name} criada com sucesso!")
        print(f"📋 ARN: {response['TableDescription']['TableArn']}")
        return True
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        
        if error_code == 'ResourceInUseException':
            print(f"⚠️  Tabela {table_name} já existe")
            return True
        else:
            print(f"❌ Erro ao criar tabela {table_name}: {e.response['Error']['Message']}")
            return False
    except Exception as e:
        print(f"❌ Erro inesperado ao criar tabela {table_name}: {str(e)}")
        return False


def wait_for_table_active(dynamodb_client, table_name, max_attempts=30):
    """Aguarda tabela ficar ativa"""
    print(f"⏳ Aguardando tabela {table_name} ficar ativa...")
    
    for attempt in range(max_attempts):
        try:
            response = dynamodb_client.describe_table(TableName=table_name)
            status = response['Table']['TableStatus']
            
            if status == 'ACTIVE':
                print(f"✅ Tabela {table_name} está ativa!")
                return True
            elif status == 'CREATING':
                print(f"🔄 Tentativa {attempt + 1}/{max_attempts} - Status: {status}")
                import time
                time.sleep(2)
            else:
                print(f"⚠️  Status inesperado: {status}")
                return False
                
        except ClientError as e:
            print(f"❌ Erro ao verificar status da tabela: {e.response['Error']['Message']}")
            return False
    
    print(f"⏰ Timeout aguardando tabela {table_name} ficar ativa")
    return False


def verify_table_access(dynamodb_client, table_name):
    """Verifica se conseguimos acessar a tabela"""
    try:
        print(f"🔍 Testando acesso à tabela {table_name}...")
        
        # Tenta fazer uma operação de leitura (scan vazio)
        response = dynamodb_client.scan(
            TableName=table_name,
            Limit=1
        )
        
        print(f"✅ Acesso à tabela {table_name} confirmado!")
        print(f"📊 Itens na tabela: {response['Count']}")
        return True
        
    except ClientError as e:
        print(f"❌ Erro ao acessar tabela {table_name}: {e.response['Error']['Message']}")
        return False


def main():
    """Função principal"""
    print("🚀 Criando tabelas DynamoDB para WhatsApp Orchestrator")
    print("=" * 60)
    
    # Verifica variáveis de ambiente
    required_vars = ["AWS_REGION", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        print("❌ Variáveis de ambiente faltando:")
        for var in missing_vars:
            print(f"   - {var}")
        print("\n💡 Configure essas variáveis no arquivo .env")
        return False
    
    # Cria cliente DynamoDB
    try:
        dynamodb = get_dynamodb_client()
        region = os.getenv("AWS_REGION")
        print(f"🔗 Conectado ao DynamoDB na região: {region}")
    except Exception as e:
        print(f"❌ Erro ao conectar com DynamoDB: {str(e)}")
        return False
    
    # Nome da tabela (pode ser customizado via env)
    table_name = os.getenv("DYNAMODB_TABLE_CONVERSAS", "ConversationStates")
    print(f"📋 Nome da tabela: {table_name}")
    
    success = True
    
    # 1. Cria tabela de estados das conversações
    if not create_conversation_state_table(dynamodb, table_name):
        success = False
    
    # 2. Aguarda tabela ficar ativa
    if success:
        if not wait_for_table_active(dynamodb, table_name):
            success = False
    
    # 3. Testa acesso à tabela
    if success:
        if not verify_table_access(dynamodb, table_name):
            success = False
    
    # Resultado final
    print("\n" + "=" * 60)
    if success:
        print("🎉 Todas as tabelas foram criadas com sucesso!")
        print("\n📋 Resumo das tabelas criadas:")
        print(f"   - {table_name} (Estados das conversações)")
        print("\n💡 Próximos passos:")
        print("   1. Configure as demais variáveis no .env")
        print("   2. Execute: uvicorn app.api.main:app --reload")
        print("   3. Teste: curl http://localhost:8000/readyz")
        return True
    else:
        print("❌ Falha na criação das tabelas DynamoDB")
        print("💡 Verifique os erros acima e tente novamente")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
