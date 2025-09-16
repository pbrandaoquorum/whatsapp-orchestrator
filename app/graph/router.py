"""
Router determinístico com classificação semântica via LLM leve
State machine explícita + regras hard-coded + classificação semântica inteligente
"""
import asyncio
from typing import Dict, Any, Optional
from app.graph.state import GraphState
from app.graph.semantic_classifier import classify_semantic, map_intent_to_flow, IntentType
from app.graph.clinical_extractor import SINAIS_VITAIS_OBRIGATORIOS
from app.graph.tools import obter_dados_turno  # Lambda getScheduleStarted
from app.infra.confirm import is_yes, is_no
from app.infra.timeutils import agora_br
from app.infra.logging import obter_logger

logger = obter_logger(__name__)


def presenca_confirmada(estado: GraphState) -> bool:
    """Verifica se a presença foi confirmada"""
    # Método 1: Flag explícita nos metadados
    if estado.metadados.get("presenca_confirmada", False):
        return True
    
    # Método 2: Inferir do estado do core
    return bool(
        estado.core.turno_permitido and 
        estado.core.turno_iniciado and 
        not estado.core.cancelado
    )


def sinais_vitais_realizados(estado: GraphState) -> bool:
    """Verifica se os sinais vitais foram completamente coletados"""
    # Método 1: Flag explícita nos metadados
    if estado.metadados.get("sinais_vitais_realizados", False):
        return True
    
    # Método 2: Verificar se todos os sinais obrigatórios estão presentes
    processados = estado.vitais.processados
    return all(sv in processados for sv in SINAIS_VITAIS_OBRIGATORIOS)


def garantir_bootstrap_sessao(estado: GraphState) -> GraphState:
    """Garante que a sessão foi inicializada com dados do Lambda"""
    if not estado.core.schedule_id or not estado.core.report_id:
        logger.info(
            "Bootstrap necessário",
            numero_telefone=estado.core.numero_telefone,
            session_id=estado.core.session_id
        )
        
        # Chamar lambda getScheduleStarted
        estado = obter_dados_turno(estado)
        
        logger.info(
            "Bootstrap concluído",
            schedule_id=estado.core.schedule_id,
            report_id=estado.core.report_id,
            turno_permitido=estado.core.turno_permitido,
            cancelado=estado.core.cancelado
        )
    
    return estado


def processar_retomada_pendente(estado: GraphState) -> str:
    """Processa retomada pendente se existir"""
    if not estado.aux.retomar_apos:
        return None
    
    retomar = estado.aux.retomar_apos
    fluxo_destino = retomar.get("flow")
    motivo = retomar.get("reason", "desconhecido")
    
    logger.info(
        "Retomando fluxo pendente",
        fluxo_destino=fluxo_destino,
        motivo=motivo
    )
    
    # Limpar retomada após usar
    estado.aux.retomar_apos = None
    
    return fluxo_destino


async def processar_pergunta_pendente(estado: GraphState) -> str:
    """Processa pergunta pendente (two-phase commit ou coleta incremental)"""
    if not estado.aux.ultima_pergunta:
        return None
    
    texto = estado.texto_usuario or ""
    
    # Caso 1: Two-phase commit (confirmação de ação)
    if estado.aux.acao_pendente:
        # Usar classificação semântica para confirmações
        try:
            resultado = await classify_semantic(texto, estado)
            
            if resultado.intent == IntentType.CONFIRMACAO_SIM:
                fluxo_destino = estado.aux.acao_pendente.get("fluxo_destino")
                logger.info(
                    "Ação confirmada semanticamente",
                    fluxo_destino=fluxo_destino,
                    confidence=resultado.confidence
                )
                return fluxo_destino
            
            elif resultado.intent == IntentType.CONFIRMACAO_NAO:
                logger.info("Ação cancelada semanticamente", confidence=resultado.confidence)
                # Limpar ação pendente
                estado.aux.acao_pendente = None
                estado.aux.ultima_pergunta = None
                estado.aux.fluxo_que_perguntou = None
                estado.router.intencao = "cancelado"
                return "auxiliar"
        
        except Exception as e:
            logger.error(f"Erro na classificação semântica de confirmação: {e}")
            # Sem fallback - retornar auxiliar para nova tentativa
            return "auxiliar"
    
    # Caso 2: Coleta incremental de sinais vitais
    if estado.aux.fluxo_que_perguntou == "clinical":
        try:
            # Usar classificação semântica para detectar sinais vitais
            resultado = await classify_semantic(texto, estado)
            
            if resultado.intent == IntentType.SINAIS_VITAIS and resultado.vital_signs:
                # Merge dos sinais vitais parciais
                estado.vitais.processados.update(resultado.vital_signs)
                
                # Recalcular faltantes
                SINAIS_VITAIS_OBRIGATORIOS = ["PA", "FC", "FR", "Sat", "Temp"]
                estado.vitais.faltantes = [
                    sv for sv in SINAIS_VITAIS_OBRIGATORIOS 
                    if sv not in estado.vitais.processados
                ]
                
                logger.info(
                    "Sinais vitais incrementais coletados semanticamente",
                    novos_sinais=list(resultado.vital_signs.keys()),
                    total_coletados=len(estado.vitais.processados),
                    faltantes=len(estado.vitais.faltantes),
                    confidence=resultado.confidence
                )
                
                # Se completo, limpar pergunta e ir para clinical
                if len(estado.vitais.faltantes) == 0:
                    estado.aux.ultima_pergunta = None
                    estado.aux.fluxo_que_perguntou = None
                    return "clinical"
                else:
                    # Ainda faltam sinais, continuar no auxiliar
                    estado.router.intencao = "coleta_incremental"
                    return "auxiliar"
        
        except Exception as e:
            logger.error(f"Erro na classificação semântica de sinais vitais: {e}")
            # Sem fallback - manter no auxiliar para nova tentativa
            return "auxiliar"
    
    return None


