"""
LLM Package - Módulos de Inteligência Artificial
===============================================

Estrutura organizada por responsabilidade:

📋 CLASSIFIERS - Classificação de entrada do usuário
├── IntentClassifier: Classifica intenções (escala/clinico/finalizar/auxiliar)
├── ConfirmationClassifier: Classifica confirmações (sim/não)
└── OperationalNoteClassifier: Detecta notas operacionais instantâneas

🔍 EXTRACTORS - Extração estruturada de dados  
└── ClinicalExtractor: Extrai sinais vitais, notas e condições respiratórias

🎭 GENERATORS - Geração de conteúdo dinâmico
└── FiscalLLM: Gera respostas contextuais para o usuário

Todos os módulos usam OpenAI GPT-4o-mini com temperature=0 para determinismo.
"""

# Imports organizados por categoria
from .classifiers import IntentClassifier, ConfirmationClassifier, OperationalNoteClassifier
from .extractors import ClinicalExtractor
from .generators import FiscalLLM

__all__ = [
    # Classificadores
    "IntentClassifier",
    "ConfirmationClassifier", 
    "OperationalNoteClassifier",
    
    # Extratores
    "ClinicalExtractor",
    
    # Geradores
    "FiscalLLM"
]
