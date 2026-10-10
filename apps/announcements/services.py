# SPDX-License-Identifier: AGPL-3.0-or-later
"""Announcements: defaults, text rendering, the approval workflow, scheduling, targeting, delivery (audited)."""
from __future__ import annotations

import datetime as dt
import re
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core import modules, outbox, settings_store, webhooks
from apps.core.audit import log
from apps.core.registry import registry

from .models import Announcement, Delivery, Level, Template

SCREENS, FEED, WEBHOOK, STAFF = "screens", "feed", "webhook", "staff"
SPEECH, SPEECH_MAX = "speech", 1000  # channel_texts key of the spoken text
PREVIEW_DAYS = 7

# ------------------------------------------------------------------ defaults
DEFAULT_LEVELS = [
    # key, name, rank, colour, display, sound, min seconds, repeat minutes, channels, emergency
    ("info", "Info", 10, "#2563eb", "ticker", "none", 60, 0, [SCREENS, FEED], False),
    ("important", "Important", 20, "#d97706", "banner", "chime", 120, 0, [SCREENS, FEED, STAFF], False),
    ("urgent", "Urgent", 30, "#dc2626", "card", "gong", 60, 10, [SCREENS, FEED, STAFF, WEBHOOK], False),
    ("emergency", "Emergency", 40, "#b91c1c", "takeover", "alert", 300, 0, [SCREENS, FEED, STAFF, WEBHOOK], True),
]
DEFAULT_TEMPLATES = [
    ("Lost child", "urgent", "Lost child", "We are looking for a child: {{description}}. Please contact {{desk}}.",
     "Lost child: {{description}} - contact {{desk}}"),
    ("Doors open soon", "important", "Doors open in {{minutes}} minutes",
     "{{place}} opens in {{minutes}} minutes. Please have your tickets ready.", "Doors open in {{minutes}} min"),
    ("Severe weather warning", "urgent", "Severe weather warning",
     "{{details}} Please follow the instructions of the staff.", "Weather warning: {{details}}"),
    ("Keep exits clear", "important", "Please keep the exits clear",
     "Do not block emergency exits and escape routes. Thank you.", "Keep exits clear"),
    ("Lost and found", "info", "Found: {{item}}", "Found {{item}}. Collect it at {{desk}}.",
     "Found: {{item}} - at {{desk}}"),
]


def ensure_defaults(event) -> None:
    """Built-in levels and English templates, created once per event (editable afterwards)."""
    if not Level.objects.filter(event=event).exists():
        Level.objects.bulk_create([
            Level(event=event, key=k, name=n, rank=r, colour=c, display=d, sound=snd, min_display_seconds=m,
                  repeat_every_minutes=rep, default_channels=ch, emergency=em, speak=k in ("urgent", "emergency"))
            for k, n, r, c, d, snd, m, rep, ch, em in DEFAULT_LEVELS])
    if not Template.objects.filter(event=event, builtin=True).exists():
        levels = {lv.key: lv for lv in Level.objects.filter(event=event)}
        Template.objects.bulk_create([
            Template(event=event, name=n, level=levels.get(lk), title=t, body=b, short=s, builtin=True)
            for n, lk, t, b, s in DEFAULT_TEMPLATES])


def ann_settings(event) -> dict[str, Any]:
    return settings_store.get("announcements", event=event)


# ------------------------------------------------------------------ texts
VAR = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_.]*)\s*\}\}")


def variables_in(*texts: str) -> list[str]:
    """Names a template asks for (``event.*`` comes from the event)."""
    seen: list[str] = []
    for text in texts:
        for name in VAR.findall(text or ""):
            if not name.startswith("event.") and name not in seen:
                seen.append(name)
    return seen


def render_text(text: str, variables: dict[str, Any], event) -> str:
    """Plain-text substitution (no markup, no logic); unknown names stay visible as ``{{name}}``."""
    def sub(m: re.Match) -> str:
        name = m.group(1)
        if name == "event.name":
            return event.name
        value = variables.get(name)
        return str(value) if value not in (None, "") else m.group(0)
    return VAR.sub(sub, text or "")


def apply_template(ann: Announcement, template: Template, variables: dict[str, Any]) -> None:
    ann.template = template
    ann.variables = {k: str(v)[:300] for k, v in variables.items()}
    ann.title = render_text(template.title, ann.variables, ann.event)[:200]
    ann.body = render_text(template.body, ann.variables, ann.event)
    ann.short = render_text(template.short, ann.variables, ann.event)[:160]
    if template.level_id and not ann.level_id:
        ann.level = template.level


# ------------------------------------------------------------------ permissions
def may(user, event, perm: str, request=None, obj=None) -> bool:
    from apps.events import rbac

    return rbac.has_perm(user, event, perm, obj=obj, request=request)


def rbac_any(user, event, perm: str, request=None) -> bool:
    """The permission anywhere in the event (scoped grants count)."""
    from apps.events import rbac

    return rbac.has_any(user, event, perm, request=request)


def reachable(user, event, perm: str) -> bool:
    """Would ``user`` hold ``perm`` after signing in (with two factors where a role needs them)? For choosing whom
    to notify, never for authorising."""
    from apps.events import rbac

    return perm in rbac.effective(user, event, two_factor=True).permissions


