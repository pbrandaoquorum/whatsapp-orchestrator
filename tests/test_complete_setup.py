#!/usr/bin/env python3
"""
Teste completo de setup para WhatsApp Orchestrator com DynamoDB
Simula ambiente de produção local
"""
import asyncio
import os
import sys
import json
from datetime import datetime
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

async def test_environment_variables():
    """Teste de variáveis de ambiente obrigatórias"""
    print("🔧 Testando variáveis de ambiente...")
    
    required_vars = {
        'AWS_REGION': 'Região AWS para DynamoDB',
        'OPENAI_API_KEY': 'Chave OpenAI para classificação semântica',
        'LAMBDA_GET_SCHEDULE': 'URL Lambda para obter agenda',
        'LAMBDA_UPDATE_SCHEDULE': 'URL Lambda para atualizar agenda', 
        'LAMBDA_UPDATE_CLINICAL': 'URL Lambda para dados clínicos',
        'LAMBDA_UPDATE_SUMMARY': 'URL Lambda para relatório final'
    }
    
    missing = []
    for var, description in required_vars.items():
        if not os.getenv(var):
            missing.append(f"  ❌ {var}: {description}")
        else:
            print(f"  ✅ {var}: configurado")
    
    if missing:
        print("\n⚠️  Variáveis OBRIGATÓRIAS faltando:")
        for m in missing:
            print(m)
        return False
    
    print("✅ Todas as variáveis obrigatórias configuradas")
    return True


async def test_imports():
    """Teste de importações críticas"""
    print("\n📦 Testando importações...")
    
    try:
        # Core modules
        from app.graph.state import GraphState, CoreState
        print("  ✅ GraphState importado")
        
        from app.graph.builder import criar_grafo
        print("  ✅ LangGraph builder importado")
        
        from app.graph.semantic_classifier import classify_semantic
        print("  ✅ Classificador semântico importado")
        
        # DynamoDB infrastructure
        from app.infra.dynamo_client import get_dynamo_client, health_check
        print("  ✅ DynamoDB client importado")
        
        from app.infra.store import SessionStore, PendingActionsStore
        print("  ✅ DynamoDB stores importados")
        
        from app.infra.state_persistence import StateManager
        print("  ✅ State persistence importado")
        
        from app.infra.locks import acquire_session_lock
        print("  ✅ Distributed locks importado")
        
        from app.infra.idempotency import idempotent
        print("  ✅ Idempotency system importado")
        
        from app.infra.memory import add_user_message, get_conversation_window
        print("  ✅ Conversation memory importado")
        
        # API modules
        from app.api.main import app
        print("  ✅ FastAPI app importado")
        
        from app.api.routes_dynamo import router
        print("  ✅ DynamoDB routes importado")
        
        print("✅ Todas as importações funcionaram")
        return True
        
    except ImportError as e:
        print(f"❌ Erro de importação: {e}")
        return False


async def test_dynamodb_connection():
    """Teste de conexão com DynamoDB"""
    print("\n🗄️  Testando conexão com DynamoDB...")
    
    try:
        from app.infra.dynamo_client import health_check, get_all_table_names, validate_table_exists
        
        # Health check geral
        health = await health_check()
        print(f"  Status: {health['status']}")
        
        if health["status"] != "healthy":
            print("❌ DynamoDB não está saudável")
            if "missing_tables" in health and health["missing_tables"]:
                print(f"  Tabelas faltando: {health['missing_tables']}")
                print("  💡 Execute: python scripts/create_dynamo_tables.py")
            return False
        
        # Verificar tabelas individualmente
        table_names = get_all_table_names()
        print(f"  Verificando {len(table_names)} tabelas...")
        
        for table_name in table_names:
            exists = validate_table_exists(table_name)
            if exists:
                print(f"    ✅ {table_name}: OK")
            else:
                print(f"    ❌ {table_name}: Não encontrada")
                return False
        
        print("✅ DynamoDB conectado e todas as tabelas encontradas")
        return True
        
    except Exception as e:
        print(f"❌ Erro ao conectar com DynamoDB: {e}")
        return False


async def test_stores_functionality():
    """Teste funcionalidade básica dos stores"""
    print("\n🏪 Testando funcionalidade dos stores...")
    
    try:
        from app.infra.store import SessionStore, IdempotencyStore
        
        # Test SessionStore
        session_store = SessionStore()
        test_session = "test_session_" + str(int(datetime.now().timestamp()))
        
        # Deve retornar None para sessão inexistente
        state, version = session_store.get(test_session)
        if state is None and version == 0:
            print("  ✅ SessionStore: busca de sessão inexistente OK")
        else:
            print("  ❌ SessionStore: comportamento inesperado")
            return False
        
        # Test IdempotencyStore
        idempotency_store = IdempotencyStore()
        test_key = "test_key_" + str(int(datetime.now().timestamp()))
        
        # Deve permitir primeira operação
        can_begin = idempotency_store.begin(test_key, test_session, 60)
        if can_begin:
            print("  ✅ IdempotencyStore: primeira operação permitida")
            # Limpar teste
            idempotency_store.end_ok(test_key, '{"test": true}')
        else:
            print("  ❌ IdempotencyStore: primeira operação negada")
            return False
        
        print("✅ Stores funcionando corretamente")
        return True
        
    except Exception as e:
        print(f"❌ Erro ao testar stores: {e}")
        return False


