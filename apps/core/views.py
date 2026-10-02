# SPDX-License-Identifier: AGPL-3.0-or-later
"""Health, readiness, Prometheus metrics and notification views."""
from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.db import connection
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .models import Notification


def healthz(request):
    """Liveness: the process answers."""
    return JsonResponse({"status": "ok"})


def readyz(request):
    """Readiness: database and cache reachable."""
    checks = {}
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["database"] = f"error: {exc}"
    try:
        cache.set("evac:readyz", 1, 5)
        checks["cache"] = "ok" if cache.get("evac:readyz") == 1 else "error"
    except Exception as exc:  # noqa: BLE001
        checks["cache"] = f"error: {exc}"
    ok = all(v == "ok" for v in checks.values())
    return JsonResponse({"status": "ok" if ok else "degraded", "checks": checks}, status=200 if ok else 503)


def metrics(request):
    """Prometheus text exposition. Modules add their own gauges via ``METRICS`` callables later."""
    from django.conf import settings

    from apps.accounts.models import User
    from apps.events.models import Event

    from . import outbox
    from .models import AuditChainHead

    token = getattr(settings, "EVAC_METRICS_TOKEN", "")
    if token and request.headers.get("Authorization") != f"Bearer {token}":
        return HttpResponse(status=401)
    head = AuditChainHead.objects.filter(pk=1).first()
    lines = [
        "# HELP evac_info EVAC build information.",
        "# TYPE evac_info gauge",
        f'evac_info{{version="{__import__("evac").__version__}",mode="{settings.EVAC_MODE}"}} 1',
        "# HELP evac_users Active user accounts.",
        "# TYPE evac_users gauge",
        f"evac_users {User.objects.filter(is_active=True).count()}",
        "# HELP evac_events Events by lifecycle state.",
        "# TYPE evac_events gauge",
    ]
    for state, _ in Event.State.choices:
        lines.append(f'evac_events{{state="{state}"}} {Event.objects.filter(state=state).count()}')
    lines += [
        "# HELP evac_outbox_depth Outbox jobs waiting for delivery.",
        "# TYPE evac_outbox_depth gauge",
        f"evac_outbox_depth {outbox.depth()}",
        "# HELP evac_audit_entries Audit log entries.",
        "# TYPE evac_audit_entries counter",
        f"evac_audit_entries {head.count if head else 0}",
    ]
    return HttpResponse("\n".join(lines) + "\n", content_type="text/plain; version=0.0.4")


@login_required
def notifications(request):
    items = Notification.objects.filter(user=request.user)[:100]
    return render(request, "core/notifications.html", {"items": items})


@login_required
@require_POST
def notification_read(request, pk):
    n = get_object_or_404(Notification, pk=pk, user=request.user)
    n.read_at = n.read_at or timezone.now()
    n.save(update_fields=["read_at"])
    if n.url and url_has_allowed_host_and_scheme(n.url, allowed_hosts={request.get_host()}):
        return redirect(n.url)
    return redirect("core:notifications")


@login_required
@require_POST
def notifications_read_all(request):
    Notification.objects.filter(user=request.user, read_at__isnull=True).update(read_at=timezone.now())
    return redirect("core:notifications")
