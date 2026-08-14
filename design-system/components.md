# Components

Class names as implemented in `app/static/style.css`. Copy these. Strings in examples are placeholders.

## Brand + topbar

```html
<header class="topbar">
  <a class="brand" href="/">
    <span class="brand__mark" aria-hidden="true">PA</span>
    <span class="brand__text">
      <span class="brand__name">Podcast aggregator</span>
      <span class="brand__sub">Sermon extractor</span>
    </span>
  </a>
  <div class="topbar__actions">
    <button class="iconbtn iconbtn--theme" id="btn-theme" type="button" aria-label="Toggle theme">🌙</button>
  </div>
</header>
```

Theme button **must** keep `id="btn-theme"` — `theme.js` binds to it.

## Buttons

```html
<button class="btn btn--primary" type="submit">Queue job</button>
<a class="btn btn--primary" href="/jobs/id/download">Download sermon clip</a>
<button class="btn btn--ghost" type="button">Cancel</button>
<button class="iconbtn iconbtn--theme" id="btn-theme" type="button">🌙</button>
```

- `.btn--primary` / `.btn--accent` — gradient CTA
- `.btn--ghost` — secondary
- `.btn--danger` — irreversible
- `.btn--sm` — compact
- Do not use a raw `<button>` or `.button` without `.btn`

## View + crumb

```html
<main class="view">
  <p class="crumb"><a href="/">All jobs</a></p>
  <div class="view__hero">
    <h1 class="view__title">New extraction</h1>
    <p class="view__desc">One-line description.</p>
  </div>
</main>
```

## Panel + table

```html
<section class="panel">
  <div class="panel__head">
    <h2 class="panel__title">Jobs</h2>
  </div>
  <div class="tbl-wrap">
    <table class="tbl">
      <thead><tr><th>Status</th><th>Title</th></tr></thead>
      <tbody>
        <tr>
          <td><span class="pill pill--ok">done</span></td>
          <td class="name"><a href="/jobs/…">Title</a></td>
        </tr>
      </tbody>
    </table>
  </div>
</section>
```

Form panels wrap fields in `.panel__body`. Job-detail heads that stack title + pill use `.panel__head--stack`.

Cell helpers: `.name` `.muted` `.mono`.

## Empty

```html
<div class="empty">
  <p class="empty__title">No jobs yet</p>
  <p class="empty__desc">Upload a service video to get started.</p>
</div>
```

## Pills (job status)

| Status | Class | Friendly label (job detail) |
|---|---|---|
| queued | `pill pill--info` | Waiting |
| running | `pill pill--warn` | Working |
| done | `pill pill--ok` | Ready |
| failed | `pill pill--bad` | Failed |

Jobs list keeps the raw API status in the pill. Job detail uses the friendly labels from `app/progress.py`.

Do not create `.badge` or extra pill colors.

## Progress (job detail)

```html
<div class="progress">
  <div class="progress__head">
    <div>
      <p class="progress__headline">Finding the sermon</p>
      <p class="progress__detail">Figuring out where the sermon starts and ends.</p>
    </div>
    <p class="progress__pct mono">50%</p>
  </div>
  <div class="progress__bar progress__bar--live" role="progressbar" aria-valuenow="50">
    <span class="progress__fill" style="--progress: 50%"></span>
  </div>
  <ol class="steps">
    <li class="steps__item steps__item--done">…</li>
    <li class="steps__item steps__item--current">…</li>
    <li class="steps__item steps__item--todo">…</li>
  </ol>
</div>
```

Modifiers: `.progress__bar--live` (active job), `--ok`, `--bad`. Step states: `--done`, `--current`, `--todo`, `--failed`.

## Player (job detail)

```html
<video class="player" controls playsinline preload="metadata" src="/jobs/id/media"></video>
<div class="player-placeholder">
  <p class="player-placeholder__title">Video will appear here</p>
  <p class="player-placeholder__desc">When the cut finishes, you can watch it on this page.</p>
</div>
```

## Details disclosure

```html
<details class="details">
  <summary class="details__summary">More details</summary>
  …
</details>
<details class="panel details-panel">
  <summary class="panel__head details-panel__summary">…</summary>
  <div class="panel__body">…</div>
</details>
```

## Forms

```html
<form class="form">
  <div class="form__row">
    <label class="lbl" for="url">YouTube link</label>
    <input class="inp" id="url" type="url" name="url">
  </div>
  <p class="divider"><span>or</span></p>
  <div class="form__grid">
    <div class="form__row">
      <label class="lbl" for="language">Language</label>
      <input class="inp" id="language" name="language">
    </div>
    <div class="form__row">
      <label class="lbl" for="source">Transcript</label>
      <select class="sel" id="source" name="transcript_source">…</select>
    </div>
  </div>
  <label class="check">
    <input type="checkbox" name="reencode" value="true">
    <span>Re-encode for a frame-accurate cut (slower)</span>
  </label>
  <button class="btn btn--primary" type="submit">Queue job</button>
</form>
```

Numeric fields: `.inp--mono`. Helper text: `.hint`.

## Key/value (job meta)

```html
<dl class="kv">
  <div><dt>Language</dt><dd>pt</dd></div>
  <div><dt>Pad</dt><dd class="mono">2s / 5s</dd></div>
</dl>
```

## Log + error banner

```html
<p class="banner banner--bad">Upload too large</p>
<pre class="log">worker output…</pre>
```

## When you need something not on these pages yet

Use the shared vocabulary before inventing classes:

- Confirm overwrite/delete → `.confirm` (add the CSS from WhatsApp-bot `style.css` if missing, then document it here)
- Toast → `.toast`
- Drawer form → `.drawer`
- Auth card → `.auth` (only if replacing HTTP Basic with an HTML login)
