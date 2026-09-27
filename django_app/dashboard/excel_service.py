"""
Excel Studio — Motor de análise de documentos para a Audit Platform.
=====================================================================

Módulo PURO (pandas/openpyxl, sem imports do Django) para que possa ser
testado isoladamente e reutilizado por views, tasks Celery e scripts.

Funcionalidades:
  1. Import inteligente  — leitura .xlsx/.xls/.csv multi-folha, mapeamento
     automático de colunas PT/EN com fuzzy matching, preview e validação.
  2. Análises de auditor — Lei de Benford, duplicados fuzzy, valores
     redondos, transações em fim-de-semana e "split transactions".
  3. Reconciliação       — cruzamento de 2 conjuntos de dados (ex.: banco
     vs contabilidade) com tolerância de valor/data e match fuzzy.
  4. Export premium      — workbooks multi-folha com formatação
     condicional, KPIs, gráficos e folhas de análise.

Uso tipico (via excel_views.py):
    frames = read_uploaded_file(content, filename)
    preview = preview_workbook(frames)
    rows, skipped = standardize_frame(df, mapping)
"""

import io
import re
import math
import unicodedata
import difflib
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# 1. MAPEAMENTO INTELIGENTE DE COLUNAS (PT/EN, fuzzy)
# ---------------------------------------------------------------------------

CANONICAL_FIELDS = {
    "transaction_id": [
        "transaction id", "id transacao", "id da transacao", "numero documento",
        "no documento", "numero do documento", "document no", "document id",
        "referencia", "ref", "voucher", "invoice no", "invoice number",
        "numero nota", "nf", "n documento", "id",
    ],
    "vendor": [
        "vendor", "fornecedor", "payee", "beneficiario", "favorecido",
        "supplier", "entidade", "counterparty", "contraparte", "cliente",
        "customer", "credor", "debitor", "nome do fornecedor",
    ],
    "amount": [
        "amount", "valor", "value", "montante", "total", "valor total",
        "importancia", "quantia", "debit", "debito", "credit", "credito",
        "valor lancado", "price", "preco", "valor da transacao",
    ],
    "currency": [
        "currency", "moeda", "divisa", "cambio", "coin", "sigla moeda",
    ],
    "timestamp": [
        "timestamp", "data", "date", "data lancamento", "data da transacao",
        "data transacao", "data operacao", "data documento", "posting date",
        "data hora", "datetime", "data emissao", "quando",
    ],
    "category": [
        "category", "categoria", "classe", "class", "tipo", "type",
        "rubrica", "conta", "account", "centro de custo", "cost center",
        "natureza", "descricao",
    ],
    "user_id": [
        "user", "usuario", "utilizador", "approver", "aprovador",
        "quem aprovou", "owner", "responsavel", "created by", "por",
        "solicitante", "requerente", "initiator",
    ],
    "status": [
        "status", "estado", "situacao", "state", "situacao atual",
    ],
}

# Campos canônicos obrigatórios para uma importação de transações
REQUIRED_FIELDS = {"amount", "timestamp"}
OPTIONAL_FIELDS = set(CANONICAL_FIELDS) - REQUIRED_FIELDS


