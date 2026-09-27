"""
Excel Copiloto IA — assistente conversacional NL→Excel.
=========================================================

Módulo PURO (pandas/openpyxl; LLM opcional via Ollama) que permite ao
utilizador fazer upload de um ficheiro e perguntar, em linguagem natural
(PT ou EN), o que quer fazer com os dados:

    • "mostra o top 10 fornecedores por valor"
    • "agrupa por categoria e calcula a média"
    • "sugere fórmulas para o ficheiro ficar automático"
    • "adiciona coluna do mês e um acumulado"
    • "como apresentar isto num dashboard?"

Fluxo:
    1. read/standardize (reutiliza excel_service)
    2. contexto do DataFrame (schema + estatísticas compactas)
    3. plano: LLM (Ollama/DeepSeek) com fallback determinístico (rule engine)
    4. execução de operações validadas (sort/filter/aggregate/pivot/…)
    5. pack de fórmulas PT-PT + EN, consciente da semântica das colunas
    6. workbook final com Tabela Excel, KPIs VIVOS (fórmulas) e folha
       "Fórmulas" para o ficheiro ficar auto-atualizável e apresentável.

Segurança: as operações vindas do LLM são validadas contra uma whitelist
(nada de SQL/código arbitrário); fórmulas do LLM são sanitizadas.
"""

import io
import os
import re
import json
import logging
import unicodedata
from datetime import datetime

import numpy as np
import pandas as pd

from . import excel_service as es

logger = logging.getLogger(__name__)

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("AUDIT_OLLAMA_MODEL", "deepseek-r1:1.5b")
OLLAMA_TIMEOUT = float(os.environ.get("AUDIT_OLLAMA_TIMEOUT", "25"))

# Rótulos canônicos usados no workbook gerado e nas fórmulas (fallback
# quando não conhecemos os cabeçalhos originais do utilizador).
CANON_LABELS_PT = {
    "transaction_id": "Nº Documento", "vendor": "Fornecedor", "amount": "Valor",
    "currency": "Moeda", "timestamp": "Data", "category": "Categoria",
    "user_id": "Usuário", "status": "Estado",
}
CANON_LABELS_EN = {
    "transaction_id": "Doc No", "vendor": "Vendor", "amount": "Amount",
    "currency": "Currency", "timestamp": "Date", "category": "Category",
    "user_id": "User", "status": "Status",
}
CANON_ORDER = ["transaction_id", "vendor", "amount", "currency",
               "timestamp", "category", "user_id", "status"]

WEEKDAY_PT = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
              "sexta-feira", "sábado", "domingo"]

TABLE_NAME = "tblDados"


def strip_accents(text: str) -> str:
    return unicodedata.normalize("NFKD", str(text or ""))\
        .encode("ascii", "ignore").decode("ascii")


def norm_q(text: str) -> str:
    """Pergunta normalizada: minúsculas, sem acentos, espaços únicos."""
    return re.sub(r"\s+", " ", strip_accents(text).lower()).strip()


# ---------------------------------------------------------------------------
# 1. CONTEXTO DO DATAFRAME (para o LLM e para o rule engine)
# ---------------------------------------------------------------------------

def describe_frame(df: pd.DataFrame) -> dict:
    """Estatísticas compactas do frame canônico — base do contexto."""
    info = {"rows": int(len(df)), "columns": []}
    for col in df.columns:
        s = df[col]
        entry = {
            "name": str(col),
            "non_null": int(s.notna().sum()),
            "null_pct": round(float(s.isna().mean()) * 100, 1),
            "sample": [ _json_safe(v) for v in s.dropna().unique()[:3] ],
        }
        if pd.api.types.is_numeric_dtype(s):
            entry["type"] = "numeric"
            if len(s.dropna()):
                entry.update({
                    "sum": float(s.sum()), "mean": float(s.mean()),
                    "min": float(s.min()), "max": float(s.max()),
                })
        elif pd.api.types.is_datetime64_any_dtype(s):
            entry["type"] = "date"
            d = s.dropna()
            if len(d):
                entry["min"] = str(d.min().date()); entry["max"] = str(d.max().date())
        else:
            entry["type"] = "text"
            vc = s.astype(str).value_counts()
            entry["unique"] = int(s.nunique())
            if len(vc):
                entry["top_values"] = [[str(k), int(v)] for k, v in vc.head(5).items()]
        info["columns"].append(entry)
    return info


def _json_safe(v):
    """Converte valores pandas/numpy para tipos JSON-safe."""
    if v is None:
        return None
    if isinstance(v, (pd.Timestamp, datetime)):
        return v.isoformat()
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating, float)):
        f = float(v)
        return None if (np.isnan(f) or np.isinf(f)) else f
    if isinstance(v, (np.bool_, bool)):
        return bool(v)
    if pd.isna(v):
        return None
    return str(v)


def semantic_roles(df: pd.DataFrame) -> dict:
    """Quais campos canônicos existem (com rótulo original quando possível)."""
    roles = {}
    for canon in CANON_ORDER:
        if canon in df.columns:
            roles[canon] = str(df[canon].name)
    return roles


