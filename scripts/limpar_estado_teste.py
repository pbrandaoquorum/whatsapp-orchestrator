#!/usr/bin/env python3
"""
Script para limpar estado de teste no DynamoDB
==============================================

Uso: python3 scripts/limpar_estado_teste.py <session_id>
Exemplo: python3 scripts/limpar_estado_teste.py 5511991261390
"""

import sys
import os

# Adiciona o diretório raiz ao path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.infra.dynamo_state import DynamoStateManager

def limpar_estado(session_id: str):
    """Deleta estado do DynamoDB para testes"""
    
    # Inicializa DynamoStateManager
    table_name = os.getenv("DYNAMO_TABLE_NAME", "conversationStates")
    dynamo_manager = DynamoStateManager(table_name=table_name)
    
    print(f"🧹 Limpando estado para session_id: {session_id}")
    print(f"📊 Tabela: {table_name}")
    
    try:
        # Deleta estado
        dynamo_manager.deletar_estado(session_id)
        print(f"✅ Estado deletado com sucesso!")
        print(f"🎉 Próxima interação iniciará com estado limpo")
        
    except Exception as e:
        print(f"❌ Erro ao deletar estado: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("❌ Uso: python3 scripts/limpar_estado_teste.py <session_id>")
        print("📝 Exemplo: python3 scripts/limpar_estado_teste.py 5511991261390")
        sys.exit(1)
    
    session_id = sys.argv[1]
    limpar_estado(session_id)

