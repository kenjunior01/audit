"""BI Engine — motor de medidas estilo DAX sobre pandas (REA · Power BI parity).

Fase 3 do método REA (compreender antes de construir) documentou as capacidades
núcleo do Power BI e como funcionam:

- DAX: medidas nomeadas avaliadas com *filter context*; iteradores; time
  intelligence (YoY/MoM); razões entre medidas.
- Matrix: pivot dinâmico com margens.
- Decomposition Tree: contribuição hierárquica de uma medida.
- What-if: parâmetro de cenário aplicado à medida.
- Pareto: 80/20 sobre uma dimensão.
- Drillthrough: linhas de detalhe sob um ponto do visual.

Este motor implementa as equivalências de forma determinística e auditável:
tudo é avaliado sobre o dataset de transações com whitelist fechada de
campos/dimensões/agregações (segurança) e RLS aplicado à fonte.
"""
import threading
from datetime import timedelta

import numpy as np
import pandas as pd
from django.db.models import Q
from django.utils import timezone

from .models import RLSRule, Transaction

# ---------------------------------------------------------------- whitelist

FIELDS = {'amount', 'id'}
AGGS = {'sum', 'avg', 'count', 'nunique', 'min', 'max', 'median'}
FILTER_OPS = {'eq', 'ne', 'gt', 'gte', 'lt', 'lte', 'in', 'contains', 'notnull'}
DIMENSIONS = {
    'vendor', 'category', 'status', 'currency', 'user_id',
    'month', 'quarter', 'weekday', 'date', 'week',
}
GRANULARITIES = {'day', 'week', 'month', 'quarter', 'year'}
MAX_DEPTH = 4
MAX_ROWS = 200_000


class BIValidationError(Exception):
    pass


def _validate(node, depth=0):
    """Valida recursivamente a árvore de expressão (whitelist fechada)."""
    if depth > MAX_DEPTH:
        raise BIValidationError("expressão demasiado profunda")
    if not isinstance(node, dict) or 'op' not in node:
        raise BIValidationError("medida inválida: falta 'op'")
    op = node['op']
    if op == 'agg':
        if node.get('agg') not in AGGS:
            raise BIValidationError(f"agregação inválida: {node.get('agg')}")
        if node.get('field') not in FIELDS:
            raise BIValidationError(f"campo inválido: {node.get('field')}")
    elif op in ('calc',):
        _validate(node.get('measure'), depth + 1)
        for f in node.get('filters', []) or []:
            _validate_filter(f)
    elif op in ('ratio', 'diff', 'add', 'mul'):
        _validate(node.get('a'), depth + 1)
        _validate(node.get('b'), depth + 1)
    elif op == 'yoy':
        _validate(node.get('measure'), depth + 1)
    elif op == 'mom':
        _validate(node.get('measure'), depth + 1)
    elif op in ('pct_of_total', 'running_total'):
        _validate(node.get('measure'), depth + 1)
        if node.get('dimension') is not None and node.get('dimension') not in DIMENSIONS:
            raise BIValidationError(f"dimensão inválida: {node.get('dimension')}")
    elif op == 'const':
        v = node.get('value')
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            raise BIValidationError("const requer número")
    else:
        raise BIValidationError(f"op desconhecida: {op}")
    return True


def _validate_filter(f):
    if not isinstance(f, dict) or f.get('field') not in (
            FIELDS | {'vendor', 'category', 'status', 'currency', 'user_id',
                      'transaction_id', 'month', 'weekday', 'date', 'week'}):
        raise BIValidationError(f"filtro: campo inválido {f.get('field')}")
    if f.get('op') not in FILTER_OPS:
        raise BIValidationError(f"filtro: op inválida {f.get('op')}")


# ---------------------------------------------------------------- dataset

