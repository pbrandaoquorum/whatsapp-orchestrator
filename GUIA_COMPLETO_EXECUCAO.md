# 🚀 GUIA COMPLETO - WhatsApp Orchestrator

## 📋 PRÉ-REQUISITOS

### 1. Sistema
- Python 3.11+
- pip (gerenciador de pacotes)
- Git

### 2. Contas/Serviços Necessários
- ✅ **OpenAI API Key** (obrigatório)
- ✅ **AWS Lambda URLs** (obrigatório)  
- ⚠️ **DynamoDB Local ou AWS** (opcional - usa fallback)
- ⚠️ **Pinecone** (opcional para RAG)
- ⚠️ **Redis** (opcional para cache)

---

## 🛠️ PASSO A PASSO - SETUP COMPLETO

### **PASSO 1: Clone e Setup Inicial**

```bash
# 1. Clone o repositório
git clone <seu-repo>
cd whatsapp-orchestrator

# 2. Criar ambiente virtual
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# ou
venv\Scripts\activate     # Windows

# 3. Instalar dependências
pip install -r requirements.txt
# ou se não existir requirements.txt:
pip install fastapi uvicorn openai langgraph langchain-openai boto3 httpx structlog python-dotenv nest-asyncio

# 4. Instalar DynamoDB Local (opcional)
# Para Mac com Homebrew:
brew install dynamodb-local
# Para outros sistemas, baixar do site da AWS
```

### **PASSO 2: Configuração das Variáveis de Ambiente**

```bash
# 1. Copiar arquivo de exemplo
cp env.example .env

# 2. Editar o arquivo .env com suas credenciais
nano .env  # ou seu editor preferido
```

**Configuração mínima obrigatória no `.env`:**

```env
# ✅ OBRIGATÓRIO - OpenAI
OPENAI_API_KEY=sk-sua-chave-openai-aqui

# ✅ OBRIGATÓRIO - URLs dos Lambdas AWS
LAMBDA_GET_SCHEDULE=https://sua-lambda-get.execute-api.sa-east-1.amazonaws.com/default/getScheduleStarted
LAMBDA_UPDATE_SCHEDULE=https://sua-lambda-update.execute-api.sa-east-1.amazonaws.com/default/updateWorkScheduleResponse
LAMBDA_UPDATE_CLINICAL=https://sua-lambda-clinical.execute-api.sa-east-1.amazonaws.com/default/updateClinicalData
LAMBDA_UPDATE_SUMMARY=https://sua-lambda-summary.execute-api.sa-east-1.amazonaws.com/default/updateReportSummary

# ⚠️ OPCIONAL - DynamoDB (usa fallback se não configurado)
AWS_ACCESS_KEY_ID=sua-chave-aws
AWS_SECRET_ACCESS_KEY=sua-chave-secreta-aws
AWS_DEFAULT_REGION=sa-east-1
DYNAMO_ENDPOINT=http://localhost:8000  # Para DynamoDB local

# ⚠️ OPCIONAL - Cache e RAG
REDIS_URL=redis://localhost:6379/0
PINECONE_API_KEY=sua-chave-pinecone
PINECONE_ENV=sua-env-pinecone
PINECONE_INDEX=whatsapp-orchestrator

# ⚠️ OPCIONAL - Configurações
LOG_LEVEL=INFO
TIMEOUT_LAMBDAS=30
MAX_RETRIES=3
```

### **PASSO 3: Setup do DynamoDB (Opcional)**

```bash
# Se usar DynamoDB local:
# Terminal 1 - Iniciar DynamoDB Local
dynamodb-local -sharedDb -port 8000

# Terminal 2 - Criar tabelas
cd whatsapp-orchestrator
source venv/bin/activate
python scripts/create_dynamo_tables.py
```

### **PASSO 4: Testar Configuração**

```bash
# Testar se tudo está configurado
python tests/test_local.py
```

**Saída esperada:**
```
🧪 TESTE LOCAL - WhatsApp Orchestrator
==================================================
✅ OPENAI_API_KEY: configurado
✅ LAMBDA_GET_SCHEDULE: configurado
✅ LAMBDA_UPDATE_SCHEDULE: configurado
✅ LAMBDA_UPDATE_CLINICAL: configurado
✅ LAMBDA_UPDATE_SUMMARY: configurado
✅ Configuração OK!
✅ FastAPI importado com sucesso
✅ LangGraph builder importado
✅ Classificação semântica funcionando!
✅ TODOS OS TESTES PASSARAM!
```

---

## 🚀 EXECUTAR A APLICAÇÃO

### **MÉTODO 1: Servidor de Desenvolvimento**

```bash
# Terminal 1 - Iniciar aplicação
cd whatsapp-orchestrator
source venv/bin/activate
export PYTHONPATH=$PWD
uvicorn app.api.main:app --reload --host 127.0.0.1 --port 8000
```

**Saída esperada:**
```
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Started reloader process
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

### **MÉTODO 2: Servidor de Produção**

```bash
# Produção com mais workers
uvicorn app.api.main:app --host 0.0.0.0 --port 8000 --workers 4
```

---

## 🧪 TESTAR FUNCIONALIDADES

### **TESTE 1: Health Check**

```bash
# Verificar se servidor está funcionando
curl http://127.0.0.1:8000/healthz
```

**Resposta esperada:**
```json
{"status": "healthy", "timestamp": "2025-09-17T19:30:00Z"}
```

### **TESTE 2: Endpoint Principal**

```bash
# Testar webhook do WhatsApp
curl -X POST http://127.0.0.1:8000/webhook/whatsapp \
  -H "Content-Type: application/json" \
  -H "X-Idempotency-Key: test-123" \
  -d '{
    "message_id": "msg_001",
    "phoneNumber": "+5511999999999",
    "text": "Cheguei no plantão da Dona Maria"
  }'
