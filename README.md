# Internal Document Q&A Assistant — Prototype

## What this is

A FastAPI backend that answers questions against a small set of internal
documents by placing their full text directly in the model's context
(no vector DB / embeddings unnecessary at this scale and cuts out an
entire failure surface for a prototype this size). Every question and
answer is logged with a `pending` review status; a human reviewer must
explicitly approve or reject each answer via a separate endpoint before
it would be considered "safe to act on."

## Why no vector database

For 2-4 short internal docs, stuffing full text into context is simpler,
cheaper, more auditable, and just as accurate as a RAG pipeline and it
removes chunking/retrieval as a source of error, which matters more at
prototype stage than at scale. This is a genuine design tradeoff, not a
shortcut: it would need revisiting if the document set grew into the
hundreds.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate   # venv\Scripts\activate on Windows
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and set the provider credentials you need.
The default provider is Gemini; use `MODEL_PROVIDER=mock` for a local smoke
test without an API key. The SQLite database path is configurable with
`QA_DB_PATH` so a deployment can mount persistent storage.

## Running

Three model providers are supported via the `MODEL_PROVIDER` env var:

**1. Mock (zero setup, no API key, proves the pipeline works)**
```bash
MODEL_PROVIDER=mock uvicorn app.main:app --reload
```
Note: the mock is a naive keyword matcher, not real language understanding
— see Known Limitations below. It's there to validate plumbing, not to
represent real answer quality.

**2. Ollama (fully free, fully local, real LLM)**
```bash
# separately: install Ollama, then `ollama pull llama3.1:8b`
MODEL_PROVIDER=ollama OLLAMA_MODEL=llama3.1:8b uvicorn app.main:app --reload
```

**3. Anthropic Claude (free-tier console credits)**
```bash
export ANTHROPIC_API_KEY=your_key_here
MODEL_PROVIDER=anthropic uvicorn app.main:app --reload
```

**4. Gemini**
```bash
export GEMINI_API_KEY=your_key_here
MODEL_PROVIDER=gemini uvicorn app.main:app --reload
```

For a production process, bind to all interfaces and use the platform port:
```bash
uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
```

### Docker

```bash
docker build -t docqa .
docker run --rm -p 8000:8000 -e MODEL_PROVIDER=mock docqa
```

To run Docker with environment configuration on Windows Command Prompt:

```cmd
copy .env.example .env
notepad .env
```

Set `MODEL_PROVIDER=mock` in `.env` for a local test without an API key,
then run:

```cmd
docker run --rm --name docqa-local -p 8000:8000 --env-file .env -v "%cd%\logs:/app/logs" docqa
```


Open `http://localhost:8000/health` to verify the service is running. For
real deployments, provide the model API key as a platform secret and mount
`/app/logs` as persistent storage. OCR support in the image uses Tesseract;
local Windows installations can set `TESSERACT_CMD` to the executable path.

Then run the test batch:
```bash
python run_test_cases.py
```

View the audit log: `GET /logs` or `/logs/{id}`
Approve/reject an answer: `POST /review/{id}` with `{"status": "approved"}`

## What was actually tested (this run)

Ran with `MODEL_PROVIDER=mock` against two sample docs (remote work policy,
expense policy) and 6 questions, 5 in-scope and 1 deliberately out-of-scope
("vacation days" — not mentioned in either doc). Full log: `logs/qa_log_export.csv`.

## The failure case (required by the assessment)

The out-of-scope question ("How many vacation days...") should have
triggered the `NOT_FOUND` response. Instead, the naive mock matcher
returned a wrong, confidently-worded answer stitched from an unrelated
sentence. This is exactly the hallucination risk the system prompt (see
`app/prompt.py`) is designed to prevent for a *real* LLM — the mock's
failure demonstrates why the explicit "don't guess, say NOT_FOUND"
instruction and the human-review gate both matter: a naive/broken
component here would have shipped a wrong answer to an employee with no
visible flag, if not for the mandatory `pending` status catching it before
release. This log entry was marked `rejected` in the review step.

**Caveat for the write-up:** this specific failure is a mock-matcher
limitation, not evidence about Claude/Ollama's real behavior — those
should be tested directly with the same out-of-scope question before
drawing conclusions about the real model's hallucination rate.

## Known limitations

- No authentication/authorization on endpoints (prototype only — would
  need this before any real deployment).
- Mock provider is a keyword matcher, not a real LLM — only used to
  validate the pipeline's plumbing (logging, review gate, citation
  parsing), not to demonstrate real answer quality.
- No chunking/retrieval — full-document-in-context won't scale past a
  small number of short documents.
- SQLite logging is fine for a prototype; a real deployment would want a
  proper database with access controls given the log stores full document
  text and questions.
- Background server processes proved unreliable in the sandbox used to
  build this (a real deployment environment would not have this issue) —
  noted here for transparency, not as a product limitation.
