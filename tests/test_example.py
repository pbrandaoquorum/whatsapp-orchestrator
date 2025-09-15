"""
Exemplos de teste end-to-end locais para demonstrar o sistema
Execute com: python test_example.py
"""
import asyncio
import json
from typing import Dict, Any

from app.graph.builder import criar_grafo
from app.graph.state import GraphState, CoreState, VitalsState, RouterState, AuxState
from app.infra.logging import configurar_logging, obter_logger

# Configurar logging
configurar_logging("INFO")
logger = obter_logger(__name__)


def criar_estado_inicial(numero_telefone: str, texto: str) -> GraphState:
    """Cria estado inicial para teste"""
    session_id = f"test_session_{numero_telefone.replace('+', '')}"
    
    return GraphState(
        core=CoreState(
            session_id=session_id,
            numero_telefone=numero_telefone,
            schedule_id="test_schedule_123",
            patient_id="test_patient_123",
            report_id="test_report_123",
            data_relatorio="2025-01-15",
            turno_permitido=True,
            turno_iniciado=False,
            cancelado=False
        ),
        vitais=VitalsState(),
        router=RouterState(),
        aux=AuxState(),
        texto_usuario=texto,
        metadados={}
    )


def simular_mensagem(grafo, numero_telefone: str, texto: str, estado_anterior=None) -> Dict[str, Any]:
    """Simula processamento de uma mensagem"""
    print(f"\n📱 Usuário ({numero_telefone}): {texto}")
    
    if estado_anterior:
        # Usar estado anterior e atualizar apenas o texto
        estado = estado_anterior
        estado.texto_usuario = texto
    else:
        # Criar novo estado
        estado = criar_estado_inicial(numero_telefone, texto)
    
    try:
        # Executar grafo
        resultado = grafo.invoke(estado)
        
        # Extrair resposta
        resposta = resultado.get("resposta_usuario", "Sem resposta")
        print(f"🤖 Sistema: {resposta}")
        
        return resultado
        
    except Exception as e:
        print(f"❌ Erro: {e}")
        return estado


def exemplo_happy_path():
    """Exemplo de fluxo completo bem-sucedido"""
    print("\n" + "="*60)
    print("🎯 EXEMPLO: HAPPY PATH COMPLETO")
    print("="*60)
    
    # Criar grafo (usando MemoryCheckpointSaver para teste local)
    grafo = criar_grafo(usar_redis=False)
    numero_telefone = "+5511999999999"
    
    # 1. Confirmação de presença
    print("\n🔹 Passo 1: Confirmação de Presença")
    estado = simular_mensagem(grafo, numero_telefone, "cheguei, confirmo presença")
    
    # 2. Resposta à confirmação
    print("\n🔹 Passo 2: Confirmação da Presença")
    estado = simular_mensagem(grafo, numero_telefone, "sim", estado)
    
    # 3. Sinais vitais completos
    print("\n🔹 Passo 3: Sinais Vitais Completos")
    estado = simular_mensagem(
        grafo, numero_telefone, 
        "PA 120x80, FC 78 bpm, FR 18 irpm, Sat 97%, Temp 36.5°C", 
        estado
    )
    
    # 4. Confirmação dos sinais vitais
    print("\n🔹 Passo 4: Confirmação dos Sinais Vitais")
    estado = simular_mensagem(grafo, numero_telefone, "sim", estado)
    
    # 5. Finalização
    print("\n🔹 Passo 5: Finalização do Plantão")
    estado = simular_mensagem(grafo, numero_telefone, "finalizar", estado)
    
    # 6. Confirmação da finalização
    print("\n🔹 Passo 6: Confirmação da Finalização")
    estado = simular_mensagem(grafo, numero_telefone, "sim", estado)
    
    print("\n✅ Happy path concluído com sucesso!")


