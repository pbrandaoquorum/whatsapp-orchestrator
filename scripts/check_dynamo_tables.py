#!/usr/bin/env python3
"""
Script para verificar status das tabelas DynamoDB
"""
import boto3
import os
from botocore.exceptions import ClientError
from dotenv import load_dotenv

# Carrega variáveis de ambiente
load_dotenv()


def get_dynamodb_client():
    """Cria cliente DynamoDB"""
    region = os.getenv("AWS_REGION", "sa-east-1")
    
    session = boto3.Session(
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        region_name=region
    )
    
    return session.client('dynamodb')


def check_table_status(dynamodb_client, table_name):
    """Verifica status de uma tabela"""
    try:
        response = dynamodb_client.describe_table(TableName=table_name)
        table_info = response['Table']
        
        print(f"📋 Tabela: {table_name}")
        print(f"   Status: {table_info['TableStatus']}")
        print(f"   Criação: {table_info['CreationDateTime']}")
        print(f"   ARN: {table_info['TableArn']}")
        print(f"   Billing Mode: {table_info.get('BillingModeSummary', {}).get('BillingMode', 'PROVISIONED')}")
        
        # Verifica chaves
        key_schema = table_info['KeySchema']
        for key in key_schema:
            key_type = "Partition Key" if key['KeyType'] == 'HASH' else "Sort Key"
            print(f"   {key_type}: {key['AttributeName']}")
        
        # Testa acesso (scan vazio)
        try:
            scan_response = dynamodb_client.scan(TableName=table_name, Limit=1)
            item_count = scan_response['Count']
            print(f"   Itens (amostra): {item_count}")
            print("   ✅ Acesso confirmado")
        except ClientError as e:
            print(f"   ❌ Erro de acesso: {e.response['Error']['Message']}")
        
        return table_info['TableStatus'] == 'ACTIVE'
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'ResourceNotFoundException':
            print(f"❌ Tabela {table_name} não encontrada")
        else:
            print(f"❌ Erro ao verificar tabela {table_name}: {e.response['Error']['Message']}")
        return False
    except Exception as e:
        print(f"❌ Erro inesperado: {str(e)}")
        return False


def list_all_tables(dynamodb_client):
    """Lista todas as tabelas DynamoDB"""
    try:
        response = dynamodb_client.list_tables()
        tables = response['TableNames']
        
        print(f"📊 Total de tabelas na região: {len(tables)}")
        if tables:
            print("📋 Tabelas encontradas:")
            for table in sorted(tables):
                print(f"   - {table}")
        return tables
    except Exception as e:
        print(f"❌ Erro ao listar tabelas: {str(e)}")
        return []


def main():
    """Função principal"""
    print("🔍 Verificando tabelas DynamoDB")
    print("=" * 50)
    
    # Verifica variáveis de ambiente
    required_vars = ["AWS_REGION", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        print("❌ Variáveis de ambiente faltando:")
        for var in missing_vars:
            print(f"   - {var}")
        return False
    
    # Conecta ao DynamoDB
    try:
        dynamodb = get_dynamodb_client()
        region = os.getenv("AWS_REGION")
        print(f"🔗 Conectado ao DynamoDB na região: {region}")
        print()
    except Exception as e:
        print(f"❌ Erro ao conectar com DynamoDB: {str(e)}")
        return False
    
    # Lista todas as tabelas
    all_tables = list_all_tables(dynamodb)
    print()
    
    # Verifica tabela específica do LangGraph
    table_name = os.getenv("DYNAMODB_TABLE_CONVERSAS", "ConversationStates")
    print(f"🎯 Verificando tabela específica: {table_name}")
    print("-" * 50)
    
    table_ok = check_table_status(dynamodb, table_name)
    
    print("\n" + "=" * 50)
    if table_ok:
        print("✅ Tabela está funcionando corretamente!")
    else:
        print("❌ Problemas encontrados com a tabela")
        print("💡 Execute: python scripts/create_dynamo_tables.py")
    
    return table_ok


if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)
