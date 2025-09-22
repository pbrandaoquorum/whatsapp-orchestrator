#!/bin/bash

# Script para testar o updateClinicalData Lambda localmente
# Requer SAM CLI instalado

set -e

echo "🧪 Testando updateClinicalData Lambda localmente..."

# Verifica se SAM CLI está instalado
if ! command -v sam &> /dev/null; then
    echo "❌ SAM CLI não está instalado."
    exit 1
fi

# Função para testar um cenário específico
test_scenario() {
    local scenario_name=$1
    local test_file="examples/test-scenarios.json"
    
    if [ ! -f "$test_file" ]; then
        echo "❌ Arquivo de teste não encontrado: $test_file"
        return 1
    fi
    
    echo "🎯 Testando cenário: $scenario_name"
    
    # Extrai o payload do cenário
    local payload=$(jq -r ".scenarios.${scenario_name}.payload" "$test_file")
    
    if [ "$payload" == "null" ]; then
        echo "❌ Cenário '$scenario_name' não encontrado"
        return 1
    fi
    
    # Cria arquivo temporário para o evento
    local event_file="/tmp/test-event-${scenario_name}.json"
    echo "{\"body\": $(echo "$payload" | jq -c .)}" > "$event_file"
    
    echo "📤 Enviando evento..."
    
    # Invoca a função localmente
    sam local invoke UpdateClinicalDataFunction --event "$event_file"
    
    # Remove arquivo temporário
    rm "$event_file"
    
    echo "✅ Teste do cenário '$scenario_name' concluído"
    echo ""
}

# Menu de opções
if [ $# -eq 0 ]; then
    echo "📋 Cenários disponíveis:"
    echo "  1. vital_signs_note_symptoms - Sinais Vitais + NoteReport + SymptomReport"
    echo "  2. vital_signs_note - Sinais Vitais + NoteReport"
    echo "  3. note_symptoms - NoteReport + SymptomReport"
    echo "  4. note_only - NoteReport apenas"
    echo "  5. family_report - Fluxo da Família"
    echo "  6. high_score_symptoms - Sintomas com score alto (alerta)"
    echo "  7. vital_signs_with_alerts - Sinais vitais críticos + sintomas + alertas"
    echo "  all - Executar todos os testes"
    echo ""
    echo "Uso: $0 [cenario]"
    echo "Exemplo: $0 note_only"
    exit 0
fi

# Build primeiro
echo "🔨 Building projeto..."
sam build

if [ $? -ne 0 ]; then
    echo "❌ Erro no build"
    exit 1
fi

# Executa testes baseado no parâmetro
case $1 in
    "vital_signs_note_symptoms")
        test_scenario "vital_signs_note_symptoms"
        ;;
    "vital_signs_note")
        test_scenario "vital_signs_note"
        ;;
    "note_symptoms")
        test_scenario "note_symptoms"
        ;;
    "note_only")
        test_scenario "note_only"
        ;;
    "family_report")
        test_scenario "family_report"
        ;;
    "high_score_symptoms")
        test_scenario "high_score_symptoms"
        ;;
    "vital_signs_with_alerts")
        test_scenario "vital_signs_with_alerts"
        ;;
    "all")
        echo "🎯 Executando todos os cenários de teste..."
        test_scenario "note_only"
        test_scenario "note_symptoms"
        test_scenario "vital_signs_note"
        test_scenario "vital_signs_note_symptoms"
        test_scenario "family_report"
        test_scenario "high_score_symptoms"
        test_scenario "vital_signs_with_alerts"
        echo "✅ Todos os testes concluídos!"
        ;;
    *)
        echo "❌ Cenário desconhecido: $1"
        echo "Execute '$0' sem parâmetros para ver os cenários disponíveis"
        exit 1
        ;;
esac
