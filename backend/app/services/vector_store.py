"""
Vector Store Service — ChromaDB wrapper for RAG

Handles:
  - Chunking strategies (role-agnostic, not domain-specific)
  - Embedding with ChromaDB's local all-MiniLM-L6-v2 ONNX model (free, $0)
  - Persistent ChromaDB storage (backend/chroma_db/)
  - Per-session collections
"""
import os
import re
from typing import Optional

import chromadb
from chromadb.config import Settings
from chromadb.utils import embedding_functions

from app.utils.logger import get_logger

log = get_logger(__name__)

_DEFAULT_EMBEDDING_FN = embedding_functions.DefaultEmbeddingFunction()


def _get_chroma_client():
    """Initialize persistent ChromaDB client pointing to backend/chroma_db/."""
    db_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "chroma_db"
    )
    log.debug("ChromaDB path: %s", os.path.abspath(db_path))
    os.makedirs(db_path, exist_ok=True)

    settings = Settings(
        is_persistent=True,
        persist_directory=db_path,
        anonymized_telemetry=False,
    )
    client = chromadb.Client(settings)
    log.info("ChromaDB client initialized | path=%s", os.path.abspath(db_path))
    return client


class VectorStore:
    """ChromaDB-backed vector store for session-scoped RAG."""

    def __init__(self):
        log.debug("Initialising VectorStore")
        self.client = _get_chroma_client()

    def _get_or_create_collection(self, session_id: str):
        """Get or create a collection for the session."""
        collection_name = f"session_{session_id}"
        try:
            collection = self.client.get_collection(
                name=collection_name,
                embedding_function=_DEFAULT_EMBEDDING_FN,
            )
            log.debug("Retrieved existing collection | session_id=%s", session_id)
        except Exception:
            collection = self.client.create_collection(
                name=collection_name,
                metadata={"session_id": session_id},
                embedding_function=_DEFAULT_EMBEDDING_FN,
            )
            log.info("Created new collection | session_id=%s", session_id)
        return collection

    # ------------------------------------------------------------------
    # Chunking strategies
    # ------------------------------------------------------------------

    def _chunk_by_section(self, text: str, section_headers: list[str]) -> list[dict]:
        """
        Split text by section headers.
        Returns list of dicts: [{"text": chunk_text, "section": header_name}, ...]
        """
        if not text:
            return []

        chunks: list[dict] = []
        current_section = "preamble"
        current_text = ""

        for line in text.split("\n"):
            # Check if line starts a new section
            matched_header = None
            for header in section_headers:
                if re.match(rf"^\s*\*\*{re.escape(header)}\*\*", line, re.IGNORECASE):
                    matched_header = header
                    break

            if matched_header:
                # Save previous section
                if current_text.strip():
                    chunks.append({"text": current_text.strip(), "section": current_section})
                # Start new section
                current_section = matched_header
                current_text = ""
            else:
                current_text += line + "\n"

        # Save final section
        if current_text.strip():
            chunks.append({"text": current_text.strip(), "section": current_section})

        log.debug(
            "Chunked by section | document_type=%s | num_chunks=%d",
            current_section, len(chunks),
        )
        return chunks

    def _chunk_sliding_window(self, text: str, window_tokens: int = 400, overlap_tokens: int = 50) -> list[str]:
        """
        Sliding window chunking for free-form prose.
        Approximates tokens as word count * 1.3 (rough heuristic).
        """
        if not text:
            return []

        words = text.split()
        window_words = max(int(window_tokens / 1.3), 50)
        overlap_words = max(int(overlap_tokens / 1.3), 10)
        stride = window_words - overlap_words

        chunks: list[str] = []
        for i in range(0, len(words), stride):
            chunk = " ".join(words[i : i + window_words])
            if chunk.strip():
                chunks.append(chunk)

        log.debug(
            "Sliding window chunked | num_chunks=%d | avg_words=%d",
            len(chunks),
            sum(len(c.split()) for c in chunks) // len(chunks) if chunks else 0,
        )
        return chunks

    def _chunk_by_rounds(self, text: str) -> list[dict]:
        """
        Split text by interview round (looks for 'Round N' or 'Stage N' patterns).
        Returns list of dicts: [{"text": chunk_text, "round_index": N}, ...]
        """
        if not text:
            return []

        chunks: list[dict] = []
        current_round = 0
        current_text = ""

        for line in text.split("\n"):
            # Look for round markers
            match = re.search(r"(?:Round|Stage|Interview)\s+(\d+)", line, re.IGNORECASE)
            if match:
                round_num = int(match.group(1))
                if current_text.strip():
                    chunks.append({"text": current_text.strip(), "round_index": current_round})
                current_round = round_num
                current_text = line + "\n"
            else:
                current_text += line + "\n"

        if current_text.strip():
            chunks.append({"text": current_text.strip(), "round_index": current_round})

        log.debug("Chunked by rounds | num_chunks=%d | rounds=%s",
                  len(chunks), [c["round_index"] for c in chunks])
        return chunks

    # ------------------------------------------------------------------
    # Store chunks
    # ------------------------------------------------------------------

    def store_chunks(
        self,
        session_id: str,
        document_type: str,
        text: str,
        role: Optional[str] = None,
        company: Optional[str] = None,
    ) -> None:
        """
        Parse text into chunks, embed, and store in the session collection.
        Document types: resume | jd | company_research | rounds | strategy | questions | behavioral | technical
        """
        if not text:
            log.warning("store_chunks called with empty text | document_type=%s | session_id=%s",
                        document_type, session_id)
            return

        log.info(
            "Storing chunks | session_id=%s | document_type=%s | text_length=%d | role=%s | company=%s",
            session_id, document_type, len(text), role, company,
        )

        collection = self._get_or_create_collection(session_id)

        # Choose chunking strategy based on document type
        if document_type == "resume":
            # Try section-based chunking first (works when storing the LLM analysis output,
            # which uses **Section Name** markdown headers).
            raw_chunks = self._chunk_by_section(
                text,
                ["Candidate Name", "Experience Level", "Current/Latest Role",
                 "Top Skills", "Key Projects", "Education", "Strengths for Interviews", "Potential Gaps"],
            )
            if len(raw_chunks) <= 1:
                # Section headers not found — fall back to sliding window (raw resume text)
                log.debug(
                    "resume section chunking yielded %d chunks — falling back to sliding window",
                    len(raw_chunks),
                )
                sw = self._chunk_sliding_window(text, window_tokens=400, overlap_tokens=50)
                chunks_to_store = [{"text": c, "chunk_index": i} for i, c in enumerate(sw)]
            else:
                chunks_to_store = [{"text": c["text"], "chunk_index": i, "section": c["section"]}
                                   for i, c in enumerate(raw_chunks)]

        elif document_type == "jd":
            raw_chunks = self._chunk_by_section(
                text,
                ["Company Name", "Role Title", "Experience Level", "Required Skills",
                 "Nice-to-Have Skills", "Key Responsibilities", "Interview Focus Areas"],
            )
            if len(raw_chunks) <= 1:
                log.debug(
                    "jd section chunking yielded %d chunks — falling back to sliding window",
                    len(raw_chunks),
                )
                sw = self._chunk_sliding_window(text, window_tokens=400, overlap_tokens=50)
                chunks_to_store = [{"text": c, "chunk_index": i} for i, c in enumerate(sw)]
            else:
                chunks_to_store = [{"text": c["text"], "chunk_index": i, "section": c["section"]}
                                   for i, c in enumerate(raw_chunks)]

        elif document_type == "rounds":
            raw_chunks = self._chunk_by_rounds(text)
            chunks_to_store = raw_chunks

        elif document_type in ("company_research", "strategy", "questions", "behavioral", "technical", "seniority", "resume_improve", "salary"):
            raw_chunks = self._chunk_sliding_window(text, window_tokens=400, overlap_tokens=50)
            chunks_to_store = [{"text": c, "chunk_index": i} for i, c in enumerate(raw_chunks)]

        else:
            log.warning("Unknown document_type=%s | storing entire text as single chunk", document_type)
            chunks_to_store = [{"text": text, "chunk_index": 0}]

        # Add chunks to collection
        for i, chunk_dict in enumerate(chunks_to_store):
            chunk_text = chunk_dict["text"]
            metadata = {
                "session_id":    session_id,
                "document_type": document_type,
                "chunk_index":   str(chunk_dict.get("chunk_index", i)),
            }
            if role:
                metadata["role"] = role
            if company:
                metadata["company"] = company
            if "section" in chunk_dict:
                metadata["section"] = chunk_dict["section"]
            if "round_index" in chunk_dict:
                metadata["round_index"] = str(chunk_dict["round_index"])

            doc_id = f"{document_type}_{chunk_dict.get('chunk_index', i)}_{i}"

            try:
                collection.add(
                    ids=[doc_id],
                    documents=[chunk_text],
                    metadatas=[metadata],
                )
                log.debug(
                    "Chunk stored | document_type=%s | chunk_index=%d | text_length=%d | doc_id=%s",
                    document_type, chunk_dict.get("chunk_index", i), len(chunk_text), doc_id,
                )
            except Exception as exc:
                log.error("Failed to store chunk | doc_id=%s | error=%s", doc_id, exc, exc_info=True)

        log.info(
            "Chunks stored complete | document_type=%s | total_chunks=%d | session_id=%s",
            document_type, len(chunks_to_store), session_id,
        )

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def query(self, session_id: str, query_text: str, top_k: int = 5) -> list[dict]:
        """
        Embed query and retrieve top-k most similar chunks from the session collection.
        Returns list of dicts: [{"text": chunk_text, "metadata": {...}, "distance": score}, ...]
        """
        if not query_text:
            log.warning("query called with empty query_text | session_id=%s", session_id)
            return []

        try:
            collection = self.client.get_collection(name=f"session_{session_id}")
        except Exception as exc:
            log.warning("Collection not found | session_id=%s | error=%s", session_id, exc)
            return []

        log.debug("Querying vectors | session_id=%s | query='%s' | top_k=%d",
                  session_id, query_text[:100], top_k)

        try:
            results = collection.query(
                query_texts=[query_text],
                n_results=top_k,
            )

            chunks: list[dict] = []
            if results and results["documents"] and len(results["documents"]) > 0:
                for doc, metadata, distance in zip(
                    results["documents"][0],
                    results["metadatas"][0],
                    results["distances"][0],
                ):
                    chunks.append({
                        "text":     doc,
                        "metadata": metadata,
                        "distance": distance,
                    })

            log.info(
                "Query result | session_id=%s | query_len=%d | retrieved=%d | top_distance=%.3f",
                session_id, len(query_text), len(chunks),
                chunks[0]["distance"] if chunks else 999,
            )
            return chunks

        except Exception as exc:
            log.error("Query failed | session_id=%s | error=%s", session_id, exc, exc_info=True)
            return []

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete_session(self, session_id: str) -> None:
        """Delete all vectors for a session."""
        collection_name = f"session_{session_id}"
        try:
            self.client.delete_collection(name=collection_name)
            log.info("Session collection deleted | session_id=%s", session_id)
        except Exception as exc:
            log.warning("Failed to delete session collection | session_id=%s | error=%s", session_id, exc)
