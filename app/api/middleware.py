"""
Middleware para FastAPI - logging, CORS, rate limiting, etc.
"""
import time
import uuid
from typing import Callable
from fastapi import Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.base import BaseHTTPMiddleware
from starlette.middleware.base import RequestResponseEndpoint

from app.infra.logging import obter_logger

logger = obter_logger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware para logging estruturado de requests/responses"""
    
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Gerar ID único para a request
        request_id = str(uuid.uuid4())
        
        # Adicionar request_id ao contexto
        request.state.request_id = request_id
        
        # Log da request
        start_time = time.time()
        
        logger.info(
            "Request iniciada",
            request_id=request_id,
            method=request.method,
            url=str(request.url),
            client_ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent", "")
        )
        
        try:
            # Processar request
            response = await call_next(request)
            
            # Calcular tempo de processamento
            process_time = time.time() - start_time
            
            # Log da response
            logger.info(
                "Request concluída",
                request_id=request_id,
                status_code=response.status_code,
                tempo_processamento_ms=round(process_time * 1000, 2),
                sucesso=200 <= response.status_code < 300
            )
            
            # Adicionar headers de tracking
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Process-Time"] = str(round(process_time * 1000, 2))
            
            return response
            
        except Exception as e:
            # Log do erro
            process_time = time.time() - start_time
            
            logger.error(
                "Erro no processamento da request",
                request_id=request_id,
                erro=str(e),
                tempo_processamento_ms=round(process_time * 1000, 2)
            )
            
            raise


class DeduplicationMiddleware(BaseHTTPMiddleware):
    """Middleware para deduplicação baseada em message_id"""
    
    def __init__(self, app, redis_client=None):
        super().__init__(app)
        self.redis_client = redis_client
    
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Apenas para endpoints de webhook
        if not request.url.path.startswith("/webhook/"):
            return await call_next(request)
        
        # Tentar extrair message_id do body
        message_id = await self._extract_message_id(request)
        
        if message_id and self.redis_client:
            # Verificar se já foi processado
            cache_key = f"msg:{message_id}"
            
            if await self._is_duplicate(cache_key):
                logger.warning(
                    "Mensagem duplicada detectada",
                    message_id=message_id,
                    request_id=getattr(request.state, 'request_id', None)
                )
                
                # Retornar resposta cached se disponível
                cached_response = await self._get_cached_response(cache_key)
                if cached_response:
                    return Response(
                        content=cached_response,
                        status_code=200,
                        headers={"Content-Type": "application/json"}
                    )
            
            # Marcar como processando
            await self._mark_processing(cache_key)
        
        # Processar normalmente
        response = await call_next(request)
        
        # Cache da resposta se sucesso
        if message_id and self.redis_client and 200 <= response.status_code < 300:
            await self._cache_response(f"msg:{message_id}", response)
        
        return response
    
    async def _extract_message_id(self, request: Request) -> str:
        """Extrai message_id do body da request"""
        try:
            # Ler body
            body = await request.body()
            
            if body:
                import json
                data = json.loads(body)
                return data.get("message_id")
        except Exception:
            pass
        
        return None
    
    async def _is_duplicate(self, cache_key: str) -> bool:
        """Verifica se é mensagem duplicada"""
        try:
            return await self.redis_client.exists(cache_key)
        except Exception:
            return False
    
    async def _mark_processing(self, cache_key: str) -> None:
        """Marca mensagem como sendo processada"""
        try:
            # TTL de 10 minutos
            await self.redis_client.setex(cache_key, 600, "processing")
        except Exception:
            pass
    
    async def _cache_response(self, cache_key: str, response: Response) -> None:
        """Faz cache da resposta"""
        try:
            # Ler body da response
            response_body = b""
            async for chunk in response.body_iterator:
                response_body += chunk
            
            # Cache por 10 minutos
            await self.redis_client.setex(f"{cache_key}:response", 600, response_body)
        except Exception:
            pass
    
    async def _get_cached_response(self, cache_key: str) -> str:
        """Obtém resposta cached"""
        try:
            return await self.redis_client.get(f"{cache_key}:response")
        except Exception:
            return None


class SecurityMiddleware(BaseHTTPMiddleware):
    """Middleware para headers de segurança"""
    
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        
        # Headers de segurança
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        # Content Security Policy básico
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "connect-src 'self'"
        )
        
        return response


def configurar_cors(app):
    """Configura CORS para a aplicação"""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Em produção, especificar origins exatos
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "X-Process-Time"]
    )


def configurar_middlewares(app, redis_client=None):
    """Configura todos os middlewares da aplicação"""
    
    # Middleware de segurança (primeiro)
    app.add_middleware(SecurityMiddleware)
    
    # CORS
    configurar_cors(app)
    
    # Deduplicação (se Redis disponível)
    if redis_client:
        app.add_middleware(DeduplicationMiddleware, redis_client=redis_client)
    
    # Logging (último, para capturar tudo)
    app.add_middleware(LoggingMiddleware)
