#!/usr/bin/env python3
"""Summarize Chris Tomer's newest Mountain Weather Update into tomer.json.

Finds the newest daily forecast video from his channel RSS feed, tries to pull the
transcript (youtube-transcript-api, then yt-dlp auto-subs), and writes a short
summary. Uses an LLM when ANTHROPIC_API_KEY or OPENAI_API_KEY is set, otherwise an
extractive keyword summary. Nothing is invented: if the transcript can't be fetched,
the exact error is recorded and the summary is built only from Tomer's own video
description.

Optional env:
  ANTHROPIC_API_KEY / ANTHROPIC_MODEL, OPENAI_API_KEY / OPENAI_MODEL
  YT_PROXY_URL   http(s) proxy for transcript requests (YouTube blocks most cloud IPs)
  YT_COOKIES     Netscape cookies.txt contents for yt-dlp
"""
import datetime as dt
import glob
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
import xml.etree.ElementTree as ET

CHANNEL_ID = "UCb8JPkld8YoOd2n6qAZ2aoQ"  # youtube.com/@TheChristomer
FEED = f"https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL_ID}"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tomer.json")
DAILY_TITLE = re.compile(r"mountain weather update|weather update|forecast", re.I)
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"

REGIONS = {
    "San Juans": ["san juan", "san juans", "wolf creek", "purgatory", "durango", "silverton", "telluride",
                  "red mountain pass", "molas", "coal bank", "southwest colorado", "southwestern colorado",
                  "southern colorado", "southern mountains", "pagosa", "ouray", "la plata", "southwest mountains"],
    "Northern Colorado": ["steamboat", "rabbit ears", "park range", "northern colorado", "northern mountains",
                          "cameron pass", "north park", "winter park", "berthoud"],
    "Central Colorado": ["i-70", "i 70", "summit county", "vail", "aspen", "breckenridge", "loveland",
                         "arapahoe basin", "a-basin", "crested butte", "monarch", "central mountains", "copper"],
    "Wyoming": ["wyoming", "snowy range", "tetons", "teton", "jackson", "togwotee", "sierra madre", "medicine bow"],
    "Utah": ["utah", "wasatch", "logan", "alta", "snowbird", "park city", "cottonwood", "bear river", "brighton",
             "solitude", "beaver mountain"],
    "Idaho": ["idaho", "mccall", "brundage", "sun valley", "sawtooth", "tamarack", "bogus basin", "boise"],
    "Arizona / New Mexico": ["arizona", "new mexico", "taos", "flagstaff", "snowbowl", "santa fe"],
}
STORM_WORDS = ["storm", "system", "front", "trough", "low pressure", "atmospheric river", "snow", "moisture", "remnants"]
CONF_WORDS = ["confidence", "confident", "uncertain", "uncertainty", "models disagree", "model spread", "wild card",
              "could change", "lot of question", "tricky", "bust", "trend", "agreement", "low probability",
              "high probability", "not sold", "big question"]
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
          "november", "december"]
NUM_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
             "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "eighteen": 18, "twenty": 20, "twenty four": 24,
             "thirty": 30, "thirty six": 36}


def http_get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def latest_video():
    ns = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015",
          "media": "http://search.yahoo.com/mrss/"}
    root = ET.fromstring(http_get(FEED))
    entries = []
    for e in root.findall("a:entry", ns):
        title = e.findtext("a:title", "", ns)
        vid = e.findtext("yt:videoId", "", ns)
        link = e.find("a:link", ns)
        url = link.get("href") if link is not None else f"https://www.youtube.com/watch?v={vid}"
        if "/shorts/" in url:
            continue
        entries.append({
            "id": vid, "title": title, "url": f"https://www.youtube.com/watch?v={vid}",
            "published": e.findtext("a:published", "", ns),
            "description": (e.findtext("media:group/media:description", "", ns) or "").strip(),
            "thumbnail": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
        })
    if not entries:
        raise RuntimeError("Channel RSS feed had no videos")
    daily = [v for v in entries if DAILY_TITLE.search(v["title"])]
    return max(daily or entries, key=lambda v: v["published"])


def transcript_api(vid):
    from youtube_transcript_api import YouTubeTranscriptApi
    kwargs = {}
    proxy = os.environ.get("YT_PROXY_URL")
    if proxy:
        from youtube_transcript_api.proxies import GenericProxyConfig
        kwargs["proxy_config"] = GenericProxyConfig(http_url=proxy, https_url=proxy)
    t = YouTubeTranscriptApi(**kwargs).fetch(vid, languages=["en", "en-US"])
    return " ".join(s.text for s in t.snippets)


