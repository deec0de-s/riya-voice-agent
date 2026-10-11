"""Day 3: turn call_log.csv into report.html (booking rate, drop-offs, failure modes).

Usage:  python analysis.py                         (all calls in call_log.csv -> report.html)
        python analysis.py --first 33 --out report_before.html   (only the first 33 calls)
        python analysis.py --last 25  --out report_after.html    (only the last 25 calls)
        python analysis.py other.csv

No extra libraries needed. Open report.html in your browser, take screenshots for the README.
The automatic checks are heuristics: they point you at calls to READ, they don't replace reading.
"""
import csv
import html
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import argparse

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))
_ap = argparse.ArgumentParser()
_ap.add_argument("csv", nargs="?", default=None)
_ap.add_argument("--first", type=int, help="only analyse the first N calls in the file")
_ap.add_argument("--last", type=int, help="only analyse the last N calls in the file")
_ap.add_argument("--out", default="report.html", help="name of the report file to write")
ARGS = _ap.parse_args()
SRC = Path(ARGS.csv) if ARGS.csv else BASE / "call_log.csv"
OUT = Path(ARGS.out) if Path(ARGS.out).is_absolute() else BASE / ARGS.out
PROJECTS = json.loads((BASE / "projects.json").read_text())["projects"]
try:
    from scenarios import BOOKABLE  # scenarios where a booking is the right outcome
except Exception:
    BOOKABLE = set()

# ---------- price check ----------
ALLOWED = set()
for p in PROJECTS:
    for c in p["configurations"]:
        ALLOWED.update({c["price_lakhs_min"], c["price_lakhs_max"]})

ONES = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
    "fifteen sixteen seventeen eighteen nineteen".split())}