def target_objects(ann: Announcement) -> list:
    return [*ann.venues.all(), *ann.zones.all(), *ann.rooms.all(), *ann.screen_groups.all(), *ann.screens.all()]


def may_target(user, ann: Announcement, perm: str, request=None) -> bool:
    """Scoped roles may only address their own venues, zones, rooms or screen groups."""
    if ann.all_screens:
        return may(user, ann.event, perm, request)
    objs = target_objects(ann)
    return bool(objs) and all(may(user, ann.event, perm, request, obj=o) for o in objs)


def needs_approval(ann: Announcement, user, request=None) -> bool:
    if ann.level.emergency:
        return False  # emergency bypasses approval for those allowed to send it (checked separately)
    if ann.level.requires_approval or ann_settings(ann.event).get("approval_required"):
        return True
    return not may_target(user, ann, "announcements.publish", request)


# ------------------------------------------------------------------ workflow
def _validate(ann: Announcement) -> None:
    if not ann.title.strip():
        raise ValidationError(_("A title is needed."))
    if ann.ends_at and ann.ends_at <= ann.starts_at:
        raise ValidationError(_("The end must be after the start."))
    if ann.recurrence and not ann.recurrence_until:
        raise ValidationError(_("Repeating announcements need a last day."))
    _validate_audiences(ann)
    _validate_anchor(ann)
    known = set(available_channels(ann.event))
    unknown = [c for c in ann.channels if c not in known]
    if unknown:
        raise ValidationError(_("Unknown channel: %(c)s") % {"c": ", ".join(unknown)})
    if not ann.channels:
        raise ValidationError(_("Choose at least one channel."))
    specs = registry.ensure_loaded().notification_channels
    for key, text in (ann.channel_texts or {}).items():
        if key == SPEECH:
            if not isinstance(text, str) or len(text) > SPEECH_MAX:
                raise ValidationError(_("The spoken text is too long (at most %(n)s characters).") % {"n": SPEECH_MAX})
            continue
        spec = specs.get(key)
        if spec is None or not isinstance(text, str):
            raise ValidationError(_("Unknown channel: %(c)s") % {"c": key})
        if spec.max_length and len(text) > spec.max_length:
            raise ValidationError(_("The text for %(c)s is too long (at most %(n)s characters).")
                                  % {"c": spec.name, "n": spec.max_length})


def save_draft(ann: Announcement, *, actor, request=None, m2m: dict | None = None) -> Announcement:
    if ann.status not in (Announcement.Status.DRAFT, Announcement.Status.PENDING, Announcement.Status.REJECTED):
        raise ValidationError(_("Only drafts can be edited."))
    if not (rbac_any(actor, ann.event, "announcements.draft", request)
            or rbac_any(actor, ann.event, "announcements.publish", request)
            or rbac_any(actor, ann.event, "announcements.emergency", request)):
        raise PermissionDenied
    _validate(ann)
    created = ann._state.adding
    if created:
        ann.created_by = actor
    ann.status = Announcement.Status.DRAFT
    with transaction.atomic():
        ann.save()
        for name, values in (m2m or {}).items():
            getattr(ann, name).set(values)
    log(action="announcement.drafted" if created else "announcement.edited", actor=actor, target=ann,
        event=ann.event, request=request, message=f"Announcement {ann.title}",
        changes={"level": ann.level.key, "channels": ann.channels, "target": ann.target_label()})
    return ann


def submit(ann: Announcement, *, actor, request=None) -> Announcement:
    """Send it: straight out when the sender may, otherwise into the approval queue."""
    if ann.status not in (Announcement.Status.DRAFT, Announcement.Status.REJECTED):
        raise ValidationError(_("Already submitted."))
    _validate(ann)
    if ann.level.emergency:
        if not may_target(actor, ann, "announcements.emergency", request):
            raise PermissionDenied(_("Emergency announcements need the emergency permission (two-factor session)."))
        return _approve(ann, actor=actor, request=request, note="emergency: no approval needed")
    if not may_target(actor, ann, "announcements.draft", request) and not may_target(
            actor, ann, "announcements.publish", request):
        raise PermissionDenied(_("You may not address these screens."))
    if needs_approval(ann, actor, request):
        ann.status = Announcement.Status.PENDING
        ann.submitted_at = timezone.now()
        ann.save(update_fields=["status", "submitted_at", "updated_at"])
        log(action="announcement.submitted", actor=actor, target=ann, event=ann.event, request=request,
            message=f"Announcement {ann.title} waits for approval")
        _notify_approvers(ann, actor)
        webhooks.emit("announcement.pending", payload(ann), event=ann.event)
        return ann
    return _approve(ann, actor=actor, request=request, note="")


def submit_external(ann: Announcement, *, source: str, publish_now: bool = False) -> Announcement:
    """An announcement made by an integration (e.g. recorded by phone in DIAL): into the approval queue, or, when
    the integration's allow-list says so, approved at once. Emergency levels always wait for a person."""
    if ann.level.emergency:
        publish_now = False
    _validate(ann)
    with transaction.atomic():
        ann.status = Announcement.Status.DRAFT
        ann.save()
        log(action="announcement.drafted", actor=None, target=ann, event=ann.event,
            message=f"Announcement {ann.title} from {source}",
            changes={"level": ann.level.key, "channels": ann.channels, "target": ann.target_label(),
                     "source": source})
        if publish_now:
            return _approve(ann, actor=None, note=f"{source}: published at once (allow-list)")
        ann.status = Announcement.Status.PENDING
        ann.submitted_at = timezone.now()
        ann.save(update_fields=["status", "submitted_at", "updated_at"])
        log(action="announcement.submitted", actor=None, target=ann, event=ann.event,
            message=f"Announcement {ann.title} from {source} waits for approval")
    _notify_approvers(ann, None)
    webhooks.emit("announcement.pending", payload(ann), event=ann.event)
    return ann