def build_llm_context(ctx: dict, sheet_name: str, question: str) -> str:
    """Schema compacto e legível para o prompt do LLM."""
    lines = [f"FOLHA: {sheet_name} | LINHAS: {ctx['rows']}"]
    for c in ctx["columns"]:
        bits = [f"{c['name']} ({c['type']})"]
        if c["type"] == "numeric":
            bits.append(f"soma={c.get('sum', 0):.2f} média={c.get('mean', 0):.2f} max={c.get('max', 0):.2f}")
        elif c["type"] == "date":
            bits.append(f"de {c.get('min','?')} a {c.get('max','?')}")
        elif "top_values" in c:
            tops = ", ".join(f"{k} ({n})" for k, n in c["top_values"][:3])
            bits.append(f"{c.get('unique', 0)} valores únicos; mais comuns: {tops}")
        lines.append("COLUNA: " + " | ".join(bits))
    lines.append(f"PERGUNTA DO UTILIZADOR: {question}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 2. RECOMENDADOR DE FÓRMULAS (PT-PT + EN, referências estruturadas)
# ---------------------------------------------------------------------------

def _col_label(canon: str, headers: dict = None, lang: str = "pt") -> str:
    """Rótulo a usar na fórmula: cabeçalho original > rótulo canônico."""
    if headers and headers.get(canon):
        return str(headers[canon])
    return CANON_LABELS_PT.get(canon) if lang == "pt" else CANON_LABELS_EN.get(canon, canon)


def suggest_formulas(df: pd.DataFrame, headers: dict = None) -> list:
    """
    Pack de fórmulas consciente da semântica das colunas.
    Cada recomendação usa referências estruturadas (Tabela 'tblDados') para
    que o ficheiro se atualize sozinho quando o utilizador acrescentar linhas.
    `headers` mapeia campo canônico → cabeçalho original do ficheiro.
    """
    cols = set(df.columns)
    pt = lambda c: _col_label(c, headers, "pt")
    en = lambda c: _col_label(c, headers, "en")
    out = []

    def add(id_, title, category, f_pt, f_en, explanation, where, needs_365=False, column=None):
        out.append({
            "id": id_, "title": title, "category": category,
            "formula_pt": f_pt, "formula_en": f_en,
            "explanation": explanation, "where": where,
            "needs_365": needs_365, "column": column,
        })

    # 0) Conselho base — Tabela Excel (não é fórmula, mas é o passo 1)
    add("tabela", "Converter os dados numa Tabela Excel", "Automação",
        "Selecionar os dados → Ctrl+T → renomear para 'tblDados'",
        "Select the data → Ctrl+T → rename to 'tblDados'",
        "É a base de toda a automação: as fórmulas abaixo usam referências "
        "estruturadas (tblDados[...]) que crescem automaticamente quando "
        "adiciona linhas — nunca mais precisa de arrastar intervalos.",
        "Folha de dados", False, None)

    if "amount" in cols:
        v, ve = pt("amount"), en("amount")
        add("kpi_total", "Total dos valores (KPI vivo)", "KPI",
            f"=SOMA({TABLE_NAME}[{v}])", f"=SUM({TABLE_NAME}[{ve}])",
            "KPI que se recalcula sozinho com cada linha nova. Use no Sumário "
            "para a visão imediata do montante total.", "Folha Sumário",
            False, "amount")
        add("kpi_media", "Valor médio", "KPI",
            f"=MÉDIA({TABLE_NAME}[{v}])", f"=AVERAGE({TABLE_NAME}[{ve}])",
            "Média sempre atualizada; combine com SEERRO para não mostrar "
            "erros quando a tabela está vazia.", "Folha Sumário", False, "amount")
        add("kpi_max", "Maior valor", "KPI",
            f"=MÁXIMO({TABLE_NAME}[{v}])", f"=MAX({TABLE_NAME}[{ve}])",
            "Detecta de imediato a transação mais pesada do período.",
            "Folha Sumário", False, "amount")

    if "status" in cols and "amount" in cols:
        v, ve = pt("amount"), en("amount")
        st, ste = pt("status"), en("status")
        top_status = str(df["status"].dropna().astype(str).value_counts().index[0]) \
            if df["status"].notna().any() else "Pending"
        add("kpi_estado", f"Total por estado ('{top_status}')", "KPI",
            f'=SOMASES({TABLE_NAME}[{v}];{TABLE_NAME}[{st}];"{top_status}")',
            f'=SUMIFS({TABLE_NAME}[{ve}],{TABLE_NAME}[{ste}],"{top_status}")',
            "Soma condicional por estado — troque o texto entre aspas para "
            "obter um KPI por cada estado do processo.", "Folha Sumário",
            False, "status")
        add("kpi_contagem_estado", f"Nº de registos por estado", "KPI",
            f'=CONT.SES({TABLE_NAME}[{st}];"{top_status}")',
            f'=COUNTIFS({TABLE_NAME}[{ste}],"{top_status}")',
            "Contagem viva por estado — ideal para painéis de aprovações "
            "pendentes vs. concluídas.", "Folha Sumário", False, "status")

    if "category" in cols and "amount" in cols:
        v, ve = pt("amount"), en("amount")
        c, ce = pt("category"), en("category")
        add("resumo_categoria", "Resumo dinâmico por categoria", "Automação",
            f"=ÚNICO({TABLE_NAME}[{c}])",
            f"=UNIQUE({TABLE_NAME}[{ce}])",
            "Numa coluna vazia, esta fórmula de matriz devolve todas as "
            "categorias e cresce sozinha. Ao lado, use SOMASES/SUMIFS com a "
            "célula da categoria como critério para o total — uma tabela de "
            "resumo que nunca fica desatualizada.", "Nova folha 'Resumo'",
            True, "category")
        add("total_categoria", "Total de uma categoria (célula dinâmica)", "Análise",
            f"=SOMASES({TABLE_NAME}[{v}];{TABLE_NAME}[{c}];F2)",
            f"=SUMIFS({TABLE_NAME}[{ve}],{TABLE_NAME}[{ce}],F2)",
            "Troque F2 pela célula que contém a categoria (ex.: resultado do "
            "ÚNICO). Uma única fórmula serve a tabela de resumo inteira "
            "arrastando para baixo.", "Ao lado do resumo por categoria",
            False, "category")
        add("pct_categoria", "% de cada categoria no total", "Apresentação",
            f"=SOMASES({TABLE_NAME}[{v}];{TABLE_NAME}[{c}];F2)/SOMA({TABLE_NAME}[{v}])",
            f"=SUMIFS({TABLE_NAME}[{ve}],{TABLE_NAME}[{ce}],F2)/SUM({TABLE_NAME}[{ve}])",
            "Percentagem dinâmica por categoria — formate a coluna como %. "
            "Excelente para gráficos de pizza sempre corretos.",
            "Folha 'Resumo'", False, "category")

    if "vendor" in cols and "amount" in cols:
        v, ve = pt("amount"), en("amount")
        f, fe = pt("vendor"), en("vendor")
        add("top10_fornecedores", "Top 10 fornecedores numa só fórmula", "Análise",
            f"=TOMAR(ORDENAR.POR(ÚNICO({TABLE_NAME}[{f}]);"
            f"SOMASES({TABLE_NAME}[{v}];{TABLE_NAME}[{f}];ÚNICO({TABLE_NAME}[{f}]));-1);10)",
            f"=TAKE(SORTBY(UNIQUE({TABLE_NAME}[{fe}]),"
            f"SUMIFS({TABLE_NAME}[{ve}],{TABLE_NAME}[{fe}],UNIQUE({TABLE_NAME}[{fe}])),-1),10)",
            "Lista dinâmica dos 10 maiores fornecedores por valor, sempre "
            "ordenada. Mude o 10 final para outro N. Requer Excel 365/2021.",
            "Folha 'Resumo'", True, "vendor")
        add("dupe_vendor", "Detetar fornecedores repetidos", "Análise",
            f'=SE(CONT.SES({TABLE_NAME}[{f}];[@[{f}]])>1;"Repetido";"OK")',
            f'=IF(COUNTIFS({TABLE_NAME}[{fe}],[@[{fe}]])>1,"Repeated","OK")',
            "Marca linhas cujo fornecedor aparece mais que uma vez — útil "
            "para padrões de fraccionamento ou pagamentos recorrentes.",
            "Coluna extra na folha de dados", False, "vendor")

    if "timestamp" in cols:
        d, de = pt("timestamp"), en("timestamp")
        add("col_mes", "Coluna auxiliar do Mês", "Automação",
            f'=TEXTO([@[{d}]];"aaaa-mm")', f'=TEXT([@[{de}]],"yyyy-mm")',
            "Base para somas mensais, gráficos de evolução e segmentações — "
            "calculada a partir da data, nunca digitada à mão.",
            "Coluna extra na folha de dados", False, "timestamp")
        add("aging", "Idade do registo (dias)", "Análise",
            f"=HOJE()-[@[{d}]]", f"=TODAY()-[@[{de}]]",
            "Dias decorridos desde a data do registo — formate como número "
            "e use formatação condicional para antigos > 60/90 dias.",
            "Coluna extra", False, "timestamp")
        if "amount" in cols:
            v, ve = pt("amount"), en("amount")
            add("acumulado", "Total acumulado por data", "Análise",
                f"=SOMA(ÍNDICE({TABLE_NAME}[{v}];1):[@[{v}]])",
                f"=SUM(INDEX({TABLE_NAME}[{ve}],1):[@[{ve}]])",
                "Soma acumulada que respeita a ordem das linhas — perfeita "
                "para curvas S e gráficos de evolução de despesa.",
                "Coluna extra", False, "amount")

    if "amount" in cols:
        v, ve = pt("amount"), en("amount")
        add("pct_total", "% de cada linha no total", "Apresentação",
            f"=[@[{v}]]/SOMA({TABLE_NAME}[{v}])",
            f"=[@[{ve}]]/SUM({TABLE_NAME}[{ve}])",
            "Peso de cada linha no total — com formatação % e barras de "
            "dados fica um 'in-app chart' sempre atualizado.",
            "Coluna extra", False, "amount")
        add("rank_valor", "Ranking da linha por valor", "Análise",
            f"=SOMARPRODUTO(({TABLE_NAME}[{v}]>[@[{v}]])*1)+1",
            f"=SUMPRODUCT(({TABLE_NAME}[{ve}]>[@[{ve}]])*1)+1",
            "Ranking sem colunas auxiliares — 1.º, 2.º, 3.º maior valor, "
            "recalculado sozinho.", "Coluna extra", False, "amount")
        add("alerta_alto", "Alerta de valor a revisar", "Automação",
            f'=SE([@[{v}]]>=10000;"Revisão obrigatória";"OK")',
            f'=IF([@[{ve}]]>=10000,"Mandatory review","OK")',
            "Ajuste o limiar 10000 ao seu materiality — a coluna acende "
            "automaticamente nas linhas acima do limiar.",
            "Coluna extra", False, "amount")

    if "transaction_id" in cols:
        t, te = pt("transaction_id"), en("transaction_id")
        add("dupe_id", "Detetar IDs duplicados", "Análise",
            f'=SE(CONT.SES({TABLE_NAME}[{t}];[@[{t}]])>1;"DUPLICADO";"OK")',
            f'=IF(COUNTIFS({TABLE_NAME}[{te}],[@[{te}]])>1,"DUPLICATE","OK")',
            "Controlo de integridade em tempo real — combina com formatação "
            "condicional para pintar a linha inteira de vermelho.",
            "Coluna extra", False, "transaction_id")

    if "vendor" in cols and "amount" in cols:
        v, ve = pt("amount"), en("amount")
        t, te = pt("transaction_id"), en("transaction_id")
        f, fe = pt("vendor"), en("vendor")
        add("procx", "Pesquisa instantânea por documento", "Pesquisa",
            f'=PROCX(H2;{TABLE_NAME}[{t}];{TABLE_NAME}[{v}];"não encontrado")',
            f'=XLOOKUP(H2,{TABLE_NAME}[{te}],{TABLE_NAME}[{ve}],"not found")',
            "Escreva o nº do documento em H2 e obtenha o valor na hora — "
            "substitua a coluna final para pesquisar outros campos.",
            "Folha de pesquisa / Sumário", True, "transaction_id")
        add("dupes_cf", "Formatação condicional de duplicados", "Apresentação",
            "Selecionar coluna → Formatação Condicional → Valores Duplicados",
            "Select column → Conditional Formatting → Duplicate Values",
            "Um clique para realçar valores repetidos; nativo do Excel, sem "
            "fórmulas. Combine com 'Corresponder a colunas' para multi-campo.",
            "Folha de dados", False, "transaction_id")

    return out


CHART_SUGGESTIONS = [
    {"type": "pie", "title": "Distribuição por Categoria",
     "description": "Pizza com a fatia de cada categoria — use o resumo dinâmico (ÚNICO + SOMASES) como fonte."},
    {"type": "bar", "title": "Top 10 Fornecedores por Valor",
     "description": "Barras horizontais a partir do Top 10 dinâmico; ordena-se sozinho via ORDENAR.POR."},
    {"type": "line", "title": "Evolução Mensal do Valor",
     "description": "Linha por mês usando a coluna auxiliar Mês (TEXTO aaaa-mm) + SOMASES."},
    {"type": "bar", "title": "Estado dos Processos",
     "description": "Colunas com CONT.SES por estado — painel de pendências em tempo real."},
]


# ---------------------------------------------------------------------------
# 3. RULE ENGINE — interpretação determinística PT/EN (fallback sem LLM)
# ---------------------------------------------------------------------------

_INTENT_PATTERNS = [
    # (intent, regex sobre a pergunta normalizada) — ordem = prioridade
    ("formula",    r"\b(formula|formulas|formula s|sugere|sugestao|sugestoes|automat|sozinho|sozinha|atualiz|dinamic|sem fazer manual)\w*"),
    ("duplicates", r"\b(duplicad|repetid|duplicat|repea)\w*"),
    ("filter",     r"\b(filtra|filtrar|filtro|apenas|somente|só |so os|so as|maior que|menor que|acima de|abaixo de|entre |antes de|depois de|show only|only |where |acima do|abaixo do)\b"),
    ("top_n",      r"\b(top|maiores|menores|maior|menor|melhores|piores|highest|largest|biggest|lowest)\b"),
    ("aggregate",  r"\b(total|soma|somar|media|mediana|media de|sum|average|avg|media por|resumo|distribuic|agrup|group by|por categoria|por fornecedor|por mes|por estado|por usuario|por moeda|breakdown)\b"),
    ("chart",      r"\b(grafic|graf|chart|visualiz|plot|apresentar grafico)\w*"),
    ("dashboard",  r"\b(dashboard|kpi|painel|indicadores|scorecard|resumo executivo)\b"),
    ("add_column", r"\b(adiciona|acrescenta|cria(r)? coluna|nova coluna|coluna do|coluna de|mes |trimestre|ano |dia da semana|acumulado|ranking?|% |percent|percentagem|faixa|aging|idade)\b"),
]

# Palavras-chave de colunas (PT/EN) → campo canônico
_COL_WORDS = [
    ("fornecedor", "vendor"), ("fornecedores", "vendor"), ("vendor", "vendor"),
    ("entidade", "vendor"), ("beneficiario", "vendor"),
    ("categoria", "category"), ("categorias", "category"), ("classe", "category"),
    ("rubrica", "category"), ("centro de custo", "category"), ("tipo", "category"),
    ("estado", "status"), ("status", "status"), ("situacao", "status"),
    ("usuario", "user_id"), ("utilizador", "user_id"), ("aprovador", "user_id"),
    ("user", "user_id"), ("moeda", "currency"), ("currency", "currency"),
    ("valor", "amount"), ("valor es", "amount"), ("amount", "amount"),
    ("montante", "amount"), ("total ", "amount"),
    ("data", "timestamp"), ("mes", "timestamp"), ("datas", "timestamp"),
    ("date", "timestamp"), ("month", "timestamp"),
    ("documento", "transaction_id"), ("id", "transaction_id"), ("nota", "transaction_id"),
]


def detect_intents(question: str) -> list:
    q = norm_q(question)
    if not q:
        return ["explain"]
    found = []
    for intent, pattern in _INTENT_PATTERNS:
        if re.search(pattern, q):
            found.append(intent)
    return found or ["explain"]


def _parse_number(token: str):
    """Aceita 10000 / 10.000 / 10,000 / 10 000 / 10k."""
    t = token.strip().lower().replace(" ", "")
    m = re.match(r"^(\d+(?:[.,]\d+)?)k$", t)
    if m:
        return float(m.group(1).replace(",", ".")) * 1000
    m = re.match(r"^(\d{1,3}(?:\.\d{3})+)(?:,\d+)?$", t)      # 10.000,50
    if m:
        return float(m.group(1).replace(".", ""))
    m = re.match(r"^(\d{1,3}(?:,\d{3})+)(?:\.\d+)?$", t)      # 10,000.50
    if m:
        return float(m.group(1).replace(",", ""))
    try:
        return float(t.replace(",", "."))
    except ValueError:
        return None


def _mentioned_cols(question: str) -> list:
    q = " " + norm_q(question) + " "
    cols = []
    for word, canon in _COL_WORDS:
        if f" {word} " in q or q.startswith(f" {word}") or f" {word}:" in q:
            if canon not in cols:
                cols.append(canon)
    return cols


def _extract_number_near(question: str, patterns: list):
    q = norm_q(question)
    for pat in patterns:
        m = re.search(pat, q)
        if m:
            tail = m.group(1) if m.lastindex else ""
            n = _parse_number(tail) if tail else None
            if n is not None:
                return n
    # último número solto como fallback
    for m in re.finditer(r"\d[\d.,]*\s*k?", q):
        n = _parse_number(m.group(0))
        if n is not None:
            return n
    return None


def _parse_filter_ops(question: str, ctx: dict) -> list:
    """Extrai condições de filtro de linguagem natural."""
    q = norm_q(question)
    ops = []
    numeric = _has_col(ctx, "amount")

    for pat, key in [(r"maior (?:que|do que) ([\d.,]+\s*k?)", "gt"),
                     (r"acima de ([\d.,]+\s*k?)", "gt"),
                     (r"mais de ([\d.,]+\s*k?)", "gt"),
                     (r"superior (?:a|que) ([\d.,]+\s*k?)", "gt"),
                     (r"menor (?:que|do que) ([\d.,]+\s*k?)", "lt"),
                     (r"abaixo de ([\d.,]+\s*k?)", "lt"),
                     (r"menos de ([\d.,]+\s*k?)", "lt"),
                     (r"inferior (?:a|que) ([\d.,]+\s*k?)", "lt")]:
        m = re.search(pat, q)
        if m and numeric:
            n = _parse_number(m.group(1))
            if n is not None:
                ops.append({"op": "filter", "column": "amount", key: n})
                break

    m = re.search(r"entre ([\d.,]+\s*k?) e ([\d.,]+\s*k?)", q)
    if m and numeric:
        a, b = _parse_number(m.group(1)), _parse_number(m.group(2))
        if a is not None and b is not None:
            ops.append({"op": "filter", "column": "amount", "gte": min(a, b),
                        "lte": max(a, b)})

    m = re.search(r"(?:ano|year) (\d{4})", q)
    if m and _has_col(ctx, "timestamp"):
        ops.append({"op": "filter", "column": "timestamp", "year": int(m.group(1))})

    for label, canon in [("fornecedor", "vendor"), ("categoria", "category"),
                         ("estado", "status"), ("moeda", "currency"),
                         ("usuario", "user_id")]:
        m = re.search(rf"{label} ([\w'\-][\w'\- &.]*)", q)
        if m and _has_col(ctx, canon):
            val = m.group(1).strip()
            for stop in (" por ", " com ", " e ", " maior", " menor", " ordena",
                         " mostra", " filtra", " no ", " que "):
                idx = val.find(stop)
                if idx > 0:
                    val = val[:idx]
            val = val.strip(" .,:;")
            if len(val) >= 2:
                ops.append({"op": "filter", "column": canon, "contains": val})
            break
    return ops


def _has_col(ctx: dict, canon: str) -> bool:
    return any(c["name"] == canon for c in ctx["columns"])


def _groupby_from_question(question: str, ctx: dict, default="category"):
    cols = _mentioned_cols(question)
    for pref in ("vendor", "category", "status", "user_id", "currency"):
        if pref in cols and _has_col(ctx, pref):
            return pref
    return default if _has_col(ctx, default) else None


def _answer_overview(ctx: dict, headers: dict) -> str:
    rows = ctx["rows"]
    amt = next((c for c in ctx["columns"] if c["name"] == "amount"), None)
    ts = next((c for c in ctx["columns"] if c["name"] == "timestamp"), None)
    ven = next((c for c in ctx["columns"] if c["name"] == "vendor"), None)
    cat = next((c for c in ctx["columns"] if c["name"] == "category"), None)
    parts = [f"**O seu ficheiro tem {rows} linhas** de dados."]
    if amt:
        parts.append(f"Valor total: **{amt.get('sum', 0):,.2f}** · média "
                     f"{amt.get('mean', 0):,.2f} · máximo {amt.get('max', 0):,.2f}.")
    if ts and ts.get("min"):
        parts.append(f"Período: **{ts['min']} → {ts['max']}**.")
    if ven and ven.get("top_values"):
        top = ", ".join(f"{k} ({n})" for k, n in ven["top_values"][:3])
        parts.append(f"Maiores intervenientes: {top}.")
    if cat and cat.get("unique"):
        parts.append(f"{cat['unique']} categorias distintas.")
    nulls = [c for c in ctx["columns"] if c["null_pct"] > 20]
    if nulls:
        names = ", ".join(c["name"] for c in nulls[:4])
        parts.append(f"⚠ Atenção: colunas com muitos vazios — {names}.")
    parts.append("\nPosso **transformar os dados** (tops, filtros, resumos), "
                 "**sugerir fórmulas** para automatizar o ficheiro ou gerar um "
                 "**workbook apresentável**. O que prefere?")
    return "\n".join(parts)


def rule_plan(question: str, ctx: dict, headers: dict = None) -> dict:
    """
    Plano determinístico: deteta a intenção e produz operations + resposta +
    subconjunto de fórmulas + followups. Nunca falha (fallback → explain).
    """
    q = norm_q(question)
    intents = detect_intents(question)
    primary = intents[0]
    ops: list = []
    charts: list = []
    formulas: list = []
    followups: list = []

    has_amount, has_date = _has_col(ctx, "amount"), _has_col(ctx, "timestamp")
    n = _extract_number_near(q, [r"top\s*(\d+)", r"(\d+)\s*(?:maiores|melhores|primeiros)"]) or 10

    if primary == "top_n":
        gb = _groupby_from_question(q, ctx, default=None)
        if gb:
            metric = "amount" if has_amount else None
            agg_word = {"vendor": "fornecedores", "category": "categorias",
                        "user_id": "utilizadores", "status": "estados",
                        "currency": "moedas"}.get(gb, gb)
            ops.append({"op": "aggregate", "group_by": gb, "metric": metric,
                        "agg": "sum" if metric else "count", "top": int(n)})
            answer = (f"Aqui está o **top {int(n)} {agg_word}** "
                      + (f"por valor total" if metric else "por nº de registos")
                      + ", já ordenado. No Excel, reproduza isto com "
                      "**ÚNICO + SOMASES** (veja as fórmulas abaixo) — a tabela "
                      "de resumo atualiza-se sozinha quando os dados mudam.")
            followups += [f"Sugere fórmulas para manter este top {int(n)} sempre atualizado?",
                          "Gera o ficheiro com esta tabela de resumo"]
        else:
            ops.append({"op": "sort", "by": "amount", "ascending": False})
            ops.append({"op": "top_n", "by": "amount", "n": int(n)})
            answer = (f"Estão aí as **{int(n)} linhas de maior valor**, ordenadas "
                      "de forma decrescente. Para isto ficar automático no Excel, "
                      "converta os dados numa Tabela (Ctrl+T) e use o pack de "
                      "fórmulas de ranking abaixo.")
            followups += ["Sugere fórmulas para o ranking atualizar sozinho",
                          "Marca valores acima de 10000"]
        formulas += ["tabela", "kpi_total", "rank_valor", "pct_total"]

    elif primary == "aggregate" or "aggregate" in intents:
        gb = _groupby_from_question(q, ctx, default="category")
        metric = "amount" if has_amount else None
        agg = "mean" if re.search(r"\b(media|average|avg)\b", q) else \
              "count" if re.search(r"\b(conta|quantidade|count|nr de|nº de)\b", q) else "sum"
        if gb:
            ops.append({"op": "aggregate", "group_by": gb, "metric": metric,
                        "agg": agg, "top": 15})
            label = {"sum": "somando", "mean": "com a média", "count": "a contar"}.get(agg, "")
            answer = (f"Resumo **por {gb}** ({label}"
                      + (f" o valor" if metric else " os registos")
                      + "), do maior para o menor. Para o Excel fazer isto "
                      "sozinho: folha nova com **ÚNICO()** na coluna "
                      f"{gb} e **SOMASES()** ao lado — zero manutenção.")
            formulas += ["resumo_categoria", "total_categoria", "pct_categoria",
                         "top10_fornecedores", "kpi_total"]
            followups += ["Transforma isto num gráfico de pizza",
                          "Aplica e gera o ficheiro com o resumo"]
        else:
            answer = ("Não encontrei uma coluna de agrupamento adequada "
                      "(categoria, fornecedor, estado…). Diga, por exemplo: "
                      "*\"agrupa por categoria e soma o valor\"*.")

    elif primary == "filter":
        fops = _parse_filter_ops(question, ctx)
        if fops:
            ops += fops
            desc = "; ".join(
                f"{o['column']} " + ("contém " + o["contains"] if "contains" in o
                 else f"{'>' if 'gt' in o else '≥' if 'gte' in o else '<' if 'lt' in o else '≤'} {o.get('gt') or o.get('gte') or o.get('lt') or o.get('lte')}"
                 if ("gt" in o or "gte" in o or "lt" in o or "lte" in o)
                 else f"ano {o['year']}") for o in fops)
            answer = (f"Filtrei: **{desc}**. Estas condições no Excel ficam "
                      "melhores com **FILTRO()** (365) ou Tabela + segmentações "
                      "de dados (Slicers) — sugiro fórmulas abaixo.")
            formulas += ["tabela", "kpi_total", "alerta_alto"]
            followups += ["Sugere fórmulas de filtro automático (FILTRO/SE)",
                          "Gera o ficheiro só com estas linhas"]
        else:
            answer = ("Diga-me a condição — por exemplo: *\"filtra valores "
                      "maior que 10000\"*, *\"só fornecedor Sonae\"*, "
                      "*\"apenas estado pendente\"* ou *\"ano 2025\"*.")

    elif primary == "duplicates":
        if _has_col(ctx, "transaction_id"):
            ops.append({"op": "flag_duplicates", "subset": ["transaction_id"]})
        answer = ("Analisei **duplicados** (por ID e por semelhança de "
                  "fornecedor+valor). No seu ficheiro, as fórmulas abaixo "
                  "marcam duplicados em tempo real — assim que alguém colar "
                  "uma linha repetida, ela acende sozinha.")
        formulas += ["dupe_id", "dupe_vendor", "dupes_cf", "tabela"]
        followups += ["Remove os duplicados e gera o ficheiro limpo",
                      "Quais os fornecedores mais repetidos?"]

    elif primary == "add_column":
        kinds = []
        for kw, kind in [("mes", "month"), ("trimestre", "quarter"),
                         ("dia da semana", "weekday"), ("ano", "year"),
                         ("acumulado", "running_total"), ("rank", "rank"),
                         ("classific", "rank"), ("%", "pct_of_total"),
                         ("percent", "pct_of_total"), ("faixa", "bucket"),
                         ("aging", "aging_days"), ("idade", "aging_days")]:
            if kw in q and kind not in kinds:
                kinds.append(kind)
        if not kinds and has_amount:
            kinds = ["pct_of_total"]
        built = []
        for k in kinds:
            if k in ("month", "quarter", "weekday", "year") and not has_date:
                continue
            if k in ("pct_of_total", "running_total", "rank", "bucket", "aging_days") and not has_amount:
                continue
            name = {"month": "Mês", "quarter": "Trimestre", "weekday": "Dia da Semana",
                    "year": "Ano", "pct_of_total": "% do Total",
                    "running_total": "Acumulado", "rank": "Rank",
                    "bucket": "Faixa de Valor", "aging_days": "Idade (dias)"}[k]
            ops.append({"op": "add_column", "kind": k, "name": name})
            built.append(name)
        if built:
            answer = (f"Adicionei as colunas: **{', '.join(built)}**. No seu "
                      "ficheiro, reproduza-as com as fórmulas abaixo — "
                      "calculam-se sozinhas a partir dos dados originais, "
                      "nunca à mão.")
            formulas += ["col_mes", "acumulado", "pct_total", "rank_valor",
                         "aging", "alerta_alto", "tabela"]
            followups += ["Agora agrupa pelo Mês e soma o valor",
                          "Gera o ficheiro com estas colunas novas"]
        else:
            answer = ("Não reconheci a coluna pedida. Exemplos: *\"adiciona "
                      "coluna do mês\"*, *\"coluna acumulado\"*, *\"coluna % do "
                      "total\"*, *\"faixas de valor\"* ou *\"dias desde a data\"*.")

    elif primary == "chart":
        if has_amount:
            gb = _groupby_from_question(q, ctx, default=None)
            if gb:
                ops.append({"op": "aggregate", "group_by": gb, "metric": "amount",
                            "agg": "sum", "top": 10})
        charts = CHART_SUGGESTIONS[:3]
        answer = ("Para apresentar bem estes dados sugiro: **pizza** por "
                  "categoria (distribuição), **barras** top 10 fornecedores "
                  "(concentração) e **linha** mensal (tendência). As fórmulas "
                  "abaixo constroem as fontes dos gráficos de forma dinâmica — "
                  "o gráfico nunca fica desatualizado.")
        formulas += ["resumo_categoria", "total_categoria", "col_mes",
                     "top10_fornecedores", "kpi_total"]
        followups += ["Gera o workbook com gráficos prontos",
                      "Sugere um layout de dashboard com KPIs"]

    elif primary == "dashboard":
        if has_amount and _has_col(ctx, "category"):
            ops.append({"op": "aggregate", "group_by": "category", "metric": "amount",
                        "agg": "sum", "top": 8})
        charts = CHART_SUGGESTIONS
        answer = ("Layout de **dashboard** que recomendo para a folha Sumário:\n"
                  "1. Linha 1 — KPIs vivos: Total, Média, Máximo, Nº registos, "
                  "valor pendente (todas com SOMA/SOMASES/CONT.SES — zero "
                  "valores colados à mão).\n"
                  "2. Linha 2 — gráfico de pizza por categoria + barras top 10.\n"
                  "3. Linha 3 — evolução mensal + contagem por estado.\n"
                  "4. Tudo alimentado pela Tabela 'tblDados' com as fórmulas "
                  "abaixo — atualiza-se 100% sozinho.")
        formulas += ["kpi_total", "kpi_media", "kpi_max", "kpi_estado",
                     "kpi_contagem_estado", "resumo_categoria", "col_mes",
                     "total_categoria", "top10_fornecedores", "tabela"]
        followups += ["Gera o workbook com este dashboard montado",
                      "Adiciona KPI de valores acima de 10000"]

    elif primary == "formula":
        formulas = None  # pack completo
        answer = ("Com base nas colunas do seu ficheiro, preparei um **pack de "
                  "fórmulas** (abaixo) para o tornar automático: KPIs vivos, "
                  "resumos dinâmicos, deteção de duplicados e colunas "
                  "calculadas — tudo com referências estruturadas à Tabela "
                  "'tblDados', de modo a **nada quebrar** quando adicionar "
                  "linhas. Cada cartão traz a versão **PT-PT** (SOMASES, "
                  "ponto-e-vírgula) e **EN** (SUMIFS, vírgula) — use a que "
                  "corresponde ao idioma do seu Excel.")
        followups += ["Explica passo a passo a fórmula do top 10",
                      "Gera o ficheiro com a folha de fórmulas incluída",
                      "Monta um dashboard com estes KPIs"]

    else:  # explain
        answer = _answer_overview(ctx, headers)
        formulas = ["tabela", "kpi_total", "kpi_media", "resumo_categoria"]
        followups += ["Sugere fórmulas para automatizar o ficheiro",
                      "Mostra o top 10 por valor",
                      "Como apresentar isto num dashboard?"]

    return {
        "intent": primary, "answer": answer, "operations": ops,
        "formula_ids": formulas, "charts": charts, "followups": followups,
        "model_used": "rule-engine",
    }


# ---------------------------------------------------------------------------
# 4. EXECUTOR DE OPERAÇÕES (whitelist, tolerante a falhas)
# ---------------------------------------------------------------------------

def _resolve_col(df: pd.DataFrame, name: str):
    """Encontra a coluna real (canônica, original ou case-insensitive)."""
    if not name:
        return None
    s = str(name)
    if s in df.columns:
        return s
    low = {str(c).lower(): c for c in df.columns}
    return low.get(s.lower())


def apply_operations(df: pd.DataFrame, operations: list) -> tuple:
    """Executa a lista de operações validadas. Devolve (novo_df, log)."""
    out = df.copy()
    log = []
    for op in (operations or [])[:6]:
        kind = (op.get("op") or "").lower()
        try:
            if kind == "sort":
                by = _resolve_col(out, op.get("by"))
                if by is None:
                    continue
                asc = bool(op.get("ascending", True))
                out = out.sort_values(by=by, ascending=asc, na_position="last")
                log.append({"op": "sort",
                            "detail": f"ordenado por {by} ({'asc' if asc else 'desc'})"})

            elif kind == "filter":
                col = _resolve_col(out, op.get("column"))
                if col is None or not len(out):
                    continue
                s = out[col]
                mask = pd.Series(True, index=out.index)
                if pd.api.types.is_numeric_dtype(s):
                    if "gt" in op: mask &= s > float(op["gt"])
                    if "gte" in op: mask &= s >= float(op["gte"])
                    if "lt" in op: mask &= s < float(op["lt"])
                    if "lte" in op: mask &= s <= float(op["lte"])
                    if "equals" in op: mask &= s == op["equals"]
                else:
                    if "equals" in op:
                        mask &= s.astype(str).str.lower() == str(op["equals"]).lower()
                    if "contains" in op:
                        mask &= s.astype(str).str.contains(
                            re.escape(str(op["contains"])), case=False, na=False)
                if "year" in op:
                    dt = pd.to_datetime(out.get("timestamp", s), errors="coerce")
                    mask &= dt.dt.year == int(op["year"])
                if "date_from" in op:
                    dt = pd.to_datetime(out.get("timestamp", s), errors="coerce")
                    mask &= dt >= pd.Timestamp(op["date_from"])
                if "date_to" in op:
                    dt = pd.to_datetime(out.get("timestamp", s), errors="coerce")
                    mask &= dt <= pd.Timestamp(op["date_to"])
                out = out[mask]
                log.append({"op": "filter", "detail": f"{col}: {len(out)} linhas após filtro"})

            elif kind == "top_n":
                by = _resolve_col(out, op.get("by"))
                n = max(1, min(int(op.get("n") or 10), 200))
                if by is None or not len(out):
                    continue
                out = out.nlargest(n, by) if pd.api.types.is_numeric_dtype(out[by]) \
                    else out.head(n)
                log.append({"op": "top_n", "detail": f"top {n} por {by}"})

            elif kind == "aggregate":
                gb = _resolve_col(out, op.get("group_by"))
                if gb is None or not len(out):
                    continue
                agg = str(op.get("agg") or "sum").lower()
                metric = _resolve_col(out, op.get("metric")) if op.get("metric") else None
                if metric is not None and pd.api.types.is_numeric_dtype(out[metric]) and agg != "count":
                    fn = {"sum": "sum", "mean": "mean", "min": "min",
                          "max": "max"}.get(agg, "sum")
                    res = out.groupby(gb)[metric].agg(fn).reset_index()
                    res.columns = [gb, {"sum": "Total", "mean": "Média",
                                        "min": "Mínimo", "max": "Máximo"}[fn]]
                else:
                    res = out.groupby(gb).size().reset_index(name="Contagem")
                res = res.sort_values(res.columns[1], ascending=False)
                top = max(1, min(int(op.get("top") or 15), 50))
                out = res.head(top)
                log.append({"op": "aggregate",
                            "detail": f"agregado por {gb} → {len(out)} grupos"})

            elif kind == "pivot":
                idx = _resolve_col(out, op.get("index"))
                vals = _resolve_col(out, op.get("values"))
                cols = _resolve_col(out, op.get("columns")) if op.get("columns") else None
                if idx is None or vals is None or not len(out):
                    continue
                pt = pd.pivot_table(out, index=idx, columns=cols, values=vals,
                                    aggfunc="sum", fill_value=0).reset_index()
                pt.columns = [str(c) for c in pt.columns]
                if pt.shape[1] > 30:
                    pt = pt.iloc[:, :30]
                out = pt.head(60)
                log.append({"op": "pivot", "detail": f"tabela cruzada {idx}"
                            + (f" × {cols}" if cols else "")})

            elif kind == "add_column":
                new = _add_derived_column(out, op.get("kind"), op.get("name"))
                if new:
                    log.append({"op": "add_column",
                                "detail": f"coluna '{new}' criada ({op.get('kind')})"})

            elif kind in ("remove_duplicates", "flag_duplicates"):
                subset = [_resolve_col(out, c) for c in (op.get("subset") or [])]
                subset = [c for c in subset if c]
                if kind == "remove_duplicates":
                    before = len(out)
                    out = out.drop_duplicates(subset=subset or None, keep="first")
                    log.append({"op": "remove_duplicates",
                                "detail": f"{before - len(out)} duplicados removidos"})
                else:
                    key = subset[0] if subset else None
                    if key is None or not len(out):
                        continue
                    name = next((n for n in ("Duplicado", "Duplicado?")
                                 if n not in out.columns), "Duplicado")
                    out[name] = np.where(out.duplicated(subset=[key], keep=False),
                                         "DUPLICADO", "OK")
                    log.append({"op": "flag_duplicates",
                                "detail": f"coluna '{name}' marca repetições de {key}"})
        except Exception as e:  # uma operação mal-formada não mata o resto
            logger.warning("copilot op '%s' falhou: %s", kind, e)
            log.append({"op": kind, "detail": f"ignorada ({e})"})
    return out.reset_index(drop=True), log


def _add_derived_column(df: pd.DataFrame, kind: str, name: str):
    """Cria a coluna calculada pedida. Devolve o nome criado ou None."""
    kind = (kind or "").lower()
    has_dt = "timestamp" in df.columns
    has_amt = "amount" in df.columns and pd.api.types.is_numeric_dtype(df["amount"])
    name = (name or "").strip() or {"month": "Mês", "quarter": "Trimestre",
        "weekday": "Dia da Semana", "year": "Ano", "pct_of_total": "% do Total",
        "running_total": "Acumulado", "rank": "Rank", "bucket": "Faixa de Valor",
        "aging_days": "Idade (dias)"}.get(kind, "Calculado")
    if name in df.columns:
        name = f"{name} (2)"
    if kind in ("month", "quarter", "weekday", "year", "aging_days") and has_dt:
        dt = pd.to_datetime(df["timestamp"], errors="coerce")
        if kind == "month":
            df[name] = dt.dt.to_period("M").astype(str)
        elif kind == "quarter":
            df[name] = dt.dt.year.astype(str) + "-Q" + dt.dt.quarter.astype(str)
        elif kind == "weekday":
            df[name] = dt.dt.dayofweek.map(lambda i: WEEKDAY_PT[i] if pd.notna(i) else None)
        elif kind == "year":
            df[name] = dt.dt.year
        elif kind == "aging_days":
            df[name] = (pd.Timestamp.now().normalize() - dt.dt.normalize()).dt.days
        return name
    if kind == "pct_of_total" and has_amt:
        total = df["amount"].sum()
        df[name] = df["amount"] / total if total else 0.0
        return name
    if kind == "running_total" and has_amt:
        df[name] = df["amount"].cumsum()
        return name
    if kind == "rank" and has_amt:
        df[name] = df["amount"].rank(ascending=False, method="min").astype("Int64")
        return name
    if kind == "bucket" and has_amt:
        df[name] = pd.cut(df["amount"], [-np.inf, 1000, 5000, 10000, np.inf],
                          labels=["≤1k", "1k–5k", "5k–10k", ">10k"])
        return name
    return None


def frame_preview(df: pd.DataFrame, n: int = 15) -> dict:
    """Pré-visualização JSON-safe do resultado (para o chat)."""
    cols = [str(c) for c in df.columns]
    head = df.head(n)
    rows = []
    for _, r in head.iterrows():
        rows.append([_json_safe(v) for v in r.tolist()])
    numeric = {}
    for c in df.columns:
        if pd.api.types.is_numeric_dtype(df[c]) and len(df):
            numeric[str(c)] = {"sum": float(df[c].sum()), "mean": float(df[c].mean())}
    return {"columns": cols, "rows": rows, "shown": len(rows),
            "total_rows": int(len(df)), "numeric": numeric}


# ---------------------------------------------------------------------------
# 5. LLM (Ollama/DeepSeek) — plano JSON com validação estrita
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """Você é o Copiloto Excel de uma plataforma de auditoria. O utilizador carregou um ficheiro e faz um pedido em português ou inglês. Responda SEMPRE em português de Portugal.

Responda APENAS com um objeto JSON válido (sem texto antes ou depois), neste formato:
{"intent": "top_n|aggregate|filter|add_column|chart|dashboard|duplicates|formula|explain",
 "answer": "resposta direta em markdown simples (máx. 100 palavras), citando números concretos dos dados",
 "operations": [],
 "followups": ["sugestão curta de próxima pergunta", "..."]}

Operações permitidas (use apenas estas; máximo 4):
{"op":"sort","by":"<coluna>","ascending":true}
{"op":"filter","column":"<coluna>","gt":1000}        (chaves numéricas possíveis: gt, gte, lt, lte, equals, contains, year)
{"op":"top_n","by":"<coluna>","n":10}
{"op":"aggregate","group_by":"<coluna>","metric":"<coluna ou null>","agg":"sum|mean|count|min|max","top":15}
{"op":"add_column","kind":"month|quarter|weekday|year|pct_of_total|running_total|rank|bucket|aging_days","name":"<nome>"}
{"op":"remove_duplicates","subset":["<coluna>"]}

Regras: use apenas colunas que existem no esquema; não invente valores; se o pedido for por sugestões de fórmulas/automação, deixe operations vazio."""


def _strip_think(text: str) -> str:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S | re.I)
    text = re.sub(r"```(?:json)?", "", text, flags=re.I)
    return text.strip()


