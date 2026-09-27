"""
Copiloto Global da Plataforma (Omni Copilot)
============================================
Assistente de suporte agéntico disponível em TODA a plataforma — não só no
Excel Studio. Três camadas:

1. TOOLS AGÉNTICAS — consultam dados vivos da plataforma (alertas,
   transações, casos, agentes IA, importações Excel, SLA, Benford,
   duplicados, previsão de risco, perfil de fornecedor) e devolvem
   {title, summary (markdown), table, insights, meta}.
2. ROUTER determinístico PT/EN — deteção multi-intenção com extração de
   filtros (severidade, estado, fornecedor, valores, dias, top N, atrasos).
3. SÍNTESE — LLM (Ollama/DeepSeek) opcional com JSON estrito
   {answer, insights, actions, followups} + whitelist de ações de
   navegação; fallback 100% determinístico quando não há LLM.

Desenvolvido para responder sempre com números concretos e propor AÇÕES
navegáveis — o "boost" que leva a IA a todos os cantos da plataforma.

Endpoints (copilot_views.py):
- POST /ai/copilot            → chat {question, history}
- GET  /ai/copilot/briefing   → briefing executivo proativo
"""
import json
import logging
import os
import re
import unicodedata
from datetime import timedelta

from django.db.models import Avg, Count, Q, Sum
from django.utils import timezone

from .models import (Alert, AuditCase, ExcelImportJob, RiskAgent,
                     Transaction)

logger = logging.getLogger(__name__)

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("AUDIT_OLLAMA_MODEL", "deepseek-r1:1.5b")
OLLAMA_TIMEOUT = float(os.environ.get("AUDIT_OLLAMA_TIMEOUT", "25"))

MAX_TOOLS_PER_QUESTION = 4
TABLE_ROW_LIMIT = 10

# Rotas conhecidas do frontend — whitelist de ações navegáveis
KNOWN_ROUTES = [
    "/", "/transactions", "/alerts", "/governance", "/cases", "/sla",
    "/assistant", "/agents", "/excel", "/graph", "/geo-risk",
    "/automation", "/context", "/integrations", "/external-actions",
    "/settings", "/rules", "/signals", "/upload", "/profile",
    "/onboarding", "/wizard",
]

SEVERITY_MAP = {
    "critic": "Critical", "critical": "Critical",
    "altíssim": "Critical", "gravíssim": "Critical",
    "alto": "High", "high": "High", "grave": "High",
    "médio": "Medium", "medio": "Medium", "medium": "Medium",
    "baixo": "Low", "low": "Low", "leve": "Low",
}
ALERT_STATUS_MAP = {
    "novo": "New", "novos": "New", "new": "New",
    "investiga": "Investigating", "em investiga": "Investigating",
    "resolvid": "Resolved", "resolvidos": "Resolved", "resolved": "Resolved",
    "falso positivo": "False Positive", "false positive": "False Positive",
    "falsos positivos": "False Positive",
}
CASE_STATUS_MAP = {
    "novo": "New", "new": "New",
    "em progresso": "In Progress", "em curso": "In Progress",
    "in progress": "In Progress",
    "resolvid": "Resolved", "resolved": "Resolved",
    "fechad": "Closed", "encerrad": "Closed", "closed": "Closed",
}


# ---------------------------------------------------------------------------
# 1. Normalização e router de intenções
# ---------------------------------------------------------------------------

def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", str(text))
                   if unicodedata.category(c) != "Mn")


def norm_q(text: str) -> str:
    return re.sub(r"\s+", " ", strip_accents(text).lower()).strip()


_TOOL_KEYWORDS = [
    # (tool, regex sobre texto normalizado sem acentos)
    # help primeiro — meta-perguntas ganham prioridade sobre tudo
    ("help", r"\bajuda\b|\bhelp\b|o que (sabes|podes|consegues|e que sabes|e que podes) fazer|"
             r"como funciona (isso|o copiloto|a plataforma|este copiloto)|"
             r"quais (as|sua) (capacidades|funcionalidades)|capacidades do copiloto|"
             r"what can you do|como te uso|como utilizar o copiloto"),
    ("explain", r"(explica|explain|porque|por que|why|o que motivou|detalha|detalhe|analisa o alerta|"
                r"analisa o caso|motivo do|razao do)[^.?!]*\b(alerta|alert|caso|case)\b|"
                r"\b(alerta|caso)\s*#?\s*\d+|\balert\s*#?\s*\d+"),
    ("trends", r"tendance?ria semanal|compara|comparar|evolucao|evolu[cu]ao|semana passada|esta semana vs|"
               r"week over week|crescimento|subiu|desceu|caiu|aumentou|diminuiu|ao longo do tempo|"
               r"historico de alertas|historico de transacoes"),
    ("benford", r"benford|1[ºo] digito|primeiro digito|distribuicao dos digitos"),
    ("duplicates", r"duplicad|repetid|duplicate|duas vezes|mesmo valor"),
    ("forecast", r"previsao|prever|tendencia|forecast|proxim[oa]s dias|proxim[oa]s semanas|projecao|vai evoluir"),
    ("sla", r"\bsla\b|atrasad|fora do prazo|vencid|overdue|prazo|deadline|sem resposta"),
    ("agents", r"agentes?\b|agents?\b"),
    ("excel", r"\bexcel\b|importa|planilha|folha|xlsx|csv|ficheiro|sheet"),
    ("cases", r"\bcasos?\b|\bcases?\b|investigac|dossie"),
    ("transactions", r"transac|pagamento|transaction|fatur|compra|despesa"),
    ("alerts", r"alerta|riscos?\b|sever|critic|alert\b|suspeit"),
    ("overview", r"resumo|overview|panorama|estado da plataforma|como esta a plataforma|como anda|situacao geral|kpi|metrica|taxa|volume"),
]

_TOOL_ORDER = ["help", "explain", "overview", "vendor", "forecast", "trends",
               "alerts", "transactions", "cases", "sla", "agents", "excel",
               "benford", "duplicates"]

# Página atual (rota frontend) → tool sugerida quando a pergunta é vaga.
# Dá ao copiloto consciência de contexto: "e agora?" na página de SLA
# responde sobre SLA, não sobre a plataforma em geral.
PAGE_TOOL_HINT = {
    "/": "overview", "/alerts": "alerts", "/transactions": "transactions",
    "/cases": "cases", "/sla": "sla", "/agents": "agents", "/excel": "excel",
    "/graph": "duplicates", "/governance": "overview", "/geo-risk": "overview",
    "/automation": "agents", "/context": "overview", "/integrations": "excel",
    "/external-actions": "agents", "/settings": "excel", "/rules": "agents",
    "/signals": "alerts", "/wizard": "excel", "/upload": "excel",
}


def detect_tools(question: str, page: str = None) -> list:
    """Deteção multi-intenção → lista ordenada de tools (máx. 4).
    `page` = rota atual do frontend; usada como dica quando a pergunta
    não contém palavras-chave reconhecidas."""
    q = norm_q(question)
    found = []
    for tool, pattern in _TOOL_KEYWORDS:
        if re.search(pattern, q) and tool not in found:
            found.append(tool)
    vendor = extract_vendor(question)
    if vendor and ("fornecedor" in q or "vendor" in q or "empresa" in q
                   or '"' in question or "«" in question or "«" in q):
        if "vendor" not in found:
            found.append("vendor")
    if not found:
        hint = PAGE_TOOL_HINT.get((page or "/").rstrip("/") or "/")
        found = [hint] if hint else ["overview"]
    found.sort(key=lambda t: _TOOL_ORDER.index(t) if t in _TOOL_ORDER else 99)
    return found[:MAX_TOOLS_PER_QUESTION]


def extract_vendor(question: str) -> str:
    """Extrai nome de fornecedor: após 'fornecedor/vendor/empresa/da X'
    ou entre aspas."""
    m = re.search(r'["«“]([^"»”]{2,40})["»”]', question)
    if m:
        return m.group(1).strip()
    q = strip_accents(question)
    m = re.search(
        r"(?:fornecedora?|vendor|empresa|entidade|cliente)\s+(?:da|do|de)?\s*"
        r"([A-Za-z0-9][\w&.\- ]{1,38})", q, re.I)
    if m:
        name = m.group(1).strip()
        # corta palavras de ligação que não pertencem ao nome
        name = re.split(
            r"\s+(?:no|na|em|com|de|do|da|que|qual|quais|e\s+os|top|últim)"
            r"\s+", name, flags=re.I)[0]
        return name.strip(" .,;:?!")
    return ""


def _parse_number_pt(token: str):
    t = token.strip().lower()
    mult = 1.0
    if t.endswith("k"):
        mult, t = 1000.0, t[:-1]
    elif t.endswith("m") and re.match(r"^\d+[.,]?\d*m$", t):
        mult, t = 1_000_000.0, t[:-1]
    t = t.replace(" ", "")
    if "," in t and "." in t:
        if t.rfind(",") > t.rfind("."):
            t = t.replace(".", "").replace(",", ".")
        else:
            t = t.replace(",", "")
    elif "," in t:
        # 10,000 (EN milhar) → 10000; 5000,50 (PT decimal) → 5000.50
        dec = t.split(",")[1]
        t = t.replace(",", "") if len(dec) == 3 else t.replace(",", ".")
    elif "." in t and re.match(r"^\d{1,3}(\.\d{3})+$", t):
        # 10.000 (PT milhar) → 10000
        t = t.replace(".", "")
    try:
        return float(t) * mult
    except ValueError:
        return None


