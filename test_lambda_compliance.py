#!/usr/bin/env python3
"""
Teste de Conformidade com Lambdas
=================================

Este script verifica se nossos payloads estão em conformidade total
com os lambdas de referência em references/

Testa todos os cenários:
1. getScheduleStarted
2. updateWorkScheduleResponse  
3. updateClinicalData
4. updatereportsummaryad
"""

import os
import json
import requests
import time
import boto3
from typing import Dict, Any
import structlog

# Configurar logging
logger = structlog.get_logger()

# Configurações
API_URL = "http://127.0.0.1:8000"
SESSION_ID = "5511991261390"  # Session ID com dados válidos
LAMBDA_URLS = {
    "getScheduleStarted": "https://f35khigesh.execute-api.sa-east-1.amazonaws.com/default/getScheduleStarted",
    "updateWorkScheduleResponse": "https://3d73k6qkla.execute-api.sa-east-1.amazonaws.com/default/updateWorkScheduleResponse",
    "updateClinicalData": "https://vhxbkwvwb7.execute-api.sa-east-1.amazonaws.com/default/updateClinicalData",
    "updatereportsummaryad": "https://vhxbkwvwb7.execute-api.sa-east-1.amazonaws.com/default/updatereportsummaryad"
}

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
            
        # Deserializa estado
        estado_str = response['Item']['estado']['S']
        estado_dict = json.loads(estado_str)
        return estado_dict
    except Exception as e:
        log(f"Erro ao recuperar estado: {e}", "ERROR")
        return {}

