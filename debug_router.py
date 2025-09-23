#!/usr/bin/env python3
"""
Debug do Router - WhatsApp Orchestrator
Testa diretamente a lógica de roteamento
"""

import sys
sys.path.insert(0, '.')

from app.graph.state import GraphState
from app.api.deps import get_main_router

def test_router_with_pending():
    """Testa router com confirmação pendente"""
    print("🔍 TESTE DE ROUTER COM CONFIRMAÇÃO PENDENTE")
    print("=" * 50)
    
    # Criar estado com confirmação pendente
    state = GraphState()
    state.sessao["session_id"] = "debug_test"
    state.entrada["texto_usuario"] = "sim"
    
    # Simular confirmação pendente do fluxo clínico
    state.pendente = {
        "fluxo": "clinico",
        "payload": {"vitais": {"PA": "120x80"}}
    }
    
    print(f"📊 Estado inicial:")
    print(f"   - Session ID: {state.sessao['session_id']}")
    print(f"   - Texto: {state.entrada['texto_usuario']}")
    print(f"   - Tem pendente: {state.tem_pendente()}")
    print(f"   - Fluxo pendente: {state.pendente.get('fluxo') if state.pendente else 'Nenhum'}")
    
    # Testar router
    router = get_main_router()
    
    try:
        resultado = router.rotear(state)
        print(f"✅ Router retornou: {resultado}")
        
        if resultado == "clinico":
            print("✅ SUCESSO: Router direcionou corretamente para clínico")
        else:
            print(f"❌ ERRO: Esperava 'clinico', mas retornou '{resultado}'")
            
    except Exception as e:
        print(f"❌ ERRO no router: {e}")
        import traceback
        traceback.print_exc()

def test_router_normal():
    """Testa router sem confirmação pendente"""
    print("\n🔍 TESTE DE ROUTER NORMAL")
    print("=" * 50)
    
    # Criar estado normal
    state = GraphState()
    state.sessao["session_id"] = "debug_test_2"
    state.entrada["texto_usuario"] = "PA 120x80 FC 75"
    
    print(f"📊 Estado inicial:")
    print(f"   - Session ID: {state.sessao['session_id']}")
    print(f"   - Texto: {state.entrada['texto_usuario']}")
    print(f"   - Tem pendente: {state.tem_pendente()}")
    print(f"   - Tem retomada: {state.tem_retomada()}")
    
    # Testar router
    router = get_main_router()
    
    try:
        resultado = router.rotear(state)
        print(f"✅ Router retornou: {resultado}")
        
        if resultado == "clinico":
            print("✅ SUCESSO: Router classificou corretamente como clínico")
        else:
            print(f"⚠️  Router classificou como: {resultado}")
            
    except Exception as e:
        print(f"❌ ERRO no router: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("🎯 DEBUG DO ROUTER - WhatsApp Orchestrator\n")
    
    try:
        test_router_with_pending()
        test_router_normal()
        
        print("\n🎉 Testes de debug concluídos!")
        
    except Exception as e:
        print(f"\n💥 ERRO GERAL: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
