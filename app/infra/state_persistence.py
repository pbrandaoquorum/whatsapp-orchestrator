"""
Sistema de persistência de estado usando DynamoDB com OCC (Optimistic Concurrency Control)
"""
import json
from typing import Dict, Any, Optional, Tuple
from fastapi import Depends, HTTPException, Request
from botocore.exceptions import ClientError
from app.graph.state import GraphState, CoreState, VitalsState, NoteState, RouterState, AuxState
from app.infra.store import SessionStore
from app.infra.dynamo_client import is_conditional_check_failed
from app.infra.logging import obter_logger

logger = obter_logger(__name__)

# Instância global do store
_session_store: Optional[SessionStore] = None


def get_session_store() -> SessionStore:
    """Retorna instância singleton do SessionStore"""
    global _session_store
    if _session_store is None:
        _session_store = SessionStore()
    return _session_store


class StateManager:
    """Gerenciador de estado da sessão com OCC"""
    
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.state: Optional[GraphState] = None
        self.version: int = 0
        self._loaded = False
        self._store = get_session_store()
    
    async def load_state(self) -> GraphState:
        """
        Carrega estado da sessão do DynamoDB
        
        Returns:
            GraphState carregado ou novo se não existir
        """
        if self._loaded:
            return self.state
        
        try:
            state_dict, version = self._store.get(self.session_id)
            self.version = version
            
            if state_dict:
                # Deserializar estado
                self.state = self._deserialize_state(state_dict)
                logger.debug("Estado carregado do DynamoDB", 
                           session_id=self.session_id, 
                           version=version)
            else:
                # Criar estado inicial
                self.state = self._create_initial_state()
                logger.debug("Estado inicial criado", 
                           session_id=self.session_id)
            
            self._loaded = True
            return self.state
            
        except Exception as e:
            logger.error("Erro ao carregar estado", 
                        session_id=self.session_id, 
                        error=str(e))
            
            # Fallback para estado inicial
            self.state = self._create_initial_state()
            self._loaded = True
            return self.state
    
    async def save_state(self, max_retries: int = 1) -> bool:
        """
        Salva estado no DynamoDB com OCC
        
        Args:
            max_retries: Número máximo de tentativas em caso de conflito
            
        Returns:
            True se salvou com sucesso
            
        Raises:
            HTTPException: Em caso de conflito irrecuperável
        """
        if not self.state:
            logger.warning("Tentativa de salvar estado nulo", session_id=self.session_id)
            return False
        
        for attempt in range(max_retries + 1):
            try:
                # Serializar estado
                state_dict = self._serialize_state(self.state)
                
                # Tentar salvar com versão atual
                new_version = self._store.put(self.session_id, state_dict, self.version)
                
                # Atualizar versão local
                self.version = new_version
                
                logger.debug("Estado salvo com sucesso", 
                           session_id=self.session_id, 
                           version=new_version, 
                           attempt=attempt + 1)
                
                return True
                
            except ClientError as e:
                if is_conditional_check_failed(e):
                    if attempt < max_retries:
                        # Conflito de versão - recarregar e tentar novamente
                        logger.warning("Conflito de versão detectado, recarregando estado", 
                                     session_id=self.session_id, 
                                     attempt=attempt + 1,
                                     expected_version=self.version)
                        
                        await self._reload_and_merge()
                        continue
                    else:
                        # Conflito irrecuperável
                        logger.error("Conflito de versão irrecuperável", 
                                   session_id=self.session_id, 
                                   attempts=max_retries + 1)
                        
                        raise HTTPException(
                            status_code=409,
                            detail="Conflito de concorrência - estado foi modificado por outra operação"
                        )
                else:
                    # Outro erro
                    logger.error("Erro ao salvar estado", 
                               session_id=self.session_id, 
                               error=str(e))
                    raise HTTPException(
                        status_code=500,
                        detail="Erro interno ao salvar estado"
                    )
        
        return False
    
    async def _reload_and_merge(self) -> None:
        """
        Recarrega estado do DynamoDB e tenta fazer merge inteligente
        """
        try:
            # Recarregar do DynamoDB
            state_dict, new_version = self._store.get(self.session_id)
            
            if state_dict:
                # Deserializar estado atual do DB
                db_state = self._deserialize_state(state_dict)
                
                # Fazer merge inteligente (priorizar dados mais recentes)
                merged_state = self._merge_states(db_state, self.state)
                
                # Atualizar estado local
                self.state = merged_state
                self.version = new_version
                
                logger.info("Estado recarregado e mesclado", 
                          session_id=self.session_id, 
                          new_version=new_version)
            else:
                # Estado foi removido, manter o atual
                self.version = 0
                
        except Exception as e:
            logger.error("Erro ao recarregar estado", 
                        session_id=self.session_id, 
                        error=str(e))
            # Manter estado atual e tentar salvar com versão 0
            self.version = 0
    
    def _create_initial_state(self) -> GraphState:
        """Cria estado inicial para nova sessão"""
        return GraphState(
            core=CoreState(
                session_id=self.session_id,
                numero_telefone=self._extract_phone_from_session_id()
            ),
            vitais=VitalsState(),
            nota=NoteState(),
            router=RouterState(),
            aux=AuxState(),
            version=0  # Versão inicial
        )
    
    def _extract_phone_from_session_id(self) -> str:
        """Extrai número de telefone do session_id"""
        # session_id tem formato "session_5511999999999"
        if self.session_id.startswith("session_"):
            phone_digits = self.session_id[8:]  # Remove "session_"
            return f"+{phone_digits}"
        return ""
    
    def _serialize_state(self, state: GraphState) -> Dict[str, Any]:
        """Serializa GraphState para dict"""
        try:
            # Usar o método dict() do Pydantic
            state_dict = state.dict()
            
            # Adicionar versão se não existir
            if "version" not in state_dict:
                state_dict["version"] = self.version
            
            return state_dict
            
        except Exception as e:
            logger.error("Erro ao serializar estado", 
                        session_id=self.session_id, 
                        error=str(e))
            raise
    
    def _deserialize_state(self, state_dict: Dict[str, Any]) -> GraphState:
        """Deserializa dict para GraphState"""
        try:
            # Remover campos que não fazem parte do modelo
            clean_dict = {k: v for k, v in state_dict.items() if k != "version"}
            
            # Criar GraphState a partir do dict
            state = GraphState(**clean_dict)
            
            # Adicionar versão como atributo
            if hasattr(state, 'version'):
                state.version = state_dict.get("version", 0)
            
            return state
            
        except Exception as e:
            logger.error("Erro ao deserializar estado", 
                        session_id=self.session_id, 
                        error=str(e))
            
            # Fallback para estado inicial
            return self._create_initial_state()
    
    def _merge_states(self, db_state: GraphState, local_state: GraphState) -> GraphState:
        """
        Faz merge inteligente entre estado do DB e estado local
        
        Args:
            db_state: Estado atual do DynamoDB
            local_state: Estado local modificado
            
        Returns:
            Estado mesclado
        """
        # Estratégia simples: usar estado local mas preservar campos críticos do DB
        merged = local_state
        
        # Preservar IDs e dados críticos do DB
        if db_state.core.schedule_id and not local_state.core.schedule_id:
            merged.core.schedule_id = db_state.core.schedule_id
        
        if db_state.core.report_id and not local_state.core.report_id:
            merged.core.report_id = db_state.core.report_id
        
        # Preservar metadados importantes
        if db_state.metadados:
            if not merged.metadados:
                merged.metadados = {}
            
            # Merge metadados
            for key, value in db_state.metadados.items():
                if key not in merged.metadados:
                    merged.metadados[key] = value
        
        logger.debug("Estados mesclados", session_id=self.session_id)
        return merged


