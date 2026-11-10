"""The eval corpus: files in backend/eval/corpus/ (gitignored), pinned by a committed manifest.json.

The files are indexed through the app's own IndexingPipeline into fresh in-memory indexes, under
one eval user, so the chunks are exactly what an upload would produce.
"""
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from app.ingestion.indexing_pipeline import IndexingPipeline
from app.retrieval.embeddings import EmbeddingService
from app.retrieval.index_builder import IndexBuilder
from app.retrieval.keyword_index import BM25KeywordIndex
from eval.retrieval.metrics import PageKey

CORPUS_DIR = Path(__file__).resolve().parent.parent / "corpus"
MANIFEST_NAME = "manifest.json"
SUPPORTED_SUFFIXES = (".pdf", ".pptx")
EVAL_USER_ID = "eval"


class CorpusError(RuntimeError):
    pass


@dataclass(frozen=True)
class CorpusFile:
    document_id: int
    file_name: str
    sha256: str


@dataclass
class IndexedCorpus:
    files: List[CorpusFile]
    index_builder: IndexBuilder
    bm25_index: BM25KeywordIndex
    chunk_counts: Dict[str, int]

    @property
    def chunks(self) -> List[Dict[str, Any]]:
        """Chunk metadata (text, file_name, page_num, …) in indexing order."""
        return self.index_builder.vector_store.metadata

    def page_texts(self) -> Dict[PageKey, str]:
        pages: Dict[PageKey, List[str]] = {}
        for chunk in self.chunks:
            pages.setdefault((chunk["file_name"], chunk["page_num"]), []).append(chunk["text"])
        return {key: "\n".join(texts) for key, texts in pages.items()}


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def write_manifest(corpus_dir: Path = CORPUS_DIR) -> List[CorpusFile]:
    paths = sorted(p for p in corpus_dir.iterdir() if p.suffix.lower() in SUPPORTED_SUFFIXES)
    if not paths:
        raise CorpusError(f"no .pdf / .pptx files in {corpus_dir}")
    files = [CorpusFile(i, p.name, sha256_of(p)) for i, p in enumerate(paths, start=1)]
    manifest = {"files": [{"document_id": f.document_id, "file_name": f.file_name, "sha256": f.sha256} for f in files]}
    (corpus_dir / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return files


def load_manifest(corpus_dir: Path = CORPUS_DIR) -> List[CorpusFile]:
    manifest_path = corpus_dir / MANIFEST_NAME
    if not manifest_path.exists():
        raise CorpusError(f"{manifest_path} is missing; create it with python -m eval.retrieval.corpus")
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    return [CorpusFile(int(f["document_id"]), str(f["file_name"]), str(f["sha256"])) for f in raw["files"]]


def verify_corpus(files: List[CorpusFile], corpus_dir: Path = CORPUS_DIR) -> None:
    """Results name the manifest, so a file that changed since would make them lie."""
    problems = []
    for f in files:
        path = corpus_dir / f.file_name
        if not path.exists():
            problems.append(f"missing: {f.file_name}")
        elif sha256_of(path) != f.sha256:
            problems.append(f"changed since the manifest was written: {f.file_name}")
    if problems:
        raise CorpusError("; ".join(problems))


def index_corpus(embedding_service: EmbeddingService, corpus_dir: Path = CORPUS_DIR) -> IndexedCorpus:
    files = load_manifest(corpus_dir)
    verify_corpus(files, corpus_dir)
    index_builder = IndexBuilder(embedding_service)
    bm25_index = BM25KeywordIndex()
    pipeline = IndexingPipeline(index_builder=index_builder, bm25_index=bm25_index)
    chunk_counts = {
        f.file_name: pipeline.index_document(
            str(corpus_dir / f.file_name), user_id=EVAL_USER_ID, document_id=f.document_id, file_name=f.file_name
        )
        for f in files
    }
    return IndexedCorpus(files, index_builder, bm25_index, chunk_counts)


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    for written in write_manifest():
        logging.getLogger("eval.corpus").info("%d  %s  %s", written.document_id, written.sha256[:12], written.file_name)
