"""
Extratores LLM
==============

Módulo para extração estruturada de dados:
- Clinical: Extrai sinais vitais, notas clínicas e condições respiratórias
- Finalizacao: Extrai tópicos de finalização de plantão
"""

from .clinical import ClinicalExtractor
from .finalizacao import FinalizacaoExtractor

__all__ = ["ClinicalExtractor", "FinalizacaoExtractor"]
