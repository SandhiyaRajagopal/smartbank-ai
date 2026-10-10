"""Document ingestion: split the policy markdown files into retrievable chunks.

Chunking strategy: one chunk per "## section". Policy documents are already
organised by topic, so section boundaries keep each chunk self-contained
(e.g. the whole "Prepayment and foreclosure" rules stay together) - better than
cutting every N characters. Each chunk carries the document title + section
heading so the answer can cite exactly where it came from.
"""
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Chunk:
    id: str
    text: str            # what gets embedded / keyword-indexed
    source: str          # file name, e.g. loan_policy.md
    title: str           # document title
    section: str         # section heading


def chunk_markdown(path: Path) -> list[Chunk]:
    raw = path.read_text(encoding="utf-8")
    title_match = re.search(r"^# (.+)$", raw, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else path.stem
    chunks = []
    for block in re.split(r"^## ", raw, flags=re.MULTILINE)[1:]:
        heading, _, body = block.partition("\n")
        body = body.strip()
        if not body:
            continue
        text = f"{title} - {heading.strip()}\n{body}"
        chunk_id = hashlib.sha1(f"{path.name}:{heading}:{body}".encode()).hexdigest()[:16]
        chunks.append(Chunk(chunk_id, text, path.name, title, heading.strip()))
    return chunks


def load_chunks(policies_dir: str) -> list[Chunk]:
    chunks: list[Chunk] = []
    for path in sorted(Path(policies_dir).glob("*.md")):
        chunks.extend(chunk_markdown(path))
    return chunks
