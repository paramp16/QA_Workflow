"""
Exports the full qa_log.db audit trail to a CSV file for the assessment
writeup. Run any time -- safe to run repeatedly, it always reflects the
current full log (mock + Ollama + any other runs, all of it).
 
Usage:
    python export_logs.py
"""
import sqlite3
import csv
from pathlib import Path
 
DB_PATH = Path(__file__).parent / "logs" / "qa_log.db"
OUT_PATH = Path(__file__).parent / "logs" / "qa_log_export.csv"
 
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
rows = conn.execute(
    """
    SELECT id, timestamp, model, source_docs, question, output, citation,
           answered_from_context, reviewer_status, reviewer_note
    FROM qa_log
    ORDER BY id
    """
).fetchall()
conn.close()
 
OUT_PATH.parent.mkdir(exist_ok=True)
with open(OUT_PATH, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow([
        "id", "timestamp", "model", "source_docs", "question", "output",
        "citation", "answered_from_context", "reviewer_status", "reviewer_note",
    ])
    for r in rows:
        writer.writerow(list(r))
 
print(f"Exported {len(rows)} rows to {OUT_PATH}")
 
