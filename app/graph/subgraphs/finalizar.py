"""
Subgrafo Finalizar
Finalização do plantão com coleta de tópicos de finalização
"""
from typing import Dict, Any, List
import structlog
import os

from app.graph.state import GraphState
from app.infra.http import LambdaHttpClient

logger = structlog.get_logger(__name__)


class FinalizarSubgraph:
    """Subgrafo para finalização do plantão"""
    
    def __init__(self, 
                 http_client: LambdaHttpClient,
                 lambda_get_note_report_url: str,
                 lambda_update_summary_url: str):
        self.http_client = http_client
        self.lambda_get_note_report_url = lambda_get_note_report_url
        self.lambda_update_summary_url = lambda_update_summary_url
        self.finalizacao_extractor = None  # Lazy loading
        logger.info("FinalizarSubgraph inicializado")
    
    def _get_finalizacao_extractor(self):
        """Lazy loading do FinalizacaoExtractor"""
        if self.finalizacao_extractor is None:
            api_key = os.getenv("OPENAI_API_KEY")
            if api_key:
                from app.llm.extractors.finalizacao import FinalizacaoExtractor
                self.finalizacao_extractor = FinalizacaoExtractor(api_key)
        return self.finalizacao_extractor
    
    def _recuperar_notas_existentes(self, state: GraphState) -> List[str]:
        """Recupera notas existentes do plantão via getNoteReport"""
        sessao = state.sessao
        report_id = sessao.get("report_id")
        report_date = sessao.get("data_relatorio")
        
        if not report_id or not report_date:
            logger.warning("report_id ou report_date não encontrados para buscar notas")
            return []
        
        try:
            logger.info("Recuperando notas existentes do plantão",
                       report_id=report_id,
                       report_date=report_date)
            
            result = self.http_client.get_note_report(
                self.lambda_get_note_report_url,
                report_id,
                report_date
            )
            
            notes = result.get("notes", [])
            notas_texto = [note.get("noteDescAI", "") for note in notes if note.get("noteDescAI")]
            
            logger.info("Notas recuperadas com sucesso",
                       total_notas=len(notas_texto))
            
            # Salva no estado para uso futuro
            state.finalizacao["notas_existentes"] = notas_texto
            
            return notas_texto
            
        except Exception as e:
            logger.error("Erro ao recuperar notas existentes", error=str(e))
            return []
    
    def _extrair_topicos_finalizacao(self, state: GraphState) -> Dict[str, Any]:
        """Extrai tópicos de finalização do texto do usuário"""
        extractor = self._get_finalizacao_extractor()
        if not extractor:
            logger.warning("FinalizacaoExtractor não disponível")
            return {}
        
        texto_usuario = state.entrada.get("texto_usuario", "")
        notas_existentes = state.finalizacao.get("notas_existentes", [])
        
        try:
            resultado = extractor.extrair_topicos(texto_usuario, notas_existentes)
            
            logger.info("Extração de tópicos concluída",
                       topicos_identificados=resultado.get("topicos_identificados", []))
            
            return resultado
            
        except Exception as e:
            logger.error("Erro na extração de tópicos", error=str(e))
            return {}
    
    def _atualizar_topicos_estado(self, state: GraphState, resultado_extracao: Dict[str, Any]) -> None:
        """Atualiza os tópicos no estado com os dados extraídos"""
        topicos_atuais = state.finalizacao["topicos"]
        faltantes_atuais = state.finalizacao["faltantes"]
        
        # Atualiza tópicos com novos dados (apenas se não for None)
        for topico, valor in resultado_extracao.items():
            if topico in topicos_atuais and valor is not None:
                topicos_atuais[topico] = valor
                
                # Remove da lista de faltantes
                if topico in faltantes_atuais:
                    faltantes_atuais.remove(topico)
        
        # Se não há dados extraídos, oferece opção de "Sem informações"
        topicos_identificados = resultado_extracao.get("topicos_identificados", [])
        if not topicos_identificados:
            # Pergunta sobre tópicos específicos ou permite marcar como "Sem informações"
            pass
        
        state.finalizacao["topicos"] = topicos_atuais
        state.finalizacao["faltantes"] = faltantes_atuais
        
        logger.info("Tópicos atualizados no estado",
                   preenchidos=len([t for t in topicos_atuais.values() if t is not None]),
                   faltantes=len(faltantes_atuais))
    
    def _enviar_para_webhook_n8n(self, state: GraphState, topico: str, informacao: str) -> None:
        """Envia informação específica para webhook n8n"""
        sessao = state.sessao
        
        # Formatar como nota clínica para ser compatível com updateClinicalData
        nota_formatada = f"[{topico.replace('_', ' ').title()}] {informacao}"
        
        payload = {
            "reportID": sessao.get("report_id"),
            "reportDate": sessao.get("data_relatorio"),
            "scheduleID": sessao.get("schedule_id"),
            "caregiverID": sessao.get("caregiver_id"),
            "patientID": sessao.get("patient_id"),
            "clinicalNote": nota_formatada,  # Usa clinicalNote em vez de topico/informacao
            # Campos opcionais para compatibilidade
            "noteType": "finalization",
            "topic": topico
        }
        
        try:
            webhook_url = "https://primary-production-031c.up.railway.app/webhook/8f70cfe8-9c88-403d-8282-0d9bd7b4311d"
            
            logger.info("Enviando tópico de finalização para n8n",
                       topico=topico,
                       informacao_length=len(informacao))
            
            result = self.http_client.post(webhook_url, payload)
            
            logger.info("Tópico enviado para n8n com sucesso", topico=topico)
            
        except Exception as e:
            logger.error("Erro ao enviar tópico para n8n", 
                        topico=topico, error=str(e))
    
    def _verificar_completude(self, state: GraphState) -> tuple[bool, List[str]]:
        """Verifica se todos os tópicos estão completos"""
        faltantes = state.finalizacao.get("faltantes", [])
        completo = len(faltantes) == 0
        
        return completo, faltantes
    
    def _preparar_payload_relatorio_final(self, state: GraphState) -> Dict[str, Any]:
        """Prepara payload final para updatereportsummaryad"""
        sessao = state.sessao
        topicos = state.finalizacao["topicos"]
        
        # Mapeia tópicos internos para campos do lambda
        payload = {
            "reportID": sessao.get("report_id"),
            "reportDate": sessao.get("data_relatorio"),
            "scheduleID": sessao.get("schedule_id"),
            "caregiverID": sessao.get("caregiver_id"),
            "patientID": sessao.get("patient_id"),
            "patientFirstName": "Paciente",  # Será preenchido pelo lambda
            "caregiverFirstName": "Cuidador",  # Será preenchido pelo lambda
            "shiftDay": "Hoje",  # Será preenchido pelo lambda
            "shiftStart": "00:00",  # Será preenchido pelo lambda
            "shiftEnd": "23:59",  # Será preenchido pelo lambda
            
            # Tópicos de finalização
            "foodHydrationSpecification": topicos.get("alimentacao_hidratacao") or "Sem informações",
            "stoolUrineSpecification": topicos.get("evacuacoes") or "Sem informações",
            "sleepSpecification": topicos.get("sono") or "Sem informações",
            "moodSpecification": topicos.get("humor") or "Sem informações",
            "medicationsSpecification": topicos.get("medicacoes") or "Sem informações",
            "activitiesSpecification": topicos.get("atividades") or "Sem informações",
            "additionalInformationSpecification": topicos.get("informacoes_clinicas_adicionais") or "Sem informações",
            "administrativeInfo": topicos.get("informacoes_administrativas") or "Sem informações"
        }
        
        logger.debug("Payload relatório final preparado",
                    report_id=sessao.get("report_id"),
                    topicos_preenchidos=len([v for v in topicos.values() if v is not None]))
        
        return payload
    
    def _executar_finalizacao_completa(self, state: GraphState) -> None:
        """Executa finalização completa do plantão"""
        pendente = state.pendente
        if not pendente or pendente.get("fluxo") != "finalizar":
            logger.error("Nenhuma finalização pendente")
            return
        
        payload = pendente.get("payload")
        
        try:
            logger.info("Executando finalização completa do plantão")
            
            # 1. Envia relatório final
            result = self.http_client.update_report_summary(
                self.lambda_update_summary_url,
                payload
            )
            
            # 2. Limpa pendente
            state.limpar_pendente()
            
            # 3. Limpa COMPLETAMENTE o estado (plantão finalizado)
            self._limpar_estado_completo(state)
            
            logger.info("Plantão finalizado com sucesso e estado limpo")
            
        except Exception as e:
            logger.error("Erro ao executar finalização completa", error=str(e))
            state.limpar_pendente()
            raise e
    
    def _limpar_estado_completo(self, state: GraphState) -> None:
        """
        Limpa completamente o estado após finalização do plantão
        DELETA o registro do DynamoDB para garantir limpeza total
        """
        session_id = state.sessao.get("session_id") or state.sessao.get("telefone")
        
        if not session_id:
            logger.warning("Não foi possível identificar session_id para deletar estado")
            return
        
        try:
            # DELETAR registro do DynamoDB em vez de resetar campos
            # Isso garante limpeza completa e novo início no próximo plantão
            logger.info("Deletando estado completo do DynamoDB após finalização",
                       session_id=session_id)
            
            # Nota: A deleção será feita pelo DynamoStateManager após este método
            # Aqui apenas marcamos que o estado deve ser deletado
            state.meta["delete_state_after_save"] = True
            
            logger.info("Estado marcado para deleção após finalização",
                       session_id=session_id)
            
        except Exception as e:
            logger.error("Erro ao marcar estado para deleção",
                        session_id=session_id,
                        error=str(e))
    
    def _gerar_resumo_topicos(self, state: GraphState) -> str:
        """Gera resumo dos tópicos coletados para confirmação"""
        topicos = state.finalizacao["topicos"]
        
        resumo_partes = ["Resumo da finalização:"]
        
        mapeamento_nomes = {
            "alimentacao_hidratacao": "Alimentação e Hidratação",
            "evacuacoes": "Evacuações",
            "sono": "Sono",
            "humor": "Humor",
            "medicacoes": "Medicações",
            "atividades": "Atividades",
            "informacoes_clinicas_adicionais": "Informações Clínicas",
            "informacoes_administrativas": "Informações Administrativas"
        }
        
        for topico, valor in topicos.items():
            nome_amigavel = mapeamento_nomes.get(topico, topico)
            valor_exibicao = valor if valor else "Sem informações"
            resumo_partes.append(f"• {nome_amigavel}: {valor_exibicao}")
        
        return "\n".join(resumo_partes)
    
    def processar(self, state: GraphState) -> str:
        """
        Processa subgrafo de finalização
        
        Fluxo:
        1. Recupera notas existentes (getNoteReport)
        2. Extrai tópicos via LLM
        3. Envia dados parciais para n8n
        4. Coleta tópicos faltantes
        5. Confirma e envia relatório final (updatereportsummaryad)
        6. Limpa estado completo
        
        Returns:
            Código para ser processado pelo fiscal
        """
        logger.info("Processando subgrafo finalizar")
        
        # Adiciona à lista de fluxos executados
        state.adicionar_fluxo_executado("finalizar")
        
        texto_usuario = state.entrada.get("texto_usuario", "")
        
        # Verifica se é resposta de confirmação final
        if state.tem_pendente() and state.pendente.get("fluxo") == "finalizar":
            try:
                from app.llm.classifiers import ConfirmationClassifier
                
                api_key = os.getenv("OPENAI_API_KEY")
                if api_key:
                    classifier = ConfirmationClassifier(
                        api_key=api_key,
                        model=os.getenv("INTENT_MODEL", "gpt-4o-mini")
                    )
                    
                    confirmacao = classifier.classificar_confirmacao(texto_usuario)
                    
                    if confirmacao == "sim":
                        self._executar_finalizacao_completa(state)
                        return "FINALIZATION_COMPLETED"  # Código para o Fiscal
                    elif confirmacao == "nao":
                        state.limpar_pendente()
                        return "FINALIZATION_CANCELLED"  # Código para o Fiscal
                    else:
                        return "FINALIZATION_CONFIRMATION_PENDING"  # Código para o Fiscal
                else:
                    return "FINALIZATION_CONFIRMATION_PENDING"
                    
            except Exception as e:
                logger.error("Erro ao classificar confirmação via LLM", error=str(e))
                return "FINALIZATION_CONFIRMATION_PENDING"
        
        # Primeira vez no fluxo de finalização - recupera notas existentes
        if not state.finalizacao.get("notas_existentes"):
            notas = self._recuperar_notas_existentes(state)
            logger.info("Notas existentes recuperadas", total=len(notas))
        
        # Extrai tópicos do texto atual
        resultado_extracao = self._extrair_topicos_finalizacao(state)
        
        if resultado_extracao:
            # Atualiza estado com tópicos extraídos
            self._atualizar_topicos_estado(state, resultado_extracao)
            
            # Envia tópicos identificados para webhook n8n
            topicos_identificados = resultado_extracao.get("topicos_identificados", [])
            for topico in topicos_identificados:
                if resultado_extracao.get(topico):
                    self._enviar_para_webhook_n8n(state, topico, resultado_extracao[topico])
        
        # Verifica se todos os tópicos estão completos
        completo, faltantes = self._verificar_completude(state)
        
        if not completo:
            # Ainda há tópicos faltantes
            logger.info("Tópicos faltantes para finalização", faltantes=faltantes)
            return "FINALIZATION_PARTIAL_DATA"  # Código para o Fiscal
        
        # Todos os tópicos estão completos - prepara confirmação final
        payload = self._preparar_payload_relatorio_final(state)
        
        state.pendente = {
            "fluxo": "finalizar",
            "payload": payload
        }
        
        return "FINALIZATION_READY_FOR_CONFIRMATION"  # Código para o Fiscal