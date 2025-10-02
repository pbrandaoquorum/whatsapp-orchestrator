"""
Subgrafo Fora de Escala
Gerencia plantões cancelados (com substituição) e "sem lembretes"
"""
import json
import structlog

from app.graph.state import GraphState
from app.infra.http import LambdaHttpClient

logger = structlog.get_logger(__name__)


class ForaEscalaSubgraph:
    """Subgrafo para lidar com plantões cancelados e fora de horário"""
    
    def __init__(self, http_client: LambdaHttpClient, create_schedule_url: str):
        self.http_client = http_client
        self.create_schedule_url = create_schedule_url
        logger.info("ForaEscalaSubgraph inicializado")
    
    def _parse_substitute_info(self, substitute_info_str: str) -> list:
        """
        Parse do substituteInfo retornado pelo getScheduleStarted
        
        Formatos esperados:
        - "[{\"caregiverIdentifier\":\"123\",\"caregiverName\":\"João Silva\"}]"
        - "Nao há profissionais substitutos"
        - ""
        
        Returns:
            Lista de dicionários com caregiverIdentifier e caregiverName
        """
        if not substitute_info_str or substitute_info_str == "Nao há profissionais substitutos":
            return []
        
        try:
            # Remove escapes extras se houver
            cleaned = substitute_info_str.replace('\\"', '"')
            substitutes = json.loads(cleaned)
            
            if not isinstance(substitutes, list):
                logger.warning("substituteInfo não é uma lista", data=substitute_info_str)
                return []
            
            logger.info("Substitutos parseados com sucesso", 
                       count=len(substitutes),
                       substitutes=substitutes)
            return substitutes
        
        except json.JSONDecodeError as e:
            logger.error("Erro ao fazer parse de substituteInfo", 
                        error=str(e), 
                        data=substitute_info_str)
            return []
    
    def _formatar_lista_substitutos(self, substitutes: list) -> str:
        """Formata lista de substitutos para apresentação ao usuário"""
        if not substitutes:
            return ""
        
        lines = ["Substitutos disponíveis:\n"]
        for idx, sub in enumerate(substitutes, 1):
            name = sub.get("caregiverName", "Nome não disponível")
            lines.append(f"{idx}. {name}")
        
        return "\n".join(lines)
    
    def _identificar_substituto_escolhido(self, texto_usuario: str, substitutes: list) -> dict:
        """
        Identifica qual substituto o usuário escolheu
        
        Aceita:
        - Número: "1", "2", "3"
        - Nome parcial: "raphael", "pepe"
        - Nome completo: "Raphael Quintanilha"
        
        Returns:
            Dicionário com caregiverIdentifier e caregiverName, ou None
        """
        texto_lower = texto_usuario.lower().strip()
        
        # Tenta match por número
        if texto_lower.isdigit():
            idx = int(texto_lower) - 1
            if 0 <= idx < len(substitutes):
                logger.info("Substituto identificado por número", 
                           numero=texto_lower, 
                           substituto=substitutes[idx])
                return substitutes[idx]
        
        # Tenta match por nome (parcial ou completo)
        for sub in substitutes:
            name = sub.get("caregiverName", "").lower()
            if texto_lower in name or name in texto_lower:
                logger.info("Substituto identificado por nome", 
                           texto=texto_usuario, 
                           substituto=sub)
                return sub
        
        logger.warning("Nenhum substituto identificado", 
                      texto=texto_usuario,
                      substitutes_count=len(substitutes))
        return None
    
    def _criar_nova_escala(self, schedule_id: str, new_caregiver_id: str) -> bool:
        """
        Chama o lambda createNewSchedule para criar uma nova escala para o substituto
        
        Args:
            schedule_id: ID do plantão cancelado
            new_caregiver_id: ID do caregiver substituto
        
        Returns:
            True se criado com sucesso, False caso contrário
        """
        try:
            payload = {
                "scheduleIdentifier": schedule_id,
                "newCaregiverID": new_caregiver_id
            }
            
            logger.info("Criando nova escala para substituto",
                       schedule_id=schedule_id,
                       new_caregiver_id=new_caregiver_id)
            
            response = self.http_client.post(self.create_schedule_url, payload)
            
            logger.info("Nova escala criada com sucesso",
                       schedule_id=schedule_id,
                       new_caregiver_id=new_caregiver_id,
                       response=response)
            
            return True
        
        except Exception as e:
            logger.error("Erro ao criar nova escala",
                        schedule_id=schedule_id,
                        new_caregiver_id=new_caregiver_id,
                        error=str(e))
            return False
    
    def processar(self, state: GraphState) -> str:
        """
        Processa fluxo "Fora de Escala"
        
        Cenários:
        1. Plantão "sem lembretes": Informa que está fora de horário
        2. Plantão "cancelado" SEM substitutos: Informa cancelamento
        3. Plantão "cancelado" COM substitutos: 
           - Pergunta se quer escolher substituto
           - Se sim, cria nova escala
        
        Returns:
            Código de resultado para o Fiscal processar
        """
        logger.info("Processando subgrafo fora de escala")
        
        # Adiciona à lista de fluxos executados
        state.adicionar_fluxo_executado("fora_escala")
        
        response_status = state.sessao.get("response", "").lower()
        texto_usuario = state.entrada.get("texto_usuario", "").strip()
        
        # === CENÁRIO 1: SEM LEMBRETES (fora de horário) ===
        if response_status == "sem lembretes":
            logger.info("Plantão sem lembretes - fora de horário")
            return "OUT_OF_SCHEDULE"
        
        # === CENÁRIO 2 e 3: PLANTÃO CANCELADO ===
        if response_status == "cancelado":
            # Verifica se a substituição já foi concluída
            substituicao_concluida = state.meta.get("substituicao_concluida", False)
            
            if substituicao_concluida:
                logger.info("Plantão cancelado mas substituição já foi concluída")
                return "SUBSTITUTION_ALREADY_DONE"
            logger.info("Plantão cancelado detectado")
            
            # Verifica se já está no fluxo de escolha de substituto
            aguardando_substituto = state.meta.get("aguardando_escolha_substituto", False)
            
            if aguardando_substituto:
                # Usuário está respondendo sobre escolha de substituto
                substitutes = state.meta.get("substitutos_disponiveis", [])
                
                # Verifica se usuário quer escolher substituto
                resposta_lower = texto_usuario.lower()
                negativas = ["não", "nao", "n", "não quero", "nao quero", "nenhum"]
                
                if any(neg in resposta_lower for neg in negativas):
                    # Usuário não quer escolher substituto
                    logger.info("Usuário não quer escolher substituto")
                    state.meta["aguardando_escolha_substituto"] = False
                    state.meta["substitutos_disponiveis"] = []
                    # Marca que o processo de substituição foi concluído (usuário recusou)
                    state.meta["substituicao_concluida"] = True
                    return "CANCELLED_NO_SUBSTITUTE_CHOSEN"
                
                # Tenta identificar substituto escolhido
                substituto = self._identificar_substituto_escolhido(texto_usuario, substitutes)
                
                if not substituto:
                    # Não conseguiu identificar - pede para tentar novamente
                    logger.warning("Substituto não identificado - pedindo nova tentativa")
                    return "SUBSTITUTE_NOT_IDENTIFIED"
                
                # Substituto identificado - cria nova escala
                schedule_id = state.sessao.get("schedule_id")
                new_caregiver_id = substituto.get("caregiverIdentifier")
                
                sucesso = self._criar_nova_escala(schedule_id, new_caregiver_id)
                
                # Limpa estado de escolha de substituto
                state.meta["aguardando_escolha_substituto"] = False
                state.meta["substitutos_disponiveis"] = []
                state.meta["substituto_escolhido"] = substituto.get("caregiverName", "")
                
                if sucesso:
                    # Marca que a substituição foi concluída
                    state.meta["substituicao_concluida"] = True
                    logger.info("Nova escala criada com sucesso - substituição marcada como concluída", 
                               substituto=substituto)
                    return "SUBSTITUTE_SCHEDULE_CREATED"
                else:
                    logger.error("Erro ao criar nova escala")
                    return "SUBSTITUTE_SCHEDULE_ERROR"
            
            else:
                # Primeira vez - verifica se há substitutos disponíveis
                substitute_info_str = state.sessao.get("substitute_info", "")
                substitutes = self._parse_substitute_info(substitute_info_str)
                
                if not substitutes:
                    # Sem substitutos disponíveis
                    logger.info("Plantão cancelado sem substitutos disponíveis")
                    return "CANCELLED_NO_SUBSTITUTES"
                
                # Há substitutos - prepara para perguntar ao usuário
                logger.info("Plantão cancelado com substitutos disponíveis", 
                           count=len(substitutes))
                
                # Salva substitutos no estado
                state.meta["aguardando_escolha_substituto"] = True
                state.meta["substitutos_disponiveis"] = substitutes
                state.meta["lista_substitutos_formatada"] = self._formatar_lista_substitutos(substitutes)
                
                return "CANCELLED_WITH_SUBSTITUTES"
        
        # Fallback: não deveria chegar aqui
        logger.warning("Fluxo fora de escala acionado sem cenário válido", 
                      response=response_status)
        return "UNKNOWN_OUT_OF_SCHEDULE_SCENARIO"