def approve(ann: Announcement, *, actor, request=None, note: str = "") -> Announcement:
    if ann.status != Announcement.Status.PENDING:
        raise ValidationError(_("Nothing to approve."))
    if ann.created_by_id == getattr(actor, "pk", None):
        raise PermissionDenied(_("Someone else has to approve your announcement."))
    if not may_target(actor, ann, "announcements.approve", request):
        raise PermissionDenied
    return _approve(ann, actor=actor, request=request, note=note)


def _approve(ann: Announcement, *, actor, request=None, note: str = "") -> Announcement:
    now = timezone.now()
    ann.decided_by, ann.decided_at, ann.decision_note = actor, now, note[:300]
    ann.status = Announcement.Status.SCHEDULED
    ann.save(update_fields=["status", "decided_by", "decided_at", "decision_note", "updated_at"])
    log(action="announcement.approved", actor=actor, target=ann, event=ann.event, request=request,
        message=f"Announcement {ann.title} approved" + (f" ({note})" if note else ""))
    if ann.created_by_id and ann.created_by_id != getattr(actor, "pk", None):
        from apps.core.notify import notify

        notify([ann.created_by], _("Your announcement was approved"), body=ann.title, event=ann.event,
               url=_url(ann), level="ok")
    queue_speech(ann)
    if ann.starts_at <= now:
        publish(ann, occurrence=ann.starts_at)
    else:
        _notify_screens(ann)  # screens know it in advance (their program covers the next days)
    return ann


def reject(ann: Announcement, *, actor, request=None, note: str = "") -> Announcement:
    if ann.status != Announcement.Status.PENDING:
        raise ValidationError(_("Nothing to reject."))
    if not may_target(actor, ann, "announcements.approve", request):
        raise PermissionDenied
    ann.status = Announcement.Status.REJECTED
    ann.decided_by, ann.decided_at, ann.decision_note = actor, timezone.now(), note[:300]
    ann.save(update_fields=["status", "decided_by", "decided_at", "decision_note", "updated_at"])
    log(action="announcement.rejected", actor=actor, target=ann, event=ann.event, request=request,
        message=f"Announcement {ann.title} rejected", changes={"note": note})
    if ann.created_by_id:
        from apps.core.notify import notify

        notify([ann.created_by], _("Your announcement was rejected"), body=f"{ann.title}: {note}".strip(": "),
               event=ann.event, url=_url(ann), level="warn")
    return ann


def cancel(ann: Announcement, *, actor, request=None) -> Announcement:
    if ann.status not in (Announcement.Status.SCHEDULED, Announcement.Status.LIVE, Announcement.Status.PENDING):
        raise ValidationError(_("Not active."))
    perm = "announcements.emergency" if ann.level.emergency else "announcements.publish"
    if not (may_target(actor, ann, perm, request) or ann.created_by_id == getattr(actor, "pk", None)):
        raise PermissionDenied
    ann.status = Announcement.Status.CANCELLED
    ann.cancelled_at = timezone.now()
    ann.save(update_fields=["status", "cancelled_at", "updated_at"])
    log(action="announcement.cancelled", actor=actor, target=ann, event=ann.event, request=request,
        message=f"Announcement {ann.title} cancelled")
    webhooks.emit("announcement.cancelled", payload(ann), event=ann.event)
    _notify_screens(ann)
    return ann


def delete_draft(ann: Announcement, *, actor, request=None) -> None:
    if ann.status not in (Announcement.Status.DRAFT, Announcement.Status.REJECTED):
        raise ValidationError(_("Only drafts can be deleted."))
    if ann.created_by_id != getattr(actor, "pk", None) and not rbac_any(actor, ann.event, "announcements.publish",
                                                                         request):
        raise PermissionDenied
    log(action="announcement.deleted", actor=actor, target=ann, event=ann.event, request=request,
        message=f"Draft {ann.title} deleted")
    ann.delete()


def save_level(level: Level, *, actor, request=None) -> Level:
    if not rbac_any(actor, level.event, "announcements.manage", request):
        raise PermissionDenied
    level.save()
    log(action="announcement_level.saved", actor=actor, target=level, event=level.event, request=request,
        message=f"Announcement level {level.name}",
        changes={"display": level.display, "sound": level.sound, "rank": level.rank,
                 "requires_approval": level.requires_approval, "default_channels": level.default_channels})
    return level


def save_template(template: Template, *, actor, request=None) -> Template:
    if not rbac_any(actor, template.event, "announcements.manage", request):
        raise PermissionDenied
    created = template._state.adding
    template.save()
    log(action="announcement_template.created" if created else "announcement_template.edited", actor=actor,
        target=template, event=template.event, request=request, message=f"Announcement template {template.name}")
    return template


def delete_template(template: Template, *, actor, request=None) -> None:
    if not rbac_any(actor, template.event, "announcements.manage", request):
        raise PermissionDenied
    log(action="announcement_template.deleted", actor=actor, target=template, event=template.event,
        request=request, message=f"Announcement template {template.name} deleted")
    template.delete()


