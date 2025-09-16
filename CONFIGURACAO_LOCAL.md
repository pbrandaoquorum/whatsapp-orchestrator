# 🚀 Configuração para Testes Locais

## 📋 Pré-requisitos Obrigatórios

### 1. **Chave OpenAI (OBRIGATÓRIO)**
- Crie uma conta em https://platform.openai.com/
- Gere uma API key em https://platform.openai.com/api-keys
- Adicione no `.env`: `OPENAI_API_KEY=sk-...`

### 2. **URLs das Lambdas AWS (OBRIGATÓRIO)**
As URLs no `.env` são exemplos. Você precisa das URLs reais das suas lambdas:
```
LAMBDA_GET_SCHEDULE=https://sua-lambda.execute-api.sa-east-1.amazonaws.com/default/getScheduleStarted
LAMBDA_UPDATE_SCHEDULE=https://sua-lambda.execute-api.sa-east-1.amazonaws.com/default/updateWorkScheduleResponse
LAMBDA_UPDATE_CLINICAL=https://sua-lambda.execute-api.sa-east-1.amazonaws.com/Prod/updateClinicalData
LAMBDA_UPDATE_SUMMARY=https://sua-lambda.execute-api.sa-east-1.amazonaws.com/default/updateReportSummaryAD
```

### 3. **Redis (Recomendado)**
Para desenvolvimento local:
```bash
# macOS (com Homebrew)
brew install redis
brew services start redis

# Ubuntu/Debian
sudo apt update && sudo apt install redis-server
sudo systemctl start redis-server

# Docker (alternativa)
docker run -d -p 6379:6379 redis:alpine
```

### 4. **Pinecone (Opcional para testes básicos)**
- Crie uma conta em https://www.pinecone.io/
- Crie um índice chamado `sintomas-index`
- Configure: `PINECONE_API_KEY` e `PINECONE_ENV`

### 5. **Google Sheets (Opcional para testes básicos)**
- Configure service account no Google Cloud Console
- Baixe o arquivo JSON das credenciais
- Configure: `GOOGLE_SHEETS_ID` e `GOOGLE_SERVICE_ACCOUNT_JSON`

## ⚡ Instalação Rápida

```bash
# 1. Instalar dependências
pip install -e .

# 2. Configurar variáveis (edite o arquivo .env)
cp env.example .env
nano .env  # ou code .env

# 3. Testar Redis (opcional)
redis-cli ping  # Deve retornar PONG

# 4. Executar aplicação
uvicorn app.api.main:app --reload

# 5. Testar endpoint
curl -X POST http://localhost:8000/webhook/whatsapp \
  -H "Content-Type: application/json" \
  -d '{
    "message_id": "test_123",
    "phoneNumber": "+5511999999999",
    "text": "cheguei, confirmo presença"
  }'
```

## 🧪 Testes Básicos

### Teste 1: Confirmação de Presença
```bash
curl -X POST http://localhost:8000/webhook/whatsapp \
  -H "Content-Type: application/json" \
  -d '{
    "message_id": "test_001",
    "phoneNumber": "+5511999999999",
    "text": "cheguei no local"
  }'
```

### Teste 2: Sinais Vitais
```bash
curl -X POST http://localhost:8000/webhook/whatsapp \
  -H "Content-Type: application/json" \
  -d '{
    "message_id": "test_002", 
    "phoneNumber": "+5511999999999",
    "text": "PA 120x80, FC 78, FR 18, Sat 97%, Temp 36.5"
  }'
```

### Teste 3: Nota Clínica
```bash
curl -X POST http://localhost:8000/webhook/whatsapp \
  -H "Content-Type: application/json" \
  -d '{
    "message_id": "test_003",
    "phoneNumber": "+5511999999999", 
    "text": "paciente consciente e orientado, sem queixas"
  }'
```

## 🔧 Troubleshooting

### Erro: "Variáveis de ambiente obrigatórias não configuradas"
- Verifique se todas as URLs das Lambdas estão configuradas no `.env`
- Certifique-se que o arquivo `.env` está na raiz do projeto

### Erro: "OpenAI API key not found"
- Configure `OPENAI_API_KEY` no `.env` com uma chave válida
- Teste a chave: `curl -H "Authorization: Bearer sk-..." https://api.openai.com/v1/models`

### Erro: "Redis connection failed"
- Inicie o Redis: `redis-server` ou `brew services start redis`
- Ou configure `REDIS_URL` para um Redis remoto
- Para desenvolvimento, Redis é opcional (dados ficam em memória)

### Erro: "Lambda timeout" ou "500 Internal Server Error"
- Verifique se as URLs das Lambdas estão corretas
- Teste as Lambdas diretamente com curl
- Ajuste `TIMEOUT_LAMBDAS` no `.env` se necessário

## 📊 Monitoramento

### Logs
```bash
# Ver logs em tempo real
tail -f logs/app.log

# Ou executar com logs no console
uvicorn app.api.main:app --reload --log-level debug
```

### Health Check
```bash
# Verificar se aplicação está funcionando
curl http://localhost:8000/healthz

# Verificar dependências
curl http://localhost:8000/readyz
```

## 🎯 Modo de Desenvolvimento

Para desenvolvimento sem dependências externas:
```bash
# Criar .env mínimo (apenas OpenAI obrigatório)
cat > .env << EOF
OPENAI_API_KEY=sk-your-key-here
REDIS_URL=redis://localhost:6379/0
LAMBDA_GET_SCHEDULE=http://localhost:8001/mock/getSchedule
LAMBDA_UPDATE_SCHEDULE=http://localhost:8001/mock/updateSchedule
LAMBDA_UPDATE_CLINICAL=http://localhost:8001/mock/updateClinical
LAMBDA_UPDATE_SUMMARY=http://localhost:8001/mock/updateSummary
LOG_LEVEL=DEBUG
EOF

# Executar com mocks (se implementados)
uvicorn app.api.main:app --reload --port 8000
```

## 📚 Próximos Passos

1. **Configure OpenAI**: Essencial para classificação semântica
2. **Configure Lambdas**: Para integração com sistema existente  
3. **Configure Redis**: Para persistência de estado
4. **Configure Pinecone**: Para RAG de sintomas (opcional)
5. **Execute testes**: Use os exemplos de curl acima

A aplicação agora usa **100% classificação semântica via LLM** - não há mais regex ou keywords no código! 🎉