def _base_df(rls_rules=None):
    """Dataset de transações → DataFrame (com RLS aplicado quando existir)."""
    qs = Transaction.objects.all().values(
        'id', 'transaction_id', 'vendor', 'amount', 'currency', 'timestamp',
        'category', 'status', 'user_id')
    if rls_rules:
        for r in rls_rules:
            field = r.dimension
            values = r.allowed_values or []
            if field in ('vendor', 'category', 'status', 'currency', 'user_id') and values:
                qs = qs.filter(**{f"{field}__in": values})
    df = pd.DataFrame(list(qs[:MAX_ROWS]))
    if df.empty:
        return pd.DataFrame(columns=['id', 'transaction_id', 'vendor', 'amount',
                                     'currency', 'timestamp', 'category',
                                     'status', 'user_id'])
    df['amount'] = pd.to_numeric(df['amount'], errors='coerce')
    ts = pd.to_datetime(df['timestamp'], errors='coerce', utc=True)
    df['timestamp'] = ts
    df['month'] = ts.dt.strftime('%Y-%m')
    df['quarter'] = ts.dt.year.astype('Int64').astype(str) + '-T' + ts.dt.quarter.astype('Int64').astype(str)
    df['weekday'] = ts.dt.day_name()
    df['date'] = ts.dt.strftime('%Y-%m-%d')
    return df


def rls_rules_for(user_id, role):
    """Regras RLS ativas aplicáveis a este utilizador (por user_id ou role)."""
    try:
        conds = Q()
        if user_id:
            conds |= Q(user_id=user_id)
        if role:
            conds |= Q(role=role)
        return list(RLSRule.objects.filter(conds, active=True))
    except Exception:
        return []


def _apply_filters(df, filters):
    for f in filters or []:
        field, op, value = f.get('field'), f.get('op'), f.get('value')
        if field == 'month':
            s = pd.to_datetime(df['timestamp'], errors='coerce', utc=True).dt.strftime('%Y-%m')
        elif field == 'week':
            iso = df['timestamp'].dt.isocalendar()
            s = iso['year'].astype(str) + '-S' + iso['week'].astype(str).str.zfill(2)
        elif field == 'weekday':
            s = df['timestamp'].dt.day_name() if 'timestamp' in df else None
        elif field == 'date':
            s = pd.to_datetime(df['timestamp'], errors='coerce', utc=True).dt.strftime('%Y-%m-%d')
        else:
            s = df[field]
        temporal = field in ('date', 'month', 'week')  # ISO strings: comparar lexicograficamente
        if op == 'eq':
            mask = (s == value) if (temporal or field not in FIELDS) else (pd.to_numeric(s, errors='coerce') == float(value))
        elif op == 'ne':
            mask = (s != value)
        elif op in ('gt', 'gte', 'lt', 'lte'):
            if temporal:
                s_cmp = s.astype(str)
                v_cmp = str(value)
            else:
                s_cmp = pd.to_numeric(s, errors='coerce')
                v_cmp = float(value)
            mask = (s_cmp > v_cmp if op == 'gt' else
                    s_cmp >= v_cmp if op == 'gte' else
                    s_cmp < v_cmp if op == 'lt' else s_cmp <= v_cmp)
        elif op == 'in':
            vals = value if isinstance(value, list) else [value]
            mask = s.isin([str(v) for v in vals] if field not in FIELDS else vals)
        elif op == 'contains':
            mask = s.astype(str).str.contains(str(value), case=False, na=False)
        elif op == 'notnull':
            mask = s.notna() & (s.astype(str) != '')
        else:
            raise BIValidationError(f"op de filtro inválida: {op}")
        df = df[mask]
    return df


def _agg_series(s, agg):
    if agg == 'sum':
        return float(np.nansum(s.fillna(0))) if len(s) else 0.0
    if agg == 'avg':
        return float(s.mean()) if len(s) else 0.0
    if agg == 'count':
        return int(len(s))
    if agg == 'nunique':
        return int(s.nunique())
    if agg == 'min':
        return float(s.min()) if len(s) else 0.0
    if agg == 'max':
        return float(s.max()) if len(s) else 0.0
    if agg == 'median':
        return float(s.median()) if len(s) else 0.0
    raise BIValidationError(f"agregação inválida: {agg}")


def _dim_series(df, dim):
    if dim == 'month':
        return df['timestamp'].dt.strftime('%Y-%m')
    if dim == 'quarter':
        return df['quarter']
    if dim == 'weekday':
        return df['timestamp'].dt.day_name()
    if dim == 'date':
        return df['timestamp'].dt.strftime('%Y-%m-%d')
    if dim == 'week':
        iso = df['timestamp'].dt.isocalendar()
        return iso['year'].astype(str) + '-S' + iso['week'].astype(str).str.zfill(2)
    return df[dim].astype(str).replace('None', '—').replace('nan', '—')


