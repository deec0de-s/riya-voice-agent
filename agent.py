"""MASAL-style real estate lead-qualifying agent (text version, Day 1).

Works with ANY OpenAI-compatible LLM API, including free tiers (Groq, Google Gemini, OpenRouter)
and local Ollama. Configure with three environment variables:

    LLM_API_KEY    your key
    LLM_BASE_URL   default: https://api.groq.com/openai/v1
    LLM_MODEL      default: llama-3.3-70b-versatile

Run interactively:   python agent.py
Run test scenarios:  python agent.py --scenarios
"""
import argparse
import csv
import json
import os
import re
import sys
import uuid
from datetime import datetime
from pathlib import Path

from openai import OpenAI

from prompts import SYSTEM_PROMPT

MODEL = os.environ.get("LLM_MODEL", "llama-3.3-70b-versatile")
BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.groq.com/openai/v1")
BASE = Path(__file__).parent
PROJECTS = json.loads((BASE / "projects.json").read_text())["projects"]
LOG_FILE = BASE / "call_log.csv"
BOOKINGS: list[dict] = []

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_project_info",
            "description": (
                "Look up real project details (price range, area, possession, amenities, nearby, "
                "visit hours). Filter by locality and/or bhk and/or max budget in lakhs. "
                "This is the ONLY allowed source of project facts."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "locality": {"type": "string", "description": "e.g. Whitefield, Hebbal"},
                    "bhk": {"type": "integer"},
                    "max_budget_lakhs": {"type": "number"},
                    "project_name": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "book_site_visit",
            "description": "Book a site visit. Returns success or an error with allowed slots.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "string"},
                    "customer_name": {"type": "string"},
                    "date": {"type": "string", "description": "YYYY-MM-DD"},
                    "time": {"type": "string", "description": "HH:MM, 24h"},
                },
                "required": ["project_id", "customer_name", "date", "time"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "request_callback",
            "description": "Arrange a callback from a human sales executive.",
            "parameters": {
                "type": "object",
                "properties": {"reason": {"type": "string"}},
                "required": ["reason"],
            },
        },
    },
]


def get_project_info(locality=None, bhk=None, max_budget_lakhs=None, project_name=None):
    results = []
    for p in PROJECTS:
        if project_name and project_name.lower() not in p["name"].lower():
            continue
        if locality and locality.lower() not in p["locality"].lower():
            continue
        configs = p["configurations"]
        if bhk:
            configs = [c for c in configs if c["bhk"] == bhk]
        if max_budget_lakhs:
            configs = [c for c in configs if c["price_lakhs_min"] <= max_budget_lakhs]
        if not configs:
            continue
        results.append({**p, "configurations": configs})
    return results or {"message": "No matching project. Offer a callback from the sales team."}


def book_site_visit(project_id, customer_name, date, time):
    project = next((p for p in PROJECTS if p["id"] == project_id), None)
    if not project:
        return {"success": False, "error": "Unknown project_id"}
    try:
        when = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
    except ValueError:
        return {"success": False, "error": "Bad date/time format"}
    if when < datetime.now():
        return {"success": False, "error": "That time is in the past"}
    day = when.strftime("%a")
    allowed_days = project["visit_days"]
    open_t, close_t = project["visit_hours"].split("-")
    if allowed_days == "Mon-Sat" and day == "Sun":
        return {"success": False, "error": f"Closed on Sundays. Visit days: {allowed_days}"}
    if not (open_t <= time <= close_t):
        return {"success": False, "error": f"Outside visit hours {project['visit_hours']}"}
    BOOKINGS.append({"project": project["name"], "name": customer_name, "when": str(when)})
    return {"success": True, "project": project["name"], "when": when.strftime("%A %d %b, %H:%M")}


def request_callback(reason):
    return {"success": True, "note": "Callback queued", "reason": reason}


TOOL_FUNCS = {
    "get_project_info": get_project_info,
    "book_site_visit": book_site_visit,
    "request_callback": request_callback,
}


def one_turn(text):
    """Voice guard (code-level, in addition to the prompt rule): end the reply at the first
    question, so Riya can never fire several questions at the caller in one breath."""
    i = text.find("?")
    return text if i == -1 else text[: i + 1].strip()


def run_turn(client, messages, tool_calls_log, hint=None):
    """Run the model until it produces a final text reply (handles tool loops).
    `hint` is a per-turn instruction (e.g. the reply language). It is added to the system message
    on every model call of this turn, including the call after a tool result, and is not saved."""
    while True:
        api_messages = messages
        if hint:
            api_messages = ([dict(messages[0], content=messages[0]["content"] + "\n\n" + hint)]
                            + messages[1:])
        resp = client.chat.completions.create(
            model=MODEL,
            max_tokens=400,
            messages=api_messages,
            tools=TOOLS,
        )
        msg = resp.choices[0].message
        entry = {"role": "assistant", "content": msg.content or ""}
        if msg.tool_calls:
            entry["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in msg.tool_calls
            ]
        messages.append(entry)
        if not msg.tool_calls:
            reply = one_turn((msg.content or "").strip())
            entry["content"] = reply  # keep history consistent with what the caller heard
            return reply
        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
                out = TOOL_FUNCS[tc.function.name](**args)
            except Exception as e:  # keep the call alive; let the model recover
                args, out = {}, {"error": str(e)}
            tool_calls_log.append({"tool": tc.function.name, "input": args, "output": out})
            messages.append(
                {"role": "tool", "tool_call_id": tc.id, "content": json.dumps(out)}
            )


