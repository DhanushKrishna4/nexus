"""
title: Blueprint Analyzer
author: Nexus
version: 0.1
description: Reads instrument tags off a P&ID image (vision model) and returns
  each tag's failure-state manual from the ChromaDB knowledge base. Appears as a
  selectable model called "Blueprint Analyzer".
"""
# Paste this whole file into Open WebUI:  Workspace → Functions → + New Function.
# Then enable it. It will appear in the model dropdown as "Blueprint Analyzer".
# Select it, attach a P&ID image, send — it returns the tag analysis.

import re
import httpx
from pydantic import BaseModel, Field

# Same tag rules as the Streamlit app.
TAG_PATTERN = r"\b[A-Z]{1,4}-\d{3,4}[A-Z]?\b"
_TAG_RE = re.compile(r"^([A-Z]{1,4})-([A-Z0-9]{3,4})([A-Z]?)$")
_DIGIT_FIX = str.maketrans({"O": "0", "Q": "0", "I": "1", "L": "1",
                            "S": "5", "B": "8", "Z": "2"})
VISION_PROMPT = (
    "Look closely at the text in this engineering diagram (P&ID). Extract and "
    "list every alphanumeric instrument tag you can read clearly, such as "
    "T-101, V-104, P-102A, PT-101, LT-104, FT-105. Respond with just the tags, "
    "comma-separated. Do not describe the image."
)


def _ocr_normalize(tag: str) -> str:
    m = _TAG_RE.match(tag.upper())
    if not m:
        return tag.upper()
    prefix, mid, suffix = m.groups()
    return f"{prefix}-{mid.translate(_DIGIT_FIX)}{suffix}"


class Pipe:
    class Valves(BaseModel):
        OLLAMA_URL: str = Field(default="http://localhost:11434")
        VISION_MODEL: str = Field(default="qwen2.5vl:7b")
        CHROMA_URL: str = Field(default="http://localhost:8000")
        COLLECTION: str = Field(default="instrument_failures")

    def __init__(self):
        self.valves = self.Valves()

    def pipes(self):
        return [{"id": "blueprint-analyzer", "name": "Blueprint Analyzer"}]

    # ---- helpers ----
    def _chroma_base(self):
        return (f"{self.valves.CHROMA_URL}/api/v2/tenants/default_tenant/"
                f"databases/default_database")

    def _collection_id(self):
        r = httpx.get(f"{self._chroma_base()}/collections", timeout=15)
        r.raise_for_status()
        for c in r.json():
            if c["name"] == self.valves.COLLECTION:
                return c["id"]
        raise RuntimeError(f"Collection '{self.valves.COLLECTION}' not found.")

    def _lookup(self, cid, tag):
        for cand in (tag, _ocr_normalize(tag)):
            r = httpx.post(
                f"{self._chroma_base()}/collections/{cid}/get",
                json={"where": {"tag": cand},
                      "include": ["documents", "metadatas"]},
                timeout=15,
            )
            r.raise_for_status()
            data = r.json()
            docs = data.get("documents") or []
            if docs:
                meta = (data.get("metadatas") or [{}])[0] or {}
                src = meta.get("source", "—")
                loc = meta.get("loc", "")
                cite = f"{src} · {loc}" if loc else src
                return docs[0], cite
        return None, None

    # ---- main ----
    def pipe(self, body: dict):
        messages = body.get("messages", [])
        if not messages:
            return "Send a P&ID image to analyze."

        # Pull text + image(s) out of the latest user message.
        last = messages[-1]
        content = last.get("content", "")
        images = []
        if isinstance(content, list):
            for part in content:
                if part.get("type") == "image_url":
                    url = part.get("image_url", {}).get("url", "")
                    if "base64," in url:
                        images.append(url.split("base64,", 1)[1])
        if not images:
            return ("⚠️ No image found. Attach a P&ID / blueprint image and send "
                    "again.")

        # 1) Vision model reads the tags.
        try:
            vr = httpx.post(
                f"{self.valves.OLLAMA_URL}/api/chat",
                json={
                    "model": self.valves.VISION_MODEL,
                    "messages": [{"role": "user", "content": VISION_PROMPT,
                                  "images": images}],
                    "stream": False, "keep_alive": -1,
                },
                timeout=180,
            )
            vr.raise_for_status()
            raw = vr.json()["message"]["content"]
        except Exception as e:  # noqa: BLE001
            return f"Vision model error: {e}"

        seen, tags = set(), []
        for t in re.findall(TAG_PATTERN, raw.upper()):
            if t not in seen:
                seen.add(t)
                tags.append(t)
        if not tags:
            return f"No instrument tags detected.\n\n*Raw vision output:* {raw}"

        # 2) Look each tag up in the knowledge base.
        try:
            cid = self._collection_id()
        except Exception as e:  # noqa: BLE001
            return f"Database error: {e}"

        found, missing = [], []
        for tag in tags:
            doc, cite = self._lookup(cid, tag)
            (found if doc else missing).append((tag, doc, cite))

        out = [f"**Detected {len(tags)} tag(s):** {', '.join(tags)}\n"]
        if found:
            out.append("\n### ✅ Failure-state manuals")
            for tag, doc, cite in found:
                out.append(f"\n**{tag}**  ·  _{cite}_\n\n{doc}")
        if missing:
            out.append("\n### ⚠️ No manual found")
            out.append(", ".join(t for t, _, _ in missing))
        return "\n".join(out)
