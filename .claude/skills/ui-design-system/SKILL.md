---
name: ui-design-system
description: >-
  Apply the thebots.lab UI design system so the Extractor dashboard stays visually consistent
  with WhatsApp-bot. Use when adding or changing HTML, CSS, Jinja templates, components, pages,
  themes, buttons, forms, tables, or copy in app/templates or app/static; or when the user
  mentions UI, design system, restyle, frontend, or dashboard.
---

# UI Design System

Read and follow **`design-system/AGENTS.md`** before editing any dashboard UI.

Then open only what you need:

- Tokens: `design-system/tokens.md`
- Class catalog: `design-system/components.md`
- Page recipes: `design-system/patterns.md`
- Copy: `design-system/i18n.md`

Implemented CSS: `app/static/style.css`. Theme: `app/static/theme.js`.

Do not add a second stylesheet. Do not hardcode colors. If you add a token or component, update `design-system/` in the same change.
