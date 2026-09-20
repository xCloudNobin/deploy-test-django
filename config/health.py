from django.db import connection
from django.db.utils import DatabaseError, OperationalError
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin

from config.settings import RELEASE_SHA


def health_live(request):
    return JsonResponse({"status": "alive", "release": RELEASE_SHA})


def health_ready(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except (DatabaseError, OperationalError):
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse({"status": "ready", "release": RELEASE_SHA})


class ServiceUnavailableMiddleware(MiddlewareMixin):
    def process_exception(self, request, exception):
        if isinstance(exception, (DatabaseError, OperationalError)):
            return JsonResponse(
                {"error": "database unavailable", "release": RELEASE_SHA},
                status=503,
            )
        return None