def call_ollama_plan(question: str, ctx: dict, sheet_name: str,
                     history: list = None) -> dict:
    """Pede o plano JSON ao Ollama. Devolve dict validado ou None."""
    try:
        import requests
        context = build_llm_context(ctx, sheet_name, question)
        hist = ""
        for m in (history or [])[-4:]:
            role = "UTILIZADOR" if m.get("role") == "user" else "ASSISTENTE"
            hist += f"\n{role}: {str(m.get('content', ''))[:300]}"
        prompt = (SYSTEM_PROMPT + "\n\nESQUEMA DOS DADOS:\n" + context
                  + ("\nCONVERSA ANTERIOR:" + hist if hist else "")
                  + "\n\nJSON:")
        resp = requests.post(
            f"{OLLAMA_URL.rstrip('/')}/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False,
                  "options": {"temperature": 0.1, "num_predict": 700}},
            timeout=OLLAMA_TIMEOUT)
        if resp.status_code != 200:
            logger.info("copilot LLM http %s", resp.status_code)
            return None
        raw = _strip_think(resp.json().get("response", ""))
        start, end = raw.find("{"), raw.rfind("}")
        if start < 0 or end <= start:
            return None
        plan = json.loads(raw[start:end + 1])
        if not isinstance(plan, dict):
            return None
        answer = str(plan.get("answer") or "").strip()
        return {
            "intent": str(plan.get("intent") or "explain")[:40],
            "answer": answer[:2500],
            "operations": plan.get("operations") if isinstance(plan.get("operations"), list) else [],
            "followups": [str(f)[:120] for f in plan.get("followups", [])[:4]]
                         if isinstance(plan.get("followups"), list) else [],
            "formulas": [str(f)[:500] for f in plan.get("formulas", [])[:4]]
                        if isinstance(plan.get("formulas"), list) else [],
        }
    except Exception as e:
        logger.info("copilot LLM indisponível: %s", e)
        return None


