import re

from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError

from backend.app.errors import DomainError
from backend.app.knowledge.index import KnowledgeIndex, tokenize
from backend.app.models import Device, KnowledgeChunk, KnowledgeDocument


class KnowledgeSearch:
    def __init__(self, index: KnowledgeIndex):
        self.index = index

    async def search(
        self, query: str, device_id: str | None = None, *, method: str = "fts5"
    ) -> dict:
        if not isinstance(query, str) or not query.strip() or len(query) > 300:
            raise DomainError("INVALID_ARGUMENTS", "知识查询必须是1—300字符非空文本")
        if not self.index.available:
            raise DomainError("KNOWLEDGE_UNAVAILABLE", "知识索引不可用", 503)
        terms = list(dict.fromkeys(tokenize(query)))[:64]
        strong = {
            term
            for term in terms
            if len(term) == 2
            and all("\u3400" <= c <= "\u9fff" for c in term)
            or re.fullmatch(r"[a-z0-9_]+", term)
        }
        async with self.index.db.sessions() as session:
            model = "SIM-CHG-V2"
            if device_id is not None:
                device = await session.get(Device, device_id)
                if device is None:
                    raise DomainError("DEVICE_NOT_FOUND", "设备不存在", 404)
                model = device.model
            if not terms:
                return {"matches": []}
            try:
                if method == "fts5":
                    expression = " OR ".join('"' + term.replace('"', '""') + '"' for term in terms)
                    rows = (
                        (
                            await session.execute(
                                text("""SELECT d.source_id,d.version,d.title,d.tags,d.category,c.chunk_id,c.content,c.content_hash,
                        bm25(knowledge_fts,5,3,1) AS score FROM knowledge_fts
                        JOIN knowledge_chunks c ON c.id=knowledge_fts.rowid
                        JOIN knowledge_documents d ON d.id=c.document_id
                        WHERE knowledge_fts MATCH :query AND d.current=1 AND d.applicable_model=:model
                        ORDER BY score,d.source_id,c.chunk_id"""),
                                {"query": expression, "model": model},
                            )
                        )
                        .mappings()
                        .all()
                    )
                elif method == "exact_tags":
                    rows = (
                        (
                            await session.execute(
                                text("""SELECT d.source_id,d.version,d.title,d.tags,d.category,c.chunk_id,c.content,c.content_hash
                        FROM knowledge_chunks c JOIN knowledge_documents d ON d.id=c.document_id
                        WHERE d.current=1 AND d.applicable_model=:model ORDER BY d.source_id,c.chunk_id"""),
                                {"model": model},
                            )
                        )
                        .mappings()
                        .all()
                    )
                else:
                    raise ValueError("Unknown retrieval method")
            except SQLAlchemyError as error:
                self.index.available = False
                raise DomainError("KNOWLEDGE_UNAVAILABLE", "知识索引查询失败", 503) from error
            matches = []
            for row in rows:
                label_text = row["title"] + " " + row["tags"] + " " + row["category"]
                if method == "exact_tags":
                    normalized = query.casefold()
                    if not any(tag.casefold() in normalized for tag in row["tags"].split()):
                        continue
                else:
                    available = (
                        set(tokenize(label_text + " " + row["content"]))
                        if strong
                        else set(tokenize(label_text))
                    )
                    if not (strong or set(terms)) & available:
                        continue
                    # A lone incidental word in the body cannot support a multi-concept question.
                    # A title/tag match or two meaningful body terms provide a usable candidate.
                    if (
                        strong
                        and not strong & set(tokenize(label_text))
                        and len(strong & available) < min(2, len(strong))
                    ):
                        continue
                matches.append(
                    {
                        key: row[key]
                        for key in ("source_id", "version", "chunk_id", "title", "content")
                    }
                    | {"hash": row["content_hash"]}
                )
                if len(matches) == 5:
                    break
            return {"matches": matches}

    async def source(self, source_id: str, version: str) -> dict:
        async with self.index.db.sessions() as session:
            source = await session.scalar(
                select(KnowledgeDocument).where(
                    KnowledgeDocument.source_id == source_id, KnowledgeDocument.version == version
                )
            )
            if source is None:
                raise DomainError("KNOWLEDGE_NOT_FOUND", "来源版本不存在", 404)
            chunks = (
                await session.scalars(
                    select(KnowledgeChunk)
                    .where(KnowledgeChunk.document_id == source.id)
                    .order_by(KnowledgeChunk.id)
                )
            ).all()
            return {
                column.name: getattr(source, column.name)
                for column in source.__table__.columns
                if column.name != "id"
            } | {
                "chunks": [
                    {
                        "chunk_id": chunk.chunk_id,
                        "heading": chunk.heading,
                        "content": chunk.content,
                        "hash": chunk.content_hash,
                    }
                    for chunk in chunks
                ]
            }