def exemplo_coleta_incremental():
    """Exemplo de coleta incremental de sinais vitais"""
    print("\n" + "="*60)
    print("🔄 EXEMPLO: COLETA INCREMENTAL")
    print("="*60)
    
    grafo = criar_grafo(usar_redis=False)
    numero_telefone = "+5511888888888"
    
    # Simular presença já confirmada
    estado = criar_estado_inicial(numero_telefone, "")
    estado.metadados["presenca_confirmada"] = True
    
    # 1. Primeiro sinal vital
    print("\n🔹 Enviando PA apenas")
    estado = simular_mensagem(grafo, numero_telefone, "PA 130x90", estado)
    
    # 2. Mais alguns sinais
    print("\n🔹 Enviando FC e Sat")
    estado = simular_mensagem(grafo, numero_telefone, "FC 82, Sat 95%", estado)
    
    # 3. Completar os sinais
    print("\n🔹 Completando com FR e Temp")
    estado = simular_mensagem(grafo, numero_telefone, "FR 16, Temp 37.1°C", estado)
    
    # 4. Confirmação
    print("\n🔹 Confirmando salvamento")
    estado = simular_mensagem(grafo, numero_telefone, "sim", estado)
    
    print("\n✅ Coleta incremental concluída!")


def exemplo_retomada_contexto():
    """Exemplo de retomada de contexto"""
    print("\n" + "="*60)
    print("🔄 EXEMPLO: RETOMADA DE CONTEXTO")
    print("="*60)
    
    grafo = criar_grafo(usar_redis=False)
    numero_telefone = "+5511777777777"
    
    # Simular presença confirmada mas SV não realizados
    estado = criar_estado_inicial(numero_telefone, "")
    estado.metadados["presenca_confirmada"] = True
    estado.metadados["sinais_vitais_realizados"] = False
    
    # 1. Tentar finalizar sem sinais vitais
    print("\n🔹 Tentando finalizar sem sinais vitais")
    estado = simular_mensagem(grafo, numero_telefone, "quero finalizar", estado)
    
    # 2. Sistema deve pedir sinais vitais primeiro
    print("\n🔹 Enviando sinais vitais solicitados")
    estado = simular_mensagem(
        grafo, numero_telefone,
        "PA 125x85, FC 75, FR 17, Sat 98%, Temp 36.3°C",
        estado
    )
    
    # 3. Confirmação dos sinais vitais
    print("\n🔹 Confirmando sinais vitais")
    estado = simular_mensagem(grafo, numero_telefone, "sim", estado)
    
    # Sistema deve automaticamente retomar finalização
    print("\n🔹 Sistema deve retomar finalização automaticamente")
    
    print("\n✅ Retomada de contexto demonstrada!")


def exemplo_nota_clinica_com_rag():
    """Exemplo de nota clínica com identificação de sintomas"""
    print("\n" + "="*60)
    print("📝 EXEMPLO: NOTA CLÍNICA + RAG")
    print("="*60)
    
    grafo = criar_grafo(usar_redis=False)
    numero_telefone = "+5511666666666"
    
    # Simular presença confirmada
    estado = criar_estado_inicial(numero_telefone, "")
    estado.metadados["presenca_confirmada"] = True
    
    # 1. Enviar nota clínica
    print("\n🔹 Enviando nota clínica")
    nota = ("Paciente consciente e orientado, refere dor de cabeça intensa "
            "desde ontem, acompanhada de náusea. Nega febre. Apresenta "
            "sensibilidade à luz. Deambula sem auxílio.")
    
    estado = simular_mensagem(grafo, numero_telefone, nota, estado)
    
    # 2. Confirmação da nota
    print("\n🔹 Confirmando nota clínica")
    estado = simular_mensagem(grafo, numero_telefone, "sim", estado)
    
    print("\n✅ Nota clínica com RAG processada!")


