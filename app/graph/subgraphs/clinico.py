"""
Subgrafo Clínico
Subrouter: extrai vitais e/ou nota via LLM estruturado
Se houver nota, roda RAG e produz SymptomReport[]
"""
from typing import Dict, Any, List
import structlog

from app.graph.state import GraphState, SymptomReport
# Extração clínica consolidada no ClinicalExtractor
# RAG desabilitado - processamento via webhook n8n
from app.llm.extractors import ClinicalExtractor
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
        resultado = self.clinical_extractor.extrair_clinico_completo(texto_usuario)
        
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
        
        # Atualiza condição respiratória (apenas se não for None - preserva valor anterior)
        if "supplementaryOxygen" in resultado and resultado["supplementaryOxygen"] is not None:
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
        
        # RAG desabilitado - processamento via webhook n8n
        logger.info("RAG será processado pelo webhook n8n - pulando processamento local")
    
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
    
    def _preparar_payload_n8n_nota_isolada(self, state: GraphState) -> Dict[str, Any]:
        """Prepara payload para webhook n8n apenas com nota clínica"""
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
        
        # Apenas nota clínica (obrigatória para este cenário)
        payload["clinicalNote"] = clinico.get("nota", "")
        
        logger.info("Payload n8n nota isolada preparado",
                   tem_nota=bool(clinico.get("nota")),
                   payload_keys=list(payload.keys()))
        
        return payload
    
    def _verificar_dados_completos(self, state: GraphState) -> tuple[bool, str]:
        """
        Verifica se os dados clínicos estão completos para envio ao webhook n8n
        
        Critérios:
        - PRIMEIRA aferição: Deve ter todos os vitais + nota clínica + condição respiratória
        - AFERIÇÕES SUBSEQUENTES: Deve ter todos os vitais + condição respiratória (nota opcional)
        
        Returns:
            (dados_completos: bool, mensagem_status: str)
        """
        clinico = state.clinico
        vitais = clinico.get("vitais", {})
        nota = clinico.get("nota")
        condicao_resp = clinico.get("supplementaryOxygen")
        ja_teve_afericao = clinico.get("afericao_completa_realizada", False)
        
        # Verifica vitais completos (todos os 5)
        campos_vitais = ["PA", "FC", "FR", "Sat", "Temp"]
        vitais_validos = {k: v for k, v in vitais.items() if v is not None and k in campos_vitais}
        vitais_completos = len(vitais_validos) == 5
        
        tem_nota = bool(nota)
        tem_condicao_resp = bool(condicao_resp)
        
        # REGRA 1: Primeira aferição - EXIGE nota clínica
        if not ja_teve_afericao:
            if vitais_completos and tem_nota and tem_condicao_resp:
                return True, f"Primeira aferição completa: 5 vitais + nota clínica + condição respiratória"
            else:
                faltantes = []
                if not vitais_completos:
                    faltantes_vitais = [v for v in campos_vitais if not vitais.get(v)]
                    faltantes.append(f"vitais ({', '.join(faltantes_vitais)})")
                if not tem_nota:
                    faltantes.append("nota clínica")
                if not tem_condicao_resp:
                    faltantes.append("condição respiratória")
                
                return False, f"Falta para primeira aferição: {', '.join(faltantes)}"
        
        # REGRA 2: Aferições subsequentes - nota clínica OPCIONAL
        else:
            if vitais_completos and tem_condicao_resp:
                if tem_nota:
                    return True, f"Aferição completa: 5 vitais + condição respiratória + nota clínica"
                else:
                    return True, f"Aferição completa: 5 vitais + condição respiratória (sem nota)"
            else:
                faltantes = []
                if not vitais_completos:
                    faltantes_vitais = [v for v in campos_vitais if not vitais.get(v)]
                    faltantes.append(f"vitais ({', '.join(faltantes_vitais)})")
                if not tem_condicao_resp:
                    faltantes.append("condição respiratória")
                
                return False, f"Falta: {', '.join(faltantes)}"
    
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
            
            # Marca que já teve aferição completa no plantão
            state.clinico["afericao_completa_realizada"] = True
            
            # Limpa pendente e dados clínicos após envio bem-sucedido
            state.limpar_pendente()
            self._limpar_dados_clinicos(state)
            
            logger.info("Dados enviados para n8n com sucesso e estado clínico limpo",
                       afericao_completa_realizada=True)
            
        except Exception as e:
            logger.error("Erro ao enviar dados para n8n", error=str(e))
            state.limpar_pendente()
    
    def _limpar_dados_clinicos(self, state: GraphState):
        """
        Limpa os dados clínicos do estado após envio bem-sucedido
        Preserva a flag afericao_completa_realizada
        """
        # Preserva a flag de primeira aferição
        ja_teve_afericao = state.clinico.get("afericao_completa_realizada", False)
        
        # Reseta todos os campos clínicos para valores padrão
        state.clinico = {
            "vitais": {},
            "faltantes": ["PA", "FC", "FR", "Sat", "Temp"],
            "nota": None,
            "supplementaryOxygen": None,
            "afericao_em_andamento": False,
            "afericao_completa_realizada": ja_teve_afericao  # Preserva
        }
        logger.info("Dados clínicos limpos do estado",
                   afericao_completa_realizada=ja_teve_afericao)
    
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
                from app.llm.classifiers import ConfirmationClassifier
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
        
        # 4. NOVA LÓGICA: Determina o tipo de coleta baseado na regra de primeira aferição
        ja_teve_afericao_completa = state.clinico.get("afericao_completa_realizada", False)
        
        logger.info("Analisando tipo de coleta",
                   tem_vitais=bool(vitais_validos),
                   tem_nota=tem_nota,
                   afericao_em_andamento=state.clinico.get("afericao_em_andamento", False),
                   ja_teve_afericao_completa=ja_teve_afericao_completa)
        
        # REGRA 1: Se NÃO teve aferição completa no plantão, FORÇA aferição completa
        if not ja_teve_afericao_completa:
            if tem_nota and not vitais_validos:
                # Usuário tentou enviar apenas nota na primeira aferição
                logger.warning("Primeira aferição deve ser completa - rejeitando nota isolada")
                return "CLINICAL_INCOMPLETE_FIRST_ASSESSMENT"
            
            # Se há vitais, marca como aferição em andamento
            if vitais_validos:
                state.clinico["afericao_em_andamento"] = True
                logger.info("Primeira aferição em andamento - vitais detectados")
        
        # REGRA 2: Se JÁ teve aferição completa, permite nota isolada OU aferição sem nota
        else:
            # Se há vitais, marca como aferição em andamento
            if vitais_validos:
                state.clinico["afericao_em_andamento"] = True
                logger.info("Aferição subsequente em andamento - vitais detectados")
            
            # Se há apenas nota e não há aferição em andamento, é nota isolada
            elif tem_nota and not state.clinico.get("afericao_em_andamento", False):
                logger.info("Nota clínica isolada detectada (após primeira aferição) - enviando diretamente")
                # Prepara payload apenas com nota
                payload = self._preparar_payload_n8n_nota_isolada(state)
                
                state.pendente = {
                    "fluxo": "clinico", 
                    "payload": payload
                }
                
                logger.info("Retornando código CLINICAL_NOTE_READY_FOR_CONFIRMATION")
                return "CLINICAL_NOTE_READY_FOR_CONFIRMATION"  # Nota isolada após primeira aferição
        
        # 5. Para aferição completa, verifica se todos os dados estão completos
        if state.clinico.get("afericao_em_andamento", False):
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
            
            # 6. Dados completos - prepara confirmação para envio ao n8n
            payload = self._preparar_payload_n8n(state)
            
            state.pendente = {
                "fluxo": "clinico", 
                "payload": payload
            }
            
            return "CLINICAL_DATA_READY_FOR_CONFIRMATION"  # Código para o Fiscal
        
        # Fallback
        return "CLINICAL_PARTIAL_DATA"
