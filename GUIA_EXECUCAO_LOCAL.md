# 🚀 Guia de Execução Local - WhatsApp Orchestrator

## 📋 Pré-requisitos

### 1. Python 3.13+ e Dependências
```bash
# Verificar versão do Python
python3 --version

# Ativar ambiente virtual
source venv/bin/activate

# Instalar dependências (se necessário)
pip install -r requirements.txt
```

### 2. Variáveis de Ambiente
Certifique-se de que o arquivo `.env` está configurado:

```bash
# Copiar exemplo se necessário
cp env.example .env

# Editar .env com suas chaves
nano .env
```

**Variáveis obrigatórias:**
```env
# OpenAI
OPENAI_API_KEY=sk-...

# AWS DynamoDB
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=us-east-1
DYNAMO_TABLE_NAME=whatsapp-orchestrator-states

# URLs dos Lambdas
LAMBDA_GET_SCHEDULE_URL=https://...
LAMBDA_UPDATE_SCHEDULE_URL=https://...
LAMBDA_UPDATE_CLINICAL_URL=https://...
LAMBDA_UPDATE_REPORT_URL=https://...

# Modelos LLM
INTENT_MODEL=gpt-4o-mini
EXTRACTOR_MODEL=gpt-4o-mini
```

### 3. DynamoDB Local (Opcional)
Se quiser usar DynamoDB local:
```bash
# Instalar DynamoDB Local
docker run -p 8000:8000 amazon/dynamodb-local

# Criar tabela
python scripts/create_dynamo_tables.py
```

## 🏃‍♂️ Executando a Aplicação

### 1. Iniciar o Servidor
```bash
# Ativar ambiente virtual
source venv/bin/activate

# Iniciar servidor FastAPI
python -m uvicorn app.api.main:app --reload --host 127.0.0.1 --port 8000

# Ou usando o Makefile
make run
```

### 2. Verificar se está funcionando
```bash
# Testar endpoint de saúde
curl http://127.0.0.1:8000/health

# Resposta esperada:
# {"status": "healthy", "timestamp": "..."}
```

## 🧪 Testando com cURL

### 1. Teste Básico - Confirmação de Presença
```bash
curl -X POST "http://127.0.0.1:8000/webhook/whatsapp" \
  -H "Content-Type: application/json" \
  -d '{
    "message_id": "test_001",
    "phoneNumber": "5511991261390",
    "text": "confirmo presença",
    "meta": {"source": "test"}
  }' | jq .
```

**Resposta esperada:**
```json
{
  "reply": "Confirma sua presença no plantão?",
  "session_id": "5511991261390",
  "status": "success"
}
```

### 2. Teste de Dados Clínicos Parciais
```bash
curl -X POST "http://127.0.0.1:8000/webhook/whatsapp" \
  -H "Content-Type: application/json" \
  -d '{
    "message_id": "test_002",
    "phoneNumber": "5511991261390",
    "text": "PA 120x80 FC 75",
    "meta": {"source": "test"}
  }' | jq .
```

**Resposta esperada:**
```json
{
  "reply": "Salvei os vitais: PA 120x80, FC 75.\nPor favor, envie também uma nota clínica (ou 'sem alterações').",
  "session_id": "5511991261390",
  "status": "success"
}
```

### 3. Teste de Dados Clínicos Completos
```bash
curl -X POST "http://127.0.0.1:8000/webhook/whatsapp" \
  -H "Content-Type: application/json" \
  -d '{
    "message_id": "test_003",
    "phoneNumber": "5511991261390",
    "text": "paciente sem alterações",
    "meta": {"source": "test"}
  }' | jq .
```

**Resposta esperada:**
```json
{
  "reply": "Confirma salvar:\nVitais: PA 120x80, FC 75\nNota: paciente sem alterações",
  "session_id": "5511991261390",
  "status": "success"
}
```

### 4. Teste de Confirmação
```bash
curl -X POST "http://127.0.0.1:8000/webhook/whatsapp" \
  -H "Content-Type: application/json" \
  -d '{
    "message_id": "test_004",
    "phoneNumber": "5511991261390",
    "text": "sim",
    "meta": {"source": "test"}
  }' | jq .
```

