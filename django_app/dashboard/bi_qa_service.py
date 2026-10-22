"""Pergunte aos dados — Q&A em linguagem natural sobre o modelo BI.

Equivalente ao visual Q&A / Copilot do Power BI, mas determinístico e
auditável (REA: compreender antes de construir — o parser é transparente,
devolve a especificação gerada para o utilizador validar).

Pipeline: normalizar → detectar agregação → campo → dimensão → filtros
(tempo, fornecedor, estado) → top N → modo → visual sugerido → executar.
Sem LLM: 100% offline, latência estável e testável.
"""
import re
from datetime import date, timedelta

from .bi_service import (BIValidationError, group_measure, kpi_view,
                         matrix_view, pareto_view, series_view,
                         waterfall_view, funnel_view, scatter_view)
from .copilot_service import extract_vendor, norm_q

# ---- léxicos (PT primeiro, EN como alternativa) --------------------------

AGG_WORDS = [
    (r'\b(mediana|median)\b', 'median'),
    (r'\b(media|average|avg|em media)\b', 'avg'),
    (r'\b(numero de|quantas|quantos|contagem|count|n de|nr de|num de)\b', 'count'),
    (r'\b(distintos?|unicos?|nunique)\b', 'nunique'),
    (r'\b(maximo|maior valor|max)\b', 'max'),
    (r'\b(minimo|menor valor|min)\b', 'min'),
    (r'\b(soma|somatorio|total|sum)\b', 'sum'),
]
DIM_WORDS = [
    (r'\b(dia da semana|weekday)\b', 'weekday'),
    (r'\b(por mes|mensal|month|monthly)\b', 'month'),
    (r'\b(trimestre|trimestral|quarter)\b', 'quarter'),
    (r'\b(semana|semanal|weekly)\b', 'week'),
    (r'\b(dia|diario|daily)\b', 'date'),
    (r'\b(fornecedores?|fornecedora?|vendor|entidade|empresa)\b', 'vendor'),
    (r'\b(categorias?|category|categorica)\b', 'category'),
    (r'\b(moedas?|currency)\b', 'currency'),
    (r'\b(utilizadores?|usuario|users?)\b', 'user_id'),
    (r'\b(estados?|status|situacao)\b', 'status'),
]
STATUS_WORDS = [
    (r'\b(pendentes?|pending)\b', 'Pending'),
    (r'\b(aprovad[oa]s?|approved)\b', 'aprovad'),
    (r'\b(rejeitad[oa]s?|rejected)\b', 'rejeitad'),
    (r'\b(bandeirad[oa]s?|flagged|sinalizad[oa]s?)\b', 'flag'),
    (r'\b(concluid[oa]s?|completed|complet[oa]s?)\b', 'Conclud'),
]

COUNT_WORDS = r'\b(transacoes?|transactions?|registros?|entradas?|operacoes?)\b'
VALUE_WORDS = r'\b(valor(es)?|montante|amount|volume|dinheiro|gasto|despesa)\b'
VISUAL_WORDS = [
    (r'\b(pareto|80 ?/ ?20)\b', 'pareto'),
    (r'\b(tendencia|evolucao|ao longo do tempo|time ?line|serie)\b', 'series'),
    (r'\b(matrix|tabela cruzada|cruzad[oa])\b', 'matrix'),
    (r'\b(waterfall|cascata)\b', 'waterfall'),
    (r'\b(funil|funnel)\b', 'funnel'),
    (r'\b(pizza|torta|pie|distribuicao)\b', 'pie'),
    (r'\b(barras?|bar)\b', 'bar'),
]
TIME_WORDS = [
    (r'\bhoje\b', 'today'),
    (r'\bontem\b', 'yesterday'),
    (r'\b(este mes|deste mes|mes atual|mes corrente)\b', 'this_month'),
    (r'\b(mes passado|mes anterior)\b', 'last_month'),
    (r'\b(este ano|deste ano|ano atual|ano corrente)\b', 'this_year'),
    (r'\b(ano passado|ano anterior)\b', 'last_year'),
]
DAYS_RE = re.compile(r'\bultim[oa]s?\s+(\d+)\s+dias?\b', re.I)
MONTHS_RE = re.compile(r'\bultim[oa]s?\s+(\d+)\s+mes(es)?\b', re.I)
TOP_RE = re.compile(r'\btop\s+(\d{1,3})\b', re.I)