def on_air_data(event) -> dict[str, Any]:
    """Data source for custom widgets: announcements on air (newest first)."""
    qs = (Announcement.objects.filter(event=event, status=Announcement.Status.LIVE).select_related("level")
          .order_by("-published_at")[:50])
    return {"announcements": [{"title": a.title, "text": a.text, "short": a.short_text, "level": a.level.name,
                               "colour": a.level.colour, "published": a.published_at.isoformat()
                               if a.published_at else None} for a in qs]}


# ------------------------------------------------------------------ public feed
def feed_title(event) -> str:
    return ann_settings(event).get("feed_title") or event.name


def feed_items(event, limit: int = 50) -> list[Announcement]:
    """Published (or recently ended) announcements that went to the feed channel, newest first."""
    qs = (Announcement.objects.filter(event=event, status__in=[Announcement.Status.LIVE, Announcement.Status.ENDED],
                                      published_at__isnull=False)
          .select_related("level").order_by("-published_at"))
    return [a for a in qs[:limit * 2] if FEED in a.channels][:limit]


# ------------------------------------------------------------------ audiences and time anchors (ADR-0025)
MAX_ANCHOR_OFFSET = 7 * 24 * 60  # minutes
PERSONAL_CHANNELS = {STAFF}  # channels that reach people and honour audiences


def _enabled(spec, event) -> bool:
    return spec.module == "core" or modules.is_enabled(spec.module, event)


def _sorted(specs):
    return sorted(specs.values(), key=lambda s: (s.order, s.key))


def audience_choices(event) -> list[tuple[str, str]]:
    """Groups channels that reach people can be limited to: ``("roles:<id>", "Role: Orga")``."""
    out: list[tuple[str, str]] = []
    for spec in _sorted(registry.ensure_loaded().audiences):
        if _enabled(spec, event):
            out += [(f"{spec.key}:{i}", f"{spec.title}: {label}") for i, label in spec.choices(event)]
    return out


def audience_labels(ann: Announcement) -> list[str]:
    names = dict(audience_choices(ann.event)) if ann.audiences else {}
    return [names.get(a, a) for a in ann.audiences or []]


def audience_members(ann: Announcement) -> set | None:
    """The people the audiences cover (``None``: no audiences chosen, everybody the channel reaches)."""
    if not ann.audiences:
        return None
    wanted: dict[str, set[str]] = {}
    for value in ann.audiences:
        kind, _sep, ident = str(value).partition(":")
        wanted.setdefault(kind, set()).add(ident)
    specs = registry.ensure_loaded().audiences
    users: set = set()
    for kind, ids in wanted.items():
        spec = specs.get(kind)
        if spec is not None and _enabled(spec, ann.event):
            users |= set(spec.members(ann.event, ids))
    return users


def _validate_audiences(ann: Announcement) -> None:
    if not isinstance(ann.audiences, list) or not all(isinstance(a, str) for a in ann.audiences):
        raise ValidationError(_("Audiences must be a list."))
    if ann.audiences:
        unknown = set(ann.audiences) - set(dict(audience_choices(ann.event)))
        if unknown:
            raise ValidationError(_("Unknown audience: %(a)s") % {"a": ", ".join(sorted(unknown))})
        if not set(ann.channels) & PERSONAL_CHANNELS:
            raise ValidationError(_("Audiences only apply to staff notifications: choose that channel too."))


def anchor_choices(event) -> list[tuple[str, str]]:
    """Time anchors announcements can be scheduled relative to: ``("<source>:<id>", "Talk: Opening")``."""
    out: list[tuple[str, str]] = []
    for spec in _sorted(registry.ensure_loaded().anchor_sources):
        if _enabled(spec, event):
            out += [(f"{spec.key}:{i}", f"{spec.title}: {label}") for i, label in spec.choices(event)]
    return out


def resolve_anchor(event, value: str):
    source, _sep, ident = (value or "").partition(":")
    spec = registry.ensure_loaded().anchor_sources.get(source)
    if spec is None or not ident or not _enabled(spec, event):
        return None
    return spec.resolve(event, ident)


def apply_anchor(ann: Announcement) -> bool:
    """Move ``starts_at`` (and ``ends_at``, keeping the duration) to the anchor time plus the offset. Returns
    whether the times changed; raises ``ValidationError`` when the anchor is gone."""
    anchor = resolve_anchor(ann.event, ann.anchor)
    if anchor is None or anchor.start is None:
        raise ValidationError(_("The item this announcement is timed relative to no longer exists."))
    base = anchor.end if ann.anchor_edge == "end" and anchor.end else anchor.start
    when = base + dt.timedelta(minutes=ann.anchor_offset)
    ann.anchor_label = str(anchor.label or "")[:200]
    if when == ann.starts_at:
        return False
    if ann.ends_at and ann.starts_at:
        ann.ends_at = ann.ends_at + (when - ann.starts_at)
    ann.starts_at = when
    return True


def _validate_anchor(ann: Announcement) -> None:
    if not ann.anchor:
        ann.anchor_label = ""
        return
    if ann.recurrence:
        raise ValidationError(_("Announcements timed relative to an item cannot repeat."))
    if ann.anchor_edge not in ("start", "end") or abs(int(ann.anchor_offset or 0)) > MAX_ANCHOR_OFFSET:
        raise ValidationError(_("The offset may be at most a week."))
    apply_anchor(ann)


