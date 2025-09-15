# WhatsApp Orchestrator

Sistema **FastAPI + LangGraph** para orquestração de fluxos WhatsApp em plantões domiciliares. Utiliza **classificação semântica via LLM (GPT-4o-mini)** com **LLM as a Judge** para substituir detecção por keywords, mantendo **determinismo** através de state machine explícita, **circuit breakers**, **cache inteligente** e **two-phase commit** para todas as ações críticas.

## 🏗️ Arquitetura

### Componentes Principais

- **FastAPI**: API REST para receber mensagens e enviar respostas
- **LangGraph**: Orquestração de fluxos com estado persistente
- **Classificador Semântico**: LLM (GPT-4o-mini) + LLM as a Judge para classificação inteligente
- **Router Determinístico**: State machine explícita com gates de negócio
- **Circuit Breaker**: Proteção contra falhas de LLM e Lambda
- **Cache Inteligente**: Memória + Redis para otimizar chamadas LLM
- **4 Lambdas AWS**: Integração com sistema existente via HTTP
- **Redis**: Checkpointing e cache
- **Pinecone**: RAG para identificação de sintomas
- **Google Sheets**: Base de dados de sintomas

### Fluxos Implementados

1. **Escala**: Confirmação/cancelamento de presença
2. **Clinical**: Coleta de sinais vitais e dados clínicos  
3. **Notas**: Notas clínicas com identificação de sintomas via RAG
4. **Finalizar**: Encerramento do plantão com relatório
5. **Auxiliar**: Orientações e esclarecimentos

## 🚀 Instalação e Configuração

### Pré-requisitos

- Python 3.11+
- Redis (para checkpointing)
- Conta Pinecone (para RAG)
- Conta Google Cloud (para Sheets)
- Chaves de API (OpenAI, Pinecone, etc.)

### Instalação

```bash
# Clonar repositório
git clone <repo-url>
cd whatsapp-orchestrator

# Instalar dependências
pip install -e .

# Copiar configurações
cp env.example .env
```

### Configuração (.env)

```bash
# Redis
REDIS_URL=redis://user:pass@host:11078/0

# Lambdas AWS  
LAMBDA_GET_SCHEDULE=https://f35khigesh.execute-api.sa-east-1.amazonaws.com/default/getScheduleStarted
LAMBDA_UPDATE_SCHEDULE=https://f35khigesh.execute-api.sa-east-1.amazonaws.com/default/updateWorkScheduleResponse
LAMBDA_UPDATE_CLINICAL=https://aitacl3wg8.execute-api.sa-east-1.amazonaws.com/Prod/updateClinicalData
LAMBDA_UPDATE_SUMMARY=https://f35khigesh.execute-api.sa-east-1.amazonaws.com/default/updateReportSummaryAD

# Pinecone RAG
PINECONE_API_KEY=your_pinecone_api_key
PINECONE_ENV=your_pinecone_environment  
PINECONE_INDEX=sintomas-index

# Google Sheets
GOOGLE_SHEETS_ID=your_google_sheets_id
GOOGLE_SERVICE_ACCOUNT_JSON=path/to/service-account.json

# OpenAI (fallback LLM)
OPENAI_API_KEY=your_openai_api_key

# Configurações
LOG_LEVEL=INFO
TIMEOUT_LAMBDAS=30
MAX_RETRIES=3
```

### Executar Aplicação

```bash
# Desenvolvimento
uvicorn app.api.main:app --reload

# Produção
uvicorn app.api.main:app --host 0.0.0.0 --port 8000
```

## 📡 API Endpoints

### Webhook Principal

```http
POST /webhook/whatsapp
Content-Type: application/json

{
  "message_id": "msg_123456",
  "phoneNumber": "+5511999999999", 
  "text": "cheguei, confirmo presença",
  "meta": {}
}
```

**Resposta:**
```json
{
  "success": true,
  "message": "✅ Presença confirmada! Agora você pode informar sinais vitais...",
  "session_id": "session_5511999999999",
  "next_action": "clinical"
}
```

### Notificação de Template

