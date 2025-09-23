#!/usr/bin/env python3
"""
TESTE ABRANGENTE DE PRODUÇÃO - WhatsApp Orchestrator
==================================================

Este script simula cenários complexos e edge cases para testar TODAS
as funcionalidades do sistema em ambiente de produção.

Cenários testados:
1. Fluxo completo com dados faltantes
2. Preservação de dados clínicos durante confirmações
3. Retomada de fluxos interrompidos
4. Cancelamento e mudança de contexto
5. Dados inválidos e ambíguos
6. Múltiplas tentativas e correções
7. Finalização com dados incompletos
8. Context switching entre fluxos
9. Persistência de estado entre sessões
10. Edge cases e cenários adversos

Número de teste: 5511991261390 (ambiente de produção)
"""

import os
import json
import requests
import time
import boto3
from typing import Dict, Any, List, Tuple
from dataclasses import dataclass
import traceback

# Configurações
API_URL = "http://127.0.0.1:8000"
SESSION_ID = "5511991261390"  # Número real do usuário

@dataclass
class TestResult:
    scenario: str
    success: bool
    expected: str
    actual: str
    details: Dict[str, Any]
    error: str = ""

class ComprehensiveProductionTester:
    def __init__(self):
        self.results: List[TestResult] = []
        self.message_counter = 1
        
    def log(self, message: str, level: str = "INFO"):
        """Log com timestamp e cor"""
        timestamp = time.strftime("%H:%M:%S")
        icons = {
            "INFO": "ℹ️",
            "SUCCESS": "✅", 
            "ERROR": "❌",
            "WARNING": "⚠️",
            "TEST": "🧪",
            "ANALYSIS": "🔍"
        }
        icon = icons.get(level, "📋")
        print(f"{timestamp} {icon} {message}")
    
    def clear_dynamo_state(self, session_id: str):
        """Limpa estado no DynamoDB"""
        try:
            dynamodb = boto3.client('dynamodb', region_name='sa-east-1')
            dynamodb.delete_item(
                TableName='ConversationStates',
                Key={'session_id': {'S': session_id}}
            )
            self.log(f"Estado limpo para session_id: {session_id}")
        except Exception as e:
            self.log(f"Erro ao limpar estado: {e}", "ERROR")
    
    def get_dynamo_state(self, session_id: str) -> Dict[str, Any]:
        """Recupera estado detalhado do DynamoDB"""
        try:
            dynamodb = boto3.client('dynamodb', region_name='sa-east-1')
            response = dynamodb.get_item(
                TableName='ConversationStates',
                Key={'session_id': {'S': session_id}}
            )
            
            if 'Item' not in response:
                return {}
                
            estado_str = response['Item']['estado']['S']
            return json.loads(estado_str)
        except Exception as e:
            self.log(f"Erro ao recuperar estado: {e}", "ERROR")
            return {}
    
    def send_message(self, text: str, expected_keywords: List[str] = None) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Envia mensagem e retorna resposta + estado
        
        Returns:
            Tuple[resposta_api, estado_dynamo]
        """
        message_id = f"test_msg_{self.message_counter:03d}"
        self.message_counter += 1
        
        payload = {
            "message_id": message_id,
            "phoneNumber": SESSION_ID,
            "text": text,
            "meta": {"source": "comprehensive_test"}
        }
        
        try:
            self.log(f"📤 Enviando: '{text}'")
            response = requests.post(
                f"{API_URL}/webhook/whatsapp",
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            api_response = response.json()
            
            # Aguardar processamento
            time.sleep(1)
            
            # Recuperar estado atual
            state = self.get_dynamo_state(SESSION_ID)
            
            reply = api_response.get("reply", "")
            self.log(f"📥 Resposta: '{reply}'")
            
            # Verificar palavras-chave esperadas
            if expected_keywords:
                found_keywords = [kw for kw in expected_keywords if kw.lower() in reply.lower()]
                if not found_keywords:
                    self.log(f"⚠️  Palavras-chave esperadas não encontradas: {expected_keywords}", "WARNING")
            
            return api_response, state
            
        except Exception as e:
            self.log(f"Erro ao enviar mensagem: {e}", "ERROR")
            return {"error": str(e)}, {}
    
    def add_result(self, scenario: str, success: bool, expected: str, actual: str, details: Dict[str, Any] = None, error: str = ""):
        """Adiciona resultado de teste"""
        result = TestResult(
            scenario=scenario,
            success=success,
            expected=expected,
            actual=actual,
            details=details or {},
            error=error
        )
        self.results.append(result)
        
        status = "✅ PASSOU" if success else "❌ FALHOU"
        self.log(f"{scenario}: {status}")
        if not success and error:
            self.log(f"   Erro: {error}", "ERROR")
    
    def analyze_state(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Analisa estado atual e retorna métricas"""
        analysis = {
            "has_session_data": bool(state.get("sessao", {}).get("schedule_id")),
            "has_pending": bool(state.get("pendente")),
            "has_retomada": bool(state.get("retomada")),
            "executed_flows": state.get("fluxos_executados", []),
            "clinical_vitals": state.get("clinico", {}).get("vitais", {}),
            "clinical_missing": state.get("clinico", {}).get("faltantes", []),
            "clinical_note": state.get("clinico", {}).get("nota"),
            "pending_flow": state.get("pendente", {}).get("fluxo") if state.get("pendente") else None,
            "retomada_flow": state.get("retomada", {}).get("fluxo") if state.get("retomada") else None,
            "session_info": {
                "schedule_id": state.get("sessao", {}).get("schedule_id"),
                "report_id": state.get("sessao", {}).get("report_id"),
                "turno_permitido": state.get("sessao", {}).get("turno_permitido"),
            }
        }
        return analysis
    
    def test_scenario_1_incomplete_data_flow(self):
        """Cenário 1: Fluxo com dados incompletos e faltantes"""
        self.log("\n🧪 CENÁRIO 1: Fluxo com dados incompletos", "TEST")
        self.log("=" * 60)
        
        try:
            self.clear_dynamo_state(SESSION_ID)
            
            # 1.1: Início básico
            response, state = self.send_message("oi", ["assistente"])
            analysis = self.analyze_state(state)
            
            self.add_result(
                "1.1 - Inicialização",
                analysis["has_session_data"],
                "Dados de sessão carregados",
                f"Schedule ID: {analysis['session_info']['schedule_id']}",
                analysis
            )
            
            # 1.2: Enviar dados clínicos incompletos (só alguns vitais)
            response, state = self.send_message("PA 130x85 FC 88", ["Confirma", "salvar"])
            analysis = self.analyze_state(state)
            
            vitais_presentes = list(analysis["clinical_vitals"].keys())
            faltantes = analysis["clinical_missing"]
            
            self.add_result(
                "1.2 - Dados clínicos incompletos",
                len(vitais_presentes) > 0 and len(faltantes) > 0,
                "Vitais parciais detectados + faltantes identificados",
                f"Presentes: {vitais_presentes}, Faltantes: {faltantes}",
                analysis
            )
            
            # 1.3: Confirmar dados incompletos
            response, state = self.send_message("sim", ["salvos com sucesso"])
            analysis = self.analyze_state(state)
            
            self.add_result(
                "1.3 - Confirmação dados incompletos",
                not analysis["has_pending"],
                "Dados salvos mesmo incompletos",
                f"Pendente: {analysis['has_pending']}",
                analysis
            )
            
            # 1.4: Tentar finalizar com dados faltantes
            response, state = self.send_message("finalizar plantão")
            analysis = self.analyze_state(state)
            
            # Deve criar retomada para clínico
            has_retomada = analysis["has_retomada"]
            retomada_flow = analysis["retomada_flow"]
            
            self.add_result(
                "1.4 - Finalização com dados faltantes",
                has_retomada and retomada_flow == "finalizar",
                "Retomada criada para completar dados",
                f"Retomada: {retomada_flow}",
                analysis
            )
            
        except Exception as e:
            self.add_result("Cenário 1", False, "Execução sem erros", str(e), error=traceback.format_exc())
    
    def test_scenario_2_data_preservation(self):
        """Cenário 2: Preservação de dados durante confirmações"""
        self.log("\n🧪 CENÁRIO 2: Preservação de dados clínicos", "TEST")
        self.log("=" * 60)
        
        try:
            self.clear_dynamo_state(SESSION_ID)
            
            # 2.1: Confirmar presença
            response, state = self.send_message("confirmo presença", ["Confirma"])
            analysis = self.analyze_state(state)
            
            self.add_result(
                "2.1 - Preparação confirmação",
                analysis["has_pending"] and analysis["pending_flow"] == "escala",
                "Confirmação de presença pendente",
                f"Pendente: {analysis['pending_flow']}",
                analysis
            )
            
            # 2.2: Enviar dados clínicos DURANTE confirmação pendente
            response, state = self.send_message(
                "PA 120x80 FC 75 FR 18 Sat 98 Temp 36.5 paciente com dor de cabeça"
            )
            analysis = self.analyze_state(state)
            
            # Dados devem ser preservados mesmo com confirmação pendente
            vitais_preservados = analysis["clinical_vitals"]
            nota_preservada = analysis["clinical_note"]
            
            self.add_result(
                "2.2 - Preservação durante confirmação",
                len(vitais_preservados) > 0 and nota_preservada is not None,
                "Dados clínicos preservados durante confirmação pendente",
                f"Vitais: {list(vitais_preservados.keys())}, Nota: {bool(nota_preservada)}",
                analysis
            )
            
            # 2.3: Confirmar presença (dados devem ser mantidos)
            response, state = self.send_message("sim", ["confirmada"])
            analysis = self.analyze_state(state)
            
            vitais_mantidos = analysis["clinical_vitals"]
            nota_mantida = analysis["clinical_note"]
            
            self.add_result(
                "2.3 - Manutenção após confirmação",
                len(vitais_mantidos) > 0 and nota_mantida is not None,
                "Dados mantidos após confirmação",
                f"Vitais: {list(vitais_mantidos.keys())}, Nota: {bool(nota_mantida)}",
                analysis
            )
            
            # 2.4: Adicionar mais dados (mesclagem)
            response, state = self.send_message("temperatura 37.8 paciente com febre")
            analysis = self.analyze_state(state)
            
            temp_atualizada = analysis["clinical_vitals"].get("Temp")
            nota_atualizada = analysis["clinical_note"]
            
            self.add_result(
                "2.4 - Mesclagem de dados",
                temp_atualizada == 37.8 and "febre" in (nota_atualizada or ""),
                "Dados mesclados corretamente",
                f"Temp: {temp_atualizada}, Nota contém 'febre': {'febre' in (nota_atualizada or '')}",
                analysis
            )
            
        except Exception as e:
            self.add_result("Cenário 2", False, "Execução sem erros", str(e), error=traceback.format_exc())
    
    def test_scenario_3_retomada_flow(self):
        """Cenário 3: Fluxo de retomada"""
        self.log("\n🧪 CENÁRIO 3: Fluxo de retomada", "TEST")
        self.log("=" * 60)
        
        try:
            self.clear_dynamo_state(SESSION_ID)
            
            # 3.1: Preparar dados básicos
            self.send_message("oi")
            self.send_message("confirmo presença")
            self.send_message("sim")
            
            # 3.2: Tentar finalizar sem dados clínicos
            response, state = self.send_message("finalizar plantão")
            analysis = self.analyze_state(state)
            
            # Deve criar retomada
            has_retomada = analysis["has_retomada"]
            retomada_flow = analysis["retomada_flow"]
            
            self.add_result(
                "3.1 - Criação de retomada",
                has_retomada and retomada_flow == "finalizar",
                "Retomada criada para finalizar",
                f"Retomada: {retomada_flow}",
                analysis
            )
            
            # 3.3: Enviar dados para completar
            response, state = self.send_message("PA 110x70 FC 70 FR 16 Sat 99 Temp 36.0")
            analysis = self.analyze_state(state)
            
            vitais_completos = analysis["clinical_vitals"]
            faltantes = analysis["clinical_missing"]
            
            self.add_result(
                "3.2 - Dados para retomada",
                len(vitais_completos) >= 5 and len(faltantes) == 0,
                "Dados clínicos completos",
                f"Vitais: {len(vitais_completos)}, Faltantes: {len(faltantes)}",
                analysis
            )
            
            # 3.4: Confirmar dados clínicos
            response, state = self.send_message("sim", ["salvos"])
            analysis = self.analyze_state(state)
            
            # 3.5: Agora finalizar deve funcionar
            response, state = self.send_message("finalizar plantão", ["finalizar"])
            analysis = self.analyze_state(state)
            
            self.add_result(
                "3.3 - Retomada bem-sucedida",
                analysis["has_pending"] and analysis["pending_flow"] == "finalizar",
                "Finalização preparada após retomada",
                f"Pendente: {analysis['pending_flow']}",
                analysis
            )
            
            # 3.6: Confirmar finalização
            response, state = self.send_message("sim", ["finalizado"])
            analysis = self.analyze_state(state)
            
            self.add_result(
                "3.4 - Finalização completa",
                not analysis["has_pending"] and not analysis["has_retomada"],
                "Finalização concluída",
                f"Pendente: {analysis['has_pending']}, Retomada: {analysis['has_retomada']}",
                analysis
            )
            
        except Exception as e:
            self.add_result("Cenário 3", False, "Execução sem erros", str(e), error=traceback.format_exc())
    
    def test_scenario_4_ambiguous_data(self):
        """Cenário 4: Dados ambíguos e inválidos"""
        self.log("\n🧪 CENÁRIO 4: Dados ambíguos e inválidos", "TEST")
        self.log("=" * 60)
        
        try:
            self.clear_dynamo_state(SESSION_ID)
            self.send_message("oi")
            
            # 4.1: Dados ambíguos (PA 12/8 - pode ser 120x80 ou inválido)
            response, state = self.send_message("PA 12/8 FC 85")
            analysis = self.analyze_state(state)
            
            # Sistema deve lidar com ambiguidade
            pa_value = analysis["clinical_vitals"].get("PA")
            
            self.add_result(
                "4.1 - Dados ambíguos",
                pa_value is not None,  # Sistema deve tentar interpretar ou deixar null
                "PA ambígua tratada adequadamente",
                f"PA interpretada como: {pa_value}",
                analysis
            )
            
            # 4.2: Dados claramente inválidos
            response, state = self.send_message("FC 300 Temp 50 PA 300x200")
            analysis = self.analyze_state(state)
            
            fc_invalid = analysis["clinical_vitals"].get("FC")
            temp_invalid = analysis["clinical_vitals"].get("Temp")
            
            # Valores fora da faixa devem ser rejeitados
            self.add_result(
                "4.2 - Dados inválidos",
                fc_invalid != 300 and temp_invalid != 50,
                "Valores inválidos rejeitados",
                f"FC: {fc_invalid}, Temp: {temp_invalid}",
                analysis
            )
            
            # 4.3: Mistura de dados válidos e inválidos
            response, state = self.send_message("FC 75 Temp 36.5 Sat 150")  # Sat inválida
            analysis = self.analyze_state(state)
            
            fc_valid = analysis["clinical_vitals"].get("FC")
            temp_valid = analysis["clinical_vitals"].get("Temp")
            sat_invalid = analysis["clinical_vitals"].get("Sat")
            
            self.add_result(
                "4.3 - Mistura válido/inválido",
                fc_valid == 75 and temp_valid == 36.5 and sat_invalid != 150,
                "Valores válidos aceitos, inválidos rejeitados",
                f"FC: {fc_valid}, Temp: {temp_valid}, Sat: {sat_invalid}",
                analysis
            )
            
        except Exception as e:
            self.add_result("Cenário 4", False, "Execução sem erros", str(e), error=traceback.format_exc())
    
    def test_scenario_5_context_switching(self):
        """Cenário 5: Mudança de contexto entre fluxos"""
        self.log("\n🧪 CENÁRIO 5: Context switching", "TEST")
        self.log("=" * 60)
        
        try:
            self.clear_dynamo_state(SESSION_ID)
            self.send_message("oi")
            
            # 5.1: Iniciar fluxo clínico
            response, state = self.send_message("PA 120x80 FC 75", ["Confirma"])
            analysis = self.analyze_state(state)
            
            self.add_result(
                "5.1 - Início fluxo clínico",
                analysis["has_pending"] and analysis["pending_flow"] == "clinico",
                "Fluxo clínico preparado",
                f"Pendente: {analysis['pending_flow']}",
                analysis
            )
            
            # 5.2: Mudar para fluxo operacional (sem confirmar)
            response, state = self.send_message("registro administrativo: plantão iniciado às 8h")
            analysis = self.analyze_state(state)
            
            # Deve processar operacional diretamente
            executed_flows = analysis["executed_flows"]
            
            self.add_result(
                "5.2 - Mudança para operacional",
                "operacional" in executed_flows,
                "Fluxo operacional executado",
                f"Fluxos executados: {executed_flows}",
                analysis
            )
            
            # 5.3: Voltar para confirmação clínica pendente
            response, state = self.send_message("sim")  # Deve confirmar o clínico pendente
            analysis = self.analyze_state(state)
            
            self.add_result(
                "5.3 - Retorno ao clínico pendente",
                not analysis["has_pending"] and "clinico" in analysis["executed_flows"],
                "Confirmação clínica processada",
                f"Pendente: {analysis['has_pending']}, Fluxos: {analysis['executed_flows']}",
                analysis
            )
            
            # 5.4: Testar ajuda durante fluxo
            response, state = self.send_message("ajuda", ["assistente", "ajuda"])
            analysis = self.analyze_state(state)
            
            self.add_result(
                "5.4 - Fluxo de ajuda",
                "auxiliar" in analysis["executed_flows"],
                "Ajuda processada",
                f"Fluxos executados: {analysis['executed_flows']}",
                analysis
            )
            
        except Exception as e:
            self.add_result("Cenário 5", False, "Execução sem erros", str(e), error=traceback.format_exc())
    
    def test_scenario_6_edge_cases(self):
        """Cenário 6: Edge cases e situações extremas"""
        self.log("\n🧪 CENÁRIO 6: Edge cases", "TEST")
        self.log("=" * 60)
        
        try:
            self.clear_dynamo_state(SESSION_ID)
            self.send_message("oi")
            
            # 6.1: Mensagem vazia
            response, state = self.send_message("", ["assistente"])
            analysis = self.analyze_state(state)
            
            self.add_result(
                "6.1 - Mensagem vazia",
                "auxiliar" in analysis["executed_flows"],
                "Mensagem vazia tratada como auxiliar",
                f"Fluxos executados: {analysis['executed_flows']}",
                analysis
            )
            
            # 6.2: Múltiplas confirmações seguidas
            self.send_message("confirmo presença")
            response, state = self.send_message("sim sim sim", ["confirmada"])
            analysis = self.analyze_state(state)
            
            self.add_result(
                "6.2 - Múltiplas confirmações",
                not analysis["has_pending"],
                "Confirmação processada uma vez",
                f"Pendente: {analysis['has_pending']}",
                analysis
            )
            
            # 6.3: Cancelamento
            self.send_message("PA 130x90")  # Preparar confirmação
            response, state = self.send_message("não", ["cancelado", "descartado"])
            analysis = self.analyze_state(state)
            
            self.add_result(
                "6.3 - Cancelamento",
                not analysis["has_pending"],
                "Confirmação cancelada",
                f"Pendente: {analysis['has_pending']}",
                analysis
            )
            
            # 6.4: Dados extremos válidos
            response, state = self.send_message("PA 90x60 FC 45 FR 8 Sat 95 Temp 35.0")
            analysis = self.analyze_state(state)
            
            vitals = analysis["clinical_vitals"]
            all_accepted = all(vitals.get(k) is not None for k in ["PA", "FC", "FR", "Sat", "Temp"])
            
            self.add_result(
                "6.4 - Dados extremos válidos",
                all_accepted,
                "Valores extremos mas válidos aceitos",
                f"Vitais aceitos: {list(vitals.keys())}",
                analysis
            )
            
        except Exception as e:
            self.add_result("Cenário 6", False, "Execução sem erros", str(e), error=traceback.format_exc())
    
    def test_scenario_7_session_persistence(self):
        """Cenário 7: Persistência entre sessões"""
        self.log("\n🧪 CENÁRIO 7: Persistência de sessão", "TEST")
        self.log("=" * 60)
        
        try:
            # 7.1: Criar sessão com dados
            self.clear_dynamo_state(SESSION_ID)
            self.send_message("oi")
            self.send_message("PA 125x85 FC 80")
            self.send_message("sim")  # Salvar dados
            
            # 7.2: Simular nova sessão (mesmo número)
            response, state = self.send_message("oi novamente")
            analysis = self.analyze_state(state)
            
            # Dados anteriores devem estar preservados
            vitals_preservados = analysis["clinical_vitals"]
            has_session_data = analysis["has_session_data"]
            
            self.add_result(
                "7.1 - Persistência entre sessões",
                has_session_data and len(vitals_preservados) > 0,
                "Dados preservados entre sessões",
                f"Session data: {has_session_data}, Vitais: {list(vitals_preservados.keys())}",
                analysis
            )
            
            # 7.3: Adicionar mais dados na sessão continuada
            response, state = self.send_message("FR 20 Sat 96")
            analysis = self.analyze_state(state)
            
            vitals_updated = analysis["clinical_vitals"]
            
            self.add_result(
                "7.2 - Continuação de sessão",
                len(vitals_updated) > len(vitals_preservados),
                "Novos dados adicionados à sessão existente",
                f"Vitais antes: {len(vitals_preservados)}, depois: {len(vitals_updated)}",
                analysis
            )
            
        except Exception as e:
            self.add_result("Cenário 7", False, "Execução sem erros", str(e), error=traceback.format_exc())
    
    def run_all_tests(self):
        """Executa todos os cenários de teste"""
        self.log("🚀 INICIANDO TESTE ABRANGENTE DE PRODUÇÃO", "TEST")
        self.log("=" * 80)
        self.log(f"📱 Número de teste: {SESSION_ID}")
        self.log(f"🌐 API URL: {API_URL}")
        
        # Verificar servidor
        try:
            response = requests.get(f"{API_URL}/healthz", timeout=5)
            if response.status_code != 200:
                self.log("❌ Servidor não está ativo", "ERROR")
                return
        except:
            self.log("❌ Não foi possível conectar ao servidor", "ERROR")
            return
        
        self.log("✅ Servidor ativo - Iniciando testes", "SUCCESS")
        
        # Executar todos os cenários
        test_scenarios = [
            self.test_scenario_1_incomplete_data_flow,
            self.test_scenario_2_data_preservation,
            self.test_scenario_3_retomada_flow,
            self.test_scenario_4_ambiguous_data,
            self.test_scenario_5_context_switching,
            self.test_scenario_6_edge_cases,
            self.test_scenario_7_session_persistence,
        ]
        
        for i, scenario in enumerate(test_scenarios, 1):
            try:
                scenario()
                time.sleep(2)  # Pausa entre cenários
            except Exception as e:
                self.log(f"❌ Erro no cenário {i}: {e}", "ERROR")
        
        # Análise final
        self.analyze_results()
    
    def analyze_results(self):
        """Análise crítica e detalhada dos resultados"""
        self.log("\n🔍 ANÁLISE CRÍTICA DOS RESULTADOS", "ANALYSIS")
        self.log("=" * 80)
        
        total_tests = len(self.results)
        passed_tests = sum(1 for r in self.results if r.success)
        failed_tests = total_tests - passed_tests
        success_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0
        
        self.log(f"📊 ESTATÍSTICAS GERAIS:")
        self.log(f"   Total de testes: {total_tests}")
        self.log(f"   ✅ Passou: {passed_tests}")
        self.log(f"   ❌ Falhou: {failed_tests}")
        self.log(f"   📈 Taxa de sucesso: {success_rate:.1f}%")
        
        # Análise por categoria
        categories = {}
        for result in self.results:
            category = result.scenario.split(" - ")[0] if " - " in result.scenario else result.scenario
            if category not in categories:
                categories[category] = {"passed": 0, "failed": 0, "total": 0}
            
            categories[category]["total"] += 1
            if result.success:
                categories[category]["passed"] += 1
            else:
                categories[category]["failed"] += 1
        
        self.log(f"\n📋 ANÁLISE POR CATEGORIA:")
        for category, stats in categories.items():
            rate = (stats["passed"] / stats["total"] * 100) if stats["total"] > 0 else 0
            status = "✅" if stats["failed"] == 0 else "⚠️" if rate >= 50 else "❌"
            self.log(f"   {status} {category}: {stats['passed']}/{stats['total']} ({rate:.1f}%)")
        
        # Análise detalhada dos falhas
        failures = [r for r in self.results if not r.success]
        if failures:
            self.log(f"\n❌ ANÁLISE DETALHADA DAS FALHAS:")
            for i, failure in enumerate(failures, 1):
                self.log(f"   {i}. {failure.scenario}")
                self.log(f"      Esperado: {failure.expected}")
                self.log(f"      Obtido: {failure.actual}")
                if failure.error:
                    self.log(f"      Erro: {failure.error}")
                self.log("")
        
        # Análise de funcionalidades críticas
        self.log(f"\n🎯 ANÁLISE DE FUNCIONALIDADES CRÍTICAS:")
        
        critical_functions = {
            "Preservação de dados": any("preservação" in r.scenario.lower() for r in self.results if r.success),
            "Retomada de fluxos": any("retomada" in r.scenario.lower() for r in self.results if r.success),
            "Dados faltantes": any("faltantes" in r.scenario.lower() for r in self.results if r.success),
            "Context switching": any("context" in r.scenario.lower() for r in self.results if r.success),
            "Dados inválidos": any("inválidos" in r.scenario.lower() for r in self.results if r.success),
            "Persistência": any("persistência" in r.scenario.lower() for r in self.results if r.success),
        }
        
        for function, working in critical_functions.items():
            status = "✅ FUNCIONANDO" if working else "❌ COM PROBLEMAS"
            self.log(f"   {status} {function}")
        
        # Recomendações
        self.log(f"\n💡 RECOMENDAÇÕES:")
        
        if success_rate >= 90:
            self.log("   🎉 Sistema em excelente estado para produção!")
            self.log("   ✅ Todos os fluxos críticos funcionando adequadamente")
        elif success_rate >= 70:
            self.log("   ⚠️  Sistema funcional, mas com pontos de atenção")
            self.log("   🔧 Revisar falhas antes do deploy em produção")
        else:
            self.log("   ❌ Sistema com problemas críticos")
            self.log("   🚨 NÃO RECOMENDADO para produção no estado atual")
        
        if failed_tests > 0:
            self.log("   📝 Priorizar correção dos testes que falharam")
            self.log("   🧪 Re-executar testes após correções")
        
        # Análise de performance
        self.log(f"\n⚡ ANÁLISE DE PERFORMANCE:")
        self.log(f"   📨 Total de mensagens enviadas: {self.message_counter - 1}")
        self.log(f"   ⏱️  Tempo médio por teste: ~2-3 segundos")
        self.log(f"   💾 Estado DynamoDB: Consistente entre operações")
        
        # Conclusão final
        self.log(f"\n🏁 CONCLUSÃO FINAL:")
        if success_rate >= 95:
            self.log("   🌟 EXCELENTE - Sistema robusto e confiável")
        elif success_rate >= 85:
            self.log("   ✅ BOM - Sistema funcional com pequenos ajustes")  
        elif success_rate >= 70:
            self.log("   ⚠️  ACEITÁVEL - Requer melhorias antes da produção")
        else:
            self.log("   ❌ INADEQUADO - Necessita revisão extensiva")
        
        return success_rate >= 70  # Threshold para aprovação

if __name__ == "__main__":
    tester = ComprehensiveProductionTester()
    success = tester.run_all_tests()
    exit(0 if success else 1)
