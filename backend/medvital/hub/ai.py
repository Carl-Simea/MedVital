"""The two AIs from the team plan, with safe fallbacks so the demo never depends on them.

* Workers AI (Cloudflare): words alerts and daily summaries in plain language. Used through the
  MedVital Worker when ``MEDVITAL_CLOUDFLARE_URL`` and ``MEDVITAL_CLOUDFLARE_KEY`` are set (preferred:
  no API token on the laptop), or the REST API with ``CLOUDFLARE_ACCOUNT_ID`` and
  ``CLOUDFLARE_API_TOKEN``; otherwise the template text stays.
* Onboard agent (local, second AI): answers the astronaut's questions, double-checks the daily
  summaries. Uses a local Ollama model when ``MEDVITAL_OLLAMA_MODEL`` is set (e.g. ``gemma3``);
  otherwise it answers with rules from the astronaut's own data.

Standard library only.
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from typing import Any

WORKERS_AI_MODEL = os.environ.get("MEDVITAL_WORKERS_AI_MODEL", "@cf/meta/llama-3.1-8b-instruct")
SYSTEM = (
    "You are MedVital, the health system on a crewed spacecraft. Write for an astronaut: short, calm, "
    "plain language, no diagnosis. Keep every number exactly as given."
)


def _post(url: str, body: dict[str, Any], headers: dict[str, str], timeout: float) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        method="POST",
        headers={"Content-Type": "application/json", **headers},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (fixed hosts)
        return json.loads(resp.read().decode())


def _worker() -> tuple[str, str] | None:
    """The MedVital Worker (cloudflare/) runs Workers AI through its AI binding: no API token needed here."""
    url = os.environ.get("MEDVITAL_CLOUDFLARE_URL", "").rstrip("/")
    key = os.environ.get("MEDVITAL_CLOUDFLARE_KEY", "")
    return (url, key) if url and key else None


def workers_ai_enabled() -> bool:
    return bool(
        _worker() or (os.environ.get("CLOUDFLARE_ACCOUNT_ID") and os.environ.get("CLOUDFLARE_API_TOKEN"))
    )


def workers_ai(prompt: str, timeout: float = 8.0) -> str | None:
    if not workers_ai_enabled():
        return None
    worker = _worker()
    if worker:
        try:
            out = _post(worker[0] + "/ai", {"prompt": prompt}, {"x-medvital-key": worker[1]}, timeout)
            text = out.get("text")
            return text.strip() if isinstance(text, str) and text.strip() else None
        except Exception:  # noqa: BLE001 - e.g. no Workers AI in `wrangler dev --local`: keep the template
            return None
    url = (
        f"https://api.cloudflare.com/client/v4/accounts/{os.environ['CLOUDFLARE_ACCOUNT_ID']}"
        f"/ai/run/{WORKERS_AI_MODEL}"
    )
    try:
        out = _post(
            url,
            {"messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]},
            {"Authorization": f"Bearer {os.environ['CLOUDFLARE_API_TOKEN']}"},
            timeout,
        )
        text = (out.get("result") or {}).get("response")
        return text.strip() if isinstance(text, str) and text.strip() else None
    except Exception:  # noqa: BLE001 - AI is optional; any failure falls back to the template
        return None


def agent_model() -> str | None:
    return os.environ.get("MEDVITAL_OLLAMA_MODEL") or None


def ollama(prompt: str, timeout: float = 30.0) -> str | None:
    model = agent_model()
    if not model:
        return None
    url = os.environ.get("MEDVITAL_OLLAMA_URL", "http://localhost:11434").rstrip("/") + "/api/chat"
    try:
        out = _post(
            url,
            {
                "model": model,
                "stream": False,
                "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
            },
            {},
            timeout,
        )
        text = (out.get("message") or {}).get("content")
        return text.strip() if isinstance(text, str) and text.strip() else None
    except Exception:  # noqa: BLE001
        return None


def numbers_survive(original: str, rewritten: str) -> bool:
    """The onboard agent's double-check: every number in the rule text must appear in the AI text."""
    nums = set(re.findall(r"\d+(?:\.\d+)?", original))
    return all(n in rewritten for n in nums)