async def processar_classificacao_semantica(estado: GraphState) -> Optional[str]:
    """Processa classificação semântica via LLM leve"""
    texto = estado.texto_usuario or ""
    
    if not texto.strip():
        return None
    
    try:
        # Classificação semântica
        resultado = await classify_semantic(texto, estado)
        
        logger.info(
            "Classificação semântica concluída",
            intent=resultado.intent,
            confidence=resultado.confidence,
            rationale=resultado.rationale,
            session_id=estado.core.session_id
        )
        
        # Atualizar estado com dados extraídos
        if resultado.vital_signs:
            # Processar sinais vitais detectados semanticamente
            return processar_sinais_vitais_semanticos(estado, resultado.vital_signs)
        
        # Mapear intenção para fluxo
        fluxo = map_intent_to_flow(resultado.intent)
        
        # Atualizar estado do router
        estado.router.intencao = resultado.intent
        
        return fluxo
        
    except Exception as e:
        logger.error(f"Erro na classificação semântica: {e}")
        return "auxiliar"  # Sem fallback - apenas auxiliar


def processar_sinais_vitais_semanticos(estado: GraphState, vital_signs: Dict[str, Any]) -> str:
    """Processa sinais vitais detectados semanticamente"""
    logger.info(
        "Sinais vitais detectados semanticamente",
        sinais_detectados=list(vital_signs.keys())
    )
    
    # Verificar se presença foi confirmada
    if not presenca_confirmada(estado):
        logger.info(
            "Sinais vitais detectados mas presença não confirmada",
            guardando_em_buffer=True
        )
        
        # Guardar em buffer e exigir presença primeiro
        estado.aux.buffers["vitals"] = vital_signs
        estado.aux.retomar_apos = {
            "flow": "clinical",
            "reason": "need_presence_first",
            "ts": agora_br().isoformat()
        }
        estado.router.intencao = "escala"
        return "escala"
    else:
        # Presença confirmada, processar sinais vitais
        estado.vitais.processados.update(vital_signs)
        
        # Recalcular faltantes
        SINAIS_VITAIS_OBRIGATORIOS = ["PA", "FC", "FR", "Sat", "Temp"]
        estado.vitais.faltantes = [
            sv for sv in SINAIS_VITAIS_OBRIGATORIOS 
            if sv not in estado.vitais.processados
        ]
        
        estado.router.intencao = "sinais_vitais"
        return "clinical"


