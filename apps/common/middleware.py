"""Audit log middleware - captures request metadata."""
import logging

from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger("apps.audit")


class AuditLogMiddleware(MiddlewareMixin):
    """Attach request metadata to thread-local for audit logging."""

    def process_request(self, request):
        # Store IP for audit logging
        request._audit_ip = self._get_client_ip(request)

    @staticmethod
    def _get_client_ip(request):
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            return x_forwarded_for.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR", "unknown")
