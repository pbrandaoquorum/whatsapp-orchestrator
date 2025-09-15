# 🧠 Funcionamento Detalhado - WhatsApp Orchestrator

## 🎯 **RESPOSTA ÀS SUAS DÚVIDAS CRÍTICAS**

### ❓ **DÚVIDA 1: Como retornar mensagem quando clinical precisa de confirmação?**

**RESPOSTA**: TODOS os fluxos podem **terminar** (enviar resposta) OU **continuar** (voltar ao router). A decisão é feita pela função `decide_continuacao()`.

#### **Exemplo: Clinical Flow com Confirmação**
```python
# clinical_flow.py - Cenário onde precisa de confirmação
async def clinical_flow(estado: GraphState) -> GraphState:
    # ... processamento ...
    
    if todos_sinais_coletados and not tem_confirmacao:
        # PREPARAR CONFIRMAÇÃO (Two-Phase Commit)
        estado.aux.acao_pendente = criar_acao_pendente(...)
        estado.aux.ultima_pergunta = "Confirma salvar sinais vitais? (sim/não)"
        estado.resposta_usuario = estado.aux.ultima_pergunta
        
        # MARCAR PARA TERMINAR (aguardar resposta do usuário)
        estado.terminar_fluxo = True  # ← AQUI!
        return estado
    
    elif confirmacao_recebida:
        # EXECUTAR LAMBDA
        await atualizar_dados_clinicos(estado)
        estado.resposta_usuario = "✅ Sinais vitais salvos!"
        
        # MARCAR PARA TERMINAR (ação completa)
        estado.terminar_fluxo = True  # ← AQUI!
        return estado
    
    else:
        # CONTINUAR COLETANDO
        estado.resposta_usuario = "Ainda faltam: FC, FR..."
        
        # MARCAR PARA TERMINAR (aguardar mais dados)
        estado.terminar_fluxo = True  # ← AQUI!
        return estado
```

### ❓ **DÚVIDA 2: Como funciona quando webhook dispara template?**

**RESPOSTA**: Templates **atualizam o estado** via `POST /events/template-sent` para preparar a próxima interação.

#### **Fluxo Completo:**
```
1. Sistema → Seu Webhook → "Precisa informar sinais vitais"
2. Seu Webhook → POST /events/template-sent → Atualiza estado interno
3. Usuário → "PA 120x80" → Seu Webhook → POST /webhook/whatsapp
4. Sistema → Já sabe que está coletando SV → Processa corretamente
```

#### **Implementação:**
```python
# routes.py - Template enviado
@router.post("/events/template-sent")
async def template_enviado(template_data: TemplateSent):
    # Carregar estado da sessão
    estado = carregar_estado_redis(template_data.phoneNumber)
    
    if template_data.template == "pedir_sinais_vitais":
        # Preparar para coleta de SV
        estado.aux.ultima_pergunta = "Aguardando sinais vitais..."
        estado.aux.fluxo_que_perguntou = "clinical"
        estado.metadados["aguardando_sinais_vitais"] = True
    
    elif template_data.template == "confirmar_presenca":
        # Preparar para confirmação
        estado.aux.ultima_pergunta = "Aguardando confirmação de presença..."
        estado.aux.fluxo_que_perguntou = "escala"
    
    # Salvar estado atualizado
    salvar_estado_redis(estado)
```

### ❓ **DÚVIDA 3: Como puxamos/atualizamos estados a cada execução?**

**RESPOSTA**: **Redis Checkpointing** automático do LangGraph + cache manual para templates.

#### **Puxar Estado (Automático):**
```python
# routes.py - Cada chamada do webhook
config = {"configurable": {"thread_id": session_id}}
resultado = grafo.invoke(estado_inicial, config=config)
#                                      ↑
#                    LangGraph automaticamente:
#                    1. Puxa estado do Redis
#                    2. Mescla com estado_inicial
#                    3. Executa grafo
#                    4. Salva estado no Redis
```

#### **Atualizar Estado (Manual para Templates):**
```python
# Função auxiliar para templates
async def carregar_estado_redis(phone_number: str) -> GraphState:
    redis_client = obter_cliente_redis()
    session_id = f"session_{phone_number.replace('+', '')}"
    
    # Buscar checkpoint
    key = f"checkpoint:{session_id}"
    data = await redis_client.get(key)
    
    if data:
        checkpoint = pickle.loads(data)
        return GraphState(**checkpoint["checkpoint"])
    else:
        # Estado inicial se não existe
        return GraphState(core=CoreState(
            session_id=session_id,
            numero_telefone=phone_number
        ))

async def salvar_estado_redis(estado: GraphState):
    redis_client = obter_cliente_redis()
    key = f"checkpoint:{estado.core.session_id}"
    
    data = {
        "checkpoint": estado.dict(),
        "metadata": "",
        "timestamp": time.time()
    }
    
    await redis_client.setex(key, 3600, pickle.dumps(data))
```

