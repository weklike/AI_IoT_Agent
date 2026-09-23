"""Bounded repository sources and atomic FTS5 import, shared by startup and CLI."""

import asyncio
import hashlib
import re
import unicodedata
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError

from backend.app.db import Database
from backend.app.models import KnowledgeChunk, KnowledgeDocument

ROOT = Path(__file__).resolve().parents[3] / "knowledge"
HAN = re.compile(r"[\u3400-\u9fff]+|[a-z0-9_]+")


def tokenize(value: str) -> list[str]:
    result = []
    for match in HAN.finditer(unicodedata.normalize("NFKC", value).lower()):
        word = match.group()
        if "\u3400" <= word[0] <= "\u9fff":
            for offset, character in enumerate(word):
                result.append(character)
                if offset + 1 < len(word):
                    result.append(word[offset : offset + 2])
        else:
            result.append(word)
    return result


class Document(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: str = Field(pattern=r"^[A-Z][A-Z0-9_-]{0,80}$")
    version: str = Field(pattern=r"^[A-Za-z0-9._-]{1,40}$")
    title: str = Field(min_length=1, max_length=200)
    category: str = Field(min_length=1, max_length=80)
    applicable_model: str = Field(min_length=1, max_length=80)
    source_kind: Literal["authored_simulation", "external_reference"]
    source_url: str | None
    license_note: str = Field(min_length=1, max_length=1000)
    tags: str = ""
    current: bool = True
    content: str = Field(min_length=1)

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.content.encode()).hexdigest()


def load_documents(directory: Path = ROOT) -> list[Document]:
    if directory.is_symlink():
        raise ValueError("Knowledge root points outside via a symlink")
    root = directory.resolve(strict=True)
    documents = []
    total = 0
    seen = set()
    current = set()
    for path in root.rglob("*"):
        if path.is_symlink() and not path.resolve().is_relative_to(root):
            raise ValueError("Knowledge path is outside its root")
    for path in sorted(root.rglob("*.md")):
        if not path.resolve().is_relative_to(root):
            raise ValueError("Knowledge path is outside its root")
        size = path.stat().st_size
        total += size
        if size > 32768 or total > 1048576:
            raise ValueError("Knowledge corpus exceeds size limits")
        lines = path.read_text().splitlines()
        if not lines or not lines[0].startswith("# "):
            raise ValueError("Knowledge title is missing")
        offset = 1
        while offset < len(lines) and not lines[offset].strip():
            offset += 1
        metadata = {}
        while offset < len(lines) and lines[offset].strip():
            key, separator, value = lines[offset].partition(":")
            if not separator or key in metadata:
                raise ValueError("Malformed or duplicate knowledge metadata")
            metadata[key] = None if value.strip() == "null" else value.strip()
            offset += 1
        document = Document.model_validate(
            {**metadata, "content": "\n".join(lines[offset:]).strip()}
        )
        if document.source_kind == "external_reference" and not document.source_url:
            raise ValueError("External sources need attribution URL")
        if document.source_url and not document.source_url.startswith(("https://", "http://")):
            raise ValueError("Invalid attribution URL")
        key = (document.source_id, document.version)
        if key in seen or document.current and document.source_id in current:
            raise ValueError("Duplicate knowledge source/version")
        seen.add(key)
        if document.current:
            current.add(document.source_id)
        documents.append(document)
    if not documents:
        raise ValueError("Knowledge corpus is empty")
    return documents


def make_chunks(document: Document) -> list[dict]:
    chunks = []
    heading = document.title
    for paragraph in re.split(r"\n\s*\n", document.content):
        if paragraph.startswith("#"):
            lines = paragraph.splitlines()
            heading = lines[0].lstrip("#").strip()
            paragraph = "\n".join(lines[1:]).strip()
        for offset in range(0, len(paragraph), 520):
            body = paragraph[offset : offset + 600].strip()
            if not body:
                continue
            digest = hashlib.sha256(body.encode()).hexdigest()
            identity = hashlib.sha256(
                f"{document.source_id}/{document.version}/{len(chunks)}/{digest}".encode()
            ).hexdigest()[:24]
            chunks.append(
                {
                    "chunk_id": identity,
                    "heading": heading,
                    "content": body,
                    "content_hash": digest,
                    "search_text": " ".join(tokenize(body)),
                }
            )
            if offset + 600 >= len(paragraph):
                break
    return chunks


