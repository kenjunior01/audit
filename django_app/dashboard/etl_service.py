"""ETL estilo Power Query — 'applied steps' re-executáveis sobre DataFrames.

Vocabulário de passos (whitelist fechada, auditável):
  map_columns  → mapeia cabeçalhos para o canónico (fuzzy, reusa excel_service)
  rename       → {from, to}
  filter       → {field, op: eq|ne|gt|gte|lt|lte|in|contains|notnull, value}
  derive       → {target, kind: month|quarter|weekday|year|pct_of_total|
                  running_total|rank|multiply|add|bucket|upper|lower|trim,
                  field, value}
  dedupe       → {subset?, keep: first|last}
  fillna       → {field, value|strategy: mean|zero}
  cast         → {field, type: number|date|string}
  sort         → {field, desc}
  dropna       → {subset?}
  select       → {columns}
  upper_headers→ {}
  trim_text    → {fields?}

Cada passo devolve entrada; um passo inválido é registado como erro no log
(comportamento Power Query: o passo fica marcado a vermelho) e ignorado.
"""
import numpy as np
import pandas as pd

from .excel_service import map_columns

MAX_STEPS = 50
STEP_OPS = {
    'map_columns', 'rename', 'filter', 'derive', 'dedupe', 'fillna', 'cast',
    'sort', 'dropna', 'select', 'upper_headers', 'trim_text',
}


def _log(log, i, op, note, rows):
    log.append({'step': i + 1, 'op': op, 'note': note, 'rows_after': int(len(rows))})


def _do_filter(df, st, log, i):
    field, op = st.get('field'), (st.get('cmp') or st.get('filter_op'))
    if field not in df.columns:
        _log(log, i, 'filter', f"campo ausente: {field}", df)
        return df
    s = df[field]
    v = st.get('value')
    if not op:
        _log(log, i, 'filter', "falta 'cmp' (eq|ne|gt|gte|lt|lte|in|contains|notnull)", df)
        return df
    try:
        if op == 'eq':
            mask = (s == v) if not isinstance(v, (int, float)) else (pd.to_numeric(s, errors='coerce') == v)
        elif op == 'ne':
            mask = (s != v)
        elif op == 'gt':
            mask = pd.to_numeric(s, errors='coerce') > float(v)
        elif op == 'gte':
            mask = pd.to_numeric(s, errors='coerce') >= float(v)
        elif op == 'lt':
            mask = pd.to_numeric(s, errors='coerce') < float(v)
        elif op == 'lte':
            mask = pd.to_numeric(s, errors='coerce') <= float(v)
        elif op == 'in':
            vals = v if isinstance(v, list) else [v]
            mask = s.isin([str(x) for x in vals])
        elif op == 'contains':
            mask = s.astype(str).str.contains(str(v), case=False, na=False)
        elif op == 'notnull':
            mask = s.notna() & (s.astype(str).str.strip() != '')
        else:
            _log(log, i, 'filter', f"op inválida: {op}", df)
            return df
    except Exception as e:
        _log(log, i, 'filter', f"erro: {e}", df)
        return df
    out = df[mask]
    _log(log, i, 'filter', f"{field} {op} {v!r}: {len(df)}→{len(out)}", out)
    return out


def _do_derive(df, st, log, i):
    target, kind = st.get('target'), st.get('kind')
    field = st.get('field')
    if not target:
        _log(log, i, 'derive', "falta target", df)
        return df
    try:
        if kind in ('month', 'quarter', 'weekday', 'year'):
            dt = pd.to_datetime(df[field], errors='coerce')
            if kind == 'month':
                df[target] = dt.dt.strftime('%Y-%m')
            elif kind == 'quarter':
                df[target] = dt.dt.year.astype('Int64').astype(str) + '-T' + dt.dt.quarter.astype('Int64').astype(str)
            elif kind == 'weekday':
                df[target] = dt.dt.day_name()
            else:
                df[target] = dt.dt.year
        elif kind == 'pct_of_total':
            s = pd.to_numeric(df[field], errors='coerce')
            total = s.sum()
            df[target] = (s / total) if total else 0.0
        elif kind == 'running_total':
            df[target] = pd.to_numeric(df[field], errors='coerce').fillna(0).cumsum()
        elif kind == 'rank':
            df[target] = pd.to_numeric(df[field], errors='coerce').rank(ascending=False)
        elif kind == 'multiply':
            df[target] = pd.to_numeric(df[field], errors='coerce') * float(st.get('value', 1))
        elif kind == 'add':
            df[target] = pd.to_numeric(df[field], errors='coerce') + float(st.get('value', 0))
        elif kind == 'bucket':
            s = pd.to_numeric(df[field], errors='coerce')
            edges = st.get('value') or [0, 100, 1000, 10000, 100000]
            labels = st.get('labels') or [f"≤{e:g}" for e in edges[1:]]
            df[target] = pd.cut(s, bins=[-np.inf] + list(edges[1:]) + [np.inf],
                                labels=labels, right=True)
        elif kind == 'upper':
            df[target] = df[field].astype(str).str.upper()
        elif kind == 'lower':
            df[target] = df[field].astype(str).str.lower()
        elif kind == 'trim':
            df[target] = df[field].astype(str).str.strip()
        else:
            _log(log, i, 'derive', f"kind inválido: {kind}", df)
            return df
        _log(log, i, 'derive', f"coluna '{target}' ({kind})", df)
    except Exception as e:
        _log(log, i, 'derive', f"erro: {e}", df)
    return df


