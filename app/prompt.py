"""
Prompt construction for the Doc Q&A assistant.

Design choice worth calling out in the writeup: the system prompt explicitly
forbids answering from outside the provided context, and requires the model
to say so in a detectable way. This is the fix that came out of the
"break it on purpose" test (see /run_test_cases.py and the writeup) after
the first version of this prompt hallucinated an answer to an
out-of-scope question instead of admitting it didn't know.
"""

SYSTEM_PROMPT = """You are an internal document Q&A assistant for a company.

Rules:
1. Answer ONLY using the document excerpts provided in the <documents> block below.
2. If the answer is not present in the documents, you MUST respond with exactly:
   "NOT_FOUND: The provided documents do not contain information to answer this question."
   Do not guess, infer beyond the text, or use outside knowledge.
3. When you do answer, cite which document the answer came from using the
   format [Source: <filename>] immediately after the relevant sentence.
4. Keep answers concise (2-5 sentences) and factual.
5. Never fabricate a citation. Only cite a filename that appears in the
   <documents> block.
6. A question phrased as "can I..." or "am I allowed to..." can be answered
   by a rule stated in the negative (e.g. "X is not permitted", "X is not
   reimbursable", "X requires approval"). Read prohibitions and restrictions
   as valid, direct answers to permission-style questions -- do not return
   NOT_FOUND just because the document's wording doesn't literally echo the
   question's wording.
"""


def build_documents_block(docs: dict[str, str]) -> str:
    """docs: {filename: text_content}"""
    parts = []
    for name, content in docs.items():
        parts.append(f'<document filename="{name}">\n{content.strip()}\n</document>')
    return "<documents>\n" + "\n\n".join(parts) + "\n</documents>"


def build_user_message(docs: dict[str, str], question: str) -> str:
    return f"{build_documents_block(docs)}\n\n<question>\n{question}\n</question>"


def full_prompt_for_log(docs: dict[str, str], question: str) -> str:
    """Human-readable combined prompt, stored in the log for auditability."""
    return f"[SYSTEM]\n{SYSTEM_PROMPT}\n\n[USER]\n{build_user_message(docs, question)}"