def anchor_text(ann: Announcement) -> str:
    """ "10 min before the start of Opening" """
    if not ann.anchor:
        return ""
    minutes, edge = abs(ann.anchor_offset), (_("the start") if ann.anchor_edge == "start" else _("the end"))
    label = ann.anchor_label or ann.anchor
    if not minutes:
        return _("at %(edge)s of %(label)s") % {"edge": edge, "label": label}
    when = _("before") if ann.anchor_offset < 0 else _("after")
    return _("%(m)s min %(when)s %(edge)s of %(label)s") % {"m": minutes, "when": when, "edge": edge,
                                                            "label": label}


def anchor_moved(sender, *, event, anchor_id, **kwargs) -> int:
    """Signal ``apps.core.signals.anchor_moved``: announcements not yet sent follow their anchor."""
    moved = 0
    waiting = [Announcement.Status.DRAFT, Announcement.Status.PENDING, Announcement.Status.SCHEDULED,
               Announcement.Status.REJECTED]
    for ann in Announcement.objects.filter(event=event, anchor=f"{sender}:{anchor_id}", status__in=waiting
                                           ).select_related("level", "event"):
        before = ann.starts_at
        try:
            changed = apply_anchor(ann)
        except ValidationError:
            log(action="announcement.anchor_lost", target=ann, event=event,
                message=f"Announcement {ann.title}: the item it is timed relative to is gone; it keeps its time")
            continue
        ann.save(update_fields=["starts_at", "ends_at", "anchor_label", "updated_at"])
        if changed:
            moved += 1
            log(action="announcement.rescheduled", target=ann, event=event,
                message=f"Announcement {ann.title} follows {ann.anchor_label or ann.anchor}",
                changes={"starts_at": [before.isoformat(), ann.starts_at.isoformat()]})
            if ann.status == Announcement.Status.SCHEDULED:
                _notify_screens(ann)
    return moved


# ------------------------------------------------------------------ timing
def duration(ann: Announcement) -> dt.timedelta | None:
    """How long one occurrence lasts (None: until cancelled)."""
    if ann.ends_at and not ann.recurrence:
        return ann.ends_at - ann.starts_at
    if ann.ends_at and ann.recurrence:
        return min(ann.ends_at - ann.starts_at, dt.timedelta(hours=23))
    if ann.level.repeat_every_minutes:
        return None
    return dt.timedelta(seconds=ann.level.min_display_seconds)


def occurrences(ann: Announcement, start: dt.datetime, end: dt.datetime) -> list[dt.datetime]:
    """Start times of the occurrences that overlap [start, end)."""
    step = {"daily": dt.timedelta(days=1), "weekly": dt.timedelta(days=7)}.get(ann.recurrence)
    length = duration(ann)
    last_day = ann.recurrence_until
    out, t = [], ann.starts_at
    for _i in range(400):
        if t >= end or (step and last_day and t.date() > last_day):
            break
        if length is None or t + length > start:
            out.append(t)
        if not step:
            break
        t += step
    return out


def screen_windows(ann: Announcement, start: dt.datetime, end: dt.datetime) -> list[list[dt.datetime | None]]:
    """When it is visible on screens: per occurrence, or every N minutes for the level's display time."""
    out: list[list[dt.datetime | None]] = []
    length = duration(ann)
    show = dt.timedelta(seconds=ann.level.min_display_seconds)
    every = dt.timedelta(minutes=ann.level.repeat_every_minutes) if ann.level.repeat_every_minutes else None
    for occ in occurrences(ann, start, end):
        stop = occ + length if length is not None else None
        if every and ann.level.display != Level.Display.TAKEOVER:
            t = occ
            while t < end and (stop is None or t < stop) and len(out) < 500:
                if t + show > start:
                    out.append([t, min(t + show, stop) if stop else t + show])
                t += every
        else:
            out.append([occ, stop])
    return out


# ------------------------------------------------------------------ screens
def _ms(value: dt.datetime | None) -> int | None:
    return None if value is None else int(value.timestamp() * 1000)


def applies_to(ann: Announcement, target) -> bool:
    if ann.all_screens:
        return True
    screen = getattr(target, "screen", None)
    if screen is not None:
        return (any(s.pk == screen.pk for s in ann.screens.all())
                or bool(target.group_ids & {g.pk for g in ann.screen_groups.all()})
                or (screen.venue_id is not None and any(v.pk == screen.venue_id for v in ann.venues.all()))
                or (screen.zone_id is not None and any(z.pk == screen.zone_id for z in ann.zones.all()))
                or (screen.room_id is not None and any(r.pk == screen.room_id for r in ann.rooms.all())))
    return bool(target.group_ids & {g.pk for g in ann.screen_groups.all()})


def text_on(colour: str) -> str:
    """Black or white, whichever has the higher contrast on ``colour`` (twin of the player's ``textOn``)."""
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", colour or ""):
        return "#ffffff"

    def lin(h: str) -> float:
        c = int(h, 16) / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    lum = 0.2126 * lin(colour[1:3]) + 0.7152 * lin(colour[3:5]) + 0.0722 * lin(colour[5:7])
    return "#000000" if lum > 0.179 else "#ffffff"


