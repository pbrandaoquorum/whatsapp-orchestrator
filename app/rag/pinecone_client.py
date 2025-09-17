"""
Cliente Pinecone para busca de sintomas similares
Implementa busca vetorial e conversão para SymptomReport
"""
import os
from typing import List, Dict, Any, Optional
import pinecone
from pinecone import Pinecone, ServerlessSpec
from sentence_transformers import SentenceTransformer
from app.infra.logging import obter_logger
# from app.infra.cache import rag_cache  # Módulo não encontrado
from app.infra.circuit_breaker import circuit_breaker, PINECONE_CIRCUIT_CONFIG, CircuitBreakerError

logger = obter_logger(__name__)

# Configurações do Pinecone
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_ENV = os.getenv("PINECONE_ENV", "us-east-1-aws")
PINECONE_INDEX = os.getenv("PINECONE_INDEX", "sintomas-index")

# Modelo para embeddings (pode ser configurado via env)
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")

# Cache global do modelo de embeddings
_embedding_model = None
_pinecone_client = None
_index = None


def obter_modelo_embeddings():
    """Obtém modelo de embeddings (singleton)"""
    global _embedding_model
    
    if _embedding_model is None:
        logger.info(f"Carregando modelo de embeddings: {EMBEDDING_MODEL}")
        _embedding_model = SentenceTransformer(EMBEDDING_MODEL)
        logger.info("Modelo de embeddings carregado com sucesso")
    
    return _embedding_model


def obter_cliente_pinecone():
    """Obtém cliente Pinecone (singleton)"""
    global _pinecone_client
    
    if _pinecone_client is None:
        if not PINECONE_API_KEY:
            raise ValueError("PINECONE_API_KEY não configurado")
        
        logger.info("Inicializando cliente Pinecone")
        _pinecone_client = Pinecone(api_key=PINECONE_API_KEY)
        logger.info("Cliente Pinecone inicializado")
    
    return _pinecone_client


def obter_indice_pinecone():
    """Obtém índice Pinecone (singleton)"""
    global _index
    
    if _index is None:
        client = obter_cliente_pinecone()
        
        # Verificar se índice existe
        indices_existentes = client.list_indexes()
        nomes_indices = [idx.name for idx in indices_existentes.indexes]
        
        if PINECONE_INDEX not in nomes_indices:
            logger.warning(f"Índice {PINECONE_INDEX} não existe. Criando...")
            criar_indice_se_nao_existir()
        
        _index = client.Index(PINECONE_INDEX)
        logger.info(f"Conectado ao índice: {PINECONE_INDEX}")
    
    return _index


def criar_indice_se_nao_existir():
    """Cria índice Pinecone se não existir"""
    client = obter_cliente_pinecone()
    
    # Dimensão do modelo de embeddings (384 para MiniLM-L12-v2)
    dimensao = 384
    
    logger.info(f"Criando índice {PINECONE_INDEX} com dimensão {dimensao}")
    
    client.create_index(
        name=PINECONE_INDEX,
        dimension=dimensao,
        metric="cosine",
        spec=ServerlessSpec(
            cloud="aws",
            region=PINECONE_ENV.split("-")[0] + "-" + PINECONE_ENV.split("-")[1] + "-1"
        )
    )
    
    logger.info(f"Índice {PINECONE_INDEX} criado com sucesso")


def gerar_embedding(texto: str) -> List[float]:
    """Gera embedding para texto usando SentenceTransformer"""
    if not texto or not texto.strip():
        return []
    
    modelo = obter_modelo_embeddings()
    
    try:
        # Normalizar texto
        texto_limpo = texto.strip().lower()
        
        # Gerar embedding
        embedding = modelo.encode([texto_limpo])[0]
        
        # Converter para lista de floats
        return embedding.tolist()
        
    except Exception as e:
        logger.error(f"Erro ao gerar embedding para '{texto[:50]}': {e}")
        return []


# @rag_cache(ttl=3600)  # Cache por 1 hora - módulo não encontrado
@circuit_breaker("pinecone_query", PINECONE_CIRCUIT_CONFIG)
async def _executar_consulta_pinecone(embedding: List[float], k: int, limiar_score: float) -> List[Dict[str, Any]]:
    """Executa consulta no Pinecone com circuit breaker"""
    try:
        index = obter_index_pinecone()
        
        resultado = index.query(
            vector=embedding,
            top_k=k,
            include_metadata=True,
            include_values=False
        )
        
        # Filtrar por limiar de similaridade
        matches_filtrados = [
            match for match in resultado.matches 
            if match.score >= limiar_score
        ]
        
        return matches_filtrados
        
    except Exception as e:
        logger.error(f"Erro na consulta Pinecone: {e}")
        raise


