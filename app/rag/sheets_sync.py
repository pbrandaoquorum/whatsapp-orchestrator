"""
Sincronização com Google Sheets para base de sintomas
Carrega dados do Sheets e sincroniza com Pinecone
"""
import os
import re
from typing import List, Dict, Any, Optional
import gspread
from google.oauth2.service_account import Credentials
from app.rag.pinecone_client import upsert_sintomas_batch, obter_estatisticas_indice
from app.infra.logging import obter_logger
from app.infra.timeutils import agora_br_iso

logger = obter_logger(__name__)

# Configurações do Google Sheets
GOOGLE_SHEETS_ID = os.getenv("GOOGLE_SHEETS_ID")
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")

# Scopes necessários para Google Sheets
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly"
]

# Cache global do cliente
_sheets_client = None


def obter_cliente_sheets():
    """Obtém cliente Google Sheets (singleton)"""
    global _sheets_client
    
    if _sheets_client is None:
        if not GOOGLE_SERVICE_ACCOUNT_JSON:
            raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON não configurado")
        
        if not os.path.exists(GOOGLE_SERVICE_ACCOUNT_JSON):
            raise FileNotFoundError(f"Arquivo de credenciais não encontrado: {GOOGLE_SERVICE_ACCOUNT_JSON}")
        
        logger.info("Inicializando cliente Google Sheets")
        
        # Carregar credenciais
        creds = Credentials.from_service_account_file(
            GOOGLE_SERVICE_ACCOUNT_JSON,
            scopes=SCOPES
        )
        
        # Criar cliente
        _sheets_client = gspread.authorize(creds)
        
        logger.info("Cliente Google Sheets inicializado")
    
    return _sheets_client


def carregar_sintomas_do_sheets(
    sheets_id: Optional[str] = None,
    nome_aba: str = "Sintomas",
    colunas_esperadas: List[str] = ["sintoma", "pontuacao"]
) -> List[Dict[str, Any]]:
    """
    Carrega sintomas do Google Sheets
    
    Args:
        sheets_id: ID da planilha (usa GOOGLE_SHEETS_ID se None)
        nome_aba: Nome da aba/worksheet
        colunas_esperadas: Colunas esperadas na planilha
    
    Returns:
        Lista de sintomas com metadados
    """
    sheets_id = sheets_id or GOOGLE_SHEETS_ID
    
    if not sheets_id:
        raise ValueError("ID da planilha não fornecido")
    
    try:
        # Obter cliente
        client = obter_cliente_sheets()
        
        # Abrir planilha
        logger.info(f"Abrindo planilha: {sheets_id}")
        planilha = client.open_by_key(sheets_id)
        
        # Obter worksheet
        try:
            worksheet = planilha.worksheet(nome_aba)
        except gspread.WorksheetNotFound:
            # Tentar primeira aba se a especificada não existir
            worksheet = planilha.get_worksheet(0)
            logger.warning(f"Aba '{nome_aba}' não encontrada, usando primeira aba: {worksheet.title}")
        
        # Obter todos os dados
        dados_brutos = worksheet.get_all_records()
        
        logger.info(f"Carregados {len(dados_brutos)} registros do Sheets")
        
        # Processar dados
        sintomas_processados = []
        
        for i, linha in enumerate(dados_brutos, start=2):  # Linha 2 é a primeira com dados
            try:
                sintoma_processado = processar_linha_sintoma(linha, i)
                if sintoma_processado:
                    sintomas_processados.append(sintoma_processado)
                    
            except Exception as e:
                logger.error(f"Erro ao processar linha {i}: {e}", linha=linha)
                continue
        
        logger.info(f"Processados {len(sintomas_processados)} sintomas válidos")
        return sintomas_processados
        
    except Exception as e:
        logger.error(f"Erro ao carregar sintomas do Sheets: {e}")
        raise


