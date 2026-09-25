#!/usr/bin/env python3
"""
Render the per-app privacy policies and terms of use for heyghoshi.com.

Source of truth:
    legal/controller.json     who "we" are (publisher, entity, contact, jurisdiction)
    legal/apps/<slug>.json    the facts that differ per app
    legal/notes/<slug>.json   internal setup notes - GITIGNORED, never committed
    legal/sections/*.html     shared privacy prose, with {{tokens}}
    legal/terms/*.html        shared terms prose
    legal/theme/page.html     the page chrome (head, header, hero, TOC, footer)

Output (committed to the repo, served by GitHub Pages):
    privacy/index.html            legal index for every app
    privacy/<slug>/index.html     that app's privacy policy
    terms/<slug>/index.html       that app's terms of use
    terms/index.html              redirect to the legal index
    privacy.html, terms.html      redirects kept alive for old App Store URLs

Output (local only - under the gitignored legal/notes/):
    legal/notes/REVIEW.md         every fact that still needs confirming

The `_todos` and `_decisions` keys are read from legal/notes/<slug>.json when that
file exists. They are deliberately kept out of legal/apps/*.json: the repo is
public and the whole tree is deployed, so those engineering notes must not sit in
anything that ships. Keep them in legal/notes/ and they stay on your machine.

Usage:
    python3 legal/build_legal.py

Run it after editing any file under legal/, then commit the generated HTML.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "legal"

# --------------------------------------------------------------------------
# Tiny mustache-like renderer
#
#   {{a.b.c}}            substitute (raw HTML, no escaping)
#   {{#x}}...{{/x}}      repeat over a list, or render once if truthy
#   {{^x}}...{{/x}}      render if falsy / empty / absent
#   {{this}}             the current item, inside a list of strings
#
# Unknown paths are collected as warnings so a typo cannot silently render
# as an empty string.
# --------------------------------------------------------------------------

TOKEN = re.compile(r"\{\{([#^/]?)\s*([A-Za-z0-9_.]+)\s*\}\}")


class _Missing:
    def __bool__(self) -> bool:  # pragma: no cover - defensive
        return False

    def __repr__(self) -> str:  # pragma: no cover - defensive
        return "<missing>"


MISSING = _Missing()


def lookup(path: str, ctx: dict, stack: tuple):
    parts = path.split(".")
    for frame in reversed(stack):
        if isinstance(frame, str):
            if parts[0] == "this":
                return frame
            continue
        if isinstance(frame, dict) and parts[0] in frame:
            value = frame[parts[0]]
            for part in parts[1:]:
                if isinstance(value, dict) and part in value:
                    value = value[part]
                else:
                    return MISSING
            return value
    value = ctx
    for part in parts:
        if isinstance(value, dict) and part in value:
            value = value[part]
        else:
            return MISSING
    return value


def find_block(template: str, start: int, name: str) -> tuple[str, int]:
    """Return (body, index_after_closing_tag) for the block opened at `start`."""
    depth = 1
    pos = start
    while True:
        match = TOKEN.search(template, pos)
        if not match:
            raise ValueError(f"unclosed block {{{{#{name}}}}}")
        sigil, token_name = match.group(1), match.group(2)
        if token_name == name and sigil in ("#", "^"):
            depth += 1
        elif token_name == name and sigil == "/":
            depth -= 1
            if depth == 0:
                return template[start : match.start()], match.end()
        pos = match.end()


def render(template: str, ctx: dict, stack: tuple = (), warnings: set | None = None) -> str:
    warnings = warnings if warnings is not None else set()
    out: list[str] = []
    pos = 0
    while True:
        match = TOKEN.search(template, pos)
        if not match:
            out.append(template[pos:])
            break
        out.append(template[pos : match.start()])
        sigil, name = match.group(1), match.group(2)

        if sigil in ("#", "^"):
            body, end = find_block(template, match.end(), name)
            value = lookup(name, ctx, stack)
            if sigil == "^":
                if value is MISSING:
                    warnings.add(name)
                if not value:
                    out.append(render(body, ctx, stack, warnings))
            elif isinstance(value, list):
                for item in value:
                    out.append(render(body, ctx, stack + (item,), warnings))
            elif value is MISSING:
                warnings.add(name)
            elif value:
                out.append(render(body, ctx, stack + (value if isinstance(value, dict) else {},), warnings))
            pos = end
        elif sigil == "/":
            pos = match.end()
        else:
            value = lookup(name, ctx, stack)
            if value is MISSING:
                warnings.add(name)
            elif value not in (None, False):
                out.append(str(value))
            pos = match.end()

    return "".join(out)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# Section plan — the order, and when each section applies
# --------------------------------------------------------------------------

AI_FILES = {"on-device": "ai-ondevice.html", "third-party": "ai-third-party.html"}

# Where each region's shared prose lives under legal/
FRAGMENT_DIR = {"privacy": "sections", "terms": "terms"}

SECTIONS = [
    {"key": "overview", "title": "Overview & Core Privacy Vision", "file": "overview.html"},
    {"key": "ai", "title_from": "app.ai.title", "file_from_ai_mode": True},
    {"key": "storage", "title": "Where Your Data Lives", "file": "storage.html"},
    {
        "key": "accounts",
        "title": "Accounts & What We Store On Our Servers",
        "file": "accounts.html",
        "needs": "accounts",
    },
    {
        "key": "sharing",
        "title": "Questions You Share With Other Children",
        "file": "sharing.html",
        "needs": "sharing",
    },
    {
        "key": "bug-reports",
        "title": "Sending Us a Bug Report",
        "file": "bug-reports.html",
        "needs": "bugReports",
    },
    {
        "key": "permissions",
        "title": "Device Permissions Requested",
        "file": "permissions.html",
        "needs": "permissions",
    },
    {
        "key": "analytics",
        "title": "Analytics & Advertising Measurement",
        "file": "analytics.html",
        "needs": "analytics",
    },
    {
        "key": "third-parties",
        "title": "Third-Party Service Providers",
        "file": "third-parties.html",
        "needs": "thirdParties",
    },
    {"key": "children", "title": "Children's Privacy", "file": "children.html"},
    {"key": "rights", "title": "Your Data Rights & Deletion", "file": "rights.html"},
    {"key": "updates", "title": "Policy Updates", "file": "updates.html"},
    {"key": "contact", "title": "Contact & Privacy Inquiries", "file": "contact.html"},
]

TERMS_SECTIONS = [
    {"key": "acceptance", "title": "Acceptance & Which Licence Applies", "file": "acceptance.html"},
    {"key": "the-app", "title": "The App & Your Licence", "file": "the-app.html"},
    {"key": "purchases", "title": "In-App Purchases & Subscriptions", "file": "purchases.html"},
    {"key": "ai", "title": "Automated Output & Its Limits", "file": "ai.html", "ai_not_none": True},
    {"key": "acceptable-use", "title": "Acceptable Use", "file": "acceptable-use.html"},
    {"key": "privacy", "title": "Privacy", "file": "privacy.html"},
    {"key": "liability", "title": "Disclaimer & Limitation of Liability", "file": "liability.html"},
    {"key": "law", "title": "Governing Law", "file": "law.html"},
    {"key": "contact", "title": "Contact & Legal Inquiries", "file": "contact.html", "dark": True},
]


def needs_met(spec: dict, app: dict) -> bool:
    if spec.get("needs"):
        value = app.get(spec["needs"])
        if not value:
            return False
    if spec.get("ai_not_none") and app.get("ai", {}).get("mode") == "none":
        return False
    if spec.get("file_from_ai_mode") and app.get("ai", {}).get("mode") not in AI_FILES:
        return False
    return True


def section_file(spec: dict, app: dict, fold: str) -> Path:
    directory = SRC / FRAGMENT_DIR[fold]
    if spec.get("file_from_ai_mode"):
        return directory / AI_FILES[app["ai"]["mode"]]
    return directory / spec["file"]


def accent_classes(app: dict) -> dict:
    accent = dict(app["accent"])
    family = re.search(r"bg-([a-z]+)-\d+", accent.get("soft", "bg-slate-100")).group(1)
    accent["family"] = family
    accent["border"] = f"border-{family}-500"
    accent["tint"] = f"bg-{family}-50"
    accent["solid"] = f"bg-{family}-100 text-{family}-700"
    return accent


# --------------------------------------------------------------------------
# Fragments
# --------------------------------------------------------------------------

ICONS = {
    "check": "M5 13l4 4L19 7",
    "device": "M12 18h.01M8 21h8a2 2 0 002-2V5a2 2 0 00-2-2H8a2 2 0 00-2 2v14a2 2 0 002 2z",
    "cloud": "M3 15a4 4 0 004 4h9a5 5 0 10-.1-9.999 5.002 5.002 0 10-9.78 2.096A4.001 4.001 0 003 15z",
    "shield": "M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z",
}


def hero_card(icon: str, classes: str, title: str, body: str) -> str:
    return f"""
          <div class="bg-white p-5 rounded-2xl border border-slate-200 shadow-sm flex flex-col justify-between">
            <div>
              <div class="w-10 h-10 rounded-xl {classes} flex items-center justify-center mb-3">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="{ICONS[icon]}"></path>
                </svg>
              </div>
              <h3 class="font-bold text-slate-900 text-base mb-1">{title}</h3>
              <p class="text-xs text-slate-500 leading-normal">{body}</p>
            </div>
          </div>"""


def build_cards(app: dict, accent: dict) -> str:
    solid = accent["solid"]
    cards = []

    if app.get("accounts"):
        cards.append(
            hero_card(
                "cloud",
                "bg-sky-100 text-sky-700",
                "Optional Account",
                "You can sign in to sync your library. This page explains exactly what is stored on our servers, and how to delete it.",
            )
        )
    elif app.get("ai", {}).get("mode") == "third-party":
        cards.append(
            hero_card(
                "device",
                "bg-emerald-100 text-emerald-700",
                "On-Device, With One Exception",
                "We keep no copy of your work, and there is no account. One disclosure stands out: the text you ask for AI feedback on is sent to our AI provider.",
            )
        )
    else:
        cards.append(
            hero_card(
                "check",
                "bg-emerald-100 text-emerald-700",
                "No Account, No Profile",
                f"There is nothing to sign up for in {app['name']}, so there is no profile of you to build or sell.",
            )
        )

    permissions = app.get("permissions") or []
    if permissions:
        cards.append(
            hero_card(
                "device",
                "bg-blue-100 text-blue-700",
                f"{len(permissions)} Permission{'s' if len(permissions) != 1 else ''} Asked",
                "Each one is optional and is refused without breaking the rest of the app. See the permission list below.",
            )
        )
    else:
        cards.append(
            hero_card(
                "device",
                "bg-blue-100 text-blue-700",
                "No Permissions",
                f"{app['name']} does not ask for your camera, microphone, contacts, or location.",
            )
        )

    if app.get("analytics"):
        cards.append(
            hero_card(
                "cloud",
                solid,
                "Anonymous Analytics Only",
                "Usage counts and device model help us fix crashes, and nothing is tied to a name or an email address.",
            )
        )
    else:
        cards.append(
            hero_card("shield", solid, "No Analytics", "No third-party SDK reports on how you use the app.")
        )

    cards.append(
        hero_card(
            "shield",
            "bg-violet-100 text-violet-700",
            "Never Sold",
            "We do not sell your data or your content. Ad measurement is a limited, separate disclosure.",
        )
    )

    return "".join(cards)


def build_sections(app: dict, controller: dict, fold: str, specs: list, ctx: dict, warnings: set) -> tuple[str, list]:
    included = [s for s in specs if s.get("html") or needs_met(s, app)]
    numbers = {s["key"]: i for i, s in enumerate(included, start=1)}
    ctx["sec"] = numbers
    ctx["secLabel"] = {k: f"§{v}" for k, v in numbers.items()}

    html_parts: list[str] = []
    for spec in included:
        number = numbers[spec["key"]]
        title = resolve_title(spec, app, ctx)
        if spec.get("html"):
            body = spec["html"]
        else:
            body = render(read(section_file(spec, app, fold)), ctx, (), warnings)
        dark = spec.get("dark")
        if dark:
            wrapper = (
                'class="policy-section bg-gradient-to-br from-slate-900 to-slate-800 text-white '
                'p-6 sm:p-8 rounded-2xl shadow-lg"'
            )
            chip = "bg-white/15 text-white"
            heading = "text-white"
            prose = "prose prose-invert prose-slate text-slate-300 leading-relaxed space-y-4 text-sm sm:text-base"
        else:
            wrapper = (
                'class="policy-section bg-white p-6 sm:p-8 rounded-2xl border border-slate-200/80 shadow-sm"'
            )
            chip = app["accent"]["soft"]
            heading = "text-slate-900"
            prose = "prose prose-slate text-slate-600 leading-relaxed space-y-4 text-sm sm:text-base"
        html_parts.append(
            f"""
          <!-- Section {number} — {spec['key']} -->
          <section id="{spec['key']}" {wrapper}>
            <div class="flex items-center gap-3 mb-4">
              <span class="w-8 h-8 rounded-lg {chip} flex items-center justify-center font-bold text-sm">{number}</span>
              <h2 class="text-xl sm:text-2xl font-bold {heading}">{title}</h2>
            </div>
            <div class="{prose}">
{body}
            </div>
          </section>"""
        )
    return "".join(html_parts), included


def resolve_title(spec: dict, app: dict, ctx: dict) -> str:
    """An app may rename a shared section via its `sectionTitles` map."""
    override = (app.get("sectionTitles") or {}).get(spec["key"])
    if override:
        return override
    if spec.get("title_from"):
        return lookup(spec["title_from"], ctx, ())
    return spec["title"]


def build_toc(included: list, numbers: dict, ctx: dict) -> str:
    rows = []
    for spec in included:
        title = resolve_title(spec, ctx["app"], ctx)
        rows.append(
            f"""
              <a href="#{spec['key']}" class="toc-link block px-3 py-2 rounded-lg text-slate-600 hover:text-slate-900 hover:bg-slate-100 transition-colors">{numbers[spec['key']]}. {title}</a>"""
        )
    return "".join(rows)


def other_apps_nav(apps: list, current: str, prefix: str, fold: str) -> str:
    others = [a for a in apps if a["slug"] != current]
    if not others:
        return ""
    links = "".join(
        f"""
                <a href="{prefix}{fold}/{a['slug']}/" class="block px-3 py-1.5 rounded-lg text-slate-500 hover:text-slate-900 hover:bg-slate-100 transition-colors text-xs">{a['name']}</a>"""
        for a in others
    )
    return f"""
            <div class="pt-3 border-t border-slate-100">
              <h2 class="text-xs font-bold uppercase tracking-wider text-slate-400 px-2 pb-1">Other apps</h2>
              <nav class="space-y-0.5">{links}
              </nav>
            </div>"""


def icon_html(app: dict | None, prefix: str) -> tuple[str, str]:
    """Return (icon html, brand name)."""
    if app and app.get("icon"):
        return (
            f'\n              <img src="{prefix}{app["icon"]}" alt="{app["name"]} icon" class="w-full h-full object-cover" />\n            ',
            app["name"],
        )
    if app:
        return (
            f'\n              <div class="w-full h-full flex items-center justify-center bg-slate-900 text-white font-black text-sm sm:text-base tracking-tight">{app["monogram"]}</div>\n            ',
            app["name"],
        )
    return (
        '\n              <div class="w-full h-full flex items-center justify-center bg-slate-900 text-white font-black text-sm sm:text-base tracking-tight">HG</div>\n            ',
        "HeyGhoshi",
    )


def page_prefix(rel_path: Path) -> str:
    """Relative path from the output file back to the repo root."""
    depth = len(rel_path.parts) - 1
    return "../" * depth


def render_page(*, rel_path: Path, app: dict | None, controller: dict, region: str, fold: str,
                specs: list, apps: list, warnings: set) -> str:
    prefix = page_prefix(rel_path)
    theme = read(SRC / "theme" / "page.html")
    if region == "hub":
        specs = [
            {"key": "which-app", "title": "One Policy Per App", "file": "hub-who.html"},
            {"key": "at-a-glance", "title": "At a Glance", "html": hub_table(apps, prefix)},
            {"key": "contact", "title": "Contact & Privacy Inquiries", "file": "hub-contact.html", "dark": True},
        ]
    accent = accent_classes(app) if app else accent_classes(
        {"accent": {"chip": "bg-slate-900 text-white", "soft": "bg-slate-200 text-slate-800",
                    "text": "text-slate-600", "hero": "from-slate-500/10 via-slate-500/5 to-slate-50",
                    "ring": "shadow-slate-500/20"}}
    )

    ctx: dict = {
        "app": app or {},
        "c": controller,
        "url": {
            "home": prefix or "./",
            "legalHome": f"{prefix}privacy/",
            "terms": f"{prefix}terms/{app['slug']}/" if app else f"{prefix}terms/",
            "privacy": f"{prefix}privacy/{app['slug']}/" if app else f"{prefix}privacy/",
            "privacyLabel": f"{app['name']} privacy policy" if app else "privacy policies",
        },
        "accent": accent,
    }

    sections_html, included = build_sections(app or {"ai": {"mode": "none"}, "accent": app_accent_stub()},
                                            controller, fold, specs, ctx, warnings)

    icon, brand_name = icon_html(app, prefix)
    if region == "hub":
        title = f"Privacy & Terms — {controller['publisher']}"
        h1 = "Privacy & Terms"
        lede = (
            f"{controller['publisher']} publishes {len(apps)} apps, and each one handles your data "
            "differently. Pick your app below."
        )
        badge = f"Published by {controller['legalEntity']}"
        search = "Search the legal index…"
    elif fold == "privacy":
        title = f"Privacy Policy — {app['name']}"
        h1 = "Privacy Policy"
        lede = (
            f"This is the privacy policy for <strong class=\"text-slate-900\">{app['name']}</strong>, "
            f"published by {controller['publisher']}. {app['promise']}"
        )
        badge = f"Effective Date: {app['effectiveDate']}"
        search = "Search privacy terms (e.g. 'camera', 'AI', 'storage', 'delete')…"
    else:
        title = f"Terms of Use — {app['name']}"
        h1 = "Terms of Use"
        lede = (
            f"The terms that apply to <strong class=\"text-slate-900\">{app['name']}</strong>. "
            "This app uses Apple's Standard EULA, plus the app-specific terms on this page."
        )
        badge = f"Effective Date: {app['effectiveDate']}"
        search = "Search terms (e.g. 'copyright', 'AI', 'subscription', 'liability')…"

    draft_banner = ""
    if app and app.get("draft"):
        count = len(app.get("_todos") or [])
        draft_banner = f"""
    <div class="no-print bg-rose-600 text-white text-sm font-semibold px-4 py-3 text-center">
      DRAFT — not approved for release. {count} item{'s' if count != 1 else ''} still to confirm.
      The set-up notes are kept privately, outside this repository; this page is
      marked <code class="font-mono">noindex</code> until they are resolved.
    </div>"""

    ctx.update(
        {
            "head": {                "title": title,
                "description": f"Privacy and legal information for {app['name']}." if app and fold == "privacy"
                else (f"Terms of use for {app['name']}." if app else f"Privacy and terms for the apps published by {controller['publisher']}."),
                "robots": '\n    <meta name="robots" content="noindex, nofollow" />' if (app and app.get("draft")) else "",
                "canonical": f"{controller['siteUrl']}/{rel_path.parent.as_posix()}/",
            },
            "brand": {"name": brand_name, "kicker": "Legal" if region == "hub" else ("Privacy Policy" if fold == "privacy" else "Terms of Use"),
                      "iconHtml": icon, "link": ctx["url"]["home"], "legalHome": ctx["url"]["legalHome"]},
            "hero": {
                "badge": badge,
                "h1": h1,
                "lede": lede,
                "searchPlaceholder": search,
                "cards": build_cards(app, accent) if app else build_hub_cards(apps, prefix),
            },
            "toc": build_toc(included, ctx["sec"], ctx),
            "tocExtra": other_apps_nav(apps, app["slug"], prefix, fold) if app else "",
            "sections": sections_html,
            "footer": {
                "copyright": f"{controller['copyright']} {app['name']}." if app else controller["copyright"],
                "note": app["promise"] if app else f"{controller['publisher']} is {controller['publisherKind']}.",
                "links": (
                    f'<a href="{ctx["url"]["privacy"]}" class="hover:text-amber-600 transition-colors">Privacy</a>'
                    f'<a href="{ctx["url"]["terms"]}" class="hover:text-amber-600 transition-colors">Terms</a>'
                    f'<a href="{ctx["url"]["legalHome"]}" class="hover:text-amber-600 transition-colors">All apps</a>'
                    f'<a href="mailto:{controller["contactEmail"]}" class="hover:text-amber-600 transition-colors">Support</a>'
                ),
            },
            "draftBanner": draft_banner,
        }
    )

    html = render(theme, ctx, (), warnings)
    leftover = TOKEN.findall(html)
    if leftover:
        warnings.add(f"UNRESOLVED TOKENS in {rel_path}: {sorted({f'{{{{{{{s[2]}}}}}}}' for s in leftover})}")
    return html


def app_accent_stub() -> dict:
    return {"chip": "bg-slate-900 text-white", "soft": "bg-slate-200 text-slate-800",
            "text": "text-slate-600", "hero": "from-slate-500/10 via-slate-500/5 to-slate-50",
            "ring": "shadow-slate-500/20"}


def build_hub_cards(apps: list, prefix: str) -> str:
    cards = []
    for app in apps:
        status = "Coming Soon" if app["status"] == "coming-soon" else "On the App Store"
        draft = ' <span class="text-rose-600 font-semibold">draft</span>' if app.get("draft") else ""
        cards.append(
            f"""
          <div class="bg-white p-5 rounded-2xl border border-slate-200 shadow-sm flex flex-col justify-between">
            <div>
              <div class="flex items-center gap-3 mb-3">
                <div class="w-10 h-10 rounded-xl overflow-hidden ring-1 ring-slate-200 shrink-0">
                  {icon_html(app, prefix)[0].strip()}
                </div>
                <div>
                  <h3 class="font-bold text-slate-900 text-base leading-tight">{app['name']}{draft}</h3>
                  <p class="text-[11px] font-semibold uppercase tracking-wider text-slate-400">{status}</p>
                </div>
              </div>
              <p class="text-xs text-slate-500 leading-normal mb-4">{app['tagline']}</p>
            </div>
            <div class="flex gap-2 text-xs font-semibold">
              <a href="{prefix}privacy/{app['slug']}/" class="{app['accent']['chip']} px-3 py-1.5 rounded-lg">Privacy</a>
              <a href="{prefix}terms/{app['slug']}/" class="bg-slate-100 text-slate-700 px-3 py-1.5 rounded-lg">Terms</a>
            </div>
          </div>"""
        )
    return "".join(cards)


def hub_table(apps: list, prefix: str) -> str:
    rows = []
    for app in apps:
        status = "Coming Soon" if app["status"] == "coming-soon" else "Available"
        draft = ' <span class="text-rose-600 font-semibold">draft</span>' if app.get("draft") else ""
        rows.append(
            f"""
        <tr class="border-b border-slate-100 last:border-0 align-top">
          <td class="py-3 pr-4">
            <div class="font-bold text-slate-900 text-sm">{app['name']}{draft}</div>
            <div class="text-[11px] uppercase tracking-wider text-slate-400 font-semibold">{status}</div>
          </td>
          <td class="py-3 pr-4 text-xs text-slate-600 leading-relaxed">{app.get('dataSummary', '')}</td>
          <td class="py-3 text-xs font-semibold whitespace-nowrap">
            <a href="{prefix}privacy/{app['slug']}/" class="text-slate-900 underline decoration-slate-300 hover:decoration-slate-900">Privacy</a>
            <span class="text-slate-300"> · </span>
            <a href="{prefix}terms/{app['slug']}/" class="text-slate-500 underline decoration-slate-300 hover:decoration-slate-900">Terms</a>
          </td>
        </tr>"""
        )
    return f"""<p>Here is the whole picture on one screen. Each row links to the full documents for that app.</p>
