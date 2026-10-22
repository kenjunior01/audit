"""Auto-Dashboard — painel de 1 clique (método REA, passo 5: "ir além").

Em vez de pedir ao utilizador que configure medidas, dimensões e visuais,
o motor faz *engenharia reversa do dataset* (espírito REA: compreender antes
de construir): observa a estrutura dos dados — cardinalidade, cobertura,
tipos, série temporal — e compõe automaticamente o melhor painel possível.

Princípios herdados do REA:
- Evidências: cada escolha do motor é devolvida em ``meta.choices`` com a
  justificação (ex.: "vendor escolhido como dimensão principal: 4 valores
  distintos, cobertura 100%").
- Compreender antes de construir: a hierarquia de dimensões é deduzida dos
  próprios dados, não fixada em código.
- Ir além: além dos visuais, o motor devolve *insights* narrativos
  determinísticos (concentração 80/20, tendência, anomalias).

Tudo é determinístico, auditável e reutiliza o BI Engine existente
(whitelist fechada + RLS), sem nova superfície de risco.
"""
import numpy as np
import pandas as pd

from .bi_service import (
    BIValidationError,
    _apply_filters,
    _base_df,
    anomaly_view,
    forecast_view,
    group_measure,
    pareto_view,
    rls_rules_for,
    series_view,
)

MEASURE = {'op': 'agg', 'agg': 'sum', 'field': 'amount'}

# Dimensões candidatas por prioridade analítica (valores financeiros primeiro).
CANDIDATE_DIMS = ['vendor', 'category', 'status', 'currency', 'weekday', 'month']


def _sum_series(s):
    return float(pd.to_numeric(s, errors='coerce').fillna(0).sum())


def _rank_dimensions(df):
    """Engenharia reversa das dimensões: pontua cada candidata pela sua
    utilidade analítica (cobertura × cardinalidade saudável 2–12)."""
    scores = []
    n = max(len(df), 1)
    for dim in CANDIDATE_DIMS:
        if dim not in df.columns:
            continue
        s = df[dim].dropna()
        if s.empty:
            continue
        card = int(s.nunique())
        coverage = len(s) / n
        if card < 2:
            grade = 0.1          # constante — sem poder discriminante
        elif card <= 12:
            grade = 1.0          # zona ideal para visuais
        elif card <= 30:
            grade = 0.6
        else:
            grade = 0.3          # alta cardinalidade — só para top-N
        scores.append({'dimension': dim, 'cardinality': card,
                       'coverage': round(coverage, 3), 'score': round(grade * coverage, 3)})
    scores.sort(key=lambda x: x['score'], reverse=True)
    return scores


def _build_insights(df, ranked, series_rows, pareto_payload, anomaly_payload):
    """Insights narrativos determinísticos (sem LLM — auditável)."""
    out = []
    d1 = ranked[0]['dimension'] if ranked else 'vendor'
    rows = pareto_payload.get('rows') or []
    if rows:
        top = rows[0]
        pct = round(top.get('share', 0) * 100)
        out.append(f"\"{top[d1]}\" lidera com {pct}% do volume total.")
        n_vf = pareto_payload.get('n_vital_few')
        n_tot = pareto_payload.get('n_total_groups')
        if n_vf and n_tot:
            out.append(f"Concentração 80/20: {n_vf} de {n_tot} {d1}(s) "
                       f"explicam 80% do volume (regra de Pareto).")
    if series_rows and len(series_rows) >= 2:
        last, prev = series_rows[-1]['value'], series_rows[-2]['value']
        if prev:
            delta = (last - prev) / abs(prev) * 100
            word = 'subiu' if delta >= 0 else 'desceu'
            out.append(f"No último período ({series_rows[-1]['key']}) o volume "
                       f"{word} {abs(delta):.0f}% face ao período anterior.")
    n_anom = anomaly_payload.get('n_anomalies', 0)
    if n_anom:
        keys = [r['key'] for r in anomaly_payload.get('rows', []) if r.get('anomaly')]
        out.append(f"Deteção de anomalias: {n_anom} período(s) fora do padrão "
                   f"({', '.join(map(str, keys[:3]))}).")
    if not out:
        out.append("Ainda não há sinais fortes nos dados — importe mais "
                   "transações no Excel Studio para enriquecer a análise.")
    return out


