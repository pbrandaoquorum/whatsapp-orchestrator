#!/bin/bash
# Script de Teste Rápido - WhatsApp Orchestrator
# Executa testes básicos usando curl

set -e

BASE_URL="http://127.0.0.1:8000"
TIMESTAMP=$(date +"%H:%M:%S")

echo "🚀 TESTES RÁPIDOS - WhatsApp Orchestrator"
echo "⏰ Iniciado em: $TIMESTAMP"
echo "🎯 URL: $BASE_URL"
echo "=" | tr -d '\n'; for i in {1..50}; do echo -n "="; done; echo

# Função para log com timestamp
log() {
    echo "[$(date +"%H:%M:%S")] $1"
}

# Função para testar endpoint
test_endpoint() {
    local name="$1"
    local method="$2"
    local endpoint="$3"
    local data="$4"
    
    log "🔍 Testando: $name"
    
    if [ "$method" = "GET" ]; then
        response=$(curl -s -w "\n%{http_code}" "$BASE_URL$endpoint" || echo -e "\nERROR")
    else
        response=$(curl -s -w "\n%{http_code}" -X "$method" "$BASE_URL$endpoint" \
            -H "Content-Type: application/json" \
            -d "$data" || echo -e "\nERROR")
    fi
    
    # Extrair código de status da última linha
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | head -n -1 2>/dev/null || echo "$response" | sed '$d')
    
    if [ "$http_code" = "200" ]; then
        log "✅ $name: OK"
        echo "   Resposta: $(echo "$body" | jq -r '.reply // .message // .status // .' 2>/dev/null | head -c 80)..."
    else
        log "❌ $name: FALHOU (HTTP $http_code)"
        echo "   Erro: $(echo "$body" | head -c 100)..."
    fi
    
    echo
    sleep 1
}

# Verificar se o servidor está rodando
log "🏥 Verificando se servidor está ativo..."
if ! curl -s "$BASE_URL" >/dev/null 2>&1; then
    log "❌ ERRO: Servidor não está rodando em $BASE_URL"
    log "💡 Execute: uvicorn app.api.main:app --host 127.0.0.1 --port 8000"
    exit 1
fi

log "✅ Servidor ativo!"
echo

# Teste 1: Health Check
test_endpoint "Health Check" "GET" "/healthz" ""

# Teste 2: Readiness Check
test_endpoint "Readiness Check" "GET" "/readyz" ""

# Teste 3: Webhook - Dados Clínicos
clinical_data='{
    "message_id": "test_001",
    "phoneNumber": "5511999999999",
    "text": "PA 120x80 FC 75 FR 18 Sat 97 Temp 36.8 paciente com tosse",
    "meta": {"source": "test"}
}'
test_endpoint "Fluxo Clínico" "POST" "/webhook/whatsapp" "$clinical_data"

# Teste 4: Webhook - Confirmação
confirmation_data='{
    "message_id": "test_002",
    "phoneNumber": "5511999999999",
    "text": "sim",
    "meta": {}
}'
test_endpoint "Confirmação" "POST" "/webhook/whatsapp" "$confirmation_data"

# Teste 5: Webhook - Ajuda
help_data='{
    "message_id": "test_003",
    "phoneNumber": "5511666666666",
    "text": "ajuda",
    "meta": {}
}'
test_endpoint "Sistema de Ajuda" "POST" "/webhook/whatsapp" "$help_data"

# Teste 6: Webhook - Escala
schedule_data='{
    "message_id": "test_004",
    "phoneNumber": "5511888888888",
    "text": "confirmo presença",
    "meta": {}
}'
test_endpoint "Fluxo Escala" "POST" "/webhook/whatsapp" "$schedule_data"

# Resumo
echo "=" | tr -d '\n'; for i in {1..50}; do echo -n "="; done; echo
log "🎉 TESTES CONCLUÍDOS!"
log "📊 Verifique os resultados acima"
log "💡 Para testes detalhados: python test_production.py"
echo