def apply_pipeline(df, steps):
    """Aplica a receita ao DataFrame. Retorna (df', log, ok_count)."""
    log, ok = [], 0
    steps = (steps or [])[:MAX_STEPS]
    for i, st in enumerate(steps):
        if not isinstance(st, dict) or st.get('op') not in STEP_OPS:
            _log(log, i, str(st.get('op') if isinstance(st, dict) else '?'),
                 "passo desconhecido — ignorado", df)
            continue
        op = st['op']
        try:
            if op == 'map_columns':
                mapping = map_columns([str(c) for c in df.columns])
                ren = {hdr: field for field, hdr in mapping.items() if hdr in df.columns}
                df = df.rename(columns=ren)
                _log(log, i, op, f"mapeadas {len(ren)} colunas: {ren or '—'}", df)
            elif op == 'rename':
                f, t = st.get('from'), st.get('to')
                if f in df.columns and t:
                    df = df.rename(columns={f: t})
                _log(log, i, op, f"{f}→{t}", df)
            elif op == 'filter':
                df = _do_filter(df, st, log, i)
            elif op == 'derive':
                df = _do_derive(df, st, log, i)
            elif op == 'dedupe':
                subset = st.get('subset') or None
                if subset and any(c not in df.columns for c in subset):
                    _log(log, i, op, "subset com colunas ausentes", df)
                    continue
                before = len(df)
                df = df.drop_duplicates(subset=subset, keep=st.get('keep', 'first'))
                _log(log, i, op, f"{before}→{len(df)} (dedup)", df)
            elif op == 'fillna':
                f = st.get('field')
                if f in df.columns:
                    if st.get('strategy') == 'mean':
                        df[f] = pd.to_numeric(df[f], errors='coerce').fillna(
                            pd.to_numeric(df[f], errors='coerce').mean())
                    else:
                        df[f] = df[f].fillna(st.get('value', 0))
                _log(log, i, op, f"{f}", df)
            elif op == 'cast':
                f, t = st.get('field'), st.get('type')
                if f in df.columns:
                    if t == 'number':
                        df[f] = pd.to_numeric(df[f], errors='coerce')
                    elif t == 'date':
                        df[f] = pd.to_datetime(df[f], errors='coerce')
                    elif t == 'string':
                        df[f] = df[f].astype(str)
                _log(log, i, op, f"{f}→{t}", df)
            elif op == 'sort':
                f = st.get('field')
                if f in df.columns:
                    df = df.sort_values(f, ascending=not st.get('desc'))
                _log(log, i, op, f"{f} desc={bool(st.get('desc'))}", df)
            elif op == 'dropna':
                subset = st.get('subset') or None
                before = len(df)
                df = df.dropna(subset=subset)
                _log(log, i, op, f"{before}→{len(df)}", df)
            elif op == 'select':
                cols = [c for c in (st.get('columns') or []) if c in df.columns]
                if cols:
                    df = df[cols]
                _log(log, i, op, f"{len(cols)} colunas", df)
            elif op == 'upper_headers':
                df = df.rename(columns={c: str(c).upper() for c in df.columns})
                _log(log, i, op, "cabeçalhos em maiúsculas", df)
            elif op == 'trim_text':
                fields = st.get('fields') or [c for c in df.columns
                                              if df[c].dtype == object]
                for f in fields:
                    if f in df.columns:
                        df[f] = df[f].astype(str).str.strip()
                _log(log, i, op, f"{len(fields)} campos", df)
            ok += 1
        except Exception as e:
            _log(log, i, op, f"erro inesperado: {e}", df)
    return df, log, ok