### ❓ **DÚVIDA 4: Como funciona integração Pinecone → updateClinicalData?**

**RESPOSTA**: **RAG no notas_flow** → busca sintomas → monta SymptomReport → inclui no payload do Lambda.

#### **Fluxo Completo:**
```python
# notas_flow.py
async def notas_flow(estado: GraphState) -> GraphState:
    # 1. CLASSIFICAÇÃO SEMÂNTICA
    resultado = await classify_semantic(estado.texto_usuario, estado)
    
    if resultado.intent == IntentType.NOTA_CLINICA:
        nota_clinica = resultado.clinical_note or estado.texto_usuario
        
        # 2. RAG PINECONE - Buscar sintomas similares
        sintomas_identificados = buscar_sintomas_similares(nota_clinica)
        
        # 3. FORMATO SYMPTOM REPORT
        estado.nota.texto_bruto = nota_clinica
        estado.nota.sintomas_rag = sintomas_identificados
        
        # 4. PREPARAR TWO-PHASE COMMIT
        payload = {
            "reportID": estado.core.report_id,
            "scenario": "NOTE_SYMPTOMS",  # ← Cenário específico
            "clinicalNote": nota_clinica,
            "symptoms": sintomas_identificados  # ← SymptomReport[]
        }
        
        estado.aux.acao_pendente = criar_acao_pendente(
            fluxo_destino="clinical_commit",
            payload=payload
        )
        
        # 5. PERGUNTA DE CONFIRMAÇÃO
        resumo_sintomas = gerar_resumo_sintomas(sintomas_identificados)
        estado.aux.ultima_pergunta = f"""
📝 *Nota Clínica Registrada*

**Observação:** {nota_clinica[:100]}...

**Sintomas Identificados:**
{resumo_sintomas}

**Confirma salvar?** (sim/não)
""".strip()
        
        estado.resposta_usuario = estado.aux.ultima_pergunta
        estado.terminar_fluxo = True  # ← Aguardar confirmação
        
        return estado
```

#### **SymptomReport Format:**
```python
# Formato exato que vai para updateClinicalData
symptom_report = {
    "symptomDefinition": "cefaleia",
    "altNotepadMain": "dor de cabeça",
    "symptomCategory": "Neurológico",
    "symptomSubCategory": "Dor",
    "descricaoComparada": "dor de cabeça intensa",
    "coeficienteSimilaridade": 0.87
}
```

## 🗂️ **EXPLICAÇÃO DE CADA ARQUIVO**

### **📁 app/api/**
- **`main.py`**: Aplicação FastAPI principal, middlewares, lifespan
- **`routes.py`**: Endpoints (webhook, templates, debug, rag, health)
- **`schemas.py`**: Modelos Pydantic para requests/responses
- **`middleware.py`**: Dedupe, logging, request ID

### **📁 app/graph/**
- **`state.py`**: Estado canônico do grafo (CoreState, VitalsState, etc.)
- **`router.py`**: Lógica de roteamento determinística + classificação semântica
- **`builder.py`**: Construção do grafo LangGraph (nós, edges, checkpointer)
- **`semantic_classifier.py`**: Classificação LLM + LLM as Judge + fallbacks
- **`clinical_extractor.py`**: Extração determinística de sinais vitais
- **`tools.py`**: Integrações com 4 Lambdas AWS (com circuit breakers)

### **📁 app/graph/flows/**
- **`escala_flow.py`**: Confirmação/cancelamento de presença
- **`clinical_flow.py`**: Coleta sinais vitais + dados clínicos
- **`notas_flow.py`**: Notas clínicas + RAG sintomas
- **`finalizar_flow.py`**: Encerramento do plantão + relatório
- **`auxiliar_flow.py`**: Orientações e mensagens de apoio

### **📁 app/rag/**
- **`pinecone_client.py`**: Cliente Pinecone + busca similaridade
- **`sheets_sync.py`**: Sincronização Google Sheets → Pinecone
- **`embeddings.py`**: Geração de embeddings com SentenceTransformers

