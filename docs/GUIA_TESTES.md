# 🧪 Guia Completo de Testes - WhatsApp Orchestrator

## 🎯 **CHECKLIST DE PRÉ-REQUISITOS**

### ✅ **1. Dependências Instaladas**
```bash
cd /Users/pedro/geria/repo-lambdas/sessionLambdas/whatsapp-orchestrator

# Instalar dependências
pip install -e .

# Verificar instalação
python -c "import app; print('✅ App importada com sucesso')"
```

### ✅ **2. Variáveis de Ambiente**
```bash
# Copiar template
cp env.example .env

# Editar .env com suas credenciais
nano .env
```

**Variáveis OBRIGATÓRIAS:**
```bash
# OpenAI (para classificação semântica)
OPENAI_API_KEY=sk-...

# Lambdas AWS (4 URLs obrigatórias)
LAMBDA_GET_SCHEDULE=https://f35khigesh.execute-api.sa-east-1.amazonaws.com/default/getScheduleStarted
LAMBDA_UPDATE_SCHEDULE=https://f35khigesh.execute-api.sa-east-1.amazonaws.com/default/updateWorkScheduleResponse
LAMBDA_UPDATE_CLINICAL=https://aitacl3wg8.execute-api.sa-east-1.amazonaws.com/Prod/updateClinicalData
LAMBDA_UPDATE_SUMMARY=https://f35khigesh.execute-api.sa-east-1.amazonaws.com/default/updateReportSummaryAD

# Redis (recomendado)
REDIS_URL=redis://localhost:6379/0

# Pinecone (para RAG)
PINECONE_API_KEY=...
PINECONE_ENV=us-east-1-aws
PINECONE_INDEX=sintomas-index

# Google Sheets (para sintomas)
GOOGLE_SHEETS_ID=...
GOOGLE_SERVICE_ACCOUNT_JSON=path/to/service-account.json
```

### ✅ **3. Serviços Externos**
```bash
# Testar Redis
redis-cli ping
# Resposta esperada: PONG

# Testar Lambdas
curl -X POST https://f35khigesh.execute-api.sa-east-1.amazonaws.com/default/getScheduleStarted \
  -H "Content-Type: application/json" \
  -d '{"phoneNumber": "+5511999999999"}'
# Resposta esperada: JSON com dados do turno

# Testar OpenAI
python -c "
import openai
openai.api_key = 'sk-...'
print('✅ OpenAI configurado')
"
```

## 🚀 **FASE 1: TESTES UNITÁRIOS**

### **1.1 Classificador Semântico**
```bash
# Executar testes do classificador
pytest tests/test_semantic_classifier.py -v

# Testes específicos
pytest tests/test_semantic_classifier.py::test_classificacao_confirmar_presenca -v
pytest tests/test_semantic_classifier.py::test_classificacao_sinais_vitais -v
pytest tests/test_semantic_classifier.py::test_circuit_breaker_fallback -v
```

**Casos de Teste Esperados:**
- ✅ "cheguei" → `CONFIRMAR_PRESENCA` (confiança > 0.8)
- ✅ "PA 120x80, FC 78" → `SINAIS_VITAIS` + extração correta
- ✅ "paciente consciente" → `NOTA_CLINICA`
- ✅ Circuit breaker → fallback determinístico
- ✅ LLM as Judge → correção de classificações

### **1.2 Router Determinístico**
```bash
pytest tests/test_router.py -v
```

**Casos de Teste Esperados:**
- ✅ Retomada pendente tem prioridade máxima
- ✅ Pergunta pendente processada corretamente
- ✅ Gates de negócio sempre prevalecem
- ✅ Finalizar sem SV → força clinical primeiro

### **1.3 Clinical Extractor**
```bash
pytest tests/test_clinical_extractor.py -v
```

**Casos de Teste Esperados:**
- ✅ "PA 120x80" → `{"PA": "120x80"}`
- ✅ "FC 78 bpm" → `{"FC": 78}`
- ✅ "temperatura 36,5°C" → `{"Temp": 36.5}`
- ✅ Formatos variados (120/80, 36.5, etc.)

## 🔥 **FASE 2: TESTES DE INTEGRAÇÃO**