def extract_filters(question: str) -> dict:
    """Extrai filtros de linguagem natural (PT/EN)."""
    q = norm_q(question)
    raw = strip_accents(question)
    f = {"severity": None, "alert_status": None, "case_status": None,
         "priority": None, "vendor": "", "category": "",
         "days": None, "top_n": None, "min_amount": None,
         "max_amount": None, "overdue": False,
         "alert_id": None, "case_id": None,
         "latest_alert": False, "latest_case": False}

    # IDs de alerta/caso — "explica o alerta 42", "alert #42", "caso 7"
    m = re.search(r"\b(?:alerta|alert)\s*#?\s*(\d{1,7})\b", q)
    if m:
        f["alert_id"] = int(m.group(1))
    m = re.search(r"\b(?:caso|case)\s*#?\s*(\d{1,7})\b", q)
    if m:
        f["case_id"] = int(m.group(1))
    # "o alerta mais recente", "este alerta", "the latest alert"
    if re.search(r"(alerta|alert)\b[^.?!]*\b(mais recente|recente|latest|last|ultimo|último|este|this)\b", q) \
            or re.search(r"\b(este|this)\s+(alerta|alert|caso|case)\b", q):
        if not f["alert_id"]:
            f["latest_alert"] = True
    if re.search(r"(caso|case)\b[^.?!]*\b(mais recente|recente|latest|last|ultimo|último)\b", q):
        if not f["case_id"]:
            f["latest_case"] = True

    for key, word in (("critic", "critical"), ("altíssim", "critical"),
                      ("alto", "high"), ("high", "high"), ("grave", "high"),
                      ("médio", "medium"), ("medio", "medium"),
                      ("medium", "medium"), ("baixo", "low"), ("low", "low")):
        if key in q:
            f["severity"] = SEVERITY_MAP.get(key) or word
            f["priority"] = f["severity"]
            break

    for key, value in ALERT_STATUS_MAP.items():
        if key in q:
            f["alert_status"] = value
            break
    for key, value in CASE_STATUS_MAP.items():
        if key in q:
            f["case_status"] = value
            break

    if re.search(r"atrasad|overdue|fora do prazo|vencid|sem resposta", q):
        f["overdue"] = True
        f["sla"] = True

    m = re.search(r"ultim[oa]s?\s+(\d{1,4})\s+dias", q) or \
        re.search(r"last\s+(\d{1,4})\s+days?", q)
    if m:
        f["days"] = min(int(m.group(1)), 365)
    elif re.search(r"\bhoje\b|\btoday\b", q):
        f["days"] = 1
    elif re.search(r"esta semana|essa semana|this week", q):
        f["days"] = 7
    elif re.search(r"este mes|esse mes|this month", q):
        f["days"] = 30
    elif re.search(r"ultim[oa]s?\s+horas|last hours|ultimas 24", q):
        f["days"] = 1

    m = re.search(r"\btop\s+(\d{1,3})\b", q) or \
        re.search(r"primeir[oa]s\s+(\d{1,3})\b", q) or \
        re.search(r"(\d{1,3})\s+maiores\b", q) or \
        re.search(r"(\d{1,3})\s+principais\b", q)
    if m:
        f["top_n"] = min(int(m.group(1)), 50)

    m = (re.search(r"maior(es)? que\s+([\d.,]+\s*[kKmM]?)", raw)
         or re.search(r"acima de\s+([\d.,]+\s*[kKmM]?)", raw)
         or re.search(r"\bover\s+([\d.,]+\s*[kKmM]?)", raw)
         or re.search(r">\s*([\d.,]+\s*[kKmM]?)", raw))
    if m:
        f["min_amount"] = _parse_number_pt(m.group(m.lastindex))
    m = (re.search(r"menor(es)? que\s+([\d.,]+\s*[kKmM]?)", raw)
         or re.search(r"abaixo de\s+([\d.,]+\s*[kKmM]?)", raw)
         or re.search(r"\bunder\s+([\d.,]+\s*[kKmM]?)", raw))
    if m:
        f["max_amount"] = _parse_number_pt(m.group(m.lastindex))

    f["vendor"] = extract_vendor(question)
    return f


def _fmt_money(v, currency: str = "") -> str:
    try:
        s = f"{float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (TypeError, ValueError):
        return "—"
    return f"{s}{(' ' + currency) if currency else ''}"


def _fmt_int(v) -> str:
    try:
        return f"{int(v):,}".replace(",", ".")
    except (TypeError, ValueError):
        return "—"


def _table(columns: list, rows: list, total: int) -> dict:
    return {"columns": columns, "rows": rows[:TABLE_ROW_LIMIT],
            "shown": min(len(rows), TABLE_ROW_LIMIT), "total": total}


# ---------------------------------------------------------------------------
# 2. TOOLS AGÉNTICAS — dados vivos da plataforma
#    Cada tool devolve {tool, title, summary, table?, insights[], meta}
# ---------------------------------------------------------------------------

SEV_ORDER = ["Critical", "High", "Medium", "Low"]


def _alert_base_qs(f: dict):
    qs = Alert.objects.all()
    if f.get("severity"):
        qs = qs.filter(severity__iexact=f["severity"])
    if f.get("alert_status"):
        qs = qs.filter(status__iexact=f["alert_status"])
    if f.get("vendor"):
        qs = qs.filter(vendor__icontains=f["vendor"])
    if f.get("days"):
        qs = qs.filter(timestamp__gte=timezone.now() - timedelta(days=f["days"]))
    return qs


def tool_overview(f: dict) -> dict:
    now = timezone.now()
    tx_total = Transaction.objects.count()
    tx_sum = Transaction.objects.aggregate(s=Sum("amount"))["s"] or 0
    tx_30 = Transaction.objects.filter(timestamp__gte=now - timedelta(days=30))
    tx30_count, tx30_sum = tx_30.count(), (tx_30.aggregate(s=Sum("amount"))["s"] or 0)

    sev_counts = {a["severity"]: a["c"] for a in
                  Alert.objects.values("severity").annotate(c=Count("id"))}
    open_alerts = Alert.objects.filter(status__in=["New", "Investigating"]).count()
    last24 = Alert.objects.filter(timestamp__gte=now - timedelta(days=1)).count()
    prev7 = Alert.objects.filter(
        timestamp__gte=now - timedelta(days=8),
        timestamp__lt=now - timedelta(days=1)).count() / 7.0

    cases_open = AuditCase.objects.exclude(
        status__in=["Resolved", "Closed"]).count()
    cases_overdue = AuditCase.objects.filter(
        deadline__lt=now).exclude(status__in=["Resolved", "Closed"]).count()
    agents_active = RiskAgent.objects.filter(active=True).count()
    jobs_7d = ExcelImportJob.objects.filter(
        created_at__gte=now - timedelta(days=7)).count()

    insights = [
        {"title": f"{open_alerts} alertas por resolver",
         "detail": f"{sev_counts.get('Critical', 0)} críticos e "
                   f"{sev_counts.get('High', 0)} de alta severidade aguardam ação.",
         "tone": "danger" if sev_counts.get("Critical") else "info"},
        {"title": "Fluxo de transações",
         "detail": f"{_fmt_int(tx30_count)} transações nos últimos 30 dias, "
                   f"total {_fmt_money(tx30_sum)}.",
         "tone": "info"},
    ]
    if cases_overdue:
        insights.append(
            {"title": f"{cases_overdue} casos fora do prazo",
             "detail": "Casos com deadline vencida por resolver — risco de SLA.",
             "tone": "warn"})
    if prev7 > 0 and last24 > prev7 * 1.5:
        insights.append(
            {"title": "Pico de alertas nas últimas 24h",
             "detail": f"{last24} alertas vs média diária de {prev7:.1f} "
                       "na semana anterior.",
             "tone": "warn"})

    rows = [[s, _fmt_int(sev_counts.get(s, 0))] for s in SEV_ORDER]
    rows.append(["Total", _fmt_int(sum(sev_counts.values()))])
    summary = (
        f"**Panorama da plataforma**\n"
        f"- Transações: {_fmt_int(tx_total)} no total ({_fmt_money(tx_sum)}); "
        f"{_fmt_int(tx30_count)} nos últimos 30 dias ({_fmt_money(tx30_sum)})\n"
        f"- Alertas: {_fmt_int(sum(sev_counts.values()))} no total, "
        f"{_fmt_int(open_alerts)} por resolver "
        f"(Críticos: {_fmt_int(sev_counts.get('Critical', 0))}, "
        f"Altos: {_fmt_int(sev_counts.get('High', 0))})\n"
        f"- Casos: {_fmt_int(cases_open)} abertos, "
        f"{_fmt_int(cases_overdue)} fora do prazo\n"
        f"- Agentes IA: {_fmt_int(agents_active)} ativos · "
        f"Importações Excel (7d): {_fmt_int(jobs_7d)}")
    return {"tool": "overview", "title": "Panorama da plataforma",
            "summary": summary,
            "table": _table(["Severidade", "Alertas"], rows,
                            sum(sev_counts.values())),
            "insights": insights,
            "meta": {"tx_total": tx_total, "tx_sum": float(tx_sum),
                     "open_alerts": open_alerts, "cases_open": cases_open,
                     "cases_overdue": cases_overdue,
                     "agents_active": agents_active}}


