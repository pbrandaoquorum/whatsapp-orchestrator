"""
Aplicação principal FastAPI
"""
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from app.api.routes import router
from app.api.middleware import configurar_middlewares
from app.api.schemas import ErrorResponse
from app.infra.logging import configurar_logging, obter_logger
from app.infra.timeutils import agora_br

# Configurar logging
configurar_logging(os.getenv("LOG_LEVEL", "INFO"))
logger = obter_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerencia ciclo de vida da aplicação"""
    # Startup
    logger.info("Iniciando aplicação WhatsApp Orchestrator")
    
    # Verificar variáveis de ambiente críticas
    verificar_configuracao()
    
    # Inicializar dependências
    await inicializar_dependencias()
    
    logger.info("Aplicação iniciada com sucesso")
    
    yield
    
    # Shutdown
    logger.info("Encerrando aplicação")
    await finalizar_dependencias()
    logger.info("Aplicação encerrada")


def verificar_configuracao():
    """Verifica se configurações críticas estão presentes"""
    variaveis_obrigatorias = [
        "LAMBDA_GET_SCHEDULE",
        "LAMBDA_UPDATE_SCHEDULE", 
        "LAMBDA_UPDATE_CLINICAL",
        "LAMBDA_UPDATE_SUMMARY"
    ]
    
    variaveis_faltantes = []
    for var in variaveis_obrigatorias:
        if not os.getenv(var):
            variaveis_faltantes.append(var)
    
    if variaveis_faltantes:
        logger.error(
            "Variáveis de ambiente obrigatórias não configuradas",
            variaveis_faltantes=variaveis_faltantes
        )
        raise RuntimeError(f"Variáveis faltantes: {', '.join(variaveis_faltantes)}")
    
    logger.info("Configuração validada com sucesso")


async def inicializar_dependencias():
    """Inicializa dependências da aplicação"""
    try:
        # Testar conexões
        from app.rag.pinecone_client import testar_conexao as testar_pinecone
        from app.rag.sheets_sync import testar_conexao_sheets
        
        # Pinecone (opcional - apenas warning se falhar)
        try:
            if testar_pinecone():
                logger.info("Conexão Pinecone testada com sucesso")
            else:
                logger.warning("Falha na conexão Pinecone - RAG pode não funcionar")
        except Exception as e:
            logger.warning(f"Erro ao testar Pinecone: {e}")
        
        # Google Sheets (opcional - apenas warning se falhar)
        try:
            if testar_conexao_sheets():
                logger.info("Conexão Google Sheets testada com sucesso")
            else:
                logger.warning("Falha na conexão Google Sheets - sincronização pode não funcionar")
        except Exception as e:
            logger.warning(f"Erro ao testar Google Sheets: {e}")
        
        # TODO: Inicializar Redis quando implementado
        # TODO: Testar conexão com Lambdas
        
        logger.info("Dependências inicializadas")
        
    except Exception as e:
        logger.error(f"Erro ao inicializar dependências: {e}")
        # Não falhar a aplicação por dependências opcionais
        # raise


async def finalizar_dependencias():
    """Finaliza dependências da aplicação"""
    try:
        # TODO: Fechar conexões Redis
        # TODO: Cleanup de recursos
        
        logger.info("Dependências finalizadas")
        
    except Exception as e:
        logger.error(f"Erro ao finalizar dependências: {e}")


# Criar aplicação FastAPI
app = FastAPI(
    title="WhatsApp Orchestrator",
    description="Sistema FastAPI + LangGraph para orquestração de fluxos WhatsApp",
    version="1.0.0",
    lifespan=lifespan
)

# Configurar middlewares
configurar_middlewares(app)  # Redis será passado quando implementado

# Incluir rotas
app.include_router(router)


# Exception handlers
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    """Handler para erros de validação"""
    logger.warning(
        "Erro de validação na request",
        url=str(request.url),
        errors=exc.errors()
    )
    
    return JSONResponse(
        status_code=422,
        content=ErrorResponse(
            error="validation_error",
            message="Dados da request inválidos",
            details={"errors": exc.errors()}
        ).dict()
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Handler para HTTPExceptions"""
    logger.error(
        "HTTP Exception",
        url=str(request.url),
        status_code=exc.status_code,
        detail=exc.detail
    )
    
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error="http_error",
            message=exc.detail,
            details={"status_code": exc.status_code}
        ).dict()
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """Handler para exceções gerais"""
    logger.error(
        "Exceção não tratada",
        url=str(request.url),
        exception_type=type(exc).__name__,
        exception_message=str(exc)
    )
    
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error="internal_error",
            message="Erro interno do servidor",
            details={"type": type(exc).__name__}
        ).dict()
    )


# Endpoint raiz
@app.get("/")
async def root():
    """Endpoint raiz com informações básicas"""
    return {
        "service": "WhatsApp Orchestrator",
        "version": "1.0.0",
        "status": "running",
        "timestamp": agora_br().isoformat(),
        "endpoints": {
            "webhook": "/webhook/whatsapp",
            "templates": "/events/template-sent",
            "debug": "/graph/debug/run",
            "health": "/healthz",
            "readiness": "/readyz",
            "rag_sync": "/rag/sync",
            "rag_search": "/rag/search"
        }
    }


if __name__ == "__main__":
    import uvicorn
    
    # Configuração para desenvolvimento
    uvicorn.run(
        "app.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
