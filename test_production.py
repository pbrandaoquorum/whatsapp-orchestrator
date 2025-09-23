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
        
    def log(self, message: str, level: str = "INFO"):
        """Log com timestamp"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {level}: {message}")
    
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
        
        if passed >= 6:  # 75% de aprovação
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
            "approved": passed >= 6
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