# Dependência FastAPI para injeção de estado
async def get_state_manager(request: Request) -> StateManager:
    """
    Dependência FastAPI para obter gerenciador de estado
    
    Args:
        request: Request FastAPI
        
    Returns:
        StateManager para a sessão
    """
    # Extrair session_id do request
    session_id = await extract_session_id(request)
    
    # Criar e retornar gerenciador
    manager = StateManager(session_id)
    
    # Armazenar no request state para uso posterior
    request.state.state_manager = manager
    
    return manager


async def extract_session_id(request: Request) -> str:
    """
    Extrai session_id do request
    
    Args:
        request: Request FastAPI
        
    Returns:
        session_id extraído
    """
    try:
        # Tentar extrair do path primeiro
        if hasattr(request, 'path_params') and 'session_id' in request.path_params:
            return request.path_params['session_id']
        
        # Tentar extrair do body JSON
        if request.method in ['POST', 'PUT', 'PATCH']:
            # Ler body se ainda não foi lido
            if not hasattr(request.state, 'json_body'):
                body = await request.body()
                if body:
                    try:
                        request.state.json_body = json.loads(body)
                    except json.JSONDecodeError:
                        request.state.json_body = {}
                else:
                    request.state.json_body = {}
            
            body = request.state.json_body
            phone_number = body.get('phoneNumber', '')
            
            if phone_number:
                # Converter telefone para session_id
                session_id = phone_number.replace('+', '').replace('-', '').replace(' ', '')
                return f"session_{session_id}"
        
        # Tentar extrair da query string
        session_id = request.query_params.get('session_id')
        if session_id:
            return session_id
        
        # Fallback para ID genérico
        logger.warning("Não foi possível extrair session_id do request")
        return "session_unknown"
        
    except Exception as e:
        logger.error("Erro ao extrair session_id", error=str(e))
        return "session_error"


# Dependência para obter estado carregado
async def get_loaded_state(manager: StateManager = Depends(get_state_manager)) -> GraphState:
    """
    Dependência FastAPI para obter estado já carregado
    
    Args:
        manager: StateManager injetado
        
    Returns:
        GraphState carregado
    """
    return await manager.load_state()


# Middleware para persistência automática
class StatePersistenceMiddleware:
    """
    Middleware para carregar/salvar estado automaticamente
    """
    
    def __init__(self, app):
        self.app = app
    
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        # Criar wrapper para interceptar resposta
        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                # Antes de enviar resposta, salvar estado se foi modificado
                request = scope.get("fastapi_request")
                if request and hasattr(request.state, 'state_manager'):
                    manager = request.state.state_manager
                    if manager.state and manager._loaded:
                        try:
                            await manager.save_state()
                        except Exception as e:
                            logger.error("Erro ao salvar estado no middleware", 
                                       session_id=manager.session_id, 
                                       error=str(e))
            
            await send(message)
        
        await self.app(scope, receive, send_wrapper)


# Funções utilitárias
def create_session_id_from_phone(phone_number: str) -> str:
    """
    Cria session_id a partir do número de telefone
    
    Args:
        phone_number: Número de telefone
        
    Returns:
        session_id padronizado
    """
    # Remover caracteres especiais
    clean_phone = phone_number.replace('+', '').replace('-', '').replace(' ', '').replace('(', '').replace(')', '')
    
    return f"session_{clean_phone}"


def extract_phone_from_session_id(session_id: str) -> str:
    """
    Extrai número de telefone do session_id
    
    Args:
        session_id: ID da sessão
        
    Returns:
        Número de telefone
    """
    if session_id.startswith("session_"):
        phone_digits = session_id[8:]  # Remove "session_"
        return f"+{phone_digits}"
    return ""