def processar_linha_sintoma(linha: Dict[str, Any], numero_linha: int) -> Optional[Dict[str, Any]]:
    """
    Processa uma linha do Sheets e converte para formato padrão
    
    Args:
        linha: Dados da linha como dict
        numero_linha: Número da linha para logging
    
    Returns:
        Dict com dados processados ou None se inválida
    """
    # Mapear possíveis nomes de colunas (case insensitive)
    mapeamento_colunas = {
        "sintoma": ["sintoma", "symptom", "descricao", "description", "texto"],
        "pontuacao": ["pontuacao", "pontuação", "score", "rating", "peso", "weight"],
        "categoria": ["categoria", "category", "tipo", "type", "grupo", "group"],
        "subcategoria": ["subcategoria", "subcategory", "subtipo", "subtype"]
    }
    
    # Normalizar chaves (lowercase, sem espaços)
    linha_normalizada = {
        re.sub(r'[^\w]', '', k.lower()): v 
        for k, v in linha.items()
    }
    
    # Extrair campos
    sintoma_texto = None
    pontuacao = 0
    categoria = "Geral"
    subcategoria = "Geral"
    
    # Buscar sintoma
    for campo_sintoma in mapeamento_colunas["sintoma"]:
        if campo_sintoma in linha_normalizada:
            sintoma_texto = str(linha_normalizada[campo_sintoma]).strip()
            break
    
    # Buscar pontuação
    for campo_pontuacao in mapeamento_colunas["pontuacao"]:
        if campo_pontuacao in linha_normalizada:
            try:
                pontuacao = float(linha_normalizada[campo_pontuacao])
            except (ValueError, TypeError):
                pontuacao = 0
            break
    
    # Buscar categoria
    for campo_categoria in mapeamento_colunas["categoria"]:
        if campo_categoria in linha_normalizada:
            categoria = str(linha_normalizada[campo_categoria]).strip() or "Geral"
            break
    
    # Buscar subcategoria
    for campo_subcategoria in mapeamento_colunas["subcategoria"]:
        if campo_subcategoria in linha_normalizada:
            subcategoria = str(linha_normalizada[campo_subcategoria]).strip() or "Geral"
            break
    
    # Validar dados essenciais
    if not sintoma_texto or len(sintoma_texto) < 3:
        logger.warning(f"Linha {numero_linha}: sintoma inválido ou muito curto", sintoma=sintoma_texto)
        return None
    
    # Gerar ID único
    sintoma_id = gerar_id_sintoma(sintoma_texto, numero_linha)
    
    # Montar resultado
    resultado = {
        "id": sintoma_id,
        "texto": sintoma_texto,
        "metadata": {
            "sintoma": sintoma_texto,
            "pontuacao": pontuacao,
            "categoria": categoria,
            "subcategoria": subcategoria,
            "linha_sheets": numero_linha,
            "data_sync": agora_br_iso()
        }
    }
    
    return resultado


def gerar_id_sintoma(sintoma_texto: str, numero_linha: int) -> str:
    """Gera ID único para o sintoma"""
    # Normalizar texto para ID
    texto_normalizado = re.sub(r'[^\w\s]', '', sintoma_texto.lower())
    texto_normalizado = re.sub(r'\s+', '_', texto_normalizado.strip())
    
    # Truncar se muito longo
    if len(texto_normalizado) > 50:
        texto_normalizado = texto_normalizado[:50]
    
    # Adicionar sufixo da linha para garantir unicidade
    return f"sintoma_{texto_normalizado}_{numero_linha}"


