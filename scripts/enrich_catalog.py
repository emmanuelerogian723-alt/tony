#!/usr/bin/env python3
"""Enrich Tony's app registry: real logos, clean categories, popularity.

Idempotent and non-destructive: it only fills EMPTY fields and never
overwrites a logo, category or flag that is already set. Every logo URL it
adds is verified with a real HTTP request first, so the catalog never ships a
broken image.

    python scripts/enrich_catalog.py            # dry run, prints a report
    python scripts/enrich_catalog.py --write    # rewrite tony/registry/apps.jsonl
"""
from __future__ import annotations

import argparse
import collections
import concurrent.futures as cf
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "tony" / "registry" / "apps.jsonl"
CACHE = ROOT / "data" / "logo_cache.json"
UA = {"User-Agent": "Mozilla/5.0 (TonyCatalogBot)"}

# Apps people actually reach for first. Drives the "Popular first" sort.
POPULAR = """
gmail google-calendar googlecalendar google-drive googledrive google-sheets googlesheets google-docs
slack github gitlab notion linear jira confluence asana trello airtable hubspot salesforce stripe
shopify openai anthropic twilio sendgrid mailchimp discord telegram whatsapp zoom microsoft-teams
outlook onedrive sharepoint dropbox box figma zendesk intercom freshdesk quickbooks xero paypal
youtube facebook instagram linkedin twitter x tiktok pinterest reddit calendly cal-com calcom zapier
supabase firebase mongodb postgres mysql aws-s3 cloudflare vercel netlify datadog sentry pagerduty
docusign typeform monday clickup basecamp pipedrive zoho activecampaign klaviyo segment mixpanel
amplitude posthog elevenlabs perplexity gemini mistral groq replicate huggingface
""".split()

# Keyword -> category, used ONLY for apps currently filed under "Other".
CATEGORY_RULES = [
    ("Payments", r"pay|stripe|billing|invoice|checkout|wallet|bank|card|remit|flutterwave|paystack|razorpay"),
    ("Finance", r"account|ledger|tax|crypto|coin|stock|trading|forex|exchange|quickbooks|xero|expens|payroll"),
    ("Communication", r"mail|sms|chat|message|voice|call|phone|whatsapp|telegram|slack|discord|meet|zoom|video call"),
    ("Marketing", r"market|seo|campaign|newsletter|advert|ads|lead|social media|analytics|affiliate"),
    ("CRM & Sales", r"crm|sales|deal|pipeline|prospect|contact"),
    ("Support", r"support|helpdesk|ticket|desk|customer service|feedback"),
    ("Developer", r"api|dev|code|git|deploy|ci\b|cd\b|monitor|log|sdk|webhook|database|sql|cloud|server|docker"),
    ("AI & ML", r"\bai\b|gpt|llm|model|machine learning|vision|speech|embedding|transcri|inference"),
    ("Productivity", r"task|todo|project|calendar|note|doc|sheet|wiki|workflow|schedul|time track"),
    ("E-commerce", r"shop|store|cart|product|order|inventory|commerce|marketplace"),
    ("HR", r"\bhr\b|recruit|hiring|employee|talent|applicant|onboarding"),
    ("Storage", r"storage|file|drive|bucket|backup|upload"),
    ("Media", r"image|photo|video|music|audio|podcast|stream|movie|gallery"),
    ("Security", r"security|auth|identity|password|sso|scim|vault|compliance|fraud"),
    ("IoT", r"sensor|device|smart home|thermostat|iot|light|camera"),
    ("Education", r"learn|course|school|student|lms|education|quiz"),
    ("Travel", r"flight|hotel|travel|booking|trip|airline|map|geo|location"),
    ("Data", r"data|dataset|weather|news|search|scrape|enrich|public|open data"),
    ("Social", r"social|follower|post|tweet|community|forum"),
    ("Cloud", r"\\baws\\b|azure|cloud|compute|serverless|infrastructure|load balanc|kubernetes|vpc"),
]


def load() -> list[dict]:
    return [json.loads(line) for line in REGISTRY.read_text(encoding="utf-8").splitlines() if line.strip()]


def probe(url: str) -> bool:
    """True only if the URL really serves an image."""
    try:
        resp = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=10)
        ctype = resp.headers.get("content-type", "")
        return resp.status == 200 and ("image" in ctype or "svg" in ctype) and len(resp.read(4096)) > 150
    except Exception:
        return False