```http
POST /events/template-sent
Content-Type: application/json

{
  "phoneNumber": "+5511999999999",
  "template": "confirmar_presenca",
  "metadata": {
    "hint_campos_faltantes": ["FR","Sat","Temp"],
    "shiftDay": "2025-01-15"
  }
}
```

### Outros Endpoints

- `GET /healthz` - Health check
- `GET /readyz` - Readiness check  
- `POST /graph/debug/run` - Debug do grafo
- `POST /rag/sync` - Sincronizar base de sintomas
- `POST /rag/search` - Buscar sintomas similares

## 🧠 Como Funciona

### 1. Ciclo de Vida da Mensagem

```
Mensagem WhatsApp → FastAPI → Dedupe → LangGraph → Router → Fluxo → Lambda → Resposta
```

### 2. Router Determinístico

O router segue esta **ordem de prioridade**:

1. **Bootstrap da sessão** (se necessário)
2. **Retomada pendente** (`aux.retomar_apos`)  
3. **Pergunta pendente** (two-phase commit ou coleta incremental)
4. **Detecção determinística** de sinais vitais no texto
5. **Fallback LLM** (temperatura 0, JSON estruturado)
6. **Gates de negócio** (presença, sinais vitais, turno cancelado)

### 3. Two-Phase Commit

**Todas** as ações que chamam Lambdas usam confirmação:

```
Ação → Staging → "Confirma X? (sim/não)" → Commit/Cancel
```

**Exemplo:**
```
Usuário: "cheguei"
Sistema: "Confirma presença no plantão de 15/01 às 14h? (sim/não)"  
Usuário: "sim"
Sistema: ✅ Presença confirmada! [chama Lambda]
```

### 4. Coleta Incremental

Sinais vitais podem ser enviados **aos poucos**:

```
Usuário: "PA 120x80"
Sistema: "Coletado PA. Ainda faltam: FC, FR, Sat, Temp"

Usuário: "FC 78, Sat 97%"  
Sistema: "Coletados FC e Sat. Ainda faltam: FR, Temp"

Usuário: "FR 18, Temp 36.8"
Sistema: "Todos os sinais coletados! Confirma salvar?"
```

## 🔄 Fluxos Detalhados

### Fluxo de Confirmação (Escala)

```mermaid
graph TD
    A[Detectar intenção] --> B{Confirmar/Cancelar?}
    B -->|Confirmar| C[Staging: confirmar presença]
    B -->|Cancelar| D[Staging: cancelar presença]  
    C --> E[Pergunta: "Confirma presença?"]
    D --> F[Pergunta: "Confirma cancelamento?"]
    E --> G{Resposta}
    F --> G
    G -->|Sim| H[Commit: Lambda updateWorkScheduleResponse]
    G -->|Não| I[Cancel: voltar ao início]
    H --> J[Atualizar metadados + re-bootstrap]
```

### Fluxo Clínico (Sinais Vitais)

```mermaid
graph TD
    A[Extrair sinais vitais] --> B{Todos coletados?}
    B -->|Não| C[Solicitar faltantes]
    B -->|Sim| D[Staging: salvar dados]
    C --> E[Coleta incremental]
    E --> A
    D --> F[Pergunta: "Confirma salvar dados?"]
    F --> G{Resposta}
    G -->|Sim| H[Commit: Lambda updateClinicalData]
    G -->|Não| I[Cancel: continuar coletando]
    H --> J[Marcar SV realizados]
```

### Fluxo de Finalização

```mermaid
graph TD
    A[Validar pré-requisitos] --> B{Presença + SV OK?}
    B -->|Não| C[Orientar sobre faltantes]
    B -->|Sim| D[Montar dados do relatório]
    D --> E[Staging: finalizar plantão]
    E --> F[Pergunta: "Confirma finalizar?"]
    F --> G{Resposta}
    G -->|Sim| H[Commit: Lambda updatereportsummaryad]
    G -->|Não| I[Cancel: continuar plantão]
    H --> J[Plantão finalizado + DailyReport]
```

## 🧪 RAG e Identificação de Sintomas

### Google Sheets → Pinecone

1. **Planilha** com colunas: `sintoma`, `pontuacao`, `categoria`, `subcategoria`
2. **Sincronização** via `POST /rag/sync`
3. **Embeddings** com SentenceTransformers (multilingual)
4. **Busca** por similaridade com limiar configurável