def sincronizar_com_pinecone(
    sheets_id: Optional[str] = None,
    nome_aba: str = "Sintomas",
    batch_size: int = 100
) -> Dict[str, Any]:
    """
    Sincroniza dados do Google Sheets com Pinecone
    
    Args:
        sheets_id: ID da planilha
        nome_aba: Nome da aba
        batch_size: Tamanho do batch para upsert
    
    Returns:
        Estatísticas da sincronização
    """
    logger.info("Iniciando sincronização Sheets -> Pinecone")
    
    try:
        # Obter estatísticas antes
        stats_antes = obter_estatisticas_indice()
        vectors_antes = stats_antes.get("total_vectors", 0)
        
        # Carregar dados do Sheets
        sintomas = carregar_sintomas_do_sheets(sheets_id, nome_aba)
        
        if not sintomas:
            logger.warning("Nenhum sintoma válido encontrado no Sheets")
            return {
                "sucesso": False,
                "erro": "Nenhum sintoma válido encontrado",
                "sintomas_processados": 0
            }
        
        # Sincronizar com Pinecone
        logger.info(f"Sincronizando {len(sintomas)} sintomas com Pinecone")
        sintomas_inseridos = upsert_sintomas_batch(sintomas)
        
        # Obter estatísticas depois
        stats_depois = obter_estatisticas_indice()
        vectors_depois = stats_depois.get("total_vectors", 0)
        
        # Montar resultado
        resultado = {
            "sucesso": True,
            "sintomas_carregados": len(sintomas),
            "sintomas_inseridos": sintomas_inseridos,
            "vectors_antes": vectors_antes,
            "vectors_depois": vectors_depois,
            "data_sync": agora_br_iso(),
            "sheets_id": sheets_id or GOOGLE_SHEETS_ID,
            "aba": nome_aba
        }
        
        logger.info(
            "Sincronização concluída com sucesso",
            **{k: v for k, v in resultado.items() if k != "sheets_id"}
        )
        
        return resultado
        
    except Exception as e:
        logger.error(f"Erro na sincronização: {e}")
        return {
            "sucesso": False,
            "erro": str(e),
            "data_sync": agora_br_iso()
        }


def validar_estrutura_sheets(
    sheets_id: Optional[str] = None,
    nome_aba: str = "Sintomas"
) -> Dict[str, Any]:
    """
    Valida estrutura da planilha Google Sheets
    
    Returns:
        Informações sobre a estrutura e possíveis problemas
    """
    sheets_id = sheets_id or GOOGLE_SHEETS_ID
    
    try:
        client = obter_cliente_sheets()
        planilha = client.open_by_key(sheets_id)
        
        # Listar todas as abas
        abas_disponiveis = [ws.title for ws in planilha.worksheets()]
        
        # Verificar se aba existe
        if nome_aba not in abas_disponiveis:
            return {
                "valido": False,
                "erro": f"Aba '{nome_aba}' não encontrada",
                "abas_disponiveis": abas_disponiveis
            }
        
        # Obter worksheet
        worksheet = planilha.worksheet(nome_aba)
        
        # Obter cabeçalhos (primeira linha)
        cabecalhos = worksheet.row_values(1)
        
        # Obter algumas linhas de exemplo
        dados_exemplo = worksheet.get_all_records(head=1, expected_headers=cabecalhos)[:5]
        
        # Análise da estrutura
        total_linhas = len(worksheet.get_all_values())
        total_colunas = len(cabecalhos)
        
        # Verificar colunas essenciais
        cabecalhos_lower = [h.lower() for h in cabecalhos]
        tem_sintoma = any("sintoma" in h or "symptom" in h for h in cabecalhos_lower)
        tem_pontuacao = any("pontuacao" in h or "score" in h for h in cabecalhos_lower)
        
        resultado = {
            "valido": tem_sintoma,
            "sheets_id": sheets_id,
            "aba": nome_aba,
            "total_linhas": total_linhas,
            "total_colunas": total_colunas,
            "cabecalhos": cabecalhos,
            "tem_sintoma": tem_sintoma,
            "tem_pontuacao": tem_pontuacao,
            "dados_exemplo": dados_exemplo,
            "abas_disponiveis": abas_disponiveis
        }
        
        if not tem_sintoma:
            resultado["erro"] = "Coluna de sintoma não encontrada (esperado: 'sintoma' ou 'symptom')"
        
        return resultado
        
    except Exception as e:
        return {
            "valido": False,
            "erro": str(e),
            "sheets_id": sheets_id,
            "aba": nome_aba
        }


def testar_conexao_sheets() -> bool:
    """Testa conexão com Google Sheets"""
    try:
        if not GOOGLE_SHEETS_ID:
            logger.error("GOOGLE_SHEETS_ID não configurado")
            return False
        
        validacao = validar_estrutura_sheets()
        
        if validacao.get("valido"):
            logger.info("Conexão Google Sheets testada com sucesso", 
                       total_linhas=validacao.get("total_linhas"),
                       total_colunas=validacao.get("total_colunas"))
            return True
        else:
            logger.error("Estrutura do Sheets inválida", erro=validacao.get("erro"))
            return False
            
    except Exception as e:
        logger.error(f"Erro na conexão Google Sheets: {e}")
        return False