**Resposta esperada:**
```json
{
  "reply": "Dados clínicos processados com sucesso!",
  "session_id": "5511991261390",
  "status": "success"
}
```

### 5. Teste de Ajuda
```bash
curl -X POST "http://127.0.0.1:8000/webhook/whatsapp" \
  -H "Content-Type: application/json" \
  -d '{
    "message_id": "test_005",
    "phoneNumber": "5511991261390",
    "text": "oi, bom dia",
    "meta": {"source": "test"}
  }' | jq .
```

## 📊 Monitoramento e Debug

### 1. Logs em Tempo Real
```bash
# Seguir logs do servidor
tail -f logs/app.log

# Ou usar journalctl se estiver usando systemd
journalctl -f -u whatsapp-orchestrator
```

### 2. Verificar Estado no DynamoDB
```bash
# Script para verificar estados
python scripts/check_dynamo_tables.py

# Ou consulta direta
aws dynamodb scan --table-name whatsapp-orchestrator-states --region us-east-1
```

### 3. Testar Componentes Individuais
```bash
# Testar extração clínica
python -c "
from app.llm.extractor import ClinicalExtractor
import os
extractor = ClinicalExtractor(os.getenv('OPENAI_API_KEY'))
result = extractor.extrair_json('PA 120x80 FC 75 paciente bem')
print(result)
"

# Testar classificação de intenção
python -c "
from app.llm.confirmation_classifier import ConfirmationClassifier
import os
classifier = ConfirmationClassifier(os.getenv('OPENAI_API_KEY'))
result = classifier.classificar_confirmacao('pode salvar')
print(result)
"
```

## 🔧 Comandos Úteis do Makefile

```bash
# Executar aplicação
make run

# Executar testes
make test

# Limpar ambiente
make clean

# Verificar lint
make lint

# Instalar dependências
make install
```

## 🐛 Troubleshooting

### Erro: "Connection refused"
```bash
# Verificar se o servidor está rodando
ps aux | grep uvicorn

# Verificar porta
netstat -tlnp | grep 8000

# Reiniciar servidor
pkill -f uvicorn
python -m uvicorn app.api.main:app --reload --host 127.0.0.1 --port 8000
```

### Erro: "OpenAI API key not found"
```bash
# Verificar variáveis de ambiente
env | grep OPENAI

# Recarregar .env
source .env
```

### Erro: "DynamoDB access denied"
```bash
# Verificar credenciais AWS
aws sts get-caller-identity

# Verificar permissões da tabela
aws dynamodb describe-table --table-name whatsapp-orchestrator-states
```

### Erro: "Module not found"
```bash
# Verificar ambiente virtual
which python
pip list

# Reinstalar dependências
pip install -r requirements.txt
```

## 📝 Estrutura de Payload para Webhook N8N

O sistema agora envia dados para o webhook n8n com a seguinte estrutura:

```json
{
  "reportID": "...",
  "reportDate": "...",
  "patientIdentifier": "...",
  "caregiverIdentifier": "...",
  "scheduleID": "...",
  "sessionID": "5511991261390",
  "respRate": 18,
  "saturationO2": 98,
  "bloodPressure": "120x80",
  "heartRate": 75,
  "temperature": 36.5,
  "supplementaryOxygen": null,
  "oxygenVolume": null,
  "oxygenConcentrator": null,
  "clinicalNote": "paciente sem alterações"
}
```

## 🎯 Fluxo de Dados Clínicos

1. **Dados Parciais**: Sistema armazena no estado DynamoDB
2. **Dados Completos**: Sistema prepara confirmação
3. **Confirmação**: Sistema envia para webhook n8n
4. **RAG**: Processado pelo n8n (não localmente)

---

## ✅ Checklist de Verificação

- [ ] Servidor rodando na porta 8000
- [ ] Variáveis de ambiente configuradas
- [ ] DynamoDB acessível
- [ ] OpenAI API key válida
- [ ] Webhook n8n respondendo
- [ ] Testes básicos passando

**🎉 Aplicação pronta para uso!**
