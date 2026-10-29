"""Vector search over the service documentation (RAG)."""

import re
from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_ollama import OllamaEmbeddings

from incident_assistant.config import CHROMA_DIR, DATA_DIR, EMBEDDING_MODEL, OLLAMA_URL

DOCS_DIR = DATA_DIR / "docs"
COLLECTION = "service_docs"


def _store() -> Chroma:
    return Chroma(
        collection_name=COLLECTION,
        embedding_function=OllamaEmbeddings(model=EMBEDDING_MODEL, base_url=OLLAMA_URL),
        persist_directory=str(CHROMA_DIR),
    )


def _slug(heading: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", heading.lower()).strip("-")


def split_markdown(file: Path) -> list[Document]:
    """One chunk per '## ' section, prefixed with the document title for context."""
    text = file.read_text()
    title = text.splitlines()[0].lstrip("# ").strip()
    chunks = []
    for section in re.split(r"^## ", text, flags=re.MULTILINE)[1:]:
        heading, _, body = section.partition("\n")
        ref = f"doc:{file.name}#{_slug(heading)}"
        chunks.append(
            Document(
                page_content=f"{title} - {heading.strip()}\n{body.strip()}",
                metadata={"ref": ref, "source": file.name},
            )
        )
    return chunks


def build_index() -> int:
    store = _store()
    store.reset_collection()
    documents = [chunk for file in sorted(DOCS_DIR.glob("*.md")) for chunk in split_markdown(file)]
    store.add_documents(documents, ids=[d.metadata["ref"] for d in documents])
    return len(documents)


def search_docs(query: str, k: int = 4) -> dict:
    if not CHROMA_DIR.exists():
        return {"ok": False, "results": [], "error": "Document index is missing. Run `python ingest.py`."}
    documents = _store().similarity_search(query, k=min(k, 6))
    results = [{"ref": d.metadata["ref"], "text": d.page_content} for d in documents]
    return {"ok": True, "results": results}