async def test_graph_creation():
    """Teste criação do grafo LangGraph"""
    print("\n🕸️  Testando criação do grafo...")
    
    try:
        from app.graph.builder import criar_grafo, validar_grafo
        
        # Criar grafo
        grafo = criar_grafo()
        print("  ✅ Grafo criado com sucesso")
        
        # Validar grafo
        is_valid = validar_grafo(grafo)
        if is_valid:
            print("  ✅ Grafo validado com sucesso")
        else:
            print("  ❌ Grafo não passou na validação")
            return False
        
        print("✅ Grafo LangGraph funcionando")
        return True
        
    except Exception as e:
        print(f"❌ Erro ao criar grafo: {e}")
        return False


async def test_semantic_classification():
    """Teste classificação semântica"""
    print("\n🧠 Testando classificação semântica...")
    
    try:
        from app.graph.semantic_classifier import classify_semantic, IntentType
        from app.graph.state import GraphState, CoreState
        
        # Criar estado de teste
        estado = GraphState(
            core=CoreState(
                session_id="test_session",
                numero_telefone="+5511999999999"
            )
        )
        
        # Teste simples de classificação
        resultado = await classify_semantic("cheguei no local", estado)
        
        if resultado and resultado.intent:
            print(f"  ✅ Classificação funcionando: {resultado.intent}")
            print(f"  Confiança: {resultado.confidence}")
        else:
            print("  ❌ Classificação não retornou resultado válido")
            return False
        
        print("✅ Classificação semântica funcionando")
        return True
        
    except Exception as e:
        print(f"❌ Erro na classificação semântica: {e}")
        print("  💡 Verifique se OPENAI_API_KEY está configurado")
        return False


async def test_state_management():
    """Teste gerenciamento de estado"""
    print("\n📊 Testando gerenciamento de estado...")
    
    try:
        from app.infra.state_persistence import StateManager
        from app.graph.state import GraphState, CoreState
        
        # Criar gerenciador de estado
        test_session = "test_state_" + str(int(datetime.now().timestamp()))
        manager = StateManager(test_session)
        
        # Carregar estado (deve criar novo)
        estado = await manager.load_state()
        if estado and estado.core.session_id == test_session:
            print("  ✅ Estado carregado/criado com sucesso")
        else:
            print("  ❌ Erro ao carregar estado")
            return False
        
        # Modificar e salvar estado
        estado.metadados = {"test": True}
        sucesso = await manager.save_state()
        
        if sucesso:
            print("  ✅ Estado salvo com sucesso")
        else:
            print("  ❌ Erro ao salvar estado")
            return False
        
        print("✅ Gerenciamento de estado funcionando")
        return True
        
    except Exception as e:
        print(f"❌ Erro no gerenciamento de estado: {e}")
        return False


async def test_memory_system():
    """Teste sistema de memória"""
    print("\n🧠 Testando sistema de memória...")
    
    try:
        from app.infra.memory import add_user_message, add_assistant_message, get_conversation_window
        
        test_session = "test_memory_" + str(int(datetime.now().timestamp()))
        
        # Adicionar mensagens
        add_user_message(test_session, "Olá, como está?", {"test": True})
        add_assistant_message(test_session, "Olá! Estou bem, obrigado.", {"test": True})
        
        # Recuperar conversação
        messages = get_conversation_window(test_session, 10)
        
        if len(messages) >= 2:
            print(f"  ✅ {len(messages)} mensagens recuperadas")
            # Verificar ordem (mais recente primeiro na busca, mas cronológica no resultado)
            if messages[0]["role"] == "user" and messages[1]["role"] == "assistant":
                print("  ✅ Ordem das mensagens correta")
            else:
                print("  ❌ Ordem das mensagens incorreta")
                return False
        else:
            print("  ❌ Mensagens não foram recuperadas")
            return False
        
        print("✅ Sistema de memória funcionando")
        return True
        
    except Exception as e:
        print(f"❌ Erro no sistema de memória: {e}")
        return False


async def test_api_startup():
    """Teste inicialização da API"""
    print("\n🚀 Testando inicialização da API...")
    
    try:
        from app.api.main import app
        
        # Verificar se app foi criado
        if app:
            print("  ✅ FastAPI app criado")
        else:
            print("  ❌ Erro ao criar FastAPI app")
            return False
        
        # Verificar rotas
        routes = [route.path for route in app.routes]
        expected_routes = ["/webhook/ingest", "/hooks/template-fired", "/healthz", "/readyz"]
        
        missing_routes = []
        for route in expected_routes:
            if not any(route in r for r in routes):
                missing_routes.append(route)
        
        if missing_routes:
            print(f"  ❌ Rotas faltando: {missing_routes}")
            return False
        else:
            print("  ✅ Todas as rotas essenciais encontradas")
        
        print("✅ API pronta para inicialização")
        return True
        
    except Exception as e:
        print(f"❌ Erro na inicialização da API: {e}")
        return False


