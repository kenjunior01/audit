"""Endpoints da Central de Notificações in-app."""
from datetime import timedelta

from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from .auth import IsViewerOrAbove
from .models import Notification
from .notifications_service import unread_count


def _recipient(request):
    """user_id autenticado (convenção da plataforma: string do ApiToken).

    O auth do ApiTokenAuthentication devolve request.user = SimpleNamespace
    com .id = user_id; para utilizadores Django reais (sessão/admin) usa o
    username para manter a consistência das notificações.
    """
    u = getattr(request, 'user', None)
    uid = getattr(u, 'id', None) or getattr(u, 'pk', None)
    if uid is None:
        return ''
    if isinstance(uid, int):  # Django User real → username é a chave da plataforma
        uid = getattr(u, 'username', None) or uid
    return str(uid)


@api_view(['GET'])
@permission_classes([IsViewerOrAbove])
@throttle_classes([UserRateThrottle])
def notifications_list(request):
    """Lista as notificações do utilizador (mais recentes primeiro).

    Query: ?unread=1 (só não lidas) &limit=50
    """
    rc = _recipient(request)
    qs = Notification.objects.filter(recipient=rc)
    if request.query_params.get('unread') in ('1', 'true'):
        qs = qs.filter(read_at__isnull=True)
    try:
        limit = max(1, min(int(request.query_params.get('limit', '50')), 200))
    except ValueError:
        limit = 50
    items = [{
        'id': n.id, 'kind': n.kind, 'severity': n.severity, 'title': n.title,
        'body': n.body, 'route': n.route, 'meta': n.meta,
        'read_at': n.read_at, 'unread': n.is_unread,
        'created_at': n.created_at,
    } for n in qs[:limit]]
    return Response({'results': items, 'unread': unread_count(rc), 'count': qs.count()})


@api_view(['GET'])
@permission_classes([IsViewerOrAbove])
@throttle_classes([UserRateThrottle])
def notifications_unread_count(request):
    return Response({'unread': unread_count(_recipient(request))})


@api_view(['POST'])
@permission_classes([IsViewerOrAbove])
@throttle_classes([UserRateThrottle])
def notifications_mark_read(request):
    """Marca notificações como lidas. Body: {"ids": [..]} ou {"all": true}."""
    rc = _recipient(request)
    data = request.data if isinstance(request.data, dict) else {}
    now = timezone.now()
    if data.get('all'):
        updated = Notification.objects.filter(recipient=rc, read_at__isnull=True)\
            .update(read_at=now)
        return Response({'marked': updated, 'unread': 0})
    ids = data.get('ids') or []
    if not isinstance(ids, list) or not ids:
        return Response({'error': 'indique ids ou all=true'}, status=400)
    clean_ids = []
    for i in ids:
        try:
            clean_ids.append(int(i))
        except (TypeError, ValueError):
            continue
    updated = Notification.objects.filter(recipient=rc, id__in=clean_ids,
                                          read_at__isnull=True).update(read_at=now)
    return Response({'marked': updated, 'unread': unread_count(rc)})
