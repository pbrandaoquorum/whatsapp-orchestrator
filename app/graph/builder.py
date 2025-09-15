"""
Builder do grafo LangGraph - monta o grafo completo com todos os nós e edges
"""
from typing import Dict, Any
from langgraph import StateGraph, END
from langgraph.checkpoint import MemoryCheckpointSaver

from app.graph.state import GraphState
from app.graph.router import route
from app.graph.flows.escala_flow import escala_flow
from app.graph.flows.clinical_flow import clinical_flow
from app.graph.flows.notas_flow import notas_flow
from app.graph.flows.finalizar_flow import finalizar_flow
from app.graph.flows.auxiliar_flow import auxiliar_flow
from app.infra.redis_checkpointer import criar_redis_checkpointer
from app.infra.logging import obter_logger

logger = obter_logger(__name__)


def criar_grafo(usar_redis: bool = True) -> StateGraph:
    """
    Cria o grafo LangGraph completo com todos os nós e conexões
    
    Args:
        usar_redis: Se deve usar Redis para checkpointing (fallback para MemoryCheckpointSaver)
    
    Returns:
        Grafo LangGraph compilado e pronto para uso
    """
    logger.info("Criando grafo LangGraph", usar_redis=usar_redis)
    
    # Criar grafo base
    grafo = StateGraph(GraphState)
    
    # Adicionar nós
    grafo.add_node("router", router_node)
    grafo.add_node("escala", escala_node)
    grafo.add_node("clinical", clinical_node)
    grafo.add_node("notas", notas_node)
    grafo.add_node("finalizar", finalizar_node)
    grafo.add_node("auxiliar", auxiliar_node)
    
    # Definir ponto de entrada
    grafo.set_entry_point("router")
    
    # Adicionar edges condicionais do router
    grafo.add_conditional_edges(
        "router",
        route,  # Função que determina o próximo nó
        {
            "escala": "escala",
            "clinical": "clinical", 
            "notas": "notas",
            "finalizar": "finalizar",
            "auxiliar": "auxiliar"
        }
    )
    
    # Função para decidir se continua ou termina após cada fluxo
    def decide_continuacao(state: GraphState) -> str:
        """Decide se continua no router ou termina baseado no estado"""
        # Se fluxo marcou para terminar, terminar
        if hasattr(state, 'terminar_fluxo') and state.terminar_fluxo:
            logger.info("Fluxo marcado para terminar", session_id=state.core.session_id)
            return "END"
        
        # Se há resposta para o usuário mas sem próximo fluxo, terminar
        if hasattr(state, 'resposta_usuario') and state.resposta_usuario:
            if not hasattr(state, 'continuar_fluxo') or not state.continuar_fluxo:
                logger.info("Resposta pronta, terminando", session_id=state.core.session_id)
                return "END"
        
        # Caso padrão: continuar no router para próxima iteração
        logger.info("Continuando no router", session_id=state.core.session_id)
        return "router"
    
    # Edges condicionais para TODOS os fluxos (podem continuar ou terminar)
    for fluxo in ["escala", "clinical", "notas", "finalizar", "auxiliar"]:
        grafo.add_conditional_edges(
            fluxo,
            decide_continuacao,
            {
                "router": "router",
                "END": END
            }
        )
    
    # Configurar checkpointer
    if usar_redis:
        try:
            checkpointer = criar_redis_checkpointer()
            logger.info("Usando Redis para checkpointing")
        except Exception as e:
            logger.warning(f"Erro ao configurar Redis checkpointer: {e}")
            logger.info("Usando MemoryCheckpointSaver como fallback")
            checkpointer = MemoryCheckpointSaver()
    else:
        checkpointer = MemoryCheckpointSaver()
        logger.info("Usando MemoryCheckpointSaver")
    
    # Compilar grafo
    try:
        grafo_compilado = grafo.compile(checkpointer=checkpointer)
        logger.info("Grafo LangGraph criado com sucesso")
        return grafo_compilado
        
    except Exception as e:
        logger.error(f"Erro ao compilar grafo: {e}")
        raise


async def router_node(state: GraphState) -> GraphState:
    """
    Nó do router - determina próximo fluxo baseado no estado usando classificação semântica
    """
    logger.debug("Executando nó router", session_id=state.core.session_id)
    
    try:
        # Executar roteamento assíncrono
        proximo_fluxo = await route(state)
        
        logger.info(
            "Router processado",
            session_id=state.core.session_id,
            intencao=state.router.intencao,
            ultimo_fluxo=state.router.ultimo_fluxo,
            proximo_fluxo=proximo_fluxo
        )
        
        # Definir próximo nó no estado
        state.proximo_no = proximo_fluxo
        
        return state
        
    except Exception as e:
        logger.error(f"Erro no nó router: {e}")
        # Em caso de erro, ir para auxiliar
        state.resposta_usuario = "Desculpe, ocorreu um erro. Tente novamente."
        state.router.intencao = "auxiliar"
        state.proximo_no = "auxiliar"
        return state