def _time_key(ts, granularity):
    """Chave temporal ISO determinística por granularidade."""
    if granularity == 'day':
        return ts.strftime('%Y-%m-%d')
    if granularity == 'week':
        iso = ts.isocalendar()
        return f"{iso.year}-S{iso.week:02d}"
    if granularity == 'month':
        return ts.strftime('%Y-%m')
    if granularity == 'quarter':
        return f"{ts.year}-T{(ts.month - 1) // 3 + 1}"
    return str(ts.year)


# ---------------------------------------------------------------- avaliação

def evaluate_measure(node, df):
    """Avalia a árvore de expressão sobre o DataFrame (filter context já aplicado)."""
    op = node['op']
    if op == 'agg':
        s = pd.to_numeric(df[node['field']], errors='coerce')
        return _agg_series(s, node['agg'])
    if op == 'const':
        return float(node['value'])
    if op == 'calc':
        sub = _apply_filters(df, node.get('filters'))
        return evaluate_measure(node['measure'], sub)
    if op in ('ratio', 'diff', 'add', 'mul'):
        a = evaluate_measure(node['a'], df)
        b = evaluate_measure(node['b'], df)
        if op == 'add':
            return a + b
        if op == 'mul':
            return a * b
        if op == 'diff':
            return a - b
        if b == 0:
            return 0.0
        return a / b
    if op in ('yoy', 'mom'):
        days = 365 if op == 'yoy' else 30
        now = timezone.now()
        cur = _apply_filters(df, [{'field': 'date', 'op': 'gte',
                                   'value': (now - timedelta(days=days)).strftime('%Y-%m-%d')}])
        prev_start = (now - timedelta(days=2 * days)).strftime('%Y-%m-%d')
        prev_end = (now - timedelta(days=days)).strftime('%Y-%m-%d')
        prev = _apply_filters(df, [
            {'field': 'date', 'op': 'gte', 'value': prev_start},
            {'field': 'date', 'op': 'lt', 'value': prev_end},
        ])
        a = evaluate_measure(node['measure'], cur)
        b = evaluate_measure(node['measure'], prev)
        if b == 0:
            return None
        return (a - b) / b
    # pct_of_total / running_total são conceitos de contexto visual: avaliados
    # em group_context; num contexto escalar caem no valor absoluto da medida.
    if op in ('pct_of_total', 'running_total'):
        return evaluate_measure(node['measure'], df)
    raise BIValidationError(f"op desconhecida: {op}")


def run_measure(measure, filters=None, user_id='', role=''):
    """Ponto de entrada: valida, carrega dataset (RLS), aplica filtros globais."""
    _validate(measure)
    df = _base_df(rls_rules=rls_rules_for(user_id, role))
    df = _apply_filters(df, filters)
    return evaluate_measure(measure, df), len(df)


# ---------------------------------------------------------------- visuais

def group_measure(measure, dimension, top_n=20, filters=None, user_id='', role='',
                  mode='plain'):
    """Agrega a medida por dimensão (bar/line/pie). mode: plain|pct_of_total|running_total."""
    _validate(measure)
    if dimension not in DIMENSIONS:
        raise BIValidationError(f"dimensão inválida: {dimension}")
    df = _base_df(rls_rules=rls_rules_for(user_id, role))
    df = _apply_filters(df, filters)
    if df.empty:
        return {'rows': [], 'dimension': dimension, 'mode': mode}

    op = measure['op']
    inner_mode = mode
    if op in ('pct_of_total', 'running_total'):
        # a medida declara o próprio modo visual (estilo DAX calculado no visual)
        inner_mode = op
        measure = measure['measure']
        op = measure['op']

    def _agg_on(sub):
        if measure['op'] == 'agg':
            return _agg_series(pd.to_numeric(sub[measure['field']], errors='coerce'),
                               measure['agg'])
        if measure['op'] == 'calc':
            return evaluate_measure(measure, sub)
        if measure['op'] in ('ratio', 'diff', 'add', 'mul'):
            a = evaluate_measure(measure['a'], sub)
            b = evaluate_measure(measure['b'], sub)
            if measure['op'] == 'add':
                return a + b
            if measure['op'] == 'mul':
                return a * b
            if measure['op'] == 'diff':
                return a - b
            return a / b if b else 0.0
        raise BIValidationError(f"op não agregável por dimensão: {measure['op']}")

    d = _dim_series(df, dimension)
    rows = []
    for key, sub in df.groupby(d, observed=True):
        rows.append({dimension: str(key), 'value': _agg_on(sub)})
    rows.sort(key=lambda r: r['value'], reverse=(inner_mode != 'running_total'))

    if inner_mode == 'pct_of_total':
        total = sum(r['value'] for r in rows) or 1.0
        rows = [{**r, 'value': r['value'] / total} for r in rows]
    elif inner_mode == 'running_total':
        acc, out = 0.0, []
        for r in sorted(rows, key=lambda x: x[dimension]):
            acc += r['value']
            out.append({**r, 'value': acc})
        rows = out

    try:
        top_n = max(1, min(int(top_n or 20), 100))
    except (TypeError, ValueError):
        top_n = 20
    return {'rows': rows[:top_n], 'dimension': dimension, 'mode': inner_mode,
            'total_groups': len(rows)}


