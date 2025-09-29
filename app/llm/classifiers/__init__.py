"""
Classificadores LLM
==================

Módulo para classificação de diferentes tipos de entrada do usuário:
- Intent: Classifica intenções (escala, clinico, finalizar, etc.)
- Confirmation: Classifica confirmações (sim/não)
- Operational: Classifica notas operacionais instantâneas
"""

from .intent import IntentClassifier
from .confirmation import ConfirmationClassifier
from .operational import OperationalNoteClassifier

__all__ = [
    "IntentClassifier",
    "ConfirmationClassifier", 
    "OperationalNoteClassifier"
]
