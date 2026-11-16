import json
from html import escape

import httpx
from fastapi import HTTPException

from app.core.config import settings


GEMINI_MODEL = "gemini-3.8-flash"
MAX_SOURCE_CHARACTERS = 30000

OUTPUT_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "blocks": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "type": {"type": "STRING", "enum": ["title", "heading", "paragraph", "bullet", "number", "quote"]},
                    "text": {"type": "STRING"},
                    "level": {"type": "INTEGER", "minimum": 1, "maximum": 3},
                },
                "required": ["type", "text"],
            },
        }
    },
    "required": ["blocks"],
}


class DocumentFormattingService:
    """Formats a transcript without changing its language or adding new facts."""

    @staticmethod
    def _validate_result(value: object) -> dict:
        if not isinstance(value, dict) or not isinstance(value.get("blocks"), list):
            raise HTTPException(status_code=502, detail="The formatted document could not be validated. Please try again.")
        if not value["blocks"] or len(value["blocks"]) > 500:
            raise HTTPException(status_code=502, detail="The formatted document was empty or too large. Please try again.")
        clean = []
        allowed = {"title", "heading", "paragraph", "bullet", "number", "quote"}
        for block in value["blocks"]:
            if not isinstance(block, dict) or block.get("type") not in allowed or not isinstance(block.get("text"), str):
                raise HTTPException(status_code=502, detail="The formatted document could not be validated. Please try again.")
            text = block["text"].strip()
            if not text or len(text) > 12000:
                continue
            item = {"type": block["type"], "text": text}
            if item["type"] == "heading":
                item["level"] = min(3, max(1, int(block.get("level", 2))))
            clean.append(item)
        if not clean:
            raise HTTPException(status_code=502, detail="The formatted document was empty. Please try again.")
        return {"blocks": clean}

    @staticmethod
    def _to_html(content: dict) -> str:
        parts = []
        for block in content["blocks"]:
            text = escape(block["text"]).replace("\\n", "<br>")
            kind = block["type"]
            if kind == "title":
                parts.append(f"<h1>{text}</h1>")
            elif kind == "heading":
                parts.append(f"<h{block.get('level', 2)}>{text}</h{block.get('level', 2)}>")
            elif kind == "bullet":
                parts.append(f"<ul><li>{text}</li></ul>")
            elif kind == "number":
                parts.append(f"<ol><li>{text}</li></ol>")
            elif kind == "quote":
                parts.append(f"<blockquote><p>{text}</p></blockquote>")
            else:
                parts.append(f"<p>{text}</p>")
        return "".join(parts)

    @classmethod
    def format_transcript(cls, transcript: str) -> tuple[dict, str]:
        source = (transcript or "").strip()
        if not source:
            raise HTTPException(status_code=400, detail="There is no transcript to format.")
        if len(source) > MAX_SOURCE_CHARACTERS:
            raise HTTPException(status_code=413, detail=f"Please format documents up to {MAX_SOURCE_CHARACTERS:,} characters at a time.")
        if not settings.gemini_api_key:
            raise HTTPException(status_code=503, detail="Document formatting is not configured yet.")
        prompt = (
            "Organize the following voice transcript into a clear, professional document. "
            "Preserve the original language, script, names, numbers, facts, and meaning exactly. "
            "The source may contain English, Marathi, Hindi, or mixed-language text. "
            "Do not translate, summarize away details, invent information, add facts, or answer questions in the transcript. "
            "Correct only obvious transcription punctuation and spacing. Use concise headings and paragraphs, "
            "and bullet or numbered blocks only where the transcript clearly supports them. "
            "Return every meaningful source detail. Output only the requested structured document.\n\n"
            "TRANSCRIPT:\n" + source
        )
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": OUTPUT_SCHEMA,
                "thinkingConfig": {"thinkingLevel": "low"},
            },
        }
        try:
            response = httpx.post(
                url,
                headers={"x-goog-api-key": settings.gemini_api_key},
                json=payload,
                timeout=settings.document_ai_timeout_seconds,
            )
            if response.status_code == 429:
                raise HTTPException(status_code=429, detail="Document formatting is temporarily busy. Please try again later.")
            response.raise_for_status()
            data = response.json()
            raw = data["candidates"][0]["content"]["parts"][0]["text"]
            parsed = json.loads(raw)
        except HTTPException:
            raise
        except (httpx.HTTPError, KeyError, IndexError, ValueError, TypeError) as exc:
            # Never log transcript text or provider response bodies.
            raise HTTPException(status_code=502, detail="Document formatting is temporarily unavailable. Please try again.") from exc
        structured = cls._validate_result(parsed)
        return structured, cls._to_html(structured)