def _validate_ops(ops: list, df: pd.DataFrame) -> list:
    """Whitelist + coerção das operações (do LLM ou do cliente)."""
    clean = []
    for op in (ops or [])[:6]:
        if not isinstance(op, dict):
            continue
        kind = str(op.get("op") or "").lower()
        if kind not in ("sort", "filter", "top_n", "aggregate", "pivot",
                        "add_column", "remove_duplicates", "flag_duplicates"):
            continue
        o = {"op": kind}
        for k in ("by", "column", "group_by", "metric", "index", "values",
                  "columns", "kind", "name"):
            if op.get(k) is not None:
                o[k] = str(op[k])[:80]
        for k in ("gt", "gte", "lt", "lte", "n", "top", "year"):
            if op.get(k) is not None:
                try:
                    o[k] = float(op[k]) if k in ("gt", "gte", "lt", "lte") else int(op[k])
                except (TypeError, ValueError):
                    pass
        for k in ("contains", "equals"):
            if op.get(k) is not None:
                o[k] = str(op[k])[:120]
        if "ascending" in op:
            o["ascending"] = bool(op["ascending"])
        if isinstance(op.get("subset"), list):
            o["subset"] = [str(c)[:80] for c in op["subset"][:4]]
        if kind == "aggregate" and "group_by" not in o:
            continue
        if kind == "add_column" and not o.get("kind"):
            continue
        clean.append(o)
    return clean


