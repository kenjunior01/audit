"""Relatório Global de Auditoria — PDF premium gerado sobre dados vivos.

Estrutura do documento:
1. Capa (título, organização, período, autor, classificação)
2. Sumário Executivo (KPIs)
3. Metodologia
4. Análise de Risco (distribuição por severidade + gráfico, top fornecedores,
   Benford MAD, tendência 14d)
5. Achados Principais (top alertas)
6. Casos de Auditoria (estado + SLA)
7. Qualidade de Dados (importações Excel recentes, completude de campos)
8. Recomendações (regras sobre os achados)
9. Rodapé legal

Tudo determinístico (sem LLM) — o relatório é um documento formal.
"""
import io
from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone

from .models import Alert, AuditCase, ExcelImportJob, Transaction

# ---------------------------------------------------------------- helpers

def _fmt_money(v, currency='BRL'):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return '—'
    # formato brasileiro/português: 1.234.567,89
    s = f"{v:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    return f"{currency} {s}"


def audit_report_summary(days=30):
    """Dict com todos os números do relatório (usado pelo preview JSON e pelo PDF)."""
    days = max(1, min(int(days or 30), 365))
    now = timezone.now()
    since = now - timedelta(days=days)

    tx_total = Transaction.objects.count()
    tx_value = 0.0
    try:
        from django.db.models import Sum
        agg = Transaction.objects.aggregate(v=Sum('amount'))
        tx_value = float(agg['v'] or 0)
    except Exception:
        pass

    sev_counts = {r['severity']: r['c'] for r in
                  Alert.objects.values('severity').annotate(c=Count('id')).order_by()}
    alert_total = sum(sev_counts.values())
    alert_period = Alert.objects.filter(timestamp__gte=since).count()

    case_counts = {r['status']: r['c'] for r in
                   AuditCase.objects.values('status').annotate(c=Count('id')).order_by()}
    cases_open = case_counts.get('New', 0) + case_counts.get('In Progress', 0)

    # SLA: casos com deadline passada e não fechados
    sla_breach = AuditCase.objects.filter(
        deadline__lt=now).exclude(status__in=['Resolved', 'Closed']).count()

    # top fornecedores por valor transacionado
    top_vendors = []
    try:
        tv = (Transaction.objects.values('vendor').annotate(
            total=Count('id'), value=Sum('amount')).order_by('-value')[:8])
        top_vendors = [{'vendor': r['vendor'] or '—',
                        'n': r['total'], 'value': float(r['value'] or 0)} for r in tv]
    except Exception:
        pass

    # fornecedores com mais alertas (vendor vive no próprio Alert)
    alert_vendors = []
    try:
        av = (Alert.objects.values('vendor').annotate(
            c=Count('id')).order_by('-c')[:5])
        alert_vendors = [{'vendor': r['vendor'] or '—', 'n': r['c']} for r in av]
    except Exception:
        pass

    # Benford MAD (reusa excel_service se disponível)
    benford_mad = None
    try:
        from .excel_service import benford_analysis
        import pandas as pd
        qs = list(Transaction.objects.values_list('amount', flat=True)[:5000])
        res = benford_analysis(pd.Series([float(a) for a in qs if a is not None]))
        benford_mad = res.get('mad') if isinstance(res, dict) else None
    except Exception:
        benford_mad = None

    # tendência de alertas (14 dias, 7+7)
    def _window(start, end):
        return Alert.objects.filter(timestamp__gte=start, timestamp__lt=end).count()
    w_now = _window(now - timedelta(days=7), now)
    w_prev = _window(now - timedelta(days=14), now - timedelta(days=7))
    trend = 'estável'
    if w_prev == 0 and w_now > 0:
        trend = 'alta'
    elif w_prev > 0:
        delta = (w_now - w_prev) / w_prev
        trend = 'alta' if delta > 0.15 else ('queda' if delta < -0.15 else 'estável')

    # qualidade de dados
    imports = [
        {'file': j.file_name, 'rows': j.rows_imported, 'skipped': j.rows_skipped,
         'status': j.status, 'at': timezone.localtime(j.created_at).strftime('%d/%m/%Y %H:%M')}
        for j in ExcelImportJob.objects.order_by('-created_at')[:5]
    ]
    missing_vendor = Transaction.objects.filter(Q(vendor__isnull=True) | Q(vendor='')).count()
    completeness = 100.0
    if tx_total:
        completeness = round(100.0 * (tx_total - missing_vendor) / tx_total, 1)

    return {
        'days': days,
        'period': {'from': timezone.localtime(since).strftime('%d/%m/%Y'),
                   'to': timezone.localtime(now).strftime('%d/%m/%Y')},
        'kpis': {
            'transactions': tx_total,
            'transactions_value': tx_value,
            'alerts': alert_total,
            'alerts_period': alert_period,
            'alerts_by_severity': sev_counts,
            'cases_open': cases_open,
            'cases_by_status': case_counts,
            'sla_breaches': sla_breach,
            'benford_mad': benford_mad,
            'data_completeness': completeness,
            'trend_7d': trend,
            'alerts_last7': w_now,
            'alerts_prev7': w_prev,
        },
        'top_vendors': top_vendors,
        'alert_vendors': alert_vendors,
        'recent_imports': imports,
    }


