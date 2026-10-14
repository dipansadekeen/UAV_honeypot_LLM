# UAV Honeypot LLM

A MAVLink drone honeypot that answers ground control station commands and generates heartbeat and telemetry updates with an LLM.

This repository contains the files from `Final` at the repository root: the Python modules, `prompts/`, `examples/`, and example mission plans in `missions/`.

## Run locally

Use Python 3.10 or newer. From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export OLLAMA_URL=http://127.0.0.1:11434
export OLLAMA_MODEL=gpt-oss:20b
python module_main.py
```

Set `OLLAMA_URL` and `OLLAMA_MODEL` to a running Ollama server and an available model. The current network configuration listens for MAVLink on `127.0.0.1:14551` and sends to a ground control station on `127.0.0.1:14550`.

The command heartbeat and telemetry system prompts are in `prompts/`. The example data loaded at startup is in `out/`.

## Optional cloud credentials

The active command handlers use local Ollama. If you switch to the optional cloud functions, set `OLLAMA_API_KEY` or `GEMINI_API_KEY` in your environment. The code also accepts local `api_key.txt` and `gemini_api.txt` files, which are ignored by Git. Do not commit real credentials.

Runtime logs are written under `logs/` and are also ignored by Git.
