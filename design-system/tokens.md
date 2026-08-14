# Tokens

All dashboard visuals come from CSS custom properties on `:root` (light) and `html[data-theme="dark"]` (dark). Defined in `app/static/style.css`. Values match the WhatsApp-bot design system.

Theme persistence: `app/static/theme.js` writes `html[data-theme]` from `localStorage.uiTheme` (`"light"` | `"dark"`). Default is **light**. Load `theme.js` in `<head>` so the theme applies before first paint.

## Color — light (default)

| Token | Value | Role |
|---|---|---|
| `--bg` | `#f3f4fb` | Page canvas |
| `--bg-deep` | `#eceef7` | Recessed log |
| `--bg-elev` | `#ffffff` | Elevated |
| `--surface` | `#ffffff` | Panels, inputs |
| `--surface-2` | `#f7f8fd` | Table header |
| `--line` | `#e7e9f4` | Default border |
| `--line-soft` | `#eef0f8` | Hairline / row divider |
| `--hairline-strong` | `#d9dcee` | Hover border, scrollbar |
| `--ink` | `#23263b` | Primary text |
| `--ink-2` | `#4b4f68` | Secondary text |
| `--ink-mute` | `#7e8299` | Labels, captions |
| `--ink-faint` | `#a8abc0` | Placeholders |
| `--accent` | `#7c5cfc` | Violet accent |
| `--accent-deep` | `#6847e8` | Accent text on light |
| `--accent-soft` | `rgba(124, 92, 252, 0.12)` | Focus ring, soft fill |
| `--accent-ink` | `#ffffff` | Text on accent / gradient |
| `--ok` / `--ok-soft` / `--ok-ink` | `#14b88a` / tint / `#0b8a66` | Success (done) |
| `--warn` / `--warn-soft` / `--warn-ink` | `#f5a524` / tint / `#ad6800` | Warning (running) |
| `--bad` / `--bad-soft` / `--bad-ink` | `#f4537e` / tint / `#d62e60` | Danger (failed) |
| `--info` / `--info-soft` / `--info-ink` | `#4596ff` / tint / `#1d6fe0` | Info (queued) |
| `--mix` | `#ffffff` | Mix base for `color-mix(...)` |
| `--grad` | `135deg, accent → grape` | Primary CTA fill |
| `--grad-hover` | `135deg, accent-deep → grape` | Primary CTA hover |

Personality tints `--mint` `#2dd4a8` · `--coral` `#ff7a8a` · `--sky` `#38bdf8` · `--sun` `#fbbf24` · `--grape` `#c06cf6` exist for future stats/nav. Do not use them as one-off hex in templates.

## Color — dark (`html[data-theme="dark"]`)

| Token | Value | Role |
|---|---|---|
| `--bg` | `#0b0d0f` | Canvas (thebots.lab) |
| `--bg-deep` | `#08090b` | Log well |
| `--bg-elev` | `#111418` | Elevated |
| `--surface` | `#0f1216` | Panels |
| `--surface-2` | `#14181d` | Table header |
| `--line` | `rgba(232,234,237,0.10)` | Border |
| `--line-soft` | `rgba(232,234,237,0.06)` | Divider / grid |
| `--hairline-strong` | `rgba(232,234,237,0.16)` | Strong border |
| `--ink` | `#e8eaed` | Primary text |
| `--ink-2` | `#b8bcc2` | Secondary |
| `--ink-mute` | `#7a8089` | Muted |
| `--ink-faint` | `#565c64` | Faint |
| `--accent` | `#ffd60a` | Yellow accent |
| `--accent-deep` | `#e6c009` | Deep yellow |
| `--accent-soft` | `rgba(255,214,10,0.14)` | Soft yellow |
| `--accent-ink` | `#0b0d0f` | Text on yellow |
| `--ok` / `--ok-ink` | `#4ade80` / `#6ee7a0` | Success |
| `--warn` / `--warn-ink` | `#fbbf24` / `#fcd34d` | Warning |
| `--bad` / `--bad-ink` | `#ff6b6b` / `#ff9d9d` | Danger |
| `--info` / `--info-ink` | `#7aa2ff` / `#a9c1ff` | Info |
| `--mix` | `#14181d` | Mix base |
| `--grad` | `135deg, #ffd60a → #ffb020` | Primary CTA |
| `--grad-hover` | `135deg, #f2c50a → #f5a524` | Primary CTA hover |

Status `*-soft` values on dark are `rgba(color, 0.12)`.

On dark, links and accent-on-tint text use `var(--accent)`, not `--accent-deep`.

## Type

| Token | Value | Use |
|---|---|---|
| `--sans` | `"Nunito", ui-sans-serif, system-ui, sans-serif` | Body, labels, buttons, table |
| `--display` | `"Outfit", var(--sans)` | Page titles, brand, empty title |
| `--mono` | `"JetBrains Mono", ui-monospace, "SF Mono", Menlo, monospace` | Times, pads, log, IDs |

Google Fonts in `base.html`: Outfit 500–800, Nunito 400–800, JetBrains Mono 400–600.

Body: `14px / 1.5`, antialiased. Do not add a fourth family.

## Radius, elevation, motion, focus

| Token | Value |
|---|---|
| `--r-xs` / `--r-sm` / `--r-md` / `--r-lg` | 8 / 12 / 14 / 20px |
| Buttons, pills | `999px` |
| Brand mark | `13px`, 40×40 |
| `--shadow-sm/md/lg` | light: ink alpha; dark: near-black |
| `--glow-accent` | CTA glow |
| Hover | 120ms, `translateY(-1px)` |
| Focus | `border-color: var(--accent); box-shadow: 0 0 0 4px var(--accent-soft)` |

## Layout

| Token | Value |
|---|---|
| `--content` | `920px` max width of `.view` |
| Breakpoint | `max-width: 920px` → single-column form grid, tighter padding |

Light background: pastel radial blobs. Dark: 32px terminal grid.
