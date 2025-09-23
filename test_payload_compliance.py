#!/usr/bin/env python3
"""
Teste de Conformidade de Payloads
=================================

Verifica se nossos payloads estão em conformidade com os lambdas
de referência, testando apenas a integração com nossa API.
"""

import os
import json
import requests
import time
import boto3
from typing import Dict, Any

# Configurações
API_URL = "http://127.0.0.1:8000"
SESSION_ID = "5511991261390"

def log(message: str, level: str = "INFO"):
    """Log com timestamp"""
    timestamp = time.strftime("%H:%M:%S")
    icon = {"INFO": "ℹ️", "SUCCESS": "✅", "ERROR": "❌", "WARNING": "⚠️"}.get(level, "📋")
    print(f"{timestamp} {icon} {message}")

def clear_dynamo_state(session_id: str):
    """Limpa estado no DynamoDB"""
    try:
        dynamodb = boto3.client('dynamodb', region_name='sa-east-1')
        dynamodb.delete_item(
            TableName='ConversationStates',
            Key={'session_id': {'S': session_id}}
        )
        log(f"Estado limpo para session_id: {session_id}")
    except Exception as e:
        log(f"Erro ao limpar estado: {e}", "ERROR")

def get_dynamo_state(session_id: str) -> Dict[str, Any]:
    """Recupera estado do DynamoDB"""
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
        log(f"Erro ao recuperar estado: {e}", "ERROR")
        return {}

