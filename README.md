# WhatsApp Orchestrator 🤖

Sistema inteligente de orquestração para WhatsApp com processamento de dados clínicos, gerenciamento de escalas, notas operacionais e finalização automática de plantões.

## 🚀 Funcionalidades Principais

- **🏥 Gestão de Plantões**: Confirmação de presença e controle de escalas
- **📊 Dados Clínicos**: Coleta inteligente de sinais vitais, notas e condições respiratórias via LLM
- **⚡ Notas Operacionais**: Processamento instantâneo de observações administrativas
- **📋 Finalização Automática**: Coleta de 8 tópicos de finalização com envio para relatórios
- **🧠 IA Contextual**: Respostas dinâmicas baseadas no estado completo da conversa
- **🔄 Integração Completa**: Webhooks n8n, Lambdas AWS e DynamoDB

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

## 🎯 Regras de Negócio e Fluxos

### 🚦 Sistema de Gates Determinísticos

O sistema utiliza um **roteamento inteligente** com gates de prioridade para determinar qual subgrafo deve processar cada mensagem:

#### **📋 Ordem de Prioridade dos Gates:**

1. **🔴 GATE DE FINALIZAÇÃO (Prioridade Máxima)**
   - **Condição**: `finishReminderSent = true` no estado da sessão
   - **Ação**: Força direcionamento para subgrafo `finalizar`
   - **Características**: Sobrepõe qualquer classificação LLM
   - **Objetivo**: Garantir que plantões prontos para finalização sejam processados

2. **🟡 GATE DE CONFIRMAÇÃO PENDENTE**
   - **Condição**: Existe confirmação pendente no estado (`state.pendente`)
   - **Ação**: Direciona para o subgrafo que iniciou a confirmação
   - **Características**: Mantém contexto de confirmações em andamento
   - **Objetivo**: Preservar fluxo de confirmações (presença, dados clínicos, finalização)

3. **🟠 GATE DE NOTAS OPERACIONAIS**
   - **Condição**: LLM `OperationalNoteClassifier` detecta nota operacional
   - **Ação**: Direciona para subgrafo `operacional`
   - **Características**: Processamento instantâneo sem confirmação
   - **Exemplos**: "acabou a fralda", "médico visitou", "familiar ligou"

4. **🟢 GATE DE PLANTÃO NÃO CONFIRMADO**
   - **Condição**: `shift_allow = true` MAS `response != "confirmado"`
   - **Ação**: Força direcionamento para subgrafo `escala`
   - **Características**: Impede coleta de dados sem confirmação de presença
   - **Objetivo**: Garantir confirmação antes de qualquer update

5. **🔵 CLASSIFICAÇÃO LLM (Padrão)**
   - **Condição**: Nenhum gate anterior ativado
   - **Ação**: Usa `IntentClassifier` para determinar intenção
   - **Opções**: `escala`, `clinico`, `operacional`, `finalizar`, `auxiliar`

### 🏥 Fluxos de Negócio Detalhados

#### **📊 Fluxo Clínico**

**🔴 PRIMEIRA AFERIÇÃO (Obrigatória Completa)**
```
1. Validação → Sistema verifica se já houve aferição completa no plantão
2. Rejeição → Se usuário envia apenas nota, sistema rejeita e pede aferição completa
3. Coleta Obrigatória:
   - ✅ TODOS os sinais vitais (PA, FC, FR, Sat, Temp)
   - ✅ Condição respiratória (Ar ambiente/O2 suplementar/Ventilação mecânica)
   - ✅ Nota clínica (observações obrigatórias na primeira aferição)
4. Validação → Faixas aceitáveis e formato correto
5. Confirmação → Apresenta resumo completo e pede confirmação
6. Envio → Webhook n8n → Lambda updateClinicalData
7. Flag → Marca afericao_completa_realizada=true
8. Limpeza → Estado clínico resetado (preserva flag)
```

**🟢 AFERIÇÕES SUBSEQUENTES (Flexíveis)**
```
OPÇÃO 1: Aferição Completa (com ou sem nota)
- ✅ TODOS os sinais vitais (PA, FC, FR, Sat, Temp)
- ✅ Condição respiratória
- ⚪ Nota clínica (OPCIONAL - se não houver, usa "sem alterações")

OPÇÃO 2: Nota Clínica Isolada
- 📝 Apenas nota clínica (sem vitais)
- ⚡ Processamento direto via webhook n8n
- ✅ Sem necessidade de confirmação complexa
```

#### **⚡ Fluxo Operacional (Instantâneo)**
```
1. Detecção LLM → Classifica como nota operacional
2. Processamento → Sem necessidade de confirmação
3. Envio → Webhook n8n imediato
4. Resposta → Confirmação de recebimento
```

#### **📋 Fluxo de Finalização**

**⚠️ REGRA CRÍTICA: Só Ativa se finishReminderSent=true**
```
🚨 Sistema NUNCA menciona "finalização" ou "encerramento" se finishReminderSent=false
🚨 Fiscal IGNORA completamente dados de finalização quando flag está desabilitada
```

