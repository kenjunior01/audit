from rest_framework.authentication import BaseAuthentication
from rest_framework.permissions import BasePermission
from rest_framework import exceptions
from .models import ApiToken
from types import SimpleNamespace

class ApiTokenAuthentication(BaseAuthentication):
    def authenticate(self, request):
        auth = request.headers.get('Authorization') or ''
        token = None
        if auth.lower().startswith('bearer '):
            token = auth[7:]
        if not token:
            return None
        try:
            rec = ApiToken.objects.get(pk=token)
        except ApiToken.DoesNotExist:
            raise exceptions.AuthenticationFailed('invalid token')
        user = SimpleNamespace(is_authenticated=True, id=rec.user_id, role=rec.role)
        return (user, {'role': rec.role, 'token': token})

class IsViewerOrAbove(BasePermission):
    def has_permission(self, request, view):
        auth_data = request.auth
        if isinstance(auth_data, dict):
            role = auth_data.get('role')
        elif hasattr(auth_data, 'role'):
            role = auth_data.role
        elif hasattr(auth_data, 'get'):
            role = auth_data.get('role')
        else:
            role = None
        return role in ('viewer', 'auditor', 'admin')

class IsAuditorOrAdmin(BasePermission):
    def has_permission(self, request, view):
        auth_data = request.auth
        if isinstance(auth_data, dict):
            role = auth_data.get('role')
        elif hasattr(auth_data, 'role'):
            role = auth_data.role
        elif hasattr(auth_data, 'get'):
            role = auth_data.get('role')
        else:
            role = None
        return role in ('auditor', 'admin')
