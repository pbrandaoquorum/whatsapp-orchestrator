# 🧪 Guia de Testes - WhatsApp Orchestrator

Este documento descreve como executar os testes do WhatsApp Orchestrator em diferentes cenários.

## 📋 Tipos de Teste

### 1. 🏥 **Testes Unitários** (`pytest`)
Testes isolados de componentes individuais:
```bash
# Executar todos os testes
make test
# ou
pytest tests/ -v

# Executar teste específico
pytest tests/test_clinico.py -v
pytest tests/test_router.py::test_intent_classification -v
```

### 2. ⚡ **Testes Rápidos** (Shell/curl)
Testes básicos de endpoints usando curl:
```bash
# Via Makefile
make test-quick

# Diretamente
./test_quick.sh

# Com URL customizada
BASE_URL="http://localhost:8080" ./test_quick.sh
```

**O que testa:**
- ✅ Health check (`/healthz`)
- ✅ Readiness check (`/readyz`) 
- ✅ Webhook básico
- ✅ Fluxos principais (clínico, escala, ajuda)

### 3. 🧪 **Testes de Produção** (Python completo)
Simulação completa de cenários reais:
```bash
# Via Makefile
make test-prod

# Diretamente
python test_production.py

# Com URL customizada
python test_production.py http://localhost:8080
```

**O que testa:**
- 🏥 Health/Readiness checks
- 📱 Fluxo clínico completo (LLM + validação)
- ✅ Two-phase commit (confirmações)
- 🏥 Fluxo de escala
- 📝 Fluxo operacional
- 🤖 Sistema de ajuda
- 🧠 Casos extremos (PA ambígua, valores inválidos)

## 🎯 Cenários de Teste Detalhados

### Fluxo Clínico (LLM + Validação)
```json
{
  "text": "PA 120x80 FC 75 FR 18 Sat 97 Temp 36.8 paciente com tosse seca"
}
```
**Esperado:**
- ✅ Extração via LLM (temp=0)
- ✅ Validação de faixas
- ✅ Preparação de confirmação
- ✅ RAG para sintomas (se nota presente)

### Casos Extremos
```json
// PA ambígua
{"text": "PA 12/8 e febre"}
// Esperado: PA=null, warning="PA_ambigua_12_8"

// Valores inválidos  
{"text": "FC 350 FR 5 saturação 120%"}
// Esperado: FC=null, Sat=null, warnings

// Somente nota
{"text": "Apenas uma nota sem vitais"}
// Esperado: todos vitais=null, nota preenchida
```

### Confirmações (TPC)
```json
// Após preparar dados clínicos
{"text": "sim"}   // Confirma e chama updateClinicalData
{"text": "não"}   // Cancela operação
```

## 📊 Interpretando Resultados

### ✅ **Sucessos Esperados**
- **Health/Readiness**: Sistema funcionando + DynamoDB conectado
- **Fluxo Clínico**: Extração LLM + validação + confirmação preparada
- **Sistema Ajuda**: Instruções completas geradas
- **Casos Extremos**: Tratamento correto de ambiguidades

### ⚠️ **"Erros" Esperados** (Normais em ambiente de teste)
- **Fluxo Escala**: "Dados da escala não encontrados" (sem schedule válido)
- **Fluxo Operacional**: "Cenário não reconhecido" (sem sessão válida)
- **Lambdas**: Erros HTTP 400/404 (endpoints de teste/desenvolvimento)

### ❌ **Erros Reais** (Precisam correção)
- Falha de conexão com DynamoDB
- Erro de parsing JSON do LLM
- Timeout em requisições
- Falha na classificação de intenção

## 🚀 Executando em Diferentes Ambientes

### Desenvolvimento Local
```bash
# 1. Iniciar servidor
make run
# ou
uvicorn app.api.main:app --reload

# 2. Em outro terminal
make test-quick
```

### Ambiente de Staging
```bash
# Testar ambiente remoto
python test_production.py https://staging.exemplo.com
./test_quick.sh  # (editar BASE_URL no script)
```

### CI/CD Pipeline
```yaml
# .github/workflows/test.yml
- name: Unit Tests
  run: pytest tests/ -v

- name: Integration Tests  
  run: |
    uvicorn app.api.main:app --host 0.0.0.0 --port 8000 &
    sleep 10
    python test_production.py
    pkill -f uvicorn
```

## 🔧 Troubleshooting

### Servidor não responde
```bash
# Verificar se está rodando
curl http://localhost:8000/healthz

# Verificar logs
make run  # Em foreground para ver logs

# Verificar porta
lsof -i :8000
```

### Falhas de LLM
```bash
# Verificar variáveis de ambiente
echo $OPENAI_API_KEY

# Testar classificação isolada
python -c "
from app.llm.classifier import IntentClassifier
c = IntentClassifier()
print(c.classificar_intencao('ajuda'))
"
```

### Problemas de DynamoDB
```bash
# Verificar tabelas
make dynamo-check

# Recriar se necessário
make dynamo-setup
```

## 📈 Métricas de Sucesso

### Taxa de Aprovação Mínima
- **Desenvolvimento**: 75% (6/8 testes)
- **Staging**: 85% (7/8 testes)  
- **Produção**: 95% (8/8 testes)

### Tempos Esperados
- **Health Check**: < 1s
- **Fluxo Clínico**: < 10s (inclui LLM)
- **Confirmação**: < 5s
- **Sistema Ajuda**: < 3s

### Logs Importantes
```json
{"event": "Sistema inicializado", "level": "info"}
{"event": "IntentClassifier inicializado", "model": "gpt-4o-mini"}
{"event": "Intenção classificada", "intencao": "clinico"}
{"event": "Estado salvo com sucesso", "tamanho_bytes": 1234}
```

## 🎉 Exemplo de Execução Completa

```bash
# 1. Setup inicial
make setup-full

# 2. Iniciar aplicação
make run &

# 3. Aguardar inicialização
sleep 5

# 4. Testes rápidos
make test-quick

# 5. Testes completos
make test-prod

# 6. Verificar relatório
ls test_report_*.json
```

## 💡 Dicas Avançadas

### Teste de Carga
```bash
# Múltiplas sessões simultâneas
for i in {1..10}; do
  curl -X POST localhost:8000/webhook/whatsapp \
    -H "Content-Type: application/json" \
    -d "{\"phoneNumber\": \"551199999999$i\", \"text\": \"ajuda\"}" &
done
wait
```

### Debug de Estado
```bash
# Verificar estado no DynamoDB
aws dynamodb get-item \
  --table-name ConversationStates \
  --key '{"session_id": {"S": "5511999999999"}}'
```

### Monitoramento Contínuo
```bash
# Loop de testes de saúde
while true; do
  make health && echo "✅ OK" || echo "❌ FAIL"
  sleep 30
done
```
