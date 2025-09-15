"""
Testes para o extrator clínico determinístico
"""
import pytest
from app.graph.clinical_extractor import (
    extrair_sinais_vitais, extrair_pressao_arterial, extrair_frequencia_cardiaca,
    extrair_frequencia_respiratoria, extrair_saturacao, extrair_temperatura,
    validar_sinais_vitais_completos, gerar_resumo_sinais_vitais
)


class TestClinicalExtractor:
    """Testes do extrator clínico"""
    
    def test_extrair_pressao_arterial_formato_x(self):
        """Testa extração de PA no formato com x"""
        resultado = extrair_pressao_arterial("PA 120x80")
        assert resultado == {"PA": "120x80"}
        
        resultado = extrair_pressao_arterial("pressão 130x85")
        assert resultado == {"PA": "130x85"}
    
    def test_extrair_pressao_arterial_formato_barra(self):
        """Testa extração de PA no formato com barra"""
        resultado = extrair_pressao_arterial("PA 120/80")
        assert resultado == {"PA": "120x80"}  # Normaliza para x
    
    def test_extrair_frequencia_cardiaca(self):
        """Testa extração de frequência cardíaca"""
        resultado = extrair_frequencia_cardiaca("FC 78")
        assert resultado == {"FC": 78}
        
        resultado = extrair_frequencia_cardiaca("78 bpm")
        assert resultado == {"FC": 78}
        
        resultado = extrair_frequencia_cardiaca("frequencia cardiaca 85")
        assert resultado == {"FC": 85}
    
    def test_extrair_frequencia_respiratoria(self):
        """Testa extração de frequência respiratória"""
        resultado = extrair_frequencia_respiratoria("FR 18")
        assert resultado == {"FR": 18}
        
        resultado = extrair_frequencia_respiratoria("18 irpm")
        assert resultado == {"FR": 18}
    
    def test_extrair_saturacao(self):
        """Testa extração de saturação"""
        resultado = extrair_saturacao("Sat 97")
        assert resultado == {"Sat": 97}
        
        resultado = extrair_saturacao("97%")
        assert resultado == {"Sat": 97}
        
        resultado = extrair_saturacao("saturacao 95")
        assert resultado == {"Sat": 95}
    
    def test_extrair_temperatura(self):
        """Testa extração de temperatura"""
        resultado = extrair_temperatura("Temp 36.5")
        assert resultado == {"Temp": 36.5}
        
        resultado = extrair_temperatura("36,8°C")
        assert resultado == {"Temp": 36.8}
        
        resultado = extrair_temperatura("temperatura 37.2")
        assert resultado == {"Temp": 37.2}
    
    def test_extrair_sinais_vitais_completo(self):
        """Testa extração de todos os sinais vitais de uma vez"""
        texto = "PA 120x80, FC 78 bpm, FR 18 irpm, Sat 97%, Temp 36.5°C"
        
        resultado = extrair_sinais_vitais(texto)
        
        assert len(resultado.processados) == 5
        assert resultado.processados["PA"] == "120x80"
        assert resultado.processados["FC"] == 78
        assert resultado.processados["FR"] == 18
        assert resultado.processados["Sat"] == 97
        assert resultado.processados["Temp"] == 36.5
        assert len(resultado.faltantes) == 0
    
    def test_extrair_sinais_vitais_parcial(self):
        """Testa extração parcial de sinais vitais"""
        texto = "PA 130x90, FC 82"
        
        resultado = extrair_sinais_vitais(texto)
        
        assert len(resultado.processados) == 2
        assert resultado.processados["PA"] == "130x90"
        assert resultado.processados["FC"] == 82
        assert len(resultado.faltantes) == 3
        assert "FR" in resultado.faltantes
        assert "Sat" in resultado.faltantes
        assert "Temp" in resultado.faltantes
    
    def test_extrair_sinais_vitais_texto_vazio(self):
        """Testa extração com texto vazio"""
        resultado = extrair_sinais_vitais("")
        
        assert len(resultado.processados) == 0
        assert len(resultado.faltantes) == 5
    
    def test_extrair_sinais_vitais_texto_sem_sinais(self):
        """Testa extração com texto que não contém sinais vitais"""
        texto = "Paciente consciente e orientado, sem queixas"
        
        resultado = extrair_sinais_vitais(texto)
        
        assert len(resultado.processados) == 0
        assert len(resultado.faltantes) == 5
    
    def test_validar_sinais_vitais_completos_true(self):
        """Testa validação com todos os sinais presentes"""
        dados = {
            "PA": "120x80",
            "FC": 78,
            "FR": 18,
            "Sat": 97,
            "Temp": 36.5
        }
        
        assert validar_sinais_vitais_completos(dados) is True
    
    def test_validar_sinais_vitais_completos_false(self):
        """Testa validação com sinais faltantes"""
        dados = {
            "PA": "120x80",
            "FC": 78
        }
        
        assert validar_sinais_vitais_completos(dados) is False
    
    def test_gerar_resumo_sinais_vitais(self):
        """Testa geração de resumo dos sinais vitais"""
        dados = {
            "PA": "120x80",
            "FC": 78,
            "FR": 18,
            "Sat": 97,
            "Temp": 36.5
        }
        
        resumo = gerar_resumo_sinais_vitais(dados)
        
        assert "PA: 120x80" in resumo
        assert "FC: 78 bpm" in resumo
        assert "FR: 18 irpm" in resumo
        assert "Sat: 97%" in resumo
        assert "Temp: 36.5°C" in resumo
    
    def test_gerar_resumo_sinais_vitais_vazio(self):
        """Testa geração de resumo com dados vazios"""
        resumo = gerar_resumo_sinais_vitais({})
        assert resumo == "Nenhum sinal vital informado"
    
    def test_extrair_sinais_vitais_formato_brasileiro(self):
        """Testa extração com formatos típicos brasileiros"""
        textos_teste = [
            "pressão 12 por 8, pulso 80",
            "PA: 140x90, FC: 75, saturação 96%",
            "Sinais vitais: PA=120x80 FC=78 FR=16 Sat=98% T=36.8",
            "Paciente com PA 110x70, FC 65 bpm, FR 14 irpm, Sat 99%, Temp 36.2°C"
        ]
        
        for texto in textos_teste:
            resultado = extrair_sinais_vitais(texto)
            # Pelo menos alguns sinais devem ser extraídos
            assert len(resultado.processados) > 0
    
    def test_validacao_ranges_sinais_vitais(self):
        """Testa se validações de range estão funcionando"""
        # Valores fora do range devem ser rejeitados
        
        # FC muito baixa
        resultado = extrair_frequencia_cardiaca("FC 30")
        assert "FC" not in resultado
        
        # FC muito alta  
        resultado = extrair_frequencia_cardiaca("FC 250")
        assert "FC" not in resultado
        
        # Temperatura muito baixa
        resultado = extrair_temperatura("Temp 25.0")
        assert "Temp" not in resultado
        
        # Temperatura muito alta
        resultado = extrair_temperatura("Temp 50.0")
        assert "Temp" not in resultado
