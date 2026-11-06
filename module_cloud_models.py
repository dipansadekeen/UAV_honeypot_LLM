# module_cloud_models.py

import os, time, requests
from pathlib import Path

from google import genai
from google.genai import types

from module_helper_functions import extract_json


GEMINI_MODEL_NAME = "gemini-2.5-flash"


def _load_secret(env_var, key_file):
    """Return a credential from the environment, else from a local (git-ignored) file."""
    value = os.environ.get(env_var, "").strip()
    if value:
        return value
    key_path = Path(__file__).resolve().parent / key_file
    try:
        return key_path.read_text().strip()
    except OSError:
        raise RuntimeError(f"Set {env_var} or create {key_file}")


_gemini_client = None


def _get_gemini_client():
    """Create the Gemini client lazily so importing this module needs no credentials."""
    global _gemini_client
    if _gemini_client is None:
        _gemini_client = genai.Client(api_key=_load_secret("GEMINI_API_KEY", "gemini_api.txt"))
    return _gemini_client


def call_gemini_cloud(
    system_text: str,
    user_text: str,
    tag: str = "general",
    model_name: str = GEMINI_MODEL_NAME,
    log_fn=None,
    return_meta: bool = False,
):
    t0 = time.monotonic()

    try:
        response = _get_gemini_client().models.generate_content(
            model=model_name,
            contents=user_text,
            config=types.GenerateContentConfig(
                system_instruction=system_text,
                temperature=0,
                top_p=0.9,
                response_mime_type="application/json",
            ),
        )

        raw = response.text.strip() if response.text else ""
        dt_ms = (time.monotonic() - t0) * 1000.0

        parsed = extract_json(raw)

        if log_fn is not None:
            log_fn(tag, system_text, user_text, raw, parsed, dt_ms)

        if return_meta:
            return {
                "raw": raw,
                "parsed": parsed,
                "latency_ms": dt_ms,
                "model_name": model_name,
                "tag": tag,
            }

        return raw

    except Exception as e:
        dt_ms = (time.monotonic() - t0) * 1000.0

        print(f"[LLM GEMINI FAIL {tag}] {e}", flush=True)

        if return_meta:
            return {
                "raw": "",
                "parsed": None,
                "latency_ms": dt_ms,
                "model_name": model_name,
                "tag": tag,
                "error": str(e),
            }

        return ""



def call_ollama_cloud(self, system_text: str, user_text: str, tag: str = "general") -> str:
    t0 = time.monotonic()
    # Evaluated cloud models: nemotron-3-super:cloud, nemotron-3-nano:30b-cloud,
    # gpt-oss:120b-cloud, gpt-oss:20b-cloud, gemma4:31b-cloud
    model_name = os.environ.get("OLLAMA_CLOUD_MODEL", "nemotron-3-super:cloud")

    try:
        api_key = _load_secret("OLLAMA_API_KEY", "api_key.txt")

        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_text},
                {"role": "user", "content": user_text}
            ],
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0,
                "top_p": 0.9
            }
        }

        r = requests.post(
            "https://ollama.com/api/chat",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=360
        )

        if r.status_code != 200:
            print(f"[LLM CLOUD ERROR {tag}] {r.text[:300]}", flush=True)

        r.raise_for_status()

        raw = r.json()["message"]["content"]
        dt_ms = (time.monotonic() - t0) * 1000.0

        self.last_llm_latency_ms = dt_ms
        self.last_llm_model_name = model_name

        parsed = extract_json(raw)
        self.log_llm_io(tag, system_text, user_text, raw, parsed, dt_ms)

        return raw

    except Exception as e:
        print(f"[LLM CLOUD FAIL {tag}] {e}", flush=True)
        return ""

# Local Ollama
def call_ollama(self, system_text: str, user_text: str, tag: str = "general") -> str:
    payload = {
        "model": self.OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system_text},
            {"role": "user", "content": user_text}
        ],
        "stream": False,
        "format": "json",  # force valid JSON
        "options": {
            "temperature": 0,
            "top_p": 0.9
        }
    }
    t0 = time.monotonic()
    r = requests.post(
        f"{self.OLLAMA_URL}/api/chat",
        json=payload,
        timeout=self.OLLAMA_TIMEOUT_SEC,
    )
    r.raise_for_status()
    
    raw = r.json()["message"]["content"]
    dt_ms = (time.monotonic() - t0) * 1000.0

    self.last_llm_latency_ms = dt_ms
    self.last_llm_model_name = self.OLLAMA_MODEL

    parsed = extract_json(raw)  # may be None
    self.log_llm_io(tag, system_text, user_text, raw, parsed, dt_ms)

    return raw