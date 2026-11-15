"""The onboard AI agent as a chatbot: small talk, follow-ups, symptoms, the astronaut's own numbers.

* Never a diagnosis. For a symptom it gives the causes commonly reported in spaceflight (each with its source),
  checks the astronaut's live numbers, says what to try, and offers "Send to flight surgeon".
* Danger signs (general emergency warning signs, a convention, not a NASA list) skip the chat: the reply says
  "contact the flight surgeon now" and the hub raises an urgent CHECK_VITALS alert that goes to NASA at once.
* Order: a local Ollama model (MEDVITAL_OLLAMA_MODEL, e.g. gemma4) with the conversation, then Workers AI
  (small, fast model) through the Cloudflare Worker, then the built-in replies below. A model's reply is used
  only when every number it states about the astronaut appears in the astronaut's data.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from medvital.hub import ai

# ---------------------------------------------------------------------------- symptoms (common causes in flight)
# Each entry: words that name it, the causes commonly reported in spaceflight, what to try, the source.
SYMPTOMS: dict[str, dict[str, Any]] = {
    "headache": {
        "words": ("headache", "head hurts", "head ache", "my head", "migraine", "head is pounding"),
        "causes": "carbon dioxide building up in the cabin air, the shift of body fluid towards the head in "
        "weightlessness, space motion sickness in the first days, too little sleep, or not drinking enough",
        "try": "drink water, move to a well-ventilated spot near a fan, rest your eyes, and check the cabin CO₂ "
        "reading",
        "source": "Law J et al. 2014, J Occup Environ Med (CO₂ and headaches on the ISS); Vein AA et al. 2009, "
        "Cephalalgia (space headache)",
        "checks": ("hr", "spo2", "temp", "sleep"),
    },
    "nausea": {
        "words": ("nausea", "nauseous", "sick to my stomach", "want to vomit", "vomit", "throw up", "queasy"),
        "causes": "space motion sickness: the balance organs and the eyes disagree in weightlessness. It is most "
        "common in the first two or three days of flight or after landing",
        "try": "keep your head still, keep a fixed visual reference (the floor and ceiling of the module), eat "
        "small amounts and sip water",
        "source": "Heer M & Paloski WH 2006, Autonomic Neuroscience (space motion sickness)",
        "checks": ("hr", "temp"),
    },
    "back pain": {
        "words": ("back pain", "back hurts", "my back", "lower back", "backache"),
        "causes": "the spine lengthens without gravity and the muscles around it are stretched; most crew "
        "members feel it in the first days",
        "try": "curl up in a fetal position for a few minutes and use the stretching routine",
        "source": "Kerstman EL et al. 2012, Aviat Space Environ Med (space adaptation back pain)",
        "checks": ("hr",),
    },
    "stuffy nose": {
        "words": ("stuffy", "congested", "congestion", "blocked nose", "puffy face"),
        "causes": "body fluid moving towards the head in weightlessness, which swells the face and nose",
        "try": "this usually settles; exercise and drinking water help",
        "source": "NASA Human Research Program, Risk of Spaceflight Associated Neuro-ocular Syndrome (fluid shift)",
        "checks": ("spo2", "temp"),
    },
    "sleep": {
        "words": ("can't sleep", "cannot sleep", "insomnia", "trouble sleeping", "tired", "exhausted", "fatigue"),
        "causes": "short sleep is common in flight: noise, light, a shifting work schedule and the 90-minute "
        "day-night cycle in orbit",
        "try": "keep the sleep station dark and quiet, avoid screens for the last half hour, and keep your sleep "
        "period at the same time",
        "source": "Barger LK et al. 2014, Lancet Neurology (sleep deficiency in astronauts)",
        "checks": ("sleep", "hr"),
    },
    "vision": {
        "words": ("blurry", "blurred", "vision", "can't focus", "see clearly"),
        "causes": "changes in near vision are reported in long flights and are followed closely (spaceflight "
        "associated neuro-ocular syndrome)",
        "try": "note when it started; the flight surgeon will want an eye check today",
        "source": "Mader TH et al. 2011, Ophthalmology (optic disc oedema and globe flattening after long flight)",
        "checks": ("hr",),
        "send_now": True,
    },
    "dizzy": {
        "words": ("dizzy", "lightheaded", "light-headed", "spinning", "vertigo"),
        "causes": "the balance system adapting to weightlessness, or after landing to gravity again; low fluid "
        "intake makes it worse",
        "try": "sit or hold on, keep your head still, and drink water",
        "source": "Heer M & Paloski WH 2006, Autonomic Neuroscience",
        "checks": ("hr", "spo2"),
    },
}

# General emergency warning signs (a convention, not a NASA list): never handled by chat alone.
DANGER = (
    ("chest pain", ("chest pain", "chest hurts", "pressure in my chest", "chest tight")),
    ("trouble breathing", ("can't breathe", "cannot breathe", "short of breath", "hard to breathe", "choking")),
    ("a sudden, severe headache", ("worst headache", "sudden severe headache", "thunderclap")),
    ("sudden loss of vision", ("can't see", "cannot see", "lost my vision", "went blind", "vision loss")),
    ("confusion", ("confused", "don't know where i am", "can't think")),
    ("fainting", ("fainted", "passed out", "blacked out")),
    ("weakness or numbness on one side", ("numb on one side", "can't move my arm", "face drooping", "slurred")),
    ("heavy bleeding", ("bleeding a lot", "won't stop bleeding", "heavy bleeding")),
)

GREETING = re.compile(r"^\s*(hi|hello|hey|good (morning|afternoon|evening)|yo|hola|bonjour|sup)\b", re.I)
THANKS = re.compile(r"\b(thanks|thank you|thx|merci|cheers)\b", re.I)
BYE = re.compile(r"^\s*(bye|goodbye|good night|see you|later)\b", re.I)
HOW_ARE_YOU = re.compile(r"\bhow are you\b|\bwho are you\b|\bwhat can you do\b", re.I)


def find_symptoms(text: str) -> list[str]:
    t = text.lower()
    return [name for name, s in SYMPTOMS.items() if any(w in t for w in s["words"])]


def find_danger(text: str) -> str | None:
    t = text.lower()
    return next((label for label, words in DANGER if any(w in t for w in words)), None)


# ---------------------------------------------------------------------------- the astronaut's numbers
def facts(view: dict[str, Any]) -> dict[str, Any]:
    """A short, exact summary of the astronaut's data: what a model may quote."""
    last, prof, rad = view.get("latest") or {}, view["profile"], view["radiation"]
    today = view.get("today") or {}
    real = next((a for a in view.get("alerts") or [] if a["code"] not in ("INFO",)), None)
    return {
        "name": prof.get("name", "").split(" ")[0],
        "state": last.get("state"),
        "heartRate": round(last["heart_rate"]) if last else None,
        "restingBaseline": round(prof["resting_hr"]),
        "spo2": round(last["spo2"]) if last else None,
        "spo2Baseline": round(prof["spo2"]),
        "temperature": round(last["skin_temp"], 1) if last and last.get("skin_temp") else None,
        "breathing": round(last["resp_rate"]) if last and last.get("resp_rate") else None,
        "sleptHours": today.get("sleepHours"),
        "sleepTargetHours": prof.get("sleep_target_h"),
        "exerciseMinutes": today.get("exerciseMinutes"),
        "doseRate": round(last["dose_rate"], 1) if last else None,
        "careerDosePctOfLimit": round(rad["careerPct"], 1),
        "solarEventNow": (view["spaceWeather"]["active"] or {}).get("summary"),
        "lastAlert": f"{real['code']}: {real['message']}" if real else None,
        "lastSummary": (view.get("lastSummary") or {}).get("text"),
    }


