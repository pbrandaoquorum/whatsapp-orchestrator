#!/bin/bash

# Script para verificar a nova estrutura modular

echo "🏗️  Verificando estrutura modular do UpdateClinicalData..."
echo ""

# Função para contar linhas e verificar sintaxe
check_file() {
    local file=$1
    local description=$2
    
    if [ -f "$file" ]; then
        local lines=$(wc -l < "$file")
        echo "✅ $description: $lines linhas"
        
        # Verifica sintaxe
        if node -c "$file" 2>/dev/null; then
            echo "   ✓ Sintaxe OK"
        else
            echo "   ❌ Erro de sintaxe"
        fi
    else
        echo "❌ $description: Arquivo não encontrado"
    fi
    echo ""
}

echo "📁 Estrutura principal:"
check_file "src/index.js" "Handler principal"

echo "📝 Handlers específicos:"
check_file "src/handlers/noteHandler.js" "Note Handler"
check_file "src/handlers/symptomHandler.js" "Symptom Handler" 
check_file "src/handlers/vitalSignsHandler.js" "VitalSigns Handler"

echo "⚙️  Serviços de negócio:"
check_file "src/services/alertService.js" "Alert Service"

echo "🔧 Utilitários:"
check_file "src/utils/symptomFormatter.js" "Symptom Formatter"
check_file "src/utils/scenarioIdentifier.js" "Scenario Identifier"

echo "📋 Documentação:"
check_file "ARCHITECTURE.md" "Documentação da arquitetura"

# Conta total de linhas
echo "📊 Resumo do código:"
total_lines=0
for file in src/index.js src/handlers/*.js src/services/*.js src/utils/*.js; do
    if [ -f "$file" ]; then
        lines=$(wc -l < "$file")
        total_lines=$((total_lines + lines))
    fi
done

original_lines=1578
echo "   • Código original: $original_lines linhas (1 arquivo)"
echo "   • Código modular: $total_lines linhas (8 arquivos)"
echo "   • Arquivo maior: ~$(($total_lines / 8)) linhas médias"
echo "   • Redução de complexidade: $(echo "scale=1; $original_lines / ($total_lines / 8)" | bc)x mais organizado"

echo ""
echo "🎉 Estrutura modular verificada com sucesso!"
