#!/bin/bash

# Script de setup para WhatsApp Orchestrator
set -e

echo "🚀 Configurando WhatsApp Orchestrator..."

# Verificar Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 não encontrado. Instale Python 3.11+"
    exit 1
fi

# Verificar versão do Python
PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
REQUIRED_VERSION="3.11"

if [ "$(printf '%s\n' "$REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]; then
    echo "❌ Python $REQUIRED_VERSION+ necessário. Versão atual: $PYTHON_VERSION"
    exit 1
fi

echo "✅ Python $PYTHON_VERSION detectado"

# Criar ambiente virtual se não existir
if [ ! -d "venv" ]; then
    echo "📦 Criando ambiente virtual..."
    python3 -m venv venv
fi

# Ativar ambiente virtual
echo "🔧 Ativando ambiente virtual..."
source venv/bin/activate

# Atualizar pip
echo "⬆️ Atualizando pip..."
pip install --upgrade pip

# Instalar dependências
echo "📚 Instalando dependências..."
pip install -e .

# Copiar arquivo de configuração se não existir
if [ ! -f ".env" ]; then
    echo "⚙️ Copiando arquivo de configuração..."
    cp env.example .env
    echo "📝 Configure as variáveis em .env antes de executar"
fi

# Verificar Redis (opcional)
if command -v redis-cli &> /dev/null; then
    if redis-cli ping &> /dev/null; then
        echo "✅ Redis conectado"
    else
        echo "⚠️ Redis não está rodando (opcional para desenvolvimento)"
    fi
else
    echo "⚠️ Redis não instalado (opcional para desenvolvimento)"
fi

echo ""
echo "🎉 Setup concluído!"
echo ""
echo "📋 Próximos passos:"
echo "1. Configure as variáveis em .env"
echo "2. Execute: source venv/bin/activate"
echo "3. Teste: python test_example.py"
echo "4. Execute: uvicorn app.api.main:app --reload"
echo "5. Acesse: http://localhost:8000"
echo ""
echo "📖 Documentação completa no README.md"
