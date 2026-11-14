"""The eval corpus: files in backend/eval/corpus/ (gitignored), pinned by a committed manifest.json.

The files are indexed through the app's own IndexingService into document_chunks, under one eval
user that every run deletes and re-creates (Day 15: retrieval runs in Postgres), so the chunks are
exactly what an upload would produce. The database is EVAL_DATABASE_URL's (eval/retrieval/database.py),
or the one a test passes in.
"""
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.db.models import Chunk, Document, User
from app.retrieval.embeddings import EmbeddingService
from app.services.indexing_service import IndexingService
from eval.retrieval.metrics import PageKey

CORPUS_DIR = Path(__file__).resolve().parent.parent / "corpus"
MANIFEST_NAME = "manifest.json"
SUPPORTED_SUFFIXES = (".pdf", ".pptx")
# .invalid is a reserved TLD: this account can never belong to a real person.
EVAL_USER_EMAIL = "retrieval-eval@eval.invalid"


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
    embedding_service: EmbeddingService
    session_factory: sessionmaker
    # A string, like every user id retrieval sees (CLAUDE.md: index metadata keeps string ids).
    user_id: str
    chunk_counts: Dict[str, int]

    @property
    def chunks(self) -> List[Dict[str, Any]]:
        """Chunk text, file_name and page_num in indexing order."""
        with self.session_factory() as db:
            rows = db.execute(
                select(Chunk.text, Document.file_name, Chunk.page)
                .join(Document, Document.id == Chunk.document_id)
                .where(Chunk.user_id == int(self.user_id))
                .order_by(Chunk.id)
            )
            return [{"text": text, "file_name": file_name, "page_num": page} for text, file_name, page in rows]

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


def index_corpus(
    embedding_service: EmbeddingService,
    corpus_dir: Path = CORPUS_DIR,
    session_factory: sessionmaker | None = None,
) -> IndexedCorpus:
    files = load_manifest(corpus_dir)
    verify_corpus(files, corpus_dir)
    if session_factory is None:
        from eval.retrieval.database import eval_session_factory

        session_factory = eval_session_factory()
    indexing = IndexingService(embedding_service)

    with session_factory() as db:
        # ON DELETE CASCADE takes the previous run's documents and chunks with the user.
        db.query(User).filter(User.email == EVAL_USER_EMAIL).delete(synchronize_session=False)
        user = User(email=EVAL_USER_EMAIL)
        db.add(user)
        db.flush()
        chunk_counts: Dict[str, int] = {}
        for f in files:
            path = corpus_dir / f.file_name
            document = Document(
                user_id=user.id, file_name=f.file_name, file_path=str(path), file_hash=f.sha256,
                version=1, is_active=True,
            )
            db.add(document)
            db.flush()
            result = indexing.index_document(
                db, file_path=str(path), user_id=user.id, document_id=document.id,
                document_version=1, file_name=f.file_name,
            )
            chunk_counts[f.file_name] = result.chunks_indexed
        db.commit()
        user_id = str(user.id)

    return IndexedCorpus(files, embedding_service, session_factory, user_id, chunk_counts)


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    for written in write_manifest():
        logging.getLogger("eval.corpus").info("%d  %s  %s", written.document_id, written.sha256[:12], written.file_name)
