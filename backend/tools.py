"""
Definição e execução das ferramentas (tool calling).

Ferramentas implementadas (mínimo 5):
  1. consultar_agenda
  2. adicionar_evento_agenda
  3. listar_tarefas
  4. adicionar_tarefa
  5. concluir_tarefa
  6. buscar_material_rag
  7. reindexar_documentos   (bônus)

Esta versão inclui:
- TOOL_ALIASES: mapeia variações de nome (criar_tarefa → adicionar_tarefa, etc.)
- ARG_ALIASES: mapeia variações de argumentos (title → titulo, id → tarefa_id)
- Logging detalhado de cada execução
"""

import json
import time
import logging
from typing import Any, Dict, List, Optional, Tuple

from backend import agenda, tasks
from backend.rag import get_rag
from backend import logger_system

logger = logging.getLogger(__name__)


# ── Aliases de nomes de ferramentas ─────────────────────────────────────────
# O LLM nem sempre usa o nome exato definido no schema. Mapeamos variações
# comuns (em pt-BR e en) para os nomes canônicos.

TOOL_ALIASES: Dict[str, str] = {
    # consultar_agenda
    "ver_agenda": "consultar_agenda",
    "listar_eventos": "consultar_agenda",
    "ver_eventos": "consultar_agenda",
    "get_agenda": "consultar_agenda",
    "check_agenda": "consultar_agenda",

    # adicionar_evento_agenda
    "adicionar_evento": "adicionar_evento_agenda",
    "criar_evento": "adicionar_evento_agenda",
    "novo_evento": "adicionar_evento_agenda",
    "add_event": "adicionar_evento_agenda",
    "create_event": "adicionar_evento_agenda",
    "agendar": "adicionar_evento_agenda",
    "agendar_evento": "adicionar_evento_agenda",

    # listar_tarefas
    "ver_tarefas": "listar_tarefas",
    "ver_tasks": "listar_tarefas",
    "list_tasks": "listar_tarefas",
    "get_tasks": "listar_tarefas",
    "tarefas_pendentes": "listar_tarefas",

    # adicionar_tarefa
    "criar_tarefa": "adicionar_tarefa",
    "nova_tarefa": "adicionar_tarefa",
    "add_task": "adicionar_tarefa",
    "create_task": "adicionar_tarefa",
    "adicionar_task": "adicionar_tarefa",
    "registrar_tarefa": "adicionar_tarefa",

    # concluir_tarefa
    "completar_tarefa": "concluir_tarefa",
    "finalizar_tarefa": "concluir_tarefa",
    "marcar_tarefa_concluida": "concluir_tarefa",
    "marcar_concluida": "concluir_tarefa",
    "complete_task": "concluir_tarefa",
    "finish_task": "concluir_tarefa",
    "done_task": "concluir_tarefa",

    # buscar_material_rag
    "buscar_material": "buscar_material_rag",
    "pesquisar_material": "buscar_material_rag",
    "buscar_rag": "buscar_material_rag",
    "consultar_material": "buscar_material_rag",
    "search_material": "buscar_material_rag",
    "rag_search": "buscar_material_rag",

    # reindexar_documentos
    "reindexar": "reindexar_documentos",
    "atualizar_indice": "reindexar_documentos",
    "rebuild_index": "reindexar_documentos",
}


# ── Aliases de argumentos por ferramenta ─────────────────────────────────────
# Mapeia chaves alternativas que o LLM pode gerar para os nomes canônicos
# esperados pelas funções Python.