def reword(template: str, kind: str) -> tuple[str, str, str]:
    """(text, source, check note). Falls back to the template whenever AI is off or changes a number."""
    text = workers_ai(f"Rewrite this {kind} for the astronaut in at most 3 sentences:\n{template}")
    if text is None:
        return template, "template", "Rule text (Workers AI not configured)."
    if not numbers_survive(template, text):
        return template, "template", "Workers AI wording rejected by the onboard agent: a number changed."
    return text, "Workers AI", "Checked by the onboard agent: all numbers match the rules."


# ---------------------------------------------------------------------------- onboard agent
def answer(question: str, ctx: dict[str, Any]) -> tuple[str, str]:
    """Answer an astronaut's question from their own data. Returns (answer, source)."""
    facts = json.dumps(ctx, default=str)[:6000]
    llm = ollama(
        f"Data from the spacecraft hub (JSON): {facts}\n\nAstronaut's question: {question}\n"
        "Answer in at most 4 sentences using only this data."
    )
    if llm:
        return llm, f"onboard agent · {agent_model()}"
    return _rule_answer(question.lower(), ctx), "onboard agent · rules"


def _rule_answer(q: str, c: dict[str, Any]) -> str:
    last, prof = c.get("latest") or {}, c["profile"]
    rad, wx = c["radiation"], c["spaceWeather"]
    alert = c.get("activeAlert")
    has = lambda *words: any(w in q for w in words)  # noqa: E731
    if not last:
        return "I have no readings from your wearable yet. Make sure it is on and sending."
    if has("why", "buzz", "vibrat", "alert", "warning"):
        if alert:
            return f"Your last alert was {alert['code']}: {alert['message']}"
        return "No active alert. Your readings are within your personal ranges."
    if has("outside", "spacewalk", "eva", "go out"):
        if wx["active"]:
            return (
                f"Not now. A solar event is active ({wx['active']['summary'].rstrip('.')}). "
                "Stay inside the shielded area."
            )
        return (
            f"Space weather is quiet. Your career dose is {rad['careerPct']:.1f}% of the NASA limit, "
            f"and each spacewalk has a {rad['evaBudgetMsv']} mSv budget. "
            "Check with the crew before going out."
        )
    if has("radiation", "dose", "sievert", "msv", "solar", "sun", "flare"):
        msg = (
            f"Dose rate now {last['dose_rate']:.1f} µSv/h. Mission dose {last['total_dose']:.2f} mSv; career "
            f"{rad['careerMsv']:.1f} mSv = {rad['careerPct']:.1f}% of NASA's 600 mSv limit."
        )
        if wx["active"]:
            msg += f" A solar event is active: {wx['active']['summary']}"
        return msg
    if has("heart", "pulse", "bpm"):
        return (
            f"Heart rate {last['heart_rate']:.0f} bpm while {last['state']}. "
            "Your pre-flight resting baseline "
            f"is {prof['resting_hr']:.0f} bpm."
        )
    if has("oxygen", "spo2", "breath"):
        return f"Blood oxygen {last['spo2']:.0f}% (your baseline {prof['spo2']:.0f}%)."
    if has("sleep", "tired", "rest"):
        d = c.get("today") or {}
        return (
            f"Today you slept {d.get('sleepHours', 0)} h of your {prof['sleep_target_h']} h target. "
            "A dark, cool sleep station and a fixed schedule help."
        )
    if has("exercise", "workout", "bone", "muscle", "gym"):
        d = c.get("today") or {}
        return (
            f"Exercise today: {d.get('exerciseMinutes', 0)} of {d.get('exerciseTargetMinutes', 120)} min. "
            "Resistance exercise protects hip and spine bone; cardio keeps your heart fit."
        )
    if has("summary", "report", "today", "how am i", "status"):
        s = c.get("lastSummary")
        return s["text"] if s else "No daily summary yet. One is written at the end of each mission day."
    return (
        "I can answer about your heart rate, blood oxygen, radiation, space weather, sleep, exercise, "
        "alerts and your daily summary."
    )