def tool_query_alerts(f: dict) -> dict:
    qs = _alert_base_qs(f)
    total = qs.count()
    if total == 0:
        return {"tool": "alerts", "title": "Alertas",
                "summary": "Não encontrei alertas com esses critérios. "
                           "Tente alargar o período ou remover filtros.",
                "insights": [], "meta": {"total": 0}}
    agg = qs.aggregate(avg_mat=Avg("materiality"), total_amt=Sum("amount"))
    by_sev = {a["severity"]: a["c"] for a in
              qs.values("severity").annotate(c=Count("id"))}
    by_status = {a["status"]: a["c"] for a in
                 qs.values("status").annotate(c=Count("id"))}
    top_vendor = (qs.exclude(vendor__isnull=True).exclude(vendor="")
                  .values("vendor").annotate(c=Count("id"))
                  .order_by("-c").first())

    rows = [[a.id, a.vendor or "—", _fmt_money(a.amount),
             a.severity, a.status, f"{(a.materiality or 0) * 100:.0f}%",
             timezone.localtime(a.timestamp).strftime("%d/%m %H:%M")]
            for a in qs.order_by("-materiality", "-timestamp")
            [:TABLE_ROW_LIMIT]]

    scope = (f" ({f['severity']})" if f.get("severity") else "")
    if f.get("days"):
        scope += f" nos últimos {f['days']} dia(s)"
    if f.get("vendor"):
        scope += f" · fornecedor: {f['vendor']}"
    summary = (
        f"**Alertas{scope}** — {total} resultados, materialidade média "
        f"{(agg['avg_mat'] or 0) * 100:.0f}%.\n"
        f"- Por severidade: " + ", ".join(
            f"{s}: {_fmt_int(by_sev.get(s, 0))}" for s in SEV_ORDER
            if by_sev.get(s)) + "\n"
        f"- Por estado: " + ", ".join(
            f"{k}: {_fmt_int(v)}" for k, v in by_status.items()))
    if top_vendor:
        summary += f"\n- Fornecedor mais recorrente: **{top_vendor['vendor']}** " \
                   f"({_fmt_int(top_vendor['c'])} alertas)"
    insights = []
    if by_sev.get("Critical"):
        insights.append({"title": f"{by_sev['Critical']} alertas críticos",
                         "detail": "Recomenda-se criação de casos e triagem "
                                   "imediata destes alertas.", "tone": "danger"})
    top_fp = by_status.get("False Positive", 0)
    if total >= 10 and top_fp / total > 0.3:
        insights.append({"title": "Taxa de falsos positivos elevada",
                         "detail": f"{top_fp} de {total} alertas marcados como "
                                   "falso positivo — vale a pena afinar as "
                                   "regras/agentes.", "tone": "warn"})
    return {"tool": "alerts", "title": "Alertas filtrados", "summary": summary,
            "table": _table(["ID", "Fornecedor", "Valor", "Severidade",
                             "Estado", "Material.", "Data"], rows, total),
            "insights": insights,
            "meta": {"total": total, "by_severity": by_sev}}


def tool_query_transactions(f: dict) -> dict:
    qs = Transaction.objects.all()
    if f.get("vendor"):
        qs = qs.filter(vendor__icontains=f["vendor"])
    if f.get("category"):
        qs = qs.filter(category__icontains=f["category"])
    if f.get("min_amount") is not None:
        qs = qs.filter(amount__gte=f["min_amount"])
    if f.get("max_amount") is not None:
        qs = qs.filter(amount__lte=f["max_amount"])
    if f.get("days"):
        qs = qs.filter(timestamp__gte=timezone.now() - timedelta(days=f["days"]))
    total = qs.count()
    if total == 0:
        return {"tool": "transactions", "title": "Transações",
                "summary": "Não encontrei transações com esses critérios.",
                "insights": [], "meta": {"total": 0}}
    agg = qs.aggregate(total=Sum("amount"), avg=Avg("amount"),
                       mx=Sum("amount"))
    biggest = qs.order_by("-amount").first()
    top_n = f.get("top_n") or TABLE_ROW_LIMIT
    rows = [[t.transaction_id, t.vendor or "—", _fmt_money(t.amount, t.currency),
             t.category or "—", t.status,
             timezone.localtime(t.timestamp).strftime("%d/%m/%Y")]
            for t in qs.order_by("-amount")[:top_n]]
    by_cat = list(qs.exclude(category__isnull=True).exclude(category="")
                  .values("category").annotate(c=Count("id"),
                                               s=Sum("amount"))
                  .order_by("-s")[:5])
    scope = []
    if f.get("vendor"):
        scope.append(f"fornecedor: {f['vendor']}")
    if f.get("min_amount") is not None:
        scope.append(f"valor ≥ {_fmt_money(f['min_amount'])}")
    if f.get("max_amount") is not None:
        scope.append(f"valor ≤ {_fmt_money(f['max_amount'])}")
    if f.get("days"):
        scope.append(f"últimos {f['days']} dias")
    summary = (
        f"**Transações**" + (f" ({'; '.join(scope)})" if scope else "") +
        f" — {total} resultados, valor total {_fmt_money(agg['total'])}, "
        f"média {_fmt_money(agg['avg'])}.\n"
        f"- Maior transação: {_fmt_money(biggest.amount)} "
        f"({biggest.vendor or '—'})\n"
        + ("- Por categoria: " + ", ".join(
            f"{b['category']}: {_fmt_money(b['s'])} ({_fmt_int(b['c'])})"
            for b in by_cat) if by_cat else ""))
    insights = []
    if by_cat:
        share = (by_cat[0]["s"] / agg["total"] * 100) if agg["total"] else 0
        insights.append({"title": f"Top categoria: {by_cat[0]['category']}",
                         "detail": f"Representa {share:.0f}% do valor "
                                   f"({_fmt_money(by_cat[0]['s'])}).",
                         "tone": "info"})
    return {"tool": "transactions", "title": "Transações filtradas",
            "summary": summary,
            "table": _table(["ID", "Fornecedor", "Valor", "Categoria",
                             "Estado", "Data"], rows, total),
            "insights": insights,
            "meta": {"total": total, "sum": float(agg["total"] or 0)}}


def tool_query_cases(f: dict) -> dict:
    qs = AuditCase.objects.all()
    if f.get("case_status"):
        qs = qs.filter(status__iexact=f["case_status"])
    if f.get("priority"):
        qs = qs.filter(priority__iexact=f["priority"])
    now = timezone.now()
    overdue = f.get("overdue", False)
    if overdue:
        qs = qs.filter(deadline__lt=now).exclude(
            status__in=["Resolved", "Closed"])
    total = qs.count()
    if total == 0:
        msg = ("Não há casos fora do prazo — bom sinal de SLA."
               if overdue else "Não encontrei casos com esses critérios.")
        return {"tool": "cases", "title": "Casos", "summary": msg,
                "insights": [], "meta": {"total": 0}}
    by_status = {a["status"]: a["c"] for a in
                 qs.values("status").annotate(c=Count("id"))}
    by_prio = {a["priority"]: a["c"] for a in
               qs.values("priority").annotate(c=Count("id"))}
    rows = [[c.id, (c.title[:38] + "…") if len(c.title or "") > 38 else c.title,
             c.status, c.priority,
             timezone.localtime(c.deadline).strftime("%d/%m/%Y")
             if c.deadline else "—",
             c.assigned_to or "—"]
            for c in qs.order_by("deadline")[:TABLE_ROW_LIMIT]]
    summary = (
        f"**Casos** — {total} resultados.\n"
        f"- Por estado: " + ", ".join(f"{k}: {_fmt_int(v)}"
                                      for k, v in by_status.items()) + "\n"
        f"- Por prioridade: " + ", ".join(
            f"{p}: {_fmt_int(by_prio.get(p, 0))}" for p in
            ["Critical", "High", "Medium", "Low"] if by_prio.get(p)))
    insights = []
    next_case = qs.filter(deadline__gte=now).order_by("deadline").first()
    if next_case and next_case.deadline:
        days = (next_case.deadline - now).days
        insights.append({"title": "Próximo prazo",
                         "detail": f"Caso #{next_case.id} «{next_case.title}» "
                                   f"vence em {max(days, 0)} dia(s).",
                         "tone": "info" if days > 3 else "warn"})
    if by_prio.get("Critical"):
        insights.append({"title": f"{by_prio['Critical']} casos críticos",
                         "detail": "Priorize atribuição de responsáveis e "
                                   "planos de ação.", "tone": "danger"})
    return {"tool": "cases", "title": "Casos filtrados", "summary": summary,
            "table": _table(["ID", "Título", "Estado", "Prioridade",
                             "Prazo", "Responsável"], rows, total),
            "insights": insights,
            "meta": {"total": total, "by_status": by_status}}


