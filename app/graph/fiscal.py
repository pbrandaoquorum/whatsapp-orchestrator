"""
Módulo Fiscal - Sempre o último
Lê estado canônico do DynamoDB e gera respostas dinâmicas via LLM
NUNCA usa respostas estáticas - tudo é contextual e gerado por LLM
"""
import structlog
from typing import Optional

from app.graph.state import GraphState
from app.llm.fiscal_llm import FiscalLLM
from app.infra.dynamo_state import DynamoStateManager

logger = structlog.get_logger(__name__)


class FiscalProcessor:
    """Processador fiscal - gera respostas dinâmicas via LLM"""
    
    def __init__(self, dynamo_manager: DynamoStateManager, api_key: str, model: str = "gpt-4o-mini"):
        self.dynamo_manager = dynamo_manager
        
        # Inicializa LLM apenas se tiver API key
        if api_key:
            self.fiscal_llm = FiscalLLM(api_key, model)
            logger.info("FiscalProcessor inicializado com LLM", model=model)
        else:
            self.fiscal_llm = None
            logger.warning("FiscalProcessor inicializado SEM LLM - API key não encontrada")
    
    def _ler_estado_canonico(self, session_id: str) -> Optional[dict]:
        """
        Lê o estado canônico diretamente do DynamoDB (fonte de verdade)
        
        Args:
            session_id: ID da sessão
            
        Returns:
            Estado completo do DynamoDB ou None se erro
        """
        try:
            # Carrega estado do DynamoDB
            state = self.dynamo_manager.carregar_estado(session_id)
            
            if state is None:
                logger.warning("Estado não encontrado no DynamoDB", session_id=session_id)
                return None
            
            # Converte para dict para o LLM
            estado_dict = state.model_dump()
            
            # Valida estrutura do estado
            if not isinstance(estado_dict, dict):
                logger.error("Estado não é um dict válido", session_id=session_id, tipo=type(estado_dict))
                return None
                
            # Garante estruturas básicas
            if "sessao" not in estado_dict:
                estado_dict["sessao"] = {}
            if "clinico" not in estado_dict:
                estado_dict["clinico"] = {}
            if "pendente" not in estado_dict:
                estado_dict["pendente"] = {}
            if "fluxos_executados" not in estado_dict:
                estado_dict["fluxos_executados"] = []
            
            logger.debug("Estado canônico carregado do DynamoDB",
                        session_id=session_id,
                        fluxos_executados=len(estado_dict.get("fluxos_executados", [])),
                        tem_pendente=bool(estado_dict.get("pendente")))
            
            return estado_dict
            
        except Exception as e:
            logger.error("Erro ao ler estado canônico do DynamoDB", 
                        session_id=session_id, error=str(e))
            return None
    
    def _gerar_resposta_fallback(self, entrada_usuario: str) -> str:
        """
        Gera resposta fallback quando LLM não está disponível
        Ainda assim, evita ser completamente estática
        """
        entrada_lower = entrada_usuario.lower()
        
        if any(palavra in entrada_lower for palavra in ['ajuda', 'help', 'oi', 'olá']):
            return "Sistema temporariamente limitado. Tente: confirmo presença, dados vitais, finalizar plantão."
        elif any(palavra in entrada_lower for palavra in ['pa', 'fc', 'fr', 'sat', 'temp']):
            return "Dados recebidos. Sistema processando sem confirmação dinâmica no momento."
        else:
            return "Sistema em modo básico. Funcionalidades limitadas."
    
    def processar_resposta_fiscal(self, session_id: str, entrada_usuario: str) -> str:
        """
        Processa resposta fiscal final - SEMPRE lê estado do DynamoDB
        
        Args:
            session_id: ID da sessão para buscar no DynamoDB
            entrada_usuario: Última mensagem do usuário
        
        Returns:
            Resposta contextual e dinâmica gerada via LLM
        """
        logger.info("Processando resposta fiscal via LLM",
                   session_id=session_id,
                   entrada=entrada_usuario[:50])
        
        # 1. Lê estado canônico do DynamoDB (fonte de verdade)
        logger.info("Iniciando leitura do estado canônico", session_id=session_id)
        estado_atual = self._ler_estado_canonico(session_id)
        
        if estado_atual is None:
            logger.error("Não foi possível ler estado do DynamoDB", session_id=session_id)
            return "Erro interno. Tente novamente."
        
        logger.info("Estado canônico lido com sucesso", 
                   session_id=session_id,
                   tem_clinico=bool(estado_atual.get("clinico")),
                   fluxos_executados=len(estado_atual.get("fluxos_executados", [])))
        
        # 2. Se LLM disponível, gera resposta dinâmica
        if self.fiscal_llm:
            logger.info("Tentando gerar resposta via LLM", session_id=session_id)
            try:
                resposta = self.fiscal_llm.gerar_resposta(estado_atual, entrada_usuario)
                
                logger.info("Resposta gerada via LLM com sucesso",
                           session_id=session_id,
                           resposta_length=len(resposta),
                           resposta_preview=resposta[:50])
                
                return resposta
                
            except Exception as e:
                logger.error("Erro ao gerar resposta via LLM", 
                            session_id=session_id, 
                            error=str(e),
                            error_type=type(e).__name__)
                # Fallback em caso de erro
                return self._gerar_resposta_fallback(entrada_usuario)
        
        # 3. Fallback se LLM não disponível
        else:
            logger.warning("Usando resposta fallback - LLM não disponível", session_id=session_id)
            return self._gerar_resposta_fallback(entrada_usuario)
