"""
Runs a batch of realistic questions against the running API and prints a
summary. Use this to generate the log entries for the assessment writeup.

Usage:
    (start the server first: uvicorn app.main:app --reload)
    python run_test_cases.py
"""
import io
import json
import httpx

from pathlib import Path
from app.pdf_utils import read_pdf

BASE_URL = "http://127.0.0.1:8000"
DOCS_DIR = Path(__file__).parent / "sample_docs"

TEST_QUESTIONS = [
    "How many days of continuous employment before I'm eligible for remote work?",
    "What is the home office stipend amount?",
    "Do I need a receipt for a $15 expense?",
    "What is the daily meal reimbursement cap while travelling?",
    "Can I expense alcohol on a business trip?",
    "How many vacation days do employees get per year?",   # NOT in either doc -> should trigger NOT_FOUND
]
# TEST_QUESTIONS = [
  
#     # --- 2. Dyson Warranty Doc Questions (Direct Fact Extraction) ---
#     "What is the timeframe allowed for exchanging or returning a product?",  # 14 days[cite: 10]
#     "How long is the warranty period for cordless vacuums and purifiers?",  # 2 years[cite: 10]
#     "What is the warranty period for upright vacuums?",  # 5 years[cite: 10]
#     "What email address should I contact for customer support within the UAE?",  # support.uae@dyson.com[cite: 10]
#     "Are battery and filter replacements covered under normal wear and tear?",  # No[cite: 10]
#     "In what form will a refund be issued if I return an item?",  # Dyson credit vouchers / credit memo[cite: 10]
#     "Can I transfer my Dyson warranty to a new owner if I sell the machine?",  # Yes, with conditions[cite: 10]

#     # --- 3. Ontario Electricity Mix Doc Questions (Data & Numbers) ---
#     "What percentage of Ontario's electricity supply mix came from Nuclear Energy in 2025?",  # 46.2%
#     "How many Terawatt-hours (TWh) did Water Power generate in total?",  # 38.1 TWh[cite: 9]
#     "What was the total Terawatt-hour generation from Tx-Connected sources?",  # 162.5 TWh[cite: 9]
#     "What percentage of the 2025 electricity mix came from Bioenergy?",  # 0.4%[cite: 9]
#     "Which regulation requires electricity retailers to disclose the supply mix to consumers?",  # O. Reg. 416/99[cite: 9]

#     # --- 4. Out-of-Scope / Hallucination Triggers (Must return NOT_FOUND) ---
#     "What is the phone number for Dyson customer support in Canada?",  # NOT_FOUND (Only UAE numbers listed)[cite: 10]
#     "What was the total electricity generation in Ontario for the year 2020?",  # NOT_FOUND (Only 2025 data present)[cite: 9]
#     "How long is the warranty on Dyson robot lawnmowers?",  # NOT_FOUND (Product category not present)[cite: 10]
#     "What is the cost of replacing a damaged Dyson vacuum motor?",  # NOT_FOUND (Prices not in doc)[cite: 10]
#     "What is the target percentage for Solar power generation in 2030?",  # NOT_FOUND[cite: 9]

#     # --- 5. Adversarial / Trick Questions ---
#     "Is accidental damage covered under the Dyson warranty if I present the original invoice?",  # Not covered [cite: 10]
#     "Does the electricity supply mix data account for Clean Energy Credits (CECs)?",  # No / Figures do not account[cite: 9]
# ]



def load_docs() -> dict[str, str]:
    """Loads text from all .txt and .pdf files in DOCS_DIR."""
    docs = {}
    
    # Load .txt files
    for p in DOCS_DIR.glob("*.txt"):
        docs[p.name] = p.read_text(encoding="utf-8")
        
    # Load .pdf files
    for p in DOCS_DIR.glob("*.pdf"):
        docs[p.name] = read_pdf(p)
        
    return docs


def main():
    docs = load_docs()
    if not docs:
        print(f"No .txt or .pdf files found in {DOCS_DIR.resolve()}")
        return

    print(f"Loaded {len(docs)} documents: {list(docs.keys())}\n")
    
    results = []
    with httpx.Client(timeout=500) as client:
        for q in TEST_QUESTIONS:
            resp = client.post(f"{BASE_URL}/ask", json={"docs": docs, "question": q})
            resp.raise_for_status()
            data = resp.json()
            results.append({"question": q, **data})
            flag = "NOT_FOUND (expected fail case)" if not data["answered_from_context"] else "answered"
            print(f"[{flag}] Q: {q}\n  -> {data['answer'][:200]}\n")

    Path("test_results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\n{len(results)} questions run. Full results in test_results.json")
    print("Fetch full audit log via GET /logs")


if __name__ == "__main__":
    main()
