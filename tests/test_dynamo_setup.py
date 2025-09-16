#!/usr/bin/env python3
"""
Script de teste para validar setup completo do DynamoDB
"""
import os
import sys
import asyncio
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

async def test_imports():
    """Teste de importações básicas"""
    print("🧪 Testando importações...")
    
    try:
        from app.infra.dynamo_client import get_dynamo_client, health_check
        from app.infra.store import SessionStore, PendingActionsStore, ConversationBufferStore, LockStore, IdempotencyStore
        from app.infra.state_persistence import StateManager
        from app.infra.locks import acquire_session_lock
        from app.infra.memory import add_user_message, get_conversation_window
        from app.infra.idempotency import idempotent
        from app.infra.tpc import criar_acao_pendente
        from app.infra.resume import set_resume_after
        from app.graph.state import GraphState
        
        print("✅ Todas as importações funcionaram")
        return True
        
    except ImportError as e:
        print(f"❌ Erro de importação: {e}")
        return False


async def test_environment():
    """Teste de variáveis de ambiente"""
    print("\n🔧 Testando configuração de ambiente...")
    
    required_vars = [
        'AWS_REGION',
        'OPENAI_API_KEY'
    ]
    
    optional_vars = [
        'AWS_ACCESS_KEY_ID',
        'AWS_SECRET_ACCESS_KEY',
        'DDB_TABLE_SESSIONS',
        'DDB_TABLE_PENDING_ACTIONS',
        'DDB_TABLE_CONV_BUFFER',
        'DDB_TABLE_LOCKS',
        'DDB_TABLE_IDEMPOTENCY'
    ]
    
    missing_required = []
    missing_optional = []
    
    for var in required_vars:
        if not os.getenv(var):
            missing_required.append(var)
        else:
            print(f"✅ {var}: configurado")
    
    for var in optional_vars:
        if not os.getenv(var):
            missing_optional.append(var)
        else:
            print(f"✅ {var}: configurado")
    
    if missing_required:
        print(f"\n❌ Variáveis OBRIGATÓRIAS faltando: {missing_required}")
        return False
    
    if missing_optional:
        print(f"\n⚠️  Variáveis opcionais faltando: {missing_optional}")
    
    print("✅ Configuração de ambiente OK")
    return True


async def test_dynamo_connection():
    """Teste de conexão com DynamoDB"""
    print("\n🔗 Testando conexão com DynamoDB...")
    
    try:
        from app.infra.dynamo_client import health_check
        
        health = await health_check()
        
        if health["status"] == "healthy":
            print("✅ Conexão com DynamoDB estabelecida")
            
            missing_tables = health.get("missing_tables", [])
            if missing_tables:
                print(f"⚠️  Tabelas faltando: {missing_tables}")
                print("💡 Execute: python scripts/create_dynamo_tables.py")
                return False
            else:
                print("✅ Todas as tabelas DynamoDB encontradas")
            
            return True
        else:
            print(f"❌ DynamoDB não está saudável: {health}")
            return False
            
    except Exception as e:
        print(f"❌ Erro ao conectar com DynamoDB: {e}")
        return False


async def test_stores():
    """Teste básico dos stores"""
    print("\n🗄️  Testando stores básicos...")
    
    try:
        from app.infra.store import SessionStore, IdempotencyStore
        
        # Teste SessionStore
        session_store = SessionStore()
        state, version = session_store.get("test_session_nonexistent")
        
        if state is None and version == 0:
            print("✅ SessionStore funcionando")
        else:
            print("❌ SessionStore retornou dados inesperados")
            return False
        
        # Teste IdempotencyStore
        idempotency_store = IdempotencyStore()
        can_begin = idempotency_store.begin("test_key", "test_session", 60)
        
        if can_begin:
            print("✅ IdempotencyStore funcionando")
            # Limpar teste
            idempotency_store.end_ok("test_key", '{"test": true}')
        else:
            print("❌ IdempotencyStore não permitiu operação")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ Erro ao testar stores: {e}")
        return False


async def test_state_model():
    """Teste do modelo de estado"""
    print("\n📊 Testando modelo de estado...")
    
    try:
        from app.graph.state import GraphState, CoreState
        
        # Criar estado
        estado = GraphState(
            core=CoreState(
                session_id="test_session",
                numero_telefone="+5511999999999"
            ),
            version=1
        )
        
        # Testar serialização
        state_dict = estado.dict()
        
        if "version" in state_dict and state_dict["version"] == 1:
            print("✅ Modelo de estado com versão funcionando")
            return True
        else:
            print("❌ Campo version não encontrado no estado")
            return False
            
    except Exception as e:
        print(f"❌ Erro ao testar modelo de estado: {e}")
        return False


async def test_memory_system():
    """Teste do sistema de memória"""
    print("\n🧠 Testando sistema de memória...")
    
    try:
        from app.infra.memory import add_user_message, get_conversation_window
        
        session_id = "test_memory_session"
        
        # Adicionar mensagem
        add_user_message(session_id, "Teste de mensagem", {"test": True})
        
        # Recuperar mensagens
        messages = get_conversation_window(session_id, 5)
        
        if len(messages) >= 1:
            print("✅ Sistema de memória funcionando")
            return True
        else:
            print("❌ Mensagem não foi recuperada")
            return False
            
    except Exception as e:
        print(f"❌ Erro ao testar sistema de memória: {e}")
        return False


async def main():
    """Função principal de teste"""
    print("🚀 Teste de Setup DynamoDB - WhatsApp Orchestrator")
    print("=" * 60)
    
    tests = [
        ("Importações", test_imports),
        ("Ambiente", test_environment),
        ("Conexão DynamoDB", test_dynamo_connection),
        ("Stores", test_stores),
        ("Modelo de Estado", test_state_model),
        ("Sistema de Memória", test_memory_system),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            result = await test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ Erro crítico no teste {test_name}: {e}")
            results.append((test_name, False))
    
    # Resumo final
    print("\n" + "=" * 60)
    print("📋 RESUMO DOS TESTES")
    print("=" * 60)
    
    passed = 0
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASSOU" if result else "❌ FALHOU"
        print(f"{test_name:.<30} {status}")
        if result:
            passed += 1
    
    print(f"\nResultado: {passed}/{total} testes passaram")
    
    if passed == total:
        print("\n🎉 TODOS OS TESTES PASSARAM!")
        print("\n📝 Próximos passos:")
        print("1. Execute: uvicorn app.api.main:app --reload")
        print("2. Teste os endpoints com curl ou Postman")
        print("3. Execute os testes unitários: pytest tests/test_dynamo_store.py -v")
        return 0
    else:
        print(f"\n⚠️  {total - passed} teste(s) falharam")
        print("\n🔧 Ações necessárias:")
        
        failed_tests = [name for name, result in results if not result]
        
        if "Ambiente" in failed_tests:
            print("- Configure as variáveis de ambiente no .env")
        
        if "Conexão DynamoDB" in failed_tests:
            print("- Verifique credenciais AWS")
            print("- Execute: python scripts/create_dynamo_tables.py")
        
        if any(test in failed_tests for test in ["Stores", "Modelo de Estado", "Sistema de Memória"]):
            print("- Verifique se as tabelas DynamoDB foram criadas")
            print("- Verifique permissões IAM")
        
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