### **2.1 Iniciar Aplicação**
```bash
# Terminal 1: Iniciar FastAPI
uvicorn app.api.main:app --reload --log-level debug

# Aguardar mensagem:
# INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

### **2.2 Health Checks**
```bash
# Terminal 2: Testar health checks
curl http://localhost:8000/healthz
# Resposta esperada: {"status": "healthy", "timestamp": "..."}

curl http://localhost:8000/readyz
# Resposta esperada: {"status": "ready", "services": {"redis": true, ...}}
```

### **2.3 Teste Básico de Webhook**
```bash
# Teste 1: Mensagem simples
curl -X POST http://localhost:8000/webhook/whatsapp \
  -H "Content-Type: application/json" \
  -d '{
    "message_id": "test_001",
    "phoneNumber": "+5511999999999",
    "text": "cheguei"
  }' | jq .

# Resposta esperada:
# {
#   "success": true,
#   "message": "Confirma presença no plantão? (sim/não)",
#   "session_id": "session_5511999999999",
#   "next_action": "escala"
# }
```

### **2.4 Demo Interativa**
```bash
# Executar demo interativa
python demo_semantic_classification.py

# Escolher opção 2 (modo interativo)
# Testar diferentes mensagens:
# - "cheguei"
# - "PA 120x80, FC 78"
# - "finalizar"
# - "ajuda"
```

## 🎭 **FASE 3: CENÁRIOS COMPLETOS**

### **3.1 Happy Path Completo**

#### **Passo 1: Confirmação de Presença**
```bash
curl -X POST http://localhost:8000/webhook/whatsapp \
  -H "Content-Type: application/json" \
  -d '{
    "message_id": "hp_001",
    "phoneNumber": "+5511888888888",
    "text": "cheguei, confirmo presença"
  }'

# Resposta esperada: "Confirma presença no plantão? (sim/não)"
```

```bash
curl -X POST http://localhost:8000/webhook/whatsapp \
  -H "Content-Type: application/json" \
  -d '{
    "message_id": "hp_002",
    "phoneNumber": "+5511888888888",
    "text": "sim"
  }'

# Resposta esperada: "✅ Presença confirmada! Agora você pode informar sinais vitais..."
```

#### **Passo 2: Sinais Vitais**
```bash
curl -X POST http://localhost:8000/webhook/whatsapp \
  -H "Content-Type: application/json" \
  -d '{
    "message_id": "hp_003",
    "phoneNumber": "+5511888888888",
    "text": "PA 120x80, FC 78, FR 18, Sat 97%, Temp 36.5°C"
  }'

# Resposta esperada: "Confirma salvar estes sinais vitais? ..."
```

```bash
curl -X POST http://localhost:8000/webhook/whatsapp \
  -H "Content-Type: application/json" \
  -d '{
    "message_id": "hp_004",
    "phoneNumber": "+5511888888888",
    "text": "sim"
  }'

# Resposta esperada: "✅ Dados salvos! Você pode finalizar o plantão..."
```

#### **Passo 3: Finalização**
```bash
curl -X POST http://localhost:8000/webhook/whatsapp \
  -H "Content-Type: application/json" \
  -d '{
    "message_id": "hp_005",
    "phoneNumber": "+5511888888888",
    "text": "finalizar"
  }'

# Resposta esperada: "Confirma finalizar plantão? Relatório: ..."
```

```bash
curl -X POST http://localhost:8000/webhook/whatsapp \
  -H "Content-Type: application/json" \
  -d '{
    "message_id": "hp_006",
    "phoneNumber": "+5511888888888",
    "text": "sim"
  }'

# Resposta esperada: "🎉 Plantão finalizado com sucesso! ..."
```

### **3.2 Coleta Incremental**
```bash
# SV enviados aos poucos
curl -X POST http://localhost:8000/webhook/whatsapp \
  -d '{"message_id": "inc_001", "phoneNumber": "+5511777777777", "text": "PA 120x80"}'
# Esperado: "Coletado PA. Ainda faltam: FC, FR, Sat, Temp"

curl -X POST http://localhost:8000/webhook/whatsapp \
  -d '{"message_id": "inc_002", "phoneNumber": "+5511777777777", "text": "FC 78, Sat 97%"}'
# Esperado: "Coletados FC e Sat. Ainda faltam: FR, Temp"

