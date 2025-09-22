"""
Subgrafo Clínico
Subrouter: extrai vitais e/ou nota via LLM estruturado
Se houver nota, roda RAG e produz SymptomReport[]
"""
from typing import Dict, Any, List
import structlog

from app.graph.state import GraphState, SymptomReport
from app.graph.clinical_extractor import extrair_clinico_via_llm
from app.graph.rag import RAGSystem
from app.llm.extractor import ClinicalExtractor
from app.infra.http import LambdaHttpClient

logger = structlog.get_logger(__name__)


class ClinicoSubgraph:
    """Subgrafo clínico - subrouter para vitais/nota"""
    
    def __init__(self, 
                 clinical_extractor: ClinicalExtractor,
                 rag_system: RAGSystem,
                 http_client: LambdaHttpClient,
                 lambda_update_clinical_url: str):
        self.clinical_extractor = clinical_extractor
        self.rag_system = rag_system
        self.http_client = http_client
        self.lambda_update_clinical_url = lambda_update_clinical_url
        logger.info("ClinicoSubgraph inicializado")
    
    def _extrair_dados_clinicos(self, state: GraphState) -> Dict[str, Any]:
        """Extrai dados clínicos via LLM"""
        texto_usuario = state.entrada.get("texto_usuario", "")
        
        logger.info("Extraindo dados clínicos", texto=texto_usuario[:100])
        
        # Chama extrator clínico
        resultado = extrair_clinico_via_llm(texto_usuario, self.clinical_extractor)
        
        # Atualiza estado
        state.clinico["vitais"] = resultado["vitais"]
        state.clinico["nota"] = resultado["nota"]
        state.clinico["faltantes"] = resultado["faltantes"]
        
        # Log warnings se houver
        if resultado["warnings"]:
            logger.warning("Warnings na extração clínica", 
                          warnings=resultado["warnings"])
        
        logger.info("Extração clínica concluída",
                   vitais_encontrados=[k for k, v in resultado["vitais"].items() if v is not None],
                   tem_nota=bool(resultado["nota"]),
                   faltantes=resultado["faltantes"])
        
        return resultado
    
    def _processar_nota_com_rag(self, state: GraphState) -> None:
        """Processa nota clínica via RAG se presente"""
        nota = state.clinico.get("nota")
        
        if not nota:
            logger.info("Nenhuma nota para processar com RAG")
            return
        
        logger.info("Processando nota via RAG", nota=nota[:100])
        
        try:
            # Chama sistema RAG
            symptom_reports = self.rag_system.processar_nota_clinica(nota)
            
            # Converte para dict para serialização no estado
            symptom_reports_dict = [report.model_dump() for report in symptom_reports]
            state.clinico["sintomas"] = symptom_reports_dict
            
            logger.info("RAG concluído",
                       sintomas_encontrados=len(symptom_reports),
                       nota=nota[:50])
            
        except Exception as e:
            logger.error("Erro no processamento RAG", nota=nota[:50], error=str(e))
            state.clinico["sintomas"] = []
    
    def _preparar_payload_clinical(self, state: GraphState) -> Dict[str, Any]:
        """Prepara payload para updateClinicalData"""
        sessao = state.sessao
        clinico = state.clinico
        
        payload = {
            "reportID": sessao.get("report_id"),
            "reportDate": sessao.get("data_relatorio"),
            "scheduleID": sessao.get("schedule_id"),
            "caregiverID": sessao.get("caregiver_id"),
            "patientID": sessao.get("patient_id")
        }
        
        # Adiciona vitais se presentes
        vitais = clinico.get("vitais", {})
        vitais_validos = {k: v for k, v in vitais.items() if v is not None}
        
        if vitais_validos:
            # Monta vitalSignsData
            vital_signs_data = {}
            
            if vitais_validos.get("PA"):
                vital_signs_data["bloodPressure"] = vitais_validos["PA"]
            if vitais_validos.get("FC"):
                vital_signs_data["heartRate"] = vitais_validos["FC"]
            if vitais_validos.get("FR"):
                vital_signs_data["respRate"] = vitais_validos["FR"]
            if vitais_validos.get("Sat"):
                vital_signs_data["saturationO2"] = vitais_validos["Sat"]
            if vitais_validos.get("Temp"):
                vital_signs_data["temperature"] = vitais_validos["Temp"]
            
            payload["vitalSignsData"] = vital_signs_data
        
        # Adiciona nota se presente
        if clinico.get("nota"):
            payload["clinicalNote"] = clinico["nota"]
        
        # Adiciona sintomas se presentes
        sintomas = clinico.get("sintomas", [])
        if sintomas:
            # Converte de volta para formato esperado pelo Lambda
            payload["SymptomReport"] = sintomas
        
        logger.debug("Payload clinical preparado",
                    tem_vitais=bool(vitais_validos),
                    tem_nota=bool(clinico.get("nota")),
                    tem_sintomas=len(sintomas))
        
        return payload
    
    def _montar_mensagem_confirmacao(self, state: GraphState) -> str:
        """Monta mensagem de confirmação com dados encontrados"""
        clinico = state.clinico
        vitais = clinico.get("vitais", {})
        nota = clinico.get("nota")
        sintomas = clinico.get("sintomas", [])
        
        partes_mensagem = ["Confirma salvar:"]
        
        # Vitais válidos
        vitais_validos = [(k, v) for k, v in vitais.items() if v is not None]
        if vitais_validos:
            vitais_str = ", ".join([f"{k} {v}" for k, v in vitais_validos])
            partes_mensagem.append(f"Vitais: {vitais_str}")
        
        # Nota
        if nota:
            nota_preview = nota[:50] + "..." if len(nota) > 50 else nota
            partes_mensagem.append(f"Nota: {nota_preview}")
        
        # Sintomas
        if sintomas:
            partes_mensagem.append(f"Sintomas identificados: {len(sintomas)}")
        
        # Faltantes
        faltantes = clinico.get("faltantes", [])
        if faltantes:
            partes_mensagem.append(f"Faltantes: {', '.join(faltantes)}")
        
        return "\n".join(partes_mensagem)
    
    def _executar_salvamento(self, state: GraphState) -> str:
        """Executa salvamento dos dados clínicos"""
        pendente = state.pendente
        if not pendente or pendente.get("fluxo") != "clinico":
            return "Erro: Nenhum dado clínico pendente."
        
        payload = pendente.get("payload")
        
        try:
            logger.info("Salvando dados clínicos")
            
            # Chama Lambda
            result = self.http_client.update_clinical_data(
                self.lambda_update_clinical_url,
                payload
            )
            
            # Limpa pendente
            state.limpar_pendente()
            
            logger.info("Dados clínicos salvos com sucesso")
            return "Dados clínicos salvos com sucesso!"
            
        except Exception as e:
            logger.error("Erro ao salvar dados clínicos", error=str(e))
            state.limpar_pendente()
            return f"Erro ao salvar dados clínicos: {str(e)}"
    
    def processar(self, state: GraphState) -> str:
        """
        Processa subgrafo clínico
        
        Fluxo:
        1. Extrai vitais/nota via LLM
        2. Se houver nota, roda RAG
        3. Prepara confirmação (two-phase commit)
        4. Se confirmado, chama updateClinicalData
        
        Returns:
            Mensagem para ser processada pelo fiscal
        """
        logger.info("Processando subgrafo clínico")
        
        # Adiciona à lista de fluxos executados
        state.adicionar_fluxo_executado("clinico")
        
        texto_usuario = state.entrada.get("texto_usuario", "").lower()
        
        # Verifica se é resposta de confirmação
        if state.tem_pendente() and state.pendente.get("fluxo") == "clinico":
            if "sim" in texto_usuario or "confirmo" in texto_usuario or "ok" in texto_usuario:
                return self._executar_salvamento(state)
            elif "não" in texto_usuario or "nao" in texto_usuario or "cancelar" in texto_usuario:
                state.limpar_pendente()
                return "Salvamento cancelado."
            else:
                return "Responda 'sim' para confirmar ou 'não' para cancelar."
        
        # 1. Extrai dados clínicos
        resultado_extracao = self._extrair_dados_clinicos(state)
        
        # 2. Se houver nota, processa via RAG
        if state.clinico.get("nota"):
            self._processar_nota_com_rag(state)
        
        # 3. Verifica se há dados para salvar
        vitais_validos = {k: v for k, v in state.clinico["vitais"].items() if v is not None}
        tem_nota = bool(state.clinico.get("nota"))
        tem_sintomas = len(state.clinico.get("sintomas", [])) > 0
        
        if not vitais_validos and not tem_nota and not tem_sintomas:
            return "Nenhum dado clínico encontrado. Envie sinais vitais ou notas clínicas."
        
        # 4. Prepara payload e confirmação
        payload = self._preparar_payload_clinical(state)
        
        state.pendente = {
            "fluxo": "clinico",
            "payload": payload
        }
        
        # 5. Monta mensagem de confirmação
        return self._montar_mensagem_confirmacao(state)