ARG_ALIASES: Dict[str, Dict[str, str]] = {
    "consultar_agenda": {
        "period": "periodo", "data": "periodo", "date": "periodo",
        "quando": "periodo", "when": "periodo",
    },
    "adicionar_evento_agenda": {
        "title": "titulo", "name": "titulo", "nome": "titulo",
        "date": "data", "dia": "data", "day": "data",
        "time": "horario", "hora": "horario", "hour": "horario",
        "type": "tipo", "kind": "tipo", "category": "tipo",
        "description": "descricao", "desc": "descricao", "details": "descricao",
        "location": "local", "place": "local", "lugar": "local",
    },
    "listar_tarefas": {
        "filter": "filtro", "status": "filtro", "tipo": "filtro",
    },
    "adicionar_tarefa": {
        "title": "titulo", "name": "titulo", "nome": "titulo", "task": "titulo",
        "description": "descricao", "desc": "descricao", "details": "descricao",
        "priority": "prioridade", "importance": "prioridade",
        "deadline": "prazo", "due_date": "prazo", "data": "prazo",
        "date": "prazo", "until": "prazo", "ate": "prazo",
        "subject": "disciplina", "materia": "disciplina", "matéria": "disciplina",
        "course": "disciplina",
    },
    "concluir_tarefa": {
        "id": "tarefa_id", "task_id": "tarefa_id", "tarefa": "tarefa_id",
        "numero": "tarefa_id", "número": "tarefa_id", "task": "tarefa_id",
    },
    "buscar_material_rag": {
        "q": "query", "search": "query", "pergunta": "query",
        "termo": "query", "busca": "query", "consulta": "query",
        "k": "top_k", "limit": "top_k", "n": "top_k", "quantidade": "top_k",
    },
    "reindexar_documentos": {},
}


def normalizar_nome_ferramenta(nome: str) -> str:
    """Resolve um nome de ferramenta (possivelmente com alias) para o nome canônico."""
    if not nome:
        return ""
    nome_lower = nome.strip().lower()
    # Tenta direto e via alias
    return TOOL_ALIASES.get(nome_lower, nome_lower)


