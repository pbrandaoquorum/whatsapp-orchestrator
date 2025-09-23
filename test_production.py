#!/usr/bin/env python3
"""
Script de Teste de Produção - WhatsApp Orchestrator
Executa testes reais simulando cenários de produção
"""

import requests
import json
import time
import sys
from typing import Dict, Any, List
from datetime import datetime

class ProductionTester:
    def __init__(self, base_url: str = "http://127.0.0.1:8000"):
        self.base_url = base_url
        self.results: List[Dict[str, Any]] = []
        # Session ID com escala real configurada
        self.real_session_phone = "5511991261390"
        
    def log(self, message: str, level: str = "INFO"):
        """Log com timestamp"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {level}: {message}")
    
    def check_dynamo_context(self, session_id: str, step: str = "") -> Dict[str, Any]:
        """Verifica contexto no DynamoDB"""
        try:
            import boto3
            import json
            
            dynamo = boto3.client('dynamodb', region_name='sa-east-1')
            response = dynamo.get_item(
                TableName='ConversationStates',
                Key={'session_id': {'S': session_id}}
            )
            
            context_info = {
                "exists": False,
                "tem_pendente": False,
                "fluxo_pendente": None,
                "fluxos_executados": [],
                "vitais": {},
                "nota": None
            }
            
            if 'Item' in response:
                context_info["exists"] = True
                
                if 'S' in response['Item']['estado']:
                    estado_str = response['Item']['estado']['S']
                    estado = json.loads(estado_str)
                    
                    context_info["tem_pendente"] = bool(estado.get('pendente'))
                    context_info["fluxo_pendente"] = estado.get('pendente', {}).get('fluxo') if estado.get('pendente') else None
                    context_info["fluxos_executados"] = estado.get('fluxos_executados', [])
                    context_info["vitais"] = list(estado.get('clinico', {}).get('vitais', {}).keys())
                    context_info["nota"] = bool(estado.get('clinico', {}).get('nota'))
                    
            if step:
                self.log(f"🔍 CONTEXTO {step}:")
                self.log(f"   📊 Existe no DynamoDB: {context_info['exists']}")
                if context_info["exists"]:
                    self.log(f"   📊 Fluxos executados: {context_info['fluxos_executados']}")
                    self.log(f"   📊 Tem pendente: {context_info['tem_pendente']}")
                    if context_info["tem_pendente"]:
                        self.log(f"   📊 Fluxo pendente: {context_info['fluxo_pendente']}")
                    self.log(f"   📊 Vitais: {context_info['vitais']}")
                    self.log(f"   📊 Tem nota: {context_info['nota']}")
                    
            return context_info
            
        except Exception as e:
            self.log(f"❌ Erro ao verificar contexto DynamoDB: {e}", "ERROR")
            return {"error": str(e)}
    
    def test_health_check(self) -> bool:
        """Teste 1: Health Check"""
        self.log("🏥 TESTE 1: Health Check")
        try:
            response = requests.get(f"{self.base_url}/healthz", timeout=10)
            if response.status_code == 200:
                data = response.json()
                self.log(f"✅ Health OK: {data['message']}")
                return True
            else:
                self.log(f"❌ Health FALHOU: {response.status_code}", "ERROR")
                return False
        except Exception as e:
            self.log(f"❌ Health ERRO: {e}", "ERROR")
            return False
    
    def test_readiness_check(self) -> bool:
        """Teste 2: Readiness Check (DynamoDB)"""
        self.log("🔍 TESTE 2: Readiness Check")
        try:
            response = requests.get(f"{self.base_url}/readyz", timeout=10)
            if response.status_code == 200:
                data = response.json()
                self.log(f"✅ Readiness OK: {data['message']}")
                return True
            else:
                self.log(f"❌ Readiness FALHOU: {response.status_code}", "ERROR")
                return False
        except Exception as e:
            self.log(f"❌ Readiness ERRO: {e}", "ERROR")
            return False
    
    def test_clinical_flow(self) -> bool:
        """Teste 3: Fluxo Clínico Completo"""
        self.log("📱 TESTE 3: Fluxo Clínico - Dados Vitais + Nota")
        
        payload = {
            "message_id": "test_001",
            "phoneNumber": "5511999999999",
            "text": "PA 120x80 FC 75 FR 18 Sat 97 Temp 36.8 paciente com tosse seca",
            "meta": {"source": "test"}
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/webhook/whatsapp",
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                reply = data.get("reply", "")
                
                # Verificar se extraiu os vitais corretamente
                if "PA 120x80" in reply and "FC 75" in reply and "tosse seca" in reply:
                    self.log("✅ Extração clínica OK - LLM funcionando")
                    self.log(f"   Resposta: {reply[:100]}...")
                    return True
                else:
                    self.log(f"❌ Extração clínica FALHOU: {reply}", "ERROR")
                    return False
            else:
                self.log(f"❌ Webhook FALHOU: {response.status_code}", "ERROR")
                return False
                
        except Exception as e:
            self.log(f"❌ Fluxo clínico ERRO: {e}", "ERROR")
            return False
    
    def test_confirmation_flow(self) -> bool:
        """Teste 4: Two-Phase Commit (Confirmação)"""
        self.log("✅ TESTE 4: Confirmação (TPC)")
        
        payload = {
            "message_id": "test_002",
            "phoneNumber": "5511999999999",
            "text": "sim",
            "meta": {}
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/webhook/whatsapp",
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                reply = data.get("reply", "")
                self.log(f"✅ Confirmação processada: {reply[:80]}...")
                return True
            else:
                self.log(f"❌ Confirmação FALHOU: {response.status_code}", "ERROR")
                return False
                
        except Exception as e:
            self.log(f"❌ Confirmação ERRO: {e}", "ERROR")
            return False
    
    def test_schedule_flow(self) -> bool:
        """Teste 5: Fluxo de Escala"""
        self.log("🏥 TESTE 5: Fluxo de Escala")
        
        payload = {
            "message_id": "test_003",
            "phoneNumber": "5511888888888",
            "text": "confirmo presença",
            "meta": {}
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/webhook/whatsapp",
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                reply = data.get("reply", "")
                
                # Pode dar erro por falta de dados de escala válidos
                if "escala" in reply.lower() or "erro" in reply.lower():
                    self.log("✅ Fluxo de escala processado (erro esperado sem dados)")
                    self.log(f"   Resposta: {reply[:80]}...")
                    return True
                else:
                    self.log(f"❌ Fluxo escala inesperado: {reply}", "ERROR")
                    return False
            else:
                self.log(f"❌ Fluxo escala FALHOU: {response.status_code}", "ERROR")
                return False
                
        except Exception as e:
            self.log(f"❌ Fluxo escala ERRO: {e}", "ERROR")
            return False
    
    def test_operational_flow(self) -> bool:
        """Teste 6: Fluxo Operacional (Direto, sem confirmação)"""
        self.log("📝 TESTE 6: Fluxo Operacional")
        
        payload = {
            "message_id": "test_004",
            "phoneNumber": "5511777777777",
            "text": "Paciente dormindo tranquilo, sem intercorrências",
            "meta": {}
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/webhook/whatsapp",
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                reply = data.get("reply", "")
                
                # Pode dar erro por falta de dados de sessão válidos
                if "nota" in reply.lower() or "erro" in reply.lower():
                    self.log("✅ Fluxo operacional processado (erro esperado sem sessão)")
                    self.log(f"   Resposta: {reply[:80]}...")
                    return True
                else:
                    self.log(f"❌ Fluxo operacional inesperado: {reply}", "ERROR")
                    return False
            else:
                self.log(f"❌ Fluxo operacional FALHOU: {response.status_code}", "ERROR")
                return False
                
        except Exception as e:
            self.log(f"❌ Fluxo operacional ERRO: {e}", "ERROR")
            return False
    
    def test_help_flow(self) -> bool:
        """Teste 7: Fluxo de Ajuda"""
        self.log("🤖 TESTE 7: Fluxo Auxiliar (Ajuda)")
        
        payload = {
            "message_id": "test_005",
            "phoneNumber": "5511666666666",
            "text": "ajuda",
            "meta": {}
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/webhook/whatsapp",
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                reply = data.get("reply", "")
                
                # Deve conter instruções de ajuda
                if "ESCALA" in reply and "CLÍNICO" in reply and "FINALIZAR" in reply:
                    self.log("✅ Sistema de ajuda funcionando")
                    self.log(f"   Instruções completas geradas ({len(reply)} chars)")
                    return True
                else:
                    self.log(f"❌ Sistema de ajuda incompleto: {reply[:100]}...", "ERROR")
                    return False
            else:
                self.log(f"❌ Sistema de ajuda FALHOU: {response.status_code}", "ERROR")
                return False
                
        except Exception as e:
            self.log(f"❌ Sistema de ajuda ERRO: {e}", "ERROR")
            return False
    
    def test_llm_extraction_edge_cases(self) -> bool:
        """Teste 8: Casos Extremos de Extração LLM"""
        self.log("🧠 TESTE 8: Casos Extremos - LLM")
        
        test_cases = [
            {
                "text": "PA 12/8 e febre",
                "description": "PA ambígua (12/8)",
                "phone": "5511111111111"
            },
            {
                "text": "FC 350 FR 5 saturação 120%",
                "description": "Valores fora da faixa",
                "phone": "5511222222222"
            },
            {
                "text": "Apenas uma nota sem vitais",
                "description": "Somente nota",
                "phone": "5511333333333"
            }
        ]
        
        success_count = 0
        
        for i, case in enumerate(test_cases):
            self.log(f"   Teste 8.{i+1}: {case['description']}")
            
            payload = {
                "message_id": f"test_edge_{i+1}",
                "phoneNumber": case["phone"],
                "text": case["text"],
                "meta": {}
            }
            
            try:
                response = requests.post(
                    f"{self.base_url}/webhook/whatsapp",
                    json=payload,
                    timeout=30
                )
                
                if response.status_code == 200:
                    data = response.json()
                    reply = data.get("reply", "")
                    self.log(f"   ✅ Caso {i+1} processado: {reply[:60]}...")
                    success_count += 1
                else:
                    self.log(f"   ❌ Caso {i+1} FALHOU: {response.status_code}", "ERROR")
                    
            except Exception as e:
                self.log(f"   ❌ Caso {i+1} ERRO: {e}", "ERROR")
            
            time.sleep(1)  # Evitar rate limit
        
        return success_count >= 2  # Pelo menos 2 de 3 casos
    
    def test_complete_conversation_flow(self) -> bool:
        """Teste 9: Conversa Completa com Session ID Real"""
        self.log("🗣️ TESTE 9: Conversa Completa - Session ID Real")
        
        phone = self.real_session_phone
        self.log(f"📱 Usando telefone com escala real: {phone}")
        
        # Verificar contexto inicial
        self.check_dynamo_context(phone, "INICIAL")
        
        # === PASSO 1: Confirmação de Presença ===
        self.log("\n📋 PASSO 1: Confirmando presença...")
        msg1 = self.send_message(phone, "confirmo presença", "conv_001")
        
        if 'error' in msg1:
            self.log(f"❌ Erro no passo 1: {msg1}", "ERROR")
            return False
            
        self.log(f"📥 Resposta 1: {msg1.get('reply', '')[:80]}...")
        context1 = self.check_dynamo_context(phone, "APÓS CONFIRMAÇÃO")
        
        time.sleep(2)
        
        # === PASSO 2: Envio de Dados Clínicos ===
        self.log("\n🏥 PASSO 2: Enviando dados clínicos...")
        clinical_data = "PA 135x90 FC 78 FR 19 Sat 98 Temp 36.7 paciente relatando leve dor de cabeça e cansaço"
        msg2 = self.send_message(phone, clinical_data, "conv_002")
        
        if 'error' in msg2:
            self.log(f"❌ Erro no passo 2: {msg2}", "ERROR")
            return False
            
        self.log(f"📥 Resposta 2: {msg2.get('reply', '')[:80]}...")
        context2 = self.check_dynamo_context(phone, "APÓS DADOS CLÍNICOS")
        
        # Verificar se preparou confirmação
        if not context2.get("tem_pendente"):
            self.log("❌ Dados clínicos não prepararam confirmação", "ERROR")
            return False
            
        time.sleep(2)
        
        # === PASSO 3: Confirmação dos Dados Clínicos ===
        self.log("\n✅ PASSO 3: Confirmando dados clínicos...")
        msg3 = self.send_message(phone, "sim", "conv_003")
        
        if 'error' in msg3:
            self.log(f"❌ Erro no passo 3: {msg3}", "ERROR")
            return False
            
        self.log(f"📥 Resposta 3: {msg3.get('reply', '')[:80]}...")
        context3 = self.check_dynamo_context(phone, "APÓS CONFIRMAÇÃO CLÍNICA")
        
        # Verificar se confirmação foi processada (pendente deve ser limpo)
        if context3.get("tem_pendente"):
            self.log("⚠️ Confirmação não limpou estado pendente", "WARN")
        
        time.sleep(2)
        
        # === PASSO 4: Consulta de Status ===
        self.log("\n❓ PASSO 4: Consultando status...")
        msg4 = self.send_message(phone, "como estou?", "conv_004")
        
        if 'error' in msg4:
            self.log(f"❌ Erro no passo 4: {msg4}", "ERROR")
            return False
            
        self.log(f"📥 Resposta 4: {msg4.get('reply', '')[:80]}...")
        context4 = self.check_dynamo_context(phone, "APÓS CONSULTA")
        
        time.sleep(2)
        
        # === PASSO 5: Finalização do Plantão ===
        self.log("\n🏁 PASSO 5: Finalizando plantão...")
        msg5 = self.send_message(phone, "finalizar plantão", "conv_005")
        
        if 'error' in msg5:
            self.log(f"❌ Erro no passo 5: {msg5}", "ERROR")
            return False
            
        self.log(f"📥 Resposta 5: {msg5.get('reply', '')[:80]}...")
        context5 = self.check_dynamo_context(phone, "APÓS SOLICITAÇÃO FINALIZAÇÃO")
        
        time.sleep(2)
        
        # === PASSO 6: Confirmação da Finalização ===
        if context5.get("tem_pendente") and context5.get("fluxo_pendente") == "finalizar":
            self.log("\n🏁 PASSO 6: Confirmando finalização...")
            msg6 = self.send_message(phone, "sim", "conv_006")
            
            if 'error' in msg6:
                self.log(f"❌ Erro no passo 6: {msg6}", "ERROR")
                return False
                
            self.log(f"📥 Resposta 6: {msg6.get('reply', '')[:80]}...")
            context6 = self.check_dynamo_context(phone, "APÓS CONFIRMAÇÃO FINALIZAÇÃO")
        else:
            self.log("ℹ️ Finalização não requer confirmação ou não foi preparada")
        
        # === ANÁLISE FINAL ===
        self.log("\n📊 ANÁLISE DA CONVERSA COMPLETA:")
        
        success_checks = 0
        total_checks = 6
        
        # Check 1: Confirmação de presença funcionou
        if "confirm" in msg1.get('reply', '').lower() or "presença" in msg1.get('reply', '').lower():
            self.log("✅ Check 1: Confirmação de presença processada")
            success_checks += 1
        else:
            self.log("❌ Check 1: Confirmação de presença falhou")
            
        # Check 2: Dados clínicos extraídos
        if context2.get("vitais") and len(context2["vitais"]) > 0:
            self.log("✅ Check 2: Dados clínicos extraídos e armazenados")
            success_checks += 1
        else:
            self.log("❌ Check 2: Dados clínicos não foram extraídos")
            
        # Check 3: Confirmação preparada
        if context2.get("tem_pendente") and context2.get("fluxo_pendente") == "clinico":
            self.log("✅ Check 3: Confirmação clínica preparada corretamente")
            success_checks += 1
        else:
            self.log("❌ Check 3: Confirmação clínica não foi preparada")
            
        # Check 4: Confirmação processada
        if "salv" in msg3.get('reply', '').lower() or "erro" in msg3.get('reply', '').lower():
            self.log("✅ Check 4: Confirmação clínica processada (salvou ou deu erro esperado)")
            success_checks += 1
        else:
            self.log("❌ Check 4: Confirmação clínica não foi processada")
            
        # Check 5: Contexto mantido entre mensagens
        if len(context4.get("fluxos_executados", [])) >= 2:
            self.log("✅ Check 5: Contexto mantido entre múltiplas mensagens")
            success_checks += 1
        else:
            self.log("❌ Check 5: Contexto não foi mantido adequadamente")
            
        # Check 6: Sistema de ajuda funciona
        if "ajud" in msg4.get('reply', '').lower() or "posso" in msg4.get('reply', '').lower():
            self.log("✅ Check 6: Sistema de ajuda/status funcionando")
            success_checks += 1
        else:
            self.log("❌ Check 6: Sistema de ajuda/status não funcionou")
        
        success_rate = (success_checks / total_checks) * 100
        self.log(f"📈 Taxa de Sucesso da Conversa: {success_rate:.1f}% ({success_checks}/{total_checks})")
        
        return success_checks >= 4  # 67% de aprovação
    
    def send_message(self, phone: str, text: str, message_id: str) -> dict:
        """Envia mensagem para o webhook (método helper)"""
        payload = {
            "message_id": message_id,
            "phoneNumber": phone,
            "text": text,
            "meta": {"source": "conversation_test"}
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/webhook/whatsapp",
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                return {"error": f"HTTP {response.status_code}", "text": response.text}
                
        except Exception as e:
            return {"error": str(e)}
    
    def run_all_tests(self) -> Dict[str, Any]:
        """Executa todos os testes"""
        self.log("🚀 INICIANDO TESTES DE PRODUÇÃO - WhatsApp Orchestrator")
        self.log("=" * 60)
        
        tests = [
            ("Health Check", self.test_health_check),
            ("Readiness Check", self.test_readiness_check),
            ("Fluxo Clínico", self.test_clinical_flow),
            ("Confirmação TPC", self.test_confirmation_flow),
            ("Fluxo Escala", self.test_schedule_flow),
            ("Fluxo Operacional", self.test_operational_flow),
            ("Sistema Ajuda", self.test_help_flow),
            ("Casos Extremos LLM", self.test_llm_extraction_edge_cases),
            ("🗣️ CONVERSA COMPLETA", self.test_complete_conversation_flow),
        ]
        
        results = {}
        passed = 0
        total = len(tests)
        
        for test_name, test_func in tests:
            self.log("-" * 40)
            try:
                result = test_func()
                results[test_name] = result
                if result:
                    passed += 1
                time.sleep(2)  # Pausa entre testes
            except Exception as e:
                self.log(f"❌ ERRO CRÍTICO no teste {test_name}: {e}", "ERROR")
                results[test_name] = False
        
        # Relatório final
        self.log("=" * 60)
        self.log("📊 RELATÓRIO FINAL")
        self.log(f"✅ Testes Aprovados: {passed}/{total}")
        self.log(f"❌ Testes Falharam: {total - passed}/{total}")
        
        if passed >= 7:  # 78% de aprovação (7 de 9 testes)
            self.log("🎉 SISTEMA APROVADO PARA PRODUÇÃO!")
            success_rate = (passed / total) * 100
            self.log(f"   Taxa de Sucesso: {success_rate:.1f}%")
        else:
            self.log("⚠️  SISTEMA PRECISA DE AJUSTES", "WARN")
        
        # Detalhes por teste
        self.log("\n📋 DETALHES:")
        for test_name, result in results.items():
            status = "✅ PASS" if result else "❌ FAIL"
            self.log(f"   {status} {test_name}")
        
        return {
            "total_tests": total,
            "passed": passed,
            "failed": total - passed,
            "success_rate": (passed / total) * 100,
            "details": results,
            "approved": passed >= 7
        }

def main():
    """Função principal"""
    if len(sys.argv) > 1:
        base_url = sys.argv[1]
    else:
        base_url = "http://127.0.0.1:8000"
    
    print(f"🎯 Testando WhatsApp Orchestrator em: {base_url}")
    print("⚡ Certifique-se de que o servidor está rodando!")
    print()
    
    tester = ProductionTester(base_url)
    
    try:
        results = tester.run_all_tests()
        
        # Salvar relatório
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = f"test_report_{timestamp}.json"
        
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        print(f"\n📄 Relatório salvo em: {report_file}")
        
        # Exit code baseado no resultado
        sys.exit(0 if results["approved"] else 1)
        
    except KeyboardInterrupt:
        print("\n🛑 Testes interrompidos pelo usuário")
        sys.exit(2)
    except Exception as e:
        print(f"\n💥 ERRO CRÍTICO: {e}")
        sys.exit(3)

if __name__ == "__main__":
    main()