def matrix_view(measure, row_dim, col_dim, filters=None, user_id='', role='',
                max_pivot=12):
    """Matrix estilo Power BI: pivot com margens de linha/coluna."""
    _validate(measure)
    if row_dim not in DIMENSIONS or col_dim not in DIMENSIONS:
        raise BIValidationError("dimensões inválidas para matrix")
    df = _base_df(rls_rules=rls_rules_for(user_id, role))
    df = _apply_filters(df, filters)
    if df.empty:
        return {'rows': [], 'row_dim': row_dim, 'col_dim': col_dim, 'grand_total': 0}

    def _agg_on(sub):
        if measure['op'] == 'agg':
            return _agg_series(pd.to_numeric(sub[measure['field']], errors='coerce'),
                               measure['agg'])
        return evaluate_measure(measure, sub)

    r = _dim_series(df, row_dim)
    c = _dim_series(df, col_dim)
    top_rows = list(r.value_counts().head(max_pivot).index)
    top_cols = list(c.value_counts().head(max_pivot).index)
    mask = r.isin(top_rows) & c.isin(top_cols)
    sub = df[mask]

    # pivot manual (determinístico)
    grid = {}
    for rk in top_rows:
        for ck in top_cols:
            cell = sub[(r == rk) & (c == ck)]
            grid[(rk, ck)] = _agg_on(cell) if len(cell) else None
    row_totals = {rk: _agg_on(sub[r == rk]) for rk in top_rows}
    col_totals = {ck: _agg_on(sub[c == ck]) for ck in top_cols}
    grand = _agg_on(sub)

    rows = [{'row': rk,
             **{ck: grid[(rk, ck)] for ck in top_cols},
             'total': row_totals[rk]} for rk in top_rows]
    return {'row_dim': row_dim, 'col_dim': col_dim, 'columns': top_cols,
            'rows': rows, 'col_totals': col_totals, 'grand_total': grand}


def pareto_view(measure, dimension, filters=None, user_id='', role='', max_items=25):
    """Pareto 80/20: valores desc + cum_pct + marcação dos 'vital few'."""
    g = group_measure(measure, dimension, top_n=200, filters=filters,
                      user_id=user_id, role=role)
    rows = g['rows']
    total = sum(r['value'] for r in rows) or 1.0
    cum = 0.0
    crossed = False
    out = []
    for r in rows[:max_items]:
        share = r['value'] / total
        cum += share
        vital = not crossed
        if cum >= 0.80:
            crossed = True
        out.append({**r, 'share': share, 'cum_share': min(cum, 1.0), 'vital_few': vital})
    return {'dimension': dimension, 'rows': out,
            'n_total_groups': g.get('total_groups', len(rows)),
            'n_vital_few': sum(1 for o in out if o['vital_few'])}


def decompose_view(measure, dimensions, filters=None, user_id='', role='',
                   top_n=8):
    """Decomposition Tree: contribuição de cada nível da hierarquia."""
    _validate(measure)
    if not dimensions or not isinstance(dimensions, list):
        raise BIValidationError("dimensions requer lista")
    for d in dimensions:
        if d not in DIMENSIONS:
            raise BIValidationError(f"dimensão inválida: {d}")
    df = _base_df(rls_rules=rls_rules_for(user_id, role))
    df = _apply_filters(df, filters)
    if df.empty:
        return {'tree': [], 'root_value': 0}

    def _agg_on(sub):
        if measure['op'] == 'agg':
            return _agg_series(pd.to_numeric(sub[measure['field']], errors='coerce'),
                               measure['agg'])
        return evaluate_measure(measure, sub)

    root_value = _agg_on(df)
    tree, cur = [], df
    parent_value = root_value or 1.0
    for level, dim in enumerate(dimensions):
        children = []
        d = _dim_series(cur, dim)
        for key, sub in cur.groupby(d, observed=True):
            v = _agg_on(sub)
            children.append({'value': v, 'pct_of_parent': v / parent_value,
                             'filters': (filters or []) + [
                                 {'field': dim, 'op': 'eq', 'value': str(key)}]})
        children.sort(key=lambda c: c['value'], reverse=True)
        children = children[:max(1, min(int(top_n or 8), 20))]
        tree.append({'level': level, 'dimension': dim, 'children': children})
        if not children:
            break
        best = children[0]
        cur = _apply_filters(cur, [{'field': dim, 'op': 'eq', 'value': best['filters'][-1]['value']}])
        parent_value = best['value'] or 1.0
    return {'tree': tree, 'root_value': root_value}