**🔄 Processo de Finalização:**
```
1. Trigger → finishReminderSent=true no backend (getScheduleStarted)
2. Gate Prioritário → Router redireciona automaticamente para subgrafo finalizar
3. Recuperação → Notas existentes via getNoteReport
4. Coleta LLM → 8 tópicos de finalização:
   - Alimentação e Hidratação
   - Evacuações (Fezes e Urina)  
   - Sono
   - Humor
   - Medicações
   - Atividades (físicas e cognitivas)
   - Informações clínicas adicionais
   - Informações administrativas
5. Envio Parcial → Cada tópico vai para webhook n8n
6. Confirmação → Resumo completo quando todos preenchidos
7. Finalização → updatereportsummaryad + limpeza completa do estado
```

#### **🏥 Fluxo de Escala**
```
1. Verificação → getScheduleStarted para dados da sessão
2. Validação → Plantão existe e está permitido
3. Confirmação → Usuário confirma presença
4. Update → updateWorkScheduleResponse marca como confirmado
5. Liberação → Permite coleta de dados clínicos
```

### 🧠 Sistema de IA Contextual

#### **🎯 Fiscal Processor (Orquestrador Central)**
- **Função**: Gera todas as respostas ao usuário via LLM
- **Entrada**: Estado canônico completo do DynamoDB + código do subgrafo
- **Características**:
  - Sem respostas estáticas
  - Contexto completo da conversa
  - Adaptação dinâmica baseada no estado
  - Códigos específicos para cada situação

#### **🔍 Classificadores LLM**
- **`IntentClassifier`**: Determina intenção geral (escala/clinico/operacional/finalizar/auxiliar)
- **`OperationalNoteClassifier`**: Detecta notas operacionais instantâneas
- **`ConfirmationClassifier`**: Interpreta confirmações (sim/não/cancelar)

#### **📊 Extratores LLM**
- **`ClinicalExtractor`**: Extrai sinais vitais, notas e condições respiratórias
- **`FinalizacaoExtractor`**: Extrai tópicos de finalização de forma estruturada

### 🔄 Integrações Externas

#### **🌐 Webhooks n8n**
- **Uso**: Processamento de dados clínicos, operacionais e de finalização
- **Formato**: Compatível com lambda updateClinicalData
- **Campos**: `clinicalNote`, `reportID`, `reportDate`, etc.

#### **⚡ Lambdas AWS**
- **`getScheduleStarted`**: Dados da sessão e flags de controle
- **`updateWorkScheduleResponse`**: Confirmação de presença
- **`getNoteReport`**: Recuperação de notas existentes
- **`updatereportsummaryad`**: Finalização de relatórios

#### **🗄️ DynamoDB**
- **Tabela**: `ConversationStates`
- **Formato**: JSON estruturado com estado completo
- **Persistência**: Contexto preservado entre mensagens
- **Limpeza**: Estado zerado após finalização completa

## 📊 Diagrama Visual Completo

Para uma visualização completa de todos os fluxos, gates e integrações, consulte: **[DIAGRAMA_FLUXO.md](./DIAGRAMA_FLUXO.md)**

O diagrama inclui:
- 🌊 Fluxo principal com gates de prioridade
- 📊 Detalhamento de cada subgrafo (clínico, finalização, operacional)
- 🎯 Sistema de prioridades dos gates
- 🧠 Arquitetura de IA com classificadores e extratores
- 🔄 Integrações externas (n8n, Lambdas, DynamoDB)

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
- **`env.example`** - Exemplo de variáveis de ambiente necessárias
- **`README.md`** - Este arquivo, documentação principal do projeto

## 🚀 Como Executar

### 📋 Pré-requisitos
- Python 3.11+
- Conta AWS com DynamoDB configurado
- Chaves de API OpenAI
- Webhooks n8n configurados

### ⚙️ Configuração
1. **Clone o repositório**:
   ```bash
   git clone <repo-url>
   cd whatsapp-orchestrator
   ```

2. **Crie ambiente virtual**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   # ou
   venv\Scripts\activate     # Windows
   ```

3. **Instale dependências**:
   ```bash
   pip install -e .
   ```

4. **Configure variáveis de ambiente**:
   ```bash
   cp env.example .env
   # Edite .env com suas credenciais
   ```

5. **Execute a aplicação**:
   ```bash
   python -m uvicorn app.api.main:app --reload --host 0.0.0.0 --port 8000
   ```

### 🧪 Teste via curl
```bash
curl -X POST "http://127.0.0.1:8000/webhook/whatsapp" \
  -H "Content-Type: application/json" \
  -d '{
    "message_id": "test_001",
    "phoneNumber": "5511999999999",
    "text": "confirmo presença",
    "meta": {"source": "test"}
  }'
```

### 🔧 Variáveis de Ambiente Principais
```env
# OpenAI
OPENAI_API_KEY=sk-...
EXTRACTOR_MODEL=gpt-4o-mini

# AWS
AWS_REGION=sa-east-1
DYNAMODB_TABLE_CONVERSAS=ConversationStates

# Lambdas
LAMBDA_GET_SCHEDULE_STARTED=https://...
LAMBDA_UPDATE_WORK_SCHEDULE=https://...
LAMBDA_GET_NOTE_REPORT=https://...
LAMBDA_UPDATE_SUMMARY=https://...

# Webhooks
N8N_WEBHOOK_URL_PROD=https://...
```

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