def _sanitize_llm_formula(text: str):
    t = str(text or "").strip().replace("\n", " ")
    if not t.startswith("=") or len(t) > 500 or any(ch in t for ch in ("{", "}", "<script")):
        return None
    return t


# ---------------------------------------------------------------------------
# 6. ORQUESTRADOR DO CHAT
# ---------------------------------------------------------------------------

def _chat_core(df: pd.DataFrame, sheet_name: str, headers: dict,
               question: str, history: list = None) -> dict:
    """Núcleo: contexto → plano (LLM com fallback) → execução → resposta."""
    df = df.copy()
    ctx = describe_frame(df)
    rule = rule_plan(question, ctx, headers)
    llm = call_ollama_plan(question, ctx, sheet_name, history)

    model_used = "rule-engine"
    answer = rule["answer"]
    followups = rule["followups"]
    intent = rule["intent"]
    ops = rule["operations"]

    if llm:
        model_used = f"Ollama/{OLLAMA_MODEL}"
        validated = _validate_ops(llm["operations"], df)
        if llm["answer"] and len(llm["answer"]) >= 40:
            answer = llm["answer"]
            intent = llm["intent"]
        if validated:
            ops = validated
        if llm["followups"]:
            followups = llm["followups"]
    ops = _validate_ops(ops, df)

    df2, applied = apply_operations(df, ops)

    # Pack de fórmulas: determinístico (semântica das colunas) + extras da IA
    full_pack = suggest_formulas(df, headers)
    ids = rule["formula_ids"]
    formulas = ([f for f in full_pack if f["id"] in ids] if ids else full_pack)
    if llm:
        for i, f in enumerate(llm["formulas"]):
            safe = _sanitize_llm_formula(f)
            if safe:
                formulas.append({
                    "id": f"ia_{i}", "title": f"Sugestão IA #{i + 1}",
                    "category": "Sugestão IA", "formula_pt": safe,
                    "formula_en": safe,
                    "explanation": "Fórmula gerada pela IA a partir do seu "
                                   "pedido — confirme intervalos antes de aplicar.",
                    "where": "Conforme o seu pedido", "needs_365": False,
                    "column": None,
                })

    charts = rule["charts"]
    if not charts and intent in ("chart", "dashboard"):
        charts = CHART_SUGGESTIONS[:3]

    return {
        "intent": intent,
        "model_used": model_used,
        "answer": answer,
        "sheet": sheet_name,
        "data_context": ctx,
        "operations_applied": applied,
        "plan": ops,
        "result": frame_preview(df2),
        "formulas": formulas,
        "charts": charts,
        "followups": followups[:4] or ["Gera o ficheiro com estas alterações",
                                       "Sugere mais fórmulas de automação"],
    }