def buscar_sintomas_similares(
    termo_busca: str,
    k: int = 5,
    limiar_score: float = 0.7,
    incluir_metadata: bool = True
) -> List[Dict[str, Any]]:
    """
    Busca sintomas similares no Pinecone
    
    Args:
        termo_busca: Termo para buscar sintomas similares
        k: Número máximo de resultados
        limiar_score: Score mínimo para considerar resultado relevante
        incluir_metadata: Se deve incluir metadados na resposta
    
    Returns:
        Lista de sintomas similares com scores e metadados
    """
    if not termo_busca or not termo_busca.strip():
        logger.warning("Termo de busca vazio")
        return []
    
    try:
        # Gerar embedding do termo de busca
        embedding_busca = gerar_embedding(termo_busca)
        
        if not embedding_busca:
            logger.error("Não foi possível gerar embedding para o termo de busca")
            return []
        
        # Usar função protegida por circuit breaker
        import asyncio
        matches_filtrados = asyncio.run(_executar_consulta_pinecone(embedding_busca, k, limiar_score))
        
        # Processar resultados
        sintomas_encontrados = []
        
        for match in matches_filtrados:
            score = float(match.score)
            
            # Filtrar por limiar de score
            if score < limiar_score:
                continue
            
            # Extrair dados do match
            sintoma_data = {
                "id": match.id,
                "score": score,
                "sintoma": match.metadata.get("sintoma", "") if match.metadata else "",
                "categoria": match.metadata.get("categoria", "Geral") if match.metadata else "Geral",
                "subcategoria": match.metadata.get("subcategoria", "Geral") if match.metadata else "Geral",
                "descricao": match.metadata.get("descricao", "") if match.metadata else "",
                "pontuacao": match.metadata.get("pontuacao", 0) if match.metadata else 0
            }
            
            sintomas_encontrados.append(sintoma_data)
        
        logger.info(
            f"Busca por '{termo_busca}' retornou {len(sintomas_encontrados)} resultados",
            termo=termo_busca,
            resultados=len(sintomas_encontrados),
            score_min=min([s["score"] for s in sintomas_encontrados]) if sintomas_encontrados else 0,
            score_max=max([s["score"] for s in sintomas_encontrados]) if sintomas_encontrados else 0
        )
        
        return sintomas_encontrados
        
    except Exception as e:
        logger.error(f"Erro na busca Pinecone para '{termo_busca}': {e}")
        return []


def upsert_sintoma(
    sintoma_id: str,
    sintoma_texto: str,
    metadata: Dict[str, Any]
) -> bool:
    """
    Insere ou atualiza um sintoma no índice Pinecone
    
    Args:
        sintoma_id: ID único do sintoma
        sintoma_texto: Texto do sintoma para gerar embedding
        metadata: Metadados do sintoma (categoria, pontuação, etc.)
    
    Returns:
        True se sucesso, False se erro
    """
    try:
        # Gerar embedding
        embedding = gerar_embedding(sintoma_texto)
        
        if not embedding:
            logger.error(f"Não foi possível gerar embedding para sintoma '{sintoma_texto}'")
            return False
        
        # Obter índice
        index = obter_indice_pinecone()
        
        # Preparar dados para upsert
        vector_data = {
            "id": sintoma_id,
            "values": embedding,
            "metadata": metadata
        }
        
        # Fazer upsert
        index.upsert([vector_data])
        
        logger.info(f"Sintoma '{sintoma_texto}' inserido/atualizado com sucesso", id=sintoma_id)
        return True
        
    except Exception as e:
        logger.error(f"Erro ao inserir sintoma '{sintoma_texto}': {e}")
        return False


def upsert_sintomas_batch(sintomas: List[Dict[str, Any]]) -> int:
    """
    Insere ou atualiza múltiplos sintomas em batch
    
    Args:
        sintomas: Lista de dicts com 'id', 'texto', 'metadata'
    
    Returns:
        Número de sintomas inseridos com sucesso
    """
    if not sintomas:
        return 0
    
    sucesso = 0
    batch_size = 100  # Limite do Pinecone para batch upsert
    
    try:
        index = obter_indice_pinecone()
        
        # Processar em batches
        for i in range(0, len(sintomas), batch_size):
            batch = sintomas[i:i + batch_size]
            vectors_batch = []
            
            for sintoma in batch:
                embedding = gerar_embedding(sintoma.get("texto", ""))
                
                if embedding:
                    vector_data = {
                        "id": sintoma.get("id"),
                        "values": embedding,
                        "metadata": sintoma.get("metadata", {})
                    }
                    vectors_batch.append(vector_data)
            
            if vectors_batch:
                index.upsert(vectors_batch)
                sucesso += len(vectors_batch)
                
                logger.info(
                    f"Batch {i//batch_size + 1} inserido",
                    batch_size=len(vectors_batch),
                    total_sucesso=sucesso
                )
        
        logger.info(f"Upsert em batch concluído: {sucesso}/{len(sintomas)} sintomas")
        return sucesso
        
    except Exception as e:
        logger.error(f"Erro no upsert em batch: {e}")
        return sucesso


def deletar_sintoma(sintoma_id: str) -> bool:
    """Deleta um sintoma do índice"""
    try:
        index = obter_indice_pinecone()
        index.delete(ids=[sintoma_id])
        
        logger.info(f"Sintoma deletado", id=sintoma_id)
        return True
        
    except Exception as e:
        logger.error(f"Erro ao deletar sintoma {sintoma_id}: {e}")
        return False


def obter_estatisticas_indice() -> Dict[str, Any]:
    """Obtém estatísticas do índice Pinecone"""
    try:
        index = obter_indice_pinecone()
        stats = index.describe_index_stats()
        
        return {
            "total_vectors": stats.total_vector_count,
            "dimensao": stats.dimension,
            "indice_cheio": stats.index_fullness,
            "namespaces": dict(stats.namespaces) if stats.namespaces else {}
        }
        
    except Exception as e:
        logger.error(f"Erro ao obter estatísticas do índice: {e}")
        return {}


def testar_conexao() -> bool:
    """Testa conexão com Pinecone"""
    try:
        stats = obter_estatisticas_indice()
        logger.info("Conexão Pinecone testada com sucesso", stats=stats)
        return True
        
    except Exception as e:
        logger.error(f"Erro na conexão Pinecone: {e}")
        return False
