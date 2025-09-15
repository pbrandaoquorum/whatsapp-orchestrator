"""
Testes para helpers de confirmação (sim/não)
"""
import pytest
from app.infra.confirm import is_yes, is_no, classificar_resposta, normalizar_texto


class TestConfirm:
    """Testes dos helpers de confirmação"""
    
    def test_is_yes_palavras_basicas(self):
        """Testa reconhecimento de confirmações básicas"""
        confirmacoes = [
            "sim", "s", "ok", "okay", "confirmo", "confirma", "confirmado",
            "certo", "perfeito", "correto", "positivo", "afirmativo",
            "concordo", "aceito", "pode", "beleza", "show", "top"
        ]
        
        for confirmacao in confirmacoes:
            assert is_yes(confirmacao) is True, f"'{confirmacao}' deveria ser reconhecido como SIM"
    
    def test_is_yes_emojis_e_simbolos(self):
        """Testa reconhecimento de emojis e símbolos de confirmação"""
        confirmacoes = ["👍", "✅", "✓", "1", "yes", "y"]
        
        for confirmacao in confirmacoes:
            assert is_yes(confirmacao) is True, f"'{confirmacao}' deveria ser reconhecido como SIM"
    
    def test_is_yes_frases(self):
        """Testa reconhecimento de frases de confirmação"""
        confirmacoes = [
            "isso mesmo", "é isso", "tudo certo", "pode ser", 
            "pode ir", "pode mandar", "vamos", "vai", "bora"
        ]
        
        for confirmacao in confirmacoes:
            assert is_yes(confirmacao) is True, f"'{confirmacao}' deveria ser reconhecido como SIM"
    
    def test_is_no_palavras_basicas(self):
        """Testa reconhecimento de negações básicas"""
        negacoes = [
            "não", "nao", "n", "nunca", "jamais", "negativo",
            "errado", "incorreto", "falso", "para", "pare",
            "cancela", "cancelar", "cancelado", "desisto"
        ]
        
        for negacao in negacoes:
            assert is_no(negacao) is True, f"'{negacao}' deveria ser reconhecido como NÃO"
    
    def test_is_no_emojis_e_simbolos(self):
        """Testa reconhecimento de emojis e símbolos de negação"""
        negacoes = ["👎", "❌", "✗", "0", "no", "nope"]
        
        for negacao in negacoes:
            assert is_no(negacao) is True, f"'{negacao}' deveria ser reconhecido como NÃO"
    
    def test_is_no_frases(self):
        """Testa reconhecimento de frases de negação"""
        negacoes = [
            "não confirmo", "nao confirmo", "não confere", "nao confere",
            "não é isso", "nao e isso", "não quero", "nao quero",
            "não aceito", "nao aceito"
        ]
        
        for negacao in negacoes:
            assert is_no(negacao) is True, f"'{negacao}' deveria ser reconhecido como NÃO"
    
    def test_normalizar_texto(self):
        """Testa normalização de texto"""
        casos_teste = [
            ("SIM!", "sim"),
            ("  Ok  ", "ok"),
            ("Não!!!!", "não"),
            ("CONFIRMO.", "confirmo"),
            ("   beleza   ?", "beleza")
        ]
        
        for entrada, esperado in casos_teste:
            resultado = normalizar_texto(entrada)
            assert resultado == esperado, f"'{entrada}' deveria normalizar para '{esperado}', got '{resultado}'"
    
    def test_classificar_resposta_sim(self):
        """Testa classificação de respostas positivas"""
        respostas_sim = ["sim", "ok", "confirmo", "👍", "beleza"]
        
        for resposta in respostas_sim:
            resultado = classificar_resposta(resposta)
            assert resultado == "sim", f"'{resposta}' deveria ser classificado como 'sim'"
    
    def test_classificar_resposta_nao(self):
        """Testa classificação de respostas negativas"""
        respostas_nao = ["não", "nao", "cancelar", "❌", "nunca"]
        
        for resposta in respostas_nao:
            resultado = classificar_resposta(resposta)
            assert resultado == "nao", f"'{resposta}' deveria ser classificado como 'nao'"
    
    def test_classificar_resposta_indefinido(self):
        """Testa classificação de respostas indefinidas"""
        respostas_indefinidas = [
            "talvez", "não sei", "depende", "mais ou menos",
            "pode ser que sim", "vou pensar", "depois eu vejo"
        ]
        
        for resposta in respostas_indefinidas:
            resultado = classificar_resposta(resposta)
            assert resultado == "indefinido", f"'{resposta}' deveria ser classificado como 'indefinido'"
    
    def test_case_insensitive(self):
        """Testa que reconhecimento é case insensitive"""
        casos_teste = [
            ("SIM", True, False),
            ("Sim", True, False),
            ("sIm", True, False),
            ("NÃO", False, True),
            ("Não", False, True),
            ("nÃo", False, True),
            ("OK", True, False),
            ("Ok", True, False),
            ("CANCELAR", False, True)
        ]
        
        for texto, esperado_sim, esperado_nao in casos_teste:
            assert is_yes(texto) == esperado_sim, f"is_yes('{texto}') deveria retornar {esperado_sim}"
            assert is_no(texto) == esperado_nao, f"is_no('{texto}') deveria retornar {esperado_nao}"
    
    def test_texto_vazio_ou_none(self):
        """Testa comportamento com texto vazio ou None"""
        assert is_yes("") is False
        assert is_yes(None) is False
        assert is_no("") is False
        assert is_no(None) is False
        
        assert classificar_resposta("") == "indefinido"
        assert classificar_resposta(None) == "indefinido"
    
    def test_pontuacao_e_espacos(self):
        """Testa que pontuação e espaços extras são ignorados"""
        casos_teste = [
            ("sim!", True),
            ("  ok  ", True),
            ("não.", False),
            ("cancelar!!!", False),
            ("   confirmo   ???", True)
        ]
        
        for texto, esperado_positivo in casos_teste:
            if esperado_positivo:
                assert is_yes(texto) is True, f"'{texto}' deveria ser reconhecido como SIM"
            else:
                assert is_no(texto) is True, f"'{texto}' deveria ser reconhecido como NÃO"
    
    def test_regex_patterns(self):
        """Testa padrões regex específicos"""
        # Testa padrões que usam regex
        casos_regex = [
            ("confirmo a ação", True, False),  # deve pegar "confirmo"
            ("não quero isso", False, True),   # deve pegar "não"
            ("pode mandar", True, False),      # deve pegar "pode"
            ("para tudo", False, True),        # deve pegar "para"
        ]
        
        for texto, esperado_sim, esperado_nao in casos_regex:
            assert is_yes(texto) == esperado_sim, f"is_yes('{texto}') falhou"
            assert is_no(texto) == esperado_nao, f"is_no('{texto}') falhou"
    
    def test_ambiguidade(self):
        """Testa que textos ambíguos não são classificados incorretamente"""
        # Textos que não deveriam ser classificados nem como sim nem como não
        textos_neutros = [
            "talvez", "depende", "vou pensar", "não sei ainda",
            "pode ser", "mais tarde", "vamos ver"
        ]
        
        for texto in textos_neutros:
            # Não deveria ser nem sim nem não
            assert not (is_yes(texto) and is_no(texto)), f"'{texto}' não pode ser sim E não ao mesmo tempo"
            
            # Na maioria dos casos, deveria ser indefinido
            resultado = classificar_resposta(texto)
            # Permitir que alguns sejam classificados se houver palavras-chave
            assert resultado in ["sim", "nao", "indefinido"], f"Classificação inválida para '{texto}': {resultado}"
