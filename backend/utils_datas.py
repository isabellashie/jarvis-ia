"""
Utilitários de parsing de datas em português brasileiro.

Resolve termos relativos comuns ("amanhã", "próxima sexta", "daqui 3 dias")
para datas absolutas no formato YYYY-MM-DD.

Esta camada existe porque LLMs (especialmente modelos médios como Gemma 12B)
frequentemente erram o cálculo aritmético de datas. Resolvemos em Python para
garantir precisão e centralizar a lógica.
"""

import re
import unicodedata
from datetime import date, datetime, timedelta
from typing import Optional

# Mapeamento de dia da semana (0 = segunda, 6 = domingo, padrão Python)
_DIAS_SEMANA = {
    "segunda": 0, "segunda-feira": 0, "seg": 0,
    "terca": 1, "terça": 1, "terca-feira": 1, "terça-feira": 1, "ter": 1,
    "quarta": 2, "quarta-feira": 2, "qua": 2,
    "quinta": 3, "quinta-feira": 3, "qui": 3,
    "sexta": 4, "sexta-feira": 4, "sex": 4,
    "sabado": 5, "sábado": 5, "sab": 5,
    "domingo": 6, "dom": 6,
}

_DIAS_SEMANA_DISPLAY = [
    "segunda-feira", "terça-feira", "quarta-feira",
    "quinta-feira", "sexta-feira", "sábado", "domingo",
]

# Números por extenso em PT-BR (suficiente para casos comuns)
_NUMEROS_PT = {
    "um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "três": 3,
    "quatro": 4, "cinco": 5, "seis": 6, "sete": 7, "oito": 8,
    "nove": 9, "dez": 10, "onze": 11, "doze": 12, "treze": 13,
    "catorze": 14, "quatorze": 14, "quinze": 15, "vinte": 20, "trinta": 30,
}


def _normalizar(s: str) -> str:
    """Remove acentos, baixa caixa e tira espaços extras."""
    s = s.strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"\s+", " ", s)
    return s


def _parse_numero(token: str) -> Optional[int]:
    """Converte '3', 'três', 'tres' em inteiro. Retorna None se não conseguir."""
    token = token.strip().lower()
    if token.isdigit():
        return int(token)
    return _NUMEROS_PT.get(token)