def what_if_view(measure, adjustment_pct=0.0, filters=None, user_id='', role=''):
    """Cenário what-if: base vs ajustado (+/-%) e delta (Power BI what-if param)."""
    base, n = run_measure(measure, filters, user_id, role)
    try:
        pct = max(-95.0, min(float(adjustment_pct or 0), 1000.0))
    except (TypeError, ValueError):
        pct = 0.0
    adjusted = base * (1 + pct / 100.0)
    return {'base': base, 'adjustment_pct': pct, 'adjusted': adjusted,
            'delta': adjusted - base, 'rows': n}


def drillthrough_view(filters, dimension=None, value=None, user_id='', role='',
                      limit=50):
    """Drillthrough: linhas de transação por baixo de um ponto do visual."""
    df = _base_df(rls_rules=rls_rules_for(user_id, role))
    conds = list(filters or [])
    if dimension and value is not None:
        conds.append({'field': dimension, 'op': 'eq', 'value': str(value)})
    df = _apply_filters(df, conds)
    df = df.sort_values('timestamp', ascending=False).head(max(1, min(int(limit or 50), 200)))
    cols = ['transaction_id', 'vendor', 'amount', 'currency', 'category',
            'status', 'user_id', 'timestamp']
    out = df[cols].copy()
    out['timestamp'] = out['timestamp'].astype(str)
    return {'rows': out.to_dict('records'), 'count': len(out)}


# ---------------------------------------------------------------- visuais v2
# Fase REA de iteração: capacidades avançadas do Power BI documentadas e
# reproduzidas — séries com média móvel, forecast (tendência linear),
# deteção de anomalias (z-score), waterfall, funil, scatter e KPI com alvo.

def _agg_on_factory(measure):
    """Função de agregação de sub-DataFrames reutilizável pelos visuais."""
    def _agg_on(sub):
        if measure['op'] == 'agg':
            return _agg_series(pd.to_numeric(sub[measure['field']], errors='coerce'),
                               measure['agg'])
        return evaluate_measure(measure, sub)
    return _agg_on


def _time_series_df(measure, granularity, filters, user_id, role, min_points=2):
    """Série temporal determinística: [(key, value)] ordenada ascendente."""
    _validate(measure)
    if granularity not in GRANULARITIES:
        raise BIValidationError(f"granularidade inválida: {granularity} "
                                f"(use {sorted(GRANULARITIES)})")
    df = _base_df(rls_rules=rls_rules_for(user_id, role))
    df = _apply_filters(df, filters)
    if df.empty:
        return []
    agg = _agg_on_factory(measure)
    ts = df['timestamp'].dt.tz_convert('UTC')
    keys = ts.map(lambda t: None if pd.isna(t) else _time_key(t, granularity))
    keys = keys.dropna()
    out = []
    for key in sorted(keys.unique()):
        sub = df[keys == key]
        out.append({'key': str(key), 'value': agg(sub)})
    return out


def series_view(measure, granularity='month', window=3, filters=None,
                user_id='', role=''):
    """Série temporal + média móvel + acumulado (Power BI analytics pane)."""
    try:
        window = max(2, min(int(window or 3), 12))
    except (TypeError, ValueError):
        window = 3
    rows = _time_series_df(measure, granularity, filters, user_id, role)
    values = [r['value'] for r in rows]
    for i, r in enumerate(rows):
        lo = max(0, i - window + 1)
        seg = values[lo:i + 1]
        r['moving_avg'] = float(np.mean(seg)) if seg else r['value']
        r['cumulative'] = float(np.sum(values[:i + 1]))
    return {'granularity': granularity, 'window': window, 'rows': rows}