### Formato SymptomReport

```json
{
  "symptomDefinition": "dor de cabeça",
  "altNotepadMain": "cefaleia",
  "symptomCategory": "Neurológico", 
  "symptomSubCategory": "Dor",
  "descricaoComparada": "dor de cabeça intensa",
  "coeficienteSimilaridade": 0.85
}
```

## 🔧 Cenários do updateClinicalData

O Lambda recebe **7 cenários** diferentes:

1. `VITAL_SIGNS_NOTE_SYMPTOMS` - SV + nota + sintomas
2. `VITAL_SIGNS_SYMPTOMS` - SV + sintomas (sem nota)
3. `VITAL_SIGNS_NOTE` - SV + nota (sem sintomas)  
4. `VITAL_SIGNS_ONLY` - Apenas SV
5. `NOTE_SYMPTOMS` - Nota + sintomas (sem SV)
6. `SYMPTOMS_ONLY` - Apenas sintomas
7. `NOTE_ONLY` - Apenas nota

## 📊 Exemplos de Uso

### Happy Path Completo

```bash
# 1. Confirmação de presença
curl -X POST http://localhost:8000/webhook/whatsapp \
  -H "Content-Type: application/json" \
  -d '{
    "message_id": "msg_001",
    "phoneNumber": "+5511999999999",
    "text": "cheguei, confirmo presença"
  }'

# Resposta: "Confirma presença no plantão? (sim/não)"

curl -X POST http://localhost:8000/webhook/whatsapp \
  -H "Content-Type: application/json" \
  -d '{
    "message_id": "msg_002", 
    "phoneNumber": "+5511999999999",
    "text": "sim"
  }'

# Resposta: "✅ Presença confirmada! Agora você pode informar sinais vitais..."

# 2. Sinais vitais
curl -X POST http://localhost:8000/webhook/whatsapp \
  -H "Content-Type: application/json" \
  -d '{
    "message_id": "msg_003",
    "phoneNumber": "+5511999999999", 
    "text": "PA 120x80, FC 78, FR 18, Sat 97%, Temp 36.5°C"
  }'

# Resposta: "Confirma salvar estes sinais vitais? PA: 120x80, FC: 78 bpm..."

curl -X POST http://localhost:8000/webhook/whatsapp \
  -H "Content-Type: application/json" \
  -d '{
    "message_id": "msg_004",
    "phoneNumber": "+5511999999999",
    "text": "sim"
  }'

# Resposta: "✅ Dados salvos! Você pode finalizar o plantão..."

# 3. Finalização  
curl -X POST http://localhost:8000/webhook/whatsapp \
  -H "Content-Type: application/json" \
  -d '{
    "message_id": "msg_005",
    "phoneNumber": "+5511999999999",
    "text": "finalizar"
  }'

# Resposta: "Confirma finalizar plantão? Relatório: report_123..."
```

### Retomada de Contexto

```bash
# Usuário tenta finalizar sem sinais vitais
curl -X POST http://localhost:8000/webhook/whatsapp \
  -H "Content-Type: application/json" \
  -d '{
    "message_id": "msg_006",
    "phoneNumber": "+5511999999999", 
    "text": "quero finalizar"
  }'

# Sistema: "Para finalizar, você precisa informar sinais vitais primeiro..."

curl -X POST http://localhost:8000/webhook/whatsapp \
  -H "Content-Type: application/json" \
  -d '{
    "message_id": "msg_007",
    "phoneNumber": "+5511999999999",
    "text": "PA 130x85, FC 82, FR 16, Sat 98%, Temp 36.2°C"
  }'

# Sistema salva SV e automaticamente retoma finalização
# "✅ Sinais vitais salvos! Agora vamos finalizar o plantão..."
```

### Coleta Incremental

