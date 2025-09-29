"""
Subgrafo Clínico
Subrouter: extrai vitais e/ou nota via LLM estruturado
Se houver nota, roda RAG e produz SymptomReport[]
"""
from typing import Dict, Any, List
import structlog

from app.graph.state import GraphState, SymptomReport
from app.graph.clinical_extractor import extrair_clinico_via_llm
# from app.graph.rag import RAGSystem  # Usando mock no deps
from app.llm.extractor import ClinicalExtractor
from app.infra.http import LambdaHttpClient

logger = structlog.get_logger(__name__)


class ClinicoSubgraph:
    """Subgrafo clínico - subrouter para vitais/nota"""
    
    def __init__(self, 
                 clinical_extractor: ClinicalExtractor,
                 rag_system,  # Mock RAG system
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
        
        # CORREÇÃO: Mescla vitais em vez de sobrescrever
        vitais_existentes = state.clinico.get("vitais", {})
        vitais_novos = resultado["vitais"]
        
        # Mescla: novos sobrescrevem existentes apenas se não forem None
        for campo, valor in vitais_novos.items():
            if valor is not None:
                vitais_existentes[campo] = valor
        
        state.clinico["vitais"] = vitais_existentes
        
        # Atualiza nota se presente
        if resultado["nota"]:
            state.clinico["nota"] = resultado["nota"]
        
        # Atualiza condição respiratória se presente
        if resultado.get("supplementaryOxygen"):
            state.clinico["supplementaryOxygen"] = resultado["supplementaryOxygen"]
        
        # Recalcula faltantes baseado nos vitais mesclados
        campos_obrigatorios = ["PA", "FC", "FR", "Sat", "Temp"]
        faltantes = [campo for campo in campos_obrigatorios if not vitais_existentes.get(campo)]
        state.clinico["faltantes"] = faltantes
        
        # Log warnings se houver
        if resultado["warnings"]:
            logger.warning("Warnings na extração clínica", 
                          warnings=resultado["warnings"])
        
        logger.info("Extração clínica concluída",
                   vitais_encontrados=[k for k, v in vitais_existentes.items() if v is not None],
                   tem_nota=bool(state.clinico.get("nota")),
                   faltantes=faltantes)
        
        return resultado
    
    def _processar_nota_com_rag(self, state: GraphState) -> None:
        """RAG COMENTADO - Agora usa webhook n8n"""
        # COMENTADO: RAG local substituído por webhook n8n
        # 
        # nota = state.clinico.get("nota")
        # 
        # if not nota:
        #     logger.info("Nenhuma nota para processar com RAG")
        #     return
        # 
        # logger.info("Processando nota via RAG", nota=nota[:100])
        # 
        # try:
        #     # Chama sistema RAG
        #     symptom_reports = self.rag_system.processar_nota_clinica(nota)
        #     
        #     # Converte para dict para serialização no estado
        #     symptom_reports_dict = [report.model_dump() for report in symptom_reports]
        #     state.clinico["sintomas"] = symptom_reports_dict
        #     
        #     logger.info("RAG concluído",
        #                sintomas_encontrados=len(symptom_reports),
        #                nota=nota[:50])
        #     
        # except Exception as e:
        #     logger.error("Erro no processamento RAG", nota=nota[:50], error=str(e))
        #     state.clinico["sintomas"] = []
        
        # RAG agora é processado pelo webhook n8n
        logger.info("RAG será processado pelo webhook n8n - pulando processamento local")
        state.clinico["sintomas"] = []
    
    def _preparar_payload_clinical(self, state: GraphState) -> Dict[str, Any]:
        """COMENTADO - Prepara payload para updateClinicalData (agora usa webhook n8n)"""
        # COMENTADO: updateClinicalData substituído por webhook n8n
        # 
        # sessao = state.sessao
        # clinico = state.clinico
        # 
        # payload = {
        #     "reportID": sessao.get("report_id"),
        #     "reportDate": sessao.get("data_relatorio"),
        #     "scheduleID": sessao.get("schedule_id"),
        #     "caregiverID": sessao.get("caregiver_id"),
        #     "patientID": sessao.get("patient_id")
        # }
        # 
        # # Adiciona vitais se presentes
        # vitais = clinico.get("vitais", {})
        # vitais_validos = {k: v for k, v in vitais.items() if v is not None}
        # 
        # if vitais_validos:
        #     # Monta vitalSignsData
        #     vital_signs_data = {}
        #     
        #     if vitais_validos.get("PA"):
        #         vital_signs_data["bloodPressure"] = vitais_validos["PA"]
        #     if vitais_validos.get("FC"):
        #         vital_signs_data["heartRate"] = vitais_validos["FC"]
        #     if vitais_validos.get("FR"):
        #         vital_signs_data["respRate"] = vitais_validos["FR"]
        #     if vitais_validos.get("Sat"):
        #         vital_signs_data["saturationO2"] = vitais_validos["Sat"]
        #     if vitais_validos.get("Temp"):
        #         vital_signs_data["temperature"] = vitais_validos["Temp"]
        #     
        #     payload["vitalSignsData"] = vital_signs_data
        # 
        # # Adiciona nota se presente
        # if clinico.get("nota"):
        #     payload["clinicalNote"] = clinico["nota"]
        # 
        # # Adiciona sintomas se presentes
        # sintomas = clinico.get("sintomas", [])
        # if sintomas:
        #     # Converte de volta para formato esperado pelo Lambda
        #     payload["SymptomReport"] = sintomas
        # 
        # logger.debug("Payload clinical preparado",
        #             tem_vitais=bool(vitais_validos),
        #             tem_nota=bool(clinico.get("nota")),
        #             tem_sintomas=len(sintomas))
        # 
        # return payload
        
        # Agora usa webhook n8n - retorna payload vazio
        return {}
    
    def _preparar_payload_n8n(self, state: GraphState) -> Dict[str, Any]:
        """Prepara payload para webhook n8n"""
        sessao = state.sessao
        clinico = state.clinico
        
        # Payload base obrigatório
        payload = {
            "reportID": sessao.get("report_id"),
            "reportDate": sessao.get("data_relatorio"), 
            "patientIdentifier": sessao.get("patient_id"),
            "caregiverIdentifier": sessao.get("caregiver_id"),
            "scheduleID": sessao.get("schedule_id"),
            "sessionID": sessao.get("telefone")  # phoneNumber
        }
        
        # Adiciona vitais se presentes
        vitais = clinico.get("vitais", {})
        
        # Mapeia vitais para formato n8n
        if vitais.get("FR"):
            payload["respRate"] = vitais["FR"]
        if vitais.get("Sat"):
            payload["saturationO2"] = vitais["Sat"]
        if vitais.get("PA"):
            payload["bloodPressure"] = vitais["PA"]
        if vitais.get("FC"):
            payload["heartRate"] = vitais["FC"]
        if vitais.get("Temp"):
            payload["temperature"] = vitais["Temp"]
        
        # Condição respiratória
        payload["supplementaryOxygen"] = clinico.get("supplementaryOxygen")
        payload["oxygenVolume"] = None
        payload["oxygenConcentrator"] = None
        
        # Adiciona nota clínica (obrigatória)
        payload["clinicalNote"] = clinico.get("nota", "sem alterações")
        
        logger.debug("Payload n8n preparado",
                    tem_vitais=len([k for k in ["FR", "Sat", "PA", "FC", "Temp"] if vitais.get(k)]),
                    tem_nota=bool(clinico.get("nota")))
        
        return payload
    
    def _verificar_dados_completos(self, state: GraphState) -> tuple[bool, str]:
        """
        Verifica se os dados clínicos estão completos para envio ao webhook n8n
        
        Critério: Deve ter pelo menos 1 vital + nota clínica + condição respiratória
        
        Returns:
            (dados_completos: bool, mensagem_status: str)
        """
        clinico = state.clinico
        vitais = clinico.get("vitais", {})
        nota = clinico.get("nota")
        condicao_resp = clinico.get("supplementaryOxygen")
        
        # Conta vitais válidos
        vitais_validos = {k: v for k, v in vitais.items() if v is not None}
        qtd_vitais = len(vitais_validos)
        
        # Deve ter pelo menos 1 vital + nota + condição respiratória
        tem_vitais = qtd_vitais > 0
        tem_nota = bool(nota)
        tem_condicao_resp = bool(condicao_resp)
        
        if tem_vitais and tem_nota and tem_condicao_resp:
            return True, f"Dados completos: {qtd_vitais} vitais + nota clínica + condição respiratória"
        else:
            faltantes = []
            if not tem_vitais:
                faltantes.append("vitais")
            if not tem_nota:
                faltantes.append("nota clínica")
            if not tem_condicao_resp:
                faltantes.append("condição respiratória")
            
            return False, f"Falta: {', '.join(faltantes)} (vitais: {qtd_vitais})"
    
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
    
    def _executar_salvamento(self, state: GraphState) -> None:
        """Executa salvamento via webhook n8n - não retorna mensagem"""
        pendente = state.pendente
        if not pendente or pendente.get("fluxo") != "clinico":
            logger.error("Nenhum dado clínico pendente para salvamento")
            return
        
        # COMENTADO: Lambda updateClinicalData substituído por webhook n8n
        # payload = pendente.get("payload")
        # 
        # try:
        #     logger.info("Salvando dados clínicos")
        #     
        #     # Chama Lambda
        #     result = self.http_client.update_clinical_data(
        #         self.lambda_update_clinical_url,
        #         payload
        #     )
        #     
        #     # Limpa pendente
        #     state.limpar_pendente()
        #     
        #     logger.info("Dados clínicos salvos com sucesso")
        #     
        # except Exception as e:
        #     logger.error("Erro ao salvar dados clínicos", error=str(e))
        #     state.limpar_pendente()
        
        try:
            logger.info("Enviando dados para webhook n8n")
            
            # Prepara payload para n8n
            payload = self._preparar_payload_n8n(state)
            
            # URL do webhook n8n
            webhook_url = "https://primary-production-031c.up.railway.app/webhook/8f70cfe8-9c88-403d-8282-0d9bd7b4311d"
            
            # Chama webhook n8n
            result = self.http_client.post(webhook_url, payload)
            
            # Limpa pendente
            state.limpar_pendente()
            
            logger.info("Dados enviados para n8n com sucesso")
            
        except Exception as e:
            logger.error("Erro ao enviar dados para n8n", error=str(e))
            state.limpar_pendente()
    
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
        
        texto_usuario = state.entrada.get("texto_usuario", "")
        
        # Verifica se é resposta de confirmação
        if state.tem_pendente() and state.pendente.get("fluxo") == "clinico":
            try:
                # Usar LLM para classificar confirmação
                from app.llm.confirmation_classifier import ConfirmationClassifier
                import os
                
                api_key = os.getenv("OPENAI_API_KEY")
                if api_key:
                    classifier = ConfirmationClassifier(
                        api_key=api_key,
                        model=os.getenv("INTENT_MODEL", "gpt-4o-mini")
                    )
                    
                    confirmacao = classifier.classificar_confirmacao(texto_usuario)
                    
                    if confirmacao == "sim":
                        self._executar_salvamento(state)
                        return "CLINICAL_DATA_SAVED"  # Código para o Fiscal
                    elif confirmacao == "nao":
                        state.limpar_pendente()
                        return "CLINICAL_DATA_CANCELLED"  # Código para o Fiscal
                    else:
                        return "CLINICAL_CONFIRMATION_PENDING"  # Código para o Fiscal
                else:
                    # Fallback se não tiver API key
                    return "CLINICAL_CONFIRMATION_PENDING"
                    
            except Exception as e:
                logger.error("Erro ao classificar confirmação via LLM", error=str(e))
                return "CLINICAL_CONFIRMATION_PENDING"
        
        # 1. Extrai dados clínicos
        resultado_extracao = self._extrair_dados_clinicos(state)
        
        # 2. RAG comentado - será processado pelo webhook n8n
        if state.clinico.get("nota"):
            self._processar_nota_com_rag(state)
        
        # 3. Verifica se há dados básicos
        vitais_validos = {k: v for k, v in state.clinico["vitais"].items() if v is not None}
        tem_nota = bool(state.clinico.get("nota"))
        
        if not vitais_validos and not tem_nota:
            return "CLINICAL_NO_DATA_FOUND"  # Código para o Fiscal
        
        # 4. Verifica se dados estão completos para envio ao n8n
        dados_completos, status_msg = self._verificar_dados_completos(state)
        
        if not dados_completos:
            # Dados parciais - armazena no estado e pede o que falta
            logger.info("Dados parciais armazenados no estado", status=status_msg)
            
            if vitais_validos and not tem_nota:
                return "CLINICAL_PARTIAL_VITALS_ONLY"  # Código para o Fiscal
            elif tem_nota and not vitais_validos:
                return "CLINICAL_PARTIAL_NOTE_ONLY"  # Código para o Fiscal
            else:
                return "CLINICAL_PARTIAL_DATA"  # Código para o Fiscal
        
        # 5. Dados completos - prepara confirmação para envio ao n8n
        payload = self._preparar_payload_n8n(state)
        
        state.pendente = {
            "fluxo": "clinico", 
            "payload": payload
        }
        
        # 6. Dados completos - aguarda confirmação
        return "CLINICAL_DATA_READY_FOR_CONFIRMATION"  # Código para o Fiscal
