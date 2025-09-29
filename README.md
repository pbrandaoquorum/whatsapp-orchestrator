# WhatsApp Orchestrator 🤖

Sistema inteligente de orquestração para WhatsApp com processamento de dados clínicos, gerenciamento de escalas e notas operacionais.

## 🏗️ Arquitetura

```
app/
├── 🌐 api/                 # FastAPI - Endpoints e dependências
├── 🧠 graph/               # Lógica de negócio e fluxos
│   ├── fiscal.py              # Processador fiscal (resposta ao usuário)
│   ├── router.py              # Roteamento inteligente
│   ├── state.py               # Estado unificado do sistema
│   └── subgraphs/             # Módulos especializados
│       ├── auxiliar.py        # Ajuda e instruções
│       ├── clinico.py         # Dados clínicos (vitais, notas)
│       ├── escala.py          # Confirmação de presença
│       ├── finalizar.py       # Finalização de plantão
│       └── operacional.py     # Notas operacionais instantâneas
├── 🔧 infra/               # Infraestrutura e integrações
│   ├── dynamo_state.py        # Gerenciamento de estado no DynamoDB
│   ├── http.py                # Cliente HTTP para Lambdas/Webhooks
│   └── logging.py             # Configuração de logs estruturados
└── 🤖 llm/                 # Módulos de Inteligência Artificial
    ├── classifiers/           # Classificação de entrada
    │   ├── confirmation.py    # Classificação de confirmações (sim/não)
    │   ├── intent.py          # Classificação de intenções
    │   └── operational.py     # Detecção de notas operacionais
    ├── extractors/            # Extração estruturada
    │   └── clinical.py        # Extração de dados clínicos via LLM
    └── generators/            # Geração de conteúdo
        └── fiscal.py          # Geração de respostas contextuais
```

## 📂 Explicação Detalhada dos Arquivos

### 🌐 **API Layer** (`app/api/`)
- **`main.py`** - Aplicação FastAPI principal, define endpoints e middleware
- **`deps.py`** - Gerenciamento de dependências, inicialização de componentes e injeção

### 🧠 **Graph Layer** (`app/graph/`) - Lógica de Negócio
- **`state.py`** - Define o modelo Pydantic do estado unificado da conversa
- **`router.py`** - Roteador principal que direciona mensagens para subgrafos apropriados
- **`fiscal.py`** - Processador fiscal que lê estado do DynamoDB e gera resposta final

#### 🔧 **Subgrafos** (`app/graph/subgraphs/`) - Módulos Especializados
- **`auxiliar.py`** - Processa pedidos de ajuda e instruções gerais
- **`clinico.py`** - Gerencia coleta de sinais vitais, notas clínicas e condições respiratórias
- **`escala.py`** - Controla confirmação de presença e início de plantão
- **`finalizar.py`** - Processa finalização de plantão e envio de relatórios
- **`operacional.py`** - Processa notas operacionais instantâneas (sem confirmação)

### 🔧 **Infrastructure Layer** (`app/infra/`)
- **`dynamo_state.py`** - Cliente DynamoDB para persistência de estado de conversação
- **`http.py`** - Cliente HTTP para integração com Lambdas AWS e webhooks n8n
- **`logging.py`** - Configuração de logs estruturados com contexto e metadata

### 🤖 **LLM Layer** (`app/llm/`) - Inteligência Artificial

#### 📋 **Classificadores** (`app/llm/classifiers/`)
- **`intent.py`** - Classifica intenção do usuário (escala/clinico/finalizar/auxiliar)
- **`confirmation.py`** - Detecta confirmações em respostas (sim/não/talvez)
- **`operational.py`** - Identifica notas operacionais urgentes para envio instantâneo

#### 🔍 **Extratores** (`app/llm/extractors/`)
- **`clinical.py`** - Extrai sinais vitais, notas clínicas e condições respiratórias com validação

#### 🎭 **Geradores** (`app/llm/generators/`)
- **`fiscal.py`** - Gera respostas contextuais dinâmicas baseadas no estado completo

### 🛠️ **Scripts de Desenvolvimento** (`scripts/`)
- **`create_dynamo_tables.py`** - Script para criar tabelas DynamoDB necessárias
- **`check_dynamo_tables.py`** - Verifica se tabelas DynamoDB existem e estão configuradas

### 📚 **Referências** (`references/`)
- **`getschedulestarted.js`** - Código de referência do Lambda para consulta de escala
- **`updateworkscheduleresponse.js`** - Lambda para confirmação de presença no plantão
- **`updatereportsummaryad.js`** - Lambda para finalização e relatório de plantão
- **`updateclinicaldata/`** - Estrutura completa do Lambda para processamento de dados clínicos

### 📋 **Arquivos de Configuração**
- **`pyproject.toml`** - Configuração do projeto Python, dependências e metadados
- **`Makefile`** - Comandos automatizados para desenvolvimento (dev, test, clean, etc.)
- **`GUIA_EXECUCAO_LOCAL.md`** - Guia detalhado para executar o sistema localmente
- **`README.md`** - Este arquivo, documentação principal do projeto

## 🎯 Funcionalidades Principais

### 📋 **Classificação Inteligente (Zero Keywords)**
- **Intenções**: Detecta automaticamente se usuário quer confirmar presença, enviar dados clínicos, finalizar plantão ou pedir ajuda
- **Confirmações**: Classifica respostas como sim/não/talvez usando LLM
- **Notas Operacionais**: Detecta urgências como "acabou a fralda", "ar condicionado quebrou"

