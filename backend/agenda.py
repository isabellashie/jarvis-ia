"""
Gerenciamento da agenda acadêmica.
Armazena e recupera eventos em arquivo JSON local.
"""

import json
import os
from datetime import datetime, date
from typing import List, Dict, Any, Optional

from backend.utils_datas import resolver_data_relativa

AGENDA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "agenda.json")


def _load() -> List[Dict]:
    if not os.path.exists(AGENDA_PATH):
        return []
    with open(AGENDA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _save(eventos: List[Dict]) -> None:
    os.makedirs(os.path.dirname(AGENDA_PATH), exist_ok=True)
    with open(AGENDA_PATH, "w", encoding="utf-8") as f:
        json.dump(eventos, f, ensure_ascii=False, indent=2)


def _normalizar_data(data_str: str) -> Optional[str]:
    """
    Converte uma data (absoluta OU relativa em PT-BR) para YYYY-MM-DD.
    Delega para o utilitário compartilhado, que entende termos como
    'amanhã', 'próxima sexta', 'daqui 3 dias' além dos formatos comuns.
    """
    if not data_str:
        return None
    return resolver_data_relativa(data_str)


# ── Operações públicas ──────────────────────────────────────────────────────

def consultar_agenda(periodo: str = "hoje") -> Dict[str, Any]:
    """
    Retorna eventos conforme o período solicitado.
    periodo: 'hoje', 'amanhã', 'semana', ou uma data 'YYYY-MM-DD' / 'DD/MM/YYYY'
    """
    eventos = _load()
    hoje = date.today()

    periodo_lower = periodo.lower().strip()

    if periodo_lower in ("hoje", "today"):
        alvo = [hoje.isoformat()]
    elif periodo_lower in ("amanhã", "amanha", "tomorrow"):
        from datetime import timedelta
        alvo = [(hoje + timedelta(days=1)).isoformat()]
    elif periodo_lower in ("semana", "week", "esta semana", "essa semana"):
        from datetime import timedelta
        alvo = [(hoje + timedelta(days=i)).isoformat() for i in range(7)]
    else:
        data_norm = _normalizar_data(periodo)
        alvo = [data_norm] if data_norm else []

    if not alvo:
        return {"erro": f"Período '{periodo}' não reconhecido.", "eventos": []}

    filtrados = [e for e in eventos if e.get("data") in alvo]
    filtrados.sort(key=lambda e: (e.get("data", ""), e.get("horario", "")))

    return {
        "periodo": periodo,
        "datas_consultadas": alvo,
        "total": len(filtrados),
        "eventos": filtrados,
    }


def adicionar_evento(
    titulo: str,
    data: str,
    horario: str = "",
    tipo: str = "aula",
    descricao: str = "",
    local: str = "",
) -> Dict[str, Any]:
    """Adiciona um novo evento à agenda."""
    data_norm = _normalizar_data(data)
    if not data_norm:
        return {"erro": f"Data inválida: '{data}'. Use YYYY-MM-DD ou DD/MM/YYYY."}

    eventos = _load()
    novo_id = max((e.get("id", 0) for e in eventos), default=0) + 1
    evento = {
        "id": novo_id,
        "titulo": titulo,
        "data": data_norm,
        "horario": horario,
        "tipo": tipo,
        "descricao": descricao,
        "local": local,
        "criado_em": datetime.now().isoformat(),
    }
    eventos.append(evento)
    _save(eventos)
    return {"sucesso": True, "evento": evento}


def remover_evento(evento_id: int) -> Dict[str, Any]:
    eventos = _load()
    novos = [e for e in eventos if e.get("id") != evento_id]
    if len(novos) == len(eventos):
        return {"erro": f"Evento ID {evento_id} não encontrado."}
    _save(novos)
    return {"sucesso": True, "removido": evento_id}


def listar_todos_eventos() -> Dict[str, Any]:
    eventos = _load()
    eventos.sort(key=lambda e: (e.get("data", ""), e.get("horario", "")))
    return {"total": len(eventos), "eventos": eventos}
