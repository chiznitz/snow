#!/usr/bin/env python3
"""Build afd.json: the extended-forecast excerpt from each NWS office's Area Forecast Discussion.

Uses api.weather.gov. Offices differ in layout (.LONG TERM, .EXTENDED, .DISCUSSION, .KEY MESSAGES),
and some offices issue aviation-only updates under the same product code, so this walks back through
recent issuances until it finds one with a forecast section. Nothing is paraphrased: the excerpt is
the forecaster's own text, cut at a sentence boundary.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "afd.json")
OFFICES = {
    "GJT": "Grand Junction", "BOU": "Boulder / Denver", "PUB": "Pueblo",
    "CYS": "Cheyenne", "SLC": "Salt Lake City", "BOI": "Boise",
}
HEADERS = {"User-Agent": "chiznitz-snow (github.com/chiznitz/snow)", "Accept": "application/geo+json"}
PREFERRED = ["LONG TERM", "EXTENDED", "DISCUSSION", "KEY MESSAGES", "SHORT TERM"]
EXCERPT_CHARS = 260
SECTION_CHARS = 2000


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=40) as r:
        return json.load(r)


def sections(text):
    """Split an AFD into {NAME: body}. Headers look like '.LONG TERM /SUNDAY THROUGH THURSDAY/...'."""
    out, name, buf = {}, None, []
    for line in text.splitlines():
        m = re.match(r"^\.([A-Za-z][A-Za-z0-9 /&\-\(\)\.,']*?)\.{3}\s*(.*)$", line)
        if m:
            if name:
                out[name] = "\n".join(buf)
            name, buf = re.sub(r"\s*(/.*|,\s*Issued.*)$", "", m.group(1), flags=re.I).strip().upper(), [m.group(2)]
        elif line.strip() == "&&":
            if name:
                out[name] = "\n".join(buf)
            name, buf = None, []
        elif name:
            buf.append(line)
    if name:
        out[name] = "\n".join(buf)
    return out


def paragraphs(body):
    paras = []
    for p in re.split(r"\n\s*\n", body):
        p = re.sub(r"\s+", " ", p).strip()
        p = re.sub(r"^Issued \d{3,4} [AP]M \w+ \w+ \w+ \d+ \d{4}\s*", "", p)  # per-section issue stamps
        p = re.sub(r"\s*-\s*[A-Z]{2,3}$|\s*\.\.\.\s*[A-Za-z]+$", "", p)          # forecaster initials
        if len(p) > 40:
            paras.append(p)
    return paras


def one_line(text, limit=EXCERPT_CHARS):
    sents = re.split(r"(?<=[.!?])\s+", text)
    out = ""
    for s in sents:
        if out and len(out) + len(s) + 1 > limit:
            break
        out = (out + " " + s).strip()
    if not out:
        out = text[:limit].rsplit(" ", 1)[0] + "…"
    return out


ADMIN = re.compile(r"\b(warnings?|advisor(y|ies)|headlines?|no changes|on track|previous discussion|see .* for details)\b", re.I)


def extended_paragraph(paras):
    """The furthest-out discussion is almost always the last real forecast paragraph; skip
    short housekeeping notes about headlines and warnings that some offices tack on the end."""
    for p in reversed(paras):
        if len(p) >= 120 and not (len(p) < 300 and ADMIN.search(p)):
            return p
    return paras[-1]


def pick(text):
    secs = sections(text)
    for want in PREFERRED:
        for name, body in secs.items():
            if name.startswith(want):
                paras = paragraphs(body)
                if paras:
                    return name, paras
    return None, []


def office(code):
    listing = get(f"https://api.weather.gov/products/types/AFD/locations/{code}")
    for item in listing.get("@graph", [])[:6]:
        prod = get(item["@id"])
        text = prod.get("productText", "")
        name, paras = pick(text)
        if not paras:
            continue
        return {
            "office": code, "name": OFFICES[code],
            "issued": prod["issuanceTime"],
            "section": name,
            "excerpt": one_line(extended_paragraph(paras)),
            "text": "\n\n".join(paras)[:SECTION_CHARS],
            "url": f"https://forecast.weather.gov/product.php?site=NWS&issuedby={code}&product=AFD&format=txt",
        }
    raise RuntimeError(f"{code}: none of the recent AFDs had a forecast section")


def main():
    out = {"generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "offices": {}, "errors": []}
    for code in OFFICES:
        try:
            out["offices"][code] = office(code)
            print(f"{code}: {out['offices'][code]['section']} · {out['offices'][code]['excerpt'][:80]}…", file=sys.stderr)
        except Exception as e:  # keep the other offices; record what failed verbatim
            out["errors"].append(f"{code}: {type(e).__name__}: {e}")
            print(out["errors"][-1], file=sys.stderr)
    if os.path.exists(OUT):
        try:
            with open(OUT) as f:
                old = json.load(f)
            old.pop("generated_at", None)
            new = dict(out)
            new.pop("generated_at", None)
            if old == new:
                print("afd.json unchanged", file=sys.stderr)
                return
            # Keep an office's last good text if it failed this time.
            for code, rec in old.get("offices", {}).items():
                out["offices"].setdefault(code, rec)
        except (OSError, ValueError):
            pass
    with open(OUT, "w") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    print(f"wrote {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