def resolver_data_relativa(texto: str, referencia: Optional[date] = None) -> Optional[str]:
    """
    Tenta interpretar um termo de data (relativo ou absoluto) e retorna a data
    no formato 'YYYY-MM-DD'. Retorna None se não conseguir interpretar.

    Casos suportados:
      - Absolutas: 'YYYY-MM-DD', 'DD/MM/YYYY', 'DD-MM-YYYY'
      - 'hoje', 'amanhã', 'depois de amanhã', 'ontem'
      - 'próxima sexta', 'proxima segunda', 'sexta-feira', 'sexta que vem'
      - 'essa/esta quinta', 'nesta sexta'
      - 'daqui 3 dias', 'em 5 dias', 'daqui a uma semana'
      - 'fim de semana' (próximo sábado)
    """
    if not texto or not texto.strip():
        return None

    hoje = referencia or date.today()
    texto_norm = _normalizar(texto)

    # ── 1. Já é um formato absoluto? ────────────────────────────────────────
    formatos_absolutos = ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"]
    for fmt in formatos_absolutos:
        try:
            return datetime.strptime(texto.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue

    # ── 2. Termos diretos ───────────────────────────────────────────────────
    if texto_norm in ("hoje", "today"):
        return hoje.isoformat()
    if texto_norm in ("amanha", "amanhã", "tomorrow"):
        return (hoje + timedelta(days=1)).isoformat()
    if texto_norm in ("depois de amanha", "depois de amanhã"):
        return (hoje + timedelta(days=2)).isoformat()
    if texto_norm in ("ontem", "yesterday"):
        return (hoje - timedelta(days=1)).isoformat()
    if "fim de semana" in texto_norm or "final de semana" in texto_norm:
        # próximo sábado
        dias_ate_sabado = (5 - hoje.weekday()) % 7 or 7
        return (hoje + timedelta(days=dias_ate_sabado)).isoformat()

    # ── 3. "daqui N dias" / "em N dias" / "daqui a N dias" ──────────────────
    padrao_dias = re.search(
        r"(?:daqui|em|dentro de)\s*(?:a\s*)?(\w+)\s*dias?",
        texto_norm,
    )
    if padrao_dias:
        n = _parse_numero(padrao_dias.group(1))
        if n is not None:
            return (hoje + timedelta(days=n)).isoformat()

    # ── 4. "daqui N semanas" ────────────────────────────────────────────────
    padrao_semanas = re.search(
        r"(?:daqui|em|dentro de)\s*(?:a\s*)?(\w+)\s*semanas?",
        texto_norm,
    )
    if padrao_semanas:
        n = _parse_numero(padrao_semanas.group(1))
        if n is not None:
            return (hoje + timedelta(weeks=n)).isoformat()

    # ── 5. Dia da semana com modificador ────────────────────────────────────
    # Casos: "próxima sexta", "sexta-feira", "esta quarta", "sexta que vem"
    # Substitui hífens por espaço para que "sexta-feira" funcione com \b
    texto_check = texto_norm.replace("-", " ")
    # Ordena por nome mais longo primeiro para que "segunda-feira" tenha
    # prioridade sobre "segunda" e abreviações como "seg".
    for nome_dia, idx_dia in sorted(
        _DIAS_SEMANA.items(), key=lambda kv: -len(kv[0])
    ):
        nome_check = nome_dia.replace("-", " ")
        # Word boundary previne match em substrings (ex: "qui" em "aqui")
        if not re.search(rf"\b{re.escape(nome_check)}\b", texto_check):
            continue

        tem_proxima = bool(re.search(r"\b(proxima|próxima|que vem|seguinte)\b", texto_norm))
        tem_esta = bool(re.search(r"\b(esta|essa|deste|desta|nesta|nessa)\b", texto_norm))

        dias_diff = (idx_dia - hoje.weekday()) % 7

        if tem_proxima:
            # "próxima X": sempre na semana seguinte
            if dias_diff == 0:
                dias_diff = 7
            else:
                # Se o dia ainda está nesta semana, "próxima" significa a seguinte
                if dias_diff <= (6 - hoje.weekday()):
                    dias_diff += 7
        elif tem_esta:
            # "esta X": dentro da semana atual
            if dias_diff == 0:
                return hoje.isoformat()
        else:
            # Apenas "sexta" sozinho → próxima ocorrência
            if dias_diff == 0:
                dias_diff = 7

        return (hoje + timedelta(days=dias_diff)).isoformat()

    # ── 6. Não conseguiu interpretar ────────────────────────────────────────
    return None


def gerar_contexto_temporal() -> str:
    """
    Gera um bloco textual com o contexto temporal absoluto.
    Usado no topo do system prompt para que o LLM não precise calcular datas.
    """
    agora = datetime.now()
    hoje = agora.date()
    dia_idx = hoje.weekday()
    nome_dia = _DIAS_SEMANA_DISPLAY[dia_idx]

    # Datas relativas pré-calculadas (evita o LLM ter que fazer aritmética)
    amanha = hoje + timedelta(days=1)
    depois_amanha = hoje + timedelta(days=2)

    proximos_dias_semana = []
    for offset_nome, offset_idx in [
        ("segunda", 0), ("terça", 1), ("quarta", 2),
        ("quinta", 3), ("sexta", 4), ("sábado", 5), ("domingo", 6),
    ]:
        dias_diff = (offset_idx - dia_idx) % 7
        if dias_diff == 0:
            dias_diff = 7  # próxima ocorrência, não hoje
        data_alvo = hoje + timedelta(days=dias_diff)
        proximos_dias_semana.append(
            f"  - Próxima {offset_nome}: {data_alvo.isoformat()}"
        )

    bloco = [
        "═══════════════════════════════════════════════════════════════",
        "  CONTEXTO TEMPORAL ATUAL (use estes valores, não calcule sozinho)",
        "═══════════════════════════════════════════════════════════════",
        f"  HOJE é {nome_dia}, {hoje.strftime('%d/%m/%Y')} ({hoje.isoformat()})",
        f"  Agora são {agora.strftime('%H:%M')}.",
        "",
        "  Datas absolutas pré-calculadas (use-as quando o usuário usar termos relativos):",
        f"  - Hoje:               {hoje.isoformat()}",
        f"  - Amanhã:             {amanha.isoformat()}",
        f"  - Depois de amanhã:   {depois_amanha.isoformat()}",
        *proximos_dias_semana,
        "",
        "  REGRA: ao chamar ferramentas que recebem data, SEMPRE passe no formato",
        "  YYYY-MM-DD usando os valores acima. Não tente calcular datas mentalmente.",
        "═══════════════════════════════════════════════════════════════",
    ]
    return "\n".join(bloco)