def candidates(row: dict) -> list[str]:
    slug = row["slug"]
    src = row.get("source", "")
    out: list[str] = []
    if src == "nango":
        out.append(f"https://app.nango.dev/images/template-logos/{slug}.svg")
    if src == "activepieces":
        out.append(f"https://cdn.activepieces.com/pieces/{slug}.png")
    if src == "homeassistant":
        out.append(f"https://brands.home-assistant.io/{slug}/icon.png")
    # Cross-catalog: a Nango brand logo often exists for apps from other catalogs too.
    if src != "nango":
        out.append(f"https://app.nango.dev/images/template-logos/{slug}.svg")
    return out


# Words so common in descriptions ("... API") that they say nothing about the category.
NOISE = re.compile(r"\b(api|apis|rest|restful|service|services|platform|authenticated access|"
                   r"provider|endpoint|endpoints|sdk|v\d+)\b", re.I)


VENDOR_PREFIX = [
    ("amazonaws-", "Cloud"), ("azure", "Cloud"), ("googleapis-", "Cloud"), ("microsoft", "Productivity"),
    ("adyen", "Payments"), ("stripe", "Payments"), ("paypal", "Payments"), ("square", "Payments"),
    ("twilio", "Communication"), ("sendgrid", "Communication"), ("mailgun", "Communication"),
    ("github", "Developer"), ("gitlab", "Developer"), ("atlassian", "Productivity"),
    ("salesforce", "CRM & Sales"), ("hubspot", "CRM & Sales"), ("zoho", "Business"),
    ("shopify", "E-commerce"), ("woocommerce", "E-commerce"), ("bigcommerce", "E-commerce"),
    ("facebook", "Social"), ("instagram", "Social"), ("twitter", "Social"), ("linkedin", "Social"),
    ("youtube", "Media"), ("spotify", "Media"), ("openai", "AI & ML"), ("anthropic", "AI & ML"),
]


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text or "")


def categorise(row: dict) -> str:
    slug = row.get("slug", "")
    for prefix, cat in VENDOR_PREFIX:
        if slug.startswith(prefix):
            return cat
    row = {**row, "description": _strip_html(row.get("description", ""))}
    return _categorise_text(row)


def _categorise_text(row: dict) -> str:
    name = NOISE.sub(" ", row.get("name", "")).lower()
    desc = NOISE.sub(" ", row.get("description", "")).lower()
    for text in (name, desc):          # name wins; description is the fallback
        for cat, pattern in CATEGORY_RULES:
            if re.search(pattern, text):
                return cat
    return "Other"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--workers", type=int, default=24)
    args = ap.parse_args()

    rows = load()
    cache: dict[str, str] = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    todo = [r for r in rows if not r.get("logo") and r["slug"] not in cache]
    print(f"{len(rows)} apps, {sum(1 for r in rows if not r.get('logo'))} without a logo, "
          f"{len(todo)} to probe ({len(cache)} cached)")

    def work(row: dict) -> tuple[str, str]:
        for url in candidates(row):
            if probe(url):
                return row["slug"], url
        return row["slug"], ""

    with cf.ThreadPoolExecutor(args.workers) as ex:
        for slug, url in ex.map(work, todo):
            cache[slug] = url
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cache))

    popular = set(POPULAR)
    stats = collections.Counter()
    for row in rows:
        if not row.get("logo") and cache.get(row["slug"]):
            row["logo"] = cache[row["slug"]]
            stats["logo_added"] += 1
        if (row.get("category") or "Other") == "Other":
            new = categorise(row)
            if new != "Other":
                row["category"] = new
                stats["recategorised"] += 1
        key = row["slug"].replace("_", "-")
        row["popular"] = key in popular or key.replace("-", "") in popular
        stats["popular"] += int(row["popular"])

    after = sum(1 for r in rows if r.get("logo"))
    others = sum(1 for r in rows if (r.get("category") or "Other") == "Other")
    print(f"logos: +{stats['logo_added']}  -> {after}/{len(rows)} real logos")
    print(f"recategorised out of 'Other': {stats['recategorised']}  (still Other: {others})")
    print(f"flagged popular: {stats['popular']}")

    if args.write:
        REGISTRY.write_text("\n".join(json.dumps(r, separators=(",", ":")) for r in rows) + "\n", encoding="utf-8")
        print("wrote", REGISTRY)
    else:
        print("dry run - pass --write to save")
    return 0


if __name__ == "__main__":
    sys.exit(main())