def send_message(session_id: str, text: str, message_id: str) -> Dict[str, Any]:
    """Envia mensagem para nossa API"""
    payload = {
        "message_id": message_id,
        "phoneNumber": session_id,
        "text": text,
        "meta": {"source": "payload_compliance"}
    }
    
    try:
        response = requests.post(
            f"{API_URL}/webhook/whatsapp",
            json=payload,
            timeout=30
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        log(f"Erro ao enviar mensagem: {e}", "ERROR")
        return {}

def verify_getschedulestarted_integration():
    """Verifica integração com getScheduleStarted"""
    log("🔍 VERIFICANDO integração getScheduleStarted")
    
    clear_dynamo_state(SESSION_ID)
    response = send_message(SESSION_ID, "oi", "test_getschedule")
    
    if not response.get("reply"):
        log("❌ Falha na resposta da API", "ERROR")
        return False
    
    # Verificar se dados foram salvos no estado
    state = get_dynamo_state(SESSION_ID)
    sessao = state.get("sessao", {})
    
    required_fields = {
        "schedule_id": "scheduleID do lambda",
        "report_id": "reportID do lambda", 
        "caregiver_id": "caregiverID do lambda",
        "patient_id": "patientID do lambda",
        "turno_permitido": "shiftAllow do lambda",
        "empresa": "company do lambda",
        "cooperativa": "cooperative do lambda"
    }
    
    missing_fields = []
    for field, description in required_fields.items():
        if not sessao.get(field):
            missing_fields.append(f"{field} ({description})")
    
    if missing_fields:
        log(f"❌ Campos ausentes no estado: {missing_fields}", "ERROR")
        return False
    
    log("✅ getScheduleStarted: Todos os campos mapeados corretamente", "SUCCESS")
    log(f"   - Schedule ID: {sessao.get('schedule_id')}")
    log(f"   - Report ID: {sessao.get('report_id')}")
    log(f"   - Caregiver ID: {sessao.get('caregiver_id')}")
    log(f"   - Patient ID: {sessao.get('patient_id')}")
    log(f"   - Turno Permitido: {sessao.get('turno_permitido')}")
    log(f"   - Empresa: {sessao.get('empresa')}")
    log(f"   - Cooperativa: {sessao.get('cooperativa')}")
    
    return True

def verify_updateworkschedule_payload():
    """Verifica payload do updateWorkScheduleResponse"""
    log("🔍 VERIFICANDO payload updateWorkScheduleResponse")
    
    clear_dynamo_state(SESSION_ID)
    
    # Preparar confirmação de presença
    send_message(SESSION_ID, "confirmo presença", "test_confirm_prep")
    
    state = get_dynamo_state(SESSION_ID)
    if not state.get("pendente"):
        log("❌ Confirmação não foi preparada", "ERROR")
        return False
    
    payload = state["pendente"].get("payload", {})
    
    # Verificar campos obrigatórios do lambda
    required_fields = {
        "scheduleID": "Campo obrigatório (ou scheduleIdentifier)",
        "responseValue": "Campo obrigatório (ou checkAttend)",
        "caregiverID": "Campo para identificação",
        "phoneNumber": "Campo para identificação"
    }
    
    missing_fields = []
    for field, description in required_fields.items():
        if field not in payload:
            missing_fields.append(f"{field} ({description})")
    
    if missing_fields:
        log(f"❌ Campos obrigatórios ausentes: {missing_fields}", "ERROR")
        return False
    
    # Verificar valores corretos
    if payload.get("responseValue") not in ["confirmado", "cancelado"]:
        log(f"❌ responseValue inválido: {payload.get('responseValue')}", "ERROR")
        return False
    
    # Verificar que não há campos inválidos
    invalid_fields = ["action"]  # Campo que estava incorreto antes
    found_invalid = [field for field in invalid_fields if field in payload]
    
    if found_invalid:
        log(f"❌ Campos inválidos encontrados: {found_invalid}", "ERROR")
        return False
    
    log("✅ updateWorkScheduleResponse: Payload correto", "SUCCESS")
    log(f"   - scheduleID: {payload.get('scheduleID')}")
    log(f"   - responseValue: {payload.get('responseValue')}")
    log(f"   - caregiverID: {payload.get('caregiverID')}")
    log(f"   - phoneNumber: {payload.get('phoneNumber')}")
    
    # Testar execução da confirmação
    response = send_message(SESSION_ID, "sim", "test_confirm_execute")
    
    if "confirmada com sucesso" not in response.get("reply", ""):
        log(f"❌ Confirmação falhou: {response.get('reply')}", "ERROR")
        return False
    
    log("✅ updateWorkScheduleResponse: Execução bem-sucedida", "SUCCESS")
    return True

def verify_updateclinicaldata_payload():
    """Verifica payload do updateClinicalData"""
    log("🔍 VERIFICANDO payload updateClinicalData")
    
    clear_dynamo_state(SESSION_ID)
    
    # Preparar estado
    send_message(SESSION_ID, "confirmo presença", "clinical_setup")
    send_message(SESSION_ID, "sim", "clinical_setup_confirm")
    
    # Enviar dados clínicos
    clinical_data = "PA 120x80 FC 75 FR 18 Sat 98 Temp 36.5 paciente com dor de cabeça"
    response = send_message(SESSION_ID, clinical_data, "test_clinical_data")
    
    if "Confirma salvar" not in response.get("reply", ""):
        log(f"❌ Dados clínicos não processados: {response.get('reply')}", "ERROR")
        return False
    
    state = get_dynamo_state(SESSION_ID)
    if not state.get("pendente") or state["pendente"].get("fluxo") != "clinico":
        log("❌ Confirmação clínica não preparada", "ERROR")
        return False
    
    payload = state["pendente"].get("payload", {})
    
    # Verificar campos obrigatórios do lambda
    required_fields = {
        "reportID": "Campo obrigatório",
        "reportDate": "Campo obrigatório",
        "scheduleID": "Campo para identificação",
        "caregiverID": "Campo para logs/rastreamento",
        "patientID": "Campo para logs/rastreamento"
    }
    
    missing_fields = []
    for field, description in required_fields.items():
        if field not in payload:
            missing_fields.append(f"{field} ({description})")
    
    if missing_fields:
        log(f"❌ Campos obrigatórios ausentes: {missing_fields}", "ERROR")
        return False
    
    # Verificar estrutura de dados clínicos
    has_vitals = "vitalSignsData" in payload
    has_note = "clinicalNote" in payload
    
    if not has_vitals and not has_note:
        log("❌ Nenhum dado clínico encontrado no payload", "ERROR")
        return False
    
    log("✅ updateClinicalData: Payload correto", "SUCCESS")
    log(f"   - reportID: {payload.get('reportID')}")
    log(f"   - reportDate: {payload.get('reportDate')}")
    log(f"   - scheduleID: {payload.get('scheduleID')}")
    log(f"   - Tem vitais: {has_vitals}")
    log(f"   - Tem nota: {has_note}")
    
    if has_vitals:
        vitals = payload.get("vitalSignsData", {})
        log(f"   - Vitais: {list(vitals.keys())}")
    
    # Testar execução
    response = send_message(SESSION_ID, "sim", "test_clinical_confirm")
    
    if "salvos com sucesso" not in response.get("reply", ""):
        log(f"❌ Salvamento falhou: {response.get('reply')}", "ERROR")
        return False
    
    log("✅ updateClinicalData: Execução bem-sucedida", "SUCCESS")
    return True

def verify_updatereportsummary_payload():
    """Verifica payload do updatereportsummaryad"""
    log("🔍 VERIFICANDO payload updatereportsummaryad")
    
    clear_dynamo_state(SESSION_ID)
    
    # Preparar dados completos
    send_message(SESSION_ID, "confirmo presença", "final_setup1")
    send_message(SESSION_ID, "sim", "final_setup2")
    
    # Adicionar dados clínicos completos
    clinical_data = "PA 120x80 FC 75 FR 18 Sat 98 Temp 36.5"
    send_message(SESSION_ID, clinical_data, "final_clinical")
    send_message(SESSION_ID, "sim", "final_clinical_confirm")
    
    # Tentar finalizar
    response = send_message(SESSION_ID, "finalizar plantão", "test_finalize")
    
    if "finalização" not in response.get("reply", "").lower():
        log(f"❌ Finalização não preparada: {response.get('reply')}", "ERROR")
        return False
    
    state = get_dynamo_state(SESSION_ID)
    if not state.get("pendente") or state["pendente"].get("fluxo") != "finalizar":
        log("❌ Confirmação de finalização não preparada", "ERROR")
        return False
    
    payload = state["pendente"].get("payload", {})
    
    # Verificar campos obrigatórios do lambda
    required_fields = {
        "reportID": "Campo obrigatório",
        "reportDate": "Campo obrigatório", 
        "scheduleID": "Campo para WorkSchedules update",
        "caregiverID": "Campo para identificação"
    }
    
    missing_fields = []
    for field, description in required_fields.items():
        if field not in payload:
            missing_fields.append(f"{field} ({description})")
    
    if missing_fields:
        log(f"❌ Campos obrigatórios ausentes: {missing_fields}", "ERROR")
        return False
    
    # Verificar que não há campos inválidos antigos
    invalid_fields = ["action"]  # Campo que estava incorreto antes
    found_invalid = [field for field in invalid_fields if field in payload]
    
    if found_invalid:
        log(f"❌ Campos inválidos encontrados: {found_invalid}", "ERROR")
        return False
    
    log("✅ updatereportsummaryad: Payload correto", "SUCCESS")
    log(f"   - reportID: {payload.get('reportID')}")
    log(f"   - reportDate: {payload.get('reportDate')}")
    log(f"   - scheduleID: {payload.get('scheduleID')}")
    log(f"   - caregiverID: {payload.get('caregiverID')}")
    
    # Testar execução
    response = send_message(SESSION_ID, "sim", "test_finalize_confirm")
    
    if "finalizado com sucesso" not in response.get("reply", ""):
        log(f"❌ Finalização falhou: {response.get('reply')}", "ERROR")
        return False
    
    log("✅ updatereportsummaryad: Execução bem-sucedida", "SUCCESS")
    return True

def run_payload_compliance_test():
    """Executa teste completo de conformidade de payloads"""
    log("🚀 TESTE DE CONFORMIDADE DE PAYLOADS")
    log("=" * 50)
    
    # Verificar servidor
    try:
        response = requests.get(f"{API_URL}/healthz", timeout=5)
        if response.status_code != 200:
            log("❌ Servidor não está ativo", "ERROR")
            return False
    except:
        log("❌ Não foi possível conectar ao servidor", "ERROR")
        return False
    
    log("✅ Servidor ativo", "SUCCESS")
    
    # Executar verificações
    results = {}
    
    log("\n" + "="*50)
    results["getScheduleStarted"] = verify_getschedulestarted_integration()
    
    log("\n" + "="*50)
    results["updateWorkScheduleResponse"] = verify_updateworkschedule_payload()
    
    log("\n" + "="*50)
    results["updateClinicalData"] = verify_updateclinicaldata_payload()
    
    log("\n" + "="*50)
    results["updatereportsummaryad"] = verify_updatereportsummary_payload()
    
    # Resultado final
    log("\n" + "="*50)
    log("📊 RESULTADO FINAL - CONFORMIDADE DE PAYLOADS")
    log("="*50)
    
    total_tests = len(results)
    passed_tests = sum(1 for result in results.values() if result)
    
    for lambda_name, passed in results.items():
        status = "✅ CONFORME" if passed else "❌ NÃO CONFORME"
        log(f"{lambda_name}: {status}")
    
    success_rate = (passed_tests/total_tests)*100
    log(f"\n📈 CONFORMIDADE: {passed_tests}/{total_tests} ({success_rate:.1f}%)")
    
    if passed_tests == total_tests:
        log("🎉 CONFORMIDADE TOTAL ATINGIDA!", "SUCCESS")
        log("Todos os payloads estão 100% compatíveis com os lambdas!")
        return True
    else:
        log(f"⚠️  {total_tests - passed_tests} payloads não conformes", "WARNING")
        return False

if __name__ == "__main__":
    success = run_payload_compliance_test()
    exit(0 if success else 1)
