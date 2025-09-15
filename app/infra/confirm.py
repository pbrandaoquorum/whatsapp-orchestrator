"""
Helpers para confirmação (sim/não) em português brasileiro
"""
import re
from typing import Set

# Palavras e expressões que indicam confirmação (SIM)
CONFIRMACOES: Set[str] = {
    "sim", "s", "ok", "okay", "confirmo", "confirma", "confirmado", "confere",
    "certo", "perfeito", "exato", "correto", "isso", "isso mesmo", "é isso",
    "tudo certo", "pode ser", "beleza", "blz", "show", "top", "positivo",
    "afirmativo", "concordo", "aceito", "vamos", "vai", "dale", "bora",
    "pode", "pode ir", "pode mandar", "manda", "enviar", "envie",
    "👍", "✅", "✓", "1", "yes", "y"
}

# Palavras e expressões que indicam negação (NÃO)
NEGACOES: Set[str] = {
    "não", "nao", "n", "nunca", "jamais", "negativo", "não confirmo",
    "nao confirmo", "não confere", "nao confere", "errado", "incorreto",
    "falso", "não é isso", "nao e isso", "não é", "nao e", "para",
    "pare", "cancela", "cancelar", "cancelado", "desisto", "não quero",
    "nao quero", "recuso", "rejeito", "discordo", "não aceito",
    "nao aceito", "👎", "❌", "✗", "0", "no", "nope"
}

# Padrões regex para confirmação
PADROES_CONFIRMACAO = [
    r'\bsim\b',
    r'\bok\b',
    r'\bconfirm[ao]\b',
    r'\bcerto\b',
    r'\bperfeito\b',
    r'\bcorreto\b',
    r'\bpositivo\b',
    r'\bafirmativo\b',
    r'\bconcordo\b',
    r'\baceito\b',
    r'\bpode\b',
    r'\bmanda\b',
    r'\benviar?\b',
    r'👍|✅|✓',
]

# Padrões regex para negação
PADROES_NEGACAO = [
    r'\bnão\b|\bnao\b',
    r'\bnunca\b',
    r'\bjamais\b',
    r'\bnegativo\b',
    r'\berrado\b',
    r'\bincorreto\b',
    r'\bfalso\b',
    r'\bpara\b|\bpare\b',
    r'\bcancela\b|\bcancelar?\b',
    r'\bdesisto\b',
    r'\brecuso\b',
    r'\brejeito\b',
    r'\bdiscordo\b',
    r'👎|❌|✗',
]


def normalizar_texto(texto: str) -> str:
    """Normaliza texto para comparação"""
    if not texto:
        return ""
    
    # Converter para lowercase
    texto = texto.lower().strip()
    
    # Remover pontuação extra
    texto = re.sub(r'[!.,;:?]+$', '', texto)
    
    # Normalizar espaços
    texto = re.sub(r'\s+', ' ', texto)
    
    return texto


def is_yes(texto: str) -> bool:
    """
    Verifica se o texto indica confirmação (SIM)
    """
    if not texto:
        return False
    
    texto_normalizado = normalizar_texto(texto)
    
    # Verificar palavras exatas
    if texto_normalizado in CONFIRMACOES:
        return True
    
    # Verificar padrões regex
    for padrao in PADROES_CONFIRMACAO:
        if re.search(padrao, texto_normalizado, re.IGNORECASE):
            return True
    
    return False


def is_no(texto: str) -> bool:
    """
    Verifica se o texto indica negação (NÃO)
    """
    if not texto:
        return False
    
    texto_normalizado = normalizar_texto(texto)
    
    # Verificar palavras exatas
    if texto_normalizado in NEGACOES:
        return True
    
    # Verificar padrões regex
    for padrao in PADROES_NEGACAO:
        if re.search(padrao, texto_normalizado, re.IGNORECASE):
            return True
    
    return False


def classificar_resposta(texto: str) -> str:
    """
    Classifica resposta como 'sim', 'nao' ou 'indefinido'
    """
    if is_yes(texto):
        return "sim"
    elif is_no(texto):
        return "nao"
    else:
        return "indefinido"


def extrair_confirmacao_contexto(texto: str, contexto: str = "") -> str:
    """
    Extrai confirmação considerando contexto da pergunta
    """
    # Primeiro tenta classificação direta
    resultado = classificar_resposta(texto)
    
    if resultado != "indefinido":
        return resultado
    
    # Se indefinido, pode tentar heurísticas baseadas no contexto
    # Por exemplo, se o contexto é sobre "cancelar" e usuário diz "sim",
    # isso significa confirmação de cancelamento
    
    return resultado
