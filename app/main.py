"""
Internal Document Q&A Assistant — FastAPI backend.

Endpoints:
    POST /ask                  -> ask a question against uploaded doc text
    GET  /logs                 -> view the full audit log
    GET  /logs/{log_id}        -> view one log entry
    POST /review/{log_id}      -> human reviewer sets approved/rejected

Model: Anthropic Claude (claude-3-5-haiku or similar cheap/free-tier model)
by default. Swap MODEL_PROVIDER to "ollama" to run fully free/local against
Ollama (e.g. llama3.1:8b) with zero API cost -- see call_ollama() below.
No vector DB / embeddings: at this scale (a handful of internal docs) the
full text is simply placed in context, which is simpler, cheaper, and
easier to audit than a RAG pipeline for a prototype of this size.
"""
import os
import re
import httpx

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from typing import List

from . import db
from .prompt import SYSTEM_PROMPT, build_user_message, full_prompt_for_log
from .pdf_utils import read_pdf

MODEL_PROVIDER = os.environ.get("MODEL_PROVIDER", "gemini")  # "anthropic" | "ollama" | "mock"
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-3-5-haiku-20241022")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.1:8b")
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", 'gemini-3.1-flash-lite')
app = FastAPI(title="Internal Document Q&A Assistant")


@app.on_event("startup")
def startup():
    db.init_db()


@app.get("/health")
def health():
    return {"status": "ok"}


# ---------- Model calls ----------

# Not used 
def call_anthropic(docs: dict[str, str], question: str) -> str:
    import anthropic

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
    resp = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=500,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": build_user_message(docs, question)}],
    )
    return resp.content[0].text

# Used
def call_ollama(docs: dict[str, str], question: str) -> str:
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": f"{SYSTEM_PROMPT}\n\n{build_user_message(docs, question)}",
        "stream": False,
    }
    r = httpx.post(f"{OLLAMA_HOST}/api/generate", json=payload, timeout=120)
    r.raise_for_status()
    return r.json()["response"]

def call_gemini(docs: dict[str, str], question: str) -> str:
    from google import genai
    from google.genai import types

    # Reads GEMINI_API_KEY automatically from environment
    client = genai.Client()

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=build_user_message(docs, question),
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0.2,
        ),
    )
    return response.text


def call_mock(docs: dict[str, str], question: str) -> str:
    """
    Deterministic keyword-match stand-in for a real LLM. Used only to prove
    the pipeline (context-passing, logging, NOT_FOUND detection, citation
    parsing, review gate) works end-to-end without needing an API key or a
    local model installed. Swap MODEL_PROVIDER to "anthropic" or "ollama"
    for real answers -- this is plumbing verification, not the actual AI
    step, and the writeup should say so explicitly.
    """
    q_lower = question.lower()
    for name, text in docs.items():
        for line in text.splitlines():
            words = [w for w in re.findall(r"[a-z]+", q_lower) if len(w) > 3]
            if words and sum(w in line.lower() for w in words) >= 2:
                return f"{line.strip()} [Source: {name}]"
    return "NOT_FOUND: The provided documents do not contain information to answer this question."


def call_model(docs: dict[str, str], question: str) -> str:
    if MODEL_PROVIDER == "gemini":
        return call_gemini(docs, question)
    if MODEL_PROVIDER == "ollama":
        return call_ollama(docs, question)
    if MODEL_PROVIDER == "mock":
        return call_mock(docs, question)
    if MODEL_PROVIDER == "anthropic":
        return call_anthropic(docs, question)
    
    # Default fallback to Gemini
    return call_gemini(docs, question)



# ---------- Schemas ----------

class AskRequest(BaseModel):
    docs: dict[str, str]      # {filename: raw text}
    question: str


class ReviewRequest(BaseModel):
    status: str                # "approved" | "rejected"
    note: str | None = None


# ---------- Routes ----------

@app.post("/ask")
def ask(req: AskRequest):
    if not req.docs:
        raise HTTPException(400, "No documents provided")
    if not req.question.strip():
        raise HTTPException(400, "Empty question")

    model_name_map = {
        "gemini": GEMINI_MODEL,
        "ollama": OLLAMA_MODEL,
        "mock": "mock-keyword-matcher",
        "anthropic": ANTHROPIC_MODEL,
    }
    model_name = model_name_map.get(MODEL_PROVIDER, GEMINI_MODEL)

    raw_output = call_model(req.docs, req.question)

    answered_from_context = not raw_output.strip().startswith("NOT_FOUND")
    citation_match = re.search(r"\[Source:\s*([^\]]+)\]", raw_output)
    citation = citation_match.group(1).strip() if citation_match else None

    log_id = db.insert_log(
        model=model_name,
        source_docs=list(req.docs.keys()),
        prompt=full_prompt_for_log(req.docs, req.question),
        question=req.question,
        output=raw_output,
        citation=citation,
        answered_from_context=answered_from_context,
    )

    return {
        "log_id": log_id,
        "answer": raw_output,
        "citation": citation,
        "answered_from_context": answered_from_context,
        "reviewer_status": "pending",
    }

@app.post("/ask-pdf")
async def ask_pdf(question: str = Form(...), files: List[UploadFile] = File(...)):
    if not files:
        raise HTTPException(400, "No PDF files uploaded")
    if not question.strip():
        raise HTTPException(400, "Empty question")

    # Extract text from uploaded PDF files into your docs dictionary
    docs: dict[str, str] = {}
    for file in files:
        if not file.filename.endswith(".pdf"):
            raise HTTPException(400, f"File {file.filename} is not a PDF")
        
        contents = await file.read()
        extracted_text = read_pdf(contents)
        docs[file.filename] = extracted_text

    # Route to Gemini model using your existing pipeline
    raw_output = call_model(docs, question)

    answered_from_context = not raw_output.strip().startswith("NOT_FOUND")
    citation_match = re.search(r"\[Source:\s*([^\]]+)\]", raw_output)
    citation = citation_match.group(1).strip() if citation_match else None

    # Log execution matching your audit schema
    log_id = db.insert_log(
        model=GEMINI_MODEL if MODEL_PROVIDER == "gemini" else MODEL_PROVIDER,
        source_docs=list(docs.keys()),
        prompt=full_prompt_for_log(docs, question),
        question=question,
        output=raw_output,
        citation=citation,
        answered_from_context=answered_from_context,
    )

    return {
        "log_id": log_id,
        "answer": raw_output,
        "citation": citation,
        "answered_from_context": answered_from_context,
        "reviewer_status": "pending",
    }

@app.get("/logs")
def logs():
    return db.get_all_logs()


@app.get("/logs/{log_id}")
def get_log(log_id: int):
    row = db.get_log(log_id)
    if not row:
        raise HTTPException(404, "Log not found")
    return row


@app.post("/review/{log_id}")
def review(log_id: int, req: ReviewRequest):
    if not db.get_log(log_id):
        raise HTTPException(404, "Log not found")
    db.update_review_status(log_id, req.status, req.note)
    return db.get_log(log_id)