<div class="overflow-x-auto">
  <table class="w-full text-left border-collapse min-w-[34rem]">
    <thead>
      <tr class="border-b border-slate-200">
        <th class="py-2 pr-4 text-[11px] font-bold uppercase tracking-wider text-slate-400">App</th>
        <th class="py-2 pr-4 text-[11px] font-bold uppercase tracking-wider text-slate-400">What it keeps, and where</th>
        <th class="py-2 text-[11px] font-bold uppercase tracking-wider text-slate-400">Documents</th>
      </tr>
    </thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</div>"""


def redirect_page(target: str, label: str, canonical: str) -> str:
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <title>Redirecting — {label}</title>
    <link rel="canonical" href="{canonical}" />
    <meta name="robots" content="noindex" />
    <meta http-equiv="refresh" content="0; url={target}" />
    <script>
      location.replace("{target}");
    </script>
  </head>
  <body>
    <p>This page has moved to <a href="{target}">{label}</a>.</p>
  </body>
</html>
"""


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--published-only",
        action="store_true",
        help="Build only the apps that are not drafts, and delete any draft pages a "
        "previous build left behind. Use this for a deploy so unfinished policies are "
        "never served.",
    )
    args = parser.parse_args()

    controller = json.loads(read(SRC / "controller.json"))
    apps = [json.loads(read(p)) for p in sorted((SRC / "apps").glob("*.json"))]
    apps.sort(key=lambda a: a["name"])

    # The internal setup notes live outside the repository (legal/notes/ is
    # gitignored). Merge them back in so every consumer below is unchanged.
    notes_dir = SRC / "notes"
    for app in apps:
        note_file = notes_dir / f"{app['slug']}.json"
        if note_file.exists():
            notes = json.loads(read(note_file))
            app["_todos"] = notes.get("_todos") or app.get("_todos") or []
            app["_decisions"] = notes.get("_decisions") or app.get("_decisions") or []

    # Drafts must never reach the deploy. In published-only mode they are dropped and
    # their stale build output removed, so the legal index does not link to them either.
    all_apps = list(apps)
    if args.published_only:
        keep = [a for a in apps if not a.get("draft")]
        for app in apps:
            if app.get("draft"):
                for rel in (f"privacy/{app['slug']}", f"terms/{app['slug']}"):
                    stale = ROOT / rel
                    if stale.exists():
                        shutil.rmtree(stale)
                        print(f"removed draft build {rel}/")
        apps = keep

    warnings: set = set()
    written: list[Path] = []

    def write(rel: str, content: str) -> None:
        path = ROOT / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        written.append(path)

    for app in apps:
        write(
            f"privacy/{app['slug']}/index.html",
            render_page(rel_path=Path(f"privacy/{app['slug']}/index.html"), app=app,
                        controller=controller, region="app", fold="privacy",
                        specs=SECTIONS, apps=apps, warnings=warnings),
        )
        write(
            f"terms/{app['slug']}/index.html",
            render_page(rel_path=Path(f"terms/{app['slug']}/index.html"), app=app,
                        controller=controller, region="app", fold="terms",
                        specs=TERMS_SECTIONS, apps=apps, warnings=warnings),
        )

    hub = render_page(rel_path=Path("privacy/index.html"), app=None, controller=controller,
                      region="hub", fold="privacy",
                      specs=[], apps=apps, warnings=warnings)
    write("privacy/index.html", hub)
    write("terms/index.html", redirect_page("../privacy/", "Privacy & Terms", f"{controller['siteUrl']}/privacy/"))

    # Keep the two original URLs alive for listings already pointing at them.
    write("privacy.html", redirect_page("privacy/music-banana/", "Music Banana Privacy Policy",
                                         f"{controller['siteUrl']}/privacy/music-banana/"))
    write("terms.html", redirect_page("terms/music-banana/", "Music Banana Terms of Use",
                                      f"{controller['siteUrl']}/terms/music-banana/"))

    # Review notes
    lines = ["# Legal pages — facts still to confirm", "",
             f"Generated by `legal/build_legal.py` on this run. Reviewed against `legal/controller.json` "
             f"(last reviewed {controller['lastReviewed']}).", ""]
    for app in all_apps:
        lines.append(f"## {app['name']}" + ("  — **draft, not published**" if app.get("draft") else "  — published"))
        lines.append("")
        todos = app.get("_todos") or []
        if todos:
            lines += [f"- [ ] {t}" for t in todos]
        else:
            lines.append("- [x] No open items.")
        lines.append("")
        # Decisions already taken by the owner. Kept out of the checkbox list so
        # they are never re-raised as open questions.
        decisions = app.get("_decisions") or []
        if decisions:
            lines.append("Settled — do not re-raise:")
            lines += [f"- {d}" for d in decisions]
            lines.append("")
        lines.append(f"Privacy: `/privacy/{app['slug']}/` · Terms: `/terms/{app['slug']}/`")
        lines.append("")

    if warnings:
        lines += ["## Template warnings", "",
                  "These token paths were referenced but not found in the data. "
                  "Each one rendered as an empty string:", ""]
        lines += [f"- `{w}`" for w in sorted(warnings)]
        lines.append("")

    # Local only, and gitignored along with the notes it is generated from.
    write("legal/notes/REVIEW.md", "\n".join(lines))

    print(f"Wrote {len(written)} files:")
    for path in written:
        print(f"  {path.relative_to(ROOT)}")
    if warnings:
        print("\nWARNINGS (rendered as empty strings):")
        for w in sorted(warnings):
            print(f"  {w}")
    drafts = [a["name"] for a in all_apps if a.get("draft")]
    if drafts:
        if args.published_only:
            held = ", ".join(a["name"] for a in all_apps if a.get("draft"))
            print(f"\nHeld back (draft, not built or linked): {held}")
        else:
            print("\nDrafts (noindex, still to confirm): " + ", ".join(drafts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
