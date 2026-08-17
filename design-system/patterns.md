# Patterns

## Compact shell

Extractor has two pages (jobs list, job detail). Do not add a sidebar.

```
body
  header.topbar
    a.brand
    .topbar__actions  (Jobs, Edit, Settings, #btn-theme)
  main.view
    (crumb on detail)
    .view__hero (list / edit / settings)
    section.panel …
```

Head assets in `base.html` (order matters):

1. Google Fonts (Outfit, Nunito, JetBrains Mono) + preconnect
2. `/static/style.css`
3. `/static/theme.js` (synchronous, in `<head>`)

## List + create (index)

1. `.view__hero` with title + description
2. `.panel` “Source” containing `.form` with `.tabs` (YouTube link | Upload)
3. Errors as `.banner.banner--bad` inside the form panel
4. `.panel` “Jobs” with `.tbl` or `.empty`

Create stays **on the list page**, not in a drawer.

## Edit package

1. `.view__hero` explaining intro → sermon → ending
2. `.panel` “Active package” summarizing the selected clips
3. `.panel` “Intro” + `.panel` “Ending”: upload form, then `.asset-list` of `.asset` cards (preview `.player.player--asset`, select / clear / delete)

Selected branding is applied automatically when a job finishes. Job detail can rebuild with **Rebuild with current intro & ending**.

## Job detail

1. `.crumb` back to `/`
2. `.panel` with title, friendly status pill (`Waiting` / `Working` / `Ready` / `Failed`), `.progress` (bar + `.steps`), optional player, then “What we found”
3. Job options live under `.details` (“More details”)
4. Raw worker output under `<details class="panel details-panel">` (“Technical log”)

Active jobs keep `<meta http-equiv="refresh" content="3">`. A small script restores window scroll and keeps `#job-log` pinned to the bottom across refreshes (unless the user scrolled up in the log).

When `status == done` and the output exists, show `.player` pointing at `/jobs/{id}/media` (inline) plus download / rebuild actions. Packaging uses the active intro & ending from `/edit`.

## New page

1. `{% extends "base.html" %}`
2. Content only inside `{% block content %}` — never a second topbar
3. Use hero + panel (or detail pattern above)
4. Add i18n/strings per [i18n.md](i18n.md) if introducing new copy
5. Do not create `page.css`

## Responsive

At `max-width: 920px`: tighter topbar/view padding; `.form__grid` becomes one column. Keep the primary CTA visible.

## Auth

HTTP Basic. Do not build an `.auth` card unless product explicitly replaces Basic auth.