def normalize_text(value) -> str:
    """Minúsculas, sem acentos, sem pontuação, espaços colapsados."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    s = str(value)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().strip()
    s = re.sub(r"[º°.]", "_", s)
    s = re.sub(r"[^a-z0-9_ ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _header_score(header: str, synonym: str) -> float:
    """Score de semelhança entre um cabeçalho e um sinónimo canônico."""
    h, syn = normalize_text(header), normalize_text(synonym)
    if not h or not syn:
        return 0.0
    if h == syn:
        return 1.0
    if syn in h or h in syn:
        return 0.85
    ratio = difflib.SequenceMatcher(None, h, syn).ratio()
    # palavras-chave partilhadas contam
    h_words, syn_words = set(h.split()), set(syn.split())
    if h_words & syn_words:
        overlap = len(h_words & syn_words) / max(len(syn_words), 1)
        ratio = max(ratio, 0.55 * overlap + ratio * 0.5)
    return round(ratio, 3)


def map_columns(headers) -> dict:
    """
    Devolve {campo_canonico: header_original} com o melhor cabeçalho
    para cada campo canônico (cada header só pode ser usado uma vez).
    """
    scores = []  # (score, field, header)
    for field, synonyms in CANONICAL_FIELDS.items():
        for header in headers:
            best = max((_header_score(header, syn) for syn in synonyms), default=0.0)
            if best >= 0.55:
                scores.append((best, field, header))
    scores.sort(reverse=True)

    mapping, used_headers = {}, set()
    for score, field, header in scores:
        if field in mapping or header in used_headers:
            continue
        mapping[field] = header
        used_headers.add(header)
    return mapping


# ---------------------------------------------------------------------------
# 2. LEITURA DE FICHEIROS (multi-folha) + PARSE DE VALORES
# ---------------------------------------------------------------------------

SUPPORTED_EXTENSIONS = (".xlsx", ".xlsm", ".xls", ".csv")


def read_uploaded_file(content: bytes, filename: str) -> dict:
    """
    Lê um ficheiro carregado e devolve {nome_da_folha: DataFrame}.
    Para CSV devolve {'csv': DataFrame}.
    """
    name = (filename or "").lower()
    if name.endswith((".xlsx", ".xlsm")):
        return pd.read_excel(io.BytesIO(content), sheet_name=None, engine="openpyxl")
    if name.endswith(".xls"):
        return pd.read_excel(io.BytesIO(content), sheet_name=None, engine="xlrd")
    if name.endswith(".csv"):
        raw = content
        # Detecta encoding simples (utf-8-sig cobre BOM; latin-1 nunca falha)
        for enc in ("utf-8-sig", "utf-8", "latin-1"):
            try:
                text = raw.decode(enc)
                break
            except (UnicodeDecodeError, AttributeError):
                continue
        sep = ";" if text.count(";") > text.count(",") else ","
        df = pd.read_csv(io.StringIO(text), sep=sep, dtype=str)
        return {"csv": df}
    raise ValueError(f"Formato não suportado: {filename}. Use {SUPPORTED_EXTENSIONS}")


def pick_best_sheet(frames: dict) -> str:
    """Escolhe a folha com maior número de células preenchidas."""
    best_name, best_score = None, -1
    for name, df in frames.items():
        if df.empty:
            continue
        score = int(df.notna().sum().sum())
        if score > best_score:
            best_name, best_score = str(name), score
    return best_name or (list(frames)[0] if frames else "")


def parse_amount(value):
    """Converte valores monetários PT ('1.234,56') e EN ('1,234.56')."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if isinstance(value, (int, float, np.integer, np.floating)):
        try:
            return float(value)
        except (TypeError, ValueError, OverflowError):
            return None
    s = str(value).strip()
    if not s:
        return None
    s = re.sub(r"[R$\u20ac\u00a3\u00a4\s]", "", s)  # símbolos monetários
    neg = s.startswith("(") and s.endswith(")")      # contabilidade: (123) = -123
    s = s.strip("()").replace("-", "") if neg else s.lstrip("-")
    s = re.sub(r"[A-Za-z]", "", s)
    if "," in s and "." in s:
        # o separador decimal é o que aparece por último
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        head, _, tail = s.rpartition(",")
        if len(tail) <= 2 and head.count(",") == 0:
            s = head.replace(",", "") + "." + tail
        else:
            s = s.replace(",", "")
    elif "." in s:
        head, _, tail = s.rpartition(".")
        if not (len(tail) <= 2 and head.count(".") == 0):
            s = s.replace(".", "")
    try:
        val = float(s)
        return -val if neg else val
    except ValueError:
        return None


