# UpdateClinicalData - Regras de Negócio

## Visão Geral

O Lambda `updateClinicalData` é um sistema consolidado que processa dados clínicos de pacientes, incluindo sinais vitais, notas clínicas e relatórios de sintomas. O sistema é flexível e suporta múltiplos cenários de entrada de dados.

## Cenários Suportados

### 1. VITAL_SIGNS_NOTE_SYMPTOMS
**Entrada**: Sinais Vitais + Nota Clínica + Relatório de Sintomas
- Processa sinais vitais com alertas automáticos
- Salva nota clínica no NoteReport
- Processa sintomas com pontuação das regras
- **Exemplo de uso**: Aferição completa de cuidador com observações

### 2. VITAL_SIGNS_SYMPTOMS (NOVO)
**Entrada**: Sinais Vitais + Relatório de Sintomas (SEM nota clínica)
- Processa sinais vitais com alertas automáticos
- Processa sintomas com pontuação das regras
- Pula processamento de NoteReport
- **Exemplo de uso**: Aferição de sinais vitais com sintomas observados, mas sem nota descritiva

### 3. VITAL_SIGNS_NOTE
**Entrada**: Sinais Vitais + Nota Clínica
- Processa sinais vitais com alertas automáticos
- Salva nota clínica no NoteReport
- **Exemplo de uso**: Aferição com observações do cuidador

### 4. VITAL_SIGNS_ONLY (NOVO)
**Entrada**: Sinais Vitais apenas
- Processa sinais vitais com alertas automáticos
- **Exemplo de uso**: Aferição simples de sinais vitais

### 5. NOTE_SYMPTOMS
**Entrada**: Nota Clínica + Relatório de Sintomas
- Salva nota clínica no NoteReport
- Processa sintomas com alertas baseados em regras
- **Exemplo de uso**: Relatório de sintomas com observações detalhadas

### 6. SYMPTOMS_ONLY (NOVO)
**Entrada**: Relatório de Sintomas apenas
- Processa sintomas com alertas baseados em regras
- **Exemplo de uso**: Relatório de sintomas observados sem nota adicional

### 7. NOTE_ONLY
**Entrada**: Nota Clínica apenas
- Salva nota clínica no NoteReport
- **Exemplo de uso**: Observações do cuidador sem dados quantitativos

## Regras de Alertas

### Alertas por Sinais Vitais Críticos (Score = 5)

#### Frequência Cardíaca (FC)
- **Crítico**: FC fora dos limites normais (muito alta ou muito baixa)
- **Alerta**: "FC crítica: {valor} bpm"
- **Categoria**: Sinais Vitais → Frequência Cardíaca

#### Frequência Respiratória (FR)
- **Crítico**: FR = 5 pontos E média histórica ≤ 40 rpm
- **Alerta**: "FR crítica: {valor} rpm"
- **Categoria**: Sinais Vitais → Frequência Respiratória

#### Saturação de Oxigênio (SatO2)
- **Crítico**: SatO2 = 5 pontos E média histórica ≥ 88%
- **Alerta**: "SatO2 crítica: {valor}%"
- **Categoria**: Sinais Vitais → Saturação de Oxigênio

#### Pressão Arterial Sistólica (PAS)
- **Crítico**: PAS = 5 pontos E média histórica ≥ 80 mmHg
- **Alerta**: "PAS crítica: {valor} mmHg"
- **Categoria**: Sinais Vitais → Pressão Arterial

### Alertas por Temperatura
- **Condição**: Temperatura ≥ 37.8°C
- **Alerta**: "Temperatura elevada: {valor}°C"
- **Categoria**: Temperatura → Febre

### Alertas por Z-Score (Variações Extremas)

#### Frequência Cardíaca
- **Condição**: |z-score| ≥ 3 E score ≥ 1
- **Alerta**: "FC com alta variação: {valor} bpm"
- **Categoria**: Sinais Vitais → Variação FC

#### Frequência Respiratória
- **Condição**: z-score ≥ 3 E score_FR ≥ 2 E score_FC ≥ 1
- **Alerta**: "FR com alta variação: {valor} rpm"
- **Categoria**: Sinais Vitais → Variação FR

#### Saturação de Oxigênio
- **Condição**: z-score < 0 E |z-score| ≥ 3 E score ≥ 2
- **Alerta**: "SatO2 com alta variação: {valor}%"
- **Categoria**: Sinais Vitais → Variação SatO2

#### Pressão Arterial
- **Condição**: z-score < 0 E |z-score| ≥ 3 E score ≥ 2
- **Alerta**: "PAS com alta variação: {valor} mmHg"
- **Categoria**: Sinais Vitais → Variação PAS

### Alertas por Mudança de Risco
- **Condição**: Risco anterior ≠ 'Crítico' E risco atual = 'Crítico'
- **Alerta**: "Mudança de risco: {anterior} para {atual}"
- **Categoria**: Risco → Mudança de Status

### Alertas de Fallback por Risco Alto/Crítico
- **Condição**: Risco = 'Alto' ou 'Crítico' E nenhum alerta anterior
- **Alerta**: "Risco global classificado como {risco}"
- **Categoria**: Risco → Classificação

## Sistema de Pontuação de Sintomas

### Pontuação por Regras Customizadas
- **Fonte**: Campo `regras` no payload
- **Formato**: `[{sintoma: "Nome", pontuacao: N, freq: "Sim/Não"}]`
- **Aplicação**: Cada sintoma recebe pontuação conforme regra definida