def escala_node(state: GraphState) -> GraphState:
    """
    Nó do fluxo de escala (confirmação/cancelamento de presença)
    """
    logger.debug("Executando nó escala", session_id=state.core.session_id)
    
    try:
        # Executar fluxo de escala assíncrono
        import asyncio
        state = asyncio.run(escala_flow(state))
        
        logger.info(
            "Fluxo de escala processado",
            session_id=state.core.session_id,
            presenca_confirmada=state.metadados.get("presenca_confirmada", False),
            cancelado=state.core.cancelado
        )
        
        return state
        
    except Exception as e:
        logger.error(f"Erro no nó escala: {e}")
        state.resposta_usuario = "Erro ao processar confirmação de presença. Tente novamente."
        return state


def clinical_node(state: GraphState) -> GraphState:
    """
    Nó do fluxo clínico (sinais vitais e dados clínicos)
    """
    logger.debug("Executando nó clinical", session_id=state.core.session_id)
    
    try:
        # Executar fluxo clínico assíncrono
        import asyncio
        state = asyncio.run(clinical_flow(state))
        
        logger.info(
            "Fluxo clínico processado",
            session_id=state.core.session_id,
            vitais_coletados=len(state.vitais.processados),
            vitais_faltantes=len(state.vitais.faltantes),
            sv_realizados=state.metadados.get("sinais_vitais_realizados", False)
        )
        
        return state
        
    except Exception as e:
        logger.error(f"Erro no nó clinical: {e}")
        state.resposta_usuario = "Erro ao processar dados clínicos. Tente novamente."
        return state


def notas_node(state: GraphState) -> GraphState:
    """
    Nó do fluxo de notas clínicas
    """
    logger.debug("Executando nó notas", session_id=state.core.session_id)
    
    try:
        # Executar fluxo de notas
        state = notas_flow(state)
        
        logger.info(
            "Fluxo de notas processado",
            session_id=state.core.session_id,
            nota_enviada=state.metadados.get("nota_clinica_enviada", False),
            sintomas_identificados=state.metadados.get("sintomas_identificados", 0)
        )
        
        return state
        
    except Exception as e:
        logger.error(f"Erro no nó notas: {e}")
        state.resposta_usuario = "Erro ao processar nota clínica. Tente novamente."
        return state


def finalizar_node(state: GraphState) -> GraphState:
    """
    Nó do fluxo de finalização
    """
    logger.debug("Executando nó finalizar", session_id=state.core.session_id)
    
    try:
        # Executar fluxo de finalização
        state = finalizar_flow(state)
        
        logger.info(
            "Fluxo de finalização processado",
            session_id=state.core.session_id,
            plantao_finalizado=state.metadados.get("plantao_finalizado", False),
            relatorio_enviado=state.metadados.get("relatorio_enviado", False)
        )
        
        return state
        
    except Exception as e:
        logger.error(f"Erro no nó finalizar: {e}")
        state.resposta_usuario = "Erro ao finalizar plantão. Tente novamente."
        return state


def auxiliar_node(state: GraphState) -> GraphState:
    """
    Nó do fluxo auxiliar (orientações e esclarecimentos)
    """
    logger.debug("Executando nó auxiliar", session_id=state.core.session_id)
    
    try:
        # Executar fluxo auxiliar
        state = auxiliar_flow(state)
        
        logger.info(
            "Fluxo auxiliar processado",
            session_id=state.core.session_id,
            tipo_orientacao="geral"  # Poderia ser mais específico baseado no contexto
        )
        
        return state
        
    except Exception as e:
        logger.error(f"Erro no nó auxiliar: {e}")
        state.resposta_usuario = "Como posso ajudar você?"
        return state


def obter_configuracao_grafo() -> Dict[str, Any]:
    """
    Retorna configuração atual do grafo para debug/monitoring
    """
    return {
        "nos": ["router", "escala", "clinical", "notas", "finalizar", "auxiliar"],
        "ponto_entrada": "router",
        "edges": {
            "router": ["escala", "clinical", "notas", "finalizar", "auxiliar"],
            "escala": ["router"],
            "clinical": ["router"],
            "notas": ["router"],
            "finalizar": ["END"],
            "auxiliar": ["END"]
        },
        "checkpointer": "Redis" if True else "Memory",  # TODO: detectar tipo real
        "versao": "1.0.0"
    }


def validar_grafo(grafo: StateGraph) -> bool:
    """
    Valida se o grafo foi construído corretamente
    """
    try:
        # Verificações básicas
        if not grafo:
            return False
        
        # TODO: Adicionar mais validações específicas
        # - Verificar se todos os nós estão conectados
        # - Verificar se não há loops infinitos
        # - Verificar se estados são válidos
        
        logger.info("Validação do grafo concluída com sucesso")
        return True
        
    except Exception as e:
        logger.error(f"Erro na validação do grafo: {e}")
        return False


# Cache do grafo para reutilização
_grafo_cache = None


def obter_grafo_cached(usar_redis: bool = True) -> StateGraph:
    """
    Obtém grafo com cache para melhor performance
    """
    global _grafo_cache
    
    if _grafo_cache is None:
        _grafo_cache = criar_grafo(usar_redis)
        
        # Validar grafo
        if not validar_grafo(_grafo_cache):
            logger.warning("Grafo não passou na validação")
    
    return _grafo_cache


def limpar_cache_grafo():
    """
    Limpa cache do grafo (útil para testes ou reload)
    """
    global _grafo_cache
    _grafo_cache = None
    logger.info("Cache do grafo limpo")
