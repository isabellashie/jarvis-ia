"""
Cliente LLM com orquestração de tool calling para o JARVIS Acadêmico.

Mudanças desta versão:
- Contexto temporal absoluto no TOPO do system prompt (datas pré-calculadas)
- Few-shot examples para tools de escrita (adicionar/concluir tarefa)
- Parser de tool_call mais tolerante:
  * Detecta tool_call em blocos ```json
  * Detecta JSON solto sem tags <tool_call>
  * Detecta múltiplos tool_calls e executa o primeiro
  * Tolera vírgulas finais, aspas simples, quebras de linha
- Logging detalhado de cada iteração
"""

import json
import re
import logging
import uuid
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI

from backend.tools import schema_para_prompt, executar_ferramenta
from backend.utils_datas import gerar_contexto_temporal

logger = logging.getLogger(__name__)

# ── Configuração do cliente ──────────────────────────────────────────────────

LLM_BASE_URL = "https://llm.liaufms.org/v1/gemma-3-12b-it"
LLM_API_KEY = "Cxt2ftLF7d3mHS2JdiFqB-eSDAQeZvFATPXPs02lV9A"
LLM_MODEL = "google/gemma-3-12b-it"

_client: Optional[OpenAI] = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY)
    return _client


# ── System Prompt ────────────────────────────────────────────────────────────

SYSTEM_PROMPT_TEMPLATE = """{contexto_temporal}

Você é JARVIS, um assistente acadêmico inteligente e prestativo. Seu objetivo é
ajudar estudantes a organizar seus estudos, consultar materiais, gerenciar
tarefas e a agenda.

══ FERRAMENTAS DISPONÍVEIS ══

{tools_schema}

══ FORMATO OBRIGATÓRIO DE TOOL CALLING ══

Quando precisar usar uma ferramenta, responda EXATAMENTE neste formato — e
APENAS isto na sua resposta (sem texto antes ou depois):

<tool_call>
{{"name": "nome_exato_da_ferramenta", "arguments": {{"param1": "valor1"}}}}
</tool_call>

Use SEMPRE os nomes EXATOS das ferramentas listadas acima. Não traduza, não
abrevie, não invente nomes alternativos.

══ EXEMPLOS DE USO (few-shot) ══

Exemplo 1 — Usuário pede para adicionar tarefa:
USUÁRIO: "Adicione uma tarefa de revisar k-NN com prioridade alta para sexta"
ASSISTENTE:
<tool_call>
{{"name": "adicionar_tarefa", "arguments": {{"titulo": "Revisar k-NN", "prioridade": "alta", "prazo": "próxima sexta"}}}}
</tool_call>

Exemplo 2 — Usuário diz que terminou uma tarefa:
USUÁRIO: "Já terminei a tarefa 3"
ASSISTENTE:
<tool_call>
{{"name": "concluir_tarefa", "arguments": {{"tarefa_id": 3}}}}
</tool_call>

Exemplo 3 — Usuário cria evento:
USUÁRIO: "Marca uma prova de IA para amanhã às 14h"
ASSISTENTE:
<tool_call>
{{"name": "adicionar_evento_agenda", "arguments": {{"titulo": "Prova de IA", "data": "amanhã", "horario": "14:00", "tipo": "prova"}}}}
</tool_call>

Exemplo 4 — Pergunta sobre conteúdo:
USUÁRIO: "Explique árvores de decisão"
ASSISTENTE:
<tool_call>
{{"name": "buscar_material_rag", "arguments": {{"query": "árvores de decisão", "top_k": 4}}}}
</tool_call>

══ REGRAS GERAIS ══

- Seja direto, organizado e amigável.
- SEMPRE chame a ferramenta apropriada antes de responder sobre agenda, tarefas
  ou conteúdo dos materiais. Não invente dados.
- Para datas, você pode usar termos relativos ("amanhã", "próxima sexta") — o
  sistema resolve para a data absoluta. Mas SEMPRE prefira usar os valores
  exatos do bloco "CONTEXTO TEMPORAL ATUAL" no topo deste prompt.
- Após receber o <tool_result>, formule uma resposta em português brasileiro
  clara e útil, baseada nos dados retornados.
- Use markdown discreto para destacar pontos importantes (negrito, listas).
- Se não souber algo após consultar as ferramentas, diga claramente.
"""


