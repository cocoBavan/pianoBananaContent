# Legal pages (`legal/`)

This folder is the **source** for the privacy policies and terms of use served at
`heyghoshi.com`. The HTML it produces is committed to the repo, so GitHub Pages
needs no build step — the existing `.github/workflows/pages.yml` keeps uploading
the repo as-is.

## Why it is generated instead of hand-written

Before, `privacy.html` was one 1,100-line page for a single app. It made claims that
are only true for Music Banana — "no servers", "no accounts", "your sheet music never
leaves your device" — and once there were four apps those claims were wrong for the
other three. Selective Teacher sends question text to an AI provider; Books & Vocab
stores an account on a server. A shared page cannot honestly describe both.

So:

- **shared prose lives once**, in `sections/` and `terms/`, and changes in one place;
- **the facts that differ** live in `apps/<slug>.json`;
- **one page per app is published**, at a URL that describes only that app — which is
  what App Store Connect expects for the privacy policy URL;
- **section numbering is computed** from which sections apply, so removing a section
  cannot leave a stale "see §6" behind.

## Layout

```
legal/
  controller.json       who "we" are — publisher, legal entity, contact, jurisdiction
  apps/<slug>.json      the per-app facts (the only file you normally edit)
  sections/*.html       shared privacy prose, privacy fragments
  terms/*.html          shared terms prose, terms fragments
  theme/page.html       page chrome: head, header, hero, table of contents, footer
  build_legal.py        the generator
  notes/<slug>.json     the setup notes — GITIGNORED, stays on your machine
  notes/REVIEW.md       GENERATED — every fact still to confirm, local only
```

Published output:

| Path                         | What it is                                                        |
| ---------------------------- | ----------------------------------------------------------------- |
| `privacy/index.html`         | the legal index — one card per app                                |
| `privacy/<slug>/index.html`  | that app's privacy policy                                         |
| `terms/<slug>/index.html`    | that app's terms of use                                           |
| `terms/index.html`           | redirect to the legal index                                       |
| `privacy.html`, `terms.html` | redirects, kept alive for App Store URLs already pointing at them |

## Two build modes

| Command                                         | What it produces                                                                            | When to use it                                           |
| ----------------------------------------------- | ------------------------------------------------------------------------------------------- | -------------------------------------------------------- |
| `python3 legal/build_legal.py`                  | every app, drafts included                                                                  | local review — this is how you read an unfinished policy |
| `python3 legal/build_legal.py --published-only` | only apps with `"draft": false`, and deletes the draft folders a previous build left behind | **before committing for deploy**                         |

Why the second one exists: everything in this repo is published by GitHub Pages the
moment it is pushed. Without `--published-only` the legal index links to the draft
policies, so an unfinished — and possibly wrong — privacy policy becomes publicly
reachable. Drafts are `noindex` and carry a red banner, but reachable is reachable.
Removing them also removes the hub cards that point at them, so nothing 404s.

`legal/notes/REVIEW.md` lists every app either way, so switching to a published-only
build does not hide the work that is outstanding.

## How to change something

1. Edit the JSON (or the shared fragment) under `legal/`.
2. Run the generator:

   ```bash
   python3 legal/build_legal.py
   ```

3. Read the output. It prints every file written, plus two things you should act on:
   - **WARNINGS** — a `{{token}}` referenced but not present in the data. It rendered
     as an empty string, so the page is silently missing a fact. Fix the JSON or the
     fragment.
   - **Drafts** — apps whose pages are `noindex` and carry a red banner.

4. Commit the generated HTML. Note `scripts/add_song.py` only adds `songs.json`,
   `content/`, `thumbnails/` and `images/` — use `git add privacy terms legal` (or
   `git add -A`). `legal/notes/` is gitignored, so the setup notes stay on your
   machine; never force-add them.

## Drafts: the safety catch

An app whose JSON has `"draft": true`:

- gets `noindex, nofollow` in its `<head>`;
- gets a red banner on the page counting the open items;
- is listed in the local `notes/REVIEW.md`.

Set `"draft": false` only after every item in its `notes/<slug>.json` `_todos` array
has been resolved.
A wrong privacy claim is worse than an unfinished page, so the default is to stay a
draft until someone confirms the facts.

## Adding a fifth app

1. Copy the closest existing file in `apps/`, change `slug`, `name`, `monogram`,
   `accent`, `tagline`, `promise`, `dataSummary`, and the data facts.
2. Set `"draft": true` and list what you need to confirm in `legal/notes/<slug>.json`
   (create the file; it is gitignored).
3. Run the generator. The index page, both documents, and the cross-app navigation
   pick it up automatically — nothing else to edit.

## Two things worth knowing

- **`legal/` is no longer served.** It used to be: the site root is the repository
  root, so the generator, the per-app data and the notes were all downloadable from
  `heyghoshi.com/legal/`. `_config.yml` now excludes `legal/`, `README.md`,
  `.github/` and `.gitignore` from the Pages build, and the notes moved to the
  gitignored `legal/notes/` — so they are not in the deployed tree at all, and not in
  the repository either. Anything you add under `legal/` is covered by the folder
  exclusion.
- **Draft pages are still reachable.** They are `noindex` and watermarked, but a
  direct URL works. Until an app is confirmed, do not put its draft URL in App Store
  Connect.