META_FIELDS = (
    "title",
    "category",
    "tags",
    "applicable_model",
    "source_kind",
    "source_url",
    "license_note",
    "content",
)


class KnowledgeIndex:
    def __init__(self, db: Database, directory: Path = ROOT):
        self.db, self.directory = db, directory
        self.available = False

    async def refresh(self, *, check_only: bool = False) -> bool:
        try:
            documents = await asyncio.to_thread(load_documents, self.directory)
            expected = {(doc.source_id, doc.version): doc for doc in documents}
            async with self.db.sessions() as session:
                await session.execute(text("BEGIN IMMEDIATE"))
                stored = {
                    (doc.source_id, doc.version): doc
                    for doc in (await session.scalars(select(KnowledgeDocument))).all()
                }
                for key, document in expected.items():
                    previous = stored.get(key)
                    if previous and (
                        previous.content_hash != document.content_hash
                        or any(
                            getattr(previous, field) != getattr(document, field)
                            for field in META_FIELDS
                        )
                    ):
                        raise ValueError(
                            "Knowledge version is immutable; increment the source version"
                        )
                current_keys = {key for key, doc in expected.items() if doc.current}
                old_current = {key for key, doc in stored.items() if doc.current}
                chunks = (await session.scalars(select(KnowledgeChunk))).all()
                indexed = {chunk.chunk_id: chunk for chunk in chunks}
                prepared = {key: make_chunks(doc) for key, doc in expected.items()}
                changed = current_keys != old_current or any(key not in stored for key in expected)
                for key, parts in prepared.items():
                    for part in parts:
                        previous = indexed.get(part["chunk_id"])
                        changed = (
                            changed
                            or previous is None
                            or previous.search_text != part["search_text"]
                        )
                fts = (
                    await session.execute(
                        text("SELECT rowid,title,tags,body FROM knowledge_fts ORDER BY rowid")
                    )
                ).all()
                expected_fts = []
                if not changed:
                    for key in sorted(current_keys):
                        doc = expected[key]
                        for part in prepared[key]:
                            expected_fts.append(
                                (
                                    indexed[part["chunk_id"]].id,
                                    " ".join(tokenize(doc.title)),
                                    " ".join(
                                        tokenize(
                                            doc.tags + " " + doc.category + " " + doc.source_id
                                        )
                                    ),
                                    part["search_text"],
                                )
                            )
                    changed = [tuple(row) for row in fts] != sorted(expected_fts)
                if not changed:
                    await session.rollback()
                    self.available = True
                    return False
                if check_only:
                    await session.rollback()
                    self.available = False
                    return True
                for row in stored.values():
                    row.current = False
                for key, document in expected.items():
                    row = stored.get(key)
                    if row is None:
                        row = KnowledgeDocument(
                            source_id=document.source_id,
                            version=document.version,
                            content_hash=document.content_hash,
                            **{field: getattr(document, field) for field in META_FIELDS},
                            current=document.current,
                        )
                        session.add(row)
                        await session.flush()
                        stored[key] = row
                    row.current = document.current
                    for part in prepared[key]:
                        chunk = indexed.get(part["chunk_id"])
                        if chunk is None:
                            chunk = KnowledgeChunk(document_id=row.id, **part)
                            session.add(chunk)
                            await session.flush()
                            indexed[part["chunk_id"]] = chunk
                        else:
                            chunk.search_text = part["search_text"]
                await session.execute(text("DELETE FROM knowledge_fts"))
                for key in sorted(current_keys):
                    doc = expected[key]
                    for part in prepared[key]:
                        await session.execute(
                            text(
                                "INSERT INTO knowledge_fts(rowid,title,tags,body) VALUES (:id,:title,:tags,:body)"
                            ),
                            {
                                "id": indexed[part["chunk_id"]].id,
                                "title": " ".join(tokenize(doc.title)),
                                "tags": " ".join(
                                    tokenize(doc.tags + " " + doc.category + " " + doc.source_id)
                                ),
                                "body": part["search_text"],
                            },
                        )
                await session.commit()
            self.available = True
            return True
        except (ValueError, OSError, SQLAlchemyError):
            # Preserve the previous index transactionally, but report unavailable until repaired.
            self.available = False
            raise