def numbers_line(f: dict[str, Any], checks: tuple[str, ...]) -> str:
    """'Your heart rate is 64 bpm (your usual 58), blood oxygen 98% ...' for the checks a symptom needs."""
    bits = []
    if "hr" in checks and f["heartRate"] is not None:
        bits.append(f"heart rate {f['heartRate']} bpm (pre-flight resting {f['restingBaseline']})")
    if "spo2" in checks and f["spo2"] is not None:
        bits.append(f"blood oxygen {f['spo2']}% (pre-flight {f['spo2Baseline']}%)")
    if "temp" in checks and f["temperature"] is not None:
        bits.append(f"temperature {f['temperature']} °C")
    if "sleep" in checks and f["sleptHours"] is not None:
        bits.append(f"{f['sleptHours']} h of sleep today (target {f['sleepTargetHours']} h)")
    return ", ".join(bits)


def within_usual(f: dict[str, Any]) -> bool:
    """A plain check against the astronaut's own pre-flight values (demo allowance, not a clinical limit)."""
    ok_hr = f["heartRate"] is None or f["heartRate"] <= f["restingBaseline"] + 25 or f["state"] == "exercise"
    ok_o2 = f["spo2"] is None or f["spo2"] >= f["spo2Baseline"] - 3
    ok_t = f["temperature"] is None or f["temperature"] < 37.8
    return ok_hr and ok_o2 and ok_t


