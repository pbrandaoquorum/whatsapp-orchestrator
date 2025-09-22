"""
GraphState - Estado unificado do sistema usando Pydantic v2
"""
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field


class SymptomReport(BaseModel):
    """Schema para relatório de sintomas"""
    symptomDefinition: str
    altNotepadMain: str
    symptomCategory: str
    symptomSubCategory: str
    descricaoComparada: str
    coeficienteSimilaridade: float


class GraphState(BaseModel):
    """Estado unificado do grafo - todos os nomes em PT-BR conforme especificado"""
    
    # Informações da sessão
    sessao: Dict[str, Any] = Field(default_factory=lambda: {
        "session_id": None,
        "telefone": None,
        "caregiver_id": None,
        "schedule_id": None,
        "patient_id": None,
        "report_id": None,
        "data_relatorio": None,
        "turno_permitido": None,
        "turno_iniciado": None,
        "empresa": None,
        "cooperativa": None,
        "cancelado": False
    })
    
    # Entrada do usuário
    entrada: Dict[str, Any] = Field(default_factory=lambda: {
        "texto_usuario": None,
        "meta": {}
    })
    
    # Resultado do roteador
    roteador: Dict[str, Any] = Field(default_factory=lambda: {
        "intencao": None,
        "subintencao_clinico": None
    })
    
    # Dados clínicos
    clinico: Dict[str, Any] = Field(default_factory=lambda: {
        "vitais": {},  # {"PA":"120x80","FC":78,"FR":18,"Sat":97,"Temp":36.8}
        "faltantes": [],  # ["FR","Sat"]
        "nota": None,  # texto livre
        "sintomas": []  # List[SymptomReport] (serialize)
    })
    
    # Estado de retomada
    retomada: Optional[Dict[str, Any]] = None  # {"fluxo":"finalizar","motivo":"precisa_vitais"}
    
    # Estado pendente (two-phase commit)
    pendente: Optional[Dict[str, Any]] = None  # {"fluxo":"clinico","payload":{...}}
    
    # Histórico de fluxos executados
    fluxos_executados: List[str] = Field(default_factory=list)
    
    # Resposta final do fiscal
    resposta_fiscal: Optional[str] = None
    
    # Metadados adicionais
    meta: Dict[str, Any] = Field(default_factory=dict)

    def __str__(self) -> str:
        """Representação string para logs"""
        return f"GraphState(session_id={self.sessao.get('session_id')}, intencao={self.roteador.get('intencao')}, fluxos={len(self.fluxos_executados)})"
    
    def get_vitais_completos(self) -> bool:
        """Verifica se todos os sinais vitais estão presentes"""
        vitais = self.clinico["vitais"]
        campos_obrigatorios = ["PA", "FC", "FR", "Sat", "Temp"]
        return all(
            vitais.get(campo) is not None and vitais.get(campo) != "" 
            for campo in campos_obrigatorios
        )
    
    def get_vitais_faltantes(self) -> List[str]:
        """Retorna lista de vitais em falta"""
        vitais = self.clinico["vitais"]
        campos_obrigatorios = ["PA", "FC", "FR", "Sat", "Temp"]
        return [
            campo for campo in campos_obrigatorios 
            if not vitais.get(campo) or vitais.get(campo) == ""
        ]
    
    def limpar_pendente(self):
        """Limpa estado pendente após confirmação"""
        self.pendente = None
    
    def adicionar_fluxo_executado(self, fluxo: str):
        """Adiciona fluxo à lista de executados"""
        if fluxo not in self.fluxos_executados:
            self.fluxos_executados.append(fluxo)
    
    def tem_retomada(self) -> bool:
        """Verifica se há estado de retomada"""
        return self.retomada is not None
    
    def tem_pendente(self) -> bool:
        """Verifica se há ação pendente"""
        return self.pendente is not None
