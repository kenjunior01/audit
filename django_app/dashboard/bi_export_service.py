"""Exportação BI → Excel formatado (bridge Excel ⇄ BI Studio).

Módulo PURO (openpyxl, sem imports do Django) — recebe o payload de um
visual do bi_service e devolve .xlsx com: título, cabeçalho estilizado,
formatos numéricos, escala de cor condicional, totais, autofilter e painéis
congelados. Equivalente ao "Export data" do Power BI, mas com formatação
de relatório pronta a apresentar.
"""
import io
from datetime import datetime

from openpyxl import Workbook
from openpyxl.formatting.rule import ColorScaleRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

HEADER_FILL = PatternFill('solid', fgColor='1F4E79')
HEADER_FONT = Font(bold=True, color='FFFFFF', size=11)
TITLE_FONT = Font(bold=True, size=14, color='1F4E79')
SUB_FONT = Font(size=10, color='6B7280')
TOTAL_FONT = Font(bold=True)
TOTAL_FILL = PatternFill('solid', fgColor='DCE6F1')
THIN = Side(style='thin', color='D1D5DB')
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def _style_header(ws, ncols, row=1):
    for c in range(1, ncols + 1):
        cell = ws.cell(row=row, column=c)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal='center', vertical='center')
        cell.border = BORDER


def _autosize(ws, ncols, max_w=42):
    for c in range(1, ncols + 1):
        letter = get_column_letter(c)
        width = 12
        for cell in ws[letter][: min(ws.max_row, 200)]:
            v = cell.value
            if v is not None:
                width = max(width, min(len(str(v)) + 2, max_w))
        ws.column_dimensions[letter].width = width


def _num_fmt(col_values):
    if not col_values:
        return None
    nums = [v for v in col_values if isinstance(v, (int, float))]
    if len(nums) < len([v for v in col_values if v is not None]) * 0.8:
        return None
    if all(abs(v) < 100 and v == int(v) for v in nums):
        return '0'
    return '#,##0.00'


def _color_scale(ws, rng):
    try:
        ws.conditional_formatting.add(
            rng, ColorScaleRule(start_type='min', start_color='FFFFFF',
                                end_type='max', end_color='60A5FA'))
    except Exception:
        pass