def chat(file_content: bytes, filename: str, question: str,
         sheet: str = None, mapping_json: str = None,
         history: list = None) -> dict:
    """Upload + pergunta → resposta completa do Copiloto."""
    frames = es.read_uploaded_file(file_content, filename)
    sheet_name = str(sheet) if sheet else es.pick_best_sheet(frames)
    if sheet_name not in frames:
        sheet_name = es.pick_best_sheet(frames)
    df_raw = frames[sheet_name]

    mapping = None
    if mapping_json:
        try:
            mapping = json.loads(mapping_json)
        except json.JSONDecodeError:
            mapping = None
    if not mapping:
        mapping = es.map_columns([str(c) for c in df_raw.columns])

    rows, skipped = es.standardize_frame(df_raw, mapping)
    headers = {}
    for canon, orig in (mapping or {}).items():
        if canon in CANON_LABELS_PT and orig:
            headers[canon] = str(orig)

    if not rows:
        return {
            "intent": "explain", "model_used": "rule-engine",
            "answer": "Não consegui ler linhas válidas desta folha com o "
                      "mapeamento automático. Verifique se a folha escolhida "
                      "contém pelo menos **Valor** e **Data**, ou ajuste o "
                      "mapeamento na aba *Importar* e tente de novo.",
            "sheet": sheet_name,
            "data_context": {"rows": 0, "columns": []},
            "operations_applied": [], "plan": [],
            "result": {"columns": [], "rows": [], "shown": 0, "total_rows": 0,
                       "numeric": {}},
            "formulas": suggest_formulas(pd.DataFrame(columns=list(CANON_LABELS_PT)),
                                         headers),
            "charts": [], "followups": [],
        }
    return _chat_core(pd.DataFrame(rows), sheet_name, headers, question, history)


