"""
Testes para o classificador semântico com LLM e LLM as a Judge
Cobre classificação de intenções, circuit breaker e fallbacks
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.graph.semantic_classifier import (
    classificar_semanticamente,
    validar_com_judge,
    _fallback_classificacao_deterministica,
    IntentType,
    ClassificationResult
)
from app.graph.state import GraphState, CoreState, VitalsState, NoteState
from app.infra.circuit_breaker import CircuitBreakerError


class TestSemanticClassifier:
    """Testes para classificação semântica"""
    
    @pytest.fixture
    def estado_exemplo(self):
        """Estado de exemplo para testes"""
        estado = GraphState()
        estado.core = CoreState(
            session_id="test_session",
            numero_telefone="+5511999999999",
            cancelado=False,
            turno_permitido=True
        )
        estado.vitals = VitalsState()
        estado.nota = NoteState()
        estado.metadados = {
            "presenca_confirmada": False,
            "sinais_vitais_realizados": False
        }
        return estado
    
    @pytest.mark.asyncio
    async def test_classificacao_confirmar_presenca(self, estado_exemplo):
        """Testa classificação de confirmação de presença"""
        with patch('app.graph.semantic_classifier._executar_classificacao_llm') as mock_llm:
            mock_llm.return_value = {
                "intent": "confirmar_presenca",
                "confidence": 0.9,
                "rationale": "Usuário confirmou chegada ao plantão",
                "vital_signs": None,
                "clinical_note": None
            }
            
            resultado = await classificar_semanticamente("Cheguei no plantão", estado_exemplo)
            
            assert resultado.intent == IntentType.CONFIRMAR_PRESENCA
            assert resultado.confidence == 0.9
            assert "confirmou chegada" in resultado.rationale
    
    @pytest.mark.asyncio
    async def test_classificacao_sinais_vitais(self, estado_exemplo):
        """Testa classificação e extração de sinais vitais"""
        with patch('app.graph.semantic_classifier._executar_classificacao_llm') as mock_llm:
            mock_llm.return_value = {
                "intent": "sinais_vitais",
                "confidence": 0.85,
                "rationale": "Sinais vitais detectados no texto",
                "vital_signs": {
                    "PA": "120x80",
                    "FC": 78,
                    "Temp": 36.5
                },
                "clinical_note": None
            }
            
            resultado = await classificar_semanticamente(
                "PA 120x80, FC 78 bpm, temperatura 36,5°C", 
                estado_exemplo
            )
            
            assert resultado.intent == IntentType.SINAIS_VITAIS
            assert resultado.vital_signs is not None
            assert resultado.vital_signs["PA"] == "120x80"
            assert resultado.vital_signs["FC"] == 78
            assert resultado.vital_signs["Temp"] == 36.5
    
    @pytest.mark.asyncio
    async def test_classificacao_nota_clinica(self, estado_exemplo):
        """Testa classificação de nota clínica"""
        with patch('app.graph.semantic_classifier._executar_classificacao_llm') as mock_llm:
            mock_llm.return_value = {
                "intent": "nota_clinica",
                "confidence": 0.8,
                "rationale": "Texto identificado como observação clínica",
                "vital_signs": None,
                "clinical_note": "Paciente consciente e orientado, sem queixas"
            }
            
            resultado = await classificar_semanticamente(
                "Paciente consciente e orientado, sem queixas", 
                estado_exemplo
            )
            
            assert resultado.intent == IntentType.NOTA_CLINICA
            assert resultado.clinical_note == "Paciente consciente e orientado, sem queixas"
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_fallback(self, estado_exemplo):
        """Testa fallback quando circuit breaker está aberto"""
        with patch('app.graph.semantic_classifier._executar_classificacao_llm') as mock_llm:
            mock_llm.side_effect = CircuitBreakerError("Circuit breaker aberto")
            
            resultado = await classificar_semanticamente("cheguei", estado_exemplo)
            
            # Deve usar fallback determinístico
            assert resultado.intent == IntentType.CONFIRMAR_PRESENCA
            assert resultado.confidence == 0.7
            assert "Fallback determinístico" in resultado.rationale
    
    @pytest.mark.asyncio
    async def test_llm_as_judge_validacao(self, estado_exemplo):
        """Testa validação com LLM as a Judge"""
        classificacao_original = {
            "intent": "indefinido",
            "confidence": 0.4,
            "rationale": "Não consegui classificar com certeza"
        }
        
        resultado_original = ClassificationResult(
            intent=IntentType.INDEFINIDO,
            confidence=0.4,
            rationale="Não consegui classificar com certeza"
        )
        
        with patch('app.graph.semantic_classifier._executar_validacao_judge') as mock_judge:
            mock_judge.return_value = {
                "is_valid": False,
                "confidence": 0.9,
                "corrections": {
                    "intent": "confirmar_presenca",
                    "confidence": 0.8
                },
                "rationale": "Texto claramente indica confirmação de presença"
            }
            
            resultado_validado = await validar_com_judge(
                "cheguei",
                classificacao_original,
                estado_exemplo,
                resultado_original
            )
            
            assert resultado_validado.intent == IntentType.CONFIRMAR_PRESENCA
            assert resultado_validado.confidence == 0.8
            assert "Judge:" in resultado_validado.rationale
    
    @pytest.mark.asyncio
    async def test_fallback_determinístico_sinais_vitais(self, estado_exemplo):
        """Testa fallback determinístico para sinais vitais"""
        with patch('app.graph.clinical_extractor.extrair_sinais_vitais') as mock_extractor:
            mock_extractor.return_value = MagicMock()
            mock_extractor.return_value.processados = {
                "PA": "130x90",
                "FC": 82
            }
            
            resultado = await _fallback_classificacao_deterministica(
                "PA 130x90 FC 82", 
                estado_exemplo
            )
            
            assert resultado.intent == IntentType.SINAIS_VITAIS
            assert resultado.confidence == 0.8
            assert resultado.vital_signs is not None
    
    @pytest.mark.asyncio
    async def test_fallback_determinístico_texto_longo(self, estado_exemplo):
        """Testa fallback para texto longo como nota clínica"""
        texto_longo = "Paciente apresenta quadro estável, sinais vitais dentro da normalidade"
        
        resultado = await _fallback_classificacao_deterministica(texto_longo, estado_exemplo)
        
        assert resultado.intent == IntentType.NOTA_CLINICA
        assert resultado.confidence == 0.5
        assert resultado.clinical_note == texto_longo
    
    @pytest.mark.asyncio
    async def test_classificacao_texto_vazio(self, estado_exemplo):
        """Testa comportamento com texto vazio"""
        resultado = await classificar_semanticamente("", estado_exemplo)
        
        assert resultado.intent == IntentType.INDEFINIDO
        assert resultado.confidence == 0.0
        assert "vazio" in resultado.rationale.lower()
    
    @pytest.mark.asyncio
    async def test_judge_circuit_breaker_aberto(self, estado_exemplo):
        """Testa comportamento quando circuit breaker do Judge está aberto"""
        classificacao_original = {
            "intent": "confirmar_presenca",
            "confidence": 0.7,
            "rationale": "Confirmação detectada"
        }
        
        resultado_original = ClassificationResult(
            intent=IntentType.CONFIRMAR_PRESENCA,
            confidence=0.7,
            rationale="Confirmação detectada"
        )
        
        with patch('app.graph.semantic_classifier._executar_validacao_judge') as mock_judge:
            mock_judge.side_effect = CircuitBreakerError("Circuit breaker Judge aberto")
            
            resultado_validado = await validar_com_judge(
                "cheguei",
                classificacao_original,
                estado_exemplo,
                resultado_original
            )
            
            # Deve retornar resultado original sem alterações
            assert resultado_validado.intent == IntentType.CONFIRMAR_PRESENCA
            assert resultado_validado.confidence == 0.7
            assert resultado_validado.rationale == "Confirmação detectada"


class TestSemanticClassifierIntegration:
    """Testes de integração do classificador semântico"""
    
    @pytest.fixture
    def estado_completo(self):
        """Estado completo para testes de integração"""
        estado = GraphState()
        estado.core = CoreState(
            session_id="integration_test",
            numero_telefone="+5511888888888",
            caregiver_id="caregiver123",
            schedule_id="schedule456",
            patient_id="patient789",
            report_id="report101",
            cancelado=False,
            turno_permitido=True
        )
        estado.vitals = VitalsState(
            processados={"PA": "120x80", "FC": 75},
            faltantes=["FR", "Sat", "Temp"]
        )
        estado.nota = NoteState()
        estado.metadados = {
            "presenca_confirmada": True,
            "sinais_vitais_realizados": False
        }
        return estado
    
    @pytest.mark.asyncio
    async def test_fluxo_completo_confirmacao(self, estado_completo):
        """Testa fluxo completo de confirmação com contexto"""
        estado_completo.metadados["presenca_confirmada"] = False
        
        with patch('app.graph.semantic_classifier._executar_classificacao_llm') as mock_llm:
            mock_llm.return_value = {
                "intent": "confirmar_presenca",
                "confidence": 0.9,
                "rationale": "Confirmação clara considerando contexto",
                "vital_signs": None,
                "clinical_note": None
            }
            
            resultado = await classificar_semanticamente("sim, confirmo", estado_completo)
            
            assert resultado.intent == IntentType.CONFIRMAR_PRESENCA
            assert resultado.confidence == 0.9
    
    @pytest.mark.asyncio
    async def test_contexto_influencia_classificacao(self, estado_completo):
        """Testa se contexto do estado influencia classificação"""
        # Estado com presença já confirmada
        estado_completo.metadados["presenca_confirmada"] = True
        
        with patch('app.graph.semantic_classifier._executar_classificacao_llm') as mock_llm:
            # Função que simula LLM considerando contexto
            def mock_llm_context(texto, estado):
                if estado.metadados.get("presenca_confirmada"):
                    return {
                        "intent": "sinais_vitais",
                        "confidence": 0.8,
                        "rationale": "Presença já confirmada, provavelmente sinais vitais",
                        "vital_signs": {"PA": "130x85"},
                        "clinical_note": None
                    }
                else:
                    return {
                        "intent": "confirmar_presenca",
                        "confidence": 0.8,
                        "rationale": "Presença ainda não confirmada",
                        "vital_signs": None,
                        "clinical_note": None
                    }
            
            mock_llm.side_effect = lambda texto, estado: mock_llm_context(texto, estado)
            
            resultado = await classificar_semanticamente("130x85", estado_completo)
            
            assert resultado.intent == IntentType.SINAIS_VITAIS
            assert resultado.vital_signs is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