def transcript_ytdlp(vid):
    with tempfile.TemporaryDirectory() as d:
        cmd = [sys.executable, "-m", "yt_dlp", "--skip-download", "--write-auto-subs", "--write-subs",
               "--sub-langs", "en.*,en", "--sub-format", "vtt", "-o", os.path.join(d, "%(id)s.%(ext)s"),
               f"https://www.youtube.com/watch?v={vid}"]
        if os.environ.get("YT_COOKIES"):
            cf = os.path.join(d, "cookies.txt")
            with open(cf, "w") as f:
                f.write(os.environ["YT_COOKIES"])
            cmd[3:3] = ["--cookies", cf]
        if os.environ.get("YT_PROXY_URL"):
            cmd[3:3] = ["--proxy", os.environ["YT_PROXY_URL"]]
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        files = glob.glob(os.path.join(d, "*.vtt"))
        if not files:
            err = [l for l in (p.stderr or "").splitlines() if "ERROR" in l] or (p.stderr or "").splitlines()[-2:]
            raise RuntimeError(" ".join(err).strip() or f"yt-dlp exited {p.returncode} without subtitles")
        return vtt_to_text(open(files[0], encoding="utf-8").read())


def vtt_to_text(vtt):
    out, last = [], ""
    for line in vtt.splitlines():
        line = re.sub(r"<[^>]+>", "", line).strip()
        if not line or "-->" in line or line.startswith(("WEBVTT", "Kind:", "Language:", "NOTE")):
            continue
        if line != last:  # auto-subs repeat each rolling line
            out.append(line)
            last = line
    return " ".join(out)


def get_transcript(vid):
    errors = []
    for name, fn in (("youtube-transcript-api", transcript_api), ("yt-dlp", transcript_ytdlp)):
        try:
            text = re.sub(r"\s+", " ", fn(vid)).strip()
            if len(text) > 200:
                return {"status": "ok", "source": name, "chars": len(text), "errors": errors}, text
            errors.append(f"{name}: transcript too short ({len(text)} chars)")
        except Exception as e:  # noqa: BLE001 - every failure is recorded verbatim
            msg = re.sub(r"\s+", " ", str(e)).strip()
            errors.append(f"{name}: {type(e).__name__}: {msg[:400]}")
    return {"status": "unavailable", "source": None, "chars": 0, "errors": errors}, ""


# ---------------- extractive summary ----------------

def words_to_digits(text):
    t = " " + text.lower() + " "
    for w, n in sorted(NUM_WORDS.items(), key=lambda kv: -len(kv[0])):
        t = re.sub(rf"(?<=\s){w}(?=\s+(?:to|inches|inch|feet|foot|plus|\-))", str(n), t)
    return t.strip()


def sentences(text):
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [p.strip() for p in parts if p.strip()]


def windows(words, center, before=22, after=14):
    a, b = max(0, center - before), min(len(words), center + after)
    return " ".join(words[a:b])


def nearest_region(words, idx, span=30):
    best = None
    low = [w.lower() for w in words]
    for region, kws in REGIONS.items():
        for kw in kws:
            k = kw.split()
            for i in range(max(0, idx - span), min(len(low) - len(k), idx + 8)):
                if low[i:i + len(k)] == k or (len(k) == 1 and low[i].strip(",.") in (k[0], k[0] + "s")):
                    dist = abs(idx - i) + (0 if i <= idx else 6)
                    if best is None or dist < best[0]:
                        best = (dist, region)
    return best[1] if best else None


AMT = re.compile(
    r"(?P<lo>\d+(?:\.\d+)?)\s*(?:-|–|to)\s*(?P<hi>\d+(?:\.\d+)?)\s*(?:inches|inch|\"|in\b)"
    r"|(?P<one>\d+(?:\.\d+)?)\s*(?:\+|plus)?\s*(?:inches|inch|\")"
    r"|(?P<ft>(?:a|one|\d+(?:\.\d+)?))\s*(?:\+|plus\s)?\s*(?:feet|foot)(?:\s*plus)?", re.I)


