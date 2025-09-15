"""
Tools para integração com os 4 Lambdas via HTTP
Implementação completa com timeout, retry e idempotência
"""
import os
import asyncio
import httpx
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

from app.graph.state import GraphState
from app.infra.logging import obter_logger, log_request, log_response
from app.infra.timeutils import agora_br
from app.infra.tpc import marcar_acao_executada
from app.infra.circuit_breaker import circuit_breaker, LAMBDA_CIRCUIT_CONFIG, CircuitBreakerError
from app.infra.cache import lambda_cache

logger = obter_logger(__name__)

# URLs dos Lambdas (via variáveis de ambiente)
LAMBDA_GET_SCHEDULE = os.getenv("LAMBDA_GET_SCHEDULE")
LAMBDA_UPDATE_SCHEDULE = os.getenv("LAMBDA_UPDATE_SCHEDULE") 
LAMBDA_UPDATE_CLINICAL = os.getenv("LAMBDA_UPDATE_CLINICAL")
LAMBDA_UPDATE_SUMMARY = os.getenv("LAMBDA_UPDATE_SUMMARY")

# Configurações
TIMEOUT_LAMBDAS = int(os.getenv("TIMEOUT_LAMBDAS", "30"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))


class LambdaError(Exception):
    """Exceção para erros de Lambda"""
    def __init__(self, lambda_name: str, status_code: int, response: str):
        self.lambda_name = lambda_name
        self.status_code = status_code
        self.response = response
        super().__init__(f"Erro no {lambda_name}: {status_code} - {response}")


async def fazer_requisicao_lambda(
    url: str,
    payload: Dict[str, Any],
    nome_lambda: str,
    timeout: int = TIMEOUT_LAMBDAS,
    max_retries: int = MAX_RETRIES
) -> Dict[str, Any]:
    """
    Faz requisição HTTP para Lambda com retry e logging
    """
    async with httpx.AsyncClient(timeout=timeout) as client:
        for tentativa in range(max_retries + 1):
            try:
                inicio = agora_br()
                
                log_request(
                    logger,
                    metodo="POST",
                    url=url,
                    payload=payload
                )
                
                response = await client.post(
                    url,
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )
                
                tempo_resposta = (agora_br() - inicio).total_seconds() * 1000
                
                log_response(
                    logger,
                    status_code=response.status_code,
                    response_data=response.json() if response.status_code < 500 else None,
                    tempo_resposta_ms=tempo_resposta
                )
                
                if response.status_code == 200:
                    return response.json()
                else:
                    # Se não é erro 5xx, não tentar novamente
                    if response.status_code < 500:
                        raise LambdaError(nome_lambda, response.status_code, response.text)
                    
                    # Para erro 5xx, tentar novamente se não é a última tentativa
                    if tentativa < max_retries:
                        await asyncio.sleep(2 ** tentativa)  # backoff exponencial
                        continue
                    else:
                        raise LambdaError(nome_lambda, response.status_code, response.text)
                        
            except httpx.TimeoutException:
                logger.error(
                    "Timeout na requisição Lambda",
                    lambda_name=nome_lambda,
                    tentativa=tentativa + 1,
                    max_tentativas=max_retries + 1
                )
                
                if tentativa < max_retries:
                    await asyncio.sleep(2 ** tentativa)
                    continue
                else:
                    raise LambdaError(nome_lambda, 408, "Timeout")
            
            except Exception as e:
                logger.error(
                    "Erro inesperado na requisição Lambda",
                    lambda_name=nome_lambda,
                    erro=str(e),
                    tentativa=tentativa + 1
                )
                
                if tentativa < max_retries:
                    await asyncio.sleep(2 ** tentativa)
                    continue
                else:
                    raise LambdaError(nome_lambda, 500, str(e))


@circuit_breaker("lambda_get_schedule", LAMBDA_CIRCUIT_CONFIG)
@lambda_cache(ttl=300)  # Cache por 5 minutos
async def _executar_get_schedule_started(numero_telefone: str) -> Dict[str, Any]:
    """Executa chamada para getScheduleStarted com circuit breaker"""
    payload = {"phoneNumber": numero_telefone}
    
    async with httpx.AsyncClient(timeout=TIMEOUT_LAMBDAS) as client:
        response = await client.post(LAMBDA_GET_SCHEDULE, json=payload)
        response.raise_for_status()
        return response.json()


