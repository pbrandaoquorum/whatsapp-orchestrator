"""
Extratores LLM
==============

Módulo para extração estruturada de dados:
- Clinical: Extrai sinais vitais, notas clínicas e condições respiratórias
"""

from .clinical import ClinicalExtractor

__all__ = ["ClinicalExtractor"]