TENS = {w: 10 * i for i, w in enumerate(
    "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()) if w != "_"}
_NUMW = "|".join(sorted(list(ONES) + list(TENS) + ["hundred"], key=len, reverse=True))
PRICE_RE = re.compile(
    rf"\b(\d+(?:\.\d+)?|(?:{_NUMW})(?:[\s-]+(?:{_NUMW}))*)\s*(crores?|cr|lakhs?)\b", re.I)


def words_to_num(s):
    total, cur = 0, 0
    for tok in re.split(r"[\s-]+", s.lower()):
        if tok in ONES:
            cur += ONES[tok]
        elif tok in TENS:
            cur += TENS[tok]
        elif tok == "hundred":
            cur = max(cur, 1) * 100
        elif tok == "and":
            continue
        else:
            return None
    return total + cur


def price_mentions(text):
    """Return prices mentioned in `text`, in lakhs (handles '1.3 crore', 'one crore eighteen lakhs')."""
    # Models often write "sixty‑five" with a non-ASCII hyphen; normalise before parsing.
    text = re.sub(r"[‐-―−]", "-", text)
    text = text.replace(" ", " ").replace(" ", " ")
    # "one hundred and eighteen" -> "one hundred eighteen". "and" is only joined after "hundred",
    # so a range like "seventy-two and eighty-two lakhs" is not read as one number.
    text = re.sub(r"\bhundred\s+and\b", "hundred", text, flags=re.I)
    found, prev_end, prev_crore = [], -1, None
    for m in PRICE_RE.finditer(text):
        raw, unit = m.group(1), m.group(2).lower()
        try:
            num = float(raw)
        except ValueError:
            num = words_to_num(raw)
        if num is None:
            continue
        is_crore = unit.startswith("cr")
        val = num * 100 if is_crore else num
        gap = text[prev_end:m.start()].strip().lower() if prev_end >= 0 else None
        if prev_crore is not None and not is_crore and gap in ("", "and"):
            found[-1] = prev_crore + val
            prev_crore = None
        else:
            found.append(val)
            prev_crore = val if is_crore else None
        prev_end = m.end()
    return found


# ---------- other checks ----------
CLAIMS_BOOKED = re.compile(
    r"\b(booked|you're all set|is confirmed|has been confirmed|scheduled for)\b|बुक कर दी|बुक हो गई|कन्फर्म|ಬುಕ್ ಮಾಡಲಾಗಿದೆ", re.I)
MARKDOWN = re.compile(r"(\*\*|^#+\s|^\s*[-*•]\s|`)", re.M)


def sentences(t):
    return [s for s in re.split(r"[.!?।]+\s*", t) if s.strip()]


def statements(t):
    """Sentences that are NOT questions. A number inside a question (\"around one crore?\") is
    Riya asking the caller, not quoting a project price, so the price check skips it."""
    parts = re.findall(r"[^.!?।]+[.!?।]?", t)
    return " ".join(p.strip() for p in parts if p.strip() and not p.strip().endswith("?"))


def check_call(row, turns):
    issues = []
    agent_turns = [t for r, t in turns if r == "agent"]
    caller_text = " ".join(t for r, t in turns if r == "caller")
    booked = row["visit_booked"] == "True"
    caller_prices = {round(x, 1) for x in price_mentions(caller_text)}
    for t in agent_turns:
        if CLAIMS_BOOKED.search(t) and not booked:
            issues.append(("Claims booking without a successful tool call", t))
        bad = [p for p in price_mentions(statements(t))
               if not any(abs(p - a) < 0.6 for a in ALLOWED | caller_prices)]
        if bad:
            issues.append(("Price not found in project data", t))
        if t.count("?") > 1:
            issues.append(("Several questions in one reply", t))
        elif re.search(r",\s*and\s+(when|what|which|where|how|do you|are you|is it)\b[^?]*\?", t, re.I):
            issues.append(("Two questions joined by 'and'", t))
        elif re.search(r"[,，]\s*(और|aur)\s+[^?]*(कब|क्या|कौन|कितना|कहाँ|कैसे|किस|kab|kya|kaun|kitna|kahan|kaise)[^?]*\?", t):
            issues.append(("Two questions joined by 'and'", t))
        if re.search(r"लाख|करोड़|లಕ್ಷ|ಕೋಟಿ", t):
            issues.append(("Price quoted in Hindi/Kannada (not auto-checked: read it)", t))
        if len(sentences(t)) > 3 or len(t.split()) > 60:
            issues.append(("Reply too long for a phone call", t))
        if MARKDOWN.search(t):
            issues.append(("Markdown in a spoken reply", t))
    if int(row["failed_booking_attempts"] or 0) > 0:
        issues.append(("Booking attempt rejected (bad slot)", ""))
    return issues


# ---------- load ----------
if not SRC.exists():
    sys.exit(f"{SRC} not found. Run `python agent.py --scenarios --repeat 4` first.")
rows = list(csv.DictReader(SRC.open(encoding="utf-8")))
if not rows:
    sys.exit("call_log.csv is empty.")
if ARGS.first:
    rows = rows[: ARGS.first]
if ARGS.last:
    rows = rows[-ARGS.last:]

by_scn = defaultdict(list)
issue_counts = Counter()
flagged = []
unbooked = []
for r in rows:
    turns = json.loads(r["transcript"])
    iss = check_call(r, turns)
    r["_issues"] = iss
    by_scn[r["scenario"]].append(r)
    for kind, _ in iss:
        issue_counts[kind] += 1
    if iss:
        flagged.append(r)
    if r["visit_booked"] != "True":
        last_agent = next((t for ro, t in reversed(turns) if ro == "agent"), "")
        unbooked.append((r, last_agent))

n = len(rows)
booked_n = sum(r["visit_booked"] == "True" for r in rows)
cb_n = sum(r["callback_requested"] == "True" for r in rows)
avg_turns = sum(int(r["turns"]) for r in rows) / n
fb_n = sum(int(r["failed_booking_attempts"] or 0) for r in rows)
flag_n = len(flagged)
bk_rows = [r for r in rows if r["scenario"] in BOOKABLE]
bk_n, bk_booked = len(bk_rows), sum(r["visit_booked"] == "True" for r in bk_rows)

# ---------- console summary ----------
if bk_n:
    print(f"Booking rate on calls where booking is the goal: {bk_booked}/{bk_n} ({bk_booked / bk_n:.0%})")
print(f"Calls: {n} | booked: {booked_n} ({booked_n / n:.0%}) | callbacks: {cb_n} | "
      f"avg turns: {avg_turns:.1f} | rejected bookings: {fb_n} | calls with issues: {flag_n}")
for k, v in issue_counts.most_common():
    print(f"  - {k}: {v}")

# ---------- html ----------
e = html.escape


def pct(a, b):
    return f"{(a / b * 100):.0f}%" if b else "-"


scn_rows = ""
for name, rs in sorted(by_scn.items()):
    b = sum(x["visit_booked"] == "True" for x in rs)
    t = sum(int(x["turns"]) for x in rs) / len(rs)
    iss = sum(1 for x in rs if x["_issues"])
    w = int(b / len(rs) * 100)
    scn_rows += (f"<tr><td>{e(name)}</td><td>{len(rs)}</td>"
                 f"<td><div class=bar><span style='width:{w}%'></span></div>{pct(b, len(rs))}</td>"
                 f"<td>{t:.1f}</td><td>{iss}</td></tr>")

mx = max(issue_counts.values(), default=1)
fail_rows = "".join(
    f"<tr><td>{e(k)}</td><td><div class=bar warn><span style='width:{v / mx * 100:.0f}%'></span></div>{v}</td></tr>"
    for k, v in issue_counts.most_common()) or "<tr><td colspan=2>No issues flagged by the automatic checks.</td></tr>"

ex_rows = ""
for r in flagged[:40]:
    for kind, text in r["_issues"][:3]:
        ex_rows += (f"<tr><td>{e(r['call_id'])}</td><td>{e(r['scenario'])}</td><td>{e(kind)}</td>"
                    f"<td>{e(text[:220])}</td></tr>")

drop_rows = ""
for r, last in unbooked[:60]:
    drop_rows += (f"<tr><td>{e(r['call_id'])}</td><td>{e(r['scenario'])}</td><td>{r['turns']}</td>"
                  f"<td>{e(last[:200])}</td></tr>")

# Full transcripts of Hindi / Kannada calls, to check the reply language by eye.
lang_html = ""
for r in rows:
    sc = r["scenario"]
    if "hindi" in sc or sc.endswith(("-hi", "-kn")):
        lines = "".join(
            f"<p><b>{'Riya' if ro == 'agent' else 'Caller'}:</b> {e(t)}</p>"
            for ro, t in json.loads(r["transcript"]) if ro in ("agent", "caller"))
        lang_html += (f"<details><summary>{e(r['call_id'])} · {e(sc)} · "
                      f"{'booked' if r['visit_booked'] == 'True' else 'not booked'}</summary>{lines}</details>")
lang_html = lang_html or "<p class=note>No Hindi or Kannada calls in this set.</p>"
bk_tile = (f"<div><b>{bk_booked}/{bk_n}</b><span>booked, on scenarios where booking is the goal</span></div>"
           if bk_n else "")

page = f"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>Riya call analysis</title>
<style>
:root{{--bg:#fff;--fg:#1a1a1a;--mut:#666;--card:#f4f5f7;--acc:#2b59c3;--warn:#c2410c;--line:#e2e4e8}}
@media(prefers-color-scheme:dark){{:root{{--bg:#111318;--fg:#eceef2;--mut:#9aa0ab;--card:#1b1e25;--acc:#6b93ee;--warn:#f08a4b;--line:#2c303a}}}}
body{{background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif;margin:0;padding:24px 16px}}
main{{max-width:980px;margin:auto}} h1{{font-size:24px;margin:0 0 4px}} h2{{font-size:17px;margin:32px 0 8px}}
p.s{{color:var(--mut);margin:0 0 20px}}
.k{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}}
.k div{{background:var(--card);border-radius:10px;padding:14px}} .k b{{display:block;font-size:26px}}
.k span{{color:var(--mut);font-size:13px}}
table{{width:100%;border-collapse:collapse;font-size:14px}} th,td{{text-align:left;padding:8px 6px;border-bottom:1px solid var(--line);vertical-align:top}}
th{{color:var(--mut);font-weight:600}} .bar{{display:inline-block;width:110px;height:8px;background:var(--line);border-radius:4px;margin-right:8px;vertical-align:middle}}
.bar span{{display:block;height:100%;background:var(--acc);border-radius:4px}} .bar[warn] span{{background:var(--warn)}}
.note{{color:var(--mut);font-size:13px}} .scroll{{overflow-x:auto}}
details{{background:var(--card);border-radius:8px;padding:8px 12px;margin:6px 0}} summary{{cursor:pointer}} details p{{margin:4px 0}}
</style></head><body><main>
<h1>Riya call analysis</h1><p class=s>{n} calls from {e(SRC.name)}. Checks are heuristics: read the flagged calls yourself.</p>
<div class=k>
<div><b>{n}</b><span>calls</span></div>
{bk_tile}
<div><b>{pct(booked_n, n)}</b><span>booked, all calls ({booked_n}); includes scenarios that should not book</span></div>
<div><b>{avg_turns:.1f}</b><span>avg turns per call</span></div>
<div><b>{cb_n}</b><span>callback requests</span></div>
<div><b>{fb_n}</b><span>rejected booking attempts</span></div>
<div><b>{pct(flag_n, n)}</b><span>calls with a flagged issue</span></div></div>
<h2>By scenario</h2><div class=scroll><table><tr><th>Scenario</th><th>Calls</th><th>Booked</th><th>Avg turns</th><th>Flagged</th></tr>{scn_rows}</table></div>
<h2>Failure modes found</h2><div class=scroll><table><tr><th>Issue</th><th>Count</th></tr>{fail_rows}</table></div>
<h2>Flagged examples</h2><div class=scroll><table><tr><th>Call</th><th>Scenario</th><th>Issue</th><th>Agent said</th></tr>{ex_rows}</table></div>
<h2>Calls that did not end in a booking</h2><p class=note>Not all of these are failures (a caller who is not interested should not be booked). Look for ones that should have booked.</p>
<div class=scroll><table><tr><th>Call</th><th>Scenario</th><th>Turns</th><th>Riya's last line</th></tr>{drop_rows}</table></div>
<h2>Hindi and Kannada calls (read these)</h2><p class=note>Check that Riya answers in the caller's language.</p>{lang_html}
</main></body></html>"""
OUT.write_text(page, encoding="utf-8")
print(f"Wrote {OUT}. Open it in your browser.")