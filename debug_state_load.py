#!/usr/bin/env python3
"""
Debug do Carregamento de Estado - WhatsApp Orchestrator
"""

import sys
sys.path.insert(0, '.')

from app.api.deps import get_dynamo_state_manager

def test_state_loading():
    """Testa carregamento de estado do DynamoDB"""
    print("🔍 TESTE DE CARREGAMENTO DE ESTADO")
    print("=" * 50)
    
    session_id = "5511111222333"
    
    # Carregar estado
    dynamo_manager = get_dynamo_state_manager()
    
    try:
        print(f"📊 Carregando estado para session_id: {session_id}")
        state = dynamo_manager.carregar_estado(session_id)
        
        print(f"✅ Estado carregado com sucesso!")
        print(f"   - Session ID: {state.sessao.get('session_id')}")
        print(f"   - Fluxos executados: {state.fluxos_executados}")
        print(f"   - Tem pendente: {state.tem_pendente()}")
        print(f"   - Pendente data: {state.pendente}")
        
        if state.tem_pendente():
            print(f"   - Fluxo pendente: {state.pendente['fluxo']}")
            print(f"   - Payload keys: {list(state.pendente.get('payload', {}).keys())}")
        
        print(f"   - Vitais: {list(state.clinico['vitais'].keys())}")
        print(f"   - Tem nota: {bool(state.clinico.get('nota'))}")
        
        # Testar método tem_pendente diretamente
        print(f"\n🧪 Teste direto do método tem_pendente():")
        print(f"   - state.pendente: {state.pendente}")
        print(f"   - state.pendente is not None: {state.pendente is not None}")
        print(f"   - state.tem_pendente(): {state.tem_pendente()}")
        
        return state
        
    except Exception as e:
        print(f"❌ ERRO ao carregar estado: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    print("🎯 DEBUG DO CARREGAMENTO DE ESTADO\n")
    
    try:
        state = test_state_loading()
        
        if state and state.tem_pendente():
            print(f"\n✅ Estado tem confirmação pendente para fluxo: {state.pendente['fluxo']}")
        elif state:
            print(f"\n⚠️  Estado carregado mas sem confirmação pendente")
        else:
            print(f"\n❌ Falha no carregamento do estado")
            
    except Exception as e:
        print(f"\n💥 ERRO GERAL: {e}")
        import traceback
        traceback.print_exc()