### **📁 app/infra/**
- **`redis_client.py`**: Cliente Redis singleton
- **`redis_checkpointer.py`**: Checkpointer LangGraph para Redis
- **`circuit_breaker.py`**: Pattern circuit breaker para robustez
- **`cache.py`**: Cache inteligente (memória + Redis)
- **`logging.py`**: Logs estruturados em português
- **`timeutils.py`**: Utilitários de data/hora Brasil
- **`tpc.py`**: Two-Phase Commit helpers
- **`confirm.py`**: Reconhecimento sim/não em português

### **📁 tests/**
- **`test_semantic_classifier.py`**: Testes do classificador semântico
- **`test_router.py`**: Testes do router determinístico
- **`test_clinical_extractor.py`**: Testes extração sinais vitais
- **`test_flows/`**: Testes dos 5 fluxos principais

### **📄 Arquivos Raiz**
- **`pyproject.toml`**: Dependências e configuração do projeto
- **`env.example`**: Template de variáveis de ambiente
- **`setup.sh`**: Script de instalação automática
- **`test_example.py`**: Exemplos de uso e testes manuais
- **`demo_semantic_classification.py`**: Demo interativa da classificação

## 🤖 **ONDE USAMOS CADA TIPO DE INTELIGÊNCIA**

### **🧠 LLM (GPT-4o-mini) - Classificação Semântica**
**Onde:** `semantic_classifier.py`
**Quando:** Fallback quando regras determinísticas não resolvem
**Entrada:** Texto do usuário + contexto do estado
**Saída:** Intenção classificada + confiança + justificativa

```python
# Exemplo de uso
resultado = await classify_semantic("cheguei no local", estado)
# Output: {
#   "intent": "CONFIRMAR_PRESENCA",
#   "confidence": 0.92,
#   "rationale": "Usuário indica chegada ao local de trabalho"
# }
```

**Casos de Uso:**
- ✅ "cheguei" → CONFIRMAR_PRESENCA
- ✅ "PA 120x80 FC 78" → SINAIS_VITAIS
- ✅ "paciente está bem" → NOTA_CLINICA
- ✅ "quero finalizar" → FINALIZAR_PLANTAO
- ✅ "não entendi" → PEDIR_AJUDA

### **⚖️ LLM as Judge (GPT-4o-mini) - Validação**
**Onde:** `semantic_classifier.py` → `validar_com_judge()`
**Quando:** Confiança da classificação < 0.8
**Entrada:** Texto original + classificação inicial + contexto
**Saída:** Validação + correções se necessário

```python
# Exemplo de uso
if resultado.confidence < 0.8:
    resultado_validado = await validar_com_judge(texto, resultado, estado)
    # Judge pode corrigir classificação incorreta
```

**Casos de Uso:**
- ✅ Classificação ambígua → Judge decide
- ✅ Confiança baixa → Judge valida
- ✅ Contexto complexo → Judge considera histórico

### **🔍 Mapeamento por Keywords - Determinístico**
**Onde:** Múltiplos locais como fallback
**Quando:** LLM falha ou circuit breaker aberto
**Entrada:** Texto simples
**Saída:** Intenção básica

#### **1. Router (`router.py`)**
```python
# Fallback quando LLM falha
if circuit_breaker_aberto:
    if "cheguei" in texto.lower():
        return "escala"
    elif "PA" in texto or "FC" in texto:
        return "clinical"
    # etc...
```

#### **2. Confirmações (`confirm.py`)**
```python
def is_yes(texto: str) -> bool:
    palavras_sim = ["sim", "confirmo", "ok", "certo", "isso", "exato"]
    return any(palavra in texto.lower() for palavra in palavras_sim)

def is_no(texto: str) -> bool:
    palavras_nao = ["não", "nao", "negativo", "cancelar", "errado"]
    return any(palavra in texto.lower() for palavra in palavras_nao)
```

#### **3. Clinical Extractor (`clinical_extractor.py`)**
```python
# Regex para sinais vitais
PA_PATTERN = r"PA\s*:?\s*(\d{2,3})\s*[x/]\s*(\d{2,3})"
FC_PATTERN = r"FC\s*:?\s*(\d{2,3})\s*(?:bpm)?"
# etc...
```