# ---------------------------------------------------------------------------- built-in replies
def builtin(message: str, view: dict[str, Any], f: dict[str, Any]) -> dict[str, Any]:
    name = f["name"] or "there"
    danger = find_danger(message)
    if danger:
        return {
            "answer": f"You mentioned {danger}. That is a warning sign: contact the flight surgeon now. I have "
            f"alerted NASA. Right now your {numbers_line(f, ('hr', 'spo2', 'temp'))}. Stay where a crewmate can "
            "see you.",
            "danger": danger,
            "symptoms": [danger],
        }
    syms = find_symptoms(message)
    if syms:
        parts = []
        for s in syms:
            sy = SYMPTOMS[s]
            parts.append(
                f"{s.capitalize()} in space is commonly linked to {sy['causes']}. It may help to {sy['try']}. "
                f"(Source: {sy['source']}.)"
            )
        checks = tuple(dict.fromkeys(c for s in syms for c in SYMPTOMS[s]["checks"]))
        line = numbers_line(f, checks)
        verdict = (
            f"Good news from your wearable: {line}, all close to your usual."
            if within_usual(f)
            else f"Your wearable shows {line}, which is off your usual: please send this to the flight surgeon."
        )
        sends = any(SYMPTOMS[s].get("send_now") for s in syms)
        return {
            "answer": " ".join(parts) + f" {verdict} This is not a diagnosis. "
            + (
                "Please send this chat to the flight surgeon today."
                if sends
                else "If it gets worse or does not go away, send this chat to the flight surgeon."
            ),
            "symptoms": syms,
        }
    if GREETING.search(message):
        mood = "Everything looks steady on my side." if within_usual(f) else "A few of your numbers need a look."
        return {"answer": f"Hello {name}! {mood} How are you feeling today?"}
    if HOW_ARE_YOU.search(message):
        return {
            "answer": "I am the spacecraft's onboard health assistant. I read your wearable and test results, "
            "answer questions about them, and help when something does not feel right. I do not diagnose; I "
            "point you to the flight surgeon when you need one."
        }
    if THANKS.search(message):
        return {"answer": f"You're welcome, {name}. I'm here if anything changes."}
    if BYE.search(message):
        return {"answer": f"Take care, {name}. I'll keep watching your readings."}
    return {"answer": ai._rule_answer(message.lower(), view)}


# ---------------------------------------------------------------------------- the model
SYSTEM = (
    "You are the onboard health assistant on a crewed Mars mission, chatting with an astronaut. Be warm, brief "
    "(at most 5 sentences) and conversational: answer greetings and small talk naturally. Never diagnose and "
    "never name a disease the astronaut 'has'. For a symptom: say what commonly causes it in spaceflight (use "
    "the SYMPTOM NOTES), compare with their numbers from DATA, suggest what to try, and say they can press "
    "'Send to flight surgeon'. Only quote numbers that appear in DATA, exactly as written. If a danger sign is "
    "mentioned, tell them to contact the flight surgeon now."
)


def _ollama_chat(messages: list[dict[str, str]]) -> str | None:
    model = ai.agent_model()
    if not model:
        return None
    url = os.environ.get("MEDVITAL_OLLAMA_URL", "http://localhost:11434").rstrip("/") + "/api/chat"
    try:
        out = ai._post(
            url,
            {"model": model, "stream": False, "keep_alive": "30m", "messages": messages,
             "options": {"num_predict": 260, "temperature": 0.4}},
            {},
            float(os.environ.get("MEDVITAL_OLLAMA_TIMEOUT", "60")),
        )
        text = (out.get("message") or {}).get("content")
        return text.strip() if isinstance(text, str) and text.strip() else None
    except Exception:  # noqa: BLE001 - not running, still loading, too slow: the next option answers
        return None


def numbers_ok(reply: str, allowed: str) -> bool:
    """Every number the model states must appear in the data or in the built-in reply."""
    nums = re.findall(r"\d+(?:\.\d+)?", reply)
    return all(n in allowed for n in nums)


def reply(message: str, history: list[dict[str, str]], view: dict[str, Any]) -> dict[str, Any]:
    f = facts(view)
    base = builtin(message, view, f)
    if base.get("danger"):  # danger signs never wait for a model
        return {**base, "source": "onboard agent · safety rule"}
    notes = "; ".join(f"{s}: {SYMPTOMS[s]['causes']} (source: {SYMPTOMS[s]['source']})" for s in base.get("symptoms", []))
    data = json.dumps({k: v for k, v in f.items() if v is not None}, ensure_ascii=False)
    allowed = data + " " + base["answer"]
    turns = [m for m in history[-8:] if m.get("role") in ("user", "assistant") and m.get("content")]
    context = f"DATA: {data}\nSYMPTOM NOTES: {notes or 'none'}\nA safe reply you can build on: {base['answer']}"
    msgs = [{"role": "system", "content": SYSTEM + "\n" + context}, *turns, {"role": "user", "content": message}]
    text = _ollama_chat(msgs)
    if text and numbers_ok(text, allowed):
        return {**base, "answer": text, "source": f"onboard agent · Ollama {ai.agent_model()}"}
    convo = "\n".join(f"{m['role']}: {m['content']}" for m in turns)
    text = ai.workers_ai(f"{SYSTEM}\n{context}\nConversation so far:\n{convo}\nastronaut: {message}\nassistant:")
    if text and numbers_ok(text, allowed):
        return {**base, "answer": text, "source": "onboard agent · Workers AI (numbers checked)"}
    return {**base, "source": "onboard agent · built-in"}