def montar_system_prompt() -> str:
    """Monta o system prompt completo com contexto temporal atualizado."""
    return SYSTEM_PROMPT_TEMPLATE.format(
        contexto_temporal=gerar_contexto_temporal(),
        tools_schema=schema_para_prompt(),
    )


# ── Parser de tool calls (robusto) ───────────────────────────────────────────

# Padrões em ordem de preferência
_PATTERNS_TOOL_CALL = [
    # 1. <tool_call>{...}</tool_call> — formato canônico
    re.compile(r"<tool_call>\s*([\s\S]*?)\s*</tool_call>", re.IGNORECASE),
    # 2. ```json ... ``` ou ```tool_call ... ```
    re.compile(r"```(?:json|tool_call|tool)?\s*([\s\S]*?)\s*```", re.IGNORECASE),
    # 3. JSON solto contendo chaves típicas de tool call (último recurso)
    re.compile(
        r"(\{[^{}]*\"(?:name|tool|ferramenta|function|tool_name)\"[^{}]*"
        r"\"(?:arguments|args|parametros|parameters|input)\"[\s\S]*?\})"
    ),
]


def _limpar_json(raw: str) -> str:
    """Aplica transformações comuns para tornar JSON malformado parseável."""
    s = raw.strip()
    # Remove vírgulas finais antes de } ou ]
    s = re.sub(r",(\s*[}\]])", r"\1", s)
    # Aspas tipográficas → aspas normais
    s = s.replace("\u201c", '"').replace("\u201d", '"')
    s = s.replace("\u2018", "'").replace("\u2019", "'")
    return s


def _parsear_json_tolerante(raw: str) -> Optional[Dict]:
    """Tenta múltiplas estratégias para parsear JSON."""
    s = _limpar_json(raw)

    # Tentativa 1: JSON direto
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass

    # Tentativa 2: troca aspas simples por duplas
    try:
        return json.loads(s.replace("'", '"'))
    except json.JSONDecodeError:
        pass

    # Tentativa 3: extrai apenas o trecho entre { e } mais externo
    try:
        inicio = s.find("{")
        fim = s.rfind("}")
        if inicio >= 0 and fim > inicio:
            return json.loads(s[inicio : fim + 1])
    except json.JSONDecodeError:
        pass

    return None


def extrair_tool_call(texto: str) -> Optional[Tuple[str, Dict]]:
    """
    Extrai a primeira chamada de ferramenta do texto da LLM.
    Retorna (nome, argumentos) ou None se não houver.

    Tolera múltiplos formatos: tags <tool_call>, blocos markdown ```json,
    JSON solto, aspas simples, vírgulas finais, etc.
    """
    if not texto:
        return None

    for padrao in _PATTERNS_TOOL_CALL:
        match = padrao.search(texto)
        if not match:
            continue
        raw = match.group(1).strip()
        dados = _parsear_json_tolerante(raw)
        if not dados:
            logger.debug(f"[parser] JSON inválido em padrão {padrao.pattern[:30]}: {raw[:120]}")
            continue
        # Aceita várias formas de chave
        nome = (
            dados.get("name")
            or dados.get("tool")
            or dados.get("ferramenta")
            or dados.get("function")
            or dados.get("tool_name")
        )
        argumentos = (
            dados.get("arguments")
            or dados.get("args")
            or dados.get("parametros")
            or dados.get("parameters")
            or dados.get("input")
            or {}
        )
        if not isinstance(argumentos, dict):
            logger.warning(f"[parser] arguments não é dict: {type(argumentos)}. Convertendo.")
            argumentos = {}
        if nome:
            return str(nome), argumentos

    return None


# ── Chamada à LLM ────────────────────────────────────────────────────────────

def _chamar_llm(messages: List[Dict], max_tokens: int = 1500) -> str:
    """Faz uma chamada à API da LLM e retorna o conteúdo textual."""
    client = get_client()
    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=messages,
        max_tokens=max_tokens,
        temperature=0.5,  # menor temperatura para tool calling mais consistente
    )
    return response.choices[0].message.content or ""


# ── Orquestrador principal ───────────────────────────────────────────────────

MAX_ITERACOES_TOOL = 5