# ---------------------------------------------------------------- recomendações

def build_recommendations(s):
    """Recomendações formais derivadas dos números (regras determinísticas)."""
    k = s['kpis']
    recs = []
    crit = k['alerts_by_severity'].get('Critical', 0) + k['alerts_by_severity'].get('critical', 0)
    high = k['alerts_by_severity'].get('High', 0) + k['alerts_by_severity'].get('high', 0)
    if crit:
        recs.append((f"Priorizar o tratamento dos {crit} alertas críticos em aberto, com "
                     "atribuição de responsável e prazo de resposta de 48 horas."))
    if high:
        recs.append((f"Rever os {high} alertas de severidade alta — recomendada triagem semanal "
                     "com evidências documentadas no caso de auditoria correspondente."))
    if k['sla_breaches']:
        recs.append((f"{k['sla_breaches']} casos encontram-se fora do SLA. Realinhar prazos, "
                     "escalar aos gestores dos processos e registar justificação formal."))
    mad = k.get('benford_mad')
    if mad is not None:
        if mad > 0.015:
            recs.append((f"A Lei de Benford apresenta MAD de {mad:.4f} (não conformidade). "
                         "Recomendada amostragem dirigida sobre os dígitos que se desviam "
                         "e revisão do processo de aprovação de pagamentos."))
        else:
            recs.append((f"A Lei de Benford apresenta MAD de {mad:.4f} (conformidade). "
                         "Manter monitorização contínua como deteção precoce de anomalias."))
    if k['data_completeness'] < 95:
        recs.append((f"Completude do campo fornecedor em {k['data_completeness']}%. "
                     "Reforçar validações na origem (importação Excel/ingestão) para garantir "
                     "rastreabilidade das análises."))
    if k['trend_7d'] == 'alta':
        recs.append(("Tendência de subida nos últimos 7 dias — reforçar a frequência das "
                     "regras dos agentes de risco e ativar o digest automático por email."))
    if not recs:
        recs.append(("Não foram identificadas situações críticas no período. Manter o ciclo "
                     "de monitorização contínua e o digest executivo semanal."))
    return recs


# ---------------------------------------------------------------- PDF

