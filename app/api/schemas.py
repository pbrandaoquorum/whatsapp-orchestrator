"""
Schemas Pydantic para validação de requests/responses da API
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime


class WhatsAppMessage(BaseModel):
    """Schema para mensagem recebida do WhatsApp"""
    message_id: str = Field(..., description="ID único da mensagem")
    phoneNumber: str = Field(..., description="Número de telefone do usuário")
    text: str = Field(..., description="Texto da mensagem")
    meta: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Metadados adicionais")


class WhatsAppResponse(BaseModel):
    """Schema para resposta ao WhatsApp"""
    success: bool = Field(..., description="Se o processamento foi bem-sucedido")
    message: str = Field(..., description="Mensagem de resposta para o usuário")
    session_id: Optional[str] = Field(None, description="ID da sessão")
    next_action: Optional[str] = Field(None, description="Próxima ação sugerida")


class TemplateSent(BaseModel):
    """Schema para notificação de template enviado"""
    phoneNumber: str = Field(..., description="Número de telefone do destinatário")
    template: str = Field(..., description="Tipo de template enviado")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Metadados do template")


class TemplateResponse(BaseModel):
    """Schema para resposta da notificação de template"""
    success: bool = Field(..., description="Se a atualização foi bem-sucedida")
    message: str = Field(..., description="Mensagem de confirmação")
    state_updated: bool = Field(..., description="Se o estado foi atualizado")


class GraphDebugRequest(BaseModel):
    """Schema para request de debug do grafo"""
    phoneNumber: str = Field(..., description="Número de telefone para teste")
    text: str = Field(..., description="Texto da mensagem para processar")
    initial_state: Optional[Dict[str, Any]] = Field(None, description="Estado inicial personalizado")


class GraphDebugResponse(BaseModel):
    """Schema para resposta de debug do grafo"""
    success: bool = Field(..., description="Se o processamento foi bem-sucedido")
    initial_state: Dict[str, Any] = Field(..., description="Estado inicial")
    final_state: Dict[str, Any] = Field(..., description="Estado final")
    execution_path: list = Field(..., description="Caminho de execução")
    response_message: str = Field(..., description="Mensagem de resposta")
    execution_time_ms: float = Field(..., description="Tempo de execução em milissegundos")


class HealthResponse(BaseModel):
    """Schema para resposta de health check"""
    status: str = Field(..., description="Status do serviço")
    timestamp: datetime = Field(..., description="Timestamp da verificação")
    version: str = Field(..., description="Versão da aplicação")
    dependencies: Dict[str, str] = Field(..., description="Status das dependências")


class ReadinessResponse(BaseModel):
    """Schema para resposta de readiness check"""
    ready: bool = Field(..., description="Se o serviço está pronto")
    timestamp: datetime = Field(..., description="Timestamp da verificação")
    checks: Dict[str, bool] = Field(..., description="Resultado dos checks individuais")
    details: Dict[str, Any] = Field(default_factory=dict, description="Detalhes dos checks")


class ErrorResponse(BaseModel):
    """Schema para resposta de erro"""
    success: bool = Field(False, description="Sempre False para erros")
    error: str = Field(..., description="Tipo do erro")
    message: str = Field(..., description="Mensagem de erro")
    details: Optional[Dict[str, Any]] = Field(None, description="Detalhes adicionais do erro")
    timestamp: datetime = Field(default_factory=datetime.now, description="Timestamp do erro")


class SyncRequest(BaseModel):
    """Schema para request de sincronização RAG"""
    sheets_id: Optional[str] = Field(None, description="ID da planilha (usa padrão se None)")
    aba_name: str = Field("Sintomas", description="Nome da aba a sincronizar")
    force: bool = Field(False, description="Forçar sincronização mesmo se recente")


class SyncResponse(BaseModel):
    """Schema para resposta de sincronização RAG"""
    success: bool = Field(..., description="Se a sincronização foi bem-sucedida")
    sintomas_carregados: int = Field(0, description="Número de sintomas carregados do Sheets")
    sintomas_inseridos: int = Field(0, description="Número de sintomas inseridos no Pinecone")
    vectors_antes: int = Field(0, description="Número de vetores antes da sincronização")
    vectors_depois: int = Field(0, description="Número de vetores após a sincronização")
    tempo_execucao_ms: float = Field(0, description="Tempo de execução em milissegundos")
    detalhes: Optional[Dict[str, Any]] = Field(None, description="Detalhes adicionais")


class SearchRequest(BaseModel):
    """Schema para request de busca de sintomas"""
    query: str = Field(..., description="Termo de busca")
    k: int = Field(5, description="Número máximo de resultados")
    threshold: float = Field(0.7, description="Limiar mínimo de similaridade")


class SymptomMatch(BaseModel):
    """Schema para um sintoma encontrado"""
    symptomDefinition: str = Field(..., description="Definição do sintoma")
    altNotepadMain: str = Field(..., description="Termo buscado")
    symptomCategory: str = Field("Geral", description="Categoria do sintoma")
    symptomSubCategory: str = Field("Geral", description="Subcategoria do sintoma")
    descricaoComparada: str = Field(..., description="Descrição comparada")
    coeficienteSimilaridade: float = Field(..., description="Coeficiente de similaridade")


class SearchResponse(BaseModel):
    """Schema para resposta de busca de sintomas"""
    success: bool = Field(..., description="Se a busca foi bem-sucedida")
    query: str = Field(..., description="Termo buscado")
    results: list[SymptomMatch] = Field(..., description="Sintomas encontrados")
    total_found: int = Field(..., description="Total de sintomas encontrados")
    execution_time_ms: float = Field(..., description="Tempo de execução em milissegundos")
