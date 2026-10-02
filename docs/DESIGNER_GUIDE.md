# Designer Guide

> **Status:** the designer (themes, fonts, assets, layout editor, widgets, code mode) ships in **phase 1**.

What exists in phase 0 that designers will use:

- **Event branding**: name, logo, primary and accent colour (*Event settings*); the portal already uses
  them, screens will use them as the default theme tokens.
- **Settings inheritance** (instance → venue → event → screen group → screen) for display settings such as
  the heartbeat interval; screen-level settings (resolution, rotation, overscan, …) arrive with screens.
- **Widget and data source contracts** in the plugin API (`WidgetSpec`, `DataSourceSpec`): every module and
  extension can contribute widgets and data sources; the editor (phase 1) builds its widget palette and
  settings forms from them.

Planned (see [the roadmap](ROADMAP.md), epic 1.3): themes as design tokens compiled to CSS custom
properties, self-hosted fonts (incl. variable fonts and Atkinson Hyperlegible for evacuation content), a
content-hashed asset library, the visual layout editor with responsive constraints, versioning and
scheduled publishing, template variables, and a sandboxed code mode.