def build_audit_report_pdf(days=30, org_name='AuditAI Omni', generated_by=''):
    """Gera o PDF completo. Retorna (bytes, file_name)."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    s = audit_report_summary(days)
    k = s['kpis']

    styles = getSampleStyleSheet()
    h1 = ParagraphStyle('RptH1', parent=styles['Title'], fontSize=26, textColor=colors.HexColor('#1e3a5f'), spaceAfter=6)
    h2 = ParagraphStyle('RptH2', parent=styles['Heading2'], fontSize=14, textColor=colors.HexColor('#1e3a5f'),
                        spaceBefore=14, spaceAfter=6)
    body = ParagraphStyle('RptBody', parent=styles['Normal'], fontSize=9.5, leading=14)
    small = ParagraphStyle('RptSmall', parent=styles['Normal'], fontSize=8, textColor=colors.HexColor('#64748b'))
    cover_sub = ParagraphStyle('RptCoverSub', parent=styles['Normal'], fontSize=12, alignment=TA_CENTER,
                               textColor=colors.HexColor('#475569'))

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=2 * cm, bottomMargin=2 * cm,
                            leftMargin=2.2 * cm, rightMargin=2.2 * cm,
                            title=f"Relatório de Auditoria {s['period']['from']}–{s['period']['to']}")
    el = []

    # ---------- capa
    el.append(Spacer(1, 4 * cm))
    el.append(Paragraph('Relatório de Auditoria', h1))
    el.append(Paragraph(f"{org_name} — Plataforma de Auditoria Inteligente", cover_sub))
    el.append(Spacer(1, 0.8 * cm))
    el.append(Paragraph(f"Período de análise: <b>{s['period']['from']} a {s['period']['to']}</b>", cover_sub))
    if generated_by:
        el.append(Paragraph(f"Elaborado por: {generated_by}", cover_sub))
    el.append(Paragraph(f"Emitido em: {timezone.localtime().strftime('%d/%m/%Y %H:%M')}", cover_sub))
    el.append(Spacer(1, 1.4 * cm))
    el.append(Table([[Paragraph('<b>CONFIDENCIAL</b> — documento destinado exclusivamente ao '
                                'uso interno da equipa de auditoria e ao comité de auditoria.',
                                ParagraphStyle('conf', parent=small, alignment=TA_CENTER))]],
                    style=TableStyle([('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#fef3c7')),
                                      ('BOX', (0, 0), (-1, -1), 0.75, colors.HexColor('#f59e0b')),
                                      ('LEFTPADDING', (0, 0), (-1, -1), 12), ('RIGHTPADDING', (0, 0), (-1, -1), 12)])))
    el.append(Spacer(1, 1.2 * cm))

    # ---------- 1. sumário executivo
    el.append(Paragraph('1. Sumário Executivo', h2))
    sev = k['alerts_by_severity']
    crit_n = sev.get('Critical', 0) + sev.get('critical', 0)
    high_n = sev.get('High', 0) + sev.get('high', 0)
    exec_text = (
        f"No período de {s['period']['from']} a {s['period']['to']} a plataforma monitorizou "
        f"<b>{k['transactions']:,}</b> transações no valor total de <b>{_fmt_money(k['transactions_value'])}</b>, "
        f"das quais resultaram <b>{k['alerts']}</b> alertas de risco ({crit_n} críticos, {high_n} de severidade alta). "
        f"Encontram-se abertos <b>{k['cases_open']}</b> casos de auditoria, dos quais <b>{k['sla_breaches']}</b> "
        f"fora do SLA definido. A tendência de alertas na última semana é de <b>{k['trend_7d']}</b> "
        f"({k['alerts_last7']} vs. {k['alerts_prev7']} na semana anterior). "
        + (f"O teste de Benford apresenta MAD de <b>{k['benford_mad']:.4f}</b> "
           f"({'dentro' if k['benford_mad'] <= 0.015 else 'acima'} do limiar de conformidade de 0,015)." if k['benford_mad'] is not None
           else "O teste de Benford não pôde ser calculado (dados insuficientes)."))
    el.append(Paragraph(exec_text, body))

    kpi_rows = [
        ['Indicador', 'Valor', 'Indicador', 'Valor'],
        ['Transações', f"{k['transactions']:,}", 'Casos abertos', str(k['cases_open'])],
        ['Valor total', _fmt_money(k['transactions_value']), 'Fora do SLA', str(k['sla_breaches'])],
        ['Alertas (total)', str(k['alerts']), 'Completude dados', f"{k['data_completeness']}%"],
        ['Alertas (período)', str(k['alerts_period']), 'Tendência 7d', k['trend_7d']],
    ]
    t = Table(kpi_rows, colWidths=[4.2 * cm, 4.2 * cm, 4.2 * cm, 4.2 * cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a5f')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8.5),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#cbd5e1')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f1f5f9')]),
        ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    el.append(Spacer(1, 0.3 * cm))
    el.append(t)

    # ---------- 2. metodologia
    el.append(Paragraph('2. Metodologia', h2))
    el.append(Paragraph(
        "Os resultados baseiam-se na análise contínua das transações registadas na plataforma: "
        "(i) regras de risco determinísticas aplicadas por agentes automáticos; (ii) teste estatístico "
        "de conformidade de Benford sobre os primeiros dígitos dos valores (MAD &lt; 0,015 indica "
        "conformidade); (iii) deteção de duplicados exatos e fuzzy; (iv) deteção de valores redondos "
        "e lançamentos em fins de semana; (v) reconciliação de contas no Excel Studio. Os achados são "
        "convertidos em alertas com severidade e, quando relevantes, agrupados em casos de auditoria "
        "com rastreabilidade integral (ImmutableAuditLog).", body))

    # ---------- 3. análise de risco
    el.append(Paragraph('3. Análise de Risco', h2))
    sev_labels = [('critical', 'Crítico'), ('high', 'Alto'), ('medium', 'Médio'),
                  ('low', 'Baixo'), ('info', 'Informativo')]
    sev_rows = [['Severidade', 'Nº de alertas', 'Distribuição']]
    bar_colors = {'Crítico': '#dc2626', 'Alto': '#ea580c', 'Médio': '#d97706',
                  'Baixo': '#2563eb', 'Informativo': '#64748b'}
    max_n = max([sev.get(sl, sev.get(sl.lower(), 0)) for sl, _ in sev_labels] + [1])
    for slug, label in sev_labels:
        n = sev.get(slug, sev.get(slug.capitalize(), 0))
        frac = max(n / max_n, 0.02 if n else 0)
        sev_rows.append([label, str(n), f"{'█' * int(frac * 30) or '·'} {n / max(k['alerts'], 1) * 100:.0f}%"])
    t = Table(sev_rows, colWidths=[3.5 * cm, 2.8 * cm, 10.5 * cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a5f')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8.5),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#cbd5e1')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f1f5f9')]),
        ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    el.append(t)

    if s['alert_vendors']:
        el.append(Spacer(1, 0.25 * cm))
        el.append(Paragraph('<b>Fornecedores com mais alertas</b>', body))
        av_rows = [['Fornecedor', 'Alertas']] + [[v['vendor'], str(v['n'])] for v in s['alert_vendors']]
        t = Table(av_rows, colWidths=[10 * cm, 4 * cm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#334155')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8.5),
            ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#cbd5e1')),
        ]))
        el.append(t)

    # ---------- 4. achados principais
    el.append(Paragraph('4. Achados Principais', h2))
    alerts_qs = Alert.objects.order_by('-timestamp')[:15]
    find_rows = [['ID', 'Severidade', 'Tipo', 'Fornecedor', 'Valor', 'Data']]
    for a in alerts_qs:
        vendor = a.vendor
        if not vendor and a.transaction:
            vendor = a.transaction.vendor
        amount = _fmt_money(a.amount) if a.amount is not None else '—'
        data_str = timezone.localtime(a.timestamp).strftime('%d/%m/%Y') if a.timestamp else '—'
        find_rows.append([str(a.pk), str(a.severity or '—'), str(a.alert_type)[:28],
                          (vendor or '—')[:24], amount, data_str])
    t = Table(find_rows, colWidths=[1.2 * cm, 2.2 * cm, 4.4 * cm, 4.2 * cm, 3.2 * cm, 1.6 * cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a5f')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 7.5),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#cbd5e1')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f1f5f9')]),
    ]))
    el.append(t)

    # ---------- 5. casos
    el.append(Paragraph('5. Casos de Auditoria', h2))
    cs = k['cases_by_status']
    case_txt = (f"Carteira de casos: {cs.get('New', 0)} novos, {cs.get('In Progress', 0)} em curso, "
                f"{cs.get('Resolved', 0)} resolvidos, {cs.get('Closed', 0)} encerrados. "
                f"Total em aberto: <b>{k['cases_open']}</b>. Fora do SLA: <b>{k['sla_breaches']}</b>.")
    el.append(Paragraph(case_txt, body))

    # ---------- 6. qualidade de dados
    el.append(Paragraph('6. Qualidade de Dados', h2))
    el.append(Paragraph(
        f"Completude do campo fornecedor: <b>{k['data_completeness']}%</b>. "
        f"Últimas importações ({len(s['recent_imports'])}): " +
        ('; '.join(f"{i['file']} ({i['rows']} linhas, {i['status']})" for i in s['recent_imports'])
         if s['recent_imports'] else 'sem importações registadas') + '.', body))

    # ---------- 7. recomendações
    el.append(Paragraph('7. Recomendações', h2))
    recs = build_recommendations(s)
    for i, r in enumerate(recs, 1):
        el.append(Paragraph(f"<b>{i}.</b> {r}", body))
        el.append(Spacer(1, 0.12 * cm))

    # ---------- rodapé
    el.append(Spacer(1, 0.8 * cm))
    el.append(Paragraph(
        'Este documento foi gerado automaticamente pela plataforma AuditAI Omni com base em dados '
        'vividos no período indicado. Os valores apresentados destinam-se a suportar o trabalho de '
        'auditoria e não substituem o juízo profissional do auditor. Trilha de auditoria imutável '
        'disponível na plataforma para verificação de cada achado.', small))

    doc.build(el)
    pdf = buf.getvalue()
    buf.close()
    fname = f"relatorio_auditoria_{timezone.localdate().strftime('%Y%m%d')}.pdf"
    return pdf, fname, s