```bash
# Sinais vitais enviados aos poucos
curl -X POST http://localhost:8000/webhook/whatsapp \
  -d '{"message_id": "msg_008", "phoneNumber": "+5511999999999", "text": "PA 120x80"}'

# Resposta: "Coletado PA. Ainda faltam: FC, FR, Sat, Temp"

curl -X POST http://localhost:8000/webhook/whatsapp \
  -d '{"message_id": "msg_009", "phoneNumber": "+5511999999999", "text": "FC 78, Sat 97%"}'

# Resposta: "Coletados FC e Sat. Ainda faltam: FR, Temp"

curl -X POST http://localhost:8000/webhook/whatsapp \
  -d '{"message_id": "msg_010", "phoneNumber": "+5511999999999", "text": "FR 18, Temp 36.8"}'

# Resposta: "Todos os sinais coletados! Confirma salvar? PA: 120x80, FC: 78 bpm..."
```

## 🧪 Testes

### Executar Testes

```bash
# Todos os testes
pytest

# Testes específicos  
pytest tests/test_clinical_extractor.py
pytest tests/test_router.py
pytest tests/test_confirm.py

# Com cobertura
pytest --cov=app --cov-report=html

# Apenas testes rápidos (sem integração)
pytest -m "not integration and not slow"
```

### Testes Implementados

- ✅ **ClinicalExtractor**: Regex para sinais vitais
- ✅ **Router**: Lógica determinística e gates  
- ✅ **Confirmação**: Reconhecimento sim/não em PT-BR
- ⏳ **Fluxos**: Testes dos 5 subgrafos
- ⏳ **API**: Testes dos endpoints
- ⏳ **RAG**: Testes do Pinecone/Sheets

## 🔍 Debugging

### Debug do Grafo

```bash
curl -X POST http://localhost:8000/graph/debug/run \
  -H "Content-Type: application/json" \
  -d '{
    "phoneNumber": "+5511999999999",
    "text": "PA 120x80, quero finalizar",
    "initial_state": {
      "metadados": {"presenca_confirmada": true}
    }
  }'
```

### Logs Estruturados

```json
{
  "timestamp": "2025-01-15T14:30:00-03:00",
  "nivel": "informacao", 
  "evento": "roteamento_concluido",
  "session_id": "session_5511999999999",
  "intencao_llm": "finalizar",
  "intencao_final": "clinical", 
  "fluxo_final": "clinical",
  "motivo": "vitals_before_finish"
}
```

### Monitoramento

- **Request ID** em todos os logs
- **Tempo de execução** por endpoint
- **Status das dependências** via `/readyz`
- **Métricas do Redis** e Pinecone
- **Cache hit/miss** rates

## 🤖 Classificação Semântica com LLM

### Arquitetura Inteligente

O sistema utiliza **GPT-4o-mini** para classificação semântica de intenções, com **LLM as a Judge** para validação e correção automática:

```python
# Classificação principal
resultado = await classify_semantic(texto, estado)

# Validação com Judge (se confiança < 0.8)
if resultado.confidence < 0.8:
    resultado = await validar_com_judge(texto, resultado, estado)
```

### Intenções Suportadas

- `CONFIRMAR_PRESENCA`: "cheguei", "estou aqui", "confirmo presença"
- `CANCELAR_PRESENCA`: "cancelar", "não posso ir", "imprevisto"
- `SINAIS_VITAIS`: "PA 120x80", "FC 78 bpm", "temperatura 36.5"
- `NOTA_CLINICA`: "paciente consciente", "sem alterações"
- `FINALIZAR_PLANTAO`: "finalizar", "encerrar plantão"
- `CONFIRMACAO_SIM/NAO`: confirmações genéricas
- `PEDIR_AJUDA`: "ajuda", "não sei"
- `INDEFINIDO`: quando não é possível classificar

### Circuit Breaker e Fallbacks

```python
# Proteção contra falhas
@circuit_breaker("llm_classifier", LLM_CIRCUIT_CONFIG)
async def _executar_classificacao_llm(texto, estado):
    # Chamada LLM protegida
    
# Fallback determinístico
except CircuitBreakerError:
    return await _fallback_classificacao_deterministica(texto, estado)
```

### Cache Inteligente

- **Memória**: Cache local (LRU) para respostas rápidas
- **Redis**: Cache distribuído com TTL configurável
- **TTL Otimizado**: 30min para LLM, 1h para RAG, 5min para Lambda

## 📋 Quando Usar LLM vs Determinístico

### ✅ Determinístico (Sempre Preferir)

