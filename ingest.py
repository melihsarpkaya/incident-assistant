"""Prepare runtime data: SQLite transaction database and the documentation vector index."""

import sqlite3

from incident_assistant.config import DATA_DIR, DB_PATH, RUNTIME_DIR
from mcp_server.retrieval import build_index


def build_database() -> None:
    RUNTIME_DIR.mkdir(exist_ok=True)
    DB_PATH.unlink(missing_ok=True)
    with sqlite3.connect(DB_PATH) as connection:
        connection.executescript((DATA_DIR / "seed.sql").read_text())


if __name__ == "__main__":
    build_database()
    print(f"Transaction database created: {DB_PATH}")
    print(f"Indexed {build_index()} documentation chunks.")
