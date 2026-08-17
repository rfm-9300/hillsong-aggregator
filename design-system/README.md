# thebots.lab UI Design System (Extractor)

Same visual system as the WhatsApp-bot dashboards. Agents and LLMs must follow this folder when adding or changing HTML, CSS, or templates in this repo.

**Implemented CSS lives in** [`app/static/style.css`](../app/static/style.css). This folder documents it. Do not invent a parallel visual language.

## Read this first

| File | When to open it |
|---|---|
| [AGENTS.md](AGENTS.md) | **Always** — hard rules, do/don't, checklist |
| [tokens.md](tokens.md) | Colors, type, radius, elevation, motion |
| [components.md](components.md) | Class catalog + copy-paste HTML |
| [patterns.md](patterns.md) | Page recipes (compact shell, form, table, job detail) |
| [i18n.md](i18n.md) | User-facing copy |

## Surfaces

| Surface | Files | Stylesheet |
|---|---|---|
| Dashboard | `app/templates/` (`base.html`, `index.html`, `watch.html`, `job.html`, `edit.html`, `settings.html`) | `/static/style.css` |
| CLI | `extract_sermon.py`, `sermon_cut/` | **out of scope** (no web UI) |

Auth is HTTP Basic (browser dialog). There is no HTML login page.

## How this stays in sync with WhatsApp-bot

Tokens, fonts, and class names (`btn`, `panel`, `tbl`, `pill`, `form`, `inp`, `lbl`, …) match `/Users/rodrigomartins/projects/Whatsapp-bot/design-system/`.

Extractor uses a **compact shell** (topbar + centered `.view`, no sidebar). Do not add a CRM sidebar unless the product grows more than a handful of pages.

## Visual identity (two themes)

- **Light (default)** — soft paper, rounded, pastel blobs, violet accent `#7c5cfc`. Fonts: Outfit (display) + Nunito (UI) + JetBrains Mono.
- **Dark** — thebots.lab terminal: `#0b0d0f` canvas, yellow accent `#ffd60a`, 32px hairline grid.

Theme is a token swap via `html[data-theme]` and `app/static/theme.js` (`localStorage.uiTheme`).

## Agent workflow

1. Read [AGENTS.md](AGENTS.md).
2. Reuse an existing component from [components.md](components.md). Add CSS only if nothing fits.
3. Put new user-facing copy through the strings approach in [i18n.md](i18n.md).
4. Verify light **and** dark, plus the `920px` breakpoint.
5. If you add a token or component, update this folder in the same change.