```

**Resposta esperada:**
```json
{
  "success": true,
  "message": "✅ Presença confirmada! Agora você pode informar os sinais vitais...",
  "session_id": "session_5511999999999",
  "next_action": "clinical"
}
```

### **TESTE 3: Script Completo de Cenários**

```bash
# Executar todos os cenários de teste
python test_webhook_direct.py
```

**Este script testa:**
- ✅ Fluxo completo (chegada → confirmação → sinais vitais → nota → finalização)
- ✅ Cancelamento de plantão
- ✅ Coleta de sinais vitais detalhados  
- ✅ Nota clínica completa
- ✅ Mensagens simples e ambíguas

---

## 📱 SIMULAR MENSAGENS DE USUÁRIO

### **OPÇÃO 1: Via cURL (Manual)**

```bash
# Mensagem 1: Chegada
curl -X POST http://127.0.0.1:8000/webhook/whatsapp \
  -H "Content-Type: application/json" \
  -H "X-Idempotency-Key: test-chegada" \
  -d '{
    "message_id": "msg_chegada",
    "phoneNumber": "+5511987654321",
    "text": "Oi, cheguei no plantão da Dona Maria. Como procedo?"
  }'

# Mensagem 2: Confirmação
curl -X POST http://127.0.0.1:8000/webhook/whatsapp \
  -H "Content-Type: application/json" \
  -H "X-Idempotency-Key: test-confirmacao" \
  -d '{
    "message_id": "msg_confirmacao", 
    "phoneNumber": "+5511987654321",
    "text": "Confirmo minha presença no local"
  }'

# Mensagem 3: Sinais Vitais
curl -X POST http://127.0.0.1:8000/webhook/whatsapp \
  -H "Content-Type: application/json" \
  -H "X-Idempotency-Key: test-vitais" \
  -d '{
    "message_id": "msg_vitais",
    "phoneNumber": "+5511987654321", 
    "text": "PA 130x85, FC 82 bpm, FR 20 irpm, Saturação 96%, Temperatura 36.8°C"
  }'

# Mensagem 4: Nota Clínica
curl -X POST http://127.0.0.1:8000/webhook/whatsapp \
  -H "Content-Type: application/json" \
  -H "X-Idempotency-Key: test-nota" \
  -d '{
    "message_id": "msg_nota",
    "phoneNumber": "+5511987654321",
    "text": "Paciente consciente, orientada, colaborativa. Refere dor leve em MMII. Deambula com auxílio."
  }'

# Mensagem 5: Finalização
curl -X POST http://127.0.0.1:8000/webhook/whatsapp \
  -H "Content-Type: application/json" \
  -H "X-Idempotency-Key: test-final" \
  -d '{
    "message_id": "msg_final",
    "phoneNumber": "+5511987654321",
    "text": "Plantão finalizado. Como envio o relatório?"
  }'
```

### **OPÇÃO 2: Via Script Python (Automatizado)**

```bash
# Executar cenários automatizados
python test_webhook_direct.py
```

### **OPÇÃO 3: Via Postman/Insomnia**

1. **URL:** `POST http://127.0.0.1:8000/webhook/whatsapp`
2. **Headers:**
   ```
   Content-Type: application/json
   X-Idempotency-Key: test-unique-id
   ```
3. **Body (JSON):**
   ```json
   {
     "message_id": "msg_001",
     "phoneNumber": "+5511999999999",
     "text": "Sua mensagem aqui"
   }
   ```

---

## 🔍 MONITORAMENTO E LOGS

### **Ver Logs em Tempo Real**

```bash
# Logs estruturados no console
tail -f logs/app.log | jq .

# Ou executar com log level debug
LOG_LEVEL=DEBUG uvicorn app.api.main:app --reload
```

### **Endpoints de Monitoramento**

```bash
# Health check
curl http://127.0.0.1:8000/healthz

# Readiness check  
curl http://127.0.0.1:8000/readyz

# Métricas (se implementado)
curl http://127.0.0.1:8000/metrics
```

---

## ❌ TROUBLESHOOTING

### **Erro: OpenAI API Key**
```
❌ OPENAI_API_KEY não configurada!
```
**Solução:** Configurar a chave no arquivo `.env`

### **Erro: Lambda não responde**
```
❌ Erro ao obter dados do turno: timeout
```
**Solução:** Verificar URLs dos Lambdas no `.env`

### **Erro: DynamoDB**
```
❌ Could not connect to the endpoint URL
```
**Solução:** Verificar se DynamoDB local está rodando ou usar AWS

### **Erro: Asyncio**
```
❌ asyncio.run() cannot be called from a running event loop
```
**Solução:** Já corrigido com `nest_asyncio`

### **Erro: Imports**
```
❌ ModuleNotFoundError: No module named 'app'
```
**Solução:** Configurar `PYTHONPATH`:
```bash
export PYTHONPATH=$PWD
```

---

## 🎯 PRÓXIMOS PASSOS

1. ✅ **Sistema Funcionando:** Aplicação roda localmente
2. ✅ **Testes Passando:** Todos os cenários funcionam
3. ✅ **Chamadas Reais:** Sem mocks, apenas integrações reais
4. 🔄 **Deploy:** Configurar para produção
5. 🔄 **Monitoramento:** Implementar métricas avançadas

---

## 📞 SUPORTE

Se encontrar problemas:

1. **Verificar logs:** `tail -f logs/app.log`
2. **Testar configuração:** `python tests/test_local.py`
3. **Verificar variáveis:** `env | grep -E "(OPENAI|LAMBDA)"`
4. **Reiniciar servidor:** Ctrl+C e rodar novamente

**Sistema 100% operacional e testado! 🚀**
