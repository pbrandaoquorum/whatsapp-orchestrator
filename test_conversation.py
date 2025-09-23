#!/usr/bin/env python3
"""
Teste de Conversa Completa - WhatsApp Orchestrator
Testa uma conversa completa com session ID real configurado
"""

import sys
sys.path.insert(0, '.')

from test_production import ProductionTester

def main():
    """Executa apenas o teste de conversa completa"""
    print("🗣️ TESTE DE CONVERSA COMPLETA - WhatsApp Orchestrator")
    print("📱 Session ID: 5511991261390 (com escala real configurada)")
    print("=" * 60)
    
    # Verificar se servidor está ativo
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
    
    tester = ProductionTester(base_url)
    
    try:
        import requests
        response = requests.get(f"{base_url}/healthz", timeout=5)
        if response.status_code != 200:
            print("❌ Servidor não está respondendo corretamente")
            return 1
        print("✅ Servidor ativo!")
    except:
        print(f"❌ Servidor não está rodando em {base_url}")
        print("💡 Execute: uvicorn app.api.main:app --host 127.0.0.1 --port 8000")
        return 1
    
    print()
    
    try:
        # Executar apenas o teste de conversa completa
        success = tester.test_complete_conversation_flow()
        
        print("\n" + "=" * 60)
        if success:
            print("🎉 CONVERSA COMPLETA: APROVADA!")
            print("✅ O contexto está sendo mantido corretamente entre mensagens")
            print("✅ Fluxo completo funciona com dados reais")
        else:
            print("❌ CONVERSA COMPLETA: REPROVADA")
            print("⚠️ Verifique os logs acima para identificar problemas")
        
        return 0 if success else 1
        
    except KeyboardInterrupt:
        print("\n🛑 Teste interrompido pelo usuário")
        return 2
    except Exception as e:
        print(f"\n💥 ERRO: {e}")
        import traceback
        traceback.print_exc()
        return 3

if __name__ == "__main__":
    exit(main())