def takeover_layout(ann: Announcement, width: int = 1920, height: int = 1080) -> dict[str, Any]:
    """Full-screen display: the template's layout (texts filled in) or a built-in card in the level colour."""
    lay = ann.template.layout if ann.template_id and ann.template and ann.template.layout_id else None
    if lay is not None and lay.published_id:
        import json

        text = json.dumps(lay.published.data)
        for key, value in (("announcement.title", ann.title), ("announcement.text", ann.text),
                           ("announcement.short", ann.short_text)):
            text = re.sub(r"\{\{\s*" + re.escape(key) + r"\s*\}\}", json.dumps(value)[1:-1], text)
        return json.loads(text)
    fg = text_on(ann.level.colour)
    return {"format": 1, "width": width, "height": height, "background": {"color": ann.level.colour},
            "elements": [
                {"id": "level", "type": "text", "name": "Level", "frame": {"x": 6, "y": 8, "w": 60, "h": 8},
                 "style": {"fontSize": 4.5, "fontWeight": 700, "color": fg, "textTransform": "uppercase",
                           "letterSpacing": 0.15, "textAlign": "left"},
                 "props": {"text": ann.level.name, "autofit": True}},
                {"id": "title", "type": "text", "name": "Title", "frame": {"x": 6, "y": 18, "w": 88, "h": 24},
                 "style": {"fontFamily": "token:heading", "fontSize": 11, "fontWeight": 800, "color": fg,
                           "textAlign": "left"},
                 "props": {"text": ann.title, "autofit": True, "clamp": 2}},
                {"id": "text", "type": "text", "name": "Text", "frame": {"x": 6, "y": 46, "w": 88, "h": 40},
                 "style": {"fontSize": 6, "color": fg, "lineHeight": 1.3, "textAlign": "left"},
                 "props": {"text": ann.body, "autofit": True}},
                {"id": "clock", "type": "clock", "name": "Clock", "frame": {"x": 74, "y": 88, "w": 20, "h": 8},
                 "style": {"fontSize": 4.5, "textAlign": "right", "color": fg, "tabularNumbers": True},
                 "props": {"format": "HH:mm"}},
            ]}


def program_source(event, target, start: dt.datetime, end: dt.datetime) -> dict[str, Any]:
    """Announcements for one screen's program: takeovers as entries, the rest as overlays (banner, ticker,
    card). Registered with ``r.program_source``."""
    out: dict[str, Any] = {"entries": [], "messages": {}, "overlays": []}
    if not modules.is_enabled("announcements", event):
        return out
    qs = (Announcement.objects.filter(event=event, status__in=[Announcement.Status.SCHEDULED,
                                                                Announcement.Status.LIVE])
          .select_related("level", "template__layout__published")
          .prefetch_related("venues", "zones", "rooms", "screen_groups", "screens"))
    for ann in qs:
        if SCREENS not in ann.channels or not applies_to(ann, target):
            continue
        windows = [[_ms(a), _ms(b)] for a, b in screen_windows(ann, start, end)]
        if not windows:
            continue
        key = f"announcement:{ann.pk}"
        speech = speech_url(ann, getattr(target, "screen", None))
        if ann.level.display == Level.Display.TAKEOVER or ann.level.emergency:
            screen = getattr(target, "screen", None)
            portrait = screen is not None and (screen.reported or {}).get("orientation") == "portrait"
            out["entries"].append({"id": key, "source": "announcement", "name": ann.title,
                                   "priority": ann.level.screen_priority, "level": ann.level.key,
                                   "content": {"message": key}, "windows": windows,
                                   **({"speech": speech} if speech else {})})
            out["messages"][key] = takeover_layout(ann, *((1080, 1920) if portrait else (1920, 1080)))
        else:
            out["overlays"].append({"id": key, "style": ann.level.display, "rank": ann.level.rank,
                                    "level": ann.level.name, "colour": ann.level.colour, "sound": ann.level.sound,
                                    "title": ann.title, "text": ann.text if ann.level.display == "card"
                                    else ann.short_text, "windows": windows,
                                    **({"speech": speech} if speech else {})})
    return out


# ------------------------------------------------------------------ speech (ADR-0022)
def speech_text(ann: Announcement) -> str:
    own = (ann.channel_texts or {}).get(SPEECH, "").strip()
    if own:
        return own
    parts = [ann.level.name, ann.title] + ([ann.body] if ann.body and ann.body != ann.title else [])
    return ". ".join(p.strip().rstrip(".") for p in parts if p.strip()) + "."


def queue_speech(ann: Announcement) -> None:
    """Render the spoken version ahead of time (when the level speaks and the announcement goes to screens)."""
    from . import tts

    if ann.speech_recorded and ann.speech_file:
        return  # a recording is played as it is
    if not ann.level.speak or SCREENS not in ann.channels:
        return
    usable, why = tts.status(ann_settings(ann.event).get("tts_voice", ""))
    if not usable:
        Announcement.objects.filter(pk=ann.pk).update(speech_status=Announcement.Speech.UNAVAILABLE, speech_detail=why)
        ann.speech_status, ann.speech_detail = Announcement.Speech.UNAVAILABLE, why
        return
    Announcement.objects.filter(pk=ann.pk).update(speech_status=Announcement.Speech.PENDING, speech_detail="")
    ann.speech_status = Announcement.Speech.PENDING
    outbox.enqueue(SPEECH_JOB, {"announcement": str(ann.pk)}, event=ann.event, key=f"speech:{ann.pk}:{ann.updated_at}")


