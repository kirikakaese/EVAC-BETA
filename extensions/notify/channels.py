# SPDX-License-Identifier: AGPL-3.0-or-later
"""Announcement channels backed by extensions: e-mail, ntfy, Matrix, Telegram, Mastodon (ADR-0020).

Each channel is a ``NotificationChannelSpec`` whose ``send(delivery)`` looks up the extension configuration that
applies to the announcement's event (instance-wide or the event's own) and posts the message. A refusal (4xx,
bad token) marks the delivery failed at once; network trouble raises, so the outbox retries.
"""
from __future__ import annotations

import html
from typing import Any
from urllib.parse import quote

from django.core import mail
from django.utils.translation import gettext as _

from apps.extensions import services as ext

from .http import Rejected, call


def _ann(d):
    return d.announcement


def _link(ann) -> str:
    from django.conf import settings

    from apps.announcements.services import _url

    base = getattr(settings, "EVAC_PUBLIC_URL", "") or ""
    return f"{base}{_url(ann)}" if base else ""


def _text(d, key: str, limit: int = 0) -> str:
    from apps.announcements.services import text_for

    return text_for(d.announcement, key, limit)


def urgency(ann) -> str:
    """low / normal / high / max from the level."""
    if ann.level.emergency:
        return "max"
    if ann.level.rank >= 30:
        return "high"
    if ann.level.rank >= 20:
        return "normal"
    return "low"


def _base(url: str) -> str:
    return (url or "").strip().rstrip("/")


# ------------------------------------------------------------------ e-mail
def _fixed(cfg) -> list[str]:
    raw = cfg.settings.get("recipients") or []
    if isinstance(raw, str):
        raw = raw.replace(",", "\n").splitlines()
    return [a.strip() for a in raw if a and a.strip()]


def email_recipients(cfg, event) -> list[str]:
    out = _fixed(cfg)
    if cfg.settings.get("to_staff") and event is not None:
        from apps.announcements.services import staff_recipients

        out += [u.email for u in staff_recipients(event) if u.email]
    return sorted(set(out))


def send_email(cfg, d) -> dict[str, Any]:
    ann = _ann(d)
    to = email_recipients(cfg, ann.event)
    if not to:
        return {"status": "skipped", "detail": _("No recipients configured.")}
    prefix = (cfg.settings.get("subject_prefix") or f"[{ann.event.name}]").strip()
    link = _link(ann)
    body = _text(d, "email") + (f"\n\n{link}" if link else "")
    msg = mail.EmailMessage(subject=f"{prefix} {ann.level.name}: {ann.title}"[:250], body=body,
                            from_email=cfg.settings.get("from_email") or None, bcc=to)
    if urgency(ann) in ("high", "max"):
        msg.extra_headers = {"Importance": "high", "X-Priority": "1"}
    msg.send()
    return {"recipients": len(to), "detail": _("%(n)s addresses") % {"n": len(to)}}


def test_email(cfg) -> str:
    conn = mail.get_connection()
    conn.open()
    conn.close()
    return _("The mail server accepts connections; %(n)s fixed recipients.") % {"n": len(_fixed(cfg))}


# ------------------------------------------------------------------ ntfy
NTFY_PRIORITY = {"low": 2, "normal": 3, "high": 4, "max": 5}


def send_ntfy(cfg, d) -> dict[str, Any]:
    ann = _ann(d)
    body = {"topic": cfg.settings.get("topic", ""), "title": f"{ann.level.name}: {ann.title}"[:250],
            "message": _text(d, "ntfy", 4000) if (ann.channel_texts or {}).get("ntfy") else (ann.body or ann.title),
            "priority": NTFY_PRIORITY[urgency(ann)], "tags": ["rotating_light"] if ann.level.emergency else []}
    link = _link(ann)
    if link:
        body["click"] = link
    token = cfg.secret("token")
    call("POST", _base(cfg.settings.get("server") or "https://ntfy.sh"), json=body,
         headers={"Authorization": f"Bearer {token}"} if token else None)
    return {"recipients": 1, "detail": _("topic %(t)s") % {"t": body["topic"]}}


def test_ntfy(cfg) -> str:
    token = cfg.secret("token")
    call("POST", _base(cfg.settings.get("server") or "https://ntfy.sh"),
         json={"topic": cfg.settings.get("topic", ""), "title": "EVAC", "message": _("Connection test"),
               "priority": 1}, headers={"Authorization": f"Bearer {token}"} if token else None)
    return _("A test message (lowest priority) was published.")


# ------------------------------------------------------------------ Matrix
def _matrix_html(ann, text: str) -> str:
    colour = html.escape(ann.level.colour)
    return (f'<p><strong><font color="{colour}">{html.escape(ann.level.name)}</font>: '
            f"{html.escape(ann.title)}</strong></p>" + "".join(
                f"<p>{html.escape(p)}</p>" for p in text.split("\n\n")[1:] if p.strip()))


