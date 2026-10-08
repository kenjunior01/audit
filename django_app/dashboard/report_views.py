"""Endpoints do Relatório Global de Auditoria (preview JSON + PDF)."""
from django.http import HttpResponse
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from .auth import IsAuditorOrAdmin
from .report_service import audit_report_summary, build_audit_report_pdf, build_recommendations


def _actor(request):
    u = getattr(request, 'user', None)
    uid = getattr(u, 'id', None) or getattr(u, 'pk', None)
    if uid is None:
        return ''
    if isinstance(uid, int):
        uid = getattr(u, 'username', None) or uid
    return str(uid)


def _days(request):
    try:
        return max(1, min(int(request.query_params.get('days', '30')), 365))
    except (TypeError, ValueError):
        return 30


@api_view(['GET'])
@permission_classes([IsAuditorOrAdmin])
@throttle_classes([UserRateThrottle])
def audit_report_summary_view(request):
    """Preview JSON do relatório (para cartões/dashboard antes de gerar PDF)."""
    days = _days(request)
    s = audit_report_summary(days)
    s['recommendations'] = build_recommendations(s)
    return Response(s)


@api_view(['GET'])
@permission_classes([IsAuditorOrAdmin])
@throttle_classes([UserRateThrottle])
def audit_report_pdf_view(request):
    """Gera e devolve o PDF do Relatório Global de Auditoria."""
    days = _days(request)
    pdf, fname, _s = build_audit_report_pdf(days=days,
                                            generated_by=_actor(request) or 'Plataforma')
    resp = HttpResponse(pdf, content_type='application/pdf')
    resp['Content-Disposition'] = f'attachment; filename="{fname}"'
    return resp
