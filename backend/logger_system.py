"""
Sistema de logging para chamadas de ferramentas (tool calls).
Registra ferramenta chamada, entrada, saída e timestamp.
"""

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

LOGS_PATH = os.path.join(os.path.dirname(__file__), "..", "logs", "tool_calls.jsonl")


def _garantir_diretorio() -> None:
    os.makedirs(os.path.dirname(LOGS_PATH), exist_ok=True)


def registrar_tool_call(
    ferramenta: str,
    entrada: Dict[str, Any],
    saida: Any,
    duracao_ms: Optional[float] = None,
    erro: Optional[str] = None,
    conversa_id: Optional[str] = None,
) -> None:
    """
    Registra uma chamada de ferramenta em formato JSONL (uma entrada por linha).

    Args:
        ferramenta: Nome da ferramenta chamada.
        entrada: Dicionário com os argumentos passados.
        saida: Resultado retornado pela ferramenta.
        duracao_ms: Tempo de execução em milissegundos.
        erro: Mensagem de erro, se houver.
        conversa_id: Identificador da sessão de conversa.
    """
    _garantir_diretorio()

    registro = {
        "timestamp": datetime.now().isoformat(),
        "conversa_id": conversa_id,
        "ferramenta": ferramenta,
        "entrada": entrada,
        "saida": saida,
        "duracao_ms": duracao_ms,
        "erro": erro,
        "status": "erro" if erro else "sucesso",
    }

    with open(LOGS_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(registro, ensure_ascii=False) + "\n")


def obter_logs(
    limite: int = 50,
    ferramenta_filtro: Optional[str] = None,
    conversa_id_filtro: Optional[str] = None,
) -> List[Dict]:
    """
    Recupera os logs registrados, do mais recente ao mais antigo.

    Args:
        limite: Número máximo de entradas retornadas.
        ferramenta_filtro: Filtra por nome de ferramenta específica.
        conversa_id_filtro: Filtra por sessão de conversa.
    """
    if not os.path.exists(LOGS_PATH):
        return []

    registros = []
    with open(LOGS_PATH, "r", encoding="utf-8") as f:
        for linha in f:
            linha = linha.strip()
            if not linha:
                continue
            try:
                registros.append(json.loads(linha))
            except json.JSONDecodeError:
                continue

    # Filtros opcionais
    if ferramenta_filtro:
        registros = [r for r in registros if r.get("ferramenta") == ferramenta_filtro]
    if conversa_id_filtro:
        registros = [r for r in registros if r.get("conversa_id") == conversa_id_filtro]

    # Mais recentes primeiro
    registros.reverse()
    return registros[:limite]


def resumo_logs() -> Dict[str, Any]:
    """Retorna estatísticas gerais dos logs."""
    registros = obter_logs(limite=10_000)
    if not registros:
        return {"total": 0, "por_ferramenta": {}, "taxa_erro": 0.0}

    por_ferramenta: Dict[str, int] = {}
    erros = 0
    for r in registros:
        nome = r.get("ferramenta", "desconhecida")
        por_ferramenta[nome] = por_ferramenta.get(nome, 0) + 1
        if r.get("status") == "erro":
            erros += 1

    return {
        "total": len(registros),
        "por_ferramenta": por_ferramenta,
        "taxa_erro": round(erros / len(registros), 4) if registros else 0.0,
        "erros_totais": erros,
    }


def limpar_logs() -> Dict[str, Any]:
    """Apaga todos os logs (irreversível)."""
    if os.path.exists(LOGS_PATH):
        os.remove(LOGS_PATH)
        return {"sucesso": True, "mensagem": "Logs apagados com sucesso."}
    return {"sucesso": False, "mensagem": "Arquivo de logs não encontrado."}