def apply_and_build(file_content: bytes, filename: str, plan: list,
                    sheet: str = None, mapping_json: str = None,
                    title: str = None) -> tuple:
    """
    Reproduz o plano confirmado e devolve (bytes_xlsx, nome_ficheiro).
    O workbook inclui a Tabela 'tblDados', KPIs vivos e a folha de Fórmulas.
    """
    frames = es.read_uploaded_file(file_content, filename)
    sheet_name = str(sheet) if sheet else es.pick_best_sheet(frames)
    if sheet_name not in frames:
        sheet_name = es.pick_best_sheet(frames)
    df_raw = frames[sheet_name]

    mapping = None
    if mapping_json:
        try:
            mapping = json.loads(mapping_json)
        except json.JSONDecodeError:
            mapping = None
    if not mapping:
        mapping = es.map_columns([str(c) for c in df_raw.columns])

    rows, _ = es.standardize_frame(df_raw, mapping)
    if not rows:
        raise ValueError("Nenhuma linha válida para aplicar o plano.")
    df = pd.DataFrame(rows)
    headers = {}
    for canon, orig in (mapping or {}).items():
        if canon in CANON_LABELS_PT and orig:
            headers[canon] = str(orig)

    ops = _validate_ops(plan, df)
    df2, _ = apply_operations(df, ops)
    formulas = suggest_formulas(df, headers)
    safe_title = title or f"Workbook Copiloto — {sheet_name}"
    wb = build_copilot_workbook(safe_title, df2, formulas, headers)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    fname = f"Copiloto_Excel_{stamp}.xlsx"
    return wb, fname


# ---------------------------------------------------------------------------
# 7. WORKBOOK DO COPILOTO — Tabela 'tblDados' + KPIs vivos + folha Fórmulas
# ---------------------------------------------------------------------------

def _sanitize_label(label: str) -> str:
    t = re.sub(r"[\[\]'\"#]", " ", str(label or "")).strip()
    return t or "Coluna"


def _output_headers(df: pd.DataFrame, headers: dict) -> list:
    """Rótulos finais das colunas: original > canônico PT; únicos e válidos."""
    seen, out = {}, []
    for c in df.columns:
        canon = str(c)
        label = _sanitize_label(headers.get(canon, CANON_LABELS_PT.get(canon, canon)))
        if label in seen:
            seen[label] += 1
            label = f"{label} {seen[label]}"
        else:
            seen[label] = 1
        out.append(label)
    return out


def _chart_specs_for(df: pd.DataFrame) -> list:
    """Fontes de gráfico a partir do resultado final."""
    if df.empty:
        return []
    if len(df.columns) == 2 and len(df) > 0 and \
            pd.api.types.is_numeric_dtype(df[df.columns[1]]):
        top = df.head(12).copy()
        top.columns = ["Grupo", "Total"]
        return [{"type": "bar", "title": f"{df.columns[0]} — Top {len(top)}",
                 "df": top}]
    specs = es.aggregate_for_charts(df)
    return specs[:2]