def obter_dados_turno(estado: GraphState) -> GraphState:
    """
    Chama Lambda getScheduleStarted para obter dados do turno
    Função síncrona que wrappea a async
    """
    return asyncio.run(obter_dados_turno_async(estado))


async def obter_dados_turno_async(estado: GraphState) -> GraphState:
    """
    Chama Lambda getScheduleStarted para obter dados do turno
    """
    if not LAMBDA_GET_SCHEDULE:
        logger.error("URL do Lambda getScheduleStarted não configurada")
        raise ValueError("LAMBDA_GET_SCHEDULE não configurado")
    
    payload = {
        "phoneNumber": estado.core.numero_telefone
    }
    
    try:
        # Usar função protegida por circuit breaker
        response = await _executar_get_schedule_started(estado.core.numero_telefone)
        
        # Extrair dados da resposta e atualizar estado
        if "body" in response:
            body = response["body"]
            
            # Atualizar dados do core
            estado.core.caregiver_id = body.get("caregiverID")
            estado.core.schedule_id = body.get("scheduleID")
            estado.core.patient_id = body.get("patientID")
            estado.core.report_id = body.get("reportID")
            estado.core.data_relatorio = body.get("reportDate")
            estado.core.turno_permitido = body.get("shiftAllow", False)
            estado.core.turno_iniciado = body.get("scheduleStarted", False)
            estado.core.empresa = body.get("company")
            estado.core.cooperativa = body.get("cooperative")
            
            # Inferir se turno está cancelado baseado na resposta
            message = body.get("message", "")
            response_text = body.get("response", "")
            
            # Lógica para detectar cancelamento
            indicadores_cancelamento = [
                "cancelado", "cancelada", "não confirmado", "nao confirmado",
                "sem turno", "turno inexistente"
            ]
            
            texto_resposta = f"{message} {response_text}".lower()
            estado.core.cancelado = any(
                indicador in texto_resposta 
                for indicador in indicadores_cancelamento
            )
            
            # Atualizar metadados
            estado.metadados["presenca_confirmada"] = (
                estado.core.turno_permitido and 
                estado.core.turno_iniciado and 
                not estado.core.cancelado
            )
            
            logger.info(
                "Dados do turno obtidos com sucesso",
                schedule_id=estado.core.schedule_id,
                report_id=estado.core.report_id,
                turno_permitido=estado.core.turno_permitido,
                cancelado=estado.core.cancelado
            )
            
    except LambdaError as e:
        logger.error(
            "Erro ao obter dados do turno",
            erro=str(e)
        )
        # Manter estado atual em caso de erro
        
    return estado