def tool_sla_check(f: dict) -> dict:
    now = timezone.now()
    overdue_cases = AuditCase.objects.filter(
        deadline__lt=now).exclude(status__in=["Resolved", "Closed"])
    n_overdue = overdue_cases.count()
    stale_alerts = Alert.objects.filter(
        status="New", timestamp__lt=now - timedelta(days=2))
    n_stale = stale_alerts.count()
    oldest = overdue_cases.order_by("deadline").first()
    rows = [[c.id, (c.title[:34] + "…") if len(c.title or "") > 34 else c.title,
             c.priority,
             timezone.localtime(c.deadline).strftime("%d/%m/%Y")
             if c.deadline else "—",
             c.assigned_to or "—"]
            for c in overdue_cases.order_by("deadline")[:TABLE_ROW_LIMIT]]
    summary = (
        f"**Saúde de SLA**\n"
        f"- Casos fora do prazo: **{_fmt_int(n_overdue)}**\n"
        f"- Alertas «Novos» há mais de 48h sem triagem: "
        f"**{_fmt_int(n_stale)}**")
    if oldest and oldest.deadline:
        late = (now - oldest.deadline).days
        summary += f"\n- Caso mais antigo em atraso: #{oldest.id} " \
                   f"({late} dia(s) além do prazo)"
    insights = []
    if n_overdue:
        insights.append({"title": f"{n_overdue} casos em violação de SLA",
                         "detail": "Reatribuir ou renegociar prazos com os "
                                   "responsáveis.", "tone": "danger"})
    if n_stale:
        insights.append({"title": f"{n_stale} alertas sem primeira resposta",
                         "detail": "Alertas novos há mais de 2 dias — risco de "
                                   "deteção tardia.", "tone": "warn"})
    if not insights:
        insights.append({"title": "SLA saudável",
                         "detail": "Sem violações detetadas neste momento.",
                         "tone": "success"})
    return {"tool": "sla", "title": "SLA & prazos", "summary": summary,
            "table": _table(["ID", "Caso", "Prioridade", "Prazo",
                             "Responsável"], rows, n_overdue),
            "insights": insights,
            "meta": {"overdue_cases": n_overdue, "stale_alerts": n_stale}}


def tool_agents_status(f: dict) -> dict:
    agents = list(RiskAgent.objects.all().order_by("-reputation_score"))
    if not agents:
        return {"tool": "agents", "title": "Agentes IA",
                "summary": "Ainda não existem agentes de risco configurados. "
                           "Crie o primeiro em /agents.",
                "insights": [], "meta": {"total": 0}}
    active = [a for a in agents if a.active]
    avg_rep = (sum(a.reputation_score for a in active) / len(active)) if active else 0
    best, worst = agents[0], min(agents, key=lambda a: a.reputation_score)
    rows = [[a.name, a.specialization, a.active and "✅ Ativo" or "⏸ Inativo",
             f"{a.reputation_score:.2f}",
             timezone.localtime(a.last_triggered).strftime("%d/%m %H:%M")
             if a.last_triggered else "—"]
            for a in agents[:TABLE_ROW_LIMIT]]
    summary = (
        f"**Agentes IA de risco** — {_fmt_int(len(agents))} no total, "
        f"{_fmt_int(len(active))} ativos, reputação média {avg_rep:.2f}.\n"
        f"- Melhor reputação: **{best.name}** ({best.reputation_score:.2f})\n"
        f"- Pior reputação: **{worst.name}** ({worst.reputation_score:.2f}) — "
        f"considere rever condições ou treino.")
    insights = []
    if worst.reputation_score < 0.8:
        insights.append({"title": f"Agente «{worst.name}» com reputação baixa",
                         "detail": "Reputação reflete feedback dos auditores — "
                                   "revise as condições do agente.",
                         "tone": "warn"})
    idle = [a for a in active if not a.last_triggered]
    if idle:
        insights.append({"title": f"{len(idle)} agentes nunca executados",
                         "detail": "Agentes ativos sem registos de execução — "
                                   "verifique se as condições fazem match.",
                         "tone": "info"})
    return {"tool": "agents", "title": "Agentes IA", "summary": summary,
            "table": _table(["Agente", "Especialidade", "Estado",
                             "Reputação", "Última execução"], rows,
                            len(agents)),
            "insights": insights,
            "meta": {"total": len(agents), "active": len(active)}}


def tool_excel_imports(f: dict) -> dict:
    qs = ExcelImportJob.objects.all()
    if f.get("days"):
        qs = qs.filter(created_at__gte=timezone.now() - timedelta(days=f["days"]))
    total = qs.count()
    jobs = qs[:TABLE_ROW_LIMIT]
    rows_ok = sum(j.rows_imported for j in qs)
    rows_skip = sum(j.rows_skipped for j in qs)
    failed = qs.filter(status="Failed").count()
    rows = [[j.id, j.file_name[:40], j.status, _fmt_int(j.rows_imported),
             _fmt_int(j.rows_skipped),
             timezone.localtime(j.created_at).strftime("%d/%m %H:%M")]
            for j in jobs]
    summary = (
        f"**Importações Excel/CSV** — {total} job(s) registado(s), "
        f"{_fmt_int(rows_ok)} linhas importadas, {_fmt_int(rows_skip)} ignoradas.\n"
        f"- Falhadas: {_fmt_int(failed)} · No Excel Studio pode importar, "
        f"analisar, reconciliar e pedir fórmulas ao Copiloto IA.")
    insights = []
    if failed:
        insights.append({"title": f"{failed} importações falhadas",
                         "detail": "Verifique o mapeamento de colunas e o "
                                   "formato dos ficheiros.", "tone": "warn"})
    insights.append({"title": "Copiloto Excel disponível",
                     "detail": "No Excel Studio, carregue um ficheiro e pergunte "
                               "em linguagem natural: transforma, filtra, gera "
                               "fórmulas PT/EN e workbook com KPIs vivos.",
                     "tone": "info"})
    return {"tool": "excel", "title": "Excel Studio — importações",
            "summary": summary,
            "table": _table(["ID", "Ficheiro", "Estado", "Linhas",
                             "Ignoradas", "Data"], rows, total),
            "insights": insights,
            "meta": {"total": total, "rows_imported": rows_ok}}


def _transactions_frame(limit: int = 20000):
    import pandas as pd
    qs = (Transaction.objects
          .order_by("-timestamp").values("transaction_id", "vendor", "amount",
                                         "currency", "timestamp", "category",
                                         "status", "user_id")[:limit])
    df = pd.DataFrame(list(qs))
    if not df.empty:
        df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
        df["timestamp"] = df["timestamp"].dt.tz_localize(None)
    return df


def tool_benford_check(f: dict) -> dict:
    from .excel_service import benford_analysis
    df = _transactions_frame()
    if df.empty:
        return {"tool": "benford", "title": "Benford (BD)",
                "summary": "Não há transações na base de dados para aplicar "
                           "a Lei de Benford. Importe dados no Excel Studio.",
                "insights": [], "meta": {}}
    result = benford_analysis(df["amount"])
    if not result.get("applicable"):
        return {"tool": "benford", "title": "Benford (BD)",
                "summary": f"Ainda não é possível aplicar Benford: "
                           f"{result.get('reason', 'amostra insuficiente')}. "
                           "Importe mais transações (mínimo 50).",
                "insights": [], "meta": result}
    tone = "danger" if "Não conformidade" in result.get("verdict", "") else \
        ("warn" if "moderada" in result.get("verdict", "").lower() else "success")
    return {"tool": "benford", "title": "Lei de Benford (base de dados)",
            "summary": (f"**Benford sobre {_fmt_int(result['n'])} transações**\n"
                        f"- MAD: **{result['mad']:.4f}** → *{result['verdict']}*\n"
                        f"- Dígitos mais desviados: "
                        f"{', '.join(map(str, result['attention_digits']))}\n"
                        f"- {result['insight']}"),
            "insights": [{"title": f"Veredicto: {result['verdict']}",
                          "detail": "Desvios no 1º dígito podem indicar valores "
                                    "fabricados — use amostragem direcionada.",
                          "tone": tone}],
            "meta": {"mad": result["mad"], "verdict": result["verdict"]}}