def send_message(session_id: str, text: str, message_id: str) -> Dict[str, Any]:
    """Envia mensagem para nossa API"""
    payload = {
        "message_id": message_id,
        "phoneNumber": session_id,
        "text": text,
        "meta": {"source": "compliance_test"}
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

def test_direct_lambda(lambda_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Testa lambda diretamente"""
    url = LAMBDA_URLS.get(lambda_name)
    if not url:
        log(f"URL não encontrada para lambda: {lambda_name}", "ERROR")
        return {}
    
    try:
        log(f"Testando {lambda_name} diretamente...")
        response = requests.post(url, json=payload, timeout=30)
        
        log(f"Status: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            log(f"Sucesso: {lambda_name}", "SUCCESS")
            return result
        else:
            log(f"Erro {response.status_code}: {response.text}", "ERROR")
            return {"error": response.text, "status_code": response.status_code}
    except Exception as e:
        log(f"Erro ao testar {lambda_name}: {e}", "ERROR")
        return {"error": str(e)}

def verify_getschedulestarted():
    """Verifica conformidade com getScheduleStarted"""
    log("🔍 VERIFICANDO getScheduleStarted")
    log("=" * 50)
    
    # Teste direto do lambda
    payload = {"phoneNumber": SESSION_ID}
    result = test_direct_lambda("getScheduleStarted", payload)
    
    if "error" in result:
        log("❌ Falha no teste direto do getScheduleStarted", "ERROR")
        return False
    
    # Verificar campos esperados
    expected_fields = [
        "caregiverID", "scheduleID", "reportID", "reportDate",
        "shiftAllow", "patientID", "scheduleStarted"
    ]
    
    missing_fields = [field for field in expected_fields if field not in result]
    if missing_fields:
        log(f"❌ Campos ausentes: {missing_fields}", "ERROR")
        return False
    
    log("✅ getScheduleStarted: Todos os campos presentes", "SUCCESS")
    
    # Testar integração com nossa API
    clear_dynamo_state(SESSION_ID)
    api_response = send_message(SESSION_ID, "oi", "test_getschedule")
    
    if not api_response.get("reply"):
        log("❌ Falha na integração com nossa API", "ERROR")
        return False
    
    # Verificar se dados foram salvos corretamente no estado
    state = get_dynamo_state(SESSION_ID)
    sessao = state.get("sessao", {})
    
    critical_fields = ["schedule_id", "report_id", "caregiver_id", "patient_id"]
    missing_in_state = [field for field in critical_fields if not sessao.get(field)]
    
    if missing_in_state:
        log(f"❌ Campos ausentes no estado: {missing_in_state}", "ERROR")
        return False
    
    log("✅ getScheduleStarted: Integração funcionando", "SUCCESS")
    return True

def verify_updateworkschedule():
    """Verifica conformidade com updateWorkScheduleResponse"""
    log("🔍 VERIFICANDO updateWorkScheduleResponse")
    log("=" * 50)
    
    # Primeiro, obter um scheduleID válido
    clear_dynamo_state(SESSION_ID)
    send_message(SESSION_ID, "oi", "setup_schedule")
    state = get_dynamo_state(SESSION_ID)
    schedule_id = state.get("sessao", {}).get("schedule_id")
    
    if not schedule_id:
        log("❌ Não foi possível obter scheduleID válido", "ERROR")
        return False
    
    # Teste direto do lambda
    payload = {
        "scheduleID": schedule_id,
        "responseValue": "confirmado",
        "caregiverID": state.get("sessao", {}).get("caregiver_id"),
        "phoneNumber": SESSION_ID
    }
    
    result = test_direct_lambda("updateWorkScheduleResponse", payload)
    
    if "error" in result:
        log("❌ Falha no teste direto do updateWorkScheduleResponse", "ERROR")
        return False
    
    log("✅ updateWorkScheduleResponse: Teste direto passou", "SUCCESS")
    
    # Testar integração com nossa API
    clear_dynamo_state(SESSION_ID)
    
    # Passo 1: Preparar confirmação
    send_message(SESSION_ID, "confirmo presença", "test_confirm_prep")
    
    # Verificar se payload está correto
    state = get_dynamo_state(SESSION_ID)
    if not state.get("pendente"):
        log("❌ Confirmação não foi preparada", "ERROR")
        return False
    
    payload_pendente = state["pendente"].get("payload", {})
    required_fields = ["scheduleID", "responseValue", "caregiverID", "phoneNumber"]
    missing_fields = [field for field in required_fields if field not in payload_pendente]
    
    if missing_fields:
        log(f"❌ Campos ausentes no payload: {missing_fields}", "ERROR")
        return False
    
    if payload_pendente.get("responseValue") != "confirmado":
        log(f"❌ responseValue incorreto: {payload_pendente.get('responseValue')}", "ERROR")
        return False
    
    log("✅ Payload de confirmação correto", "SUCCESS")
    
    # Passo 2: Confirmar
    response = send_message(SESSION_ID, "sim", "test_confirm_execute")
    
    if "confirmada com sucesso" not in response.get("reply", ""):
        log(f"❌ Confirmação falhou: {response.get('reply')}", "ERROR")
        return False
    
    log("✅ updateWorkScheduleResponse: Integração funcionando", "SUCCESS")
    return True

def verify_updateclinicaldata():
    """Verifica conformidade com updateClinicalData"""
    log("🔍 VERIFICANDO updateClinicalData")
    log("=" * 50)
    
    # Preparar estado com dados válidos
    clear_dynamo_state(SESSION_ID)
    send_message(SESSION_ID, "oi", "setup_clinical")
    state = get_dynamo_state(SESSION_ID)
    
    report_id = state.get("sessao", {}).get("report_id")
    report_date = state.get("sessao", {}).get("data_relatorio")
    
    if not report_id or not report_date:
        log("❌ Não foi possível obter reportID/reportDate válidos", "ERROR")
        return False
    
    # Teste direto do lambda - cenário VITAL_SIGNS_NOTE
    payload = {
        "reportID": report_id,
        "reportDate": report_date,
        "scheduleID": state.get("sessao", {}).get("schedule_id"),
        "caregiverID": state.get("sessao", {}).get("caregiver_id"),
        "patientID": state.get("sessao", {}).get("patient_id"),
        "vitalSignsData": {
            "heartRate": 75,
            "bloodPressure": "120x80",
            "respRate": 18,
            "saturationO2": 98,
            "temperature": 36.5
        },
        "clinicalNote": "Paciente relatando dor de cabeça"
    }
    
    result = test_direct_lambda("updateClinicalData", payload)
    
    if "error" in result:
        log("❌ Falha no teste direto do updateClinicalData", "ERROR")
        return False
    
    log("✅ updateClinicalData: Teste direto passou", "SUCCESS")
    
    # Testar integração com nossa API
    clear_dynamo_state(SESSION_ID)
    
    # Confirmar presença primeiro
    send_message(SESSION_ID, "confirmo presença", "clinical_setup")
    send_message(SESSION_ID, "sim", "clinical_setup_confirm")
    
    # Enviar dados clínicos
    clinical_data = "PA 120x80 FC 75 FR 18 Sat 98 Temp 36.5 paciente com dor de cabeça"
    response = send_message(SESSION_ID, clinical_data, "test_clinical_data")
    
    if "Confirma salvar" not in response.get("reply", ""):
        log(f"❌ Dados clínicos não foram processados: {response.get('reply')}", "ERROR")
        return False
    
    # Verificar payload
    state = get_dynamo_state(SESSION_ID)
    if not state.get("pendente") or state["pendente"].get("fluxo") != "clinico":
        log("❌ Confirmação clínica não foi preparada", "ERROR")
        return False
    
    payload_clinical = state["pendente"].get("payload", {})
    required_fields = ["reportID", "reportDate", "scheduleID"]
    missing_fields = [field for field in required_fields if field not in payload_clinical]
    
    if missing_fields:
        log(f"❌ Campos obrigatórios ausentes: {missing_fields}", "ERROR")
        return False
    
    log("✅ Payload clínico correto", "SUCCESS")
    
    # Confirmar salvamento
    response = send_message(SESSION_ID, "sim", "test_clinical_confirm")
    
    if "salvos com sucesso" not in response.get("reply", ""):
        log(f"❌ Salvamento clínico falhou: {response.get('reply')}", "ERROR")
        return False
    
    log("✅ updateClinicalData: Integração funcionando", "SUCCESS")
    return True

def verify_updatereportsummary():
    """Verifica conformidade com updatereportsummaryad"""
    log("🔍 VERIFICANDO updatereportsummaryad")
    log("=" * 50)
    
    # Preparar estado com dados válidos
    clear_dynamo_state(SESSION_ID)
    send_message(SESSION_ID, "oi", "setup_summary")
    state = get_dynamo_state(SESSION_ID)
    
    report_id = state.get("sessao", {}).get("report_id")
    report_date = state.get("sessao", {}).get("data_relatorio")
    schedule_id = state.get("sessao", {}).get("schedule_id")
    caregiver_id = state.get("sessao", {}).get("caregiver_id")
    
    if not all([report_id, report_date, schedule_id, caregiver_id]):
        log("❌ Não foi possível obter dados válidos para teste", "ERROR")
        return False
    
    # Teste direto do lambda
    payload = {
        "reportID": report_id,
        "reportDate": report_date,
        "scheduleID": schedule_id,
        "caregiverID": caregiver_id,
        "patientFirstName": "Paciente Teste",
        "caregiverFirstName": "Cuidador Teste",
        "shiftDay": "23/09/2025",
        "shiftStart": "08:00",
        "shiftEnd": "19:00",
        "foodHydrationSpecification": "Normal",
        "stoolUrineSpecification": "Normal",
        "sleepSpecification": "Bem",
        "moodSpecification": "Estável",
        "medicationsSpecification": "Conforme prescrição",
        "activitiesSpecification": "Atividades normais",
        "additionalInformationSpecification": "Sem intercorrências",
        "administrativeInfo": "Plantão finalizado"
    }
    
    result = test_direct_lambda("updatereportsummaryad", payload)
    
    if "error" in result:
        log("❌ Falha no teste direto do updatereportsummaryad", "ERROR")
        return False
    
    log("✅ updatereportsummaryad: Teste direto passou", "SUCCESS")
    
    # Testar integração com nossa API
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
    
    if "Confirma finalizar" not in response.get("reply", ""):
        log(f"❌ Finalização não foi preparada: {response.get('reply')}", "ERROR")
        return False
    
    # Verificar payload de finalização
    state = get_dynamo_state(SESSION_ID)
    if not state.get("pendente") or state["pendente"].get("fluxo") != "finalizar":
        log("❌ Confirmação de finalização não foi preparada", "ERROR")
        return False
    
    payload_final = state["pendente"].get("payload", {})
    required_fields = ["reportID", "reportDate", "scheduleID", "caregiverID"]
    missing_fields = [field for field in required_fields if field not in payload_final]
    
    if missing_fields:
        log(f"❌ Campos obrigatórios ausentes no payload final: {missing_fields}", "ERROR")
        return False
    
    log("✅ Payload de finalização correto", "SUCCESS")
    
    # Confirmar finalização
    response = send_message(SESSION_ID, "sim", "test_finalize_confirm")
    
    if "finalizado com sucesso" not in response.get("reply", ""):
        log(f"❌ Finalização falhou: {response.get('reply')}", "ERROR")
        return False
    
    log("✅ updatereportsummaryad: Integração funcionando", "SUCCESS")
    return True

def run_compliance_test():
    """Executa teste completo de conformidade"""
    log("🚀 INICIANDO TESTE DE CONFORMIDADE COM LAMBDAS")
    log("=" * 60)
    
    # Verificar se servidor está rodando
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
    
    log("\n" + "="*60)
    results["getScheduleStarted"] = verify_getschedulestarted()
    
    log("\n" + "="*60)  
    results["updateWorkScheduleResponse"] = verify_updateworkschedule()
    
    log("\n" + "="*60)
    results["updateClinicalData"] = verify_updateclinicaldata()
    
    log("\n" + "="*60)
    results["updatereportsummaryad"] = verify_updatereportsummary()
    
    # Resultado final
    log("\n" + "="*60)
    log("📊 RESULTADO FINAL DA CONFORMIDADE")
    log("="*60)
    
    total_tests = len(results)
    passed_tests = sum(1 for result in results.values() if result)
    
    for lambda_name, passed in results.items():
        status = "✅ PASSOU" if passed else "❌ FALHOU"
        log(f"{lambda_name}: {status}")
    
    log(f"\n📈 TAXA DE SUCESSO: {passed_tests}/{total_tests} ({(passed_tests/total_tests)*100:.1f}%)")
    
    if passed_tests == total_tests:
        log("🎉 CONFORMIDADE TOTAL ATINGIDA!", "SUCCESS")
        log("Sistema 100% compatível com todos os lambdas de referência")
        return True
    else:
        log(f"⚠️  {total_tests - passed_tests} testes falharam", "WARNING")
        return False

if __name__ == "__main__":
    success = run_compliance_test()
    exit(0 if success else 1)