SPEECH_JOB = "announcements.speech"


def render_speech(job) -> None:
    """Outbox handler: run Piper (minutes at most), then tell the screens."""
    from . import tts

    ann = Announcement.objects.select_related("level", "event").filter(pk=job.payload["announcement"]).first()
    if ann is None:
        job.result = {"skipped": "announcement gone"}
        return
    try:
        name = tts.render(speech_text(ann), ann_settings(ann.event).get("tts_voice", ""))
    except tts.SpeechError as exc:
        Announcement.objects.filter(pk=ann.pk).update(speech_status=Announcement.Speech.FAILED,
                                                      speech_detail=str(exc)[:300])
        job.result = {"failed": str(exc)}
        return
    Announcement.objects.filter(pk=ann.pk).update(speech_status=Announcement.Speech.READY, speech_file=name,
                                                  speech_detail="")
    job.result = {"file": name}
    _notify_screens(ann)


def _speech_sig(screen_id, name: str) -> str:
    from django.utils.crypto import salted_hmac

    return salted_hmac("evac.announcements.speech", f"{screen_id}:{name}").hexdigest()[:32]


def speech_url(ann: Announcement, screen=None) -> str:
    """Player URL of the spoken file (signed per screen, so <audio> and the service worker can fetch it)."""
    from django.urls import reverse

    if ann.speech_status != Announcement.Speech.READY or not ann.speech_file:
        return ""
    url = reverse("announcements_player:speech", args=[ann.speech_file])
    return f"{url}?s={screen.pk}.{_speech_sig(screen.pk, ann.speech_file)}" if screen is not None else url


def screen_for_speech(value: str, name: str):
    from django.utils.crypto import constant_time_compare

    from apps.screens.models import Screen

    screen_id, _sep, sig = (value or "").partition(".")
    if not sig or not constant_time_compare(sig, _speech_sig(screen_id, name)):
        return None
    try:
        return Screen.objects.paired().select_related("event").filter(pk=screen_id).first()
    except (ValueError, ValidationError):
        return None


def _notify_screens(ann: Announcement) -> None:
    if SCREENS not in ann.channels:
        return
    from apps.screens import channel
    from apps.screens.models import Screen

    def send():
        for screen in Screen.objects.paired().filter(event=ann.event):
            channel.send(screen, "program.changed", {})
    transaction.on_commit(send)


# ------------------------------------------------------------------ delivery
def available_channels(event) -> dict[str, str]:
    """Channels this event can use: built-ins plus registered ones whose module is on."""
    out = {}
    for key, spec in registry.ensure_loaded().notification_channels.items():
        if spec.module != "core" and not modules.is_enabled(spec.module, event):
            continue
        if spec.available is not None and not spec.available(event):
            continue
        out[key] = spec.name
    return out


def text_for(ann: Announcement, channel: str, limit: int = 0) -> str:
    """The text for one channel: its own text if written, else title and text; cut to ``limit`` characters."""
    own = (ann.channel_texts or {}).get(channel, "").strip()
    text = own or (ann.title if not ann.body or ann.body == ann.title else f"{ann.title}\n\n{ann.body}")
    if limit and len(text) > limit:
        text = text[:limit - 1].rstrip() + "…"
    return text


def publish(ann: Announcement, *, occurrence: dt.datetime) -> list[Delivery]:
    """Deliver one occurrence through every chosen channel (each a Delivery row, sent via the outbox)."""
    first = ann.status != Announcement.Status.LIVE
    ann.status = Announcement.Status.LIVE
    ann.published_at = ann.published_at or timezone.now()
    ann.last_occurrence = occurrence
    ann.save(update_fields=["status", "published_at", "last_occurrence", "updated_at"])
    if first:
        log(action="announcement.published", actor=ann.decided_by, target=ann, event=ann.event,
            message=f"Announcement {ann.title} published",
            changes={"level": ann.level.key, "channels": ann.channels, "target": ann.target_label()})
    _publish_live(ann, occurrence)
    deliveries = []
    for channel_key in ann.channels:
        d, created = Delivery.objects.get_or_create(announcement=ann, channel=channel_key, occurrence=occurrence)
        if created:
            outbox.enqueue("announcements.deliver", {"delivery": str(d.pk)}, event=ann.event,
                           key=f"announcement:{d.pk}")
        deliveries.append(d)
    return deliveries


def _publish_live(ann: Announcement, occurrence: dt.datetime) -> None:
    """Tell open staff pages (realtime stream); urgent and emergency levels raise the full-screen alert there."""
    from apps.core import realtime

    data = {"id": str(ann.pk), "title": ann.title, "text": ann.text, "level": ann.level.key,
            "alert": ann.level.emergency or ann.level.rank >= 30, "url": _url(ann),
            "occurrence": occurrence.isoformat()}
    transaction.on_commit(lambda: realtime.publish(ann.event, "announcement.live", data))


