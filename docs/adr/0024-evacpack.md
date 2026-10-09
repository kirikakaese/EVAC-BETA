# ADR-0024: Screen packs (`.evacpack`)

- Status: Accepted
- Date: 2026-10-10

## Context

Roadmap ticket 2.10 and brief §5.4: export and import layouts, themes, widget configs and whole "screen packs"
as signed `.evacpack` files (zip + manifest + assets + hashes), a gallery of built-in packs and optional import
from a URL. Brief §12 lists signed packs as a security control: a pack can put content on every screen.

## Decision

- **Format** (`apps/packs/packfile.py`, version 1): a zip with exactly `manifest.json`, `files/<sha256>` and an
  optional `signature.json`. The manifest holds the items of each section as JSON and the hash and size of every
  file. The signature is Ed25519 over the exact manifest bytes, so it covers every file through the hashes.
  Reading refuses anything else: unknown or duplicate entries, files not listed or listed but missing, wrong
  hashes, a bad signature, an unknown format version, more than the configured size (entries are read with a
  limit; the zip headers are not trusted).
- **Keys and trust**: each server has one signing key (created on first export, private key encrypted with
  `apps.core.crypto`). Instance admins trust other servers' public keys under *Settings → Pack keys* (fingerprint
  shown on both sides). A pack is *built in* (gallery), *signed by a trusted key* (or this server's), *signed by
  an unknown key* or *not signed*. The last two need an explicit confirmation; the instance setting *Only import
  packs signed by a trusted key* refuses them. A broken signature or hash always refuses the pack.
- **Sections are plugins**: `r.pack_section(PackSectionSpec(key, title, choices, requires, dump, load, module,
  order))`. Content registers files, fonts, themes and layouts; widgets registers feeds and custom widgets;
  playlists registers playlists. Export follows `requires` to a fixpoint (a playlist brings its layouts, a layout
  its files, fonts, theme and custom widgets, a widget its feed; `"*"` asks every section about UUIDs inside
  layout properties, so the content module does not know about widgets).
- **Import creates copies through the module services**: every object gets a new id (and a free key or name);
  `ctx.ids` maps pack ids to new ids and `ctx.remap` rewrites references in layout data and theme tokens. The
  services validate and audit-log as for manual edits, so layouts with code still need `content.code`, data feed
  URLs still pass the SSRF check, and nothing existing is overwritten. The whole import is one transaction;
  skipped parts (a feed URL that is not allowed, a missing built-in font) become notes on the result.
- **Not packed**: secrets (feed authorization headers: the importer is told to add them), fetched feed data,
  schedules and overrides (they target this event's screens and times), built-in fonts (referenced by name).
- **Staged review**: uploads, URL downloads (a Celery task with the core's safe fetcher, `apps.core.safefetch`,
  moved there from the widgets module) and gallery picks become a `PackImport` that shows origin, fingerprint,
  contents and a preview of the first layout before anything is created. Files are removed after the import or
  after seven days.
- **Gallery**: JSON files in `apps/packs/gallery/` in the manifest format, built into a pack when chosen.
- `manage.py evac_pack key|verify|export|import` for scripts.

## Consequences

- Packs move between events and servers without a shared library; an instance-wide library of packs and a
  public template gallery remain for phase 9.
- Imported pictures and videos are processed again on the target (variants are not packed).
- New content types only need a section in their own module.
