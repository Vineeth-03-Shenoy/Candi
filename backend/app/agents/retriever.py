"""
Retriever Agent — Query interface for RAG

Handles:
  - Querying the vector store for relevant context
  - Formatting chunks into LLM-friendly context blocks
  - Caching and deduplication
"""
from typing import Optional

from app.services.vector_store import VectorStore
from app.utils.logger import get_logger

log = get_logger(__name__)


class RetrieverAgent:
    """Query interface for retrieving context from the vector store."""

    def __init__(self, vector_store: VectorStore):
        log.debug("Initialising RetrieverAgent")
        self.vector_store = vector_store

    def get_context(
        self,
        session_id: str,
        query: str,
        top_k: int = 3,
    ) -> str:
        """
        Retrieve top-k relevant chunks from the session's vector store.

        Returns a formatted context block ready to inject into an LLM prompt.
        Returns empty string if no collection exists or no results are found.

        Format:
        -------
        [Retrieved Context]
        [resume — Experience]: You have 4 years of experience in structural design...
        [rounds — Round 1]: Technical Round 1 focuses on AutoCAD and load calculations...
        [technical — chunk 2]: Common questions on Structural Analysis include...
        """
        if not query or not session_id:
            log.warning("get_context called with empty query or session_id")
            return ""

        log.info("Retrieving context | session_id=%s | query='%s' | top_k=%d",
                 session_id, query[:80], top_k)

        # Query the vector store
        chunks = self.vector_store.query(session_id, query, top_k=top_k)

        if not chunks:
            log.debug("No chunks retrieved | session_id=%s", session_id)
            return ""

        # Format chunks into a context block
        context_lines = ["[Retrieved Context]"]

        for i, chunk_dict in enumerate(chunks[:top_k]):
            text = chunk_dict.get("text", "")
            metadata = chunk_dict.get("metadata", {})
            distance = chunk_dict.get("distance", 0)

            if not text.strip():
                continue

            # Build label from document_type and section/round/index
            doc_type = metadata.get("document_type", "unknown")
            section = metadata.get("section", "")
            round_idx = metadata.get("round_index", "")
            chunk_idx = metadata.get("chunk_index", "")

            if section:
                label = f"{doc_type} — {section}"
            elif round_idx:
                label = f"{doc_type} — Round {round_idx}"
            else:
                label = f"{doc_type} — chunk {chunk_idx}"

            # Truncate text to ~200 chars per chunk for readability
            preview = text.replace("\n", " ").strip()[:200]

            context_lines.append(f"[{label}]: {preview}")
            log.debug(
                "Chunk included | doc_type=%s | distance=%.3f | preview_len=%d",
                doc_type, distance, len(preview),
            )

        context_block = "\n".join(context_lines)
        log.info(
            "Context block built | session_id=%s | num_chunks=%d | block_length=%d",
            session_id, len(chunks), len(context_block),
        )
        return context_block

    def get_context_raw(
        self,
        session_id: str,
        query: str,
        top_k: int = 5,
    ) -> list[dict]:
        """
        Get raw chunk results (unformatted) for advanced use cases.
        Returns list of dicts: [{"text": ..., "metadata": ..., "distance": ...}, ...]
        """
        log.debug("Retrieving raw context | session_id=%s | query='%s'",
                  session_id, query[:80])
        return self.vector_store.query(session_id, query, top_k=top_k)