curl -X POST http://localhost:8000/webhook/whatsapp \
  -d '{"message_id": "inc_003", "phoneNumber": "+5511777777777", "text": "FR 18, Temp 36.8"}'
# Esperado: "Todos os sinais coletados! Confirma salvar?"
```

### **3.3 Retomada de Contexto**
```bash
# Tentar finalizar sem SV
curl -X POST http://localhost:8000/webhook/whatsapp \
  -d '{"message_id": "ret_001", "phoneNumber": "+5511666666666", "text": "quero finalizar"}'
# Esperado: "Para finalizar, você precisa informar sinais vitais primeiro..."

curl -X POST http://localhost:8000/webhook/whatsapp \
  -d '{"message_id": "ret_002", "phoneNumber": "+5511666666666", "text": "PA 130x85, FC 82, FR 16, Sat 98%, Temp 36.2"}'
# Esperado: Sistema salva SV e automaticamente retoma finalização
```

### **3.4 Notas Clínicas com RAG**
```bash
curl -X POST http://localhost:8000/webhook/whatsapp \
  -H "Content-Type: application/json" \
  -d '{
    "message_id": "rag_001",
    "phoneNumber": "+5511555555555",
    "text": "Paciente apresenta cefaleia intensa e náuseas"
  }'

# Esperado: Sistema identifica sintomas via Pinecone e pergunta confirmação
```

## 🛡️ **FASE 4: TESTES DE ROBUSTEZ**

### **4.1 Circuit Breakers**
```bash
# Simular falha OpenAI (remover/alterar OPENAI_API_KEY temporariamente)
export OPENAI_API_KEY="invalid_key"

curl -X POST http://localhost:8000/webhook/whatsapp \
  -d '{"message_id": "cb_001", "phoneNumber": "+5511444444444", "text": "cheguei"}'

# Esperado: Sistema usa fallback determinístico
# Resposta deve ser funcional mesmo com LLM falhando
```

### **4.2 Deduplicação**
```bash
# Enviar mesma mensagem 3 vezes
for i in {1..3}; do
  curl -X POST http://localhost:8000/webhook/whatsapp \
    -d '{"message_id": "dup_001", "phoneNumber": "+5511333333333", "text": "teste"}'
done

# Esperado: 
# 1ª chamada: processamento normal
# 2ª e 3ª: resposta do cache (mais rápida)
```

### **4.3 Timeout e Retry**
```bash
# Simular timeout (desconectar internet temporariamente durante teste)
curl -X POST http://localhost:8000/webhook/whatsapp \
  -d '{"message_id": "timeout_001", "phoneNumber": "+5511222222222", "text": "cheguei"}' \
  --max-time 5

# Esperado: Erro graceful ou retry automático
```

## 📊 **FASE 5: MONITORAMENTO E MÉTRICAS**

### **5.1 Logs Estruturados**
```bash
# Acompanhar logs em tempo real
tail -f logs/app.log | jq .

# Verificar campos obrigatórios nos logs:
# - timestamp
# - nivel
# - evento  
# - session_id
# - request_id
# - tempo_execucao_ms
```

### **5.2 Métricas de Performance**
```bash
# Testar performance com múltiplas chamadas
for i in {1..10}; do
  curl -s -w "%{time_total}\n" -X POST http://localhost:8000/webhook/whatsapp \
    -d "{\"message_id\": \"perf_$i\", \"phoneNumber\": \"+551199999999$i\", \"text\": \"teste\"}" \
    -o /dev/null
done

# Esperado: < 1 segundo por chamada
```

### **5.3 Cache Hit Rates**
```bash
# Verificar estatísticas de cache
curl http://localhost:8000/debug/cache-stats | jq .

# Esperado:
# {
#   "memory": {"entries": 10, "hit_rate": 85.5},
#   "redis": {"available": true, "entries": 25}
# }
```

### **5.4 Circuit Breaker Status**
```bash
# Verificar status dos circuit breakers
curl http://localhost:8000/debug/circuit-breakers | jq .

