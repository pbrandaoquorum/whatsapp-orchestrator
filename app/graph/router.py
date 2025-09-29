"""
Router principal - Roteamento determinístico + LLM leve
Implementa toda a lógica de gates e despacho
"""
from typing import Dict, Any
import structlog

from app.graph.state import GraphState
from app.llm.classifiers import IntentClassifier, OperationalNoteClassifier
from app.infra.http import LambdaHttpClient

logger = structlog.get_logger(__name__)


class MainRouter:
    """Router principal do sistema"""
    
    def __init__(self, 
                 intent_classifier: IntentClassifier,
                 operational_classifier: OperationalNoteClassifier,
                 http_client: LambdaHttpClient,
                 lambda_get_schedule_url: str):
        self.intent_classifier = intent_classifier
        self.operational_classifier = operational_classifier
        self.http_client = http_client
        self.lambda_get_schedule_url = lambda_get_schedule_url
        logger.info("MainRouter inicializado")
    
    def _verificar_dados_sessao(self, state: GraphState) -> bool:
        """Verifica se os dados básicos da sessão estão presentes"""
        sessao = state.sessao
        return bool(
            sessao.get("schedule_id") and 
            sessao.get("report_id") and 
            sessao.get("patient_id") and
            sessao.get("caregiver_id")
        )
    
    def _plantao_confirmado(self, state: GraphState) -> bool:
        """Verifica se o plantão está confirmado para permitir updates de dados"""
        response = state.sessao.get("response", "").lower()
        return response == "confirmado"
    
    def _chamar_get_schedule_started(self, state: GraphState) -> None:
        """Chama getScheduleStarted e preenche dados da sessão"""
        telefone = state.sessao.get("telefone")
        if not telefone:
            logger.error("Telefone não encontrado na sessão")
            raise Exception("Telefone é obrigatório para buscar dados da sessão")
        
        logger.info("Chamando getScheduleStarted", telefone=telefone)
        
        try:
            result = self.http_client.get_schedule_started(
                self.lambda_get_schedule_url, 
                telefone
            )
            
            # Preenche dados da sessão
            response_status = result.get("response", "").lower()
            shift_allow = result.get("shiftAllow", True)
            
            # Lógica correta: só permite se shiftAllow=true E response="confirmado"
            turno_realmente_permitido = shift_allow and response_status == "confirmado"
            
            state.sessao.update({
                "schedule_id": result.get("scheduleID"),
                "report_id": result.get("reportID"),
                "patient_id": result.get("patientID"),
                "caregiver_id": result.get("caregiverID"),
                "data_relatorio": result.get("reportDate"),
                "response": result.get("response"),  # Status do plantão
                "shift_allow": shift_allow,  # True/False do backend
                "empresa": result.get("company"),
                "cooperativa": result.get("cooperative")
            })
            
            # Debug: mostrar dados extraídos
            logger.info("Dados extraídos do getScheduleStarted",
                       schedule_id=state.sessao.get("schedule_id"),
                       report_id=state.sessao.get("report_id"),
                       patient_id=state.sessao.get("patient_id"),
                       caregiver_id=state.sessao.get("caregiver_id"),
                       shift_allow=shift_allow,
                       response_status=response_status,
                       empresa=state.sessao.get("empresa"))
            
            logger.info("Lógica de permissão aplicada",
                       shift_allow_original=shift_allow,
                       response=response_status,
                       plantao_confirmado=self._plantao_confirmado(state),
                       formula="shiftAllow AND response=='confirmado'")
            
        except Exception as e:
            logger.error("Erro ao chamar getScheduleStarted", telefone=telefone, error=str(e))
            # Em caso de erro, marca como não permitido para forçar fluxo auxiliar
            state.sessao["turno_permitido"] = False
            state.sessao["cancelado"] = True
            raise
    
    def _classificar_intencao(self, state: GraphState) -> str:
        """Classifica intenção usando LLM"""
        texto_usuario = state.entrada.get("texto_usuario", "")
        
        if not texto_usuario:
            logger.warning("Texto do usuário vazio, usando intenção auxiliar")
            return "auxiliar"
        
        intencao = self.intent_classifier.classificar_intencao(texto_usuario)
        state.roteador["intencao"] = intencao
        
        logger.info("Intenção classificada", 
                   texto=texto_usuario[:50],
                   intencao=intencao)
        
        return intencao
    
    def _aplicar_gates_deterministicos(self, state: GraphState, intencao: str) -> str:
        """
        Aplica gates determinísticos APÓS classificação
        Pode modificar a intenção baseado no estado
        """
        sessao = state.sessao
        
        # Gate 1: Se plantão cancelado -> auxiliar  
        if sessao.get("response") == "cancelado":
            logger.info("Plantão cancelado, redirecionando para auxiliar")
            return "auxiliar"
        
        # Gate 2: Se turno não permitido por falta de plantão -> auxiliar
        if not sessao.get("shift_allow", True):
            logger.info("Plantão não existe (shiftAllow=false), redirecionando para auxiliar")
            return "auxiliar"
        
        # Gate 3: Se plantão não confirmado -> sempre escala (para confirmação ou clínico)
        if not self._plantao_confirmado(state):
            response = sessao.get("response", "N/A")
            if intencao == "clinico":
                logger.info("Plantão não confirmado, redirecionando clínico para escala",
                           response=response)
            else:
                logger.info("Plantão não confirmado, direcionando para escala",
                           intencao_original=intencao, response=response)
            return "escala"
        
        # Gate 4: Se intenção é finalizar mas vitais incompletos -> clinico
        if intencao == "finalizar":
            vitais_completos = state.get_vitais_completos()
            if not vitais_completos:
                faltantes = state.get_vitais_faltantes()
                logger.info("Finalizar solicitado mas vitais incompletos",
                           faltantes=faltantes)
                
                # Configura retomada
                state.retomada = {
                    "fluxo": "finalizar",
                    "motivo": "precisa_vitais",
                    "faltantes": faltantes
                }
                
                return "clinico"
        
        # Se chegou até aqui, mantém intenção original
        return intencao
    
    def _preservar_dados_clinicos_se_necessario(self, state: GraphState) -> None:
        """
        🧠 LÓGICA INTELIGENTE: Preserva dados clínicos quando há confirmação pendente
        Independente de qual fluxo está pendente, sempre tenta extrair dados clínicos
        """
        try:
            texto_usuario = state.entrada.get("texto_usuario", "")
            if not texto_usuario:
                return
            
            # 🧠 PRESERVA SEMPRE que há dados clínicos, independente de pendente
            # Isso garante que dados não sejam perdidos em qualquer situação
            
            # Preservação silenciosa de dados clínicos
            
            # Import dinâmico para evitar dependências circulares
            # Extração clínica consolidada no ClinicalExtractor
            from app.llm.extractors import ClinicalExtractor
            import os
            
            # Criar extrator
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                return
            
            extractor = ClinicalExtractor(
                api_key=api_key,
                model=os.getenv("EXTRACTOR_MODEL", "gpt-4o-mini")
            )
            
            # Extrair dados clínicos
            resultado_extracao = extractor.extrair_clinico_completo(texto_usuario)
            
            # Verificar se encontrou dados relevantes
            vitais_encontrados = {}
            for campo, valor in resultado_extracao.get("vitais", {}).items():
                if valor is not None:
                    vitais_encontrados[campo] = valor
            
            nota_encontrada = resultado_extracao.get("nota")
            
            if not vitais_encontrados and not nota_encontrada:
                return  # Nada para preservar
            
            # Preservar no estado (mesclar com existentes)
            clinico_atual = state.clinico
            
            # Mesclar vitais (novos sobrescrevem antigos)
            for campo, valor in vitais_encontrados.items():
                clinico_atual["vitais"][campo] = valor
            
            # Atualizar nota se encontrada
            if nota_encontrada:
                clinico_atual["nota"] = nota_encontrada
            
            # Atualizar lista de faltantes
            campos_obrigatorios = ["PA", "FC", "FR", "Sat", "Temp"]
            faltantes = [
                campo for campo in campos_obrigatorios 
                if not clinico_atual["vitais"].get(campo)
            ]
            clinico_atual["faltantes"] = faltantes
            
            # Dados preservados silenciosamente
            
        except Exception as e:
            logger.error("Erro ao preservar dados clínicos no router", error=str(e))
    
    def _verificar_nota_operacional(self, state: GraphState) -> bool:
        """
        Verifica se o texto contém uma nota operacional que deve ser enviada instantaneamente
        """
        try:
            texto_usuario = state.entrada.get("texto_usuario", "")
            if not texto_usuario:
                return False
            
            is_operational, operational_note = self.operational_classifier.is_operational_note(texto_usuario)
            
            if is_operational and operational_note:
                # Armazena a nota operacional no estado para processamento
                state.operacional = {
                    "nota": operational_note,
                    "timestamp": state.entrada.get("timestamp"),
                    "tipo": "instantanea"
                }
                
                logger.info("Nota operacional detectada", 
                           nota=operational_note[:100],
                           session_id=state.sessao.get("session_id"))
                return True
                
            return False
            
        except Exception as e:
            logger.error("Erro ao verificar nota operacional", error=str(e))
            return False
    
    def rotear(self, state: GraphState) -> str:
        """
        Executa roteamento completo
        
        Returns:
            Nome do próximo subgrafo a executar
        """
        logger.info("Iniciando roteamento", 
                   session_id=state.sessao.get("session_id"),
                   tem_retomada=state.tem_retomada())
        
        # 0. 🧠 LÓGICA INTELIGENTE: Preserva dados clínicos ANTES de qualquer roteamento
        self._preservar_dados_clinicos_se_necessario(state)
        
        # 0.5. 🚨 NOTAS OPERACIONAIS: Verifica se há nota operacional para envio instantâneo
        nota_operacional = self._verificar_nota_operacional(state)
        if nota_operacional:
            return "operacional"  # Redireciona para subgrafo operacional
        
        # 1. Se há confirmação pendente, vai direto para o subgrafo correto
        if state.tem_pendente():
            fluxo_pendente = state.pendente["fluxo"]
            logger.info("ROUTER: Confirmação pendente detectada", 
                       fluxo=fluxo_pendente,
                       session_id=state.sessao.get("session_id"))
            return fluxo_pendente
        
        # 2. Se há retomada, pula classificação e despacha direto
        if state.tem_retomada():
            fluxo_retomada = state.retomada["fluxo"]
            motivo = state.retomada.get("motivo", "")
            logger.info("Retomada detectada", fluxo=fluxo_retomada, motivo=motivo)
            
            # Limpa retomada após usar
            state.retomada = None
            return fluxo_retomada
        
        # 3. Verifica se precisa buscar dados da sessão
        if not self._verificar_dados_sessao(state):
            logger.info("Dados da sessão faltando, chamando getScheduleStarted")
            self._chamar_get_schedule_started(state)
        
        # 4. Classifica intenção via LLM
        intencao = self._classificar_intencao(state)
        
        # 5. Aplica gates determinísticos
        intencao_final = self._aplicar_gates_deterministicos(state, intencao)
        
        # 6. Log do resultado final
        if intencao != intencao_final:
            logger.info("Intenção modificada por gates",
                       intencao_original=intencao,
                       intencao_final=intencao_final)
        
        # 7. Atualiza estado
        state.roteador["intencao"] = intencao_final
        
        logger.info("Roteamento concluído",
                   session_id=state.sessao.get("session_id"),
                   intencao_final=intencao_final)
        
        return intencao_final