def extract_amounts(text):
    t = words_to_digits(text)
    words = t.split()
    joined, offsets, pos = "", [], 0
    for w in words:
        offsets.append(len(joined))
        joined += w + " "
    found = []
    for m in AMT.finditer(joined):
        idx = max(i for i, o in enumerate(offsets) if o <= m.start())
        if m.group("lo"):
            lo, hi = float(m.group("lo")), float(m.group("hi"))
            if hi <= lo or hi > 60:
                continue
            amount = f'{m.group("lo")}–{m.group("hi")}"'
        elif m.group("one"):
            v = float(m.group("one"))
            if v <= 0 or v > 60:
                continue
            amount = f'{m.group("one")}"'
        else:
            f = m.group("ft").lower()
            n = 1 if f in ("a", "one") else float(f)
            if n > 4:  # "10,000 feet" is an elevation, not snow
                continue
            ctx = " ".join(words[max(0, idx - 6):idx + 4])
            if re.search(r"\d,?\d{3}", ctx):
                continue
            amount = "1 ft" if n == 1 else f"{f} ft"
            if "plus" in m.group(0) or "+" in m.group(0):
                amount += "+"
        region = nearest_region(words, idx)
        if not region:
            continue
        found.append({"region": region, "amount": amount, "quote": windows(words, idx)})
    seen, out = set(), []
    for f in found:
        key = (f["region"], f["amount"])
        if key not in seen:
            seen.add(key)
            out.append(f)
    return out


STATES = {"CO": "Colorado", "UT": "Utah", "WY": "Wyoming", "ID": "Idaho", "AZ": "Arizona", "NM": "New Mexico",
          "MT": "Montana"}
DATE_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})(?:\s*-\s*(\d{1,2})/(\d{1,2}))?\b")


def storms_from_description(desc, year):
    storms = []
    for s in sentences(desc):
        dates = list(DATE_RE.finditer(s))
        if not dates or not any(w in s.lower() for w in STORM_WORDS):
            continue
        m = dates[0]
        try:
            start = dt.date(year, int(m.group(1)), int(m.group(2)))
            end = dt.date(year, int(m.group(3)), int(m.group(4))) if m.group(3) else start
        except ValueError:
            continue
        when = start.strftime("%b %-d") + ("" if end == start else "–" + (end.strftime("%-d") if end.month == start.month else end.strftime("%b %-d")))
        states = [STATES[a] for a in re.findall(r"\b(CO|UT|WY|ID|AZ|NM|MT)\b", s) if STATES[a]]
        storms.append({"when": when, "start": start.isoformat(), "end": end.isoformat(), "text": s.strip(),
                       "states": list(dict.fromkeys(states))})
    return storms


def day_refs(text_lower, pub):
    """Map weekday / 'Nth' mentions to calendar dates relative to the video date."""
    refs = set()
    for i, wd in enumerate(WEEKDAYS):
        if wd in text_lower:
            delta = (i - pub.weekday()) % 7
            refs.add(pub + dt.timedelta(days=delta))
    for m in re.finditer(r"(%s)\s+(\d{1,2})(?:st|nd|rd|th)?" % "|".join(MONTHS), text_lower):
        try:
            refs.add(dt.date(pub.year, MONTHS.index(m.group(1)) + 1, int(m.group(2))))
        except ValueError:
            pass
    return refs


def transcript_storm_details(words, storms, pub):
    if not words:
        return
    low = [w.lower() for w in words]
    chunks = [(i, " ".join(low[i:i + 40])) for i in range(0, len(low), 20)]
    for st in storms:
        s, e = dt.date.fromisoformat(st["start"]), dt.date.fromisoformat(st["end"])
        best = None
        for i, c in chunks:
            if not any(w in c for w in STORM_WORDS):
                continue
            hits = [d for d in day_refs(c, pub) if s <= d <= e]
            score = len(hits) * 3 + sum(c.count(w) for w in ("snow", "inches", "storm"))
            if hits and (best is None or score > best[0]):
                best = (score, i)
        if best:
            st["detail"] = " ".join(words[best[1]:best[1] + 40])


def confidence_notes(words):
    low = [w.lower() for w in words]
    text = " ".join(low)
    notes = []
    for kw in CONF_WORDS:
        for m in re.finditer(re.escape(kw), text):
            idx = text[:m.start()].count(" ")
            q = windows(words, idx, 16, 18)
            if not any(q[:40] in n for n in notes):
                notes.append(q)
            break
        if len(notes) >= 2:
            break
    return notes


def snow_levels(text):
    t = words_to_digits(text)
    out = []
    for m in re.finditer(r"((?:snow|freezing) levels?[^.]{0,90}?\d{1,2},?\d{3}\s*(?:feet|foot|ft)?)", t, re.I):
        q = m.group(1).strip()
        if q not in out:
            out.append(q)
    return out[:2]