# Esperado:
# {
#   "llm_classifier": {"state": "closed", "success_rate": 98.5},
#   "lambda_update_clinical": {"state": "closed", "success_rate": 99.1}
# }
```

## 🔧 **FASE 6: INTEGRAÇÃO COM SEU WEBHOOK**

### **6.1 Adaptar Seu Webhook**
No seu webhook atual, substitua a chamada para n8n por:

```javascript
// Antes (n8n)
const response = await fetch('https://n8n-webhook-url', {
  method: 'POST',
  body: JSON.stringify({
    phoneNumber: message.from,
    text: message.body
  })
});

// Depois (WhatsApp Orchestrator)
const response = await fetch('http://localhost:8000/webhook/whatsapp', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    message_id: message.id,
    phoneNumber: message.from,
    text: message.body,
    meta: {} // metadados opcionais
  })
});

const result = await response.json();

if (result.success) {
  // Enviar resposta ao usuário via Meta API
  await sendWhatsAppMessage(message.from, result.message);
} else {
  console.error('Erro no orchestrator:', result);
}
```

### **6.2 Notificar Templates**
Sempre que seu webhook enviar um template, notifique o orchestrator:

```javascript
// Após enviar template
await fetch('http://localhost:8000/events/template-sent', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    phoneNumber: destinatario,
    template: 'confirmar_presenca', // ou 'pedir_sinais_vitais', etc.
    metadata: {
      hint_campos_faltantes: ['FR', 'Sat', 'Temp'],
      shiftDay: '2025-01-15'
    }
  })
});
```

## ✅ **CHECKLIST FINAL DE VALIDAÇÃO**

### **Funcionalidades Core**
- [ ] Classificação semântica funcionando (OpenAI)
- [ ] LLM as a Judge validando classificações
- [ ] Circuit breakers protegendo falhas
- [ ] Cache otimizando performance
- [ ] Two-phase commit em todas as ações críticas
- [ ] Coleta incremental de sinais vitais
- [ ] Retomada de contexto após interrupções
- [ ] RAG identificando sintomas via Pinecone
- [ ] 4 Lambdas AWS respondendo corretamente

### **Robustez**
- [ ] Deduplicação de mensagens
- [ ] Checkpointing Redis funcionando
- [ ] Fallbacks determinísticos ativos
- [ ] Logs estruturados em português
- [ ] Health checks passando
- [ ] Timeouts e retries configurados

### **Performance**
- [ ] < 1s resposta end-to-end
- [ ] Cache hit rate > 80%
- [ ] Circuit breakers com success rate > 95%
- [ ] Memória estável sem vazamentos

### **Integração**
- [ ] Webhook adaptado para chamar orchestrator
- [ ] Templates notificando estado
- [ ] Formato de entrada/saída compatível
- [ ] Logs correlacionados entre sistemas

## 🚨 **PROBLEMAS COMUNS E SOLUÇÕES**

### **Erro: "OPENAI_API_KEY não configurada"**
```bash
export OPENAI_API_KEY="sk-sua-chave-aqui"
# ou adicionar no .env
```

### **Erro: "Redis connection failed"**
```bash
# Instalar e iniciar Redis
brew install redis  # macOS
redis-server

# Ou usar Redis remoto
export REDIS_URL="redis://user:pass@host:port/db"
```

### **Erro: "Lambda timeout"**
```bash
# Verificar URLs dos Lambdas
curl -X POST $LAMBDA_GET_SCHEDULE -d '{"phoneNumber": "+5511999999999"}'

# Aumentar timeout se necessário
export TIMEOUT_LAMBDAS=60
```

### **Performance Lenta**
```bash
# Verificar cache
curl http://localhost:8000/debug/cache-stats

# Verificar circuit breakers
curl http://localhost:8000/debug/circuit-breakers

# Analisar logs de performance
grep "tempo_execucao_ms" logs/app.log | jq .tempo_execucao_ms
```

## 📈 **MÉTRICAS DE SUCESSO**

- **Funcionalidade**: 100% dos cenários principais funcionando
- **Performance**: < 1s resposta média, 95% das chamadas < 2s
- **Confiabilidade**: > 99% de disponibilidade, circuit breakers ativos
- **Inteligência**: > 90% de classificações corretas, fallbacks < 5%
- **UX**: Two-phase commit claro, coleta incremental suave

**Sistema pronto para produção quando todos os checkboxes estiverem ✅!** 🚀
