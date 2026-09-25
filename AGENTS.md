# Working in this repository

**This repository is PUBLIC, and its root is also the live website.** It is served by
GitHub Pages at `heyghoshi.com` and acts as the content host the iOS apps download from
(`songs.json`, `content/*.banana`, `images/`).

So there are two exposures to keep in mind, and they are different:

1. **Anything you commit is public** the moment it is pushed — visible on GitHub.
2. **Anything not excluded from the Pages build is also a public URL** on the website.

Assume both, always. There is no "internal" file in this repo.

## Rules for adding files

1. **Never commit internal notes.** Setup notes, "facts to confirm" lists, decision logs
   and audit findings belong in `legal/notes/` (gitignored) — never in a tracked file.
   If you find engineering notes inside `legal/apps/*.json`, move them to
   `legal/notes/<slug>.json` (see `legal/README.md`).
2. **Never name a vendor or describe internal architecture** in the legal pages or the
   app data files. Policies describe outside services by **role** — "our AI providers",
   "our cloud platform", "our file storage", "measurement services" — never by product.
   Do not reintroduce product or service names, storage or namespace identifiers, region
   identifiers, function or file names, or any description of how the backend is wired.
   Naming a recipient was never required: APP 5 and GDPR Art 13(1)(e) accept
   **categories** of recipient.
3. **No personal data.** No names, email addresses, account identifiers, tokens, keys or
   local filesystem paths.
4. **No corporate entity name** in the generated legal pages; the publisher is the brand.
5. **Check what the deploy serves.** The Pages artifact is assembled by
   `.github/workflows/pages.yml`, which excludes `.git/ .github/ legal/ scripts/
   README.md .gitignore _config.yml`. **Every other file in the tree becomes a public
   URL.** If you add a root-level file, add it to that exclude list too unless you
   intend it to be served.
6. **The published legal pages are generated.** Edit `legal/` and run
   `python3 legal/build_legal.py --published-only`, then commit the generated HTML.
   Never hand-edit `privacy/` or `terms/`.

## The guard

`.githooks/pre-commit` scans the staged contents of every file you are about to commit
and refuses the commit if it finds a known-bad string — vendor names, infrastructure
identifiers, internal-note keys, personal data.

Enable it once per clone:

```sh
git config core.hooksPath .githooks
```

It is a net, not a substitute for judgement. It matches known-bad strings; it cannot
tell you that a paragraph *describes* internal architecture using words that are not on
the list. Read what you are about to commit.

## Other things worth knowing

- **Two deploy pipelines used to race on every push** (a legacy Jekyll branch build and
  the Actions workflow), so the same commit could produce different sites. The current
  repo runs the Actions pipeline only. Do not re-enable a branch-based Pages source.
- **Draft policies must never deploy.** An app whose JSON has `"draft": true` is
  `noindex` and holds a red banner, and `--published-only` keeps its pages out of the
  build entirely. Check `ls legal/apps/` for stray duplicate JSON files before a build.
- **The repository was rebuilt once for exactly the reasons in this file.** A note about
  an app's internals was committed and served publicly for three days; removing it cost
  a history rewrite and a new repository. The cheapest fix is to never stage it.