def tool_find_duplicates(f: dict) -> dict:
    from .excel_service import fuzzy_duplicates
    df = _transactions_frame()
    if df.empty:
        return {"tool": "duplicates", "title": "Duplicados (BD)",
                "summary": "Sem transações na base de dados para detetar "
                           "duplicados.", "insights": [], "meta": {}}
    result = fuzzy_duplicates(df)
    exact, fuzzy = result.get("exact", []), result.get("fuzzy", [])
    total_suspect = sum(g["count"] for g in exact) + sum(g["count"] for g in fuzzy)
    rows = [[g["vendor"], _fmt_money(g["amount"]), _fmt_int(g["count"]),
             _fmt_money(g["total"])] for g in (exact + fuzzy)[:TABLE_ROW_LIMIT]]
    summary = (
        f"**Duplicados na base de dados**\n"
        f"- Grupos exatos (fornecedor+valor): **{len(exact)}**\n"
        f"- Grupos fuzzy (fornecedores quase idênticos): **{len(fuzzy)}**\n"
        f"- Transações suspeitas no total: **{_fmt_int(total_suspect)}**")
    insights = []
    if exact or fuzzy:
        biggest = max(exact + fuzzy, key=lambda g: g.get("total", 0)) \
            if (exact or fuzzy) else None
        if biggest:
            insights.append({"title": "Maior grupo duplicado",
                             "detail": f"{biggest['vendor']}: "
                                       f"{_fmt_money(biggest['total'])} em "
                                       f"{biggest['count']} ocorrências.",
                             "tone": "danger"})
        insights.append({"title": "Próximo passo",
                         "detail": "Abra o Excel Studio → Análise para rever "
                                   "os duplicados em detalhe e criar casos.",
                         "tone": "info"})
    else:
        insights.append({"title": "Sem duplicados",
                         "detail": "Nenhum padrão duplicado detetado na "
                                   "amostra recente.", "tone": "success"})
    return {"tool": "duplicates", "title": "Duplicados (BD)",
            "summary": summary,
            "table": _table(["Fornecedor", "Valor", "Ocorrências", "Total"],
                            rows, len(exact) + len(fuzzy)),
            "insights": insights,
            "meta": {"exact_groups": len(exact), "fuzzy_groups": len(fuzzy)}}


def tool_risk_forecast(f: dict) -> dict:
    now = timezone.now()
    counts = []
    for i in range(14):
        start = now - timedelta(days=13 - i)
        end = start + timedelta(days=1)
        counts.append(Alert.objects.filter(
            timestamp__gte=start, timestamp__lt=end).count())
    last7 = sum(counts[-7:]) / 7.0
    prev7 = sum(counts[:7]) / 7.0 or 0
    slope = (counts[-1] - counts[0]) / 13 if len(counts) > 1 else 0
    proj = [max(0, round(counts[-1] + slope * (i + 1))) for i in range(3)]
    trend = "estável"
    if prev7 > 0:
        delta = (last7 - prev7) / prev7 * 100
        trend = f"{'alta' if delta > 10 else 'baixa' if delta < -10 else 'estável'} ({delta:+.0f}%)"
    rows = [[(now - timedelta(days=13 - i)).strftime("%d/%m"),
             counts[i]] for i in range(14)]
    last7_s = f"{last7:.1f}".replace(".", ",")
    prev7_s = f"{prev7:.1f}".replace(".", ",")
    summary = (
        f"**Previsão de risco (alertas/dia)**\n"
        f"- Média últimos 7 dias: **{last7_s}** vs 7 anteriores "
        f"**{prev7_s}** → tendência de **{trend}**\n"
        f"- Projeção próximos 3 dias: {proj[0]}, {proj[1]}, {proj[2]} "
        f"alertas (regressão linear simples)")
    insights = []
    if "alta" in trend:
        insights.append({"title": "Risco em subida",
                         "detail": "Considere ativar/rever agentes e reforçar "
                                   "triagem nas próximas 72h.", "tone": "warn"})
    elif "baixa" in trend:
        insights.append({"title": "Risco em descida",
                         "detail": "Bom momento para limpar backlog de casos "
                                   "antigos.", "tone": "success"})
    return {"tool": "forecast", "title": "Previsão de risco",
            "summary": summary,
            "table": _table(["Dia", "Alertas"], rows, 14),
            "insights": insights,
            "meta": {"last7_avg": round(last7, 1), "trend": trend,
                     "projection_3d": proj}}


def tool_vendor_profile(f: dict) -> dict:
    vendor = (f.get("vendor") or "").strip()
    if not vendor:
        return {"tool": "vendor", "title": "Perfil de fornecedor",
                "summary": "Indique o nome do fornecedor, por exemplo: "
                           "«perfil do fornecedor Acme».",
                "insights": [], "meta": {}}
    tx_qs = Transaction.objects.filter(vendor__icontains=vendor)
    al_qs = Alert.objects.filter(vendor__icontains=vendor)
    n_tx, n_alerts = tx_qs.count(), al_qs.count()
    if n_tx == 0 and n_alerts == 0:
        return {"tool": "vendor", "title": f"Perfil: {vendor}",
                "summary": f"Não encontrei dados do fornecedor «{vendor}» "
                           "na plataforma.", "insights": [], "meta": {}}
    agg = tx_qs.aggregate(total=Sum("amount"), avg=Avg("amount"))
    sev = {a["severity"]: a["c"] for a in
           al_qs.values("severity").annotate(c=Count("id"))}
    last_tx = tx_qs.order_by("-timestamp").first()
    # últimos 6 meses (volume mensal)
    months, now = {}, timezone.now()
    for i in range(5, -1, -1):
        m0 = (now - timedelta(days=30 * i)).replace(day=1)
        months[m0.strftime("%Y-%m")] = 0
    for t in tx_qs.filter(timestamp__gte=now - timedelta(days=183)):
        key = timezone.localtime(t.timestamp).strftime("%Y-%m")
        if key in months:
            months[key] += 1
    rows = [[k, _fmt_int(v)] for k, v in months.items()]
    sev_line = ", ".join(f"{s}: {_fmt_int(sev.get(s, 0))}"
                         for s in SEV_ORDER if sev.get(s)) or "sem alertas"
    summary = (
        f"**Perfil do fornecedor «{vendor}»**\n"
        f"- Transações: {_fmt_int(n_tx)} · valor total "
        f"{_fmt_money(agg['total'])} · média {_fmt_money(agg['avg'])}\n"
        f"- Alertas: {_fmt_int(n_alerts)} ({sev_line})\n"
        + (f"- Última transação: "
           f"{timezone.localtime(last_tx.timestamp).strftime('%d/%m/%Y')} · "
           f"{_fmt_money(last_tx.amount)}" if last_tx else ""))
    insights = []
    if sev.get("Critical") or sev.get("High"):
        insights.append({"title": "Fornecedor de risco",
                         "detail": f"{sev.get('Critical', 0) + sev.get('High', 0)} "
                                   "alertas de severidade crítica/alta associados "
                                   "a este fornecedor.", "tone": "danger"})
    dup_check = None
    if n_tx >= 2:
        import pandas as pd
        from .excel_service import fuzzy_duplicates
        df = pd.DataFrame(list(tx_qs.order_by("-timestamp")
                               .values("transaction_id", "vendor", "amount",
                                       "currency", "timestamp", "category",
                                       "status", "user_id")[:5000]))
        if not df.empty:
            df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
            dup_check = fuzzy_duplicates(df)
        n_dups = (len(dup_check.get("exact", [])) if dup_check else 0)
        if n_dups:
            insights.append({"title": f"{n_dups} padrões duplicados",
                             "detail": "Transações com mesmo fornecedor e valor "
                                       "repetido — possível pagamento em "
                                       "duplicado.", "tone": "warn"})
    return {"tool": "vendor", "title": f"Perfil: {vendor}", "summary": summary,
            "table": _table(["Mês", "Transações"], rows, sum(months.values())),
            "insights": insights,
            "meta": {"vendor": vendor, "tx": n_tx, "alerts": n_alerts}}


def tool_help(f: dict) -> dict:
    """Meta-suporte: o copiloto explica as próprias capacidades.
    Um modelo de suporte de classe mundial tem de saber apresentar-se."""
    summary = (
        "**Sou o Copiloto Global — conheço TODA a plataforma em tempo real.**\n"
        "Pergunte em linguagem natural (PT ou EN); respondo com números "
        "concretos e levo-o para onde precisa:\n"
        "- **Panorama & KPIs** — «resumo da plataforma», «kpi de alertas»\n"
        "- **Alertas** — «alertas críticos dos últimos 7 dias», "
        "«alertas falsos positivos», «top alertas maior que 10.000»\n"
        "- **Explicabilidade** — «explica o alerta 42», «porque foi gerado "
        "o alerta mais recente», «detalha o caso 7»\n"
        "- **Transações** — «top 10 transações por valor», "
        "«transações maior que 5.000»\n"
        "- **Casos & SLA** — «casos fora do prazo», «casos em progresso»\n"
        "- **Agentes IA** — «como estão os agentes?»\n"
        "- **Excel Studio** — «importações de excel», e no Excel Studio o "
        "Copiloto IA transforma ficheiros e sugere fórmulas PT/EN\n"
        "- **Forense** — «aplica a lei de benford», «deteta duplicados»\n"
        "- **Previsões & tendências** — «previsão de risco», «compara esta "
        "semana com a semana passada»\n"
        "- **Fornecedores** — «perfil do fornecedor Acme»\n"
        "- **Briefing executivo** — botão **Briefing** aqui no painel")
    insights = [
        {"title": "Consciência de contexto",
         "detail": "Se estiver numa página (ex.: SLA) e fizer uma pergunta "
                   "vaga como «e agora?», respondo sobre essa página.",
         "tone": "info"},
        {"title": "Ações navegáveis",
         "detail": "Cada resposta traz botões que o levam diretamente à "
                   "página certa — sem procurar menus.",
         "tone": "success"},
    ]
    rows = [["Alertas", "severidade, estado, fornecedor, período, valor"],
            ["Explicabilidade", "ID do alerta/caso ou «o mais recente»"],
            ["Transações", "top N, valor mín/máx, categoria, período"],
            ["Casos & SLA", "estado, prioridade, atrasos, prazos"],
            ["Forense", "Benford, duplicados exatos e fuzzy"],
            ["Previsões", "regressão 14 dias + projeção 3 dias"],
            ["Tendências", "semana vs semana, evolução diária"],
            ["Excel", "importações, Copiloto IA de fórmulas"]]
    return {"tool": "help", "title": "Capacidades do Copiloto",
            "summary": summary,
            "table": _table(["Domínio", "Exemplos de perguntas"], rows, len(rows)),
            "insights": insights,
            "meta": {"capabilities": 10}}