def log_call(call_id, scenario, transcript, tool_calls):
    booked = any(t["tool"] == "book_site_visit" and t["output"].get("success") for t in tool_calls)
    failed_bookings = sum(
        1 for t in tool_calls if t["tool"] == "book_site_visit" and not t["output"].get("success")
    )
    new = not LOG_FILE.exists()
    with LOG_FILE.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["call_id", "timestamp", "scenario", "turns", "visit_booked",
                        "failed_booking_attempts", "callback_requested", "transcript"])
        w.writerow([
            call_id, datetime.now().isoformat(timespec="seconds"), scenario,
            len(transcript) // 2, booked, failed_bookings,
            any(t["tool"] == "request_callback" for t in tool_calls),
            json.dumps(transcript, ensure_ascii=False),
        ])


LANG_NOTES = {
    "English": "",
    "Hindi": "\nThe caller prefers Hindi. Reply in Hindi, written in Devanagari script, "
             "keeping property terms like BHK as they are. Keep sentences short for speech.",
    "Kannada": "\nThe caller prefers Kannada. Reply in Kannada, written in Kannada script, "
               "keeping property terms like BHK as they are. Keep sentences short for speech.",
}


LANG_HINTS = {
    "Hindi": "LANGUAGE FOR THIS TURN: the caller speaks Hindi. Write your whole reply in Hindi, "
             "including any booking confirmation. Use Devanagari script if the caller used it, "
             "otherwise Hindi in English letters. Keep BHK, project names and times as they are.",
    "Kannada": "LANGUAGE FOR THIS TURN: the caller speaks Kannada. Write your whole reply in "
               "Kannada script, including any booking confirmation. Keep BHK, project names "
               "and times as they are.",
}
# Words that are Hindi but not English (for callers who type Hindi in English letters).
_HINGLISH = set(
    "haan han nahi nahin mera meri mujhe hai hain hoon chahiye kal aap aapka naam kitna boliye "
    "shaam subah kya accha acha theek karna batao bataiye mein sakta sakte rahe aur abhi "
    "dhanyavaad shukriya namaste".split())


def detect_lang(text):
    """Very small language detector: Hindi / Kannada / English."""
    if re.search(r"[ऀ-ॿ]", text):
        return "Hindi"
    if re.search(r"[ಀ-೿]", text):
        return "Kannada"
    words = re.findall(r"[a-z]+", text.lower())
    return "Hindi" if any(w in _HINGLISH for w in words) else "English"


class Session:
    """One phone call. Used by the terminal version and the web app."""

    def __init__(self, client, language="English", scenario="interactive"):
        self.client = client
        self.language = language
        self.scenario = scenario
        self.call_id = uuid.uuid4().hex[:8]
        self.transcript, self.tool_calls = [], []
        self.closed = False
        system = (SYSTEM_PROMPT + LANG_NOTES.get(language, "")
                  + f"\nToday's date is {datetime.now():%A %Y-%m-%d}.")
        self.messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": "[Call connected. The caller picked up.]"},
        ]

    def start(self):
        reply = run_turn(self.client, self.messages, self.tool_calls,
                         hint=LANG_HINTS.get(self.language))
        self.transcript += [("system", "call connected"), ("agent", reply)]
        return reply

    def say(self, text):
        # Language is "sticky": once the caller speaks Hindi/Kannada we keep answering in it,
        # and only go back to English when they write a clear English sentence.
        seen = detect_lang(text)
        if seen != "English":
            self.language = seen
        elif len(text.split()) >= 4:
            self.language = "English"
        self.messages.append({"role": "user", "content": text})
        reply = run_turn(self.client, self.messages, self.tool_calls,
                         hint=LANG_HINTS.get(self.language))
        self.transcript += [("caller", text), ("agent", reply)]
        return reply

    def close(self):
        if not self.closed:
            self.closed = True
            log_call(self.call_id, self.scenario, self.transcript, self.tool_calls)


def converse(client, user_inputs=None, scenario="interactive"):
    """If user_inputs is given, play them as the caller; otherwise read from stdin."""
    s = Session(client, scenario=scenario)
    print(f"Riya: {s.start()}")
    inputs = iter(user_inputs) if user_inputs else None
    while True:
        try:
            text = next(inputs) if inputs else input("You:  ")
        except (StopIteration, EOFError, KeyboardInterrupt):
            break
        if inputs:
            print(f"You:  {text}")
        if text.strip().lower() in {"quit", "exit", "bye"}:
            break
        print(f"Riya: {s.say(text)}")
    s.close()
    print(f"\n[logged call {s.call_id}; bookings so far: {len(BOOKINGS)}]\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", action="store_true", help="run scripted test calls")
    ap.add_argument("--repeat", type=int, default=1,
                    help="with --scenarios: run every scenario this many times (4 = 32 calls)")
    ap.add_argument("--only", nargs="+", metavar="NAME",
                    help="with --scenarios: run only these scenarios, e.g. --only hindi_caller")
    args = ap.parse_args()
    key = os.environ.get("LLM_API_KEY")
    if not key:
        sys.exit("Set LLM_API_KEY first (see README steps).")
    client = OpenAI(api_key=key, base_url=BASE_URL)
    if args.scenarios:
        from scenarios import SCENARIOS
        import time
        for i in range(args.repeat):
            for name, lines in SCENARIOS.items():
                if args.only and name not in args.only:
                    continue
                print(f"===== {name} (run {i + 1}/{args.repeat}) =====")
                try:
                    converse(client, lines, scenario=name)
                except Exception as e:  # e.g. free-tier rate limit: wait and move on
                    print(f"[skipped: {e}]")
                    time.sleep(20)
    else:
        converse(client)


if __name__ == "__main__":
    main()