def send_matrix(cfg, d) -> dict[str, Any]:
    ann = _ann(d)
    room = cfg.settings.get("room_id", "")
    text = _text(d, "matrix", 4000)
    own = (ann.channel_texts or {}).get("matrix")
    content = {"msgtype": "m.text", "body": f"{ann.level.name}: {text}"}
    if not own:
        content.update({"format": "org.matrix.custom.html", "formatted_body": _matrix_html(ann, text)})
    # the delivery id is the transaction id: a retry after a lost answer does not post twice
    url = (f"{_base(cfg.settings.get('homeserver'))}/_matrix/client/v3/rooms/{quote(room, safe='')}"
           f"/send/m.room.message/{d.pk}")
    call("PUT", url, json=content, headers={"Authorization": f"Bearer {cfg.secret('access_token')}"})
    return {"recipients": 1, "detail": _("room %(r)s") % {"r": room}}


def test_matrix(cfg) -> str:
    who = call("GET", f"{_base(cfg.settings.get('homeserver'))}/_matrix/client/v3/account/whoami",
               headers={"Authorization": f"Bearer {cfg.secret('access_token')}"})
    return _("Signed in as %(u)s.") % {"u": who.get("user_id", "?")}


# ------------------------------------------------------------------ Telegram
def _telegram(cfg, method: str, payload: dict | None = None) -> Any:
    base = _base(cfg.settings.get("api_base") or "https://api.telegram.org")
    return call("POST", f"{base}/bot{cfg.secret('bot_token')}/{method}", json=payload or {})


def send_telegram(cfg, d) -> dict[str, Any]:
    ann = _ann(d)
    own = (ann.channel_texts or {}).get("telegram")
    if own:
        text = html.escape(_text(d, "telegram", 4000))
    else:
        text = f"<b>{html.escape(ann.level.name)}: {html.escape(ann.title)}</b>"
        if ann.body and ann.body != ann.title:
            text += f"\n\n{html.escape(ann.body)}"
        link = _link(ann)
        if link:
            text += f'\n\n<a href="{html.escape(link)}">{html.escape(_("Details"))}</a>'
    chat = cfg.settings.get("chat_id", "")
    _telegram(cfg, "sendMessage", {"chat_id": chat, "text": text[:4096], "parse_mode": "HTML",
                                   "disable_notification": urgency(ann) == "low",
                                   "link_preview_options": {"is_disabled": True}})
    return {"recipients": 1, "detail": _("chat %(c)s") % {"c": chat}}


def test_telegram(cfg) -> str:
    me = _telegram(cfg, "getMe")
    return _("Bot @%(b)s is ready.") % {"b": (me.get("result") or {}).get("username", "?")}


# ------------------------------------------------------------------ Mastodon
def send_mastodon(cfg, d) -> dict[str, Any]:
    ann = _ann(d)
    status = _text(d, "mastodon", 500)
    if not (ann.channel_texts or {}).get("mastodon"):
        status = _text(d, "mastodon", 480)
        tag = (cfg.settings.get("hashtag") or "").strip().lstrip("#")
        if tag and len(status) + len(tag) + 3 <= 500:
            status += f"\n\n#{tag}"
    res = call("POST", f"{_base(cfg.settings.get('instance'))}/api/v1/statuses",
               json={"status": status, "visibility": cfg.settings.get("visibility") or "public"},
               headers={"Authorization": f"Bearer {cfg.secret('access_token')}", "Idempotency-Key": str(d.pk)})
    return {"recipients": 1, "detail": str(res.get("url") or _("posted"))[:500]}


def test_mastodon(cfg) -> str:
    me = call("GET", f"{_base(cfg.settings.get('instance'))}/api/v1/accounts/verify_credentials",
              headers={"Authorization": f"Bearer {cfg.secret('access_token')}"})
    return _("Signed in as @%(a)s.") % {"a": me.get("acct", "?")}


# ------------------------------------------------------------------ glue
SENDERS = {"email": send_email, "ntfy": send_ntfy, "matrix": send_matrix, "telegram": send_telegram,
           "mastodon": send_mastodon}
TESTS = {"email": test_email, "ntfy": test_ntfy, "matrix": test_matrix, "telegram": test_telegram,
         "mastodon": test_mastodon}


def sender(key: str):
    def send(d) -> dict[str, Any]:
        cfg = ext.effective(key, d.announcement.event)
        if cfg is None:
            return {"status": "skipped", "detail": _("The extension is off for this event.")}
        try:
            return SENDERS[key](cfg, d)
        except Rejected as exc:
            ext.write_log(cfg, "error", f"announcement delivery refused: {exc}", delivery=str(d.pk))
            return {"status": "failed", "detail": str(exc)}
    return send


def available(key: str):
    def check(event) -> bool:
        return ext.effective(key, event) is not None
    return check


def tester(key: str):
    from apps.core.plugins import ConnectionResult

    from .http import Temporary

    def test(cfg) -> ConnectionResult:
        try:
            return ConnectionResult(True, TESTS[key](cfg))
        except (Rejected, Temporary) as exc:
            return ConnectionResult(False, str(exc))
        except Exception as exc:  # noqa: BLE001 - e.g. SMTP errors: shown to the admin
            return ConnectionResult(False, f"{type(exc).__name__}: {exc}"[:300])
    return test