def tool_explain(f: dict) -> dict:
    """Explicabilidade profunda: PORQUE é que este alerta/caso existe.
    Junta o alerta + transação associada + regras/agentes compatíveis +
    histórico do fornecedor + próximos passos recomendados."""
    alert_id, case_id = f.get("alert_id"), f.get("case_id")
    if not alert_id and f.get("latest_alert"):
        latest = Alert.objects.order_by("-timestamp", "-id").first()
        alert_id = latest.id if latest else None
    if not case_id and f.get("latest_case"):
        latest = AuditCase.objects.order_by("-created_at", "-id").first()
        case_id = latest.id if latest else None

    if alert_id:
        alert = Alert.objects.filter(id=alert_id).first()
        if not alert:
            return {"tool": "explain", "title": f"Alerta #{alert_id}",
                    "summary": f"Não encontrei o alerta #{alert_id}. "
                               "Verifique o ID — por exemplo: «explica o "
                               "alerta 42» ou «explica o alerta mais recente».",
                    "insights": [], "meta": {"found": False}}
        return _explain_alert(alert)
    if case_id:
        case = AuditCase.objects.filter(id=case_id).first()
        if not case:
            return {"tool": "explain", "title": f"Caso #{case_id}",
                    "summary": f"Não encontrei o caso #{case_id}. "
                               "Verifique o ID — por exemplo: «detalha o "
                               "caso 7» ou «explica o caso mais recente».",
                    "insights": [], "meta": {"found": False}}
        return _explain_case(case)
    return {"tool": "explain", "title": "Explicabilidade",
            "summary": "Posso explicar a origem de qualquer alerta ou caso.\n"
                       "- «explica o alerta 42»\n"
                       "- «porque foi gerado o alerta mais recente»\n"
                       "- «detalha o caso 7»",
            "insights": [], "meta": {}}


def _explain_alert(alert: Alert) -> dict:
    now = timezone.now()
    tx = alert.transaction
    vendor_alerts = Alert.objects.filter(vendor=alert.vendor).exclude(id=alert.id)
    n_vendor_alerts = vendor_alerts.count()
    vendor_critical = vendor_alerts.filter(
        severity__in=["Critical", "High"]).count()

    linhas = [f"**Alerta #{alert.id} — {alert.alert_type}** "
              f"({alert.severity}, {alert.status}, "
              f"{timezone.localtime(alert.timestamp).strftime('%d/%m/%Y %H:%M')})"]
    if alert.description:
        linhas.append(f"- Descrição: {alert.description[:200]}")
    if alert.amount is not None:
        linhas.append(f"- Valor: {_fmt_money(alert.amount)} · "
                      f"materialidade {(alert.materiality or 0) * 100:.0f}%")
    if alert.vendor:
        linhas.append(f"- Fornecedor: {alert.vendor}")
    if tx:
        linhas.append(f"- Transação associada: **{tx.transaction_id}** "
                      f"({_fmt_money(tx.amount, tx.currency)}, "
                      f"{tx.category or 'sem categoria'}, {tx.status}, "
                      f"{timezone.localtime(tx.timestamp).strftime('%d/%m/%Y')})")
        xai = tx.xai_explanation if isinstance(tx.xai_explanation, dict) else None
        if xai:
            reasons = xai.get("reasons") or xai.get("factors") or []
            if isinstance(reasons, list) and reasons:
                linhas.append("- Fatores de risco da transação: "
                              + "; ".join(str(r)[:90] for r in reasons[:3]))
    else:
        linhas.append("- Sem transação associada (alerta gerado diretamente).")

    # agentes cuja especialização/action se relaciona com o tipo de alerta
    tipo_tokens = re.split(r"[\s_\-]+", strip_accents(alert.alert_type or "").lower())
    ag_matches = [a for a in RiskAgent.objects.filter(active=True)
                  if any(tok and tok in strip_accents(a.specialization).lower()
                         or tok in strip_accents(a.name).lower()
                         for tok in tipo_tokens)]
    if ag_matches:
        linhas.append("- Agentes ativos compatíveis: "
                      + ", ".join(a.name for a in ag_matches[:3]))

    steps = []
    if alert.status in ("New", "Investigating"):
        steps.append("Triar o alerta e registar a conclusão da análise")
    if alert.severity in ("Critical", "High"):
        steps.append("Criar caso de auditoria com prioridade " + alert.severity)
    if vendor_critical:
        steps.append(f"Avaliar padrão do fornecedor ({vendor_critical} "
                     "alertas graves no histórico)")
    if tx and tx.status == "Approved" and alert.severity == "Critical":
        steps.append("Considerar suspensão temporária de pagamentos a este "
                     "fornecedor enquanto investiga")

    insights = []
    if n_vendor_alerts >= 3:
        insights.append({"title": f"Padrão recorrente: {alert.vendor}",
                         "detail": f"{n_vendor_alerts} outros alertas para o "
                                   "mesmo fornecedor — não é um episódio "
                                   "isolado.", "tone": "danger"
                         if vendor_critical else "warn"})
    if (alert.materiality or 0) >= 0.8:
        insights.append({"title": "Materialidade elevada",
                         "detail": f"Impacto potencial de "
                                   f"{(alert.materiality or 0) * 100:.0f}% — "
                                   "priorize esta triagem.",
                         "tone": "danger"})
    if alert.status == "New":
        age_days = (now - alert.timestamp).days
        if age_days >= 2:
            insights.append({"title": "Alerta envelhecido sem triagem",
                             "detail": f"{age_days} dia(s) no estado «New» — "
                                       "risco de violação de SLA.",
                             "tone": "warn"})
    if steps:
        insights.append({"title": "Próximos passos recomendados",
                         "detail": " · ".join(steps[:3]), "tone": "info"})

    rows = []
    if tx:
        rows = [[tx.transaction_id, tx.vendor or "—",
                 _fmt_money(tx.amount, tx.currency), tx.category or "—",
                 tx.status,
                 timezone.localtime(tx.timestamp).strftime("%d/%m/%Y")]]
    return {"tool": "explain", "title": f"Porquê do alerta #{alert.id}",
            "summary": "\n".join(linhas),
            "table": _table(["Transação", "Fornecedor", "Valor", "Categoria",
                             "Estado", "Data"], rows, len(rows)),
            "insights": insights,
            "meta": {"alert_id": alert.id, "vendor": alert.vendor or "",
                     "vendor_alerts": n_vendor_alerts,
                     "agents_matched": [a.name for a in ag_matches[:3]]}}


