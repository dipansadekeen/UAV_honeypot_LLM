# UAV Honeypot LLM

A MAVLink drone honeypot that answers ground control station commands and generates heartbeat and telemetry updates with an LLM.

This repository contains the files from `Final` at the repository root: the Python modules, `prompts/`, `examples/`, and example mission plans in `missions/`.

## Run locally

Use Python 3.10 or newer. From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export OLLAMA_URL=http://127.0.0.1:11434   # Ollama server address
export OLLAMA_MODEL=gpt-oss:20b            # any model pulled on that server, e.g.
                                           # gpt-oss:20b, gpt-oss:120b, nemotron-3-nano:30b,
                                           # nemotron-3-super, gemma4:31b
python module_main.py
```

Set `OLLAMA_URL` and `OLLAMA_MODEL` to a running Ollama server and an available model. The current network configuration listens for MAVLink on `127.0.0.1:14551` and sends to a ground control station on `127.0.0.1:14550`.

The command heartbeat and telemetry system prompts are in `prompts/`. The example data loaded at startup is in `examples/`.

## Evaluated models

The paper evaluates five models, all served through Ollama Cloud:

| Model | Ollama tag | Name in `results/` |
|---|---|---|
| GPT-OSS 20B | `gpt-oss:20b-cloud` | `gpt-oss-20b` |
| GPT-OSS 120B | `gpt-oss:120b-cloud` | `gpt-oss-120b` |
| Nemotron 3 Super | `nemotron-3-super:cloud` | `nemotron-super` |
| Nemotron 3 Nano 30B | `nemotron-3-nano:30b-cloud` | `nemotron-nano` |
| Gemma 4 31B | `gemma4:31b-cloud` | `gemma4` |

To run the honeypot with one of these models, set the tag and switch the heartbeat and telemetry handlers in `module_llmhoneypot.py` from `call_ollama` to `call_ollama_cloud` (the alternative call is in a comment above each one):

```bash
export OLLAMA_CLOUD_MODEL=gpt-oss:20b-cloud
export OLLAMA_API_KEY=<your Ollama API key>
```

## Optional cloud credentials

The active command handlers use local Ollama. If you switch to the optional cloud functions, set `OLLAMA_API_KEY` or `GEMINI_API_KEY` in your environment. The code also accepts local `api_key.txt` and `gemini_api.txt` files, which are ignored by Git. Do not commit real credentials.

Runtime logs are written under `logs/` and are also ignored by Git.