async def run_complete_workflow_test():
    """Teste de workflow completo simulado"""
    print("\n🔄 Testando workflow completo...")
    
    try:
        from app.infra.state_persistence import StateManager
        from app.infra.memory import add_user_message, add_assistant_message
        from app.infra.locks import acquire_session_lock
        from app.graph.builder import criar_grafo
        from app.graph.state import GraphState, CoreState
        
        test_session = "test_workflow_" + str(int(datetime.now().timestamp()))
        
        # 1. Adquirir lock
        async with acquire_session_lock(test_session) as locked:
            if not locked:
                print("  ❌ Não foi possível adquirir lock")
                return False
            print("  ✅ Lock adquirido")
            
            # 2. Gerenciar estado
            manager = StateManager(test_session)
            estado = await manager.load_state()
            print("  ✅ Estado carregado")
            
            # 3. Adicionar mensagem do usuário
            add_user_message(test_session, "cheguei no local", {"test": True})
            print("  ✅ Mensagem do usuário adicionada")
            
            # 4. Processar com grafo (simulado)
            estado.texto_usuario = "cheguei no local"
            grafo = criar_grafo()
            
            # Simular processamento sem executar (para evitar dependências externas)
            estado.resposta_usuario = "Presença confirmada! Como posso ajudar?"
            print("  ✅ Processamento simulado")
            
            # 5. Salvar estado
            sucesso = await manager.save_state()
            if not sucesso:
                print("  ❌ Erro ao salvar estado")
                return False
            print("  ✅ Estado salvo")
            
            # 6. Adicionar resposta do assistente
            add_assistant_message(test_session, estado.resposta_usuario, {"test": True})
            print("  ✅ Resposta do assistente adicionada")
        
        print("  ✅ Lock liberado automaticamente")
        print("✅ Workflow completo funcionando")
        return True
        
    except Exception as e:
        print(f"❌ Erro no workflow completo: {e}")
        return False


async def main():
    """Função principal de teste"""
    print("🚀 TESTE COMPLETO DE SETUP - WhatsApp Orchestrator")
    print("=" * 60)
    print("Simulando ambiente de produção local com DynamoDB")
    print("=" * 60)
    
    tests = [
        ("Variáveis de Ambiente", test_environment_variables),
        ("Importações", test_imports),
        ("Conexão DynamoDB", test_dynamodb_connection),
        ("Funcionalidade Stores", test_stores_functionality),
        ("Criação do Grafo", test_graph_creation),
        ("Classificação Semântica", test_semantic_classification),
        ("Gerenciamento de Estado", test_state_management),
        ("Sistema de Memória", test_memory_system),
        ("Inicialização da API", test_api_startup),
        ("Workflow Completo", run_complete_workflow_test),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            print(f"\n{'='*20} {test_name} {'='*20}")
            result = await test_func()
            results.append((test_name, result))
            
            if result:
                print(f"✅ {test_name}: PASSOU")
            else:
                print(f"❌ {test_name}: FALHOU")
                
        except Exception as e:
            print(f"❌ ERRO CRÍTICO em {test_name}: {e}")
            results.append((test_name, False))
    
    # Resumo final
    print("\n" + "=" * 60)
    print("📋 RESUMO FINAL DOS TESTES")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASSOU" if result else "❌ FALHOU"
        print(f"{test_name:.<35} {status}")
    
    print(f"\nResultado: {passed}/{total} testes passaram")
    
    if passed == total:
        print("\n🎉 TODOS OS TESTES PASSARAM!")
        print("\n🚀 Sistema pronto para produção local!")
        print("\n📝 Próximos passos:")
        print("1. Execute: uvicorn app.api.main:app --reload")
        print("2. Teste os endpoints:")
        print("   curl -X POST http://localhost:8000/webhook/ingest \\")
        print("     -H 'Content-Type: application/json' \\")
        print("     -H 'X-Idempotency-Key: test-123' \\")
        print("     -d '{\"message_id\":\"test\",\"phoneNumber\":\"+5511999999999\",\"text\":\"cheguei\"}'")
        print("3. Monitore logs e métricas")
        
        return 0
    else:
        failed_count = total - passed
        print(f"\n⚠️  {failed_count} teste(s) falharam")
        print("\n🔧 Ações necessárias:")
        
        failed_tests = [name for name, result in results if not result]
        
        if "Variáveis de Ambiente" in failed_tests:
            print("- Configure todas as variáveis obrigatórias no .env")
        
        if "Conexão DynamoDB" in failed_tests:
            print("- Verifique credenciais AWS (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)")
            print("- Execute: python scripts/create_dynamo_tables.py")
        
        if "Classificação Semântica" in failed_tests:
            print("- Verifique OPENAI_API_KEY")
        
        if any(test in failed_tests for test in ["Funcionalidade Stores", "Gerenciamento de Estado"]):
            print("- Verifique se todas as tabelas DynamoDB foram criadas")
            print("- Verifique permissões IAM")
        
        print(f"\nCorrija os problemas e execute novamente: python {__file__}")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