def _explain_case(case: AuditCase) -> dict:
    now = timezone.now()
    linhas = [f"**Caso #{case.id} — {case.title}** "
              f"({case.status}, prioridade {case.priority})"]
    if case.description:
        linhas.append(f"- Descrição: {case.description[:220]}")
    if case.finding_type:
        linhas.append(f"- Tipo de achado: {case.finding_type}")
    linhas.append(f"- Criado por {case.created_by} em "
                  f"{timezone.localtime(case.created_at).strftime('%d/%m/%Y')}"
                  + (f" · atribuído a {case.assigned_to}"
                     if case.assigned_to else " · sem responsável atribuído"))
    if case.deadline:
        delta = (case.deadline - now).days
        prazo_txt = (f"FORA DO PRAZO há {-delta} dia(s)" if delta < 0
                     else f"{delta} dia(s) restantes")
        linhas.append(f"- Prazo: "
                      f"{timezone.localtime(case.deadline).strftime('%d/%m/%Y')} "
                      f"({prazo_txt})")
    if case.inherent_risk is not None or case.residual_risk is not None:
        linhas.append(f"- Risco inerente: "
                      f"{(case.inherent_risk or 0) * 100:.0f}% · residual: "
                      f"{(case.residual_risk or 0) * 100:.0f}%")
    if case.action_plan:
        linhas.append(f"- Plano de ação: {case.action_plan[:180]}")

    # alertas/transação relacionadas
    tx = (Transaction.objects.filter(
        transaction_id=case.transaction_id).first()
        if case.transaction_id else None)
    related_alerts = []
    if tx:
        related_alerts = list(Alert.objects.filter(transaction=tx)[:5])
    if not related_alerts and tx and tx.vendor:
        related_alerts = list(Alert.objects.filter(
            vendor=tx.vendor).order_by("-timestamp")[:5])
    if related_alerts:
        linhas.append(f"- Alertas relacionados: "
                      + ", ".join(f"#{a.id} ({a.severity})"
                                  for a in related_alerts[:4]))

    insights = []
    if case.deadline and case.deadline < now and \
            case.status not in ("Resolved", "Closed"):
        insights.append({"title": "Caso fora do prazo",
                         "detail": "Reatribuir ou renegociar o prazo com o "
                                   "responsável — violação de SLA ativa.",
                         "tone": "danger"})
    if not case.assigned_to:
        insights.append({"title": "Sem responsável atribuído",
                         "detail": "Casos sem owner tendem a estagnar — "
                                   "atribua um responsável hoje.",
                         "tone": "warn"})
    if case.residual_risk is not None and case.residual_risk >= 0.7:
        insights.append({"title": "Risco residual elevado",
                         "detail": f"{case.residual_risk * 100:.0f}% mesmo "
                                   "após controlos — considere ação "
                                   "estrutural.", "tone": "danger"})
    rows = [[a.id, a.vendor or "—", _fmt_money(a.amount), a.severity, a.status]
            for a in related_alerts]
    return {"tool": "explain", "title": f"Porquê do caso #{case.id}",
            "summary": "\n".join(linhas),
            "table": _table(["Alerta", "Fornecedor", "Valor", "Severidade",
                             "Estado"], rows, len(rows)),
            "insights": insights,
            "meta": {"case_id": case.id, "related_alerts": len(related_alerts)}}


def tool_trends(f: dict) -> dict:
    """Tendências comparativas: esta semana vs semana passada + série diária."""
    now = timezone.now()
    start_this = now - timedelta(days=7)
    start_prev = now - timedelta(days=14)

    a_this = Alert.objects.filter(timestamp__gte=start_this).count()
    a_prev = Alert.objects.filter(timestamp__gte=start_prev,
                                  timestamp__lt=start_this).count()
    t_this = Transaction.objects.filter(timestamp__gte=start_this)
    t_prev = Transaction.objects.filter(timestamp__gte=start_prev,
                                        timestamp__lt=start_this)
    tx_this_c, tx_prev_c = t_this.count(), t_prev.count()
    tx_this_s = float(t_this.aggregate(s=Sum("amount"))["s"] or 0)
    tx_prev_s = float(t_prev.aggregate(s=Sum("amount"))["s"] or 0)

    def _delta(cur, prev):
        if prev:
            return f"{(cur - prev) / prev * 100:+.0f}%"
        return "—" if not cur else "+100%"

    # série diária de 14 dias (alertas + transações)
    rows = []
    peak_day, peak_n = "—", -1
    for i in range(13, -1, -1):
        d0 = (now - timedelta(days=i)).replace(hour=0, minute=0,
                                               second=0, microsecond=0)
        d1 = d0 + timedelta(days=1)
        na = Alert.objects.filter(timestamp__gte=d0, timestamp__lt=d1).count()
        nt = Transaction.objects.filter(timestamp__gte=d0,
                                        timestamp__lt=d1).count()
        label = d0.strftime("%d/%m")
        if na > peak_n:
            peak_day, peak_n = label, na
        rows.append([label, na, nt, _fmt_money(
            Transaction.objects.filter(timestamp__gte=d0,
                                       timestamp__lt=d1)
            .aggregate(s=Sum("amount"))["s"] or 0)])

    summary = (
        f"**Tendências — esta semana vs semana passada**\n"
        f"- Alertas: **{a_this}** vs {a_prev} ({_delta(a_this, a_prev)})\n"
        f"- Transações: **{tx_this_c}** vs {tx_prev_c} "
        f"({_delta(tx_this_c, tx_prev_c)}) · valor {_fmt_money(tx_this_s)} "
        f"vs {_fmt_money(tx_prev_s)} ({_delta(float(tx_this_s), float(tx_prev_s))})\n"
        f"- Dia de pico de alertas: **{peak_day}** ({peak_n} alertas)")
    insights = []
    if a_prev and a_this > a_prev * 1.25:
        insights.append({"title": "Alertas em aceleração",
                         "detail": f"{_delta(a_this, a_prev)} semana a semana — "
                                   "valide se algum agente novo está a gerar "
                                   "ruído ou se o risco subiu mesmo.",
                         "tone": "warn"})
    elif a_prev and a_this < a_prev * 0.75:
        insights.append({"title": "Alertas em queda",
                         "detail": f"{_delta(a_this, a_prev)} — bom momento "
                                   "para limpar o backlog de casos.",
                         "tone": "success"})
    if tx_prev_s and tx_this_s > tx_prev_s * 1.3:
        insights.append({"title": "Volume financeiro a subir",
                         "detail": f"{_delta(float(tx_this_s), float(tx_prev_s))} "
                                   "em valor transacionado — amostragem de "
                                   "controlo recomendada.", "tone": "info"})
    return {"tool": "trends", "title": "Tendências (14 dias)",
            "summary": summary,
            "table": _table(["Dia", "Alertas", "Transações", "Valor"], rows, 14),
            "insights": insights,
            "meta": {"alerts_this": a_this, "alerts_prev": a_prev,
                     "tx_this": tx_this_c, "tx_prev": tx_prev_c,
                     "peak_day": peak_day}}


TOOL_FUNCS = {
    "overview": tool_overview,
    "alerts": tool_query_alerts,
    "transactions": tool_query_transactions,
    "cases": tool_query_cases,
    "sla": tool_sla_check,
    "agents": tool_agents_status,
    "excel": tool_excel_imports,
    "benford": tool_benford_check,
    "duplicates": tool_find_duplicates,
    "forecast": tool_risk_forecast,
    "vendor": tool_vendor_profile,
    "help": tool_help,
    "explain": tool_explain,
    "trends": tool_trends,
}


def run_tools(tool_names: list, question: str) -> list:
    f = extract_filters(question)
    results = []
    for name in tool_names:
        fn = TOOL_FUNCS.get(name)
        if not fn:
            continue
        try:
            results.append(fn(f))
        except Exception as e:  # tool nunca derruba o chat
            logger.warning("copilot tool %s falhou: %s", name, e)
            results.append({"tool": name, "title": name,
                            "summary": "Não foi possível obter estes dados "
                                       "agora. Tente novamente em instantes.",
                            "insights": [], "meta": {}})
    return results


# ---------------------------------------------------------------------------
# 3. AÇÕES determinísticas por tool (fallback e enriquecimento)
# ---------------------------------------------------------------------------

_TOOL_ACTIONS = {
    "overview": [{"label": "Ver alertas", "href": "/alerts"},
                 {"label": "Abrir casos", "href": "/cases"},
                 {"label": "Excel Studio", "href": "/excel"}],
    "alerts": [{"label": "Abrir Riscos", "href": "/alerts"}],
    "transactions": [{"label": "Inspeção de transações", "href": "/transactions"}],
    "cases": [{"label": "Abrir Casos", "href": "/cases"}],
    "sla": [{"label": "Painel de SLA", "href": "/sla"}],
    "agents": [{"label": "Gerir agentes", "href": "/agents"}],
    "excel": [{"label": "Abrir Excel Studio", "href": "/excel"}],
    "benford": [{"label": "Análise no Excel Studio", "href": "/excel"}],
    "duplicates": [{"label": "Análise no Excel Studio", "href": "/excel"}],
    "forecast": [{"label": "Ver previsão no painel", "href": "/"}],
    "vendor": [{"label": "Inspeção de transações", "href": "/transactions"}],
    "help": [{"label": "Excel Studio", "href": "/excel"},
             {"label": "Painel inicial", "href": "/"}],
    "explain": [{"label": "Abrir Riscos", "href": "/alerts"},
                {"label": "Abrir Casos", "href": "/cases"}],
    "trends": [{"label": "Ver previsão no painel", "href": "/"},
               {"label": "Abrir Riscos", "href": "/alerts"}],
}


def _followups_for(tool_names: list) -> list:
    pool = {
        "overview": ["Quais os alertas críticos de hoje?",
                     "Como está o SLA dos casos?"],
        "alerts": ["Mostra alertas dos últimos 7 dias",
                   "Deteta duplicados na base de dados"],
        "transactions": ["Top 10 transações por valor",
                         "Perfil do fornecedor com mais alertas"],
        "cases": ["Casos fora do prazo", "Casos críticos abertos"],
        "sla": ["Casos fora do prazo", "Resumo da plataforma"],
        "agents": ["Previsão de risco para os próximos dias"],
        "excel": ["Como importo e analiso um ficheiro Excel?",
                  "Que fórmulas tornam o ficheiro automático?"],
        "benford": ["Deteta duplicados na base de dados",
                    "Análise completa no Excel Studio"],
        "duplicates": ["Aplica a Lei de Benford", "Abrir análise no Excel"],
        "forecast": ["Resumo da plataforma", "Alertas críticos de hoje"],
        "vendor": ["Alertas críticos deste fornecedor",
                   "Deteta duplicados na base de dados"],
        "help": ["Explica o alerta mais recente",
                 "Compara esta semana com a semana passada",
                 "Que análises o Excel Studio faz?"],
        "explain": ["Criar caso a partir deste alerta",
                    "Alertas críticos de hoje"],
        "trends": ["Previsão de risco para os próximos dias",
                   "Resumo da plataforma"],
    }
    out = []
    for t in tool_names:
        for fu in pool.get(t, []):
            if fu not in out:
                out.append(fu)
    return out[:4]


