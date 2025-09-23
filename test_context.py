#!/usr/bin/env python3
"""
Teste de Contexto - WhatsApp Orchestrator
Verifica se o estado está sendo mantido corretamente entre mensagens
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

def check_dynamo_state(session_id: str):
    """Verifica estado no DynamoDB"""
    try:
        dynamo = boto3.client('dynamodb', region_name='sa-east-1')
        response = dynamo.get_item(
            TableName='ConversationStates',
            Key={'session_id': {'S': session_id}}
        )
        
        if 'Item' in response:
            print(f"   📊 DynamoDB - Session: {response['Item']['session_id']['S']}")
            print(f"   📊 DynamoDB - Timestamp: {response['Item']['atualizadoEm']['S']}")
            
            # Verifica formato do estado
            if 'S' in response['Item']['estado']:
                estado_str = response['Item']['estado']['S']
                print(f"   📊 DynamoDB - Formato: String (✅ correto)")
                
                # Parse do JSON para mostrar estrutura
                try:
                    estado_dict = json.loads(estado_str)
                    fluxos = estado_dict.get('fluxos_executados', [])
                    pendente = estado_dict.get('pendente')
                    clinico = estado_dict.get('clinico', {})
                    
                    print(f"   📊 DynamoDB - Fluxos executados: {fluxos}")
                    print(f"   📊 DynamoDB - Pendente: {'Sim' if pendente else 'Não'}")
                    print(f"   📊 DynamoDB - Vitais: {list(clinico.get('vitais', {}).keys())}")
                    print(f"   📊 DynamoDB - Nota: {'Sim' if clinico.get('nota') else 'Não'}")
                    
                except json.JSONDecodeError:
                    print(f"   ❌ DynamoDB - Erro ao fazer parse do JSON")
                    
            elif 'B' in response['Item']['estado']:
                print(f"   ⚠️  DynamoDB - Formato: Binary (formato antigo)")
            else:
                print(f"   ❌ DynamoDB - Formato desconhecido")
        else:
            print(f"   📊 DynamoDB - Estado não encontrado")
            
    except Exception as e:
        print(f"   ❌ DynamoDB - Erro: {e}")

def send_message(phone: str, text: str, message_id: str) -> dict:
    """Envia mensagem para o webhook"""
    payload = {
        "message_id": message_id,
        "phoneNumber": phone,
        "text": text,
        "meta": {"source": "context_test"}
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

def test_context_persistence():
    """Testa persistência de contexto entre mensagens"""
    log("🧪 TESTE DE CONTEXTO - WhatsApp Orchestrator")
    log("=" * 50)
    
    # Usar um telefone único para este teste
    phone = "5511111222333"
    session_id = phone  # Session ID é o mesmo que o telefone normalizado
    
    log(f"📱 Testando com telefone: {phone}")
    log(f"🔑 Session ID: {session_id}")
    
    # Limpar estado anterior (opcional)
    log("\n🧹 Verificando estado inicial...")
    check_dynamo_state(session_id)
    
    print("\n" + "="*50)
    
    # MENSAGEM 1: Dados clínicos
    log("📤 MENSAGEM 1: Enviando dados clínicos...")
    msg1 = send_message(phone, "PA 130x85 FC 80 FR 20 Sat 96 Temp 37.0 paciente com dor no peito", "ctx_001")
    
    log(f"📥 Resposta 1: {msg1.get('reply', msg1)[:100]}...")
    
    if 'error' not in msg1:
        log("✅ Mensagem 1 processada com sucesso")
        time.sleep(2)
        
        log("🔍 Verificando estado após mensagem 1...")
        check_dynamo_state(session_id)
    else:
        log(f"❌ Erro na mensagem 1: {msg1}")
        return False
    
    print("\n" + "="*50)
    
    # MENSAGEM 2: Confirmação
    log("📤 MENSAGEM 2: Enviando confirmação...")
    msg2 = send_message(phone, "sim", "ctx_002")
    
    log(f"📥 Resposta 2: {msg2.get('reply', msg2)[:100]}...")
    
    if 'error' not in msg2:
        log("✅ Mensagem 2 processada com sucesso")
        time.sleep(2)
        
        log("🔍 Verificando estado após mensagem 2...")
        check_dynamo_state(session_id)
    else:
        log(f"❌ Erro na mensagem 2: {msg2}")
        return False
    
    print("\n" + "="*50)
    
    # MENSAGEM 3: Nova interação
    log("📤 MENSAGEM 3: Nova interação...")
    msg3 = send_message(phone, "como estou?", "ctx_003")
    
    log(f"📥 Resposta 3: {msg3.get('reply', msg3)[:100]}...")
    
    if 'error' not in msg3:
        log("✅ Mensagem 3 processada com sucesso")
        time.sleep(2)
        
        log("🔍 Verificando estado final...")
        check_dynamo_state(session_id)
    else:
        log(f"❌ Erro na mensagem 3: {msg3}")
        return False
    
    print("\n" + "="*50)
    
    # ANÁLISE FINAL
    log("📊 ANÁLISE DE CONTEXTO:")
    
    # Verificar se houve continuidade
    if "confirma" in msg1.get('reply', '').lower():
        log("✅ Mensagem 1: Preparou confirmação corretamente")
    else:
        log("❌ Mensagem 1: Não preparou confirmação")
    
    if "erro" not in msg2.get('reply', '').lower() or "salv" in msg2.get('reply', '').lower():
        log("✅ Mensagem 2: Processou confirmação (ou mostrou contexto)")
    else:
        log("❌ Mensagem 2: Não processou confirmação corretamente")
    
    log("✅ Teste de contexto concluído!")
    return True

def main():
    """Função principal"""
    print("🎯 Testando Persistência de Contexto - WhatsApp Orchestrator")
    print("⚡ Certifique-se de que o servidor está rodando!")
    print()
    
    # Verificar se servidor está ativo
    try:
        response = requests.get("http://127.0.0.1:8000/healthz", timeout=5)
        if response.status_code != 200:
            print("❌ Servidor não está respondendo corretamente")
            return 1
        print("✅ Servidor ativo!")
    except:
        print("❌ Servidor não está rodando em http://127.0.0.1:8000")
        print("💡 Execute: uvicorn app.api.main:app --host 127.0.0.1 --port 8000")
        return 1
    
    print()
    
    try:
        success = test_context_persistence()
        return 0 if success else 1
    except KeyboardInterrupt:
        print("\n🛑 Teste interrompido pelo usuário")
        return 2
    except Exception as e:
        print(f"\n💥 ERRO: {e}")
        return 3

if __name__ == "__main__":
    exit(main())
