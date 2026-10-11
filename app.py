"""Web version of Riya with voice. Speak or type; Riya answers in text AND voice.

Local:   python app.py     then open the link it prints (http://127.0.0.1:7860)
Needs env vars: LLM_API_KEY (Groq key; used for chat and speech-to-text)
                LLM_MODEL (optional)
"""
import asyncio
import os
import re
import tempfile

import edge_tts
import gradio as gr
from openai import OpenAI

import agent

if not os.environ.get("LLM_API_KEY"):
    raise SystemExit("Set LLM_API_KEY first (on Hugging Face: Settings > Secrets).")

client = OpenAI(api_key=os.environ["LLM_API_KEY"], base_url=agent.BASE_URL)
STT_MODEL = os.environ.get("STT_MODEL", "whisper-large-v3-turbo")

LANGS = {
    "English": {"code": "en", "voice": "en-IN-NeerjaNeural", "key": "English"},
    "Hindi (हिन्दी)": {"code": "hi", "voice": "hi-IN-SwaraNeural", "key": "Hindi"},
    "Kannada (ಕನ್ನಡ)": {"code": "kn", "voice": "kn-IN-SapnaNeural", "key": "Kannada"},
}
MAX_TURNS = 30  # protects your free quota from runaway sessions


def transcribe(path, code):
    with open(path, "rb") as f:
        r = client.audio.transcriptions.create(model=STT_MODEL, file=f, language=code)
    return (r.text or "").strip()


def speak(text, voice):
    """Turn text into an mp3 file; returns its path (or None if TTS fails)."""
    clean = re.sub(r"[*_`#>]", "", text).strip()
    if not clean:
        return None
    out = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False).name
    try:
        asyncio.run(edge_tts.Communicate(clean, voice).save(out))
        return out
    except Exception as e:  # voice is a bonus; text still works
        print("TTS failed:", e)
        return None


def start_call(language):
    cfg = LANGS[language]
    s = agent.Session(client, language=cfg["key"], scenario=f"web-{cfg['code']}")
    greeting = s.start()
    history = [{"role": "assistant", "content": greeting}]
    return s, history, speak(greeting, cfg["voice"]), gr.update(value=None), ""


def end_call(session, history):
    if session is not None:
        session.close()
    history = (history or []) + [{"role": "assistant", "content": "[Call ended and logged.]"}]
    return None, history


def _turn(user_text, session, history, language):
    cfg = LANGS[language]
    if session is None or session.closed:
        return session, history, None
    if len(session.transcript) // 2 > MAX_TURNS:
        history = history + [{"role": "assistant", "content": "[Demo limit reached. Start a new call.]"}]
        return session, history, None
    history = history + [{"role": "user", "content": user_text}]
    try:
        reply = session.say(user_text)
    except Exception as e:
        reply = f"[Error talking to the model: {e}]"
    history = history + [{"role": "assistant", "content": reply}]
    return session, history, speak(reply, cfg["voice"])


def on_text(text, session, history, language):
    if not text or not text.strip():
        return session, history, None, ""
    session, history, audio = _turn(text.strip(), session, history, language)
    return session, history, audio, ""


def on_mic(path, session, history, language):
    if not path:
        return session, history, None, None
    try:
        text = transcribe(path, LANGS[language]["code"])
    except Exception as e:
        history = history + [{"role": "assistant", "content": f"[Could not transcribe audio: {e}]"}]
        return session, history, None, None
    if not text:
        history = history + [{"role": "assistant", "content": "[Could not hear anything. Try again.]"}]
        return session, history, None, None
    session, history, audio = _turn(text, session, history, language)
    return session, history, audio, None


with gr.Blocks(title="Riya - Real Estate Voice Assistant") as demo:
    gr.Markdown(
        "## Riya: real estate lead-qualifying voice assistant\n"
        "Demo with **fictional** Bengaluru projects. Pick a language, press **Start call**, "
        "then speak into the mic or type. Say you want a site visit to see booking work."
    )
    session = gr.State(None)
    with gr.Row():
        language = gr.Dropdown(list(LANGS), value="English", label="Caller language")
        start_btn = gr.Button("Start call", variant="primary")
        end_btn = gr.Button("End call")
    chat = gr.Chatbot(type="messages", height=380, label="Call transcript")
    reply_audio = gr.Audio(label="Riya's voice", autoplay=True, interactive=False, type="filepath")
    mic = gr.Audio(sources=["microphone"], type="filepath", label="Speak (press record, then stop)")
    box = gr.Textbox(label="Or type here and press Enter", placeholder="Hi, I'm looking for a 2 BHK...")

    start_btn.click(start_call, [language], [session, chat, reply_audio, mic, box])
    end_btn.click(end_call, [session, chat], [session, chat])
    mic.stop_recording(on_mic, [mic, session, chat, language], [session, chat, reply_audio, mic])
    box.submit(on_text, [box, session, chat, language], [session, chat, reply_audio, box])

if __name__ == "__main__":
    demo.launch()
