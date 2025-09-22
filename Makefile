.PHONY: install dev test run clean lint

# Instalar dependências
install:
	pip install -e .

# Instalar dependências de desenvolvimento
dev:
	pip install -e .[dev]

# Executar testes
test:
	pytest tests/ -v

# Executar aplicação em desenvolvimento
run:
	uvicorn app.api.main:app --reload --host 0.0.0.0 --port 8000

# Executar aplicação em produção
run-prod:
	uvicorn app.api.main:app --host 0.0.0.0 --port 8000

# Limpar cache e arquivos temporários
clean:
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	rm -rf .pytest_cache/
	rm -rf dist/
	rm -rf build/

# Verificar lint
lint:
	ruff check .
	ruff format --check .

# Corrigir lint automaticamente
lint-fix:
	ruff check --fix .
	ruff format .

# Setup inicial do projeto
setup: install
	@echo "Copiando arquivo de exemplo de configuração..."
	@if [ ! -f .env ]; then cp .env.example .env; echo "Arquivo .env criado. Configure suas variáveis de ambiente."; fi
	@echo "Setup concluído! Configure o arquivo .env antes de executar."

# Verificar saúde da aplicação
health:
	curl -f http://localhost:8000/healthz || echo "Aplicação não está rodando"

# Teste de webhook local
test-webhook:
	curl -X POST "http://localhost:8000/webhook/whatsapp" \
		-H "Content-Type: application/json" \
		-d '{"message_id": "test123", "phoneNumber": "5511999999999", "text": "PA 120x80 FC 75", "meta": {}}'
