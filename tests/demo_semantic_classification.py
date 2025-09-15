#!/usr/bin/env python3
"""
Demonstração da classificação semântica com LLM
Script para testar o classificador localmente
"""
import asyncio
import os
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

from app.graph.semantic_classifier import classificar_semanticamente, IntentType
from app.graph.state import GraphState, CoreState
from app.infra.circuit_breaker import get_all_circuit_breaker_stats
from app.infra.cache import get_cache_stats


def criar_estado_teste():
    """Cria estado de teste"""
    estado = GraphState()
    estado.core = CoreState(
        session_id="demo_session",
        numero_telefone="+5511999999999",
        cancelado=False,
        turno_permitido=True
    )
    estado.metadados = {
        "presenca_confirmada": False,
        "sinais_vitais_realizados": False
    }
    return estado


async def testar_classificacao(texto: str, estado: GraphState):
    """Testa classificação de um texto"""
    print(f"\n🔍 Testando: '{texto}'")
    print("-" * 50)
    
    try:
        resultado = await classificar_semanticamente(texto, estado)
        
        print(f"✅ Intenção: {resultado.intent}")
        print(f"📊 Confiança: {resultado.confidence:.2f}")
        print(f"💭 Justificativa: {resultado.rationale}")
        
        if resultado.vital_signs:
            print(f"🩺 Sinais Vitais: {resultado.vital_signs}")
        
        if resultado.clinical_note:
            print(f"📝 Nota Clínica: {resultado.clinical_note}")
            
    except Exception as e:
        print(f"❌ Erro: {e}")


async def demo_principal():
    """Demonstração principal"""
    print("🤖 Demonstração do Classificador Semântico")
    print("=" * 60)
    
    # Verificar se OpenAI API Key está configurada
    if not os.getenv("OPENAI_API_KEY"):
        print("⚠️  OPENAI_API_KEY não configurada!")
        print("Configure a variável de ambiente para testar o LLM")
        return
    
    estado = criar_estado_teste()
    
    # Casos de teste
    casos_teste = [
        # Confirmação de presença
        "Cheguei no plantão",
        "Estou aqui, confirmo presença",
        "Oi, já cheguei",
        
        # Cancelamento
        "Não posso ir hoje, imprevisto",
        "Cancelar plantão",
        
        # Sinais vitais
        "PA 120x80, FC 78 bpm",
        "Pressão 130/90, frequência cardíaca 85",
        "Temperatura 36.5°C, saturação 97%",
        
        # Nota clínica
        "Paciente consciente e orientado, sem queixas",
        "Apresenta quadro estável, sinais vitais normais",
        
        # Finalização
        "Finalizar plantão",
        "Quero encerrar",
        
        # Confirmações
        "Sim",
        "Não",
        "Ok, pode ser",
        
        # Casos ambíguos
        "Olá",
        "Não entendi",
        "Preciso de ajuda"
    ]
    
    # Testar cada caso
    for i, texto in enumerate(casos_teste, 1):
        print(f"\n📝 Teste {i}/{len(casos_teste)}")
        await testar_classificacao(texto, estado)
        
        # Simular mudança de contexto
        if i == 3:  # Após 3 testes, confirmar presença
            estado.metadados["presenca_confirmada"] = True
            print("\n🔄 Contexto atualizado: presença confirmada")
    
    # Mostrar estatísticas
    print("\n" + "=" * 60)
    print("📊 Estatísticas do Sistema")
    print("=" * 60)
    
    # Circuit Breaker Stats
    cb_stats = get_all_circuit_breaker_stats()
    if cb_stats:
        print("\n🔧 Circuit Breakers:")
        for name, stats in cb_stats.items():
            print(f"  {name}:")
            print(f"    Estado: {stats['state']}")
            print(f"    Taxa de Sucesso: {stats['success_rate']:.1f}%")
            print(f"    Total de Chamadas: {stats['total_calls']}")
    
    # Cache Stats
    cache_stats = await get_cache_stats()
    print("\n💾 Cache:")
    print(f"  Memória: {cache_stats['memory']['entries']} entradas")
    print(f"  Redis: {'✅ Disponível' if cache_stats['redis']['available'] else '❌ Indisponível'}")
    if cache_stats['redis']['available']:
        print(f"  Redis Entradas: {cache_stats['redis']['entries']}")


async def demo_interativa():
    """Demonstração interativa"""
    print("\n🎮 Modo Interativo")
    print("Digite mensagens para testar o classificador (ou 'sair' para terminar)")
    print("-" * 60)
    
    estado = criar_estado_teste()
    
    while True:
        try:
            texto = input("\n💬 Sua mensagem: ").strip()
            
            if texto.lower() in ['sair', 'exit', 'quit']:
                print("👋 Até logo!")
                break
            
            if not texto:
                continue
            
            await testar_classificacao(texto, estado)
            
            # Atualizar contexto baseado na classificação
            resultado = await classificar_semanticamente(texto, estado)
            if resultado.intent == IntentType.CONFIRMAR_PRESENCA:
                estado.metadados["presenca_confirmada"] = True
                print("🔄 Contexto: presença confirmada")
            
        except KeyboardInterrupt:
            print("\n👋 Interrompido pelo usuário")
            break
        except Exception as e:
            print(f"❌ Erro: {e}")


async def main():
    """Função principal"""
    print("🚀 Iniciando demonstração...")
    
    # Escolher modo
    print("\nEscolha o modo:")
    print("1. Demonstração automática")
    print("2. Modo interativo")
    
    try:
        escolha = input("\nDigite sua escolha (1 ou 2): ").strip()
        
        if escolha == "1":
            await demo_principal()
        elif escolha == "2":
            await demo_interativa()
        else:
            print("Escolha inválida. Executando demonstração automática...")
            await demo_principal()
            
    except KeyboardInterrupt:
        print("\n👋 Demonstração interrompida")
    except Exception as e:
        print(f"❌ Erro na demonstração: {e}")


if __name__ == "__main__":
    asyncio.run(main())
