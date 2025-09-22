#!/bin/bash

# Script de deploy para o updateClinicalData Lambda
# Usa AWS SAM para build e deploy

set -e

echo "🚀 Iniciando deploy do updateClinicalData Lambda..."

# Verifica se AWS CLI está configurado
if ! aws sts get-caller-identity > /dev/null 2>&1; then
    echo "❌ AWS CLI não está configurado. Execute 'aws configure' primeiro."
    exit 1
fi

# Verifica se SAM CLI está instalado
if ! command -v sam &> /dev/null; then
    echo "❌ SAM CLI não está instalado. Instale com:"
    echo "   pip install aws-sam-cli"
    echo "   ou siga: https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html"
    exit 1
fi

echo "✅ Pré-requisitos verificados"

# Build do projeto
echo "🔨 Building projeto SAM..."
sam build

if [ $? -eq 0 ]; then
    echo "✅ Build concluído com sucesso"
else
    echo "❌ Erro no build"
    exit 1
fi

# Deploy
echo "🚀 Fazendo deploy..."

if [ "$1" == "--guided" ]; then
    echo "📋 Deploy interativo (primeira vez)..."
    sam deploy --guided
else
    echo "📋 Deploy automático..."
    sam deploy
fi

if [ $? -eq 0 ]; then
    echo "✅ Deploy concluído com sucesso!"
    echo ""
    echo "📊 Para verificar os recursos criados:"
    echo "   aws cloudformation describe-stacks --stack-name updateClinicalData"
    echo ""
    echo "📋 Para ver os logs:"
    echo "   sam logs -n UpdateClinicalDataFunction --tail"
    echo ""
    echo "🧪 Para testar o endpoint:"
    echo "   curl -X POST [API_ENDPOINT]/updateClinicalData -H 'Content-Type: application/json' -d '{...}'"
else
    echo "❌ Erro no deploy"
    exit 1
fi