#### **4. Semantic Classifier Fallback**
```python
async def _fallback_classificacao_deterministica(texto: str, estado: GraphState):
    texto_lower = texto.lower()
    
    # Presença
    palavras_presenca = ["cheguei", "chegei", "estou aqui", "presente"]
    if any(p in texto_lower for p in palavras_presenca):
        return ClassificationResult(intent=IntentType.CONFIRMAR_PRESENCA, confidence=0.7)
    
    # Sinais vitais
    if re.search(r"PA\s*\d+", texto) or re.search(r"FC\s*\d+", texto):
        return ClassificationResult(intent=IntentType.SINAIS_VITAIS, confidence=0.7)
    
    # etc...
```

## 🔄 **FLUXO COMPLETO DE EXECUÇÃO**

### **Cenário: Usuário envia "PA 120x80, FC 78"**

#### **1. Entrada (routes.py)**
```python
POST /webhook/whatsapp
{
  "message_id": "msg_001",
  "phoneNumber": "+5511999999999",
  "text": "PA 120x80, FC 78"
}
```

#### **2. Estado Inicial + Checkpointing**
```python
# LangGraph automaticamente carrega estado do Redis
estado_existente = redis.get(f"checkpoint:session_5511999999999")
estado_atual = merge(estado_existente, texto_usuario="PA 120x80, FC 78")
```

#### **3. Router Determinístico**
```python
# router.py - Prioridades
1. Bootstrap? ✅ (já feito)
2. Retomada? ❌ (não há)
3. Pergunta pendente? ❌ (não há)
4. Classificação semântica? ✅ (vai para LLM)
```

#### **4. Classificação Semântica**
```python
# semantic_classifier.py
resultado = await _executar_classificacao_llm("PA 120x80, FC 78", estado)
# GPT-4o-mini retorna:
{
  "intent": "SINAIS_VITAIS",
  "confidence": 0.95,
  "vital_signs": {"PA": "120x80", "FC": 78}
}
```

#### **5. Gates de Negócio**
```python
# router.py - Verificar se pode processar SV
if not presenca_confirmada(estado):
    # Força escala primeiro
    estado.aux.buffers["vitals"] = {"PA": "120x80", "FC": 78}
    return "escala"
else:
    # Pode processar
    return "clinical"
```

#### **6. Clinical Flow**
```python
# clinical_flow.py
estado.vitais.processados.update({"PA": "120x80", "FC": 78})
estado.vitais.faltantes = ["FR", "Sat", "Temp"]  # Ainda faltam

# Como faltam SV, não vai para confirmação ainda
estado.resposta_usuario = "Coletados PA e FC. Ainda faltam: FR, Sat, Temp"
estado.terminar_fluxo = True  # ← Termina aqui, aguarda mais SV
```

#### **7. Decisão de Continuação**
```python
# builder.py - decide_continuacao()
if estado.terminar_fluxo:
    return "END"  # ← Termina, retorna resposta
```

#### **8. Resposta**
```python
# routes.py
return {
  "success": true,
  "message": "Coletados PA e FC. Ainda faltam: FR, Sat, Temp",
  "session_id": "session_5511999999999",
  "next_action": "clinical"
}
```

#### **9. Checkpointing Automático**
```python
# LangGraph salva estado final no Redis automaticamente
redis.set(f"checkpoint:session_5511999999999", estado_final)
```

## 🎯 **CASOS ESPECÍFICOS DE CONTINUAÇÃO vs TERMINAÇÃO**

### **TERMINA (retorna resposta ao usuário):**
- ✅ Two-phase commit pergunta confirmação
- ✅ Coleta incremental (faltam dados)
- ✅ Ação executada com sucesso
- ✅ Erro que precisa de correção do usuário
- ✅ Orientação/ajuda fornecida

### **CONTINUA (volta ao router):**
- ✅ Dados completos, mas precisa executar outro fluxo
- ✅ Retomada automática após pré-requisito atendido
- ✅ Fluxo interno que não gera resposta direta

### **Exemplo: Clinical → Notas (Continuação)**
```python
# clinical_flow.py - Todos SV coletados E tem nota clínica
if sinais_completos and tem_nota_clinica:
    # Salvar SV primeiro
    await atualizar_dados_clinicos(estado, cenario="VITAL_SIGNS_ONLY")
    
    # Preparar para processar nota
    estado.aux.retomar_apos = {"flow": "notas", "reason": "process_note"}
    estado.continuar_fluxo = True  # ← Continua no router
    
    return estado  # Não termina, vai para router → notas
```

Esta arquitetura garante **flexibilidade total** - cada fluxo decide se termina ou continua baseado na lógica de negócio específica! 🚀