# ---------------------------------------------------------------------------
# 4. SÍNTESE LLM (opcional) — JSON estrito + whitelist de ações
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """Você é o Copiloto Global de uma plataforma de auditoria inteligente (alertas de risco, transações, casos, agentes IA, Excel Studio). Recebe resultados de ferramentas internas com dados vivos e a pergunta do utilizador. Responda SEMPRE em português de Portugal.

Responda APENAS com um objeto JSON válido (sem texto antes ou depois):
{"answer": "resposta direta em markdown simples (máx. 180 palavras), citando números concretos dos dados",
 "insights": [{"title": "título curto", "detail": "explicação", "tone": "info|warn|danger|success"}],
 "actions": [{"label": "texto do botão", "href": "/rota"}],
 "followups": ["próxima pergunta sugerida"]}

Regras: NÃO invente dados — use apenas os fornecidos; href deve ser uma das rotas permitidas; máximo 4 insights, 3 actions, 3 followups; se os dados não responderem à pergunta, diga-o e sugira o que explorar."""


def _strip_think(text: str) -> str:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S | re.I)
    text = re.sub(r"```(?:json)?", "", text, flags=re.I)
    return text.strip()


def _validate_actions(actions, max_n: int = 3) -> list:
    clean = []
    for a in (actions or [])[:max_n]:
        if not isinstance(a, dict):
            continue
        label = str(a.get("label") or "")[:60].strip()
        href = str(a.get("href") or "").strip()
        if not label or not href.startswith("/"):
            continue
        route = href.split("?")[0].rstrip("/") or "/"
        if route not in KNOWN_ROUTES:
            continue
        clean.append({"label": label, "href": href})
    return clean


def _validate_insights(insights, max_n: int = 4) -> list:
    clean = []
    for i in (insights or [])[:max_n]:
        if not isinstance(i, dict):
            continue
        title = str(i.get("title") or "")[:80].strip()
        if not title:
            continue
        clean.append({"title": title,
                      "detail": str(i.get("detail") or "")[:240].strip(),
                      "tone": str(i.get("tone") or "info")
                      if i.get("tone") in ("info", "warn", "danger", "success")
                      else "info"})
    return clean


def _tools_context(results: list) -> str:
    parts = []
    for r in results:
        blob = {"tool": r.get("tool"), "title": r.get("title"),
                "summary": r.get("summary"), "table": r.get("table"),
                "meta": r.get("meta")}
        parts.append(json.dumps(blob, ensure_ascii=False, default=str))
    return "\n".join(parts)


def call_ollama_copilot(question: str, tool_results: list,
                        history: list = None) -> dict:
    """Pede síntese JSON ao Ollama. Devolve dict validado ou None."""
    try:
        import requests
        hist = ""
        for m in (history or [])[-4:]:
            role = "UTILIZADOR" if m.get("role") == "user" else "ASSISTENTE"
            hist += f"\n{role}: {str(m.get('content', ''))[:240]}"
        prompt = (SYSTEM_PROMPT
                  + "\n\nDADOS DAS FERRAMENTAS (JSON):\n" + _tools_context(tool_results)[:6000]
                  + ("\nCONVERSA ANTERIOR:" + hist if hist else "")
                  + "\n\nPERGUNTA: " + question[:500]
                  + "\n\nJSON:")
        resp = requests.post(
            f"{OLLAMA_URL.rstrip('/')}/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False,
                  "options": {"temperature": 0.2, "num_predict": 900}},
            timeout=OLLAMA_TIMEOUT)
        if resp.status_code != 200:
            logger.info("copilot global LLM http %s", resp.status_code)
            return None
        raw = _strip_think(resp.json().get("response", ""))
        start, end = raw.find("{"), raw.rfind("}")
        if start < 0 or end <= start:
            return None
        plan = json.loads(raw[start:end + 1])
        if not isinstance(plan, dict):
            return None
        answer = str(plan.get("answer") or "").strip()
        if not answer:
            return None
        return {
            "answer": answer[:2800],
            "insights": _validate_insights(plan.get("insights")),
            "actions": _validate_actions(plan.get("actions")),
            "followups": [str(f)[:120] for f in plan.get("followups", [])[:3]]
            if isinstance(plan.get("followups"), list) else [],
        }
    except Exception as e:
        logger.info("copilot global LLM indisponível: %s", e)
        return None


# ---------------------------------------------------------------------------
# 5. ORQUESTRADOR DO CHAT
# ---------------------------------------------------------------------------

def chat(question: str, history: list = None, page: str = None) -> dict:
    """Fluxo principal: router → tools → síntese (LLM com fallback).
    `page` = rota atual do frontend — dá consciência de contexto quando
    a pergunta é vaga (ex.: «e agora?» na página de SLA fala de SLA)."""
    import time
    t0 = time.time()
    question = (question or "").strip()[:1000]
    if not question:
        return {"answer": "Faça uma pergunta sobre a plataforma: alertas, "
                          "transações, casos, agentes, SLA, Excel…",
                "mode": "rules", "tools_used": [], "insights": [],
                "actions": [], "tables": [], "followups": [],
                "latency_ms": 0}

    tool_names = detect_tools(question, page=page)
    results = run_tools(tool_names, question)

    # resposta determinística (sempre calculada — garante consistência)
    rule_answer = "\n\n".join(r["summary"] for r in results)
    insights = []
    for r in results:
        insights.extend(r.get("insights", []))
    insights = insights[:4]
    actions = []
    for t in tool_names:
        for a in _TOOL_ACTIONS.get(t, []):
            if a not in actions:
                actions.append(a)
    actions = actions[:3]
    tables = [r["table"] for r in results if r.get("table")]
    followups = _followups_for(tool_names)

    # tentativa de síntese LLM (substitui answer/insights/actions/followups)
    llm = call_ollama_copilot(question, results, history)
    if llm:
        return {"answer": llm["answer"], "mode": "llm",
                "tools_used": tool_names,
                "insights": llm["insights"] or insights[:4],
                "actions": llm["actions"] or actions,
                "tables": tables,
                "followups": llm["followups"] or followups,
                "latency_ms": int((time.time() - t0) * 1000)}
    return {"answer": rule_answer or "Não encontrei dados para esta pergunta.",
            "mode": "rules", "tools_used": tool_names,
            "insights": insights, "actions": actions, "tables": tables,
            "followups": followups,
            "latency_ms": int((time.time() - t0) * 1000)}


# ---------------------------------------------------------------------------
# 6. BRIEFING EXECUTIVO PROATIVO
# ---------------------------------------------------------------------------

def build_briefing() -> dict:
    """Snapshot executivo da plataforma: KPIs + sinais + recomendações."""
    overview = tool_overview({})
    sla = tool_sla_check({})
    forecast = tool_risk_forecast({})
    benford = tool_benford_check({})
    dup = tool_find_duplicates({})

    meta = overview["meta"]
    kpis = {
        "transactions_total": meta.get("tx_total", 0),
        "transactions_amount": meta.get("tx_sum", 0),
        "open_alerts": meta.get("open_alerts", 0),
        "critical_alerts": (overview["table"]["rows"][0][1]
                            if overview.get("table") else "0"),
        "cases_open": meta.get("cases_open", 0),
        "cases_overdue": meta.get("cases_overdue", 0),
        "benford_mad": benford.get("meta", {}).get("mad"),
        "benford_verdict": benford.get("meta", {}).get("verdict"),
        "trend": forecast.get("meta", {}).get("trend", "estável"),
    }

    insights = []
    for src in (overview, sla, forecast, benford, dup):
        for i in src.get("insights", [])[:2]:
            insights.append(i)
    insights = insights[:6]

    narrative = (
        f"{overview['summary']}\n\n{sla['summary']}\n\n"
        f"{forecast['summary']}")
    if benford.get("meta", {}).get("mad") is not None:
        narrative += f"\n\n{benford['summary']}"
    if dup.get("meta", {}).get("exact_groups"):
        narrative += f"\n\n{dup['summary']}"

    actions = [{"label": "Ver alertas", "href": "/alerts"},
               {"label": "Abrir casos", "href": "/cases"},
               {"label": "Excel Studio", "href": "/excel"}]

    return {"briefing_md": narrative, "kpis": kpis, "insights": insights,
            "actions": actions, "mode": "rules",
            "generated_at": timezone.now().isoformat()}
