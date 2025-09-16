#!/usr/bin/env python3
"""
Script de teste local para verificar se a aplicação está funcionando
"""
import asyncio
import os
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

async def test_semantic_classification():
    """Teste da classificação semântica"""
    print("🧠 Testando classificação semântica...")
    
    try:
        from app.graph.semantic_classifier import classify_semantic, IntentType
        from app.graph.state import GraphState, CoreState
        
        # Criar estado de teste
        estado = GraphState(
            core=CoreState(session_id="test_session", numero_telefone="+5511999999999")
        )
        
        # Testes de classificação
        testes = [
            ("cheguei no local", IntentType.CONFIRMAR_PRESENCA),
            ("PA 120x80, FC 78", IntentType.SINAIS_VITAIS),
            ("paciente consciente", IntentType.NOTA_CLINICA),
            ("sim, confirmo", IntentType.CONFIRMACAO_SIM),
            ("não quero", IntentType.CONFIRMACAO_NAO),
            ("quero finalizar", IntentType.FINALIZAR_PLANTAO)
        ]
        
        for texto, intent_esperado in testes:
            try:
                resultado = await classify_semantic(texto, estado)
                status = "✅" if resultado.intent == intent_esperado else "❌"
                print(f"  {status} '{texto}' → {resultado.intent} (conf: {resultado.confidence:.2f})")
            except Exception as e:
                print(f"  ❌ '{texto}' → ERRO: {e}")
        
        print("✅ Classificação semântica funcionando!\n")
        return True
        
    except Exception as e:
        print(f"❌ Erro na classificação semântica: {e}\n")
        return False


async def test_clinical_extraction():
    """Teste da extração de sinais vitais"""
    print("🩺 Testando extração de sinais vitais...")
    
    try:
        from app.graph.clinical_extractor import extrair_sinais_vitais_semanticos
        
        texto = "PA 130x80, FC 85, FR 18, Sat 98%, Temp 36.8"
        resultado = await extrair_sinais_vitais_semanticos(texto)
        
        print(f"  Processados: {resultado.processados}")
        print(f"  Faltantes: {resultado.faltantes}")
        
        if resultado.processados:
            print("✅ Extração de sinais vitais funcionando!\n")
            return True
        else:
            print("❌ Nenhum sinal vital extraído\n")
            return False
            
    except Exception as e:
        print(f"❌ Erro na extração: {e}\n")
        return False


async def test_confirmation():
    """Teste de confirmação semântica"""
    print("✅ Testando confirmação semântica...")
    
    try:
        from app.infra.confirm import is_yes_semantic, is_no_semantic
        
        testes_sim = ["sim", "ok", "confirmo", "pode ser"]
        testes_nao = ["não", "cancelar", "negativo"]
        
        for texto in testes_sim:
            resultado = await is_yes_semantic(texto)
            status = "✅" if resultado else "❌"
            print(f"  {status} '{texto}' → SIM: {resultado}")
        
        for texto in testes_nao:
            resultado = await is_no_semantic(texto)
            status = "✅" if resultado else "❌"
            print(f"  {status} '{texto}' → NÃO: {resultado}")
        
        print("✅ Confirmação semântica funcionando!\n")
        return True
        
    except Exception as e:
        print(f"❌ Erro na confirmação: {e}\n")
        return False


def test_environment():
    """Teste das variáveis de ambiente"""
    print("🔧 Testando configuração...")
    
    variaveis_obrigatorias = [
        "OPENAI_API_KEY",
        "LAMBDA_GET_SCHEDULE", 
        "LAMBDA_UPDATE_SCHEDULE",
        "LAMBDA_UPDATE_CLINICAL",
        "LAMBDA_UPDATE_SUMMARY"
    ]
    
    variaveis_opcionais = [
        "REDIS_URL",
        "PINECONE_API_KEY",
        "GOOGLE_SHEETS_ID"
    ]
    
    config_ok = True
    
    for var in variaveis_obrigatorias:
        valor = os.getenv(var)
        if valor and valor != f"YOUR_{var}_HERE":
            print(f"  ✅ {var}: configurado")
        else:
            print(f"  ❌ {var}: NÃO CONFIGURADO (obrigatório)")
            config_ok = False
    
    for var in variaveis_opcionais:
        valor = os.getenv(var)
        if valor and valor != f"YOUR_{var}_HERE":
            print(f"  ✅ {var}: configurado")
        else:
            print(f"  ⚠️  {var}: não configurado (opcional)")
    
    print(f"\n{'✅ Configuração OK!' if config_ok else '❌ Configuração incompleta!'}\n")
    return config_ok


async def test_api_startup():
    """Teste de inicialização da API"""
    print("🚀 Testando inicialização da API...")
    
    try:
        from app.api.main import app
        print("✅ FastAPI importado com sucesso")
        
        # Testar importação de dependências críticas
        from app.graph.builder import criar_grafo
        print("✅ LangGraph builder importado")
        
        from app.graph.semantic_classifier import classify_semantic
        print("✅ Classificador semântico importado")
        
        from app.infra.redis_client import obter_cliente_redis
        print("✅ Redis client importado")
        
        print("✅ API pronta para inicialização!\n")
        return True
        
    except Exception as e:
        print(f"❌ Erro na inicialização: {e}\n")
        return False


async def main():
    """Executa todos os testes"""
    print("🧪 TESTE LOCAL - WhatsApp Orchestrator")
    print("=" * 50)
    
    # Teste 1: Configuração
    config_ok = test_environment()
    
    if not config_ok:
        print("❌ Configure as variáveis obrigatórias no .env antes de continuar")
        print("📖 Veja CONFIGURACAO_LOCAL.md para instruções detalhadas")
        return
    
    # Teste 2: Inicialização
    api_ok = await test_api_startup()
    if not api_ok:
        return
    
    # Teste 3: Classificação semântica
    semantic_ok = await test_semantic_classification()
    if not semantic_ok:
        print("❌ Verifique sua OPENAI_API_KEY")
        return
    
    # Teste 4: Extração clínica
    clinical_ok = await test_clinical_extraction()
    
    # Teste 5: Confirmação
    confirm_ok = await test_confirmation()
    
    # Resultado final
    print("🎉 RESULTADO FINAL")
    print("=" * 50)
    
    if semantic_ok and clinical_ok and confirm_ok:
        print("✅ TODOS OS TESTES PASSARAM!")
        print("\n🚀 Para executar a aplicação:")
        print("   uvicorn app.api.main:app --reload")
        print("\n🧪 Para testar endpoints:")
        print("   curl -X POST http://localhost:8000/webhook/whatsapp \\")
        print("     -H 'Content-Type: application/json' \\")
        print("     -d '{\"message_id\":\"test\",\"phoneNumber\":\"+5511999999999\",\"text\":\"cheguei\"}'")
    else:
        print("❌ Alguns testes falharam. Verifique a configuração.")
    
    print("\n📖 Veja CONFIGURACAO_LOCAL.md para mais detalhes")


if __name__ == "__main__":
    asyncio.run(main())
