"""Read-only access to the synthetic bank knowledge: error codes, logs, source code and transactions.

Every function returns {"ok": bool, "results": [{"ref": ..., "text": ...}], "error"?: str}.
The `ref` values are the evidence identifiers the agent must cite in its report.
"""

import json
import re
import sqlite3
from contextlib import closing
from pathlib import Path

from incident_assistant.config import DATA_DIR, DB_PATH

LOGS_DIR = DATA_DIR / "logs"
WORKSPACE_DIR = DATA_DIR / "workspace"
ERROR_CODES_FILE = DATA_DIR / "error_codes.json"

MAX_RESULTS = 20
MAX_READ_LINES = 120


def ok(results: list[dict], **extra) -> dict:
    return {"ok": True, "results": results, **extra}


def fail(error: str) -> dict:
    return {"ok": False, "results": [], "error": error}


def lookup_error_code(code: str) -> dict:
    catalog = json.loads(ERROR_CODES_FILE.read_text())
    code = code.strip().upper()
    if code not in catalog:
        return ok([], found=False, note=f"{code} is not in the error code catalog.")
    entry = catalog[code]
    text = f"{code}: {entry['meaning']} (service={entry['service']}, owner={entry['owner']})"
    return ok([{"ref": f"catalog:{code}", "text": text, **entry}], found=True)


def _terms(query: str) -> list[str]:
    return [t.lower() for t in re.split(r"\s+", query.strip()) if len(t) >= 3]


def _search_lines(files: list[Path], base: Path, prefix: str, query: str, limit: int) -> dict:
    terms = _terms(query)
    if not terms:
        return fail("Query must contain at least one term with 3 or more characters.")
    matches = []
    for file in files:
        relative = file.relative_to(base).as_posix()
        for number, line in enumerate(file.read_text().splitlines(), start=1):
            score = sum(term in line.lower() for term in terms)
            if score:
                matches.append((score, {"ref": f"{prefix}:{relative}:{number}", "text": line.strip()}))
    matches.sort(key=lambda m: -m[0])
    results = [m[1] for m in matches[: min(limit, MAX_RESULTS)]]
    return ok(results, note=None if results else "No matching lines.")


def search_logs(query: str, service: str | None = None, limit: int = MAX_RESULTS) -> dict:
    files = sorted(LOGS_DIR.glob(f"{service}.log" if service else "*.log"))
    if not files:
        return fail(f"No log file for service '{service}'. Available: {[f.stem for f in LOGS_DIR.glob('*.log')]}")
    return _search_lines(files, LOGS_DIR, "log", query, limit)


def search_code(query: str, service: str | None = None, limit: int = MAX_RESULTS) -> dict:
    root = WORKSPACE_DIR / service if service else WORKSPACE_DIR
    if not root.is_dir() or not _inside(root, WORKSPACE_DIR):
        return fail(f"Unknown service '{service}'. Available: {[p.name for p in WORKSPACE_DIR.iterdir() if p.is_dir()]}")
    return _search_lines(sorted(root.rglob("*.java")), WORKSPACE_DIR, "code", query, limit)


def _inside(path: Path, base: Path) -> bool:
    return path.resolve().is_relative_to(base.resolve())


def read_file(path: str, start_line: int = 1, end_line: int = MAX_READ_LINES) -> dict:
    # Accept refs like "code:eft-service/.../IbanValidator.java:19" as well as plain relative paths.
    path = re.sub(r"^code:", "", path.strip())
    path = re.sub(r":\d+$", "", path)
    file = WORKSPACE_DIR / path
    if not _inside(file, WORKSPACE_DIR):
        return fail("Access denied: path is outside the source workspace.")
    if not file.is_file():
        return fail(f"File not found: {path}. Use search_code to find the correct path.")
    lines = file.read_text().splitlines()
    start = max(1, start_line)
    end = min(len(lines), end_line, start + MAX_READ_LINES - 1)
    results = [
        {"ref": f"code:{path}:{number}", "text": lines[number - 1]}
        for number in range(start, end + 1)
        if lines[number - 1].strip()
    ]
    return ok(results, total_lines=len(lines))


def _query(sql: str, params: tuple) -> list[dict]:
    with closing(sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        return [dict(row) for row in connection.execute(sql, params).fetchall()]


def _transaction_results(rows: list[dict]) -> list[dict]:
    return [
        {
            "ref": f"txn:{row['authorization_id']}",
            "text": ", ".join(f"{key}={value}" for key, value in row.items() if value is not None),
        }
        for row in rows
    ]


def get_transaction(transaction_id: str) -> dict:
    if not DB_PATH.exists():
        return fail("Transaction database is not initialized. Run `python ingest.py`.")
    rows = _query("SELECT * FROM transactions WHERE transaction_id = ?", (transaction_id.strip(),))
    return ok(_transaction_results(rows), note=None if rows else "No transaction found.")


def list_customer_transactions(customer_id: str, date: str) -> dict:
    if not DB_PATH.exists():
        return fail("Transaction database is not initialized. Run `python ingest.py`.")
    rows = _query(
        "SELECT * FROM transactions WHERE customer_id = ? AND created_at LIKE ? ORDER BY created_at LIMIT 50",
        (customer_id.strip(), f"{date.strip()}%"),
    )
    return ok(_transaction_results(rows), note=None if rows else "No transactions found.")
