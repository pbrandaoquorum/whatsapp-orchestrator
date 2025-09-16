"""
Helpers para confirmação (sim/não) em português brasileiro
Agora usa classificação semântica via LLM
"""
from typing import Optional


def normalizar_texto(texto: str) -> str:
    """Normaliza texto para comparação básica"""
    if not texto:
        return ""
    
    return texto.lower().strip()


async def is_yes_semantic(texto: str) -> bool:
    """
    Verifica se o texto indica confirmação (SIM) usando LLM semântico
    """
    if not texto:
        return False
    
    try:
        from app.graph.semantic_classifier import classify_semantic, IntentType
        from app.graph.state import GraphState, CoreState
        
        # Criar estado mínimo para classificação
        estado_temp = GraphState(
            core=CoreState(session_id="temp", numero_telefone="temp"),
            texto_usuario=texto
        )
        
        # Classificar semanticamente
        resultado = await classify_semantic(texto, estado_temp)
        
        return resultado.intent == IntentType.CONFIRMACAO_SIM
    
    except Exception:
        # Fallback simples em caso de erro
        return False


async def is_no_semantic(texto: str) -> bool:
    """
    Verifica se o texto indica negação (NÃO) usando LLM semântico
    """
    if not texto:
        return False
    
    try:
        from app.graph.semantic_classifier import classify_semantic, IntentType
        from app.graph.state import GraphState, CoreState
        
        # Criar estado mínimo para classificação
        estado_temp = GraphState(
            core=CoreState(session_id="temp", numero_telefone="temp"),
            texto_usuario=texto
        )
        
        # Classificar semanticamente
        resultado = await classify_semantic(texto, estado_temp)
        
        return resultado.intent == IntentType.CONFIRMACAO_NAO
    
    except Exception:
        # Fallback simples em caso de erro
        return False


async def classificar_resposta_semantica(texto: str) -> str:
    """
    Classifica resposta como 'sim', 'nao' ou 'indefinido' usando LLM semântico
    """
    if await is_yes_semantic(texto):
        return "sim"
    elif await is_no_semantic(texto):
        return "nao"
    else:
        return "indefinido"


# Funções legacy para compatibilidade (devem ser migradas gradualmente)
def is_yes(texto: str) -> bool:
    """DEPRECATED: Use is_yes_semantic() - fallback simples apenas"""
    if not texto:
        return False
    
    # Fallback muito básico apenas para compatibilidade
    texto_lower = normalizar_texto(texto)
    palavras_sim_basicas = ["sim", "s", "ok", "confirmo", "certo", "pode"]
    return any(palavra in texto_lower for palavra in palavras_sim_basicas)


def is_no(texto: str) -> bool:
    """DEPRECATED: Use is_no_semantic() - fallback simples apenas"""
    if not texto:
        return False
    
    # Fallback muito básico apenas para compatibilidade
    texto_lower = normalizar_texto(texto)
    palavras_nao_basicas = ["não", "nao", "n", "negativo", "cancelar"]
    return any(palavra in texto_lower for palavra in palavras_nao_basicas)


def classificar_resposta(texto: str) -> str:
    """DEPRECATED: Use classificar_resposta_semantica() - fallback simples apenas"""
    if is_yes(texto):
        return "sim"
    elif is_no(texto):
        return "nao"
    else:
        return "indefinido"


async def extrair_confirmacao_contexto(texto: str, contexto: str = "") -> str:
    """
    Extrai confirmação considerando contexto da pergunta usando LLM semântico
    """
    # Usar classificação semântica que já considera contexto
    return await classificar_resposta_semantica(texto)