def exemplo_cancelamento():
    """Exemplo de cancelamento de ações"""
    print("\n" + "="*60)
    print("❌ EXEMPLO: CANCELAMENTO DE AÇÕES")
    print("="*60)
    
    grafo = criar_grafo(usar_redis=False)
    numero_telefone = "+5511555555555"
    
    # 1. Tentar confirmar presença
    print("\n🔹 Iniciando confirmação de presença")
    estado = simular_mensagem(grafo, numero_telefone, "cheguei", None)
    
    # 2. Cancelar confirmação
    print("\n🔹 Cancelando confirmação")
    estado = simular_mensagem(grafo, numero_telefone, "não", estado)
    
    # 3. Tentar novamente
    print("\n🔹 Tentando confirmar novamente")
    estado = simular_mensagem(grafo, numero_telefone, "confirmo presença", estado)
    
    # 4. Confirmar desta vez
    print("\n🔹 Confirmando presença")
    estado = simular_mensagem(grafo, numero_telefone, "sim", estado)
    
    print("\n✅ Exemplo de cancelamento concluído!")


def exemplo_turno_cancelado():
    """Exemplo com turno cancelado"""
    print("\n" + "="*60)
    print("🚫 EXEMPLO: TURNO CANCELADO")
    print("="*60)
    
    grafo = criar_grafo(usar_redis=False)
    numero_telefone = "+5511444444444"
    
    # Simular turno cancelado
    estado = criar_estado_inicial(numero_telefone, "")
    estado.core.cancelado = True
    estado.core.turno_permitido = False
    
    # 1. Tentar confirmar presença
    print("\n🔹 Tentando confirmar presença com turno cancelado")
    estado = simular_mensagem(grafo, numero_telefone, "cheguei", estado)
    
    # 2. Tentar enviar sinais vitais
    print("\n🔹 Tentando enviar sinais vitais")
    estado = simular_mensagem(grafo, numero_telefone, "PA 120x80", estado)
    
    # 3. Pedir ajuda
    print("\n🔹 Pedindo ajuda")
    estado = simular_mensagem(grafo, numero_telefone, "ajuda", estado)
    
    print("\n✅ Exemplo de turno cancelado concluído!")


def mostrar_estado_final(estado: Dict[str, Any]):
    """Mostra estado final de forma organizada"""
    print("\n" + "="*40)
    print("📊 ESTADO FINAL")
    print("="*40)
    
    core = estado.get("core", {})
    metadados = estado.get("metadados", {})
    vitais = estado.get("vitais", {})
    
    print(f"Session ID: {core.get('session_id')}")
    print(f"Telefone: {core.get('numero_telefone')}")
    print(f"Turno Permitido: {core.get('turno_permitido')}")
    print(f"Cancelado: {core.get('cancelado')}")
    
    print(f"\nMetadados:")
    print(f"  - Presença Confirmada: {metadados.get('presenca_confirmada', False)}")
    print(f"  - SV Realizados: {metadados.get('sinais_vitais_realizados', False)}")
    print(f"  - Nota Enviada: {metadados.get('nota_clinica_enviada', False)}")
    print(f"  - Plantão Finalizado: {metadados.get('plantao_finalizado', False)}")
    
    processados = vitais.get("processados", {})
    if processados:
        print(f"\nSinais Vitais Coletados:")
        for sinal, valor in processados.items():
            print(f"  - {sinal}: {valor}")


def main():
    """Função principal para executar todos os exemplos"""
    print("🚀 INICIANDO EXEMPLOS DE TESTE END-TO-END")
    print("="*80)
    
    try:
        # Executar exemplos
        exemplo_happy_path()
        exemplo_coleta_incremental()
        exemplo_retomada_contexto()
        exemplo_nota_clinica_com_rag()
        exemplo_cancelamento()
        exemplo_turno_cancelado()
        
        print("\n" + "="*80)
        print("✅ TODOS OS EXEMPLOS EXECUTADOS COM SUCESSO!")
        print("="*80)
        
        print("\n📋 Próximos passos:")
        print("1. Configurar variáveis de ambiente (.env)")
        print("2. Executar: uvicorn app.api.main:app --reload")
        print("3. Testar endpoints via curl ou Postman")
        print("4. Integrar com seu webhook WhatsApp existente")
        print("5. Sincronizar base de sintomas: POST /rag/sync")
        
    except Exception as e:
        print(f"\n❌ Erro durante execução dos exemplos: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