def parse_date(value):
    """Parse robusto de datas (ISO primeiro, depois day-first PT/BR)."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if isinstance(value, (pd.Timestamp, datetime)):
        return pd.to_datetime(value)
    if hasattr(value, "date") and not isinstance(value, str):  # date puro
        return pd.to_datetime(value)
    s = str(value).strip()
    if not s or s.lower() in ("nan", "none", "nat", "null", "-"):
        return None
    # Serial do Excel (dias desde 1899-12-30)
    if re.fullmatch(r"\d{5}(\.0)?", s):
        try:
            base = datetime(1899, 12, 30)
            return pd.to_datetime(base + timedelta(days=float(s)))
        except (ValueError, OverflowError):
            return None
    dt = pd.to_datetime(s, errors="coerce", format="mixed", dayfirst=False)
    if pd.isna(dt):
        dt = pd.to_datetime(s, errors="coerce", format="mixed", dayfirst=True)
    return None if pd.isna(dt) else dt


# ---------------------------------------------------------------------------
# 3. PREVIEW + QUALIDADE DE DADOS
# ---------------------------------------------------------------------------

def preview_workbook(frames: dict, sheet: str = None) -> dict:
    """
    Devolve a estrutura para o wizard de importação:
    folhas, cabeçalhos, mapeamento sugerido, amostra e flags de qualidade.
    """
    sheets = []
    for name, df in frames.items():
        headers = [str(h) for h in df.columns]
        sheets.append({
            "name": str(name),
            "rows": int(len(df)),
            "columns": headers,
            "mapping": map_columns(headers),
        })

    sheet_name = sheet if sheet in frames else pick_best_sheet(frames)
    df = frames.get(sheet_name, pd.DataFrame())
    headers = [str(h) for h in df.columns]
    mapping = map_columns(headers)
    missing = [f for f in REQUIRED_FIELDS if f not in mapping]

    quality = _data_quality(df, mapping)

    sample = df.head(8).replace({np.nan: None}).to_dict(orient="records")
    sample = [{str(k): v for k, v in row.items()} for row in sample]

    return {
        "detected_sheet": sheet_name,
        "sheets": sheets,
        "mapping": mapping,
        "missing_required": missing,
        "quality": quality,
        "sample": sample,
        "suggestion": (
            "Mapeamento automático concluído. Revise e confirme antes de importar."
            if not missing else
            f"Não foi possível mapear automaticamente: {', '.join(missing)}. "
            "Associe manualmente as colunas."
        ),
    }


def _data_quality(df: pd.DataFrame, mapping: dict) -> dict:
    """Diagnóstico rápido de qualidade da folha selecionada."""
    flags, total_rows = [], int(len(df))
    if total_rows == 0:
        return {"rows": 0, "issues": [{"level": "error", "msg": "Folha vazia."}]}

    amount_col = mapping.get("amount")
    date_col = mapping.get("timestamp")
    id_col = mapping.get("transaction_id")

    if amount_col:
        parsed = df[amount_col].map(parse_amount)
        bad_amt = int(parsed.isna().sum() - df[amount_col].isna().sum())
        if bad_amt:
            flags.append({"level": "warning",
                          "msg": f"{bad_amt} linha(s) com valor não numérico em '{amount_col}'."})
        neg = int((parsed < 0).sum())
        if neg:
            flags.append({"level": "info",
                          "msg": f"{neg} valor(es) negativo(s) (notas de crédito/estornos)."})

    if date_col:
        parsed_d = df[date_col].map(parse_date)
        bad_dates = int(parsed_d.isna().sum() - df[date_col].isna().sum())
        if bad_dates:
            flags.append({"level": "warning",
                          "msg": f"{bad_dates} data(s) ilegível(is) em '{date_col}'."})

    if id_col:
        dup_ids = int(df[id_col].astype(str).str.strip().duplicated().sum())
        if dup_ids:
            flags.append({"level": "warning",
                          "msg": f"{dup_ids} ID(s) de transação duplicado(s) — serão ignorados na importação."})

    missing_pct = df.isna().mean().max()
    if missing_pct > 0.4:
        worst = str(df.isna().mean().idxmax())
        flags.append({"level": "warning",
                      "msg": f"Coluna '{worst}' tem {int(missing_pct*100)}% de valores em falta."})

    return {"rows": total_rows, "issues": flags}


# ---------------------------------------------------------------------------
# 4. PADRONIZAÇÃO PARA IMPORTAÇÃO (transações)
# ---------------------------------------------------------------------------

def standardize_frame(df: pd.DataFrame, mapping: dict) -> tuple:
    """
    Aplica o mapeamento e devolve (rows, skipped):
    rows    = lista de dicts canônicos (transaction_id, vendor, amount,
              currency, timestamp ISO, category, user_id, status)
    skipped = lista de {row, reason} para linhas inválidas.
    """
    rows, skipped = [], []

    def cell(row, field):
        col = mapping.get(field)
        if not col or col not in row.index:
            return None
        return row[col]

    for idx, row in df.iterrows():
        amount = parse_amount(cell(row, "amount"))
        dt = parse_date(cell(row, "timestamp"))
        if amount is None:
            skipped.append({"row": int(idx) + 2, "reason": "valor inválido"})
            continue
        if dt is None:
            skipped.append({"row": int(idx) + 2, "reason": "data inválida"})
            continue

        tx_id = cell(row, "transaction_id")
        tx_id = str(tx_id).strip() if tx_id is not None and not pd.isna(tx_id) else ""
        currency = cell(row, "currency")
        vendor = cell(row, "vendor")
        category = cell(row, "category")
        user = cell(row, "user_id")
        status = cell(row, "status")

        def clean(v, default):
            if v is None or (isinstance(v, float) and math.isnan(v)):
                return default
            s = str(v).strip()
            return s or default

        rows.append({
            "transaction_id": tx_id or f"IMP-{datetime.utcnow().strftime('%Y%m%d')}-{len(rows)+1:06d}",
            "vendor": clean(vendor, "Unknown"),
            "amount": round(float(amount), 2),
            "currency": clean(currency, "BRL")[:10],
            "timestamp": dt.isoformat(),
            "category": clean(category, "General")[:64],
            "user_id": clean(user, "system")[:128],
            "status": clean(status, "Pending")[:32],
        })
    return rows, skipped


# ---------------------------------------------------------------------------
# 5. ANÁLISES DE AUDITOR
# ---------------------------------------------------------------------------

BENFORD_EXPECTED = {d: math.log10(1 + 1 / d) for d in range(1, 10)}
BENFORD_BANDS = [
    (0.006, "Conformidade elevada"),
    (0.012, "Conformidade aceitável"),
    (0.015, "Conformidade marginal"),
    (float("inf"), "Não conformidade — investigar"),
]


def benford_analysis(values: pd.Series) -> dict:
    """Distribuição do 1º dígito significativo + MAD (Nigrini)."""
    digits = []
    for v in values.dropna():
        v = abs(float(v))
        if v >= 1:
            first = str(v).lstrip("0.").replace(".", "").lstrip("0")
            if first:
                digits.append(int(first[0]))
    n = len(digits)
    if n < 50:
        return {"applicable": False,
                "reason": f"Amostra insuficiente ({n} valores; mínimo 50).",
                "n": n}

    counts = {d: 0 for d in range(1, 10)}
    for d in digits:
        counts[d] += 1
    observed = {d: counts[d] / n for d in counts}

    mad = float(np.mean([abs(observed[d] - BENFORD_EXPECTED[d]) for d in observed]))
    verdict = next(label for limit, label in BENFORD_BANDS if mad < limit)

    top_dev = sorted(observed, key=lambda d: -abs(observed[d] - BENFORD_EXPECTED[d]))[:3]

    return {
        "applicable": True,
        "n": n,
        "mad": round(mad, 5),
        "verdict": verdict,
        "distribution": [
            {"digit": d,
             "observed_pct": round(observed[d] * 100, 2),
             "expected_pct": round(BENFORD_EXPECTED[d] * 100, 2),
             "deviation_pct": round((observed[d] - BENFORD_EXPECTED[d]) * 100, 2)}
            for d in range(1, 10)
        ],
        "attention_digits": top_dev,
        "insight": (
            f"MAD {mad:.4f} → {verdict}. "
            f"Dígitos mais desviados: {', '.join(map(str, top_dev))}. "
            "Valores com 1º dígito muito acima do esperado merecem amostragem direcionada."
        ),
    }


def _norm_vendor(v) -> str:
    return normalize_text(v)


def fuzzy_duplicates(df: pd.DataFrame, amount_col: str = "amount",
                     vendor_col: str = "vendor", ratio: float = 0.87) -> dict:
    """
    Deteta duplicados: (a) exatos mesmo fornecedor+valor (qualquer data);
    (b) fuzzy — fornecedores quase idênticos com mesmo valor.
    """
    if df.empty:
        return {"exact": [], "fuzzy": [], "summary": "Sem dados."}
    work = df.copy()
    work["_vendor_n"] = work[vendor_col].map(_norm_vendor)

    exact = []
    for (vn, amt), grp in work.groupby(["_vendor_n", amount_col]):
        if vn and len(grp) > 1:
            exact.append({
                "vendor": grp[vendor_col].iloc[0],
                "amount": round(float(amt), 2),
                "count": int(len(grp)),
                "total": round(float(amt) * len(grp), 2),
                "ids": [str(i) for i in grp["transaction_id"]] if "transaction_id" in grp else [],
            })
    exact.sort(key=lambda x: -x["total"])

    # agrupamento fuzzy de fornecedores
    vendors = sorted({v for v in work["_vendor_n"].dropna().unique() if v})
    rep = {}  # nome normalizado -> representante
    for i, a in enumerate(vendors):
        if a in rep:
            continue
        for b in vendors[i + 1:]:
            if b in rep:
                continue
            if difflib.SequenceMatcher(None, a, b).ratio() >= ratio:
                rep[b] = a
        rep[a] = a
    work["_vendor_group"] = work["_vendor_n"].map(lambda v: rep.get(v, v))

    fuzzy = []
    grouped = work.groupby(["_vendor_group", amount_col])
    for (vg, amt), grp in grouped:
        distinct = grp[vendor_col].nunique()
        if vg and distinct > 1:
            fuzzy.append({
                "vendors": sorted(grp[vendor_col].unique().tolist()),
                "amount": round(float(amt), 2),
                "count": int(len(grp)),
                "ids": [str(i) for i in grp["transaction_id"]] if "transaction_id" in grp else [],
            })
    fuzzy.sort(key=lambda x: (-x["count"], x["amount"]))
    fuzzy = fuzzy[:50]

    return {
        "exact": exact[:50],
        "fuzzy": fuzzy,
        "summary": (f"{len(exact)} grupo(s) exato(s) e {len(fuzzy)} possível(is) duplicado(s) fuzzy. "
                    "Total exposto a duplicidade: "
                    f"{sum(g['total'] for g in exact):,.2f}."),
    }


def round_value_flags(df: pd.DataFrame, amount_col: str = "amount") -> dict:
    """Valores redondos (múltiplos de 1 000/5 000/10 000) — clássico red flag."""
    if df.empty:
        return {"items": [], "summary": "Sem dados."}
    s = pd.to_numeric(df[amount_col], errors="coerce").abs().dropna()
    mask = df.loc[s.index, amount_col].apply(
        lambda v: (lambda a: a > 0 and (a % 10000 == 0 or a % 5000 == 0 or a % 1000 == 0))(
            abs(parse_amount(v) or 0)))
    items = df.loc[mask].copy()
    if "amount" in items:
        items = items.sort_values("amount", ascending=False)
    return {
        "items": items.head(50).replace({np.nan: None}).to_dict(orient="records"),
        "count": int(mask.sum()),
        "summary": f"{int(mask.sum())} transação(ões) com valores redondos de alto valor.",
    }


def weekend_flags(df: pd.DataFrame, date_col: str = "timestamp") -> dict:
    """Transações registadas em sábado/domingo."""
    if df.empty:
        return {"items": [], "summary": "Sem dados."}
    dt = pd.to_datetime(df[date_col], errors="coerce")
    mask = dt.dt.dayofweek >= 5
    items = df.loc[mask].copy()
    if date_col in items:
        items[date_col] = dt.loc[mask].dt.strftime("%Y-%m-%d %H:%M")
    return {
        "items": items.head(50).replace({np.nan: None}).to_dict(orient="records"),
        "count": int(mask.sum()),
        "summary": f"{int(mask.sum())} transação(ões) em fim-de-semana.",
    }


def split_transaction_flags(df: pd.DataFrame, threshold: float = 10000.0,
                            amount_col: str = "amount", vendor_col: str = "vendor",
                            user_col: str = "user_id", date_col: str = "timestamp",
                            window_days: int = 7) -> dict:
    """
    "Split transactions": grupos do mesmo fornecedor+utilizador dentro de
    uma janela de dias onde cada valor individual fica abaixo do limiar de
    aprovação mas a soma excede o limiar (fraccionamento para escapar a controlos).
    """
    if df.empty:
        return {"items": [], "summary": "Sem dados."}
    work = df.copy()
    work["_dt"] = pd.to_datetime(work[date_col], errors="coerce")
    work["_amt"] = work[amount_col].map(parse_amount)
    work = work.dropna(subset=["_dt", "_amt"])
    work["_vendor_n"] = work[vendor_col].map(_norm_vendor)

    flagged_idx = set()
    groups = []
    for (vn, user), grp in work.groupby(["_vendor_n", user_col]):
        if not vn or len(grp) < 2:
            continue
        grp = grp.sort_values("_dt")
        rows = grp.reset_index()
        for i in range(len(rows)):
            window = rows[
                (rows["_dt"] >= rows["_dt"].iloc[i])
                & (rows["_dt"] <= rows["_dt"].iloc[i] + timedelta(days=window_days))
            ]
            if len(window) < 2:
                continue
            total = float(window["_amt"].sum())
            below = bool((window["_amt"].abs() < threshold).all())
            if total >= threshold and below:
                flagged_idx.update(int(r) for r in window["index"])
                groups.append({
                    "vendor": grp[vendor_col].iloc[0],
                    "user": user,
                    "n_transactions": int(len(window)),
                    "total": round(total, 2),
                    "period": f"{window['_dt'].min():%Y-%m-%d} → {window['_dt'].max():%Y-%m-%d}",
                })
                break  # 1 grupo por par fornecedor+utilizador

    items = work.loc[sorted(flagged_idx)].copy()
    items["_dt"] = items["_dt"].dt.strftime("%Y-%m-%d")
    return {
        "items": items.head(60).replace({np.nan: None}).to_dict(orient="records"),
        "groups": groups[:30],
        "count": len(flagged_idx),
        "threshold": threshold,
        "summary": (f"{len(groups)} grupo(s) suspeito(s) de fraccionamento "
                    f"(limiar {threshold:,.2f}, janela {window_days} dias)."),
    }


def run_all_analyses(df: pd.DataFrame, threshold: float = 10000.0) -> dict:
    """Executa o pacote completo de análises sobre um DataFrame canônico."""
    amount_col = "amount" if "amount" in df else None
    date_col = "timestamp" if "timestamp" in df else None
    has_amount, has_date = amount_col is not None, date_col is not None

    out = {
        "rows_analyzed": int(len(df)),
        "benford": benford_analysis(df[amount_col]) if has_amount else {"applicable": False},
        "duplicates": fuzzy_duplicates(df) if has_amount else {"exact": [], "fuzzy": []},
        "round_values": round_value_flags(df) if has_amount else {"items": []},
        "weekend": weekend_flags(df) if has_date else {"items": []},
        "splits": (split_transaction_flags(df, threshold=threshold)
                   if has_amount and has_date else {"items": []}),
    }
    risk_signals = sum([
        1 if out["benford"].get("applicable") and "Não conformidade" in out["benford"].get("verdict", "") else 0,
        1 if out["duplicates"].get("exact") else 0,
        1 if out["round_values"].get("count") else 0,
        1 if out["weekend"].get("count") else 0,
        1 if out["splits"].get("groups") else 0,
    ])
    out["risk_score"] = round(min(risk_signals / 5, 1.0), 2)
    out["verdict"] = {
        0: "Sem sinais relevantes nos testes aplicados.",
        1: "Sinais ligeiros — monitorizar.",
        2: "Sinais moderados — recomenda-se amostragem direcionada.",
    }.get(risk_signals, "Sinais elevados — recomenda-se investigação formal.")
    return out


# ---------------------------------------------------------------------------
# 6. RECONCILIAÇÃO
# ---------------------------------------------------------------------------

def reconcile(df_a: pd.DataFrame, df_b: pd.DataFrame,
              amount_tol: float = 0.01, date_tol_days: int = 3,
              vendor_ratio: float = 0.75) -> dict:
    """
    Cruzamento A ↔ B (ex.: extrato bancário vs contabilidade).
    Match = |valor igual ± tolerância| + data dentro da janela + fornecedor
    semelhante (quando existir dos dois lados). Devolve matches e órfãos.
    """
    def prep(df):
        w = df.copy()
        w["_amt"] = w["amount"].map(parse_amount) if "amount" in w else np.nan
        w["_dt"] = pd.to_datetime(w["timestamp"], errors="coerce") if "timestamp" in w else pd.NaT
        if "vendor" not in w:
            w["vendor"] = None
        w["_vendor_n"] = w["vendor"].map(_norm_vendor)
        return w.dropna(subset=["_amt"])

    a, b = prep(df_a), prep(df_b)
    if len(a) > 20000 or len(b) > 20000:
        return {"error": "Conjuntos demasiado grandes para reconciliação interativa (>20k linhas). Use filtros."}

    b_pool = b.reset_index(drop=True).copy()
    b_pool["_used"] = False
    b_amts = b_pool["_amt"].to_numpy()
    b_dts = pd.to_datetime(b_pool["_dt"]).to_numpy(dtype="datetime64[ns]")

    matches, only_a_idx = [], []
    for ridx, ra in a.iterrows():
        amt_a, dt_a = float(ra["_amt"]), ra["_dt"]
        cand_mask = np.abs(b_amts - amt_a) <= amount_tol
        if pd.notna(dt_a):
            with np.errstate(invalid="ignore"):
                dt_ok = np.abs((b_dts - np.datetime64(dt_a.to_datetime64())).astype("timedelta64[D]")
                               .astype(float)) <= date_tol_days
            cand_mask = cand_mask & dt_ok
        candidates = b_pool[cand_mask & (~b_pool["_used"].to_numpy())]
        if candidates.empty:
            only_a_idx.append(ridx)
            continue
        if pd.notna(dt_a):
            days = ((pd.to_datetime(candidates["_dt"]) - dt_a).abs().dt.days.fillna(99))
        else:
            days = pd.Series(0, index=candidates.index)
        best_idx = (days + (candidates["_amt"] - amt_a).abs() / (amount_tol + 1e-9)).idxmin()
        rb = b_pool.loc[best_idx]
        b_pool.at[best_idx, "_used"] = True
        sim = difflib.SequenceMatcher(None, str(ra["_vendor_n"]), str(rb["_vendor_n"])).ratio()
        matches.append({
            "a_id": str(ra.get("transaction_id", "")),
            "b_id": str(rb.get("transaction_id", "")),
            "a_vendor": ra.get("vendor"), "b_vendor": rb.get("vendor"),
            "a_date": str(ra["_dt"].date()) if pd.notna(ra["_dt"]) else None,
            "b_date": str(rb["_dt"].date()) if pd.notna(rb["_dt"]) else None,
            "amount": round(amt_a, 2),
            "vendor_similarity": round(float(sim), 3),
            "weak": bool(sim < vendor_ratio),
        })
    only_a = a.loc[~a.index.isin(only_a_idx)] if only_a_idx else a.iloc[0:0]
    only_b = b_pool[~b_pool["_used"]]

    sum_a = round(float(a["_amt"].sum()), 2)
    sum_b = round(float(b["_amt"].sum()), 2)

    return {
        "summary": {
            "rows_a": int(len(a)), "rows_b": int(len(b)),
            "matched": len(matches),
            "unmatched_a": int(len(only_a)), "unmatched_b": int(len(only_b)),
            "weak_matches": sum(1 for m in matches if m["weak"]),
            "total_a": sum_a, "total_b": sum_b,
            "difference": round(sum_a - sum_b, 2),
        },
        "matches": matches[:200],
        "unmatched_a": only_a.drop(columns=["_amt", "_dt", "_vendor_n"], errors="ignore")
                             .head(100).replace({np.nan: None}).to_dict(orient="records"),
        "unmatched_b": only_b.drop(columns=["_amt", "_dt", "_vendor_n", "_used"], errors="ignore")
                             .head(100).replace({np.nan: None}).to_dict(orient="records"),
    }


# ---------------------------------------------------------------------------
# 7. EXPORT PREMIUM (workbook multi-folha com estilo/gráficos)
# ---------------------------------------------------------------------------

HEADER_FILL = "1E3A8A"   # azul-900
HEADER_FONT = "FFFFFF"
STRIPES = ["FFFFFF", "EFF6FF"]


def _style_header(ws, ncols, fill=HEADER_FILL, font=HEADER_FONT):
    from openpyxl.styles import Font, PatternFill, Alignment
    for c in range(1, ncols + 1):
        cell = ws.cell(row=1, column=c)
        cell.font = Font(bold=True, color=font, size=11)
        cell.fill = PatternFill("solid", fgColor=fill)
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    ws.row_dimensions[1].height = 24


def _autofit_columns(ws, max_width=42):
    from openpyxl.utils import get_column_letter
    ncols = ws.max_column
    for c in range(1, ncols + 1):
        width = 10
        for r in range(1, min(ws.max_row, 200) + 1):
            v = ws.cell(row=r, column=c).value
            if v is not None:
                width = max(width, min(len(str(v)) + 2, max_width))
        ws.column_dimensions[get_column_letter(c)].width = width


def _write_df(ws, df, formats=None):
    """Escreve um DataFrame numa worksheet com cabeçalho estilizado."""
    from openpyxl.utils import get_column_letter
    cols = [str(c) for c in df.columns]
    ws.append(cols)
    for _, row in df.iterrows():
        vals = []
        for v in row:
            if isinstance(v, (list, dict, tuple, set)):
                vals.append(", ".join(str(x) for x in v) if isinstance(v, (list, tuple, set)) else str(v))
            elif isinstance(v, np.ndarray):
                vals.append(str(v.tolist()))
            elif pd.isna(v):
                vals.append(None)
            elif isinstance(v, (pd.Timestamp, datetime)):
                if isinstance(v, pd.Timestamp):
                    v = v.tz_localize(None) if v.tzinfo is not None else v.tz_convert(None)
                elif v.tzinfo is not None:
                    v = v.replace(tzinfo=None)
                vals.append(v)
            elif isinstance(v, (np.integer,)):
                vals.append(int(v))
            elif isinstance(v, (np.floating,)):
                vals.append(float(v))
            else:
                vals.append(v)
        ws.append(vals)
    if formats:
        for col_name, fmt in formats.items():
            if col_name in cols:
                c = cols.index(col_name) + 1
                for r in range(2, ws.max_row + 1):
                    ws.cell(row=r, column=c).number_format = fmt
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(cols))}{max(ws.max_row, 1)}"
    _style_header(ws, len(cols))
    _autofit_columns(ws)


def build_premium_workbook(title: str, df: pd.DataFrame,
                           kpis: dict = None, charts: list = None,
                           extra_sheets: list = None,
                           amount_cols=("amount", "Valor", "total")) -> bytes:
    """
    Constrói um workbook premium:
      • Folha 'Sumário'  — KPIs + gráficos (se fornecidos)
      • Folha 'Dados'    — tabela principal com autofilter/zebra/formats
      • Folhas extra     — ex.: 'Análises', 'Alertas', 'Duplicados'
    Devolve os bytes do .xlsx.
    """
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils.dataframe import dataframe_to_rows
    from openpyxl.formatting.rule import ColorScaleRule, DataBarRule
    from openpyxl.chart import BarChart, LineChart, PieChart, Reference
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    kpis = kpis or {}
    charts = charts or []

    # ---- Folha Sumário ----
    ws_sum = wb.active
    ws_sum.title = "Sumário"
    ws_sum["A1"] = title or "Relatório de Auditoria"
    ws_sum["A1"].font = Font(bold=True, size=16, color=HEADER_FILL)
    ws_sum["A2"] = f"Gerado pela Audit Platform — {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC"
    ws_sum["A2"].font = Font(size=10, italic=True, color="6B7280")

    row = 4
    if kpis:
        ws_sum.cell(row=row, column=1, value="Indicador").font = Font(bold=True)
        ws_sum.cell(row=row, column=2, value="Valor").font = Font(bold=True)
        row += 1
        for k, v in kpis.items():
            ws_sum.cell(row=row, column=1, value=k)
            c = ws_sum.cell(row=row, column=2, value=v)
            if isinstance(v, float):
                c.number_format = "#,##0.00"
            row += 1

    # ---- Folha Dados ----
    ws_data = wb.create_sheet("Dados")
    _write_df(ws_data, df, formats={"amount": "#,##0.00"})

    # formatação condicional na folha de dados
    ncols = [str(c) for c in df.columns]
    if len(df) > 0:
        last = max(ws_data.max_row, 2)
        for col in amount_cols:
            if col in ncols:
                ci = get_column_letter(ncols.index(col) + 1)
                rng = f"{ci}2:{ci}{last}"
                ws_data.conditional_formatting.add(
                    rng, ColorScaleRule(
                        start_type="min", start_color="FFFFFF",
                        end_type="max", end_color="FCA5A5"))
        if "materiality" in ncols:
            ci = get_column_letter(ncols.index("materiality") + 1)
            ws_data.conditional_formatting.add(
                f"{ci}2:{ci}{last}",
                DataBarRule(start_type="num", start_value=0,
                            end_type="num", end_value=1, color="2563EB"))
        if "severity" in ncols:
            ci = ncols.index("severity") + 1
            fill_map = {"Critical": "FCA5A5", "High": "FDBA74",
                        "Medium": "FDE68A", "Low": "BBF7D0"}
            from openpyxl.formatting.rule import CellIsRule
            from openpyxl.styles import PatternFill as PF
            for sev, color in fill_map.items():
                ws_data.conditional_formatting.add(
                    f"{ci}2:{ci}{last}",
                    CellIsRule(operator="equal", formula=[f'"{sev}"'],
                               fill=PF("solid", fgColor=color)))

    # ---- Gráficos no Sumário ----
    for i, spec in enumerate(charts):
        chart_df = spec.get("df")
        if chart_df is None or chart_df.empty:
            continue
        anchor_row = 4 + (len(kpis) + 3) + i * 22
        ws_sum.cell(row=anchor_row - 1, column=1, value=spec.get("title", "")).font = Font(bold=True)
        # escreve dados do gráfico a partir da coluna E
        base_col = 5
        ws_sum.cell(row=anchor_row - 1, column=base_col, value=chart_df.columns[0])
        for j, c in enumerate(chart_df.columns[1:3]):
            ws_sum.cell(row=anchor_row - 1, column=base_col + 1 + j, value=str(c))
        for r, (_, row_vals) in enumerate(chart_df.head(15).iterrows(), start=anchor_row):
            ws_sum.cell(row=r, column=base_col, value=str(row_vals.iloc[0])[:40])
            for j in range(2):
                if len(chart_df.columns) > 1 + j:
                    v = row_vals.iloc[1 + j]
                    ws_sum.cell(row=r, column=base_col + 1 + j,
                                value=float(v) if pd.notna(v) and isinstance(v, (int, float, np.number)) else None)
        n_rows = min(len(chart_df), 15)
        xref = Reference(ws_sum, min_col=base_col, min_row=anchor_row,
                         max_row=anchor_row + n_rows - 1)
        yref = Reference(ws_sum, min_col=base_col + 1,
                         min_row=anchor_row - 1, max_row=anchor_row + n_rows - 1)
        kind = spec.get("type", "bar")
        if kind == "pie":
            ch = PieChart()
            ch.add_data(yref, titles_from_data=True)
            ch.set_categories(xref)
        elif kind == "line":
            ch = LineChart()
            ch.add_data(yref, titles_from_data=True)
            ch.set_categories(xref)
        else:
            ch = BarChart()
            ch.type = "col"
            ch.add_data(yref, titles_from_data=True)
            ch.set_categories(xref)
        ch.title = spec.get("title", "Gráfico")
        ch.height, ch.width = 9, 16
        ws_sum.add_chart(ch, f"A{anchor_row}")

    # ---- Folhas extra ----
    for extra in (extra_sheets or []):
        name, edf = extra.get("name"), extra.get("df")
        if edf is None or not isinstance(edf, pd.DataFrame) or edf.empty:
            continue
        safe = (name or "Extra")[:28]
        ws_extra = wb.create_sheet(safe)
        _write_df(ws_extra, edf, formats=extra.get("formats"))

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def aggregate_for_charts(df: pd.DataFrame) -> list:
    """Gera agregações padrão (top fornecedores, por categoria, por mês)."""
    charts = []
    if "vendor" in df and "amount" in df and len(df):
        top = (df.groupby("vendor")["amount"].sum()
                 .sort_values(ascending=False).head(10).reset_index())
        top.columns = ["Fornecedor", "Total"]
        charts.append({"type": "bar", "title": "Top 10 Fornecedores por Valor",
                       "df": top})
    if "category" in df and "amount" in df and len(df):
        cat = (df.groupby("category")["amount"].sum()
                 .sort_values(ascending=False).head(8).reset_index())
        cat.columns = ["Categoria", "Total"]
        charts.append({"type": "pie", "title": "Distribuição por Categoria",
                       "df": cat})
    if "timestamp" in df and "amount" in df and len(df):
        dt = pd.to_datetime(df["timestamp"], errors="coerce")
        month = (df.assign(_m=dt.dt.to_period("M").astype(str))
                   .groupby("_m")["amount"].sum().reset_index())
        month.columns = ["Mês", "Total"]
        charts.append({"type": "line", "title": "Evolução Mensal do Valor",
                       "df": month})
    return charts