def _add_months(d: date, n: int) -> date:
    total = d.year * 12 + (d.month - 1) + n
    return date(total // 12, total % 12 + 1, 1)


def parse_question(question: str, today: date | None = None):
    """Traduz a pergunta numa especificação executável (auditável).

    Retorna dict com measure, dimension, visual, filters, top_n, mode,
    title, confidence e tokens detetados — nada é escondido.
    """
    today = today or date.today()
    q = norm_q(question or '')
    tokens = {}

    # 1) agregação + campo
    agg = 'sum'
    for rx, a in AGG_WORDS:
        if re.search(rx, q):
            agg, tokens['agg'] = a, a
            break
    if re.search(COUNT_WORDS, q) and agg in ('sum',) and not re.search(VALUE_WORDS, q):
        agg = 'count'
        tokens['agg'] = 'count'
    field = 'amount' if re.search(VALUE_WORDS, q) or agg not in ('count', 'nunique') else 'id'
    if agg in ('count', 'nunique') and not re.search(VALUE_WORDS, q):
        field = 'id'
    measure = {'op': 'agg', 'agg': agg, 'field': field}

    # 2) dimensão
    dimension = ''
    for rx, d in DIM_WORDS:
        if re.search(rx, q):
            dimension, tokens['dim'] = d, d
            break

    # 3) visual sugerido
    visual = ''
    for rx, v in VISUAL_WORDS:
        if re.search(rx, q):
            visual, tokens['visual'] = v, v
            break
    if not visual:
        if dimension in ('month', 'week', 'date', 'quarter'):
            visual = 'series'
        elif dimension:
            visual = 'bar'
        else:
            visual = 'kpi'
    if visual in ('series',) and dimension not in ('month', 'week', 'date', 'quarter'):
        dimension = tokens['dim'] = 'month'
    if not dimension and visual not in ('kpi',):
        dimension = 'vendor'

    # 4) filtros de tempo
    filters, tl = [], tokens.setdefault('tempo', [])
    month_keys = []
    if re.search(DAYS_RE, q):
        n = int(DAYS_RE.search(q).group(1))
        n = max(1, min(n, 3650))
        filters.append({'field': 'date', 'op': 'gte',
                        'value': (today - timedelta(days=n)).isoformat()})
        tl.append(f'últimos {n} dias')
    m = re.search(MONTHS_RE, q)
    if m:
        n = max(1, min(int(m.group(1)), 60))
        for i in range(n):
            d0 = _add_months(today, -(i + 1))
            month_keys.append(d0.strftime('%Y-%m'))
        month_keys.insert(0, today.strftime('%Y-%m'))
        filters.append({'field': 'month', 'op': 'in', 'value': month_keys})
        tl.append(f'últimos {n} meses')
    for rx, kind in TIME_WORDS:
        if re.search(rx, q):
            if kind == 'today':
                filters.append({'field': 'date', 'op': 'eq', 'value': today.isoformat()})
            elif kind == 'yesterday':
                filters.append({'field': 'date', 'op': 'eq',
                                'value': (today - timedelta(days=1)).isoformat()})
            elif kind == 'this_month':
                filters.append({'field': 'month', 'op': 'eq',
                                'value': today.strftime('%Y-%m')})
            elif kind == 'last_month':
                d0 = _add_months(today, -1)
                filters.append({'field': 'month', 'op': 'eq',
                                'value': d0.strftime('%Y-%m')})
            elif kind == 'this_year':
                filters.append({'field': 'date', 'op': 'gte',
                                'value': date(today.year, 1, 1).isoformat()})
            elif kind == 'last_year':
                filters.append({'field': 'date', 'op': 'gte',
                                'value': date(today.year - 1, 1, 1).isoformat()})
                filters.append({'field': 'date', 'op': 'lt',
                                'value': date(today.year, 1, 1).isoformat()})
            tl.append(kind)
            break

    # 5) fornecedor + estado
    vendor = extract_vendor(question)
    if vendor:
        filters.append({'field': 'vendor', 'op': 'contains', 'value': vendor})
        tokens['vendor'] = vendor
    for rx, val in STATUS_WORDS:
        if re.search(rx, q):
            filters.append({'field': 'status', 'op': 'contains', 'value': val})
            tokens['status'] = val
            break

    # 6) top N + modo
    top_n = 20
    m = re.search(TOP_RE, q)
    if m:
        top_n = max(1, min(int(m.group(1)), 100))
        tokens['top_n'] = top_n
    mode = 'plain'
    if re.search(r'\b(percentagem|percentual|participacao|share|%)\b', q):
        mode, tokens['mode'] = 'pct_of_total', 'pct_of_total'
    elif re.search(r'\b(acumulado|cumulativo|running)\b', q):
        mode, tokens['mode'] = 'running_total', 'running_total'

    # 7) título legível
    agg_pt = {'sum': 'Total', 'avg': 'Média', 'count': 'Contagem',
              'nunique': 'Nº únicos', 'min': 'Mínimo', 'max': 'Máximo',
              'median': 'Mediana'}.get(agg, 'Total')
    field_pt = 'valor' if field == 'amount' else 'registos'
    title = f"{agg_pt} de {field_pt}"
    if dimension:
        dim_pt = {'vendor': 'por fornecedor', 'category': 'por categoria',
                  'month': 'por mês', 'week': 'por semana', 'quarter': 'por trimestre',
                  'date': 'por dia', 'weekday': 'por dia da semana',
                  'currency': 'por moeda', 'user_id': 'por utilizador',
                  'status': 'por estado'}.get(dimension, f'por {dimension}')
        title += f" {dim_pt}"

    confidence = 0.55 + 0.1 * len(tokens) - (0.2 if not dimension and visual != 'kpi' else 0)
    confidence = max(0.3, min(0.95, confidence))
    return {'measure': measure, 'dimension': dimension, 'visual': visual,
            'filters': filters, 'top_n': top_n, 'mode': mode, 'title': title,
            'confidence': round(confidence, 2), 'tokens': tokens}


def _execute_visual(spec, user_id='', role=''):
    v, dim = spec['visual'], spec['dimension']
    kw = {'filters': spec['filters'], 'user_id': user_id, 'role': role}
    if v == 'kpi' or not dim:
        return {'data': kpi_view(spec['measure'], filters=spec['filters'],
                                 user_id=user_id, role=role), 'kind': 'kpi'}
    if v == 'pareto':
        return {'data': pareto_view(spec['measure'], dim, **kw), 'kind': 'pareto'}
    if v == 'matrix':
        col = 'month' if dim != 'month' else 'vendor'
        return {'data': matrix_view(spec['measure'], dim, col, **kw), 'kind': 'matrix'}
    if v == 'series':
        return {'data': series_view(spec['measure'],
                                    granularity=('month' if dim in ('month', 'vendor')
                                                else dim), **kw), 'kind': 'series'}
    if v == 'waterfall':
        return {'data': waterfall_view(spec['measure'], dim, **kw), 'kind': 'waterfall'}
    if v == 'funnel':
        return {'data': funnel_view(spec['measure'], dim, **kw), 'kind': 'funnel'}
    return {'data': group_measure(spec['measure'], dim, top_n=spec['top_n'],
                                  mode=spec['mode'], **kw), 'kind': v}


def ask_question(question, user_id='', role='', today=None):
    """Q&A completo: parse → execução → resposta com spec transparente."""
    if not (question or '').strip():
        raise BIValidationError("pergunta vazia")
    spec = parse_question(question, today=today)
    out = _execute_visual(spec, user_id=user_id, role=role)
    return {'question': question, 'spec': spec,
            'kind': out['kind'], 'data': out['data'],
            'explain': (f"Interpretação: {spec['title']}"
                        + (f" ({spec['tokens']['tempo'][0]})" if spec['tokens'].get('tempo') else '')
                        + f" — visual: {spec['visual']}, confiança {spec['confidence']:.0%}. "
                          "Especificação gerada de forma determinística e auditável.")}