### Pontuação por Sinais Vitais Gerados
- **Temperatura elevada**: 5 pontos
- **Sinais vitais críticos**: 5 pontos
- **Variações z-score**: Score original do sinal vital
- **Mudança de risco**: Baseado no nível de risco
  - Crítico: 5 pontos
  - Alto: 4 pontos
  - Moderado: 3 pontos
  - Baixo: 2 pontos

### Critérios para Geração de Alertas por Sintomas

#### Com Histórico (≥7 aferições anteriores)
- **Score individual baixo (≤2) E risco baixo**: Não gera alerta
- **Score individual alto (≥3) OU risco moderado/alto/crítico**: Gera alerta

#### Sem Histórico (<7 aferições)
- **Score individual baixo E sem histórico**: Não gera alerta
- **Score total dos sintomas ≥ threshold**: Pode gerar alerta

## Cálculo de Risco

### Score Relativo (com histórico ≥7 aferições)
- **≥10**: Crítico
- **≥7**: Alto  
- **≥5**: Moderado
- **<5**: Baixo

### Sem Histórico
- **Risco**: "Sem 7 aferições anteriores completas ainda"

## Recuperação Automática de IDs (NOVO - v2.0)

### caregiverID
1. **Primeira tentativa**: Campo `caregiverIdentifier` no payload
2. **Segunda tentativa**: Busca na tabela `Reports` usando `reportID` + `reportDate`
3. **Terceira tentativa**: Busca na tabela `WorkSchedules` usando `scheduleID`
4. **Fallback**: Se não encontrado, operações que requerem índice são puladas

### patientID
1. **Primeira tentativa**: Campo `patientIdentifier` no payload
2. **Segunda tentativa**: Busca na tabela `Reports` usando `reportID` + `reportDate`
3. **Terceira tentativa**: Busca na tabela `WorkSchedules` usando `scheduleID`
4. **Fallback**: Se não encontrado, operações que requerem índice são puladas

## Validações de Índices DynamoDB (NOVO - v2.0)

### Índices Obrigatórios
- **caregiverID-index**: Requer `caregiverID` não vazio
- **patientID-index**: Requer `patientID` não vazio

### Comportamento de Proteção
- **Alertas**: Não são salvos se `caregiverID` ou `patientID` estiverem vazios
- **VitalSigns**: Salvamento é pulado se IDs estiverem vazios
- **Logs**: Indicam claramente quando operações são puladas e porquê

## Processamento de Nota Clínica (NOVO - v2.0)

### Campo clinicalNote Opcional
- **Presente e não vazio**: Processa normalmente no NoteReport
- **Ausente ou vazio**: Pula processamento do NoteReport
- **Outros campos**: `altnotepadMain` e `adminInfo` ainda são processados independentemente

### Fluxo da Família
- **Requer**: `phoneNumber` + `clinicalNote` não vazio
- **Sem clinicalNote**: Retorna `{saved: false, reason: 'No clinical note for family flow'}`

## Tabelas Afetadas

### Principais
- **VitalSigns**: Dados de sinais vitais e scores
- **VitalSignsTest**: Réplica para testes
- **Reports**: NoteReport, SymptomReport, AlterationsReport
- **SymptomReports**: Histórico detalhado de sintomas
- **Alerts**: Alertas gerados pelo sistema
- **Patients**: Atualização de scores atuais

### Auxiliares
- **WorkSchedules**: Incremento de contadores, busca de IDs
- **FamilyReports**: Relatórios do fluxo familiar

## Logs e Debugging

### Logs Detalhados (NOVO - v2.0)
- **Recuperação de IDs**: Mostra onde cada ID foi encontrado
- **Validações**: Indica quando operações são puladas
- **Processamento**: Detalha cada etapa do processamento
- **Erros**: Stack traces completos para debugging

### Formato de Resposta
```json
{
  "message": "Dados clínicos processados com sucesso - Processados: Sinais Vitais, 2 sintomas",
  "scenario": "VITAL_SIGNS_SYMPTOMS",
  "results": {
    "vitalSigns": {...},
    "symptomReport": {...}
  },
  "timestamp": "2025-01-01T12:00:00-03:00"
}
```

## Compatibilidade

### Versão Anterior (v1.x)
- **clinicalNote obrigatório**: Gerava erro se ausente
- **IDs obrigatórios**: Gerava erro de índice se vazios
- **Cenários limitados**: Apenas 4 cenários suportados

### Versão Atual (v2.0)
- **clinicalNote opcional**: Não gera erro, apenas pula processamento
- **IDs recuperados automaticamente**: Busca em múltiplas fontes
- **7 cenários suportados**: Maior flexibilidade de entrada
- **Validações protetivas**: Evita erros de índice DynamoDB

## Resumo das Mudanças v2.0

1. **✅ clinicalNote opcional**: Sistema funciona com ou sem nota clínica
2. **✅ Recuperação automática de IDs**: caregiverID e patientID buscados em Reports/WorkSchedules
3. **✅ Validações de índices**: Proteção contra erros de string vazia em índices DynamoDB
4. **✅ Novos cenários**: VITAL_SIGNS_SYMPTOMS, VITAL_SIGNS_ONLY, SYMPTOMS_ONLY
5. **✅ Logs aprimorados**: Debugging detalhado para troubleshooting
6. **✅ Maior flexibilidade**: Sistema aceita dados parciais sem gerar erro
