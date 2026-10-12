# ADR-0050: Event setup wizard and setup checklist

- Status: Accepted
- Date: 2026-10-12

## Context

*New event* was one long form (name, dates, colours, logo, venues). Everything that makes an event usable — the
modules it needs, the evacuation safety statement, people, a first layout and screen — lived on half a dozen other
pages that new organisers had to find on their own. The first-run wizard (brief §5, roadmap 0.6.2/1.5.4) solved
this once per instance, not per event. Nothing told an organiser later what was still missing.

Forces: every module is a plugin and the core must not import optional modules (ADR-0001); state changes go through
services and the audit log; evacuation behaviour must not change (brief §8) and its statement must be accepted once
per event before the module works (roadmap 3.11); alarm permissions only work in two-factor verified sessions.

## Decision

**Wizard.** `/events/new/` (instance admins, as before) is step 1 of a guided wizard:

1. *Basics* (name, short name, description, time zone, dates; `EventBasicsForm` over `EventForm`). The event is
   created at the end of this step through `services.create_event`; *Create and skip the wizard* goes straight to
   the overview.
2. *Venue*: link existing venues (all for instance admins, as on the venues page; others keep or drop linked ones)
   and/or quick-create one (`VenueForm`, `venues.manage`).
3. *Event type*: presets that switch modules on for the event — *Conference*, *Festival / camp*, *Venue screens
   only* — or *Custom* (a checkbox per module). Presets list what they switch on. They only decide about the
   modules some preset names; extensions and third-party modules are left as they are.
4. *Safety* (only when a module with a statement, i.e. evacuation, was chosen or is on): the statement
   (`ModuleSpec.acknowledgement`), a tick box to accept it (`modules.acknowledge`), and the user's two-factor
   status with a link to the security page.
5. *Team*: invite by e-mail with a role (the members page's logic, now `admin_views.invite_member`).
6. *Screens*: pick a gallery template (posted to `content:templates` with `publish=1` and `next=`, so the content
   module creates and publishes the layout through its own services) and pair a screen (`screens:pair?next=`).
7. *Done* → overview.

Later steps live at `/e/<event>/setup/<step>/` (`events.manage`) and work on the real event. Steps the user may not
do (`modules.manage`, `events.members`, `content.edit`/`screens.pair`) or that do not apply are left out. The current
step and the modules waiting for their statement are kept in the session (`evac_event_setup`), so
`/e/<event>/setup/` resumes; every step has Back, optional steps have Skip, and *Leave the wizard* goes to the overview.

Module switching is shared with the first-run wizard in `apps.core.modules`: `blocked_reason(key, user)` (a module
off for the instance can only be switched on by an instance admin, who switches it on at instance level too — as
the first-run wizard always did), `with_dependencies()`, `switch_on()` (dependencies first) and `apply_selection()`
(the wizard's preset: on/off/unavailable/pending). A module with a statement nobody accepted for the event stays off
("pending") until the safety step accepts it; nothing about evacuation behaviour changes.

**Checklist.** Plugin API 6 adds `r.setup_check(SetupCheckSpec(key, label, check, module=, order=, url_name=, url=,
help=, optional=))`; `check(event, request)` returns `"done"`, `"todo"`, a `SetupResult(status, detail, url)` or
`None` (not relevant). `apps.core.setup` collects them: checks of modules that are off are not called, a failing
check is logged and skipped. The owning apps register: venue linked and zones/exits drawn (venues), statement
accepted (evacuation), screen paired (screens), layout published (content), team invited and two-factor for everyone
holding a role with sensitive permissions (events), a staff notification channel (notify, `optional`).

The overview shows the card to `events.manage` holders while a required item is open. Optional items never keep it
on the page. It can be hidden per event: the event-level setting `setup.checklist_hidden` (a settings namespace,
so it is audit-logged, needs no migration and can be switched back under *Event settings → Setup checklist*).

## Consequences

- New events get a short, skippable path to a working setup; existing pages stay the single place for details.
- Plugins add their own checklist items without core changes; each check costs one or two queries per overview view
  of an organiser.
- An instance admin choosing evacuation (off for the server by default) switches it on for the server; other events
  then show it too, still behind their own statement. The wizard says so before applying.
- Clones and imports copy event settings, so a hidden checklist stays hidden in a clone.
- The template gallery view accepts `publish` and `next`; `next` is checked with `safe_next`.

## Alternatives considered

- **Pluggable wizard steps** (`r.setup_step`): more general, but the step list is short and opinionated; reaching
  optional modules through their URLs keeps the core free of imports without a second new contribution type.
- **A model for the hidden flag** (or a field on `Event`): a migration for one boolean; the settings framework
  already stores, audits, exports and edits per-event values.
- **Keeping the wizard state in the database**: resuming across devices is not worth a model; the checklist already
  shows what is missing from any device.
