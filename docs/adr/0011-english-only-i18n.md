# ADR-0011: English-only build with translatable strings

- Status: Accepted
- Date: 2026-10-02

## Decision

`LANGUAGES = [("en", "English")]`, no `locale/` directory, no catalogs, no language switcher (brief §0
rule 6, §13). All Python strings go through `gettext`/`gettext_lazy`, templates use `{% trans %}` /
`{% blocktrans %}`, JavaScript contains no user-facing strings (they come from `data-*` attributes), so a
locale can be added later with `makemessages` without refactoring. Operator-entered content may be in
any language and script (RTL rendering is a layout feature, Phase 1).
