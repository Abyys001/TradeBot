from __future__ import annotations

import logging
import time
from typing import Callable

from django.http import HttpRequest, HttpResponse

SKIP_PATHS = frozenset({"/api/health/", "/ws/"})

logger = logging.getLogger("apps.logging.access")


class RequestLoggingMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if any(request.path.startswith(p) for p in SKIP_PATHS):
            return self.get_response(request)

        start = time.perf_counter()
        response = self.get_response(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 1)

        status = response.status_code
        if status >= 500:
            level = "ERROR"
        elif status >= 400:
            level = "WARNING"
        else:
            level = "INFO"

        logger.log(
            getattr(logging, level),
            "%s %s %s %sms",
            request.method,
            request.path,
            status,
            duration_ms,
            extra={
                "category": "SYSTEM",
                "context": {
                    "method": request.method,
                    "path": request.path,
                    "status": status,
                    "duration_ms": duration_ms,
                    "remote_addr": request.META.get("REMOTE_ADDR", ""),
                },
            },
        )
        return response