def normalizar_argumentos(nome_canonico: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Mapeia chaves alternativas para os nomes esperados pela função."""
    if not args:
        return {}
    aliases = ARG_ALIASES.get(nome_canonico, {})
    normalizado: Dict[str, Any] = {}
    for chave, valor in args.items():
        chave_lower = str(chave).strip().lower()
        chave_canonica = aliases.get(chave_lower, chave_lower)
        normalizado[chave_canonica] = valor
    return normalizado


# ── Definição das ferramentas (schema para o prompt da LLM) ─────────────────

TOOLS_SCHEMA: List[Dict] = [
    {
        "name": "consultar_agenda",
        "description": (
            "Consulta eventos da agenda acadêmica. "
            "Use quando o usuário perguntar sobre aulas, provas, eventos, compromissos "
            "para hoje, amanhã, esta semana ou uma data específica."
        ),
        "parameters": {
            "periodo": {
                "type": "string",
                "description": (
                    "Período a consultar. Valores aceitos: 'hoje', 'amanhã', 'semana', "
                    "ou uma data no formato 'YYYY-MM-DD'."
                ),
                "default": "hoje",
            }
        },
        "required": [],
    },
    {
        "name": "adicionar_evento_agenda",
        "description": (
            "Adiciona um novo evento, aula, prova ou compromisso à agenda acadêmica."
        ),
        "parameters": {
            "titulo": {"type": "string", "description": "Título do evento."},
            "data": {
                "type": "string",
                "description": (
                    "Data do evento. Aceita formatos 'YYYY-MM-DD' ou termos relativos "
                    "como 'amanhã', 'próxima sexta', 'daqui 3 dias'."
                ),
            },
            "horario": {"type": "string", "description": "Horário, ex: '14:00'.", "default": ""},
            "tipo": {
                "type": "string",
                "description": "Tipo: 'aula', 'prova', 'trabalho', 'seminário', 'reunião'.",
                "default": "aula",
            },
            "descricao": {"type": "string", "description": "Descrição.", "default": ""},
            "local": {"type": "string", "description": "Local do evento.", "default": ""},
        },
        "required": ["titulo", "data"],
    },
    {
        "name": "listar_tarefas",
        "description": (
            "Lista as tarefas acadêmicas cadastradas. "
            "Use quando o usuário perguntar sobre tarefas, trabalhos pendentes, "
            "o que fazer, ou pedir um resumo das atividades."
        ),
        "parameters": {
            "filtro": {
                "type": "string",
                "description": "Filtro: 'todas', 'pendentes', 'concluidas', 'alta', 'urgente'.",
                "default": "pendentes",
            }
        },
        "required": [],
    },
    {
        "name": "adicionar_tarefa",
        "description": (
            "Adiciona uma nova tarefa ou trabalho à lista. "
            "Use quando o usuário disser 'adicione', 'crie', 'registre', 'lembre-me de' "
            "uma tarefa ou atividade."
        ),
        "parameters": {
            "titulo": {"type": "string", "description": "Título da tarefa."},
            "descricao": {"type": "string", "description": "Descrição.", "default": ""},
            "prioridade": {
                "type": "string",
                "description": "Prioridade: 'baixa', 'média', 'alta', 'urgente'.",
                "default": "média",
            },
            "prazo": {
                "type": "string",
                "description": (
                    "Prazo. Aceita 'YYYY-MM-DD' ou termos relativos como 'amanhã', "
                    "'próxima sexta', 'sexta-feira', 'daqui 5 dias'."
                ),
                "default": "",
            },
            "disciplina": {"type": "string", "description": "Disciplina/matéria.", "default": ""},
        },
        "required": ["titulo"],
    },
    {
        "name": "concluir_tarefa",
        "description": (
            "Marca uma tarefa como concluída pelo ID numérico. "
            "Use quando o usuário disser que terminou, completou ou fez uma tarefa específica."
        ),
        "parameters": {
            "tarefa_id": {
                "type": "integer",
                "description": "ID numérico da tarefa (o número que aparece na lista).",
            }
        },
        "required": ["tarefa_id"],
    },
    {
        "name": "buscar_material_rag",
        "description": (
            "Busca informações nos materiais de estudo indexados. "
            "Use para responder perguntas sobre conteúdo acadêmico, explicar conceitos, "
            "resumir tópicos ou encontrar referências."
        ),
        "parameters": {
            "query": {"type": "string", "description": "Pergunta ou termo a buscar."},
            "top_k": {
                "type": "integer",
                "description": "Número de trechos a recuperar (padrão: 4).",
                "default": 4,
            },
        },
        "required": ["query"],
    },
    {
        "name": "reindexar_documentos",
        "description": (
            "Reconstrói o índice RAG a partir dos documentos disponíveis. "
            "Use quando novos documentos forem adicionados."
        ),
        "parameters": {},
        "required": [],
    },
]


def schema_para_prompt() -> str:
    """Formata o schema das ferramentas para inclusão no system prompt."""
    linhas = []
    for tool in TOOLS_SCHEMA:
        linhas.append(f"### {tool['name']}")
        linhas.append(f"Descrição: {tool['description']}")
        if tool["parameters"]:
            linhas.append("Parâmetros:")
            for param, info in tool["parameters"].items():
                obrig = "(obrigatório)" if param in tool.get("required", []) else "(opcional)"
                linhas.append(f"  - {param} {obrig}: {info['description']}")
        linhas.append("")
    return "\n".join(linhas)


# ── Executor ─────────────────────────────────────────────────────────────────

def executar_ferramenta(
    nome: str,
    argumentos: Dict[str, Any],
    conversa_id: Optional[str] = None,
) -> Tuple[Any, Optional[str]]:
    """
    Executa a ferramenta pelo nome (normalizando aliases) com os argumentos
    (também normalizados). Garante persistência ao retornar.

    Returns:
        (resultado, erro): resultado é o dict de saída; erro é None ou mensagem.
    """
    inicio = time.time()
    resultado: Any = None
    erro: Optional[str] = None

    # 1. Normaliza nome e argumentos
    nome_original = nome
    nome_canonico = normalizar_nome_ferramenta(nome)
    args_normalizados = normalizar_argumentos(nome_canonico, argumentos or {})

    if nome_original != nome_canonico:
        logger.info(
            f"[tool] Alias resolvido: '{nome_original}' → '{nome_canonico}'"
        )
    logger.info(
        f"[tool] Executando '{nome_canonico}' com args: {args_normalizados}"
    )

    try:
        if nome_canonico == "consultar_agenda":
            resultado = agenda.consultar_agenda(
                periodo=str(args_normalizados.get("periodo", "hoje"))
            )

        elif nome_canonico == "adicionar_evento_agenda":
            titulo = args_normalizados.get("titulo") or args_normalizados.get("nome")
            data = args_normalizados.get("data")
            if not titulo:
                raise ValueError("Parâmetro 'titulo' obrigatório.")
            if not data:
                raise ValueError("Parâmetro 'data' obrigatório.")
            resultado = agenda.adicionar_evento(
                titulo=str(titulo),
                data=str(data),
                horario=str(args_normalizados.get("horario", "")),
                tipo=str(args_normalizados.get("tipo", "aula")),
                descricao=str(args_normalizados.get("descricao", "")),
                local=str(args_normalizados.get("local", "")),
            )

        elif nome_canonico == "listar_tarefas":
            resultado = tasks.listar_tarefas(
                filtro=str(args_normalizados.get("filtro", "pendentes"))
            )

        elif nome_canonico == "adicionar_tarefa":
            titulo = args_normalizados.get("titulo")
            if not titulo:
                raise ValueError("Parâmetro 'titulo' obrigatório para adicionar_tarefa.")
            resultado = tasks.adicionar_tarefa(
                titulo=str(titulo),
                descricao=str(args_normalizados.get("descricao", "")),
                prioridade=str(args_normalizados.get("prioridade", "média")),
                prazo=str(args_normalizados.get("prazo", "")),
                disciplina=str(args_normalizados.get("disciplina", "")),
            )
            logger.info(f"[tool] adicionar_tarefa persistido: id={resultado.get('tarefa', {}).get('id')}")

        elif nome_canonico == "concluir_tarefa":
            id_raw = args_normalizados.get("tarefa_id")
            if id_raw is None:
                raise ValueError("Parâmetro 'tarefa_id' obrigatório.")
            # Aceita tanto int quanto string ("3", "tarefa 3", etc.)
            try:
                tarefa_id = int(str(id_raw).strip().lstrip("#").split()[-1])
            except (ValueError, IndexError):
                raise ValueError(f"Não foi possível extrair ID numérico de: {id_raw!r}")
            resultado = tasks.concluir_tarefa(tarefa_id=tarefa_id)
            logger.info(f"[tool] concluir_tarefa persistido: id={tarefa_id}")

        elif nome_canonico == "buscar_material_rag":
            query = args_normalizados.get("query")
            if not query:
                raise ValueError("Parâmetro 'query' obrigatório.")
            try:
                top_k = int(args_normalizados.get("top_k", 4))
            except (ValueError, TypeError):
                top_k = 4
            rag = get_rag()
            trechos = rag.buscar(query=str(query), top_k=top_k)
            resultado = {
                "query": str(query),
                "trechos_encontrados": len(trechos),
                "trechos": trechos,
            }

        elif nome_canonico == "reindexar_documentos":
            rag = get_rag()
            resultado = rag.reindexar()

        else:
            erro = f"Ferramenta desconhecida: '{nome_original}' (canônico: '{nome_canonico}')"
            resultado = {"erro": erro}
            logger.warning(f"[tool] {erro}")

    except (KeyError, ValueError) as e:
        erro = str(e)
        resultado = {"erro": erro}
        logger.warning(f"[tool] Erro de argumento em '{nome_canonico}': {e}")
    except Exception as e:
        erro = f"{type(e).__name__}: {e}"
        resultado = {"erro": erro}
        logger.exception(f"[tool] Erro inesperado em '{nome_canonico}': {e}")

    duracao_ms = round((time.time() - inicio) * 1000, 2)

    # Registra no log estruturado (mantém o nome original para auditoria)
    logger_system.registrar_tool_call(
        ferramenta=nome_canonico,
        entrada={"nome_original": nome_original, "argumentos": args_normalizados},
        saida=resultado,
        duracao_ms=duracao_ms,
        erro=erro,
        conversa_id=conversa_id,
    )

    return resultado, erro