def auto_dashboard(filters=None, user_id='', role=''):
    """Executa o painel automático completo (1 chamada = 1 painel pronto).

    Reutiliza os motores existentes (group/pareto/series/anomaly/forecast)
    com RLS aplicado; qualquer visual que falhe é simplesmente omitido
    (resiliência — o painel nunca quebra por um visual).
    """
    rules = rls_rules_for(user_id, role)
    df = _apply_filters(_base_df(rls_rules=rules), filters)

    empty = {'empty': True, 'kpis': [], 'visuals': {}, 'insights': [
        "Sem dados no âmbito atual. Comece por importar um Excel no "
        "Excel Studio ou limpar os filtros."],
             'recent': [], 'meta': {'records': 0, 'choices': []}}
    if df.empty:
        return empty

    # -------------------------------------------------- engenharia reversa
    ranked = _rank_dimensions(df)
    d1 = ranked[0]['dimension'] if ranked else 'vendor'
    d2 = ranked[1]['dimension'] if len(ranked) > 1 and ranked[1]['score'] > 0 else d1
    choices = [{'decision': f"dimensão principal = {d1}",
                'evidence': f"{ranked[0]['cardinality']} valores distintos, "
                            f"cobertura {ranked[0]['coverage']:.0%}"},
               {'decision': f"dimensão secundária = {d2}",
                'evidence': (f"{ranked[1]['cardinality']} valores distintos"
                             if len(ranked) > 1 else 'única dimensão útil')}]

    # --------------------------------------------------------------- KPIs
    amounts = pd.to_numeric(df['amount'], errors='coerce').fillna(0)
    total = float(amounts.sum())
    g_top = group_measure(MEASURE, d1, top_n=1, filters=filters,
                          user_id=user_id, role=role)
    top_row = (g_top.get('rows') or [{}])[0]
    top_share = (top_row.get('value', 0) / total) if total else 0
    ts = pd.to_datetime(df['timestamp'], errors='coerce', utc=True).dropna()
    period = {'start': ts.min().strftime('%Y-%m-%d'),
              'end': ts.max().strftime('%Y-%m-%d')} if len(ts) else {}
    kpis = [
        {'key': 'total', 'label': 'Volume total', 'value': round(total, 2),
         'format': 'currency'},
        {'key': 'records', 'label': 'Transações', 'value': int(len(df)),
         'format': 'int'},
        {'key': 'avg', 'label': 'Ticket médio',
         'value': round(float(amounts.mean()) if len(df) else 0, 2),
         'format': 'currency'},
        {'key': 'peak', 'label': 'Maior transação',
         'value': round(float(amounts.max()) if len(df) else 0, 2),
         'format': 'currency'},
        {'key': 'leader', 'label': f'Top {d1}', 'value': str(top_row.get(d1, '—')),
         'detail': f"{top_share:.0%} do volume", 'format': 'text'},
    ]

    # ------------------------------------------------------------ visuais
    def _safe(name, fn):
        try:
            return fn()
        except Exception:
            return None

    visuals = {}
    bar = _safe('bar', lambda: group_measure(MEASURE, d1, top_n=10,
                                             filters=filters, user_id=user_id,
                                             role=role))
    if bar:
        visuals['bar'] = {'dimension': d1, 'title': f"Volume por {d1}", 'data': bar}
    if d2 != d1:
        pie = _safe('pie', lambda: group_measure(MEASURE, d2, top_n=8,
                                                 filters=filters,
                                                 user_id=user_id, role=role))
        if pie and pie.get('rows'):
            visuals['pie'] = {'dimension': d2, 'title': f"Distribuição por {d2}",
                              'data': pie}
    series = _safe('series', lambda: series_view(MEASURE, granularity='month',
                                                 window=3, filters=filters,
                                                 user_id=user_id, role=role))
    if series:
        visuals['series'] = {'title': 'Evolução mensal (com média móvel)',
                             'data': series}
    pareto_payload = _safe('pareto', lambda: pareto_view(MEASURE, d1,
                                                         filters=filters,
                                                         user_id=user_id,
                                                         role=role))
    if pareto_payload:
        visuals['pareto'] = {'dimension': d1, 'title': f"Pareto 80/20 por {d1}",
                             'data': pareto_payload}
    anomaly_payload = _safe('anomaly', lambda: anomaly_view(MEASURE, 'month',
                                                            z_threshold=2.5,
                                                            filters=filters,
                                                            user_id=user_id,
                                                            role=role))
    if anomaly_payload:
        visuals['anomaly'] = {'title': 'Anomalias mensais', 'data': anomaly_payload}
    forecast = _safe('forecast', lambda: forecast_view(MEASURE, 'month',
                                                       periods=3,
                                                       filters=filters,
                                                       user_id=user_id,
                                                       role=role))
    if forecast and forecast.get('forecast'):
        visuals['forecast'] = {'title': 'Projeção 3 meses', 'data': forecast}

    series_rows = (series or {}).get('rows', [])
    insights = _build_insights(df, ranked, series_rows,
                               pareto_payload or {}, anomaly_payload or {})

    # ------------------------------------------------------- drillthrough
    recent_df = df.sort_values('timestamp', ascending=False).head(12)
    recent = []
    for _, r in recent_df.iterrows():
        recent.append({
            'transaction_id': r.get('transaction_id'),
            'vendor': r.get('vendor'),
            'category': r.get('category'),
            'status': r.get('status'),
            'currency': r.get('currency'),
            'amount': (float(r['amount']) if pd.notna(r.get('amount')) else None),
            'date': (r['timestamp'].strftime('%Y-%m-%d')
                     if pd.notna(r.get('timestamp')) else None),
        })

    return {'empty': False,
            'kpis': kpis,
            'visuals': visuals,
            'insights': insights,
            'recent': recent,
            'meta': {'records': int(len(df)), 'period': period,
                     'choices': choices,
                     'dimension_ranking': ranked[:4]}}
