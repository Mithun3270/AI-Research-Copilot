import os
import re
import json
import pickle
import logging
import base64
from pathlib import Path
from typing import List, Dict, Any, Optional

import pymupdf as fitz  # PyMuPDF
import numpy as np
import pandas as pd
import faiss
import requests
from sentence_transformers import SentenceTransformer

from .config import settings
from .database import SessionLocal, init_db
from .models import IndexedPaper, ResearchCategory

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("ResearchCopilot")


class ResearchCopilot:
    """
    Core AI engine for AI Research Copilot.
    Handles embedding generation, FAISS semantic search, dynamic document indexing,
    Ollama LLM interactions, and academic analytical modules.
    """

    CATEGORY_ALIASES = {
        "internet of things": "IoT",
        "iot": "IoT",
        "artificial intelligence": "AI",
        "ai": "AI",
        "machine learning": "Machine Learning",
        "ml": "Machine Learning",
        "cloud services": "Cloud Computing",
        "cloud-based computing": "Cloud Computing",
        "edge cloud computing": "Edge Computing",
        "edge-cloud computing": "Edge Computing",
        "wireless sensor network": "Wireless Sensor Networks",
        "wireless sensor networks": "Wireless Sensor Networks",
        "wsn": "Wireless Sensor Networks",
        "healthcare": "Healthcare",
    }

    def __init__(
        self,
        base_dir: Optional[str] = None,
        embedding_model_dir: Optional[str] = None,
        index_file: Optional[str] = None,
        chunks_file: Optional[str] = None,
        papers_dir: Optional[str] = None,
        ollama_url: str = "http://localhost:11434/api/generate",
        ollama_model: str = "qwen2.5:3b",
    ):
        # Resolve base directory (default to project root if called from backend/)
        current_dir = Path(__file__).resolve().parent
        if (current_dir / "research_copilot.py").exists() and current_dir.name == "backend":
            self.root_dir = current_dir.parent
        else:
            self.root_dir = current_dir

        if base_dir:
            self.root_dir = Path(base_dir).resolve()

        # Component paths
        self.model_dir = Path(embedding_model_dir) if embedding_model_dir else self.root_dir / "model" / "embedding_model"
        self.index_path = Path(index_file) if index_file else self.root_dir / "vector_db" / "research.index"
        self.chunks_path = Path(chunks_file) if chunks_file else self.root_dir / "vector_db" / "chunks.pkl"
        self.papers_dir = Path(papers_dir) if papers_dir else self.root_dir / "research_papers"
        self.extracted_dir = self.root_dir / "extracted_text"
        self.outputs_dir = self.root_dir / "outputs"

        # Ensure directories exist
        self.papers_dir.mkdir(parents=True, exist_ok=True)
        self.extracted_dir.mkdir(parents=True, exist_ok=True)
        self.outputs_dir.mkdir(parents=True, exist_ok=True)
        self.index_path.parent.mkdir(parents=True, exist_ok=True)

        self.ollama_url = ollama_url
        self.ollama_model = ollama_model
        self.embedding_dim = 384  # MiniLM-L6-v2 dimension
        self.category_similarity_threshold = settings.CATEGORY_SIMILARITY_THRESHOLD
        if not 0.0 <= self.category_similarity_threshold <= 1.0:
            raise ValueError("CATEGORY_SIMILARITY_THRESHOLD must be between 0.0 and 1.0.")
        self.rag_min_cosine_similarity = float(os.getenv("RAG_MIN_COSINE_SIMILARITY", "0.30"))
        if not 0.0 <= self.rag_min_cosine_similarity <= 1.0:
            raise ValueError("RAG_MIN_COSINE_SIMILARITY must be between 0.0 and 1.0.")
        self._paper_embeddings: Dict[str, np.ndarray] = {}
        self._category_centroids: Dict[str, np.ndarray] = {}

        # Load AI models and vector DB
        self._load_embedding_model()
        self._load_vector_db()
        init_db()
        self._refresh_category_state()
        self._persist_category_database()

    def _load_embedding_model(self):
        """Loads the SentenceTransformer embedding model from the local model folder."""
        logger.info(f"Loading embedding model from {self.model_dir}...")
        if self.model_dir.exists():
            self.embedding_model = SentenceTransformer(str(self.model_dir))
        else:
            logger.warning(f"Local model path {self.model_dir} not found! Falling back to sentence-transformers/all-MiniLM-L6-v2")
            self.embedding_model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
        logger.info("Embedding model loaded successfully.")

    def _load_vector_db(self):
        """Loads FAISS index and chunks DataFrame from disk."""
        if self.index_path.exists() and self.chunks_path.exists():
            logger.info(f"Loading FAISS index from {self.index_path}...")
            self.index = faiss.read_index(str(self.index_path))
            with open(self.chunks_path, "rb") as f:
                self.chunks_df = pickle.load(f)
            logger.info(f"FAISS index loaded. Total vectors: {self.index.ntotal}, Chunks: {len(self.chunks_df)}")
        else:
            logger.warning("FAISS index or chunks.pkl not found. Initializing empty vector database.")
            self.index = faiss.IndexFlatIP(self.embedding_dim)
            self.chunks_df = pd.DataFrame(columns=[
                "source", "page", "text", "sector", "category", "classification_text",
            ])
            self._persist_vector_db()

        if "sector" not in self.chunks_df.columns:
            self.chunks_df["sector"] = "Other"
        if "category" not in self.chunks_df.columns:
            self.chunks_df["category"] = self.chunks_df["sector"]
        if "classification_text" not in self.chunks_df.columns:
            self.chunks_df["classification_text"] = ""

        metadata_updated = False
        for name, group in self.chunks_df.groupby("source"):
            values = group["category"].dropna().astype(str).unique()
            legacy_values = group["sector"].dropna().astype(str).unique()
            stored = values[0] if len(values) == 1 else legacy_values[0] if len(legacy_values) == 1 else "Other"
            normalized = self._normalize_category_name(stored)
            paper_mask = self.chunks_df["source"] == name
            if not (group["category"] == normalized).all() or not (group["sector"] == normalized).all():
                self.chunks_df.loc[paper_mask, "category"] = normalized
                self.chunks_df.loc[paper_mask, "sector"] = normalized
                metadata_updated = True
            stored_texts = (
                group["classification_text"].dropna().astype(str).str.strip().tolist()
            )
            if not any(stored_texts):
                fallback = self._build_classification_text(str(name), group["text"].astype(str).tolist())
                self.chunks_df.loc[paper_mask, "classification_text"] = fallback
                metadata_updated = True

        if metadata_updated:
            self._persist_chunks_metadata()

    def _persist_vector_db(self):
        """Saves current FAISS index and chunks DataFrame to disk."""
        faiss.write_index(self.index, str(self.index_path))
        self._persist_chunks_metadata()

    def _persist_chunks_metadata(self):
        """Saves chunk metadata without rewriting the FAISS index."""
        with open(self.chunks_path, "wb") as f:
            pickle.dump(self.chunks_df, f)
        logger.info("Chunk metadata persisted successfully.")

    # -------------------------------------------------------------
    # LLM Interaction
    # -------------------------------------------------------------
    def check_ollama(self) -> Dict[str, Any]:
        """Checks if local Ollama service is reachable and model is available."""
        try:
            # Check tags / available models
            tags_url = self.ollama_url.replace("/api/generate", "/api/tags")
            resp = requests.get(tags_url, timeout=5)
            if resp.status_code == 200:
                models = [m.get("name") for m in resp.json().get("models", [])]
                model_ready = any(self.ollama_model in m for m in models)
                return {
                    "online": True,
                    "model_available": model_ready,
                    "model": self.ollama_model,
                    "available_models": models,
                }
            return {"online": True, "model_available": False, "model": self.ollama_model}
        except Exception as e:
            return {"online": False, "model_available": False, "error": str(e)}

    def ask_llm(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        timeout: int = 120,
        response_format: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Sends prompt to local Ollama instance running qwen2.5:3b."""
        full_prompt = prompt
        if system_prompt:
            full_prompt = f"System: {system_prompt}\n\nUser: {prompt}"

        payload = {
            "model": self.ollama_model,
            "prompt": full_prompt,
            "stream": False,
        }
        if response_format:
            payload["format"] = response_format
            if response_format == "json":
                payload["options"] = {"temperature": 0, **(options or {})}
        elif options:
            payload["options"] = options

        try:
            response = requests.post(self.ollama_url, json=payload, timeout=timeout)
            response.raise_for_status()
            data = response.json()
            return data.get("response", "").strip()
        except requests.exceptions.ConnectionError:
            raise RuntimeError(
                f"Cannot connect to Ollama at {self.ollama_url}. Please ensure Ollama is running (`ollama serve`)."
            )
        except requests.exceptions.Timeout:
            raise RuntimeError(f"Ollama request timed out after {timeout} seconds.")
        except Exception as e:
            raise RuntimeError(f"Ollama generation failed: {str(e)}")

    @classmethod
    def _normalize_category_name(cls, name: str) -> str:
        cleaned = re.sub(r"\s+", " ", name.strip(" \t\r\n\"'`.,;:"))
        if not cleaned:
            raise ValueError("Category name cannot be empty.")
        if len(cleaned) > 150:
            raise ValueError("Category names must be 150 characters or fewer.")
        alias = cls.CATEGORY_ALIASES.get(cleaned.casefold())
        return alias or cleaned.title()

    def _build_classification_text(self, paper_name: str, text_blocks: List[str]) -> str:
        """Extract title, abstract, keywords, and introduction from the opening pages."""
        opening_text = "\n".join(text_blocks[:5])[:24000]
        lines = [line.strip() for line in opening_text.splitlines() if line.strip()]
        title = lines[0] if lines else Path(paper_name).stem.replace("_", " ")

        abstract_match = re.search(
            r"\babstract\b\s*[:.\-]?\s*(.*?)(?=\b(?:keywords?|index terms?)\b|"
            r"\b(?:\d+\.?\s*)?introduction\b|$)",
            opening_text,
            re.IGNORECASE | re.DOTALL,
        )
        keywords_match = re.search(
            r"\b(?:keywords?|index terms?)\b\s*[:.\-]?\s*(.*?)(?=\n|"
            r"\b(?:\d+\.?\s*)?introduction\b|$)",
            opening_text,
            re.IGNORECASE | re.DOTALL,
        )
        introduction_match = re.search(
            r"\b(?:\d+\.?\s*)?introduction\b\s*(.*)",
            opening_text,
            re.IGNORECASE | re.DOTALL,
        )

        abstract = abstract_match.group(1).strip() if abstract_match else ""
        keywords = keywords_match.group(1).strip() if keywords_match else ""
        introduction = introduction_match.group(1).strip()[:5000] if introduction_match else ""
        if not abstract and not introduction:
            introduction = opening_text[:5000]

        return "\n".join(
            section for section in (
                f"Title: {title}",
                f"Abstract: {abstract}" if abstract else "",
                f"Keywords: {keywords}" if keywords else "",
                f"Introduction: {introduction}" if introduction else "",
            ) if section
        )

    def _refresh_category_state(self) -> None:
        """Rebuild paper embeddings and category centroids from indexed paper metadata."""
        self._paper_embeddings = {}
        self._category_centroids = {}
        if self.chunks_df.empty:
            return

        papers = []
        for name, group in self.chunks_df.groupby("source"):
            values = group["classification_text"].dropna().astype(str).str.strip()
            text = next((value for value in values if value), "")
            if not text:
                text = self._build_classification_text(str(name), group["text"].astype(str).tolist())
            category_values = group["category"].dropna().astype(str).unique()
            category = self._normalize_category_name(category_values[0] if len(category_values) else "Other")
            papers.append((str(name), category, text))

        embeddings = self.embedding_model.encode(
            [paper[2] for paper in papers],
            batch_size=32,
            show_progress_bar=False,
            convert_to_numpy=True,
        ).astype(np.float32)
        faiss.normalize_L2(embeddings)

        category_vectors: Dict[str, List[np.ndarray]] = {}
        for (name, category, _), embedding in zip(papers, embeddings):
            self._paper_embeddings[name] = embedding
            category_vectors.setdefault(category, []).append(embedding)
        for category, vectors in category_vectors.items():
            centroid = np.mean(vectors, axis=0, dtype=np.float32).reshape(1, -1)
            faiss.normalize_L2(centroid)
            self._category_centroids[category] = centroid[0]

    def _persist_category_database(self) -> None:
        """Synchronize per-paper categories and computed centroids into SQLite."""
        session = SessionLocal()
        try:
            paper_names = set()
            category_counts: Dict[str, int] = {}
            for name, group in self.chunks_df.groupby("source"):
                paper_name = str(name)
                paper_names.add(paper_name)
                category_values = group["category"].dropna().astype(str).unique()
                category = self._normalize_category_name(category_values[0] if len(category_values) else "Other")
                texts = group["classification_text"].dropna().astype(str).str.strip()
                classification_text = next(
                    (text for text in texts if text),
                    self._build_classification_text(paper_name, group["text"].astype(str).tolist()),
                )
                record = session.get(IndexedPaper, paper_name)
                if record is None:
                    record = IndexedPaper(filename=paper_name, category=category)
                    session.add(record)
                record.category = category
                record.classification_text = classification_text
                record.page_count = int(group["page"].max()) if not group.empty else 0
                category_counts[category] = category_counts.get(category, 0) + 1

            for record in session.query(IndexedPaper).all():
                if record.filename not in paper_names:
                    session.delete(record)

            for category, centroid in self._category_centroids.items():
                record = session.get(ResearchCategory, category)
                if record is None:
                    record = ResearchCategory(name=category)
                    session.add(record)
                record.centroid_json = json.dumps(centroid.tolist())
                record.paper_count = category_counts.get(category, 0)

            for record in session.query(ResearchCategory).all():
                if record.name not in self._category_centroids:
                    session.delete(record)
            session.commit()
        except Exception:
            session.rollback()
            logger.exception("Failed to synchronize category metadata with the database.")
            raise
        finally:
            session.close()

    def _category_centroids_without(self, excluded_papers: Optional[set] = None) -> Dict[str, np.ndarray]:
        excluded = excluded_papers or set()
        category_vectors: Dict[str, List[np.ndarray]] = {}
        for name, group in self.chunks_df.groupby("source"):
            if str(name) in excluded or str(name) not in self._paper_embeddings:
                continue
            values = group["category"].dropna().astype(str).unique()
            category = self._normalize_category_name(values[0] if len(values) else "Other")
            category_vectors.setdefault(category, []).append(self._paper_embeddings[str(name)])

        centroids = {}
        for category, vectors in category_vectors.items():
            centroid = np.mean(vectors, axis=0, dtype=np.float32).reshape(1, -1)
            faiss.normalize_L2(centroid)
            centroids[category] = centroid[0]
        return centroids

    def _propose_category(self, paper_name: str, classification_text: str) -> str:
        prompt = (
            "Identify the single primary research domain of this paper. Propose a concise category "
            "name of 1 to 4 words (examples: Cloud Computing, Edge Computing, Blockchain). "
            "Do not use a broad generic label such as Technology or Research. Return only the category name.\n\n"
            f"Filename: {paper_name}\n"
            f"Paper title, abstract, keywords, and introduction:\n{classification_text[:7000]}"
        )
        response = self.ask_llm(prompt, timeout=120)
        proposed = re.sub(r"^[\s\d.)-]+", "", response.splitlines()[0]).strip()
        proposed = re.sub(r"[^A-Za-z0-9&+ ._-]", "", proposed)
        if not proposed or len(proposed.split()) > 4:
            raise RuntimeError(f"Ollama returned an invalid category name for {paper_name}: {response!r}")
        category = self._normalize_category_name(proposed)
        logger.info("LLM proposed new research category %r for %s.", category, paper_name)
        return category

    def _classify_paper_category(
        self,
        paper_name: str,
        classification_text: str,
        excluded_papers: Optional[set] = None,
    ) -> str:
        """Assigns content to a category using centroid cosine similarity, then Ollama."""
        embedding = self.embedding_model.encode(
            [classification_text], convert_to_numpy=True
        ).astype(np.float32)
        faiss.normalize_L2(embedding)
        centroids = self._category_centroids_without(excluded_papers)
        scores = {
            category: float(np.dot(embedding[0], centroid))
            for category, centroid in centroids.items()
        }
        for category, score in sorted(scores.items()):
            logger.info(
                "Category similarity for %s: %s=%.4f (threshold=%.2f)",
                paper_name,
                category,
                score,
                self.category_similarity_threshold,
            )

        if scores:
            best_category, best_score = max(scores.items(), key=lambda item: item[1])
            logger.info(
                "Best category for %s: %s=%.4f",
                paper_name,
                best_category,
                best_score,
            )
            if best_score >= self.category_similarity_threshold:
                return best_category

        return self._propose_category(paper_name, classification_text)

    # -------------------------------------------------------------
    # Semantic Search & Retrieval
    # -------------------------------------------------------------
    def search(
        self,
        query: str,
        top_k: int = 6,
        paper_filter: Optional[List[str]] = None,
        score_threshold: float = 0.0,
        category_filter: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Performs semantic vector search on FAISS using normalized cosine similarity.
        Optionally filters results to a specific subset of papers and score threshold.
        """
        if self.index.ntotal == 0 or len(self.chunks_df) == 0:
            return []

        # Generate and normalize query embedding
        query_emb = self.embedding_model.encode([query], convert_to_numpy=True).astype(np.float32)
        faiss.normalize_L2(query_emb)

        # Category filtering happens after FAISS retrieval, so retrieve enough candidates.
        fetch_k = self.index.ntotal if paper_filter or category_filter else min(self.index.ntotal, top_k)
        scores, indices = self.index.search(query_emb, fetch_k)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx == -1 or idx >= len(self.chunks_df):
                continue

            similarity = float(score)
            if similarity < score_threshold:
                continue

            row = self.chunks_df.iloc[idx]
            paper_name = row["source"]

            if paper_filter and paper_name not in paper_filter:
                continue
            row_category = str(row.get("category", row.get("sector", "Other")))
            if category_filter and row_category not in category_filter:
                continue

            results.append({
                "paper": paper_name,
                "page": int(row["page"]),
                "score": round(similarity, 4),
                "text": str(row["text"]).strip(),
                "category": row_category,
            })

            if len(results) >= top_k:
                break

        return results

    def search_specific_paper(self, paper_name: str, query: str, top_k: int = 6) -> List[Dict[str, Any]]:
        """Searches within a single specific paper."""
        return self.search(query=query, top_k=top_k, paper_filter=[paper_name])

    # -------------------------------------------------------------
    # RAG Question Answering
    # -------------------------------------------------------------
    def ask(
        self,
        question: str,
        top_k: int = 6,
        paper_filter: Optional[List[str]] = None,
        category_filter: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Retrieval-Augmented Generation (RAG) question answering.
        Retrieves context, formats prompt, queries LLM, and attaches citations.
        """
        chunks = self.search(
            query=question,
            top_k=top_k,
            paper_filter=paper_filter,
            category_filter=category_filter,
        )

        if not chunks or max(chunk["score"] for chunk in chunks) < self.rag_min_cosine_similarity:
            return {
                "answer": "Not found in your indexed papers",
                "sources": [],
            }

        context_parts = []
        for i, c in enumerate(chunks, start=1):
            context_parts.append(
                f"[S{i} | Paper: {c['paper']} | Page: {c['page']}]\n{c['text']}"
            )
        context_str = "\n\n---\n\n".join(context_parts)

        system_instruction = (
            "You are an AI Research Copilot. Answer using only the supplied research-paper context.\n"
            "Strict Rules:\n"
            "1. Never use outside knowledge or infer facts absent from the context.\n"
            "2. If the context does not answer the question, return found=false and an empty answer.\n"
            "3. Cite every factual statement using one or more exact source IDs such as [S1].\n"
            "4. Return only a JSON object with keys found (boolean) and answer (string)."
        )

        prompt = (
            f"Context from indexed research papers:\n"
            f"====================================\n"
            f"{context_str}\n"
            f"====================================\n\n"
            f"Question: {question}\n"
            f"Return a JSON object only. If the context does not support an answer, use "
            f'{{"found": false, "answer": ""}}.'
        )

        response = self.ask_llm(prompt=prompt, system_prompt=system_instruction, response_format="json")
        try:
            parsed = json.loads(response)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Ollama returned an invalid grounded-answer response: {exc}") from exc

        if not isinstance(parsed, dict) or not parsed.get("found") or not isinstance(parsed.get("answer"), str):
            return {"answer": "Not found in your indexed papers", "sources": []}

        source_ids = {
            int(value)
            for value in re.findall(r"\[S(\d+)\]", parsed["answer"])
        }
        source_ids = {value for value in source_ids if 1 <= value <= len(chunks)}
        answer = parsed["answer"].strip()
        answer = re.sub(
            r"\[S(\d+)\]",
            lambda match: (
                f"[{chunks[int(match.group(1)) - 1]['paper']}, "
                f"p. {chunks[int(match.group(1)) - 1]['page']}]"
                if int(match.group(1)) in source_ids else ""
            ),
            answer,
        )
        cited_chunks = [chunk for source_id, chunk in enumerate(chunks, start=1) if source_id in source_ids]
        if not answer:
            return {"answer": "Not found in your indexed papers", "sources": []}
        if not cited_chunks:
            cited_chunks = chunks

        valid_citations = " ".join(
            f"[{chunk['paper']}, p. {chunk['page']}]" for chunk in cited_chunks
        )
        if not source_ids:
            answer = f"{answer}\n\nSources: {valid_citations}"

        return {
            "answer": answer,
            "sources": [
                {
                    "paper": c["paper"],
                    "page": c["page"],
                    "score": c["score"],
                    "text_snippet": c["text"][:700],
                }
                for c in cited_chunks
            ],
        }

    # -------------------------------------------------------------
    # Dynamic Indexing (PDF Upload & Processing)
    # -------------------------------------------------------------
    def clean_text(self, text: str) -> str:
        """Cleans extracted PDF text while preserving sentence structure."""
        text = re.sub(r"\x00", "", text)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n\s*\n+", "\n\n", text)
        return text.strip()

    def chunk_paper_pages(
        self,
        pages_text: List[Dict[str, Any]],
        chunk_size: int = 500,
        overlap: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Splits extracted pages into ~500 word chunks with ~100 word overlap.
        Preserves paper filename and page number metadata.
        """
        chunks = []
        for page_info in pages_text:
            source = page_info["source"]
            page_num = page_info["page"]
            text = page_info["text"]

            words = text.split()
            if not words:
                continue

            if len(words) <= chunk_size:
                chunks.append({"source": source, "page": page_num, "text": text})
            else:
                start = 0
                step = chunk_size - overlap
                while start < len(words):
                    chunk_words = words[start : start + chunk_size]
                    chunk_text = " ".join(chunk_words)
                    chunks.append({"source": source, "page": page_num, "text": chunk_text})
                    if start + chunk_size >= len(words):
                        break
                    start += step

        return chunks

    def add_paper(
        self,
        pdf_path: str,
        filename: Optional[str] = None,
        category_override: Optional[str] = None,
        chunk_size: int = 500,
        overlap: int = 100,
    ) -> Dict[str, Any]:
        """
        Extracts, chunks, embeds, and indexes a new PDF dynamically into FAISS.
        No server restart is required.
        """
        path = Path(pdf_path)
        paper_name = filename or path.name

        if not path.exists():
            raise FileNotFoundError(f"PDF file not found at {path}")

        logger.info(f"Processing PDF: {paper_name}")
        doc = fitz.open(str(path))
        total_pages = len(doc)

        if total_pages == 0:
            doc.close()
            raise ValueError(f"The PDF {paper_name} contains no pages.")

        pages_data = []
        total_chars = 0
        for page_idx in range(total_pages):
            page = doc[page_idx]
            raw_text = page.get_text("text")
            cleaned = self.clean_text(raw_text)
            total_chars += len(cleaned)
            if cleaned:
                pages_data.append({
                    "source": paper_name,
                    "page": page_idx + 1,
                    "text": cleaned,
                })
        doc.close()

        if total_chars < 50:
            raise ValueError(
                f"The PDF '{paper_name}' appears to be empty or image-only/scanned with no extractable text."
            )

        if chunk_size <= overlap or overlap < 0:
            raise ValueError("Chunk size must be greater than the non-negative overlap.")

        # Chunk the text
        new_chunks = self.chunk_paper_pages(
            pages_data,
            chunk_size=chunk_size,
            overlap=overlap,
        )
        if not new_chunks:
            raise ValueError(f"Could not generate text chunks from {paper_name}.")

        classification_text = self._build_classification_text(
            paper_name,
            [page["text"] for page in pages_data],
        )
        category = (
            self._classify_paper_category(
                paper_name,
                classification_text,
                excluded_papers={paper_name},
            )
            if category_override is None
            else self._normalize_category_name(category_override)
        )

        logger.info(f"Generated {len(new_chunks)} chunks for {paper_name}. Generating embeddings...")

        # If paper was already in index, remove its old chunks first to prevent duplicates
        if not self.chunks_df.empty and (self.chunks_df["source"] == paper_name).any():
            logger.info(f"Paper {paper_name} already exists. Removing old chunks prior to re-indexing.")
            self.delete_paper(paper_name, delete_file=False)

        # Embed new chunks
        chunk_texts = [c["text"] for c in new_chunks]
        embeddings = self.embedding_model.encode(
            chunk_texts, batch_size=32, show_progress_bar=False, convert_to_numpy=True
        ).astype(np.float32)

        # Normalize for cosine similarity
        faiss.normalize_L2(embeddings)

        # Add to FAISS index
        self.index.add(embeddings)

        # Append to metadata DataFrame
        new_df = pd.DataFrame(new_chunks)
        new_df["sector"] = category
        new_df["category"] = category
        new_df["classification_text"] = classification_text
        self.chunks_df = pd.concat([self.chunks_df, new_df], ignore_index=True)

        # Persist updated index and metadata
        self._persist_vector_db()
        self._refresh_category_state()
        self._persist_category_database()

        logger.info(f"Successfully indexed {paper_name}: {total_pages} pages, {len(new_chunks)} chunks.")
        return {
            "status": "success",
            "paper": paper_name,
            "sector": category,
            "category": category,
            "pages": total_pages,
            "chunks_added": len(new_chunks),
            "total_indexed_chunks": len(self.chunks_df),
        }

    def delete_paper(self, paper_name: str, delete_file: bool = True) -> Dict[str, Any]:
        """
        Deletes a paper from the system and safely re-indexes remaining chunks in FAISS
        to guarantee perfect synchronization between FAISS vectors and chunks.pkl.
        """
        logger.info(f"Deleting paper: {paper_name}")

        # Delete physical file
        if delete_file:
            file_path = self.papers_dir / paper_name
            if file_path.exists():
                try:
                    os.remove(file_path)
                    logger.info(f"Deleted physical file {file_path}")
                except Exception as e:
                    logger.warning(f"Failed to delete physical file {file_path}: {e}")

        # Filter out paper chunks
        initial_chunk_count = len(self.chunks_df)
        remaining_df = self.chunks_df[self.chunks_df["source"] != paper_name].reset_index(drop=True)
        chunks_removed = initial_chunk_count - len(remaining_df)

        self.chunks_df = remaining_df

        # Rebuild FAISS index from remaining chunks
        if len(self.chunks_df) > 0:
            logger.info(f"Rebuilding FAISS index for {len(self.chunks_df)} remaining chunks...")
            all_texts = self.chunks_df["text"].tolist()
            embeddings = self.embedding_model.encode(
                all_texts, batch_size=32, show_progress_bar=False, convert_to_numpy=True
            ).astype(np.float32)
            faiss.normalize_L2(embeddings)

            self.index = faiss.IndexFlatIP(self.embedding_dim)
            self.index.add(embeddings)
        else:
            logger.info("No remaining chunks. Resetting to empty FAISS index.")
            self.index = faiss.IndexFlatIP(self.embedding_dim)

        self._persist_vector_db()
        self._refresh_category_state()
        self._persist_category_database()

        return {
            "status": "success",
            "paper": paper_name,
            "chunks_removed": chunks_removed,
            "remaining_chunks": len(self.chunks_df),
        }

    # -------------------------------------------------------------
    # Metadata & Health
    # -------------------------------------------------------------
    def update_paper_sector(self, paper_name: str, sector: str) -> Dict[str, str]:
        """Updates or creates a category and persists it for every chunk of a paper."""
        category = self._normalize_category_name(sector)

        paper_mask = self.chunks_df["source"] == paper_name
        if not paper_mask.any():
            raise ValueError(f"Paper '{paper_name}' not found in the indexed database.")

        self.chunks_df.loc[paper_mask, "sector"] = category
        self.chunks_df.loc[paper_mask, "category"] = category
        self._persist_chunks_metadata()
        self._refresh_category_state()
        self._persist_category_database()
        return {"paper": paper_name, "sector": category, "category": category}

    def get_paper_sector(self, paper_name: str) -> str:
        """Returns the saved paper category for compatibility with older callers."""
        paper_mask = self.chunks_df["source"] == paper_name
        paper_chunks = self.chunks_df.loc[paper_mask]
        if paper_chunks.empty:
            raise ValueError(f"Paper '{paper_name}' not found in the indexed database.")

        categories = paper_chunks["category"].dropna().astype(str).unique()
        return self._normalize_category_name(categories[0] if len(categories) else "Other")

    def reclassify_all_papers(self) -> List[Dict[str, str]]:
        """Reclassifies every indexed paper and refreshes category centroids."""
        changes = []
        paper_names = sorted(self.chunks_df["source"].dropna().astype(str).unique())
        for paper_name in paper_names:
            paper_mask = self.chunks_df["source"] == paper_name
            group = self.chunks_df.loc[paper_mask]
            texts = group["classification_text"].dropna().astype(str).str.strip()
            classification_text = next(
                (text for text in texts if text),
                self._build_classification_text(paper_name, group["text"].astype(str).tolist()),
            )
            previous_category = self._normalize_category_name(
                str(group["category"].iloc[0]) if "category" in group.columns else "Other"
            )
            category = self._classify_paper_category(
                paper_name,
                classification_text,
                excluded_papers={paper_name},
            )
            self.chunks_df.loc[paper_mask, "category"] = category
            self.chunks_df.loc[paper_mask, "sector"] = category
            self.chunks_df.loc[paper_mask, "classification_text"] = classification_text
            changes.append({
                "paper": paper_name,
                "previous_category": previous_category,
                "category": category,
            })
            self._refresh_category_state()
            logger.info("Reclassified %s: %s -> %s", paper_name, previous_category, category)

        self._persist_vector_db()
        self._persist_category_database()
        return changes

    def get_categories(self) -> List[Dict[str, Any]]:
        category_counts = self.chunks_df.groupby("category")["source"].nunique()
        return [
            {"name": str(name), "paper_count": int(count)}
            for name, count in category_counts.sort_index().items()
        ]

    def get_indexed_papers(self) -> List[Dict[str, Any]]:
        """Returns list of currently indexed papers with chunk counts and disk status."""
        papers = []
        if self.chunks_df.empty:
            return papers

        grouped = self.chunks_df.groupby("source")
        for name, group in grouped:
            pdf_path = self.papers_dir / name
            file_exists = pdf_path.exists()
            file_size = pdf_path.stat().st_size if file_exists else 0
            page_count = int(group["page"].max()) if not group.empty else 0

            papers.append({
                "id": str(name),
                "name": str(name),
                "chunks": int(len(group)),
                "pages": page_count,
                "file_size": file_size,
                "file_size_kb": round(file_size / 1024, 1),
                "file_exists": file_exists,
                "sector": str(group["category"].iloc[0]) if "category" in group.columns else "Other",
                "category": str(group["category"].iloc[0]) if "category" in group.columns else "Other",
            })
        return sorted(papers, key=lambda x: x["name"])

    def get_health(self) -> Dict[str, Any]:
        """Provides status of embedding model, FAISS index, chunk metadata, and Ollama."""
        ollama_status = self.check_ollama()
        papers = self.get_indexed_papers()
        return {
            "status": "ok",
            "embedding_model": {
                "name": "sentence-transformers/all-MiniLM-L6-v2",
                "dimension": self.embedding_dim,
                "loaded": self.embedding_model is not None,
            },
            "vector_database": {
                "type": "faiss.IndexFlatIP",
                "total_vectors": int(self.index.ntotal),
                "total_chunks": int(len(self.chunks_df)),
                "synchronized": int(self.index.ntotal) == int(len(self.chunks_df)),
            },
            "papers_count": len(papers),
            "papers": [p["name"] for p in papers],
            "ollama": ollama_status,
        }

    # -------------------------------------------------------------
    # Specialized Analytical Modules
    # -------------------------------------------------------------
    def _extract_architecture_figure(self, paper_name: str) -> Optional[Dict[str, Any]]:
        pdf_path = self.papers_dir / paper_name
        if not pdf_path.exists():
            return None

        caption_pattern = re.compile(
            r"\b(?:fig(?:ure)?\.?\s*\d+|architecture|system overview|system model|framework|workflow)\b"
            r".{0,140}\b(?:architecture|system overview|system model|framework|workflow|proposed system)\b",
            re.IGNORECASE,
        )
        reverse_pattern = re.compile(
            r"\b(?:architecture|system overview|system model|framework|workflow|proposed system)\b"
            r".{0,140}\b(?:fig(?:ure)?\.?\s*\d+)\b",
            re.IGNORECASE,
        )
        with fitz.open(str(pdf_path)) as document:
            for page_index, page in enumerate(document):
                blocks = page.get_text("blocks")
                captions = [
                    fitz.Rect(block[:4])
                    for block in blocks
                    if isinstance(block[4], str)
                    and (caption_pattern.search(block[4]) or reverse_pattern.search(block[4]))
                ]
                if not captions:
                    continue

                page_area = page.rect.get_area()
                image_rects = [
                    rect for image in page.get_images(full=True)
                    for rect in page.get_image_rects(image[0])
                    if rect.get_area() >= page_area * 0.025
                ]
                candidates = []
                for caption in captions:
                    nearby = [
                        rect for rect in image_rects
                        if rect.y1 <= caption.y0 + page.rect.height * 0.08
                        and caption.y0 - rect.y1 <= page.rect.height * 0.45
                    ]
                    if nearby:
                        candidates.append(max(nearby, key=lambda rect: rect.get_area()))
                    else:
                        candidates.append(fitz.Rect(
                            page.rect.x0,
                            max(page.rect.y0, caption.y0 - page.rect.height * 0.42),
                            page.rect.x1,
                            min(page.rect.y1, caption.y1 + page.rect.height * 0.04),
                        ))

                clip = max(candidates, key=lambda rect: rect.get_area()) & page.rect
                if clip.is_empty:
                    continue
                image = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), clip=clip, alpha=False)
                encoded = base64.b64encode(image.tobytes("png")).decode("ascii")
                return {
                    "kind": "original",
                    "page": page_index + 1,
                    "image_data": f"data:image/png;base64,{encoded}",
                }
        return None

    def generate_architecture_diagram(
        self,
        paper_name: str,
        invalid_mermaid: Optional[str] = None,
    ) -> Dict[str, Any]:
        paper_chunks = self.chunks_df[self.chunks_df["source"] == paper_name]
        if paper_chunks.empty:
            raise ValueError(f"Paper '{paper_name}' not found in the indexed database.")
        excerpts = []
        for _, row in paper_chunks.iterrows():
            if re.search(r"\b(?:method|system|architecture|proposed|design|workflow)\b", str(row["text"]), re.I):
                excerpts.append(f"[Page {int(row['page'])}]\n{row['text']}")
        source_text = "\n\n".join(excerpts)[:24000]
        if not source_text:
            source_text = "\n\n".join(
                f"[Page {int(row['page'])}]\n{row['text']}"
                for _, row in paper_chunks.head(6).iterrows()
            )
        retry_instruction = (
            f"\nThe previous Mermaid was invalid:\n{invalid_mermaid}\nReturn corrected Mermaid syntax."
            if invalid_mermaid else ""
        )
        prompt = (
            f"Create a Mermaid flowchart that represents only the architecture explicitly described in this paper. "
            f"Use 5 to 8 boxes, simple ASCII node IDs, and one arrow per connection. "
            f"Return JSON with keys mermaid (including a flowchart TD header) and steps (an array of 5 to 8 short "
            f"paper-supported steps). Do not add components absent from the text.{retry_instruction}\n\n"
            f"Paper method and architecture excerpts:\n{source_text}"
        )
        response = self.ask_llm(prompt, response_format="json", options={"num_ctx": 8192})
        try:
            result = json.loads(response)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Ollama returned an invalid architecture response: {exc}") from exc
        if not isinstance(result, dict) or not isinstance(result.get("mermaid"), str):
            raise RuntimeError("Ollama did not return a Mermaid architecture diagram.")
        steps = result.get("steps")
        if not isinstance(steps, list):
            steps = []
        steps = [
            re.sub(r"\s+", " ", str(step)).strip().replace('"', "'")
            for step in steps if str(step).strip()
        ][:8]
        if 5 <= len(steps) <= 8:
            nodes = [f'N{index}["{step}"]' for index, step in enumerate(steps, 1)]
            mermaid = "flowchart TD\n  " + "\n  ".join(
                f"{node} --> {nodes[index + 1]}" for index, node in enumerate(nodes[:-1])
            ) + f"\n  {nodes[-1]}"
        else:
            mermaid = result["mermaid"].strip()
        return {
            "kind": "generated",
            "mermaid": mermaid,
            "steps": steps,
        }

    def analyze_paper(self, paper_name: str) -> Dict[str, Any]:
        paper_chunks = self.chunks_df[self.chunks_df["source"] == paper_name].sort_values(
            ["page"], kind="stable"
        )
        if paper_chunks.empty:
            raise ValueError(f"Paper '{paper_name}' not found in the indexed database.")

        fields = {
            "problem_statement": "Problem Statement",
            "proposed_method": "Proposed Method",
            "system_architecture": "System Architecture",
            "mathematical_models": "Mathematical Models",
            "dataset": "Dataset",
            "metrics": "Metrics",
            "results": "Results",
            "strengths": "Strengths",
            "limitations": "Limitations",
            "future_work": "Future Work",
        }
        extracted = {key: [] for key in fields}
        rows = list(paper_chunks.iterrows())
        for start in range(0, len(rows), 4):
            batch = rows[start:start + 4]
            context = "\n\n".join(
                f"[Chunk {start + offset + 1} | Page {int(row['page'])}]\n{row['text']}"
                for offset, (_, row) in enumerate(batch)
            )
            field_list = ", ".join(f'"{key}": "paper-supported text or empty string"' for key in fields)
            prompt = (
                f"Extract facts from this batch of chunks belonging only to the paper '{paper_name}'. "
                f"Return a JSON object with exactly these keys: {field_list}. For each field, give concise "
                f"paper-supported facts and page numbers. Use an empty string if this batch does not mention it. "
                f"Do not infer or add outside facts.\n\nPaper chunks:\n{context}"
            )
            response = self.ask_llm(
                prompt,
                response_format="json",
                options={"num_ctx": 8192},
            )
            try:
                batch_result = json.loads(response)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"Ollama returned invalid analysis JSON: {exc}") from exc
            if not isinstance(batch_result, dict):
                raise RuntimeError("Ollama returned an invalid paper analysis structure.")
            for key in fields:
                value = batch_result.get(key, "")
                if not isinstance(value, str):
                    continue
                value = value.strip()
                if value and value.casefold() not in {"not mentioned in the paper", "not specified"}:
                    if value.casefold() not in {item.casefold() for item in extracted[key]}:
                        extracted[key].append(value)

        analysis = {
            key: "\n\n".join(values) if values else "Not mentioned in the paper"
            for key, values in extracted.items()
        }
        architecture = self._extract_architecture_figure(paper_name)
        if architecture is None:
            architecture = self.generate_architecture_diagram(paper_name)

        return {
            "paper_id": paper_name,
            "paper": paper_name,
            "analysis": analysis,
            "architecture": architecture,
            "total_chunks_analyzed": len(rows),
        }

    def compare_papers(self, paper_names: List[str]) -> Dict[str, Any]:
        if len(set(paper_names)) < 2:
            raise ValueError("Please select at least 2 papers to compare.")

        paper_sectors = {name: self.get_paper_sector(name) for name in paper_names}
        unique_sectors = set(paper_sectors.values())
        if len(unique_sectors) != 1:
            raise ValueError("Selected papers belong to different sectors. Please select papers from the same sector.")
        sector = next(iter(unique_sectors))

        parameters = [
            ("research_problem", "Research Problem", "research problem objective motivation challenge"),
            ("methodology", "Methodology", "methodology approach system architecture procedure"),
            ("dataset", "Dataset", "dataset data source sample benchmark corpus"),
            ("ai_models", "AI Models Used", "artificial intelligence machine learning model algorithm"),
            ("metrics", "Evaluation Metrics", "evaluation metric performance accuracy precision recall"),
            ("key_results", "Key Results", "results findings outcome performance"),
            ("limitations", "Limitations", "limitations weaknesses constraints future work"),
            ("trade_offs", "Trade-offs", "trade-offs advantages disadvantages computational cost"),
        ]
        fields = [key for key, _, _ in parameters]
        max_context_chunks = 6
        max_context_characters = 6000
        ollama_timeout = 120
        ollama_num_predict = 1200
        ollama_num_ctx = 4096

        def parse_json_response(raw_text: str) -> Dict[str, Any]:
            cleaned = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", raw_text.strip(), flags=re.IGNORECASE)
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start >= 0 and end > start:
                cleaned = cleaned[start:end + 1]
            parsed = json.loads(cleaned)
            if not isinstance(parsed, dict):
                raise ValueError("The model response must be a JSON object.")
            return parsed

        def parse_extraction_response(raw_text: str) -> Dict[str, Any]:
            return parse_json_response(raw_text)

        def ollama_call(prompt: str, paper_name: str, json_mode: bool = True) -> Dict[str, Any]:
            payload = {
                "model": self.ollama_model,
                "prompt": prompt,
                "stream": False,
                "format": "json" if json_mode else "",
                "options": {
                    "temperature": 0,
                    "num_ctx": ollama_num_ctx,
                    "num_predict": ollama_num_predict,
                },
                "keep_alive": "10m",
            }
            if json_mode:
                payload["format"] = "json"
            else:
                payload.pop("format")
            try:
                response = requests.post(self.ollama_url, json=payload, timeout=ollama_timeout)
                response.raise_for_status()
                result = response.json()
                result["response"] = str(result.get("response", "")).strip()
                return result
            except requests.exceptions.ConnectionError as exc:
                logger.exception("Ollama connection failure paper=%r raw_output=%r", paper_name, "")
                raise RuntimeError(
                    "Model not reachable"
                ) from exc
            except requests.exceptions.Timeout as exc:
                logger.exception("Ollama timeout paper=%r raw_output=%r", paper_name, "")
                raise RuntimeError("Model timed out") from exc
            except requests.exceptions.RequestException as exc:
                logger.exception("Ollama request failure paper=%r raw_output=%r", paper_name, "")
                raise RuntimeError(f"Paper {paper_name} could not be read") from exc
            except (ValueError, AttributeError) as exc:
                logger.exception("Invalid Ollama response paper=%r raw_output=%r", paper_name, "")
                raise RuntimeError(f"Paper {paper_name} could not be read") from exc

        paper_evidence = []
        any_paper_output = False
        for name in paper_names:
            evidence_by_key = {}
            indexed_chunk_count = int((self.chunks_df["source"] == name).sum())
            if indexed_chunk_count == 0:
                logger.error("Comparison paper has no indexed chunks paper=%r", name)
                paper_evidence.append({
                    "name": name,
                    "fields": {field: "NOT_FOUND" for field in fields},
                    "pages": {field: [] for field in fields},
                    "error": f"Paper {name} could not be read",
                })
                continue
            for _, label, query in parameters:
                for result in self.search(
                    query,
                    top_k=max(1, self.index.ntotal),
                    paper_filter=[name],
                )[:4]:
                    key = (result["page"], result["text"])
                    evidence_by_key[key] = {
                        "page": result["page"],
                        "text": result["text"],
                    }

            evidence = list(evidence_by_key.values())[:max_context_chunks]
            if not evidence:
                logger.error(
                    "Comparison FAISS retrieval returned no chunks for paper=%r indexed_chunks=%d",
                    name,
                    indexed_chunk_count,
                )
                paper_evidence.append({
                    "name": name,
                    "fields": {field: "NOT_FOUND" for field in fields},
                    "pages": {field: [] for field in fields},
                    "error": f"Paper {name} could not be read",
                })
                continue

            context_parts = []
            remaining_characters = max_context_characters
            for chunk in evidence:
                if remaining_characters <= 0:
                    break
                excerpt = f"[Page {chunk['page']}]\n{chunk['text']}"
                excerpt = excerpt[:remaining_characters]
                context_parts.append(excerpt)
                remaining_characters -= len(excerpt) + 2
            context = "\n\n".join(context_parts)
            logger.info(
                "Comparison prompt context paper=%r chunks=%d characters=%d",
                name,
                len(context_parts),
                len(context),
            )
            prompt = (
                "Extract concise facts from only the paper excerpts below. Do not use outside knowledge "
                "or infer missing facts. Return a JSON object with exactly these keys and no others: "
                f"{', '.join(fields)}. Each value must be a short string or a short list of strings. "
                "Use the exact string NOT_FOUND when a fact is not stated. Keep each value to at most "
                "two lines and keep list items brief.\n\n"
                f"Paper title: {name}\nSector: {sector}\n\n"
                f"Supplied excerpts:\n{context}"
            )
            extraction_outputs = []
            extracted = {}
            parse_error = None
            try:
                model_result = ollama_call(prompt, name)
                raw_response = model_result["response"]
                extraction_outputs.append(raw_response)
                any_paper_output = any_paper_output or bool(raw_response)
            except RuntimeError as exc:
                if str(exc) == "Model not reachable":
                    raise
                if str(exc) == "Model timed out":
                    model_result = {"done_reason": "length", "eval_count": ollama_num_predict}
                    raw_response = ""
                    extraction_outputs.append(raw_response)
                else:
                    raise
            logger.info("Comparison raw Ollama extraction paper=%r response=%s", name, raw_response)
            try:
                if model_result.get("done_reason") == "length" or (
                    model_result.get("eval_count") is not None
                    and int(model_result["eval_count"]) >= ollama_num_predict
                ):
                    raise ValueError("The model output was truncated.")
                extracted = parse_extraction_response(raw_response)
            except (json.JSONDecodeError, ValueError) as exc:
                parse_error = exc
                repair_prompt = (
                    f"Repair the following response into valid JSON with exactly these keys: {', '.join(fields)}. "
                    "Values must be short strings or short lists of strings, or NOT_FOUND. Preserve only facts "
                    "already present in the response and do not add facts. Return only the repaired JSON.\n\n"
                    f"Validation error: {parse_error}\n\n"
                    f"Invalid response:\n{raw_response}"
                )
                try:
                    repair_result = ollama_call(repair_prompt, name)
                except RuntimeError as exc:
                    if str(exc) == "Model not reachable":
                        raise
                    if str(exc) == "Model timed out":
                        repair_result = {
                            "response": "",
                            "done_reason": "length",
                            "eval_count": ollama_num_predict,
                        }
                    else:
                        logger.exception("JSON repair request failed paper=%r raw_output=%r", name, "")
                        repair_result = {"response": "", "done_reason": None, "eval_count": 0}
                repaired_response = repair_result.get("response", "")
                extraction_outputs.append(repaired_response)
                any_paper_output = any_paper_output or bool(repaired_response)
                logger.info("Comparison repaired Ollama extraction paper=%r response=%s", name, repaired_response)
                try:
                    if repair_result.get("done_reason") == "length" or (
                        repair_result.get("eval_count") is not None
                        and int(repair_result["eval_count"]) >= ollama_num_predict
                    ):
                        raise ValueError("The repaired model output was truncated.")
                    extracted = parse_extraction_response(repaired_response)
                except (json.JSONDecodeError, ValueError) as repair_error:
                    logger.error(
                        "Comparison JSON parse failed paper=%r error=%s raw_output=%r",
                        name,
                        repair_error,
                        repaired_response,
                    )
                    extracted = {}
                    for group_start in range(0, len(parameters), 3):
                        field_group = parameters[group_start:group_start + 3]
                        group_fields = [field for field, _, _ in field_group]
                        group_labels = [label for _, label, _ in field_group]
                        field_prompt = (
                            f"Extract these fields from only the excerpts for paper '{name}': "
                            f"{', '.join(group_labels)}. Return valid JSON with exactly these keys: "
                            f"{', '.join(group_fields)}. Use short strings or short lists, and use the "
                            "exact string NOT_FOUND when a fact is not stated. Do not use outside knowledge.\n\n"
                            f"Excerpts:\n{context}"
                        )
                        try:
                            group_result = ollama_call(field_prompt, name)
                        except RuntimeError as exc:
                            if str(exc) in {"Model not reachable", "Model timed out"}:
                                raise
                            logger.exception(
                                "Comparison grouped fallback failed paper=%r fields=%r raw_output=%r",
                                name,
                                group_fields,
                                "",
                            )
                            for field in group_fields:
                                extracted[field] = "NOT_FOUND"
                            continue
                        field_response = group_result.get("response", "")
                        extraction_outputs.append(field_response)
                        any_paper_output = any_paper_output or bool(field_response)
                        logger.info(
                            "Comparison grouped fallback response paper=%r fields=%r response=%s",
                            name,
                            group_fields,
                            field_response,
                        )
                        try:
                            group_data = parse_extraction_response(field_response)
                            extracted.update(group_data)
                        except (json.JSONDecodeError, ValueError):
                            group_repair_prompt = (
                                f"Repair this response as valid JSON with exactly the keys "
                                f"{', '.join(group_fields)}. Preserve only facts in the response. "
                                "Use NOT_FOUND where a value is missing. Return JSON only.\n\n"
                                f"{field_response}"
                            )
                            try:
                                group_repair_result = ollama_call(group_repair_prompt, name)
                            except RuntimeError as exc:
                                if str(exc) in {"Model not reachable", "Model timed out"}:
                                    raise
                                logger.exception(
                                    "Comparison grouped repair failed paper=%r fields=%r raw_output=%r",
                                    name,
                                    group_fields,
                                    "",
                                )
                                group_repair_result = {"response": ""}
                            group_repair_response = group_repair_result.get("response", "")
                            extraction_outputs.append(group_repair_response)
                            any_paper_output = any_paper_output or bool(group_repair_response)
                            logger.error(
                                "Comparison grouped JSON parse failed paper=%r fields=%r raw_output=%r",
                                name,
                                group_fields,
                                group_repair_response,
                            )
                            try:
                                extracted.update(parse_extraction_response(group_repair_response))
                            except (json.JSONDecodeError, ValueError):
                                for field in group_fields:
                                    extracted[field] = "NOT_FOUND"

            normalized_fields = {}
            page_map = {}
            for field, _, query in parameters:
                value = extracted.get(field, "NOT_FOUND")
                if isinstance(value, dict) and "quote" in value:
                    value = value["quote"]
                if isinstance(value, str):
                    lines = [line.strip() for line in value.splitlines() if line.strip()]
                elif isinstance(value, list):
                    lines = [
                        str(item.get("quote", "") if isinstance(item, dict) else item).strip()
                        for item in value
                        if str(item.get("quote", "") if isinstance(item, dict) else item).strip()
                    ]
                else:
                    lines = []
                normalized_lines = []
                for line in lines:
                    if line.upper() == "NOT_FOUND":
                        normalized_lines = []
                        break
                    cleaned_line = re.sub(r"\*{1,2}", "", line).replace(" - ", " ")
                    normalized_lines.extend(cleaned_line.splitlines()[:2])
                normalized_fields[field] = normalized_lines[:2] or "NOT_FOUND"
                relevant_chunks = self.search(
                    query,
                    top_k=max(1, self.index.ntotal),
                    paper_filter=[name],
                )[:4]
                page_map[field] = sorted({item["page"] for item in relevant_chunks})

            found_any_field = any(value != "NOT_FOUND" for value in normalized_fields.values())
            paper_data = {"name": name, "fields": normalized_fields, "pages": page_map}
            if not found_any_field:
                paper_data["error"] = f"Paper {name} could not be read"
                logger.error(
                    "Comparison paper produced no usable fields paper=%r raw_outputs=%r",
                    name,
                    extraction_outputs,
                )
            logger.info("Comparison parsed per-paper data paper=%r data=%s", name, paper_data)
            paper_evidence.append(paper_data)

        if not any_paper_output:
            raise RuntimeError(
                f"Paper {paper_names[0]} and Paper {paper_names[1]} could not be read"
            )

        comparison_pairs = []
        for index_a in range(len(paper_evidence)):
            for index_b in range(index_a + 1, len(paper_evidence)):
                paper_a = paper_evidence[index_a]
                paper_b = paper_evidence[index_b]
                parameters_result = []
                for field, label, _ in parameters:
                    value_a = paper_a["fields"][field]
                    value_b = paper_b["fields"][field]
                    found_a = value_a != "NOT_FOUND"
                    found_b = value_b != "NOT_FOUND"
                    if found_a and found_b:
                        same_value = " ".join(value_a).strip().casefold() == " ".join(value_b).strip().casefold()
                        comparison_status = "Common" if same_value else "Different"
                    elif not found_a and not found_b:
                        comparison_status = "Missing"
                    else:
                        comparison_status = "Missing"
                    parameters_result.append({
                        "key": field,
                        "label": label,
                        "paper_a": {"name": paper_a["name"], "value": value_a, "pages": paper_a["pages"][field]},
                        "paper_b": {"name": paper_b["name"], "value": value_b, "pages": paper_b["pages"][field]},
                        "status": comparison_status,
                    })

                def model_names(value: Any) -> set[str]:
                    if value == "NOT_FOUND":
                        return set()
                    values = value if isinstance(value, list) else [value]
                    tokens = [token for item in values for token in re.split(r"[,;\n]", str(item))]
                    return {
                        re.sub(r"\s+", " ", token).strip().casefold()
                        for token in tokens if token.strip()
                    }

                models_a = model_names(paper_a["fields"]["ai_models"])
                models_b = model_names(paper_b["fields"]["ai_models"])
                synthesis_prompt = (
                    "Write a concise synthesis of these two papers using only the supplied JSON. "
                    "Do not add facts, outside knowledge, or conclusions not directly supported by these fields. "
                    "Use at most five lines. Return plain text only.\n\n"
                    f"Paper A JSON:\n{json.dumps(paper_a['fields'], ensure_ascii=False)}\n\n"
                    f"Paper B JSON:\n{json.dumps(paper_b['fields'], ensure_ascii=False)}"
                )
                try:
                    synthesis_result = ollama_call(synthesis_prompt, paper_a["name"], json_mode=False)
                    synthesis = synthesis_result["response"]
                except RuntimeError:
                    raise
                logger.info(
                    "Comparison synthesis raw Ollama response papers=%r response=%s",
                    [paper_a["name"], paper_b["name"]],
                    synthesis,
                )
                comparison_pairs.append({
                    "papers": [paper_a, paper_b],
                    "parameters": parameters_result,
                    "model_comparison": {
                        "used_only_paper_a": sorted(models_a - models_b),
                        "used_only_paper_b": sorted(models_b - models_a),
                        "used_in_both": sorted(models_a & models_b),
                    },
                    "synthesis": "\n".join(
                        re.sub(r"\*{1,2}", "", line).replace(" - ", " ")
                        for line in synthesis.splitlines()[:5]
                    ),
                })

        comparison = {
            "papers": paper_evidence,
            "pairs": comparison_pairs,
        }
        return {
            "papers": paper_names,
            "sector": sector,
            "comparison": comparison,
        }

    def detect_research_gaps(self, paper_id: str) -> Dict[str, Any]:
        """Finds evidence-grounded research gaps in one indexed paper."""
        paper_name = paper_id
        paper_mask = self.chunks_df["source"] == paper_id
        if not paper_mask.any():
            raise ValueError(f"Paper '{paper_name}' not found in the indexed database.")

        paper_chunk_count = int(paper_mask.sum())
        if self.index.ntotal != len(self.chunks_df):
            raise RuntimeError("FAISS index and paper metadata are out of sync.")

        queries = [
            "limitations weaknesses constraints future work",
            "hardware power energy cost sensor accuracy connectivity",
            "scalability deployment security privacy",
            "dataset diversity validation evaluation generalization",
            "real-time latency response time reliability",
        ]
        retrieved: Dict[int, Dict[str, Any]] = {}
        for query in queries:
            query_embedding = self.embedding_model.encode(
                [query], convert_to_numpy=True
            ).astype(np.float32)
            faiss.normalize_L2(query_embedding)
            scores, indices = self.index.search(query_embedding, int(self.index.ntotal))
            matches = []
            for score, index in zip(scores[0], indices[0]):
                if index < 0 or index >= len(self.chunks_df):
                    continue
                row = self.chunks_df.iloc[int(index)]
                if row["source"] != paper_name:
                    continue
                matches.append((float(score), int(index), row))

            for score, index, row in sorted(matches, reverse=True, key=lambda item: item[0])[:2]:
                retrieved[index] = {
                    "paper": paper_name,
                    "page": int(row["page"]),
                    "score": round(score, 4),
                    "text": str(row["text"]).strip(),
                }

        if not retrieved:
            raise ValueError(f"No FAISS chunks were found for paper '{paper_name}'.")

        evidence_chunks = sorted(
            retrieved.values(),
            key=lambda chunk: (chunk["page"], -chunk["score"]),
        )
        evidence_sentences = []
        excerpt_blocks = []
        limitation_pattern = re.compile(
            r"\b(?:limitation|challenge|may|might|could|cannot|can't|fail|failure|"
            r"lack|limited|limiting|difficult|difficulty|insufficient|inadequate|"
            r"constraint|problem|issue|weakness|weaknesses|"
            r"unaddressed|not|however|but)\b",
            re.IGNORECASE,
        )
        for chunk in evidence_chunks:
            excerpt = chunk["text"][:2200]
            sentences = re.split(r"(?<=[.!?])\s+|\n+", excerpt)
            sentence_lines = []
            for sentence in sentences:
                sentence = sentence.strip()
                if len(sentence) < 35 or not limitation_pattern.search(sentence):
                    continue
                evidence_id = f"E{len(evidence_sentences) + 1}"
                evidence_sentences.append({
                    "id": evidence_id,
                    "page": chunk["page"],
                    "text": sentence,
                })
                sentence_lines.append(f"[{evidence_id}] {sentence}")
            if sentence_lines:
                excerpt_blocks.append(
                    f"[Page {chunk['page']}]\n" + "\n".join(sentence_lines)
                )
        context_str = "\n\n".join(excerpt_blocks)
        evidence_by_id = {
            sentence["id"]: sentence for sentence in evidence_sentences
        }
        related_terms = (
            {"latency", "time", "delay", "delays", "response"},
            {"energy", "power", "battery"},
            {"scalability", "scale", "scalable", "growth"},
            {"accuracy", "error", "errors", "deviation", "deviations", "noise"},
            {"connectivity", "connection", "network"},
            {"security", "privacy"},
            {"dataset", "datasets", "sample", "samples"},
            {"cost", "costs", "expense"},
        )
        generic_terms = {
            "approach",
            "algorithm",
            "algorithms",
            "appeared",
            "authors",
            "based",
            "competing",
            "could",
            "data",
            "declare",
            "financial",
            "high",
            "influence",
            "interest",
            "lead",
            "might",
            "paper",
            "personal",
            "possible",
            "performance",
            "quality",
            "reported",
            "research",
            "should",
            "study",
            "system",
            "model",
            "models",
            "using",
            "water",
            "would",
            "work",
        }
        prompt = (
            "You are a critical academic reviewer analyzing exactly one research paper. "
            "Use only the supplied excerpts from that paper. Identify limitations or unresolved "
            "problems the paper itself supports, including hardware or energy constraints, "
            "scalability, dataset limitations, missing evaluation, latency, security, cost, "
            "sensor accuracy, connectivity, and other explicitly evidenced challenges. "
            "Do not claim a limitation merely because an excerpt does not discuss it. "
            "Do not invent evidence, results, or citations. Each gap must use one supplied evidence ID "
            "that directly supports it. Do not turn ordinary requirements, positive results, or measurements "
            "into gaps. Keep each explanation within what its evidence sentence explicitly states; do not infer "
            "resource costs, causes, impacts, or missing evaluations. If no gap is supported, return an empty gaps array.\n\n"
            "Return only valid JSON matching this schema:\n"
            '{"gaps":[{"title":"short gap title","why_it_is_a_problem":"impact explained from the paper",'
            '"severity":"High|Medium|Low","proposed_research_idea":"one specific research idea",'
            '"evidence_id":"one supplied ID"}]}\n\n'
            f"Paper: {paper_name}\n"
            f"Evidence sentences:\n{context_str}"
        )
        response = self.ask_llm(prompt=prompt, timeout=180, response_format="json")
        json_match = re.search(r"\{.*\}", response, re.DOTALL)
        if not json_match:
            logger.error("LLM returned no JSON object for research gaps on %s: %r", paper_name, response)
            raise RuntimeError("The LLM did not return valid structured JSON for research gaps.")
        try:
            payload = json.loads(json_match.group(0))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"The LLM returned invalid JSON for research gaps: {exc}") from exc

        raw_gaps = payload.get("gaps") if isinstance(payload, dict) else None
        if not isinstance(raw_gaps, list):
            raise RuntimeError("The LLM research-gap response must contain a gaps array.")

        valid_gaps = []
        for gap in raw_gaps:
            if not isinstance(gap, dict):
                continue
            title = str(gap.get("title", "")).strip()
            problem = str(gap.get("why_it_is_a_problem", "")).strip()
            idea = str(gap.get("proposed_research_idea", "")).strip()
            evidence_id = str(gap.get("evidence_id", "")).strip()
            severity = str(gap.get("severity", "")).strip().title()
            if not all((title, problem, idea, evidence_id)) or severity not in {"High", "Medium", "Low"}:
                continue

            evidence = evidence_by_id.get(evidence_id)
            if evidence is None:
                logger.warning(
                    "Discarding unknown research-gap evidence ID for %s: %r",
                    paper_name,
                    evidence_id,
                )
                continue
            claim_terms = set(
                re.findall(r"\b[a-z]{4,}\b", f"{title} {problem}".casefold())
            ) - generic_terms
            evidence_terms = set(
                re.findall(r"\b[a-z]{4,}\b", evidence["text"].casefold())
            ) - generic_terms
            directly_related = bool(claim_terms & evidence_terms)
            semantically_related = any(
                bool(claim_terms & terms) and bool(evidence_terms & terms)
                for terms in related_terms
            )
            if not directly_related and not semantically_related:
                logger.warning(
                    "Discarding research gap without matching evidence terms for %s: %s",
                    paper_name,
                    title,
                )
                continue

            valid_gaps.append({
                "title": title,
                "why_it_is_a_problem": problem,
                "severity": severity,
                "proposed_research_idea": idea,
                "evidence": evidence["text"],
                "page": evidence["page"],
            })

        logger.info(
            "Generated %d evidence-validated research gaps from %d FAISS chunks for %s.",
            len(valid_gaps),
            min(len(retrieved), paper_chunk_count),
            paper_name,
        )
        return {
            "paper": paper_name,
            "gaps": valid_gaps,
            "evidence_sources": [
                {"paper": paper_name, "page": chunk["page"]}
                for chunk in evidence_chunks
            ],
        }

    def generate_literature_review(self, paper_names: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Generates an academic-grade literature review structured as Chapter 2 (2.1 to 2.8).
        """
        target_papers = paper_names if paper_names else [p["name"] for p in self.get_indexed_papers()]

        if not target_papers:
            raise ValueError("No indexed papers available to generate a literature review.")

        # Retrieve high-level chunks
        results = self.search("methodology architecture experimental results findings", top_k=8, paper_filter=target_papers)
        context_str = "\n\n".join([f"[{c['paper']} | Page {c['page']}]: {c['text']}" for c in results])

        prompt = (
            f"You are an academic thesis supervisor. Write a formal Chapter 2: Literature Review based on the following papers:\n"
            f"{', '.join(target_papers)}\n\n"
            f"Context Evidence:\n{context_str}\n\n"
            f"Follow this EXACT academic thesis structure:\n"
            f"2. LITERATURE REVIEW\n"
            f"2.1 Introduction & Theoretical Background\n"
            f"2.2 Evolution of Existing Approaches\n"
            f"2.3 Traditional & Classical Machine Learning Methods\n"
            f"2.4 Deep Learning, Transformer & Generative AI Methods\n"
            f"2.5 Synthesis & Comparative Matrix of Existing Research\n"
            f"2.6 Critical Limitations of Existing Systems\n"
            f"2.7 Identified Research Gaps\n"
            f"2.8 Chapter Summary\n\n"
            f"Write in formal academic language. Compare and synthesize the works rather than simply listing them. Cite the specific paper names in text."
        )

        review = self.ask_llm(prompt=prompt)
        return {
            "papers": target_papers,
            "literature_review": review,
        }

    def generate_citation(self, paper_name: str, style: str = "IEEE") -> Dict[str, Any]:
        """
        Extracts bibliographic metadata from paper chunks (page 1) and formats
        citations in IEEE, APA, MLA, or Chicago style.
        """
        paper_chunks = self.chunks_df[self.chunks_df["source"] == paper_name]
        if paper_chunks.empty:
            raise ValueError(f"Paper '{paper_name}' not found.")

        # Take first 2 chunks which contain title, authors, journal, volume, year, DOI
        first_chunks = paper_chunks.iloc[:2]
        header_text = "\n".join(first_chunks["text"].tolist())

        style_upper = style.upper()
        prompt = (
            f"You are a bibliographic metadata extractor and citation generator.\n"
            f"Paper text from page 1 of '{paper_name}':\n\n"
            f"{header_text}\n\n"
            f"Task:\n"
            f"1. Extract the Title, Authors, Journal/Conference, Publication Year, Volume/Issue, Page Range, and DOI.\n"
            f"2. Format the citation strictly according to the {style_upper} citation style standard.\n"
            f"If any field cannot be found, use 'Unknown' or omit according to standard style rules. Do not hallucinate fictitious authors or DOIs.\n\n"
            f"Output Format:\n"
            f"Title: <extracted title>\n"
            f"Authors: <extracted authors>\n"
            f"Venue/Journal: <extracted journal/conference>\n"
            f"Year: <year>\n"
            f"DOI: <doi or Unknown>\n\n"
            f"Formatted Citation ({style_upper}):\n"
            f"<single formatted citation string>"
        )

        llm_response = self.ask_llm(prompt=prompt)
        return {
            "paper": paper_name,
            "style": style_upper,
            "citation": llm_response,
        }
