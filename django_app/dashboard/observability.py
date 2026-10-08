"""Observabilidade — métricas em formato Prometheus (texto), sem dependências.

- MetricsMiddleware: conta pedidos HTTP por método/endpoint/status e latência
  (p50/p95 aproximada por buckets) — ignora /metrics e ficheiros media.
- Endpoint GET /metrics: devolve counters + gauges de domínio
  (transações, alertas por severidade, casos, notificações, digest).
Seguro por design: expõe apenas contadores agregados, sem dados de utilizador.
"""
import re
import threading
import time

# ---------------------------------------------------------------- serviço

_lock = threading.Lock()

_HTTP_COUNTS = {}          # (method, route, status) -> n
_LATENCY_BUCKETS = {}      # route -> [count, sum_ms, <=50ms, <=200ms, <=1000ms, >1000ms]
_START_TS = time.time()

_BUCKET_EDGES = (50.0, 200.0, 1000.0)

# rotas normalizadas (evita cardinalidade infinita com ids numéricos)
_DYN = re.compile(r'/\d+(?=/|$)')
_UUID = re.compile(r'/[0-9a-fA-F-]{32,36}(?=/|$)')


def normalize_path(path):
    p = _UUID.sub('/:id', path)
    p = _DYN.sub('/:id', p)
    return p or '/'


def record_request(method, path, status, duration_ms):
    route = normalize_path(path)
    key = (method.upper(), route, int(status))
    with _lock:
        _HTTP_COUNTS[key] = _HTTP_COUNTS.get(key, 0) + 1
        b = _LATENCY_BUCKETS.setdefault(route, [0, 0.0, 0, 0, 0, 0])
        b[0] += 1
        b[1] += duration_ms
        if duration_ms <= _BUCKET_EDGES[0]:
            b[2] += 1
        elif duration_ms <= _BUCKET_EDGES[1]:
            b[3] += 1
        elif duration_ms <= _BUCKET_EDGES[2]:
            b[4] += 1
        else:
            b[5] += 1


def snapshot_and_render():
    """Renderiza métricas em formato Prometheus text (versão 0.0.4)."""
    lines = []

    def metric(name, mtype, help_text):
        lines.append(f"# HELP {name} {help_text}")
        lines.append(f"# TYPE {name} {mtype}")

    from django.db.models import Count
    from django.utils import timezone
    from .models import Alert, AuditCase, CopilotDigest, Notification, Transaction

    with _lock:
        http_counts = dict(_HTTP_COUNTS)
        lat = {k: list(v) for k, v in _LATENCY_BUCKETS.items()}
        uptime = time.time() - _START_TS

    # --- domínio
    metric('audit_transactions_total', 'gauge', 'Transações registadas na plataforma')
    lines.append(f"audit_transactions_total {Transaction.objects.count()}")

    metric('audit_alerts_by_severity', 'gauge', 'Alertas por severidade')
    try:
        for r in Alert.objects.values('severity').annotate(c=Count('id')).order_by():
            sev = (r['severity'] or 'unknown').lower()
            lines.append(f'audit_alerts_by_severity{{severity="{sev}"}} {r["c"]}')
    except Exception:
        pass

    metric('audit_cases_by_status', 'gauge', 'Casos de auditoria por estado')
    try:
        from django.db.models import Count
        for r in AuditCase.objects.values('status').annotate(c=Count('id')).order_by():
            st = (r['status'] or 'unknown').lower().replace(' ', '_')
            lines.append(f'audit_cases_by_status{{status="{st}"}} {r["c"]}')
    except Exception:
        pass

    metric('audit_notifications_unread', 'gauge', 'Notificações não lidas (todos os utilizadores)')
    lines.append(f"audit_notifications_unread {Notification.objects.filter(read_at__isnull=True).count()}")

    metric('audit_digests_total', 'gauge', 'Digests do copiloto gerados')
    lines.append(f"audit_digests_total {CopilotDigest.objects.count()}")

    # --- processo
    metric('audit_uptime_seconds', 'gauge', 'Segundos desde o arranque do processo')
    lines.append(f"audit_uptime_seconds {uptime:.0f}")

    # --- http
    metric('audit_http_requests_total', 'counter', 'Pedidos HTTP por método, rota e estado')
    for (method, route, status), n in sorted(http_counts.items()):
        lines.append(f'audit_http_requests_total{{method="{method}",route="{route}",status="{status}"}} {n}')

    metric('audit_http_request_duration_ms', 'summary', 'Latência por rota (buckets fixos)')
    lines.append('# UNIT audit_http_request_duration_ms milliseconds')
    for route, b in sorted(lat.items()):
        count, total = b[0], b[1]
        if not count:
            continue
        avg = total / count
        lines.append(f'audit_http_request_duration_ms_sum{{route="{route}"}} {total:.1f}')
        lines.append(f'audit_http_request_duration_ms_count{{route="{route}"}} {count}')
        lines.append(f'audit_http_request_duration_ms_avg{{route="{route}"}} {avg:.1f}')
        for label, val in zip(('le50', 'le200', 'le1000', 'gt1000'), b[2:]):
            lines.append(f'audit_http_request_duration_ms_bucket{{route="{route}",bucket="{label}"}} {val}')

    lines.append('')
    return '\n'.join(lines)


# ---------------------------------------------------------------- middleware

SKIP_PREFIXES = ('/django/api/metrics', '/api/metrics', '/django/media/', '/media/', '/static/')


class MetricsMiddleware:
    """Conta todos os pedidos HTTP (exceto /metrics e media) de forma resiliente."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start = time.time()
        try:
            response = self.get_response(request)
        except Exception:
            duration = (time.time() - start) * 1000
            try:
                record_request(request.method, request.path, 500, duration)
            except Exception:
                pass
            raise
        try:
            path = request.path or '/'
            if not any(path.startswith(p) for p in SKIP_PREFIXES):
                duration = (time.time() - start) * 1000
                record_request(request.method, path, getattr(response, 'status_code', 200), duration)
        except Exception:
            pass  # métricas nunca derrubam pedidos
        return response


# ---------------------------------------------------------------- view

def metrics_view(request):
    """GET /metrics — formato Prometheus text/plain (sem auth: só counters agregados)."""
    from django.http import HttpResponse
    try:
        body = snapshot_and_render()
    except Exception:
        body = "# erro a gerar métricas\n"
    return HttpResponse(body, content_type='text/plain; version=0.0.4; charset=utf-8')
