#!/usr/bin/env python3
"""
Script para testar diferentes cenários de mensagens usando TestClient diretamente
Não requer servidor rodando - usa TestClient do FastAPI
"""
import asyncio
import sys
import os
from pathlib import Path

# Configurar paths
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
os.environ['PYTHONPATH'] = str(project_root)

# Carregar env
from dotenv import load_dotenv
load_dotenv(project_root / '.env')

from fastapi.testclient import TestClient
from app.api.main import app
import time
from typing import Dict, Any, List
from dataclasses import dataclass

@dataclass
class TestScenario:
    """Cenário de teste"""
    name: str
    phone: str
    messages: List[Dict[str, str]]
    description: str

def test_webhook_scenarios():
    """Testa diferentes cenários usando TestClient"""
    print("🧪 TESTE DE CENÁRIOS - WhatsApp Orchestrator (TestClient)")
    print("=" * 70)
    
    # Criar client de teste
    client = TestClient(app)
    
    # Definir cenários
    scenarios = [
        TestScenario(
            name="FLUXO_COMPLETO",
            phone="+5511987654321",
            description="Fluxo completo: chegada → confirmação → sinais vitais → nota → finalização",
            messages=[
                {"text": "Oi, cheguei no plantão da Dona Maria. Como procedo?"},
                {"text": "Confirmo minha presença no local"},
                {"text": "PA 130x85, FC 82 bpm, FR 20 irpm, Saturação 96%, Temperatura 36.8°C"},
                {"text": "Paciente consciente, orientada, colaborativa. Refere dor leve em MMII."},
                {"text": "Plantão finalizado. Como envio o relatório?"}
            ]
        ),
        
        TestScenario(
            name="CANCELAMENTO",
            phone="+5511987654322",
            description="Cancelamento de plantão",
            messages=[
                {"text": "Não posso ir ao plantão hoje, tive um imprevisto"},
                {"text": "Sim, confirmo o cancelamento"}
            ]
        ),
        
        TestScenario(
            name="SINAIS_VITAIS_DETALHADOS",
            phone="+5511987654323", 
            description="Coleta detalhada de sinais vitais",
            messages=[
                {"text": "Cheguei no plantão"},
                {"text": "Confirmo presença"},
                {"text": "Sinais vitais: PA 120x80, FC 78, FR 16, Saturação 98%, Temperatura 36.2°C"}
            ]
        ),
        
        TestScenario(
            name="NOTA_CLINICA_COMPLETA",
            phone="+5511987654324",
            description="Nota clínica detalhada",
            messages=[
                {"text": "Estou no plantão, confirmo presença"},
                {"text": """Paciente apresenta quadro estável. Consciente, orientada. 
                        Refere melhora da dor após medicação. Deambula sem auxílio. 
                        Alimentou-se bem. Humor estável, colaborativa."""}
            ]
        ),
        
        TestScenario(
            name="MENSAGENS_SIMPLES",
            phone="+5511987654325",
            description="Mensagens simples e ambíguas",
            messages=[
                {"text": "Olá"},
                {"text": "Não entendi"},
                {"text": "Preciso de ajuda"},
                {"text": "Como funciona?"}
            ]
        )
    ]
    
    # Executar cada cenário
    total_messages = 0
    successful_messages = 0
    
    for scenario in scenarios:
        print(f"\n🎯 CENÁRIO: {scenario.name}")
        print(f"📱 Telefone: {scenario.phone}")
        print(f"📝 Descrição: {scenario.description}")
        print("-" * 60)
        
        scenario_success = 0
        
        for i, msg_data in enumerate(scenario.messages, 1):
            text = msg_data["text"]
            message_id = f"{scenario.name}_msg_{i}"
            
            print(f"\n📤 Mensagem {i}: '{text[:50]}{'...' if len(text) > 50 else ''}'")
            
            try:
                # Fazer requisição
                response = client.post("/webhook/whatsapp", json={
                    "message_id": message_id,
                    "phoneNumber": scenario.phone,
                    "text": text
                }, headers={
                    "X-Idempotency-Key": f"test-{message_id}"
                })
                
                total_messages += 1
                
                if response.status_code == 200:
                    successful_messages += 1
                    scenario_success += 1
                    
                    result = response.json()
                    print(f"✅ Status: {response.status_code}")
                    print(f"🤖 Resposta: {result.get('message', '')[:80]}...")
                    print(f"🔗 Session: {result.get('session_id', 'N/A')}")
                    print(f"➡️  Próximo: {result.get('next_action', 'N/A')}")
                    
                    if result.get('success'):
                        print(f"✅ Processamento bem-sucedido")
                    else:
                        print(f"⚠️  Processamento com avisos")
                        
                else:
                    print(f"❌ Erro HTTP: {response.status_code}")
                    print(f"📄 Resposta: {response.text[:100]}...")
                    
            except Exception as e:
                print(f"❌ Exceção: {str(e)}")
                total_messages += 1
        
        print(f"\n📊 Cenário: {scenario_success}/{len(scenario.messages)} mensagens processadas")
    
    # Relatório final
    print("\n" + "=" * 70)
    print("📊 RELATÓRIO FINAL")
    print("=" * 70)
    
    success_rate = (successful_messages / total_messages * 100) if total_messages > 0 else 0
    
    print(f"📈 Total de cenários: {len(scenarios)}")
    print(f"📨 Total de mensagens: {total_messages}")
    print(f"✅ Mensagens bem-sucedidas: {successful_messages}")
    print(f"📊 Taxa de sucesso: {success_rate:.1f}%")
    
    if success_rate == 100:
        print("\n🎉 TODOS OS TESTES PASSARAM!")
        print("✅ Sistema funcionando perfeitamente!")
    elif success_rate >= 80:
        print(f"\n⚠️  Sistema funcionando com algumas falhas")
        print("🔍 Verifique os erros acima")
    else:
        print(f"\n❌ Sistema com muitas falhas")
        print("🔧 Necessário debugging")
    
    print(f"\n🚀 Para executar servidor manualmente:")
    print(f"   uvicorn app.api.main:app --reload --host 127.0.0.1 --port 8000")

if __name__ == "__main__":
    test_webhook_scenarios()