@circuit_breaker("lambda_update_schedule", LAMBDA_CIRCUIT_CONFIG)
async def _executar_update_work_schedule(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Executa chamada para updateWorkScheduleResponse com circuit breaker"""
    async with httpx.AsyncClient(timeout=TIMEOUT_LAMBDAS) as client:
        response = await client.post(LAMBDA_UPDATE_SCHEDULE, json=payload)
        response.raise_for_status()
        return response.json()


async def atualizar_resposta_turno_async(
    estado: GraphState,
    resposta_valor: str  # "confirmado" ou "cancelado"
) -> Dict[str, Any]:
    """
    Chama Lambda updateWorkScheduleResponse para confirmar/cancelar presença
    """
    if not LAMBDA_UPDATE_SCHEDULE:
        logger.error("URL do Lambda updateWorkScheduleResponse não configurada")
        raise ValueError("LAMBDA_UPDATE_SCHEDULE não configurado")
    
    payload = {
        "scheduleIdentifier": estado.core.schedule_id,
        "responseValue": resposta_valor
    }
    
    try:
        # Usar função protegida por circuit breaker
        response = await _executar_update_work_schedule(payload)
        
        logger.info(
            "Resposta do turno atualizada",
            schedule_id=estado.core.schedule_id,
            resposta=resposta_valor
        )
        
        return response
        
    except LambdaError as e:
        logger.error(
            "Erro ao atualizar resposta do turno",
            schedule_id=estado.core.schedule_id,
            resposta=resposta_valor,
            erro=str(e)
        )
        raise


def determinar_cenario_clinical_data(
    tem_vitais: bool,
    tem_nota: bool,
    tem_sintomas: bool
) -> str:
    """
    Determina o cenário correto para updateClinicalData baseado nos dados disponíveis
    """
    if tem_vitais and tem_nota and tem_sintomas:
        return "VITAL_SIGNS_NOTE_SYMPTOMS"
    elif tem_vitais and tem_sintomas and not tem_nota:
        return "VITAL_SIGNS_SYMPTOMS"
    elif tem_vitais and tem_nota and not tem_sintomas:
        return "VITAL_SIGNS_NOTE"
    elif tem_vitais and not tem_nota and not tem_sintomas:
        return "VITAL_SIGNS_ONLY"
    elif not tem_vitais and tem_nota and tem_sintomas:
        return "NOTE_SYMPTOMS"
    elif not tem_vitais and not tem_nota and tem_sintomas:
        return "SYMPTOMS_ONLY"
    elif not tem_vitais and tem_nota and not tem_sintomas:
        return "NOTE_ONLY"
    else:
        # Caso padrão se nada foi fornecido
        return "VITAL_SIGNS_ONLY"


@circuit_breaker("lambda_update_clinical", LAMBDA_CIRCUIT_CONFIG)
async def _executar_update_clinical_data(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Executa chamada para updateClinicalData com circuit breaker"""
    async with httpx.AsyncClient(timeout=TIMEOUT_LAMBDAS) as client:
        response = await client.post(LAMBDA_UPDATE_CLINICAL, json=payload)
        response.raise_for_status()
        return response.json()


async def atualizar_dados_clinicos_async(
    estado: GraphState,
    dados_vitais: Optional[Dict[str, Any]] = None,
    nota_clinica: Optional[str] = None,
    sintomas_rag: Optional[list] = None
) -> Dict[str, Any]:
    """
    Chama Lambda updateClinicalData com dados clínicos
    """
    if not LAMBDA_UPDATE_CLINICAL:
        logger.error("URL do Lambda updateClinicalData não configurada")
        raise ValueError("LAMBDA_UPDATE_CLINICAL não configurado")
    
    # Determinar o que temos disponível
    tem_vitais = bool(dados_vitais)
    tem_nota = bool(nota_clinica and nota_clinica.strip())
    tem_sintomas = bool(sintomas_rag)
    
    # Determinar cenário
    cenario = determinar_cenario_clinical_data(tem_vitais, tem_nota, tem_sintomas)
    
    # Montar payload base
    payload = {
        "reportID": estado.core.report_id,
        "reportDate": estado.core.data_relatorio,
        "scenario": cenario
    }
    
    # Adicionar dados conforme cenário
    if tem_vitais:
        payload["vitalSigns"] = dados_vitais
    
    if tem_nota:
        payload["clinicalNote"] = nota_clinica
    
    if tem_sintomas:
        payload["SymptomReport"] = sintomas_rag
    
    try:
        # Usar função protegida por circuit breaker
        response = await _executar_update_clinical_data(payload)
        
        logger.info(
            "Dados clínicos atualizados",
            report_id=estado.core.report_id,
            cenario=cenario,
            tem_vitais=tem_vitais,
            tem_nota=tem_nota,
            tem_sintomas=tem_sintomas
        )
        
        return response
        
    except LambdaError as e:
        logger.error(
            "Erro ao atualizar dados clínicos",
            report_id=estado.core.report_id,
            cenario=cenario,
            erro=str(e)
        )
        raise


@circuit_breaker("lambda_update_summary", LAMBDA_CIRCUIT_CONFIG)
async def _executar_update_report_summary(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Executa chamada para updateReportSummaryAD com circuit breaker"""
    async with httpx.AsyncClient(timeout=TIMEOUT_LAMBDAS) as client:
        response = await client.post(LAMBDA_UPDATE_SUMMARY, json=payload)
        response.raise_for_status()
        return response.json()


async def finalizar_relatorio_async(
    estado: GraphState,
    dados_relatorio: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Chama Lambda updatereportsummaryad para finalizar plantão
    """
    if not LAMBDA_UPDATE_SUMMARY:
        logger.error("URL do Lambda updatereportsummaryad não configurada")
        raise ValueError("LAMBDA_UPDATE_SUMMARY não configurado")
    
    # Montar payload com dados do relatório
    payload = {
        "reportID": estado.core.report_id,
        "caregiverID": estado.core.caregiver_id,
        **dados_relatorio
    }
    
    try:
        # Usar função protegida por circuit breaker
        response = await _executar_update_report_summary(payload)
        
        logger.info(
            "Relatório finalizado",
            report_id=estado.core.report_id,
            caregiver_id=estado.core.caregiver_id
        )
        
        return response
        
    except LambdaError as e:
        logger.error(
            "Erro ao finalizar relatório",
            report_id=estado.core.report_id,
            erro=str(e)
        )
        raise


# Wrappers síncronos para uso nos fluxos LangGraph
def atualizar_resposta_turno(estado: GraphState, resposta_valor: str) -> Dict[str, Any]:
    """Wrapper síncrono para atualizar resposta do turno"""
    return asyncio.run(atualizar_resposta_turno_async(estado, resposta_valor))


def atualizar_dados_clinicos(
    estado: GraphState,
    dados_vitais: Optional[Dict[str, Any]] = None,
    nota_clinica: Optional[str] = None,
    sintomas_rag: Optional[list] = None
) -> Dict[str, Any]:
    """Wrapper síncrono para atualizar dados clínicos"""
    return asyncio.run(atualizar_dados_clinicos_async(
        estado, dados_vitais, nota_clinica, sintomas_rag
    ))


def finalizar_relatorio(estado: GraphState, dados_relatorio: Dict[str, Any]) -> Dict[str, Any]:
    """Wrapper síncrono para finalizar relatório"""
    return asyncio.run(finalizar_relatorio_async(estado, dados_relatorio))


# Função para executar ação pendente com idempotência
def executar_acao_pendente(estado: GraphState) -> GraphState:
    """
    Executa ação pendente se ela existe e pode ser executada
    Garante idempotência
    """
    acao = estado.aux.acao_pendente
    
    if not acao or acao.get("executado", False):
        logger.warning("Tentativa de executar ação já executada ou inexistente")
        return estado
    
    fluxo_destino = acao.get("fluxo_destino")
    payload = acao.get("payload", {})
    
    try:
        if fluxo_destino == "escala_commit":
            # Executar confirmação/cancelamento de presença
            resposta_valor = payload.get("responseValue")
            atualizar_resposta_turno(estado, resposta_valor)
            
            # Atualizar metadados
            if resposta_valor == "confirmado":
                estado.metadados["presenca_confirmada"] = True
                estado.core.cancelado = False
            else:
                estado.metadados["presenca_confirmada"] = False
                estado.core.cancelado = True
        
        elif fluxo_destino == "clinical_commit":
            # Executar salvamento de dados clínicos
            dados_vitais = payload.get("vitais")
            nota_clinica = payload.get("nota")
            sintomas = payload.get("sintomas")
            
            atualizar_dados_clinicos(estado, dados_vitais, nota_clinica, sintomas)
            
            # Marcar sinais vitais como realizados se foram enviados
            if dados_vitais:
                estado.metadados["sinais_vitais_realizados"] = True
        
        elif fluxo_destino == "finalizar_commit":
            # Executar finalização do relatório
            finalizar_relatorio(estado, payload)
            
            # Marcar como finalizado
            estado.metadados["plantao_finalizado"] = True
        
        # Marcar ação como executada
        marcar_acao_executada(acao)
        
        logger.info(
            "Ação pendente executada com sucesso",
            fluxo_destino=fluxo_destino
        )
        
    except Exception as e:
        logger.error(
            "Erro ao executar ação pendente",
            fluxo_destino=fluxo_destino,
            erro=str(e)
        )
        # Manter ação pendente para nova tentativa
        raise
    
    return estado
