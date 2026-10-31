"""Optional LLM layer. Rules decide the verdict; the LLM only writes plain-language text from the given facts.

Set OPENROUTER_API_KEY (free models, default) or ANTHROPIC_API_KEY in the environment or in app/.env (one line: NAME=value).
Without a key, or if the call fails, every function here returns None and the app falls back to the rule-based text.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
MODEL = os.getenv("LLM_MODEL", "claude-sonnet-5-5")          # used with ANTHROPIC_API_KEY
FREE_MODELS = ["google/gemma-4-31b-it:free", "poolside/laguna-s-2.1:free", "google/gemma-4-26b-a4b-it:free", "poolside/laguna-xs-2.1:free"]   # tried in order with OPENROUTER_API_KEY
last_error: str | None = None

SYSTEM_EXPLAIN = (
    "You are a retail analytics assistant. Explain in 3 to 4 plain sentences why a Walmart sales exception happened, "
    "for a store manager. Use ONLY the facts in the JSON. Do not add any number, store, date or quote that is not in the JSON. "
    "At most 90 words. Use quotation marks only for ONE exact quote; copy it exactly and completely from the passages (or paraphrase without quotation marks) and name the source. "
    "Say clearly whether it looks like a real problem or an explained pattern, matching the given verdict. No headings, no bullet points.")
SYSTEM_CHAT = (
    "You are a retail analytics assistant answering a follow-up question about one Walmart sales exception. Use ONLY the facts in the JSON "
    "(including 'lookup' results if present). Do not add numbers or quotes that are not in the JSON. If the facts do not answer the "
    "question, say what is missing. Keep it to 2 to 4 sentences.")


def _load_env():
    for p in (APP / ".env", APP.parent / ".env"):
        if p.exists():
            for line in p.read_text().splitlines():
                m = re.match(r"\s*([A-Z_]+)\s*=\s*(.*?)\s*$", line)
                if m and m.group(1) not in os.environ:
                    os.environ[m.group(1)] = m.group(2).strip("'\"")


_load_env()


def provider() -> str | None:
    if os.getenv("OPENROUTER_API_KEY"):
        return "openrouter"
    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic"
    return None


def available() -> bool:
    return provider() is not None


def model_label() -> str:
    return {"openrouter": f"{FREE_MODELS[0]} via OpenRouter", "anthropic": MODEL}.get(provider(), "none")


def dumps(obj) -> str:
    return json.dumps(obj, default=lambda o: float(o) if hasattr(o, "__float__") else str(o), ensure_ascii=False)


def _openrouter(system: str, user: str, max_tokens: int, models: list[str] | None = None) -> dict | None:
    """OpenAI-compatible chat call; tries each free model in turn if one is rate-limited or unavailable."""
    global last_error
    t = time.time()
    for model in (models or model_chain()):
        body = json.dumps({"model": model, "max_tokens": max_tokens, "temperature": 0.2,
                           "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}).encode()
        req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", body,
                                     {"Authorization": "Bearer " + os.environ["OPENROUTER_API_KEY"], "Content-Type": "application/json",
                                      "X-Title": "Walmart exception agents"})
        try:
            r = json.load(urllib.request.urlopen(req, timeout=90))
            text = (r["choices"][0]["message"].get("content") or "").strip()
            if not text or r["choices"][0].get("finish_reason") == "length":
                last_error = f"{model}: {'empty' if not text else 'cut off'} answer"
                continue
            u = r.get("usage", {})
            last_error = None
            return dict(text=text, model=r.get("model", model), input_tokens=u.get("prompt_tokens", 0),
                        output_tokens=u.get("completion_tokens", 0), ms=round((time.time() - t) * 1000))
        except urllib.error.HTTPError as e:
            last_error = f"{model}: HTTP {e.code}" + (" (key rejected: use a normal API key, not a management key)" if e.code == 401 else "")
            if e.code == 401:
                return None
        except Exception as e:
            last_error = f"{model}: {type(e).__name__}"
    return None


def model_chain() -> list[str]:
    if provider() == "anthropic":
        return [MODEL]
    return [os.environ["LLM_MODEL"]] if os.getenv("LLM_MODEL") else FREE_MODELS


def complete(system: str, user: str, max_tokens: int = 400, client=None, models: list[str] | None = None) -> dict | None:
    """One LLM call. Returns {text, model, input_tokens, output_tokens, ms} or None if no key / the call fails."""
    global last_error
    if client is None:
        if provider() == "openrouter":
            return _openrouter(system, user, max_tokens, models)
        if provider() != "anthropic":
            return None
        import anthropic
        client = anthropic.Anthropic()
    t = time.time()
    try:
        r = client.messages.create(model=MODEL, max_tokens=max_tokens, system=system, messages=[{"role": "user", "content": user}])
    except Exception as e:  # network, auth, rate limit: fall back to rules
        last_error = f"{type(e).__name__}: {str(e)[:160]}"
        return None
    last_error = None
    return dict(text="".join(b.text for b in r.content if getattr(b, "type", "") == "text").strip(), model=MODEL,
                input_tokens=r.usage.input_tokens, output_tokens=r.usage.output_tokens, ms=round((time.time() - t) * 1000))


_NUM = re.compile(r"\d+(?:[.,]\d+)*")


def _nums(s: str) -> set[str]:
    return {n.replace(",", "").rstrip(".") for n in _NUM.findall(s)}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("’", "'").replace("“", '"').replace("”", '"')).strip().lower()


def grounded(text: str, facts: dict) -> tuple[bool, list[str]]:
    """Every number must appear in the facts and every quoted passage must be a verbatim quote from them."""
    blob = dumps(facts)
    allowed = _nums(blob)
    problems = [f"number not in facts: {n}" for n in sorted(_nums(text) - allowed)]
    quotes = [_norm(h["quote"]) for h in facts.get("passages", [])]
    for q in re.findall(r"[\u201c\"]([^\u201d\"]{20,})[\u201d\"]", text):
        for frag in re.split(r"\u2026|\.\.\.", q):                       # a quote may be trimmed with "..."
            f = _norm(frag).strip(" .,;:!?\u2026'")
            if len(f) >= 12 and not any(f in x for x in quotes):
                problems.append(f"quote not verbatim: {f[:50]}")
                break
    verdict = facts.get("verdict")
    if verdict and not consistent(text, verdict):
        problems.append("wording contradicts the verdict")
    return (not problems), problems


def consistent(text: str, verdict: str) -> bool:
    """Simple wording check: the plain-language text must not say the opposite of the rule-based verdict."""
    low = text.lower()
    if verdict.startswith("Likely explained"):
        return not re.search(r"needs review|local to (the )?store|specific to (the )?store|store-specific problem|real problem with", low)
    return not re.search(r"not a real problem|no action (is )?needed|likely explained|just timing|simply (the )?(christmas|holiday|easter)", low)


def complete_grounded(system: str, user: str, facts: dict, max_tokens: int = 700, rounds: int = 2, client=None) -> dict | None:
    """Ask for text and keep it only if every number and quote is in the facts. Tries each model in turn (twice around if the
    free models are rate-limited). Returns {text, model, tokens, ms, attempts, grounded, problems}; text is None when every
    attempt was rejected; None when no model answered at all."""
    attempts, problems, last = 0, [], None
    for rnd in range(rounds):
        for m in model_chain():
            out = complete(system, user, max_tokens, client=client, models=[m])
            if not out:
                continue
            attempts += 1
            ok, pr = grounded(out["text"], facts)
            last = dict(out, attempts=attempts, grounded=ok, problems=pr)
            if ok:
                return last
            problems += pr
            if client is not None:
                break
        if last or client is not None:
            break
        time.sleep(3)               # every free model was busy: wait a moment and go around once more
    return dict(last, text=None, problems=problems[:3]) if last else None