def extractive_summary(video, transcript):
    pub = dt.datetime.fromisoformat(video["published"].replace("Z", "+00:00")).astimezone(
        dt.timezone(dt.timedelta(hours=-6))).date()
    desc = video["description"]
    storms = storms_from_description(desc, pub.year)
    words = transcript.split() if transcript else []
    transcript_storm_details(words, storms, pub)
    amounts = extract_amounts(transcript) if transcript else []
    amounts += [a for a in extract_amounts(desc) if (a["region"], a["amount"]) not in {(b["region"], b["amount"]) for b in amounts}]
    conf = confidence_notes(words) if words else []
    first = sentences(desc)[0] if desc else video["title"]
    return {
        "method": "extractive",
        "headline": first,
        "storms": storms,
        "amounts": amounts[:10],
        "snow_levels": snow_levels(transcript or desc),
        "confidence": conf[0] if conf else None,
        "confidence_extra": conf[1:],
    }


# ---------------- LLM summary (optional) ----------------

LLM_PROMPT = """You summarize a meteorologist's daily mountain-weather video for skiers and snowmobilers
based in Durango, Colorado. Regions on their dashboard: San Juans (Durango, Purgatory, Wolf Creek, Molas,
Silverton), Northern Colorado (Steamboat/Rabbit Ears), Wyoming (Snowy Range, Sierra Madre), Utah (Logan/Bear
River Range, Wasatch), Idaho (McCall/Brundage, West Central Mtns). Use ONLY what the transcript and description
say; never invent amounts or dates. Video date: {date}.

Return strict JSON with keys:
headline (one sentence), storms (list of {{when, text}} with dates like "Oct 20-23"),
amounts (list of {{region, amount, quote}} only where he gives a number; region must be one of the dashboard
regions or "Central Colorado" / "Arizona / New Mexico"), snow_levels (list of short strings),
confidence (one sentence on how sure he sounded, quoting him if possible, or null).

DESCRIPTION:
{desc}

TRANSCRIPT:
{transcript}"""


def llm_summary(video, transcript):
    prompt = LLM_PROMPT.format(date=video["published"][:10], desc=video["description"], transcript=transcript[:60000])
    if os.environ.get("ANTHROPIC_API_KEY"):
        model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5")
        body = {"model": model, "max_tokens": 1500, "messages": [{"role": "user", "content": prompt}]}
        req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=json.dumps(body).encode(),
                                     headers={"x-api-key": os.environ["ANTHROPIC_API_KEY"],
                                              "anthropic-version": "2023-06-01", "content-type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as r:
            text = json.load(r)["content"][0]["text"]
        method = f"llm:{model}"
    elif os.environ.get("OPENAI_API_KEY"):
        model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        body = {"model": model, "response_format": {"type": "json_object"},
                "messages": [{"role": "user", "content": prompt}]}
        req = urllib.request.Request("https://api.openai.com/v1/chat/completions", data=json.dumps(body).encode(),
                                     headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
                                              "content-type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as r:
            text = json.load(r)["choices"][0]["message"]["content"]
        method = f"llm:{model}"
    else:
        return None
    data = json.loads(re.search(r"\{.*\}", text, re.S).group(0))
    data["method"] = method
    return data


def main():
    video = latest_video()
    print(f"Newest video: {video['published']} {video['title']} {video['url']}")
    tinfo, transcript = get_transcript(video["id"])
    print(f"Transcript: {tinfo['status']} via {tinfo['source']} ({tinfo['chars']} chars)")
    for e in tinfo["errors"]:
        print("  " + e)
    summary, llm_error = None, None
    if transcript:
        try:
            summary = llm_summary(video, transcript)
        except Exception as e:  # noqa: BLE001
            llm_error = f"{type(e).__name__}: {e}"[:300]
            print("LLM summary failed, using extractive:", llm_error)
    if not summary:
        summary = extractive_summary(video, transcript)
    summary["based_on"] = "transcript + description" if transcript else "video description only"
    if llm_error:
        summary["llm_error"] = llm_error
    out = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "video": {k: video[k] for k in ("id", "title", "url", "published", "thumbnail")},
        "description": video["description"],
        "transcript": tinfo,
        "summary": summary,
    }
    try:
        with open(OUT) as f:
            old = json.load(f)
        if {**old, "generated_at": None} == {**out, "generated_at": None}:
            print("No change since", old.get("generated_at"))
            return
    except (OSError, ValueError):
        pass
    with open(OUT, "w") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
