"""
Módulo RAG (Retrieval-Augmented Generation) para identificação de sintomas
"""
from .pinecone_client import (
    buscar_sintomas_similares,
    upsert_sintoma,
    upsert_sintomas_batch,
    obter_estatisticas_indice,
    testar_conexao
)

from .sheets_sync import (
    carregar_sintomas_do_sheets,
    sincronizar_com_pinecone,
    validar_estrutura_sheets,
    testar_conexao_sheets
)

__all__ = [
    "buscar_sintomas_similares",
    "upsert_sintoma", 
    "upsert_sintomas_batch",
    "obter_estatisticas_indice",
    "testar_conexao",
    "carregar_sintomas_do_sheets",
    "sincronizar_com_pinecone",
    "validar_estrutura_sheets",
    "testar_conexao_sheets"
]
