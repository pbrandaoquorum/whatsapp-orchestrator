"""
Sistema RAG - Integração Pinecone + Google Sheets
Busca sintomas baseado em notas clínicas
"""
import re
from typing import List, Dict, Any
import gspread
from google.oauth2.service_account import Credentials
from pinecone import Pinecone
from sentence_transformers import SentenceTransformer
import structlog

from app.graph.state import SymptomReport

logger = structlog.get_logger(__name__)


class RAGSystem:
    """Sistema RAG para busca de sintomas"""
    
    def __init__(self, 
                 pinecone_api_key: str,
                 pinecone_environment: str,
                 pinecone_index_name: str,
                 google_credentials_path: str,
                 google_sheets_id: str,
                 embedding_model: str = "all-MiniLM-L6-v2"):
        
        # Inicializa Pinecone (nova API)
        pc = Pinecone(api_key=pinecone_api_key)
        self.pinecone_index = pc.Index(pinecone_index_name)
        
        # Inicializa Google Sheets
        scopes = [
            'https://www.googleapis.com/auth/spreadsheets.readonly',
            'https://www.googleapis.com/auth/drive.readonly'
        ]
        credentials = Credentials.from_service_account_file(google_credentials_path, scopes=scopes)
        self.gsheets_client = gspread.authorize(credentials)
        self.sheets_id = google_sheets_id
        
        # Modelo de embeddings
        self.embedding_model = SentenceTransformer(embedding_model)
        
        logger.info("RAGSystem inicializado",
                   pinecone_index=pinecone_index_name,
                   google_sheets_id=google_sheets_id,
                   embedding_model=embedding_model)
    
    def _extrair_termos_simples(self, nota: str) -> List[str]:
        """
        Extrai termos simples da nota clínica
        Sem regex complexo, apenas tokenização básica
        """
        if not nota:
            return []
        
        # Remove pontuação e converte para minúsculas
        texto_limpo = re.sub(r'[^\w\s]', ' ', nota.lower())
        
        # Tokeniza e filtra palavras muito curtas
        termos = [palavra for palavra in texto_limpo.split() if len(palavra) >= 3]
        
        # Remove duplicatas mantendo ordem
        termos_unicos = []
        for termo in termos:
            if termo not in termos_unicos:
                termos_unicos.append(termo)
        
        logger.debug("Termos extraídos da nota", 
                    nota=nota[:100],
                    termos=termos_unicos[:10])  # Log apenas primeiros 10
        
        return termos_unicos
    
    def _buscar_no_pinecone(self, query_text: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Busca no Pinecone usando embeddings"""
        try:
            # Gera embedding da query
            query_embedding = self.embedding_model.encode(query_text).tolist()
            
            # Busca no Pinecone
            results = self.pinecone_index.query(
                vector=query_embedding,
                top_k=top_k,
                include_metadata=True,
                include_values=False
            )
            
            # Processa resultados
            matches = []
            for match in results['matches']:
                matches.append({
                    'id': match['id'],
                    'score': match['score'],
                    'metadata': match.get('metadata', {})
                })
            
            logger.debug("Busca no Pinecone concluída",
                        query=query_text[:50],
                        results_count=len(matches))
            
            return matches
            
        except Exception as e:
            logger.error("Erro na busca do Pinecone", query=query_text[:50], error=str(e))
            return []
    
    def _buscar_no_google_sheets(self, sintoma: str) -> Dict[str, Any]:
        """
        Busca dados do sintoma no Google Sheets
        Assume formato: coluna A = sintoma, coluna B = pontuacao
        """
        try:
            worksheet = self.gsheets_client.open_by_key(self.sheets_id).sheet1
            
            # Busca todas as linhas
            records = worksheet.get_all_records()
            
            # Procura pelo sintoma (case-insensitive)
            for record in records:
                sintoma_sheet = record.get('sintoma', '').strip().lower()
                if sintoma.lower() in sintoma_sheet or sintoma_sheet in sintoma.lower():
                    return {
                        'sintoma': record.get('sintoma', ''),
                        'pontuacao': record.get('pontuacao', 0)
                    }
            
            logger.debug("Sintoma não encontrado no Google Sheets", sintoma=sintoma)
            return {}
            
        except Exception as e:
            logger.error("Erro ao buscar no Google Sheets", sintoma=sintoma, error=str(e))
            return {}
    
    def processar_nota_clinica(self, nota: str) -> List[SymptomReport]:
        """
        Processa nota clínica e retorna lista de SymptomReport
        
        Fluxo:
        1. Extrai termos da nota
        2. Busca no Pinecone
        3. Para cada resultado, busca detalhes no Google Sheets
        4. Monta SymptomReport
        """
        if not nota or not nota.strip():
            logger.info("Nota clínica vazia, retornando lista vazia")
            return []
        
        logger.info("Processando nota clínica via RAG", nota=nota[:100])
        
        # 1. Extrai termos
        termos = self._extrair_termos_simples(nota)
        if not termos:
            logger.info("Nenhum termo extraído da nota")
            return []
        
        # 2. Monta query para busca (usa os primeiros termos mais relevantes)
        query_text = " ".join(termos[:10])  # Limita para evitar query muito longa
        
        # 3. Busca no Pinecone
        matches = self._buscar_no_pinecone(query_text, top_k=3)  # Top-K pequeno conforme especificado
        
        if not matches:
            logger.info("Nenhum resultado encontrado no Pinecone")
            return []
        
        # 4. Para cada match, busca detalhes e monta SymptomReport
        symptom_reports = []
        
        for match in matches:
            try:
                # Extrai informações do match
                sintoma_id = match['id']
                score = match['score']
                metadata = match.get('metadata', {})
                
                # Busca detalhes no Google Sheets
                sintoma_nome = metadata.get('symptom', sintoma_id)
                sheets_data = self._buscar_no_google_sheets(sintoma_nome)
                
                # Monta SymptomReport
                symptom_report = SymptomReport(
                    symptomDefinition=sheets_data.get('sintoma', sintoma_nome),
                    altNotepadMain=nota[:200],  # Primeiros 200 chars da nota
                    symptomCategory=metadata.get('category', 'Geral'),
                    symptomSubCategory=metadata.get('subcategory', 'Não especificado'),
                    descricaoComparada=f"Identificado via RAG: {sintoma_nome}",
                    coeficienteSimilaridade=float(score)
                )
                
                symptom_reports.append(symptom_report)
                
                logger.debug("SymptomReport criado",
                           sintoma=sintoma_nome,
                           score=score,
                           pontuacao=sheets_data.get('pontuacao', 0))
                
            except Exception as e:
                logger.error("Erro ao processar match do Pinecone", match_id=match.get('id'), error=str(e))
                continue
        
        logger.info("Processamento RAG concluído",
                   nota=nota[:50],
                   symptom_reports_count=len(symptom_reports))
        
        return symptom_reports