def _title_block(ws, title, subtitle, ncols):
    ws.cell(row=1, column=1, value=title).font = TITLE_FONT
    ws.cell(row=2, column=1,
            value=f"{subtitle} · AuditAI BI Studio · {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            ).font = SUB_FONT
    return 4  # primeira linha de dados


def _rows_sheet(wb, title, subtitle, headers, rows, total_row=None,
                value_cols=None, sheet='Dados'):
    ws = wb.create_sheet(sheet[:31])
    start = _title_block(ws, title, subtitle, len(headers))
    hr = start
    for c, h in enumerate(headers, 1):
        ws.cell(row=hr, column=c, value=h)
    _style_header(ws, len(headers), row=hr)
    r = hr + 1
    for row in rows:
        for c, v in enumerate(row, 1):
            cell = ws.cell(row=r, column=c, value=v)
            cell.border = BORDER
        r += 1
    last_data = r - 1
    if total_row:
        for c, v in enumerate(total_row, 1):
            cell = ws.cell(row=r, column=c, value=v)
            cell.font = TOTAL_FONT
            cell.fill = TOTAL_FILL
            cell.border = BORDER
        r += 1
    # formatos numéricos + escala de cor nas colunas de valor
    for c in (value_cols or []):
        vals = [ws.cell(row=rr, column=c).value for rr in range(hr + 1, last_data + 1)]
        fmt = _num_fmt([v for v in vals if v is not None])
        if fmt:
            for rr in range(hr + 1, r):
                ws.cell(row=rr, column=c).number_format = fmt
        if last_data > hr + 1:
            _color_scale(ws, f"{get_column_letter(c)}{hr + 1}:{get_column_letter(c)}{last_data}")
    ws.freeze_panes = ws.cell(row=hr + 1, column=1)
    if len(headers) > 1 and last_data > hr:
        ws.auto_filter.ref = (f"A{hr}:{get_column_letter(len(headers))}{last_data}")
    _autosize(ws, len(headers))
    return ws


def export_visual_xlsx(kind, data, title='Visual BI', subtitle=''):
    """Ponto de entrada: kind + payload do bi_service → bytes .xlsx."""
    wb = Workbook()
    wb.remove(wb.active)
    sub = subtitle or f"visual: {kind}"

    if kind == 'matrix':
        cols = data.get('columns', [])
        headers = [data.get('row_dim', 'linha')] + [str(c) for c in cols] + ['Total']
        rows = []
        for r in data.get('rows', []):
            rows.append([r.get('row')] + [r.get(c) for c in cols] + [r.get('total')])
        col_totals = data.get('col_totals', {})
        total_row = (['Total'] + [col_totals.get(c) for c in cols]
                     + [data.get('grand_total')])
        ws = _rows_sheet(wb, title, sub, headers, rows, total_row=total_row,
                         value_cols=list(range(2, len(headers) + 1)))
        _color_scale(ws, f"B5:{get_column_letter(len(headers))}"
                         f"{4 + max(len(rows), 1)}")
    elif kind in ('pareto',):
        headers = ['Membro', 'Valor', 'Participação', 'Acumulado', 'Vital few']
        rows = []
        for r in data.get('rows', []):
            key = r.get(data.get('dimension'), r.get('vendor', r.get('category', '')))
            rows.append([key, r.get('value'), r.get('share'), r.get('cum_share'),
                         'Sim' if r.get('vital_few') else ''])
        _rows_sheet(wb, title, sub, headers, rows, value_cols=[2, 3, 4])
    elif kind in ('series', 'forecast', 'anomaly'):
        headers = ['Período', 'Valor']
        extra = []
        if kind == 'series':
            extra = ['Média móvel', 'Acumulado']
        if kind == 'anomaly':
            extra = ['Z-score', 'Anomalia']
        headers += extra
        rows = []
        for r in data.get('rows', []):
            row = [r.get('key'), r.get('value')]
            if kind == 'series':
                row += [r.get('moving_avg'), r.get('cumulative')]
            if kind == 'anomaly':
                row += [r.get('z'), 'Sim' if r.get('anomaly') else '']
            rows.append(row)
        if kind == 'forecast':
            for f in data.get('forecast', []):
                rows.append([f.get('key'), f.get('value'),
                             f.get('lower'), f.get('upper')])
            headers = ['Período', 'Valor/Projeção', 'Limite inf.', 'Limite sup.']
        _rows_sheet(wb, title, sub, headers, rows, value_cols=[2, 3, 4][:len(headers) - 1])
    elif kind in ('waterfall', 'funnel', 'group'):
        rows0 = data.get('rows', [])
        first = rows0[0] if rows0 else {}
        dim_key = data.get('dimension') or next(
            (k for k in first.keys() if k not in ('value', 'base', 'cumulative',
                                                  'share', 'cum_share', 'vital_few',
                                                  'stage', 'conv_prev', 'pct_of_first')),
            'membro')
        headers = ['Membro', 'Valor']
        if kind == 'waterfall':
            headers += ['Base', 'Acumulado']
        if kind == 'funnel':
            headers += ['Fase', 'Conversão', '% da 1ª fase']
        if any('share' in r for r in rows0):
            headers += ['Participação']
        rows = []
        for r in rows0:
            row = [r.get(dim_key, r.get('dimension')), r.get('value')]
            if kind == 'waterfall':
                row += [r.get('base'), r.get('cumulative')]
            if kind == 'funnel':
                row += [r.get('stage'), r.get('conv_prev'), r.get('pct_of_first')]
            if 'share' in r:
                row += [r.get('share')]
            rows.append(row)
        total = data.get('total') or data.get('first_value')
        _rows_sheet(wb, title, sub, headers, rows,
                    total_row=(['Total', total] if total is not None else None),
                    value_cols=[2])
    elif kind == 'kpi':
        ws = wb.create_sheet('KPI')
        _title_block(ws, title, sub, 2)
        pairs = [('Valor', data.get('value')), ('Alvo', data.get('target')),
                 ('% do alvo', data.get('pct_of_target')),
                 ('Tendência 30d', data.get('trend_30d')),
                 ('Últimos 30 dias', data.get('current_30d')),
                 ('30 dias anteriores', data.get('previous_30d')),
                 ('Estado', data.get('status')), ('Linhas', data.get('rows'))]
        r = 4
        for k, v in pairs:
            ws.cell(row=r, column=1, value=k).font = Font(bold=True)
            ws.cell(row=r, column=2, value=v)
            r += 1
        _autosize(ws, 2)
    elif kind == 'scatter':
        headers = ['Membro', 'X', 'Y', 'Nº registos']
        rows = [[p.get('dimension'), p.get('x'), p.get('y'), p.get('n')]
                for p in data.get('points', [])]
        ws = _rows_sheet(wb, title, sub, headers, rows, value_cols=[2, 3])
        ws.cell(row=1, column=5,
                value=f"Correlação: {data.get('correlation') or '—'}").font = SUB_FONT
    else:
        # drillthrough / genérico: lista de registos
        recs = data.get('rows', [])
        headers = list(recs[0].keys()) if recs else ['(vazio)']
        rows = [[r.get(h) for h in headers] for r in recs]
        _rows_sheet(wb, title, sub, headers, rows)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
