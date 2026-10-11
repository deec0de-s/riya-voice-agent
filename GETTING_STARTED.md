# Getting started (beginner steps, Windows)

You need: Python (python.org, tick "Add Python to PATH") and VS Code.

## 1. Open the right folder
Extract this zip. In VS Code: **File > Open Folder** and pick the folder that directly contains
`app.py`, `agent.py` and `requirements.txt`. Then **Terminal > New Terminal**.
Type `dir`. If you do not see `app.py`, you are in the wrong folder (`cd` into it).

## 2. Install once
```
pip install -r requirements.txt
```

## 3. Get a free key and save it (once)
Create a key at console.groq.com > API Keys. Then (PowerShell), using your own key and a model
your account can use (try `openai/gpt-oss-120b`):
```
setx LLM_API_KEY "your-key"
setx LLM_MODEL "openai/gpt-oss-120b"
```
Close the terminal and open a new one. Never share the key or put it in a file you upload.

## 4. The three days
| Day | What | Command |
|-----|------|---------|
| 1 | Text agent, tools, guardrails | `python agent.py` |
| 1 | 8 scripted test calls | `python agent.py --scenarios` |
| 2 | Voice web app (mic + spoken replies, EN/HI/KN) | `python app.py` then open the link it prints |
| 3 | 32 test calls, then analysis report | `python agent.py --scenarios --repeat 4` then `python analysis.py` |

Day 3 notes:
- The free tier has rate limits. If a run is skipped, it waits and continues. You can also run
  `--repeat 2` a couple of times. Each run adds to `call_log.csv`.
- `python analysis.py` writes `report.html`. Open it in Chrome and screenshot it for your README.
- Also make 3 to 5 real calls in `python app.py` in Hindi and Kannada. Their logs go to the
  same `call_log.csv` (as scenario `web-hi`, `web-kn`, `web-en`), so they show up in the report.

## 5. Put it on the internet (free live link)
Hugging Face > New Space > Gradio > Public. Upload every file (not `call_log.csv`). In
**Settings > Variables and secrets** add secrets `LLM_API_KEY` and `LLM_MODEL`. Wait for the build.
Put the link in your README and email.

## 6. Finish
1. Read the flagged calls in `report.html`, fix the prompt in `prompts.py`, run again.
2. Fill the "Test findings" section of `README.md` with what broke and what you changed
   (use real numbers: booking rate before and after).
3. Record the demo using `VIDEO_SCRIPT.md`.
4. Upload to GitHub (`.gitignore` already keeps your key and logs out), then send `EMAIL.md`.
