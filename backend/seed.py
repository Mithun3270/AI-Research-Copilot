import hashlib
import json
import logging
import shutil
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from backend.research_copilot import ResearchCopilot

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("ResearchCopilotSeed")


def sha256_file(file_path: Path) -> str:
    digest = hashlib.sha256()
    with file_path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def main() -> int:
    manifest_path = ROOT_DIR / "seed_manifest.json"
    sample_dir = ROOT_DIR / "sample_papers"
    papers_dir = ROOT_DIR / "research_papers"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    papers = manifest["papers"]
    if not papers:
        raise RuntimeError("The seed manifest does not contain any papers.")
    chunk_size = int(manifest["chunk_size"])
    overlap = int(manifest["overlap"])
    expected_total = int(manifest["expected_total_vectors"])
    if chunk_size <= overlap or overlap < 0:
        raise ValueError("The seed chunk size must be greater than the non-negative overlap.")
    if sum(int(paper["expected_chunks"]) for paper in papers) != expected_total:
        raise ValueError("Per-paper expected chunk counts do not match the manifest total.")

    model_path = ROOT_DIR / "model" / "embedding_model" / "model.safetensors"
    if not model_path.is_file():
        raise FileNotFoundError(f"Required embedding model file is missing: {model_path}")
    actual_model_hash = sha256_file(model_path)
    expected_model_hash = str(manifest["embedding_model_sha256"]).upper()
    if actual_model_hash != expected_model_hash:
        raise RuntimeError(
            f"Embedding model checksum mismatch: expected {expected_model_hash}, "
            f"got {actual_model_hash}."
        )

    sample_hashes = {}
    for paper in papers:
        sample_path = sample_dir / paper["filename"]
        if not sample_path.is_file():
            raise FileNotFoundError(f"Required sample PDF is missing: {sample_path}")
        actual_hash = sha256_file(sample_path)
        expected_hash = str(paper["sha256"]).upper()
        if actual_hash != expected_hash:
            raise RuntimeError(
                f"Sample PDF checksum mismatch for {paper['filename']}: "
                f"expected {expected_hash}, got {actual_hash}."
            )
        sample_hashes[paper["filename"]] = actual_hash

    copilot = ResearchCopilot(base_dir=str(ROOT_DIR), papers_dir=str(papers_dir))
    expected_names = {paper["filename"] for paper in papers}
    existing_names = set(copilot.chunks_df["source"].dropna().astype(str).unique())
    unexpected_names = existing_names - expected_names
    if unexpected_names:
        names = ", ".join(sorted(unexpected_names))
        raise RuntimeError(
            "Seeding expects an empty library or only the listed sample papers. "
            f"Remove or export these other indexed papers before seeding: {names}"
        )

    papers_dir.mkdir(parents=True, exist_ok=True)
    for paper in papers:
        filename = paper["filename"]
        sample_path = sample_dir / filename
        target_path = papers_dir / filename
        if target_path.exists():
            if sha256_file(target_path) != sample_hashes[filename]:
                raise RuntimeError(
                    f"Refusing to overwrite a different existing PDF: {target_path}"
                )
        else:
            shutil.copy2(sample_path, target_path)
        result = copilot.add_paper(
            str(target_path),
            filename=filename,
            category_override=paper["category"],
            chunk_size=chunk_size,
            overlap=overlap,
        )
        expected_chunks = paper["expected_chunks"]
        if result["chunks_added"] != expected_chunks:
            raise RuntimeError(
                f"{filename} produced {result['chunks_added']} chunks; expected {expected_chunks}."
            )
        logger.info(
            "Seeded %s: category=%s, pages=%s, chunks=%s",
            filename,
            result["category"],
            result["pages"],
            result["chunks_added"],
        )

    actual_total = int(copilot.index.ntotal)
    if actual_total != expected_total or len(copilot.chunks_df) != expected_total:
        raise RuntimeError(
            f"Seed produced {actual_total} vectors and {len(copilot.chunks_df)} chunks; "
            f"expected {expected_total}."
        )

    actual_categories = {
        name: int(count)
        for name, count in copilot.chunks_df.groupby("category")["source"].nunique().items()
    }
    expected_categories = {}
    for paper in papers:
        category = paper["category"]
        expected_categories[category] = expected_categories.get(category, 0) + 1
    if actual_categories != expected_categories:
        raise RuntimeError(
            f"Seed produced category counts {actual_categories}; expected {expected_categories}."
        )

    logger.info(
        "Seed complete: %s papers, %s categories, %s FAISS vectors.",
        len(expected_names),
        len(actual_categories),
        actual_total,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