def build_copilot_workbook(title: str, df: pd.DataFrame, formulas: list,
                           headers: dict = None) -> bytes:
    """
    Workbook final do Copiloto:
      • Sumário   — KPIs como FÓRMULAS VIVAS (SOMA/CONT.SES sobre tblDados)
      • Dados     — resultado transformado numa Tabela Excel 'tblDados'
      • Fórmulas  — pack recomendado (PT-PT + EN) com instruções
      • gráficos  — alimentados pelos dados atuais
    As fórmulas são gravadas no formato EN (padrão do ficheiro XLSX); o Excel
    apresenta-as localizadas. Os rótulos das colunas usam os cabeçalhos
    originais do utilizador para as referências estruturadas funcionarem.
    """
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter
    from openpyxl.chart import BarChart, LineChart, PieChart, Reference
    from openpyxl.formatting.rule import DataBarRule
    from openpyxl.worksheet.table import Table, TableStyleInfo

    headers = headers or {}
    wb = Workbook()

    # ---------- Folha Sumário ----------
    ws_sum = wb.active
    ws_sum.title = "Sumário"
    ws_sum["A1"] = title or "Workbook Copiloto"
    ws_sum["A1"].font = Font(bold=True, size=16, color="1D4ED8")
    ws_sum["A2"] = (f"Gerado pelo Copiloto Excel — {datetime.now().strftime('%Y-%m-%d %H:%M')} · "
                    "KPIs vivos: recalculam-se sozinhos quando editar tblDados")
    ws_sum["A2"].font = Font(size=10, italic=True, color="6B7280")

    labels = _output_headers(df, headers) if len(df) else []
    label_by_canon = {str(c): lab for c, lab in zip(df.columns, labels)}

    num_col = next((str(c) for c in df.columns
                    if pd.api.types.is_numeric_dtype(df[c]) and len(df)), None)
    status_col = next((str(c) for c in df.columns if c in ("status",)), None)
    top_status = ""
    if status_col and len(df):
        vc = df[status_col].dropna().astype(str).value_counts()
        top_status = str(vc.index[0]) if len(vc) else ""

    kpis = []
    if num_col:
        L = label_by_canon[num_col]
        kpis += [("Valor Total (SOMA)", f"=SUM({TABLE_NAME}[{L}])"),
                 ("Média", f"=AVERAGE({TABLE_NAME}[{L}])"),
                 ("Máximo", f"=MAX({TABLE_NAME}[{L}])")]
    first_label = labels[0] if labels else "A"
    kpis.append(("Nº de Registos", f"=COUNTA({TABLE_NAME}[{first_label}])"))
    if top_status and num_col:
        kpis += [(f"Registos '{top_status[:20]}'",
                  f'=COUNTIFS({TABLE_NAME}[{label_by_canon[status_col]}],"{top_status}")'),
                 (f"Valor '{top_status[:20]}'",
                  f'=SUMIFS({TABLE_NAME}[{label_by_canon[num_col]}],'
                  f'{TABLE_NAME}[{label_by_canon[status_col]}],"{top_status}")')]

    row = 4
    ws_sum.cell(row=row, column=1, value="Indicador").font = Font(bold=True)
    ws_sum.cell(row=row, column=2, value="Valor (fórmula viva)").font = Font(bold=True)
    row += 1
    for label, formula in kpis:
        ws_sum.cell(row=row, column=1, value=label)
        c = ws_sum.cell(row=row, column=2, value=formula)
        c.number_format = "#,##0.00"
        c.font = Font(bold=True, color="1D4ED8")
        row += 1
    row += 1
    ws_sum.cell(row=row, column=1,
                value="Edite ou acrescente linhas em 'Dados' — estes KPIs e os gráficos atualizam-se automaticamente.").font = \
        Font(size=9, italic=True, color="6B7280")

    # ---------- Folha Dados (Tabela Excel) ----------
    ws_data = wb.create_sheet("Dados")
    for j, lab in enumerate(labels, start=1):
        ws_data.cell(row=1, column=j, value=lab)
    for i, (_, r) in enumerate(df.iterrows(), start=2):
        for j, v in enumerate(r.tolist(), start=1):
            val = v
            if pd.isna(val):
                val = None
            elif isinstance(val, pd.Timestamp):
                val = val.to_pydatetime()
            elif isinstance(val, (np.integer,)):
                val = int(val)
            elif isinstance(val, (np.floating, float)):
                f = float(val)
                val = None if (np.isnan(f) or np.isinf(f)) else f
            elif isinstance(val, (np.bool_, bool)):
                val = bool(val)
            elif not isinstance(val, (int, float, str, type(None))):
                val = str(val)
            ws_data.cell(row=i, column=j, value=val)
    es._style_header(ws_data, len(labels))

    n_rows_out = max(len(df), 1)
    ref = f"A1:{get_column_letter(max(len(labels), 1))}{n_rows_out + 1}"
    if len(labels) and len(df):
        table = Table(displayName=TABLE_NAME, ref=ref)
        table.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2",
                                              showRowStripes=True)
        ws_data.add_table(table)
        ws_data.freeze_panes = "A2"
        es._autofit_columns(ws_data)
        if num_col:
            ci = get_column_letter(list(df.columns).index(num_col) + 1)
            ws_data.conditional_formatting.add(
                f"{ci}2:{ci}{len(df) + 1}",
                DataBarRule(start_type="min", end_type="max", color="2563EB"))

    # ---------- Gráficos no Sumário ----------
    anchor_row = row + 2
    for spec in _chart_specs_for(df):
        cdf = spec.get("df")
        if cdf is None or cdf.empty:
            continue
        ws_sum.cell(row=anchor_row - 1, column=1,
                    value=spec.get("title", "")).font = Font(bold=True)
        base_col = 5
        ws_sum.cell(row=anchor_row - 1, column=base_col, value=str(cdf.columns[0]))
        ws_sum.cell(row=anchor_row - 1, column=base_col + 1, value=str(cdf.columns[1]))
        for r, (_, rv) in enumerate(cdf.head(12).iterrows(), start=anchor_row):
            ws_sum.cell(row=r, column=base_col, value=str(rv.iloc[0])[:40])
            v = rv.iloc[1]
            ws_sum.cell(row=r, column=base_col + 1,
                        value=float(v) if isinstance(v, (int, float, np.number))
                        and pd.notna(v) else None)
        n = min(len(cdf), 12)
        xref = Reference(ws_sum, min_col=base_col, min_row=anchor_row,
                         max_row=anchor_row + n - 1)
        yref = Reference(ws_sum, min_col=base_col + 1, min_row=anchor_row - 1,
                         max_row=anchor_row + n - 1)
        kind = spec.get("type", "bar")
        if kind == "pie":
            ch = PieChart(); ch.add_data(yref, titles_from_data=True); ch.set_categories(xref)
        elif kind == "line":
            ch = LineChart(); ch.add_data(yref, titles_from_data=True); ch.set_categories(xref)
        else:
            ch = BarChart(); ch.type = "col"
            ch.add_data(yref, titles_from_data=True); ch.set_categories(xref)
        ch.title = spec.get("title", "Gráfico")
        ch.height, ch.width = 9, 15
        ws_sum.add_chart(ch, f"A{anchor_row}")
        anchor_row += 20

    # ---------- Folha Fórmulas ----------
    ws_f = wb.create_sheet("Fórmulas")
    ws_f["A1"] = "Pack de Fórmulas Recomendadas pelo Copiloto"
    ws_f["A1"].font = Font(bold=True, size=14, color="1D4ED8")
    ws_f["A2"] = ("Copie a fórmula conforme o idioma do seu Excel: PT-PT usa "
                  "ponto-e-vírgula e nomes locais (SOMASES); English usa vírgula "
                  "(SUMIFS). As referências tblDados[...] exigem converter os "
                  "dados numa Tabela (Ctrl+T).")
    ws_f["A2"].font = Font(size=10, italic=True, color="6B7280")
    ws_f["A2"].alignment = Alignment(wrap_text=True, vertical="top")
    ws_f.merge_cells("A2:F2")
    ws_f.row_dimensions[2].height = 30

    fcols = ["Título", "Categoria", "Fórmula (PT-PT)", "Fórmula (English)",
             "Onde usar", "Para quê"]
    for j, h in enumerate(fcols, start=1):
        c = ws_f.cell(row=4, column=j, value=h)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1D4ED8")
    r = 5
    for f in formulas or []:
        vals = [f.get("title", ""), f.get("category", ""),
                f.get("formula_pt", ""), f.get("formula_en", ""),
                f.get("where", ""), f.get("explanation", "")]
        for j, v in enumerate(vals, start=1):
            c = ws_f.cell(row=r, column=j, value=v)
            c.alignment = Alignment(wrap_text=True, vertical="top")
            if r % 2 == 0:
                c.fill = PatternFill("solid", fgColor="EFF6FF")
        r += 1
    for col, w in zip("ABCDEF", (34, 12, 52, 52, 22, 56)):
        ws_f.column_dimensions[col].width = w
    ws_f.freeze_panes = "A5"

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