def processar_mensagem(
    historico: List[Dict[str, str]],
    conversa_id: Optional[str] = None,
    max_tokens: int = 1500,
) -> Dict[str, Any]:
    """
    Processa uma conversa com suporte a tool calling iterativo.
    Retorna a resposta final, a lista de tool_calls executados e metadados.
    """
    if not conversa_id:
        conversa_id = str(uuid.uuid4())[:8]

    system_msg = {"role": "system", "content": montar_system_prompt()}
    messages = [system_msg] + historico

    tool_calls_realizados: List[Dict] = []
    iteracao = 0
    resposta_texto = ""

    while iteracao < MAX_ITERACOES_TOOL:
        iteracao += 1
        logger.info(f"[{conversa_id}] Iteração {iteracao}: chamando LLM...")

        resposta_texto = _chamar_llm(messages, max_tokens=max_tokens)
        logger.info(
            f"[{conversa_id}] Resposta LLM (primeiros 200 chars): {resposta_texto[:200]}"
        )

        tool_info = extrair_tool_call(resposta_texto)

        if not tool_info:
            # Resposta final — sem tool call
            return {
                "resposta": resposta_texto.strip(),
                "tool_calls": tool_calls_realizados,
                "iteracoes": iteracao,
                "conversa_id": conversa_id,
            }

        nome_tool, args_tool = tool_info
        logger.info(f"[{conversa_id}] Tool call detectado: {nome_tool}({args_tool})")

        # Executa a ferramenta (com aliases e normalização internos)
        resultado, erro = executar_ferramenta(
            nome_tool, args_tool, conversa_id=conversa_id
        )

        tool_calls_realizados.append({
            "ferramenta": nome_tool,
            "argumentos": args_tool,
            "resultado": resultado,
            "erro": erro,
        })

        # Injeta o resultado da ferramenta na conversa
        resultado_str = json.dumps(resultado, ensure_ascii=False, indent=2)
        messages.append({"role": "assistant", "content": resposta_texto})
        messages.append({
            "role": "user",
            "content": (
                f"<tool_result>\n{resultado_str}\n</tool_result>\n\n"
                "Agora responda ao usuário em português, de forma clara e útil, "
                "com base nesse resultado. Não chame outra ferramenta a menos que "
                "seja absolutamente necessário."
            ),
        })

    logger.warning(f"[{conversa_id}] Limite de iterações de tool calling atingido.")
    return {
        "resposta": resposta_texto.strip(),
        "tool_calls": tool_calls_realizados,
        "iteracoes": iteracao,
        "conversa_id": conversa_id,
        "aviso": "Limite de chamadas de ferramentas atingido.",
    }


# ── Geração de exercícios (funcionalidade de aprendizado) ────────────────────

def gerar_exercicios(tema: str, quantidade: int = 3) -> str:
    """Gera exercícios usando RAG + LLM."""
    from backend.rag import get_rag
    rag = get_rag()
    trechos = rag.buscar(tema, top_k=3)

    contexto = "\n\n".join(
        f"[{t['source']}]\n{t['content']}" for t in trechos
    ) if trechos else "Nenhum material encontrado sobre este tema."

    prompt = f"""Com base no seguinte material de estudo:

{contexto}

Gere {quantidade} exercícios sobre "{tema}".
Para cada exercício:
1. Formule a pergunta claramente
2. Se for múltipla escolha, forneça 4 alternativas (A, B, C, D) e indique a correta
3. Dê uma breve explicação da resposta

Foco em active recall — perguntas que estimulem o estudante a lembrar e refletir."""

    messages = [
        {"role": "system", "content": "Você é um professor especialista em criar exercícios pedagógicos eficazes."},
        {"role": "user", "content": prompt},
    ]

    return _chamar_llm(messages, max_tokens=2000)


def avaliar_resposta_exercicio(pergunta: str, resposta_aluno: str, tema: str) -> str:
    """Avalia a resposta de um estudante usando RAG + LLM."""
    from backend.rag import get_rag
    rag = get_rag()
    trechos = rag.buscar(tema, top_k=2)

    contexto = "\n\n".join(t["content"] for t in trechos) if trechos else ""

    prompt = f"""Pergunta: {pergunta}

Resposta do estudante: {resposta_aluno}

Material de referência: {contexto}

Avalie a resposta do estudante:
1. Está correta, parcialmente correta ou incorreta?
2. O que o estudante acertou?
3. O que faltou ou estava incorreto?
4. Qual a resposta completa e correta?
5. Dê uma nota de 0 a 10.

Seja construtivo e didático no feedback."""

    messages = [
        {"role": "system", "content": "Você é um tutor acadêmico experiente avaliando respostas de estudantes."},
        {"role": "user", "content": prompt},
    ]

    return _chamar_llm(messages, max_tokens=1000)
