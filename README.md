---
title: Riya Real Estate Voice Assistant
emoji: 🏠
colorFrom: blue
colorTo: indigo
sdk: gradio
sdk_version: 5.50.0
app_file: app.py
pinned: false
---

# Riya: a real estate lead-qualifying voice assistant

A voice and text AI agent that calls (or chats with) a property enquiry, qualifies the lead
(budget, location, BHK, intent, timeline), answers project questions from a fixed database,
and books a site visit through a function call. Works in **English, Hindi and Kannada**.

> Demo uses **fictional** projects in `projects.json`.

## What it does
- **Qualifies leads** in a natural, short, phone-style conversation (one question at a time).
- **Tool calling:** `get_project_info` (only allowed source of facts), `book_site_visit`
  (validates visit days/hours), `request_callback` (hand-off to a human).
- **Guardrails:** never invents prices, discounts, returns or availability; never confirms a
  booking unless the tool returned success; admits it is an AI if asked.
- **Voice:** speech-to-text with Whisper (Groq), spoken replies with edge-tts (Indian voices).
- **Call logs:** every call saved to `call_log.csv` (turns, booked or not, failed bookings).

## Architecture
```
Caller (mic or text) -> Whisper STT -> LLM (system prompt + guardrails)
                                          |-> get_project_info -> projects.json
                                          |-> book_site_visit  -> booking rules
                                          |-> request_callback
                     <- edge-tts voice <- reply
                                          -> call_log.csv
```

## Run it yourself
```
pip install -r requirements.txt
# Windows PowerShell:  $env:LLM_API_KEY="your-groq-key"
# Mac/Linux:           export LLM_API_KEY="your-groq-key"
python app.py          # web app with voice
python agent.py        # terminal chat
python agent.py --scenarios   # 8 scripted test calls -> call_log.csv
python agent.py --scenarios --repeat 4   # 32 calls for analysis
python analysis.py     # call_log.csv -> report.html (booking rate, failure modes)
```
Get a free key at console.groq.com. Optional: `LLM_MODEL`, `LLM_BASE_URL` (any
OpenAI-compatible API works).

## Known limitations (honest notes)
- Hindi and Kannada speech recognition is less accurate than English, especially with noise
  and mixed-language speech.
- Free-tier models are weaker at tool calling than paid ones; see test findings below.
- No real telephony yet; browser mic only.

## Call analysis
`analysis.py` reads `call_log.csv` and writes `report.html` with booking rate, average turns,
rejected bookings, and automatic checks for failure modes: claiming a booking without a
successful tool call, quoting a price that is not in the project data, replies too long for a
phone call, and markdown in spoken replies. These checks are heuristics that point to calls worth
reading; they do not replace reading them.

## Test findings
## Test findings
I ran 8 scripted caller scenarios (happy path, vague budget, discount pressure, Sunday booking,
no inventory, not interested, off-topic/human request, Hindi) before and after changing the
prompt, then analysed the logs with `analysis.py`. Model: openai/gpt-oss-120b on Groq (free tier).

| | Before (33 calls) | After (25 calls) |
|---|---|---|
| Booked, on scenarios where booking is the goal | 10/12 | 7/8 |
| Calls with several questions in one reply | 8 | 0 |
| Calls flagged by any automatic check | 24% | 0% |
| Rejected booking attempts | 0 | 0 |

**Problems found**
1. Riya packed several questions into one reply, breaking the "one question at a time" voice rule.
2. In the discount-pressure scenario she hinted at promotions ("we can explore any promotions
   when you visit") even though the rules forbid it.
3. She answered some Hindi callers in English.
4. My own checker gave false positives on spelled-out prices (a special hyphen character, and
   "seventy-two and eighty-two lakhs" read as one number). I fixed the checker, not the agent.

**Fixes**: stricter prompt rules (one short turn, never hint at offers, never suggest a budget,
mirror the caller's language) plus a code-level guard that cuts a reply at its first question.

**Caveats**: small samples; scripted callers do not react to what Riya asks, so booking rates
depend on the script; prompt and guard were changed together, so their effects are not separated;
the checks are heuristics; 7 of the 32 planned "after" calls did not complete (rate limits).

## Test findings

I ran 8 scripted caller scenarios (English, Hindi) against the agent and read the flagged transcripts myself.

- Before fixes (33 calls): 10/12 bookable calls booked; 24% of calls flagged, mostly several questions in one turn. Reading transcripts also showed wrong-weekday bookings.
- After fixes (final run, 30 calls): 10/10 bookable calls booked; 17% flagged; no wrong-weekday bookings.
- Fixes: tighter prompt rules (one question per turn, exact prices, no budget nagging), a calendar in the prompt, a weekday check inside the booking tool, retry on failed tool calls, a per-turn language hint.

Limitations:
- Small samples (3-4 calls per scenario). Scripted callers don't react to Riya.
- I didn't separate the effect of prompt changes from code guards.
- Checks are heuristics, not ground truth. Hindi/Kannada prices are checked by reading, not automatically.
- Remaining issue: Riya still sometimes joins two questions with "and" (4 calls, mostly Hindi).
- Free-tier rate limits skipped some calls in earlier runs.