def _next_time_key(key, granularity, step=1):
    """Próxima chave temporal ISO (para projeção de forecast)."""
    if granularity == 'year':
        return str(int(key) + step)
    if granularity == 'quarter':
        y, q = key.split('-T')
        q = int(q) + step
        y = int(y) + (q - 1) // 4
        q = (q - 1) % 4 + 1
        return f"{y}-T{q}"
    if granularity == 'month':
        y, m = map(int, key.split('-'))
        total = y * 12 + (m - 1) + step
        return f"{total // 12}-{total % 12 + 1:02d}"
    if granularity == 'week':
        y, w = key.split('-S')
        return f"{y}-S{int(w) + step:02d}"  # projeções curtas: semana incremental
    # day: avança em dias via dateutil-free aritmética
    import datetime as _dt
    d = _dt.date.fromisoformat(key) + _dt.timedelta(days=step)
    return d.isoformat()


def forecast_view(measure, granularity='month', periods=3, filters=None,
                  user_id='', role=''):
    """Forecast estilo Power BI: tendência linear (mínimos quadrados) sobre a
    série histórica + projeção N períodos com intervalo simples (±1 desvio)."""
    try:
        periods = max(1, min(int(periods or 3), 12))
    except (TypeError, ValueError):
        periods = 3
    hist = _time_series_df(measure, granularity, filters, user_id, role)
    if len(hist) < 2:
        return {'granularity': granularity, 'history': hist, 'forecast': [],
                'slope': 0.0, 'note': 'dados insuficientes para tendência'}
    x = np.arange(len(hist), dtype=float)
    y = np.array([r['value'] for r in hist], dtype=float)
    slope, intercept = np.polyfit(x, y, 1)
    resid = y - (slope * x + intercept)
    sigma = float(np.std(resid)) or (abs(float(y.mean())) * 0.1 or 1.0)
    fc = []
    for i in range(len(hist), len(hist) + periods):
        key = _next_time_key(hist[-1]['key'], granularity, i - len(hist) + 1)
        v = float(slope * i + intercept)
        fc.append({'key': key, 'value': max(v, 0.0),
                   'lower': max(v - sigma, 0.0), 'upper': max(v + sigma, 0.0)})
    return {'granularity': granularity, 'history': hist, 'forecast': fc,
            'slope': float(slope), 'sigma': sigma}


def anomaly_view(measure, granularity='month', z_threshold=2.5, filters=None,
                 user_id='', role=''):
    """Deteção de anomalias estilo Power BI: z-score da série; |z| ≥ limiar
    marca o ponto como anomalia (alta ou baixa)."""
    try:
        zt = max(1.0, min(float(z_threshold or 2.5), 5.0))
    except (TypeError, ValueError):
        zt = 2.5
    rows = _time_series_df(measure, granularity, filters, user_id, role)
    values = np.array([r['value'] for r in rows], dtype=float)
    if len(values) >= 3 and float(np.std(values)) > 0:
        mean, std = float(np.mean(values)), float(np.std(values))
        for r, v in zip(rows, values):
            z = (v - mean) / std
            r['z'] = round(float(z), 3)
            r['anomaly'] = bool(abs(z) >= zt)
            r['anomaly_kind'] = ('high' if z > 0 else 'low') if r['anomaly'] else ''
    else:
        for r in rows:
            r['z'] = 0.0
            r['anomaly'] = False
            r['anomaly_kind'] = ''
    return {'granularity': granularity, 'z_threshold': zt, 'rows': rows,
            'n_anomalies': sum(1 for r in rows if r['anomaly'])}


def waterfall_view(measure, dimension, filters=None, user_id='', role='',
                   max_items=12):
    """Waterfall: contribuição incremental de cada membro da dimensão até ao
    total (ordem descendente) — decomposição visual do total."""
    _validate(measure)
    if dimension not in DIMENSIONS:
        raise BIValidationError(f"dimensão inválida: {dimension}")
    g = group_measure(measure, dimension, top_n=max_items, filters=filters,
                      user_id=user_id, role=role)
    rows, cum = [], 0.0
    for r in g['rows']:
        base = cum
        cum += r['value']
        rows.append({**r, 'base': base, 'cumulative': cum})
    return {'dimension': dimension, 'rows': rows, 'total': cum}