def deliver(job) -> None:
    """Outbox handler: send one Delivery through its channel and record the result."""
    d = Delivery.objects.select_related("announcement__level", "announcement__event").get(pk=job.payload["delivery"])
    spec = registry.ensure_loaded().notification_channels.get(d.channel)
    d.attempts += 1
    if spec is None or spec.send is None:
        d.status, d.detail = Delivery.Status.SKIPPED, "channel not available"
        d.save(update_fields=["status", "detail", "attempts"])
        return
    try:
        result = spec.send(d) or {}
    except Exception as exc:
        d.status, d.detail = Delivery.Status.FAILED, f"{type(exc).__name__}: {exc}"[:500]
        d.save(update_fields=["status", "detail", "attempts"])
        raise
    d.status = Delivery.Status(result.get("status", Delivery.Status.SENT))
    d.recipients = int(result.get("recipients", 0))
    d.detail = str(result.get("detail", ""))[:500]
    d.sent_at = timezone.now()
    d.save(update_fields=["status", "recipients", "detail", "sent_at", "attempts"])
    job.result = {"recipients": d.recipients, "detail": d.detail}


def payload(ann: Announcement) -> dict[str, Any]:
    return {"id": str(ann.pk), "event": ann.event.slug, "level": ann.level.key, "title": ann.title,
            "text": ann.text, "short": ann.short_text, "status": ann.status,
            "starts_at": ann.starts_at.isoformat(), "ends_at": ann.ends_at.isoformat() if ann.ends_at else None}


# built-in channels --------------------------------------------------------
def send_screens(d: Delivery) -> dict[str, Any]:
    from apps.playlists.services import Target
    from apps.screens.models import Screen

    ann = d.announcement
    screens = [s for s in Screen.objects.paired().filter(event=ann.event).select_related("venue", "zone", "room")
               if applies_to(ann, Target(screen=s))]
    _notify_screens(ann)
    return {"recipients": len(screens), "detail": _("%(n)s screens") % {"n": len(screens)}}


def send_feed(d: Delivery) -> dict[str, Any]:
    on = ann_settings(d.announcement.event).get("public_feed")
    if not on:
        return {"status": Delivery.Status.SKIPPED, "detail": _("The public feed is switched off.")}
    return {"recipients": 0, "detail": _("on the public feed")}


def send_webhook(d: Delivery) -> dict[str, Any]:
    webhooks.emit("announcement.published", {**payload(d.announcement), "occurrence": d.occurrence.isoformat()},
                  event=d.announcement.event)
    return {"detail": _("sent to the webhook endpoints")}


def staff_recipients(event) -> list:
    from apps.events.models import Membership

    users = [m.user for m in Membership.objects.filter(event=event).select_related("user") if m.user.is_active]
    return [u for u in users if reachable(u, event, "announcements.view")]


def send_staff(d: Delivery) -> dict[str, Any]:
    from apps.core.notify import notify

    ann = d.announcement
    users = staff_recipients(ann.event)
    audience = audience_members(ann)
    if audience is not None:
        users = [u for u in users if u in audience]
    level = "err" if ann.level.emergency else ("warn" if ann.level.rank >= 30 else "info")
    n = notify(users, f"{ann.level.name}: {ann.title}", body=ann.text, url=_url(ann), level=level, event=ann.event)
    return {"recipients": n, "detail": _("%(n)s staff members") % {"n": n}}


def _url(ann: Announcement) -> str:
    from django.urls import reverse

    return reverse("announcements:detail", args=[ann.event.slug, ann.pk])


def _notify_approvers(ann: Announcement, actor) -> None:
    from apps.core.notify import notify
    from apps.events.models import Membership

    users = [m.user for m in Membership.objects.filter(event=ann.event).select_related("user")
             if m.user_id != getattr(actor, "pk", None) and reachable(m.user, ann.event, "announcements.approve")]
    notify(users, _("Announcement waiting for approval"), body=ann.title, url=_url(ann), level="warn",
           event=ann.event)


# ------------------------------------------------------------------ scheduler
def publish_due(now: dt.datetime | None = None) -> int:
    """Beat task: send scheduled announcements and new occurrences of repeating ones; end finished ones."""
    now = now or timezone.now()
    n = 0
    for ann in (Announcement.objects.filter(status__in=[Announcement.Status.SCHEDULED, Announcement.Status.LIVE],
                                            starts_at__lte=now).select_related("level", "event")):
        if ann.anchor and ann.status == Announcement.Status.SCHEDULED and _anchor_moved_later(ann, now):
            continue
        due = [o for o in occurrences(ann, ann.starts_at, now + dt.timedelta(seconds=1)) if o <= now]
        latest = due[-1] if due else None
        if latest and (ann.last_occurrence is None or latest > ann.last_occurrence):
            publish(ann, occurrence=latest)
            n += 1
        length = duration(ann)
        finished = (ann.recurrence and ann.recurrence_until and now.date() > ann.recurrence_until) or (
            not ann.recurrence and length is not None and now >= ann.starts_at + length)
        if ann.status == Announcement.Status.LIVE and finished:
            ann.status = Announcement.Status.ENDED
            ann.save(update_fields=["status", "updated_at"])
    return n


def _anchor_moved_later(ann: Announcement, now: dt.datetime) -> bool:
    """Last look at the anchor before sending (it may have moved without a signal)."""
    try:
        changed = apply_anchor(ann)
    except ValidationError:
        return False  # anchor gone: send at the last known time
    if changed:
        ann.save(update_fields=["starts_at", "ends_at", "anchor_label", "updated_at"])
    return ann.starts_at > now
