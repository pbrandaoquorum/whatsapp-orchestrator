"""
Testes para o router determinístico
"""
import pytest
from unittest.mock import patch, MagicMock

from app.graph.state import GraphState, CoreState, VitalsState, RouterState, AuxState
from app.graph.router import (
    route, presenca_confirmada, sinais_vitais_realizados,
    processar_retomada_pendente, processar_pergunta_pendente,
    detectar_sinais_vitais_no_texto, aplicar_gates_pos_classificacao
)


class TestRouter:
    """Testes do router determinístico"""
    
    def criar_estado_base(self, **kwargs):
        """Helper para criar estado base para testes"""
        estado_default = {
            "core": CoreState(
                session_id="test_session",
                numero_telefone="+5511999999999",
                turno_permitido=True,
                cancelado=False
            ),
            "vitais": VitalsState(),
            "router": RouterState(),
            "aux": AuxState(),
            "metadados": {}
        }
        
        # Merge com kwargs
        for key, value in kwargs.items():
            if hasattr(estado_default[key.split('.')[0]], key.split('.')[1] if '.' in key else key):
                if '.' in key:
                    section, field = key.split('.')
                    setattr(estado_default[section], field, value)
                else:
                    estado_default[key] = value
        
        return GraphState(**estado_default)
    
    def test_presenca_confirmada_via_metadados(self):
        """Testa verificação de presença confirmada via metadados"""
        estado = self.criar_estado_base(metadados={"presenca_confirmada": True})
        assert presenca_confirmada(estado) is True
        
        estado = self.criar_estado_base(metadados={"presenca_confirmada": False})
        assert presenca_confirmada(estado) is False
    
    def test_presenca_confirmada_via_core_state(self):
        """Testa verificação de presença confirmada via core state"""
        estado = self.criar_estado_base()
        estado.core.turno_permitido = True
        estado.core.turno_iniciado = True
        estado.core.cancelado = False
        
        assert presenca_confirmada(estado) is True
        
        estado.core.cancelado = True
        assert presenca_confirmada(estado) is False
    
    def test_sinais_vitais_realizados_via_metadados(self):
        """Testa verificação de sinais vitais via metadados"""
        estado = self.criar_estado_base(metadados={"sinais_vitais_realizados": True})
        assert sinais_vitais_realizados(estado) is True
        
        estado = self.criar_estado_base(metadados={"sinais_vitais_realizados": False})
        assert sinais_vitais_realizados(estado) is False
    
    def test_sinais_vitais_realizados_via_processados(self):
        """Testa verificação de sinais vitais via dados processados"""
        estado = self.criar_estado_base()
        estado.vitais.processados = {
            "PA": "120x80",
            "FC": 78,
            "FR": 18,
            "Sat": 97,
            "Temp": 36.5
        }
        
        assert sinais_vitais_realizados(estado) is True
        
        # Faltando um sinal vital
        estado.vitais.processados = {"PA": "120x80", "FC": 78}
        assert sinais_vitais_realizados(estado) is False
    
    def test_processar_retomada_pendente(self):
        """Testa processamento de retomada pendente"""
        estado = self.criar_estado_base()
        
        # Sem retomada pendente
        resultado = processar_retomada_pendente(estado)
        assert resultado is None
        
        # Com retomada pendente
        estado.aux.retomar_apos = {"flow": "finalizar", "reason": "vitals_before_finish"}
        resultado = processar_retomada_pendente(estado)
        assert resultado == "finalizar"
        assert estado.aux.retomar_apos is None  # Deve ser limpa
    
    @patch('app.graph.router.is_yes')
    @patch('app.graph.router.is_no')
    def test_processar_pergunta_pendente_confirmacao(self, mock_is_no, mock_is_yes):
        """Testa processamento de pergunta pendente para confirmação"""
        estado = self.criar_estado_base()
        estado.aux.ultima_pergunta = "Confirma ação?"
        estado.aux.acao_pendente = {"fluxo_destino": "escala_commit"}
        estado.texto_usuario = "sim"
        
        mock_is_yes.return_value = True
        mock_is_no.return_value = False
        
        resultado = processar_pergunta_pendente(estado)
        assert resultado == "escala_commit"
        
        # Teste com "não"
        mock_is_yes.return_value = False
        mock_is_no.return_value = True
        
        resultado = processar_pergunta_pendente(estado)
        assert resultado == "auxiliar"
        assert estado.aux.acao_pendente is None
    
    @patch('app.graph.router.extrair_sinais_vitais')
    def test_processar_pergunta_pendente_coleta_incremental(self, mock_extrair):
        """Testa coleta incremental de sinais vitais"""
        estado = self.criar_estado_base()
        estado.aux.ultima_pergunta = "Aguardando sinais vitais"
        estado.aux.fluxo_que_perguntou = "clinical"
        estado.texto_usuario = "FC 78, FR 18"
        
        # Mock do extrator
        mock_resultado = MagicMock()
        mock_resultado.processados = {"FC": 78, "FR": 18}
        mock_extrair.return_value = mock_resultado
        
        resultado = processar_pergunta_pendente(estado)
        
        # Deve ter atualizado os sinais vitais
        assert estado.vitais.processados["FC"] == 78
        assert estado.vitais.processados["FR"] == 18
        
        # Como ainda faltam sinais, deve continuar no auxiliar
        assert resultado == "auxiliar"
    
    @patch('app.graph.router.extrair_sinais_vitais')
    @patch('app.graph.router.presenca_confirmada')
    def test_detectar_sinais_vitais_no_texto_sem_presenca(self, mock_presenca, mock_extrair):
        """Testa detecção de sinais vitais sem presença confirmada"""
        estado = self.criar_estado_base()
        estado.texto_usuario = "PA 120x80, FC 78"
        
        # Mock dos helpers
        mock_resultado = MagicMock()
        mock_resultado.processados = {"PA": "120x80", "FC": 78}
        mock_extrair.return_value = mock_resultado
        mock_presenca.return_value = False
        
        resultado = detectar_sinais_vitais_no_texto(estado)
        
        assert resultado == "escala"
        assert estado.aux.buffers["vitals"] == {"PA": "120x80", "FC": 78}
        assert estado.aux.retomar_apos is not None
    
    @patch('app.graph.router.extrair_sinais_vitais')
    @patch('app.graph.router.presenca_confirmada')
    def test_detectar_sinais_vitais_no_texto_com_presenca(self, mock_presenca, mock_extrair):
        """Testa detecção de sinais vitais com presença confirmada"""
        estado = self.criar_estado_base()
        estado.texto_usuario = "PA 120x80, FC 78"
        
        # Mock dos helpers
        mock_resultado = MagicMock()
        mock_resultado.processados = {"PA": "120x80", "FC": 78}
        mock_extrair.return_value = mock_resultado
        mock_presenca.return_value = True
        
        resultado = detectar_sinais_vitais_no_texto(estado)
        
        assert resultado == "clinical"
        assert estado.vitais.processados["PA"] == "120x80"
        assert estado.vitais.processados["FC"] == 78
    
    def test_aplicar_gates_turno_cancelado(self):
        """Testa gates com turno cancelado"""
        estado = self.criar_estado_base()
        estado.core.cancelado = True
        
        resultado = aplicar_gates_pos_classificacao("clinical", estado)
        assert resultado == "auxiliar"
        
        resultado = aplicar_gates_pos_classificacao("auxiliar", estado)
        assert resultado == "auxiliar"  # Auxiliar passa
    
    @patch('app.graph.router.presenca_confirmada')
    def test_aplicar_gates_presenca_nao_confirmada(self, mock_presenca):
        """Testa gates com presença não confirmada"""
        estado = self.criar_estado_base()
        mock_presenca.return_value = False
        
        intencoes_bloqueadas = ["clinical", "sinais_vitais", "notas", "finalizar"]
        
        for intencao in intencoes_bloqueadas:
            resultado = aplicar_gates_pos_classificacao(intencao, estado)
            assert resultado == "escala"
            assert estado.aux.retomar_apos is not None
    
    @patch('app.graph.router.sinais_vitais_realizados')
    def test_aplicar_gates_finalizar_sem_sinais_vitais(self, mock_sv_realizados):
        """Testa gate de finalização sem sinais vitais"""
        estado = self.criar_estado_base()
        mock_sv_realizados.return_value = False
        
        resultado = aplicar_gates_pos_classificacao("finalizar", estado)
        assert resultado == "clinical"
        assert estado.aux.retomar_apos["flow"] == "finalizar"
    
    @patch('app.graph.router.garantir_bootstrap_sessao')
    @patch('app.graph.router.processar_retomada_pendente')
    @patch('app.graph.router.processar_pergunta_pendente') 
    @patch('app.graph.router.detectar_sinais_vitais_no_texto')
    @patch('app.graph.router.classify_intent')
    @patch('app.graph.router.aplicar_gates_pos_classificacao')
    def test_route_fluxo_completo(
        self, mock_gates, mock_classify, mock_detect_vitals, 
        mock_pergunta, mock_retomada, mock_bootstrap
    ):
        """Testa fluxo completo do router"""
        estado = self.criar_estado_base()
        estado.texto_usuario = "quero finalizar"
        
        # Setup mocks
        mock_bootstrap.return_value = estado
        mock_retomada.return_value = None
        mock_pergunta.return_value = None
        mock_detect_vitals.return_value = None
        mock_classify.return_value = "finalizar"
        mock_gates.return_value = "finalizar"
        
        resultado = route(estado)
        
        assert resultado == "finalizar"
        assert estado.router.intencao == "finalizar"
        assert estado.router.ultimo_fluxo == "finalizar"
    
    @patch('app.graph.router.garantir_bootstrap_sessao')
    @patch('app.graph.router.processar_retomada_pendente')
    def test_route_com_retomada_prioritaria(self, mock_retomada, mock_bootstrap):
        """Testa router com retomada tendo prioridade"""
        estado = self.criar_estado_base()
        
        mock_bootstrap.return_value = estado
        mock_retomada.return_value = "clinical"  # Retomada tem prioridade
        
        resultado = route(estado)
        
        assert resultado == "clinical"
        # Não deve chamar outros processamentos
    
    def test_mapear_intencao_para_fluxo(self):
        """Testa mapeamento de intenções para fluxos"""
        from app.graph.router import mapear_intencao_para_fluxo
        
        mapeamentos = {
            "escala": "escala",
            "sinais_vitais": "clinical",
            "clinical": "clinical", 
            "notas": "notas",
            "finalizar": "finalizar",
            "auxiliar": "auxiliar",
            "desconhecido": "auxiliar"  # Fallback
        }
        
        for intencao, fluxo_esperado in mapeamentos.items():
            resultado = mapear_intencao_para_fluxo(intencao)
            assert resultado == fluxo_esperado