### 🏥 **Processamento Clínico Avançado**
- **Extração de Vitais**: PA, FC, FR, Saturação, Temperatura com validação automática
- **Condição Respiratória**: Ar ambiente, Ventilação mecânica, Oxigênio suplementar
- **Notas Clínicas**: Captura descrições como "paciente estável", "sem queixas"
- **Limpeza Automática**: Estado clínico é limpo após envio bem-sucedido

### ⚡ **Notas Operacionais Instantâneas**
- **Envio Direto**: Sem confirmação para urgências operacionais
- **Detecção LLM**: Identifica automaticamente falta de materiais, problemas estruturais
- **Webhook n8n**: Integração direta para processamento imediato

### 🧠 **Fiscal Inteligente**
- **Respostas Dinâmicas**: Nunca usa respostas estáticas
- **Contexto Completo**: Lê estado canônico do DynamoDB
- **LLM Contextual**: Gera respostas baseadas no histórico completo

### 🔄 **Gerenciamento de Estado Otimizado**
- **Estado Limpo**: Remove campos desnecessários (turno_permitido, cancelado, sintomas)
- **Preservação Inteligente**: Mantém dados clínicos durante confirmações
- **Two-Phase Commit**: Confirmações seguras para operações críticas

## 🚀 Executar Localmente

### 1. **Configuração Inicial**
```bash
# Clonar repositório
git clone <repo-url>
cd whatsapp-orchestrator

# Criar ambiente virtual
python -m venv venv
source venv/bin/activate  # Linux/Mac
# ou venv\Scripts\activate  # Windows

# Instalar dependências
pip install -e .
```

### 2. **Configurar Variáveis de Ambiente**
```bash
cp .env.example .env
# Editar .env com suas chaves:
# - OPENAI_API_KEY=your_key_here
# - AWS_ACCESS_KEY_ID=your_key
# - AWS_SECRET_ACCESS_KEY=your_secret
```

### 3. **Criar Tabelas DynamoDB** (Opcional)
```bash
# Verificar tabelas existentes
make check-dynamo

# Criar tabelas se necessário
make create-dynamo
```

### 4. **Executar Aplicação**
```bash
# Desenvolvimento
make dev

# Ou manualmente
uvicorn app.api.main:app --reload --host 0.0.0.0 --port 8000
```

### 5. **Testar via curl**
```bash
# Teste básico
curl -X POST "http://localhost:8000/webhook/whatsapp" \
  -H "Content-Type: application/json" \
  -d '{
    "message_id": "test_001",
    "phoneNumber": "5511999999999",
    "text": "confirmo presença",
    "meta": {"source": "test"}
  }'

# Teste com dados clínicos
curl -X POST "http://localhost:8000/webhook/whatsapp" \
  -H "Content-Type: application/json" \
  -d '{
    "message_id": "test_002", 
    "phoneNumber": "5511999999999",
    "text": "PA 120x80, FC 78, FR 18, Sat 97%, Temp 36.5°C, paciente estável em ar ambiente",
    "meta": {"source": "test"}
  }'

# Teste nota operacional
curl -X POST "http://localhost:8000/webhook/whatsapp" \
  -H "Content-Type: application/json" \
  -d '{
    "message_id": "test_003",
    "phoneNumber": "5511999999999", 
    "text": "acabou a fralda do paciente",
    "meta": {"source": "test"}
  }'
```

## 🔧 Comandos Make

```bash
make help          # Ver todos os comandos
make dev           # Executar em desenvolvimento
make clean         # Limpar cache Python
make check-dynamo  # Verificar tabelas DynamoDB
make create-dynamo # Criar tabelas DynamoDB
```

## 🧪 Fluxos de Teste

### **Fluxo Completo de Plantão**
1. `"confirmo presença"` → Confirma plantão
2. `"PA 120x80 FC 78 paciente estável"` → Coleta dados clínicos
3. `"confirmo, pode salvar"` → Envia para webhook n8n
4. `"finalizar plantão"` → Encerra plantão

### **Notas Operacionais Instantâneas**
- `"acabou a fralda"` → Enviado imediatamente
- `"ar condicionado quebrou"` → Prioridade alta
- `"médico visitou"` → Registrado instantaneamente

## 🌐 Integrações

- **🔗 Webhook n8n**: Processamento de dados clínicos
- **⚡ AWS Lambdas**: getScheduleStarted, updateWorkScheduleResponse, updateReportSummary
- **🗄️ DynamoDB**: Persistência de estado de conversação
- **🤖 OpenAI GPT-4o-mini**: Classificação, extração e geração de conteúdo

## 📊 Monitoramento

- **📝 Logs Estruturados**: JSON com contexto completo
- **🔍 Rastreamento**: Session ID, fluxos executados, timestamps
- **⚠️ Alertas**: Erros de LLM, falhas de integração, dados inválidos

## 🛠️ Tecnologias

- **🐍 Python 3.13+**
- **⚡ FastAPI**: API assíncrona de alta performance
- **🧠 OpenAI**: GPT-4o-mini para processamento de linguagem natural
- **🗄️ AWS DynamoDB**: Banco de dados NoSQL para estado
- **📝 Pydantic**: Validação e serialização de dados
- **📊 Structlog**: Logging estruturado e contextual

---

**Sistema totalmente baseado em LLM, sem keywords, com estado otimizado e respostas dinâmicas.** 🎯