"""
Estado canônico do grafo LangGraph com validação Pydantic v2
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any


class CoreState(BaseModel):
    """Estado central da sessão"""
    session_id: Optional[str] = None
    numero_telefone: Optional[str] = None
    caregiver_id: Optional[str] = None
    schedule_id: Optional[str] = None
    patient_id: Optional[str] = None
    report_id: Optional[str] = None
    data_relatorio: Optional[str] = None
    turno_permitido: Optional[bool] = None
    turno_iniciado: Optional[bool] = None
    empresa: Optional[str] = None
    cooperativa: Optional[str] = None
    cancelado: bool = False


class VitalsState(BaseModel):
    """Estado dos sinais vitais"""
    processados: Dict[str, Any] = Field(default_factory=dict)  # {"PA":"120x80","FC":78,"FR":18,"Sat":97,"Temp":36.8}
    faltantes: List[str] = Field(default_factory=list)


class NoteState(BaseModel):
    """Estado das notas clínicas"""
    texto_bruto: Optional[str] = None
    sintomas_rag: List[Dict[str, Any]] = Field(default_factory=list)  # SymptomReport[]


class RouterState(BaseModel):
    """Estado do roteador"""
    intencao: Optional[str] = None  # escala | sinais_vitais | notas | finalizar | auxiliar
    ultimo_fluxo: Optional[str] = None


class AuxState(BaseModel):
    """Estado auxiliar para retomada e coleta incremental"""
    retomar_apos: Optional[Dict[str, Any]] = None   # {"flow":"finalizar","reason":"vitals_before_finish"}
    ultima_pergunta: Optional[str] = None           # prompt pendente ao usuário
    fluxo_que_perguntou: Optional[str] = None
    buffers: Dict[str, Any] = Field(default_factory=dict)  # {"vitals": {...}}
    acao_pendente: Optional[Dict[str, Any]] = None  # two-phase commit: payload + alvo + expiresAt


class GraphState(BaseModel):
    """Estado completo do grafo"""
    core: CoreState = Field(default_factory=CoreState)
    vitais: VitalsState = Field(default_factory=VitalsState)
    nota: NoteState = Field(default_factory=NoteState)
    router: RouterState = Field(default_factory=RouterState)
    aux: AuxState = Field(default_factory=AuxState)
    texto_usuario: Optional[str] = None
    metadados: Dict[str, Any] = Field(default_factory=dict)  # flags: presenca_confirmada, sv_realizados, modo_finalizar, etc.
    
    # Campos para resposta
    resposta_usuario: Optional[str] = None
    proximo_no: Optional[str] = None
    
    # Controle do fluxo do grafo
    terminar_fluxo: bool = False  # Marca se deve terminar o grafo
    continuar_fluxo: bool = False  # Marca se deve continuar no router