- **Retomada** (`aux.retomar_apos`) → seguir direto
- **Pergunta pendente** → validar sim/não por regex
- **Sinais vitais** → extrair por regex (PA, FC, FR, Sat, Temp)
- **Gates de negócio** → presença, SV obrigatórios, turno cancelado
- **Ferramentas/Lambdas** → payload e cenários 100% determinísticos

### 🤖 LLM (Apenas Fallback)

- **Classificação de intenção** quando **nenhuma** regra resolveu
- **Temperatura 0** + JSON estruturado obrigatório
- **Sempre validado** por gates pós-classificação
- **(Opcional)** Extração de termos para RAG se heurística falhar

## 🔒 Segurança e Idempotência

### Two-Phase Commit

- **Staging** → pergunta de confirmação → **Commit/Cancel**
- **Timeout** de 10 minutos para confirmação
- **Idempotência** via `message_id` e `acao_pendente.executado`

### Dedupe de Mensagens

- **Redis**: `msg:{message_id}` com TTL de 10 minutos
- **Cache de resposta** para mensagens duplicadas
- **Middleware** automático no FastAPI

### Validações

- **Pydantic v2** para todos os schemas
- **Range validation** para sinais vitais
- **Sanitização** de dados sensíveis nos logs

## 🚀 Deploy e Produção

### Variáveis Críticas

```bash
# Obrigatórias (aplicação não inicia sem elas)
LAMBDA_GET_SCHEDULE=https://...
LAMBDA_UPDATE_SCHEDULE=https://...
LAMBDA_UPDATE_CLINICAL=https://...  
LAMBDA_UPDATE_SUMMARY=https://...

# Recomendadas
REDIS_URL=redis://...
PINECONE_API_KEY=...
OPENAI_API_KEY=...
```

### Docker (Opcional)

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY pyproject.toml .
RUN pip install -e .

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Health Checks

- `GET /healthz` - Básico (sempre retorna OK)
- `GET /readyz` - Completo (testa Redis, Pinecone, Sheets, Lambdas)

## 📞 Integração com Webhook Existente

Seu webhook atual **permanece responsável** por:

- ✅ Processar mensagens da Meta
- ✅ Enviar respostas ao WhatsApp  
- ✅ Enviar templates proativos

### Fluxo de Integração

```
Meta → Seu Webhook → POST /webhook/whatsapp → Resposta → Seu Webhook → Meta
```

### Notificar Templates

**Sempre** que enviar um template, chame:

```bash
POST /events/template-sent
{
  "phoneNumber": "+5511999999999", 
  "template": "pedir_sinais_vitais",
  "metadata": {"hint_campos_faltantes": ["FR","Sat","Temp"]}
}
```

Isso **ajusta o estado** para a próxima mensagem cair no fluxo certo.

## 🤝 Contribuição

### Estrutura do Código

```
app/
├── api/          # FastAPI (routes, schemas, middleware)
├── graph/        # LangGraph (router, flows, state, tools)  
├── rag/          # Pinecone + Google Sheets
└── infra/        # Redis, logging, two-phase commit
```

### Padrões

- **Português BR** para logs, variáveis e comentários
- **Pydantic v2** para validação
- **Async/await** para I/O
- **Structured logging** com contexto
- **Type hints** obrigatórios
- **Docstrings** em português

### Adicionar Novo Fluxo

1. Criar `app/graph/flows/novo_flow.py`
2. Implementar função principal + two-phase commit
3. Adicionar nó em `app/graph/builder.py`
4. Atualizar router em `app/graph/router.py`
5. Criar testes em `tests/test_novo_flow.py`

## 📚 Referências

- [LangGraph Docs](https://langchain-ai.github.io/langgraph/)
- [FastAPI Docs](https://fastapi.tiangolo.com/)
- [Pydantic v2](https://docs.pydantic.dev/latest/)
- [Redis Python](https://redis-py.readthedocs.io/)
- [Pinecone Docs](https://docs.pinecone.io/)

## 📄 Licença

[Definir licença apropriada]

---

**Sistema robusto, determinístico e state-aware para orquestração de plantões domiciliares via WhatsApp** 🏥📱
