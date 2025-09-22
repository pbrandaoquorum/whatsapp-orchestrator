"""
Testes do subgrafo clínico
"""
import pytest
from unittest.mock import Mock

from app.graph.subgraphs.clinico import ClinicoSubgraph
from app.graph.state import GraphState
from app.llm.extractor import ClinicalExtractor


class TestClinicoSubgraph:
    """Testes do subgrafo clínico"""
    
    def test_extracao_llm_vitais_ok(self, mock_clinical_extractor, mock_rag_system, mock_http_client):
        """Testa extração LLM com vitais válidos"""
        subgraph = ClinicoSubgraph(
            clinical_extractor=mock_clinical_extractor,
            rag_system=mock_rag_system,
            http_client=mock_http_client,
            lambda_update_clinical_url="https://test.com/updateClinical"
        )
        
        state = GraphState()
        state.entrada["texto_usuario"] = "PA 120x80 FC 75 FR 18"
        state.sessao.update({
            "report_id": "report123",
            "data_relatorio": "2024-01-15",
            "schedule_id": "schedule123"
        })
        
        # Configura mock do extrator
        mock_clinical_extractor.extrair_json.return_value = {
            "vitals": {"PA": "120x80", "FC": 75, "FR": 18, "Sat": None, "Temp": None},
            "nota": None,
            "rawMentions": {"PA": "120x80", "FC": "75", "FR": "18"},
            "warnings": []
        }
        
        # Executa
        resultado = subgraph.processar(state)
        
        # Verifica extração
        assert state.clinico["vitais"]["PA"] == "120x80"
        assert state.clinico["vitais"]["FC"] == 75
        assert state.clinico["vitais"]["FR"] == 18
        assert state.clinico["faltantes"] == ["Sat", "Temp"]
        
        # Verifica que preparou confirmação
        assert state.tem_pendente()
        assert state.pendente["fluxo"] == "clinico"
        assert "Confirma salvar" in resultado
    
    def test_extracao_llm_com_nota_chama_rag(self, mock_clinical_extractor, mock_rag_system, mock_http_client):
        """Testa que nota clínica chama sistema RAG"""
        subgraph = ClinicoSubgraph(
            clinical_extractor=mock_clinical_extractor,
            rag_system=mock_rag_system,
            http_client=mock_http_client,
            lambda_update_clinical_url="https://test.com/updateClinical"
        )
        
        state = GraphState()
        state.entrada["texto_usuario"] = "PA 120x80 e paciente com tosse seca"
        state.sessao.update({
            "report_id": "report123",
            "data_relatorio": "2024-01-15"
        })
        
        # Configura mock do extrator
        mock_clinical_extractor.extrair_json.return_value = {
            "vitals": {"PA": "120x80", "FC": None, "FR": None, "Sat": None, "Temp": None},
            "nota": "paciente com tosse seca",
            "rawMentions": {"PA": "120x80"},
            "warnings": []
        }
        
        # Configura mock do RAG
        from app.graph.state import SymptomReport
        mock_symptom = SymptomReport(
            symptomDefinition="Tosse seca",
            altNotepadMain="paciente com tosse seca",
            symptomCategory="Respiratório",
            symptomSubCategory="Tosse",
            descricaoComparada="Identificado via RAG",
            coeficienteSimilaridade=0.85
        )
        mock_rag_system.processar_nota_clinica.return_value = [mock_symptom]
        
        # Executa
        resultado = subgraph.processar(state)
        
        # Verifica que RAG foi chamado
        mock_rag_system.processar_nota_clinica.assert_called_once_with("paciente com tosse seca")
        
        # Verifica que sintomas foram salvos
        assert len(state.clinico["sintomas"]) == 1
        assert state.clinico["sintomas"][0]["symptomDefinition"] == "Tosse seca"
        
        # Verifica nota
        assert state.clinico["nota"] == "paciente com tosse seca"
    
    def test_pa_ambigua_gera_warning(self, mock_clinical_extractor, mock_rag_system, mock_http_client):
        """Testa que PA ambígua gera warning e é marcada como null"""
        subgraph = ClinicoSubgraph(
            clinical_extractor=mock_clinical_extractor,
            rag_system=mock_rag_system,
            http_client=mock_http_client,
            lambda_update_clinical_url="https://test.com/updateClinical"
        )
        
        state = GraphState()
        state.entrada["texto_usuario"] = "PA 12/8 e febre"
        
        # Configura mock do extrator
        mock_clinical_extractor.extrair_json.return_value = {
            "vitals": {"PA": None, "FC": None, "FR": None, "Sat": None, "Temp": None},
            "nota": "febre",
            "rawMentions": {"PA": "12/8"},
            "warnings": ["PA_ambigua_12_8"]
        }
        
        # Executa
        resultado = subgraph.processar(state)
        
        # Verifica que PA foi marcada como null
        assert state.clinico["vitais"]["PA"] is None
        
        # Verifica que nota foi preservada
        assert state.clinico["nota"] == "febre"
    
    def test_valores_fora_faixa_sao_invalidados(self, mock_clinical_extractor, mock_rag_system, mock_http_client):
        """Testa validação de faixas plausíveis"""
        subgraph = ClinicoSubgraph(
            clinical_extractor=mock_clinical_extractor,
            rag_system=mock_rag_system,
            http_client=mock_http_client,
            lambda_update_clinical_url="https://test.com/updateClinical"
        )
        
        state = GraphState()
        state.entrada["texto_usuario"] = "FC 350 Temp 50"  # Valores fora da faixa
        
        # Configura mock do extrator
        mock_clinical_extractor.extrair_json.return_value = {
            "vitals": {"PA": None, "FC": 350, "FR": None, "Sat": None, "Temp": 50.0},
            "nota": None,
            "rawMentions": {"FC": "350", "Temp": "50"},
            "warnings": []
        }
        
        # Executa
        resultado = subgraph.processar(state)
        
        # Verifica que valores foram invalidados
        assert state.clinico["vitais"]["FC"] is None  # FC fora da faixa (20-220)
        assert state.clinico["vitais"]["Temp"] is None  # Temp fora da faixa (30-43)
    
    def test_confirmacao_sim_executa_salvamento(self, mock_clinical_extractor, mock_rag_system, mock_http_client):
        """Testa que confirmação 'sim' executa salvamento"""
        subgraph = ClinicoSubgraph(
            clinical_extractor=mock_clinical_extractor,
            rag_system=mock_rag_system,
            http_client=mock_http_client,
            lambda_update_clinical_url="https://test.com/updateClinical"
        )
        
        state = GraphState()
        state.entrada["texto_usuario"] = "sim"
        
        # Configura estado pendente
        state.pendente = {
            "fluxo": "clinico",
            "payload": {
                "reportID": "report123",
                "vitalSignsData": {"heartRate": 75}
            }
        }
        
        # Configura mock da resposta do Lambda
        mock_http_client.update_clinical_data.return_value = {
            "message": "Dados clínicos processados com sucesso"
        }
        
        # Executa
        resultado = subgraph.processar(state)
        
        # Verifica que Lambda foi chamado
        mock_http_client.update_clinical_data.assert_called_once()
        
        # Verifica que pendente foi limpo
        assert not state.tem_pendente()
        
        # Verifica resposta de sucesso
        assert "sucesso" in resultado
    
    def test_confirmacao_nao_cancela_salvamento(self, mock_clinical_extractor, mock_rag_system, mock_http_client):
        """Testa que confirmação 'não' cancela salvamento"""
        subgraph = ClinicoSubgraph(
            clinical_extractor=mock_clinical_extractor,
            rag_system=mock_rag_system,
            http_client=mock_http_client,
            lambda_update_clinical_url="https://test.com/updateClinical"
        )
        
        state = GraphState()
        state.entrada["texto_usuario"] = "não"
        
        # Configura estado pendente
        state.pendente = {
            "fluxo": "clinico",
            "payload": {"reportID": "report123"}
        }
        
        # Executa
        resultado = subgraph.processar(state)
        
        # Verifica que Lambda NÃO foi chamado
        mock_http_client.update_clinical_data.assert_not_called()
        
        # Verifica que pendente foi limpo
        assert not state.tem_pendente()
        
        # Verifica resposta de cancelamento
        assert "cancelado" in resultado
    
    def test_somente_nota_sem_vitais(self, mock_clinical_extractor, mock_rag_system, mock_http_client):
        """Testa processamento de apenas nota clínica sem vitais"""
        subgraph = ClinicoSubgraph(
            clinical_extractor=mock_clinical_extractor,
            rag_system=mock_rag_system,
            http_client=mock_http_client,
            lambda_update_clinical_url="https://test.com/updateClinical"
        )
        
        state = GraphState()
        state.entrada["texto_usuario"] = "Paciente apresenta dor abdominal"
        state.sessao.update({
            "report_id": "report123",
            "data_relatorio": "2024-01-15"
        })
        
        # Configura mock - apenas nota, sem vitais
        mock_clinical_extractor.extrair_json.return_value = {
            "vitals": {"PA": None, "FC": None, "FR": None, "Sat": None, "Temp": None},
            "nota": "Paciente apresenta dor abdominal",
            "rawMentions": {},
            "warnings": []
        }
        
        # Executa
        resultado = subgraph.processar(state)
        
        # Verifica que RAG foi chamado para a nota
        mock_rag_system.processar_nota_clinica.assert_called_once_with("Paciente apresenta dor abdominal")
        
        # Verifica que preparou confirmação mesmo sem vitais
        assert state.tem_pendente()
        assert "Confirma salvar" in resultado
        assert "Nota:" in resultado
