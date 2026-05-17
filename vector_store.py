"""
vector_store.py
---------------
ChromaDB-backed vector store for job and resume embeddings.
Enables semantic job search and persistent embedding cache.
"""
import logging
import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
from pathlib import Path

logger = logging.getLogger(__name__)

_DB_DIR = Path(__file__).parent / "chroma_db"
_DB_DIR.mkdir(exist_ok=True)

_EMBED_FN = SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")

_client = chromadb.PersistentClient(path=str(_DB_DIR))

_jobs_col = _client.get_or_create_collection(
    name="jobs",
    embedding_function=_EMBED_FN,
    metadata={"hnsw:space": "cosine"},
)
_resumes_col = _client.get_or_create_collection(
    name="resumes",
    embedding_function=_EMBED_FN,
    metadata={"hnsw:space": "cosine"},
)


# ── Job indexing ──────────────────────────────────────────────────

def index_job(job_id: str, title: str, company: str, description: str,
              source: str = "", location: str = "") -> None:
    """Upsert a job into the vector store. Safe to call repeatedly."""
    if not description.strip():
        return
    try:
        _jobs_col.upsert(
            ids=[job_id],
            documents=[description[:4000]],
            metadatas=[{"title": title, "company": company,
                        "source": source, "location": location}],
        )
    except Exception as e:
        logger.warning("vector_store.index_job failed for %s: %s", job_id, e)


def search_jobs(query: str, n_results: int = 10) -> list[dict]:
    """Semantic search over indexed jobs. Returns list of {job_id, title, company, score}."""
    if not query.strip():
        return []
    count = _jobs_col.count()
    if count == 0:
        return []
    try:
        res = _jobs_col.query(
            query_texts=[query[:2000]],
            n_results=min(n_results, count),
            include=["metadatas", "distances"],
        )
        results = []
        for i, job_id in enumerate(res["ids"][0]):
            meta = res["metadatas"][0][i]
            distance = res["distances"][0][i]
            similarity = round((1 - distance) * 100, 1)
            results.append({
                "job_id": job_id,
                "title": meta.get("title", ""),
                "company": meta.get("company", ""),
                "location": meta.get("location", ""),
                "score": similarity,
            })
        return results
    except Exception as e:
        logger.warning("vector_store.search_jobs failed: %s", e)
        return []


def get_similar_jobs(job_id: str, n_results: int = 5) -> list[dict]:
    """Find jobs similar to a given job_id."""
    count = _jobs_col.count()
    if count == 0:
        return []
    try:
        existing = _jobs_col.get(ids=[job_id], include=["documents"])
        if not existing["documents"]:
            return []
        doc = existing["documents"][0]
        res = _jobs_col.query(
            query_texts=[doc],
            n_results=min(n_results + 1, count),
            include=["metadatas", "distances"],
        )
        results = []
        for i, rid in enumerate(res["ids"][0]):
            if rid == job_id:
                continue
            meta = res["metadatas"][0][i]
            distance = res["distances"][0][i]
            results.append({
                "job_id": rid,
                "title": meta.get("title", ""),
                "company": meta.get("company", ""),
                "score": round((1 - distance) * 100, 1),
            })
        return results[:n_results]
    except Exception as e:
        logger.warning("vector_store.get_similar_jobs failed for %s: %s", job_id, e)
        return []


# ── Resume indexing ───────────────────────────────────────────────

def index_resume(user_id: int, resume_text: str, name: str = "") -> None:
    """Upsert a user's resume text for similarity queries."""
    if not resume_text.strip():
        return
    try:
        _resumes_col.upsert(
            ids=[str(user_id)],
            documents=[resume_text[:5000]],
            metadatas=[{"name": name}],
        )
    except Exception as e:
        logger.warning("vector_store.index_resume failed for user %s: %s", user_id, e)


def find_matching_jobs_for_resume(user_id: int, n_results: int = 10) -> list[dict]:
    """Find jobs semantically matching a stored resume."""
    if _jobs_col.count() == 0:
        return []
    try:
        existing = _resumes_col.get(ids=[str(user_id)], include=["documents"])
        if not existing["documents"]:
            return []
        resume_text = existing["documents"][0]
        return search_jobs(resume_text, n_results=n_results)
    except Exception as e:
        logger.warning("vector_store.find_matching_jobs_for_resume failed for user %s: %s", user_id, e)
        return []


# ── Stats ─────────────────────────────────────────────────────────

def store_stats() -> dict:
    try:
        return {
            "jobs_indexed": _jobs_col.count(),
            "resumes_indexed": _resumes_col.count(),
        }
    except Exception:
        return {"jobs_indexed": 0, "resumes_indexed": 0}
