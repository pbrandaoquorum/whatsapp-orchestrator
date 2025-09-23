#!/usr/bin/env python3
"""
Teste de Preservação de Dados Clínicos
Testa se dados clínicos são preservados durante confirmação pendente
"""

import requests
import json
import time
import boto3
from datetime import datetime

def log(message: str):
    """Log com timestamp"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}")

def send_message(phone: str, text: str, message_id: str) -> dict:
    """Envia mensagem para o webhook"""
    payload = {
        "message_id": message_id,
        "phoneNumber": phone,
        "text": text,
        "meta": {"source": "preserve_test"}
    }
    
    try:
        response = requests.post(
            "http://127.0.0.1:8000/webhook/whatsapp",
            json=payload,
            timeout=30
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            return {"error": f"HTTP {response.status_code}", "text": response.text}
            
    except Exception as e:
        return {"error": str(e)}

def check_dynamo_state(session_id: str) -> dict:
    """Verifica estado no DynamoDB"""
    try:
        dynamo = boto3.client('dynamodb', region_name='sa-east-1')
        response = dynamo.get_item(
            TableName='ConversationStates',
            Key={'session_id': {'S': session_id}}
        )
        
        if 'Item' in response:
            estado_str = response['Item']['estado']['S']
            estado = json.loads(estado_str)
            return {
                "vitais": estado.get('clinico', {}).get('vitais', {}),
                "nota": estado.get('clinico', {}).get('nota'),
                "faltantes": estado.get('clinico', {}).get('faltantes', []),
                "pendente": estado.get('pendente'),
                "fluxos": estado.get('fluxos_executados', [])
            }
        else:
            return {"error": "Estado não encontrado"}
            
    except Exception as e:
        return {"error": str(e)}

def test_preserve_clinical_data():
    """Testa preservação de dados clínicos"""
    log("🧪 TESTE DE PRESERVAÇÃO DE DADOS CLÍNICOS")
    log("=" * 60)
    
    phone = "5511991261390"  # Session ID com escala real
    
    # Limpar estado inicial
    try:
        dynamo = boto3.client('dynamodb', region_name='sa-east-1')
        dynamo.delete_item(
            TableName='ConversationStates',
            Key={'session_id': {'S': phone}}
        )
        log("🧹 Estado inicial limpo")
    except:
        pass
    
    # PASSO 1: Confirmar presença (preparar confirmação pendente)
    log("\n📋 PASSO 1: Confirmando presença...")
    msg1 = send_message(phone, "confirmo presença", "preserve_001")
    log(f"📥 Resposta 1: {msg1.get('reply', '')[:60]}...")
    
    state1 = check_dynamo_state(phone)
    log(f"📊 Estado 1 - Pendente: {bool(state1.get('pendente'))}")
    
    time.sleep(2)
    
    # PASSO 2: Enviar dados clínicos MESMO com confirmação pendente
    log("\n🏥 PASSO 2: Enviando dados clínicos com confirmação pendente...")
    clinical_data = "PA 140x95 FC 82 FR 20 Sat 96 Temp 37.2 paciente com dor nas costas"
    msg2 = send_message(phone, clinical_data, "preserve_002")
    log(f"📥 Resposta 2: {msg2.get('reply', '')[:80]}...")
    
    state2 = check_dynamo_state(phone)
    log(f"📊 Estado 2 - Vitais preservados: {list(state2.get('vitais', {}).keys())}")
    log(f"📊 Estado 2 - Nota preservada: {bool(state2.get('nota'))}")
    log(f"📊 Estado 2 - Faltantes: {state2.get('faltantes', [])}")
    
    time.sleep(2)
    
    # PASSO 3: Confirmar presença (deve processar E mencionar dados preservados)
    log("\n✅ PASSO 3: Confirmando presença (com dados preservados)...")
    msg3 = send_message(phone, "sim", "preserve_003")
    log(f"📥 Resposta 3: {msg3.get('reply', '')[:100]}...")
    
    state3 = check_dynamo_state(phone)
    log(f"📊 Estado 3 - Pendente limpo: {not bool(state3.get('pendente'))}")
    log(f"📊 Estado 3 - Vitais mantidos: {list(state3.get('vitais', {}).keys())}")
    
    time.sleep(2)
    
    # PASSO 4: Enviar mais dados clínicos (deve mesclar)
    log("\n🔄 PASSO 4: Enviando dados adicionais...")
    additional_data = "Temp 38.1 paciente relatando febre"
    msg4 = send_message(phone, additional_data, "preserve_004")
    log(f"📥 Resposta 4: {msg4.get('reply', '')[:80]}...")
    
    state4 = check_dynamo_state(phone)
    log(f"📊 Estado 4 - Vitais finais: {state4.get('vitais', {})}")
    nota_final = state4.get('nota', '') or ''
    log(f"📊 Estado 4 - Nota final: {nota_final[:50]}...")
    
    # ANÁLISE FINAL
    log("\n📊 ANÁLISE DE PRESERVAÇÃO:")
    
    success_checks = 0
    total_checks = 4
    
    # Check 1: Confirmação pendente foi criada
    if state1.get('pendente'):
        log("✅ Check 1: Confirmação de presença preparada")
        success_checks += 1
    else:
        log("❌ Check 1: Confirmação não foi preparada")
    
    # Check 2: Dados clínicos foram preservados
    vitais_preservados = state2.get('vitais', {})
    if len([v for v in vitais_preservados.values() if v is not None]) >= 3:
        log("✅ Check 2: Dados clínicos preservados durante confirmação pendente")
        success_checks += 1
    else:
        log("❌ Check 2: Dados clínicos não foram preservados")
    
    # Check 3: Confirmação processou e manteve dados
    if not state3.get('pendente') and state3.get('vitais'):
        log("✅ Check 3: Confirmação processada mantendo dados clínicos")
        success_checks += 1
    else:
        log("❌ Check 3: Confirmação não manteve dados clínicos")
    
    # Check 4: Mesclagem de dados funcionou
    temp_inicial = state2.get('vitais', {}).get('Temp')
    temp_final = state4.get('vitais', {}).get('Temp')
    if temp_final and temp_final != temp_inicial:
        log("✅ Check 4: Mesclagem de dados funcionando")
        success_checks += 1
    else:
        log("❌ Check 4: Mesclagem de dados falhou")
    
    success_rate = (success_checks / total_checks) * 100
    log(f"\n📈 Taxa de Sucesso: {success_rate:.1f}% ({success_checks}/{total_checks})")
    
    if success_checks >= 3:
        log("🎉 PRESERVAÇÃO DE DADOS: APROVADA!")
        return True
    else:
        log("❌ PRESERVAÇÃO DE DADOS: REPROVADA")
        return False

def main():
    """Função principal"""
    print("🧪 TESTE DE PRESERVAÇÃO DE DADOS CLÍNICOS")
    print("📱 Session ID: 5511991261390")
    print("=" * 60)
    
    # Verificar servidor
    try:
        response = requests.get("http://127.0.0.1:8000/healthz", timeout=5)
        if response.status_code != 200:
            print("❌ Servidor não está respondendo")
            return 1
        print("✅ Servidor ativo!")
    except:
        print("❌ Servidor não está rodando")
        return 1
    
    print()
    
    try:
        success = test_preserve_clinical_data()
        return 0 if success else 1
    except Exception as e:
        print(f"\n💥 ERRO: {e}")
        return 3

if __name__ == "__main__":
    exit(main())