def funnel_view(measure, dimension, filters=None, user_id='', role='',
                max_stages=10):
    """Funil: membros ordenados descendente com conversão fase-a-fase e
    percentagem face à primeira fase (estilo visual Funnel do Power BI)."""
    _validate(measure)
    if dimension not in DIMENSIONS:
        raise BIValidationError(f"dimensão inválida: {dimension}")
    g = group_measure(measure, dimension, top_n=max_stages, filters=filters,
                      user_id=user_id, role=role)
    rows = []
    first = g['rows'][0]['value'] if g['rows'] else 0.0
    prev = None
    for i, r in enumerate(g['rows']):
        conv_prev = (r['value'] / prev) if prev else 1.0
        rows.append({**r, 'stage': i + 1, 'conv_prev': min(conv_prev, 1.0) if prev else 1.0,
                     'pct_of_first': (r['value'] / first) if first else 0.0})
        prev = r['value'] or 1.0
    return {'dimension': dimension, 'rows': rows, 'first_value': first}


def scatter_view(measure_x, measure_y, dimension, filters=None, user_id='',
                 role='', max_points=30):
    """Scatter de duas medidas por dimensão com quadrantes (médias) e
    correlação de Pearson — análise cruzada estilo Power BI."""
    _validate(measure_x)
    _validate(measure_y)
    if dimension not in DIMENSIONS:
        raise BIValidationError(f"dimensão inválida: {dimension}")
    df = _base_df(rls_rules=rls_rules_for(user_id, role))
    df = _apply_filters(df, filters)
    if df.empty:
        return {'points': [], 'mean_x': 0, 'mean_y': 0, 'correlation': None}
    agg_x, agg_y = _agg_on_factory(measure_x), _agg_on_factory(measure_y)
    d = _dim_series(df, dimension)
    points = []
    for key, sub in df.groupby(d, observed=True):
        points.append({'dimension': str(key), 'x': agg_x(sub), 'y': agg_y(sub),
                       'n': int(len(sub))})
    points.sort(key=lambda p: p['y'], reverse=True)
    points = points[:max(1, min(int(max_points or 30), 100))]
    xs = np.array([p['x'] for p in points], dtype=float)
    ys = np.array([p['y'] for p in points], dtype=float)
    corr = None
    if len(points) >= 3 and float(np.std(xs)) > 0 and float(np.std(ys)) > 0:
        corr = round(float(np.corrcoef(xs, ys)[0, 1]), 4)
    return {'dimension': dimension, 'measure_x': measure_x, 'measure_y': measure_y,
            'points': points, 'mean_x': float(xs.mean()) if len(xs) else 0.0,
            'mean_y': float(ys.mean()) if len(ys) else 0.0,
            'correlation': corr}


def kpi_view(measure, target=None, filters=None, user_id='', role=''):
    """Cartão KPI com alvo e tendência (30d vs 30d anteriores) — estilo
    visual KPI do Power BI com estado on_track/warn/critical."""
    df = _base_df(rls_rules=rls_rules_for(user_id, role))
    value = evaluate_measure(measure, _apply_filters(df, filters))
    n = len(df)
    try:
        target = float(target) if target is not None else None
    except (TypeError, ValueError):
        target = None
    now = timezone.now()
    cur = _apply_filters(df, [*(filters or []),
                              {'field': 'date', 'op': 'gte',
                               'value': (now - timedelta(days=30)).strftime('%Y-%m-%d')}])
    prev = _apply_filters(df, [
        *(filters or []),
        {'field': 'date', 'op': 'gte', 'value': (now - timedelta(days=60)).strftime('%Y-%m-%d')},
        {'field': 'date', 'op': 'lt', 'value': (now - timedelta(days=30)).strftime('%Y-%m-%d')},
    ])
    agg = _agg_on_factory(measure)
    cur_v = agg(cur) if len(cur) else 0.0
    prev_v = agg(prev) if len(prev) else 0.0
    trend = ((cur_v - prev_v) / prev_v) if prev_v else (None if prev_v == cur_v else 1.0)
    pct_target = (value / target) if target else None
    status = ''
    if target is not None:
        status = ('on_track' if value >= target else
                  'warn' if value >= target * 0.8 else 'critical')
    return {'value': value, 'target': target,
            'pct_of_target': pct_target, 'status': status,
            'trend_30d': trend, 'current_30d': cur_v, 'previous_30d': prev_v,
            'rows': n}
