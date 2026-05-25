"""
Gerenciamento de tarefas acadêmicas.
Armazena tarefas em arquivo JSON local com suporte a prioridade e prazo.
"""

import json
import os
from datetime import datetime
from typing import List, Dict, Any, Optional

from backend.utils_datas import resolver_data_relativa

TASKS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "tasks.json")

PRIORIDADES_VALIDAS = {"baixa", "média", "media", "alta", "urgente"}


def _load() -> List[Dict]:
    if not os.path.exists(TASKS_PATH):
        return []
    with open(TASKS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _save(tarefas: List[Dict]) -> None:
    os.makedirs(os.path.dirname(TASKS_PATH), exist_ok=True)
    with open(TASKS_PATH, "w", encoding="utf-8") as f:
        json.dump(tarefas, f, ensure_ascii=False, indent=2)


# ── Operações públicas ──────────────────────────────────────────────────────

def listar_tarefas(
    filtro: str = "todas",
) -> Dict[str, Any]:
    """
    Lista tarefas com filtro opcional.
    filtro: 'todas', 'pendentes', 'concluidas', 'alta', 'urgente', etc.
    """
    tarefas = _load()
    filtro_lower = filtro.lower().strip()

    if filtro_lower in ("pendentes", "pendente", "abertas"):
        resultado = [t for t in tarefas if not t.get("concluida", False)]
    elif filtro_lower in ("concluidas", "concluída", "concluidas", "feitas", "done"):
        resultado = [t for t in tarefas if t.get("concluida", False)]
    elif filtro_lower in PRIORIDADES_VALIDAS:
        resultado = [
            t for t in tarefas
            if t.get("prioridade", "").lower() == filtro_lower and not t.get("concluida", False)
        ]
    else:
        resultado = tarefas

    resultado.sort(key=lambda t: (
        t.get("concluida", False),
        {"urgente": 0, "alta": 1, "média": 2, "media": 2, "baixa": 3}.get(t.get("prioridade", "baixa").lower(), 4),
        t.get("prazo", "9999-99-99"),
    ))

    return {"filtro": filtro, "total": len(resultado), "tarefas": resultado}


def adicionar_tarefa(
    titulo: str,
    descricao: str = "",
    prioridade: str = "média",
    prazo: str = "",
    disciplina: str = "",
) -> Dict[str, Any]:
    """Adiciona uma nova tarefa. Prazo aceita datas relativas (ex: 'amanhã')."""
    tarefas = _load()
    novo_id = max((t.get("id", 0) for t in tarefas), default=0) + 1

    prioridade_norm = prioridade.lower().strip()
    if prioridade_norm not in PRIORIDADES_VALIDAS:
        prioridade_norm = "média"

    # Resolve prazo relativo ("próxima sexta", "amanhã", etc.) para YYYY-MM-DD
    prazo_resolvido = ""
    if prazo:
        prazo_resolvido = resolver_data_relativa(prazo) or prazo

    tarefa = {
        "id": novo_id,
        "titulo": titulo,
        "descricao": descricao,
        "prioridade": prioridade_norm,
        "prazo": prazo_resolvido,
        "disciplina": disciplina,
        "concluida": False,
        "criada_em": datetime.now().isoformat(),
        "concluida_em": None,
    }
    tarefas.append(tarefa)
    _save(tarefas)
    return {"sucesso": True, "tarefa": tarefa}


def concluir_tarefa(tarefa_id: int) -> Dict[str, Any]:
    """Marca uma tarefa como concluída pelo ID."""
    tarefas = _load()
    for t in tarefas:
        if t.get("id") == tarefa_id:
            if t.get("concluida"):
                return {"aviso": f"Tarefa {tarefa_id} já estava concluída.", "tarefa": t}
            t["concluida"] = True
            t["concluida_em"] = datetime.now().isoformat()
            _save(tarefas)
            return {"sucesso": True, "tarefa": t}
    return {"erro": f"Tarefa ID {tarefa_id} não encontrada."}


def remover_tarefa(tarefa_id: int) -> Dict[str, Any]:
    tarefas = _load()
    novas = [t for t in tarefas if t.get("id") != tarefa_id]
    if len(novas) == len(tarefas):
        return {"erro": f"Tarefa ID {tarefa_id} não encontrada."}
    _save(novas)
    return {"sucesso": True, "removida": tarefa_id}


def editar_tarefa(tarefa_id: int, **campos) -> Dict[str, Any]:
    """Atualiza campos de uma tarefa existente."""
    tarefas = _load()
    campos_editaveis = {"titulo", "descricao", "prioridade", "prazo", "disciplina"}
    for t in tarefas:
        if t.get("id") == tarefa_id:
            for campo, valor in campos.items():
                if campo in campos_editaveis:
                    t[campo] = valor
            t["editada_em"] = datetime.now().isoformat()
            _save(tarefas)
            return {"sucesso": True, "tarefa": t}
    return {"erro": f"Tarefa ID {tarefa_id} não encontrada."}
