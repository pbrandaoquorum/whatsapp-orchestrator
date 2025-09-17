#!/usr/bin/env python3
"""
Script para testar diferentes cenários de mensagens no endpoint POST /webhook/whatsapp
Simula um fluxo completo de plantão domiciliar
"""
import asyncio
import httpx
import json
import time
from typing import Dict, Any, List
from dataclasses import dataclass

@dataclass
class TestScenario:
    """Cenário de teste"""
    name: str
    phone: str
    messages: List[Dict[str, str]]
    expected_flow: str
    description: str

class WhatsAppTester:
    """Testador do endpoint WhatsApp"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.session_results = {}
        
    async def send_message(self, phone: str, text: str, message_id: str = None) -> Dict[str, Any]:
        """Envia uma mensagem para o webhook"""
        if not message_id:
            message_id = f"msg_{int(time.time() * 1000)}"
            
        payload = {
            "message_id": message_id,
            "phoneNumber": phone,
            "text": text
        }
        
        headers = {
            "Content-Type": "application/json",
            "X-Idempotency-Key": f"test-{message_id}"
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/webhook/whatsapp",
                    json=payload,
                    headers=headers
                )
                
                return {
                    "status_code": response.status_code,
                    "response": response.json() if response.status_code == 200 else response.text,
                    "success": response.status_code == 200
                }
                
            except Exception as e:
                return {
                    "status_code": 0,
                    "response": str(e),
                    "success": False
                }
    
    async def run_scenario(self, scenario: TestScenario) -> Dict[str, Any]:
        """Executa um cenário completo"""
        print(f"\n🎯 CENÁRIO: {scenario.name}")
        print(f"📱 Telefone: {scenario.phone}")
        print(f"📝 Descrição: {scenario.description}")
        print("-" * 60)
        
        results = []
        session_id = f"session_{scenario.phone.replace('+', '')}"
        
        for i, msg_data in enumerate(scenario.messages, 1):
            text = msg_data["text"]
            expected = msg_data.get("expected", "")
            
            print(f"\n📤 Mensagem {i}: '{text}'")
            
            # Enviar mensagem
            result = await self.send_message(
                phone=scenario.phone,
                text=text,
                message_id=f"{scenario.name}_msg_{i}"
            )
            
            # Mostrar resultado
            if result["success"]:
                response_data = result["response"]
                print(f"✅ Status: {result['status_code']}")
                print(f"🤖 Resposta: {response_data.get('message', '')[:100]}...")
                print(f"🔗 Session: {response_data.get('session_id', 'N/A')}")
                print(f"➡️  Próximo: {response_data.get('next_action', 'N/A')}")
                
                if expected:
                    actual_action = response_data.get('next_action', '')
                    match = expected.lower() in actual_action.lower() if actual_action else False
                    print(f"🎯 Esperado: {expected} {'✅' if match else '❌'}")
            else:
                print(f"❌ Erro: {result['status_code']} - {result['response']}")
            
            results.append(result)
            
            # Pequena pausa entre mensagens
            await asyncio.sleep(1)
        
        # Resumo do cenário
        success_count = sum(1 for r in results if r["success"])
        print(f"\n📊 Resultado: {success_count}/{len(results)} mensagens processadas com sucesso")
        
        return {
            "scenario": scenario.name,
            "phone": scenario.phone,
            "total_messages": len(results),
            "successful_messages": success_count,
            "results": results
        }
    
    def create_scenarios(self) -> List[TestScenario]:
        """Cria cenários de teste"""
        return [
            TestScenario(
                name="FLUXO_COMPLETO_SUCESSO",
                phone="+5511987654321",
                description="Fluxo completo: chegada → confirmação → sinais vitais → nota → finalização",
                expected_flow="complete",
                messages=[
                    {"text": "Oi, cheguei no plantão da Dona Maria. Como procedo?", "expected": "auxiliar"},
                    {"text": "Confirmo minha presença no local", "expected": "escala"},
                    {"text": "PA 130x85, FC 82 bpm, FR 20 irpm, Saturação 96%, Temperatura 36.8°C", "expected": "clinical"},
                    {"text": "Paciente consciente, orientada, colaborativa. Refere dor leve em MMII. Deambula com auxílio.", "expected": "notas"},
                    {"text": "Plantão finalizado. Como envio o relatório?", "expected": "finalizar"}
                ]
            ),
            
            TestScenario(
                name="CANCELAMENTO_PLANTAO",
                phone="+5511987654322",
                description="Cancelamento de plantão por imprevisto",
                expected_flow="cancel",
                messages=[
                    {"text": "Não posso ir ao plantão hoje, tive um imprevisto familiar", "expected": "escala"},
                    {"text": "Sim, confirmo o cancelamento", "expected": "auxiliar"}
                ]
            ),
            
            TestScenario(
                name="SINAIS_VITAIS_INCREMENTAIS",
                phone="+5511987654323", 
                description="Coleta incremental de sinais vitais",
                expected_flow="clinical",
                messages=[
                    {"text": "Cheguei no plantão", "expected": "auxiliar"},
                    {"text": "Confirmo presença", "expected": "escala"},
                    {"text": "PA 120x80", "expected": "clinical"},
                    {"text": "FC 78 bpm", "expected": "clinical"},
                    {"text": "Saturação 97%", "expected": "clinical"},
                    {"text": "Temperatura 36.5°C", "expected": "clinical"},
                    {"text": "FR 18 irpm", "expected": "clinical"}
                ]
            ),
            
            TestScenario(
                name="NOTA_CLINICA_DETALHADA",
                phone="+5511987654324",
                description="Teste com nota clínica detalhada",
                expected_flow="clinical",
                messages=[
                    {"text": "Estou no plantão, confirmo presença", "expected": "escala"},
                    {"text": "Sinais vitais: PA 125x80, FC 75, FR 16, Sat 98%, Temp 36.2", "expected": "clinical"},
                    {"text": """Paciente apresenta quadro estável. Consciente, orientada no tempo e espaço. 
                            Refere melhora da dor lombar após medicação. Deambula sem auxílio. 
                            Alimentou-se bem no almoço. Humor estável, colaborativa com os cuidados. 
                            Pele íntegra, sem lesões. Eliminações fisiológicas normais.""", "expected": "notas"}
                ]
            ),
            
            TestScenario(
                name="MENSAGENS_AMBIGUAS",
                phone="+5511987654325",
                description="Teste com mensagens ambíguas e indefinidas",
                expected_flow="auxiliar",
                messages=[
                    {"text": "Olá", "expected": "auxiliar"},
                    {"text": "Não entendi", "expected": "auxiliar"},
                    {"text": "Preciso de ajuda", "expected": "auxiliar"},
                    {"text": "Como funciona?", "expected": "auxiliar"},
                    {"text": "Oi, tudo bem?", "expected": "auxiliar"}
                ]
            ),
            
            TestScenario(
                name="CONFIRMACOES_SIMPLES",
                phone="+5511987654326",
                description="Teste de confirmações simples (sim/não)",
                expected_flow="confirmation",
                messages=[
                    {"text": "Cheguei", "expected": "auxiliar"},
                    {"text": "Sim", "expected": "auxiliar"},
                    {"text": "Não", "expected": "auxiliar"},
                    {"text": "Ok", "expected": "auxiliar"},
                    {"text": "Pode ser", "expected": "auxiliar"}
                ]
            )
        ]
    
    async def run_health_check(self) -> bool:
        """Verifica se o servidor está rodando"""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/healthz")
                return response.status_code == 200
        except:
            return False
    
    async def run_all_scenarios(self):
        """Executa todos os cenários de teste"""
        print("🧪 TESTE DE CENÁRIOS - WhatsApp Orchestrator")
        print("=" * 70)
        
        # Verificar se servidor está rodando
        print("🔍 Verificando servidor...")
        if not await self.run_health_check():
            print("❌ Servidor não está rodando!")
            print("🚀 Execute: uvicorn app.api.main:app --reload")
            return
        
        print("✅ Servidor está rodando!")
        
        # Executar cenários
        scenarios = self.create_scenarios()
        all_results = []
        
        for scenario in scenarios:
            try:
                result = await self.run_scenario(scenario)
                all_results.append(result)
            except Exception as e:
                print(f"❌ Erro no cenário {scenario.name}: {e}")
        
        # Relatório final
        print("\n" + "=" * 70)
        print("📊 RELATÓRIO FINAL")
        print("=" * 70)
        
        total_scenarios = len(all_results)
        total_messages = sum(r["total_messages"] for r in all_results)
        total_successful = sum(r["successful_messages"] for r in all_results)
        
        print(f"📈 Cenários executados: {total_scenarios}")
        print(f"📨 Total de mensagens: {total_messages}")
        print(f"✅ Mensagens bem-sucedidas: {total_successful}")
        print(f"📊 Taxa de sucesso: {(total_successful/total_messages)*100:.1f}%")
        
        print("\n🎯 Resumo por cenário:")
        for result in all_results:
            success_rate = (result["successful_messages"] / result["total_messages"]) * 100
            status = "✅" if success_rate == 100 else "⚠️" if success_rate >= 80 else "❌"
            print(f"  {status} {result['scenario']}: {result['successful_messages']}/{result['total_messages']} ({success_rate:.0f}%)")
        
        if total_successful == total_messages:
            print("\n🎉 TODOS OS TESTES PASSARAM!")
            print("✅ Sistema funcionando perfeitamente!")
        else:
            print(f"\n⚠️  {total_messages - total_successful} mensagens falharam")
            print("🔍 Verifique os logs para mais detalhes")

async def main():
    """Função principal"""
    tester = WhatsAppTester()
    await tester.run_all_scenarios()

if __name__ == "__main__":
    asyncio.run(main())