def aplicar_gates_pos_classificacao(intencao: str, estado: GraphState) -> str:
    """Aplica gates de negócio após classificação LLM"""
    
    # Gate 1: Turno cancelado ou não permitido
    if estado.core.cancelado or not estado.core.turno_permitido:
        if intencao not in ["auxiliar"]:
            logger.info(
                "Intenção bloqueada - turno não permitido",
                intencao_original=intencao,
                turno_cancelado=estado.core.cancelado,
                turno_permitido=estado.core.turno_permitido
            )
            return "auxiliar"
    
    # Gate 2: Presença não confirmada
    if intencao in ["clinical", "sinais_vitais", "notas", "finalizar"]:
        if not presenca_confirmada(estado):
            logger.info(
                "Intenção requer presença confirmada",
                intencao_original=intencao,
                redirecionando_para="escala"
            )
            
            # Guardar intenção para retomar após confirmar presença
            mapeamento_retomada = {
                "clinical": "clinical",
                "sinais_vitais": "clinical",
                "notas": "notas",
                "finalizar": "finalizar"
            }
            
            estado.aux.retomar_apos = {
                "flow": mapeamento_retomada.get(intencao, "clinical"),
                "reason": "need_presence_first",
                "ts": agora_br().isoformat()
            }
            return "escala"
    
    # Gate 3: Finalizar sem sinais vitais
    if intencao == "finalizar":
        if not sinais_vitais_realizados(estado):
            logger.info(
                "Finalização requer sinais vitais completos",
                redirecionando_para="clinical"
            )
            
            estado.aux.retomar_apos = {
                "flow": "finalizar",
                "reason": "vitals_before_finish",
                "ts": agora_br().isoformat()
            }
            return "clinical"
    
    return intencao


def mapear_intencao_para_fluxo(intencao: str) -> str:
    """Mapeia intenção final para nome do fluxo/nó"""
    mapeamento = {
        "escala": "escala",
        "sinais_vitais": "clinical",
        "clinical": "clinical",
        "notas": "notas",
        "finalizar": "finalizar",
        "auxiliar": "auxiliar"
    }
    
    return mapeamento.get(intencao, "auxiliar")


async def route(estado: GraphState) -> str:
    """
    Função principal do router - implementação completa com classificação semântica
    """
    logger.info(
        "Iniciando roteamento",
        texto_usuario=estado.texto_usuario[:100] if estado.texto_usuario else None,
        session_id=estado.core.session_id
    )
    
    # Passo 0: Garantir bootstrap da sessão
    estado = garantir_bootstrap_sessao(estado)
    
    # Passo 1: Verificar retomada pendente (maior prioridade)
    fluxo_retomada = processar_retomada_pendente(estado)
    if fluxo_retomada:
        logger.info("Roteamento: retomada pendente", fluxo=fluxo_retomada)
        return fluxo_retomada
    
    # Passo 2: Processar pergunta pendente (two-phase commit ou coleta incremental)
    fluxo_pergunta = await processar_pergunta_pendente(estado)
    if fluxo_pergunta:
        logger.info("Roteamento: pergunta pendente", fluxo=fluxo_pergunta)
        return fluxo_pergunta
    
    # Passo 3: Classificação semântica via LLM leve
    logger.info("Executando classificação semântica")
    fluxo_semantico = await processar_classificacao_semantica(estado)
    if fluxo_semantico:
        logger.info("Roteamento: classificação semântica", fluxo=fluxo_semantico)
        intencao_semantica = estado.router.intencao
    else:
        logger.warning("Classificação semântica falhou - usando fallback")
        intencao_semantica = "indefinido"
        fluxo_semantico = "auxiliar"
    
    # Passo 4: Aplicar gates de negócio pós-classificação
    intencao_final = aplicar_gates_pos_classificacao(intencao_semantica, estado)
    
    # Passo 5: Determinar fluxo final
    if intencao_final != intencao_semantica:
        # Gates modificaram a intenção
        fluxo_final = mapear_intencao_para_fluxo(intencao_final)
    else:
        # Usar fluxo da classificação semântica
        fluxo_final = fluxo_semantico
    
    # Atualizar estado do router
    estado.router.intencao = intencao_final
    estado.router.ultimo_fluxo = fluxo_final
    
    logger.info(
        "Roteamento concluído",
        intencao_semantica=intencao_semantica,
        intencao_final=intencao_final,
        fluxo_final=fluxo_final
    )
    
    return fluxo_final


# Função auxiliar para recuperar sinais vitais do buffer
def recuperar_sinais_vitais_do_buffer(estado: GraphState) -> None:
    """Recupera sinais vitais guardados no buffer após confirmar presença"""
    if "vitals" in estado.aux.buffers:
        vitais_buffer = estado.aux.buffers["vitals"]
        estado.vitais.processados.update(vitais_buffer)
        
        # Recalcular faltantes
        estado.vitais.faltantes = [
            sv for sv in SINAIS_VITAIS_OBRIGATORIOS 
            if sv not in estado.vitais.processados
        ]
        
        # Limpar buffer
        del estado.aux.buffers["vitals"]
        
        logger.info(
            "Sinais vitais recuperados do buffer",
            sinais_recuperados=list(vitais_buffer.keys()),
            total_coletados=len(estado.vitais.processados)
        )
