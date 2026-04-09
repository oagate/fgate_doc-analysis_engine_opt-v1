from __future__ import annotations

import json
import re
from typing import List, Optional

from loguru import logger

from api.analysis_schemas import (
    AnalyzeDocumentRequest,
    AnalyzeDocumentResponse,
    DocumentAnalysisMetrics,
    DocumentHighlight,
)
from core.deepseek_client import deepseek_client

_MAX_CHARS = 60_000

_RISK_TIERS: list[tuple[range, str]] = [
    (range(0,  26), "Low Risk"),
    (range(26, 51), "Medium Risk"),
    (range(51, 76), "High Risk"),
    (range(76, 101), "Critical"),
]


def _risk_label(score: int) -> str:
    for tier_range, label in _RISK_TIERS:
        if score in tier_range:
            return label
    return "High Risk"


def _truncate(text: str, max_chars: int = _MAX_CHARS) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n\n[... document truncated for analysis ...]"


_SYSTEM_FULL = """\
You are OpenAct Engine — a senior legal AI assistant specializing in contract review, \
risk analysis, and legal due diligence for Uzbekistan-based legal practice.

You analyze legal documents with the precision of a top-tier law firm associate. \
You identify risks, key clauses, obligations, contracting parties, and important dates.

Respond ONLY with valid JSON — no prose, no markdown fences, no commentary outside the JSON.

Required JSON schema:
{
  "highlights": [
    {
      "id": "h1",
      "category": "<risk_high|risk_medium|risk_low|clause_key|obligation|party|date>",
      "text": "<exact verbatim excerpt from the document, max 300 chars>",
      "explanation": "<concise professional explanation, 1–2 sentences>",
      "section": "<section/clause label or null>",
      "page_hint": <integer or null>
    }
  ],
  "metrics": {
    "risk_score": <0–100 integer>,
    "clause_count": <integer>,
    "obligation_count": <integer>,
    "flagged_count": <integer — total risk_high + risk_medium highlights>,
    "parties": ["Party A", "Party B"],
    "key_dates": ["YYYY-MM-DD or plain text"],
    "summary": "<2–4 sentence executive summary>"
  }
}

Rules:
- Extract only real verbatim text — never paraphrase in the "text" field
- Minimum 8, maximum 40 highlights for a full analysis
- risk_score: 0 = no issues, 100 = catastrophically risky
- Be precise, professional, terse. No padding.
"""

_SYSTEM_RISK = """\
You are OpenAct Engine. Analyze the document for legal risks ONLY.

Identify: missing protections, unfavorable terms, liability exposure, vague language, \
unilateral termination rights, penalty clauses, and jurisdiction issues.

Respond ONLY with valid JSON:
{
  "highlights": [
    {
      "id": "h1",
      "category": "<risk_high|risk_medium|risk_low>",
      "text": "<exact verbatim excerpt>",
      "explanation": "<professional 1–2 sentence explanation>",
      "section": "<section label or null>",
      "page_hint": <integer or null>
    }
  ],
  "metrics": {
    "risk_score": <0–100>,
    "clause_count": 0,
    "obligation_count": 0,
    "flagged_count": <total risks>,
    "parties": [],
    "key_dates": [],
    "summary": "<2–4 sentences on overall risk>"
  }
}
"""

_SYSTEM_CLAUSES = """\
You are OpenAct Engine. Extract all key contractual clauses from the document.

Focus on: definitions, payment terms, IP ownership, confidentiality, limitation of liability, \
warranties, termination, dispute resolution, and governing law.

Respond ONLY with valid JSON:
{
  "highlights": [
    {
      "id": "h1",
      "category": "clause_key",
      "text": "<exact verbatim clause text>",
      "explanation": "<what this clause means and its significance>",
      "section": "<section label or null>",
      "page_hint": <integer or null>
    }
  ],
  "metrics": {
    "risk_score": 0,
    "clause_count": <total clauses found>,
    "obligation_count": 0,
    "flagged_count": 0,
    "parties": [],
    "key_dates": [],
    "summary": "<summary of key contractual structure>"
  }
}
"""

_SYSTEM_COMPARE = """\
You are OpenAct Engine. Compare two versions of a legal document.

Identify: added obligations, removed protections, changed terms, new risks, \
improved provisions, and material differences.

You will receive Document A and Document B. Respond ONLY with valid JSON:
{
  "highlights_a": [
    {
      "id": "a1",
      "category": "<risk_high|risk_medium|risk_low|clause_key|obligation>",
      "text": "<exact text from Document A>",
      "explanation": "<what changed — reference Document B if relevant>",
      "section": "<section or null>",
      "page_hint": null
    }
  ],
  "highlights_b": [
    {
      "id": "b1",
      "category": "<risk_high|risk_medium|risk_low|clause_key|obligation>",
      "text": "<exact text from Document B>",
      "explanation": "<what changed — reference Document A if relevant>",
      "section": "<section or null>",
      "page_hint": null
    }
  ],
  "metrics": {
    "risk_score": <0–100 for Document B>,
    "clause_count": 0,
    "obligation_count": 0,
    "flagged_count": <number of concerning changes>,
    "parties": [],
    "key_dates": [],
    "summary": "<3–5 sentence comparison summary>"
  },
  "compare_summary": "<concise summary of the most important differences>"
}
"""

_SYSTEM_MAP: dict[str, str] = {
    "full":    _SYSTEM_FULL,
    "risk":    _SYSTEM_RISK,
    "clauses": _SYSTEM_CLAUSES,
}

def _parse_json(raw: str) -> dict:
    text = raw.strip()
    # Strip ```json ... ``` or ``` ... ``` code fences
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise


def _build_highlights(raw_list: list, prefix: str = "h") -> List[DocumentHighlight]:
    results: List[DocumentHighlight] = []
    for i, item in enumerate(raw_list or []):
        try:
            results.append(
                DocumentHighlight(
                    id=item.get("id") or f"{prefix}{i + 1}",
                    category=item.get("category", "clause_key"),
                    text=str(item.get("text", ""))[:500],
                    explanation=str(item.get("explanation", "")),
                    section=item.get("section"),
                    page_hint=item.get("page_hint"),
                )
            )
        except Exception as exc:
            logger.warning(f"[DocumentAnalysis] Skipping malformed highlight #{i}: {exc}")
    return results


def _build_metrics(
    raw: dict,
    highlights: List[DocumentHighlight],
) -> DocumentAnalysisMetrics:
    score = max(0, min(100, int(raw.get("risk_score", 0))))

    actual_flagged = sum(
        1 for h in highlights if h.category in ("risk_high", "risk_medium")
    )

    return DocumentAnalysisMetrics(
        risk_score=score,
        risk_label=_risk_label(score),
        clause_count=int(raw.get("clause_count", 0)),
        obligation_count=int(raw.get("obligation_count", 0)),
        flagged_count=max(int(raw.get("flagged_count", actual_flagged)), actual_flagged),
        parties=list(raw.get("parties") or []),
        key_dates=list(raw.get("key_dates") or []),
        summary=str(raw.get("summary", "")),
    )



class DocumentAnalysisService:
    async def analyze(self, req: AnalyzeDocumentRequest) -> AnalyzeDocumentResponse:
        if req.analysis_type == "compare":
            return await self._analyze_compare(req)
        return await self._analyze_single(req)

    async def _analyze_single(self, req: AnalyzeDocumentRequest) -> AnalyzeDocumentResponse:
        system_prompt = _SYSTEM_MAP.get(req.analysis_type, _SYSTEM_FULL)
        doc_text = _truncate(req.text)

        user_message = (
            f"Analyze the following legal document.\n"
            f"Filename: {req.filename}\n\n"
            f"---DOCUMENT START---\n{doc_text}\n---DOCUMENT END---"
        )

        logger.info(
            f"[DocumentAnalysis] Starting | type={req.analysis_type} | "
            f"doc='{req.filename}' | chars={len(doc_text):,}"
        )

        raw = await deepseek_client.generate(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            model_name="deepseek-v3",
            temperature=0.1,
            max_tokens=6000,
        )

        data = self._safe_parse(raw, req.analysis_type)
        highlights = _build_highlights(data.get("highlights", []))
        metrics = _build_metrics(data.get("metrics", {}), highlights)

        logger.success(
            f"[DocumentAnalysis] Done | type={req.analysis_type} | "
            f"highlights={len(highlights)} | risk_score={metrics.risk_score}"
        )

        return AnalyzeDocumentResponse(
            document_id=req.document_id,
            analysis_type=req.analysis_type,
            highlights=highlights,
            metrics=metrics,
        )

    async def _analyze_compare(self, req: AnalyzeDocumentRequest) -> AnalyzeDocumentResponse:
        if not req.compare_text:
            raise ValueError("compare_text is required for analysis_type='compare'")

        half_max = _MAX_CHARS // 2
        doc_a = _truncate(req.text, half_max)
        doc_b = _truncate(req.compare_text, half_max)

        user_message = (
            f"Compare these two legal documents.\n\n"
            f"=== DOCUMENT A: {req.filename} ===\n{doc_a}\n\n"
            f"=== DOCUMENT B: {req.compare_filename or 'Document B'} ===\n{doc_b}"
        )

        logger.info(
            f"[DocumentAnalysis] Compare | a='{req.filename}' | "
            f"b='{req.compare_filename}' | chars_a={len(doc_a):,} | chars_b={len(doc_b):,}"
        )

        raw = await deepseek_client.generate(
            messages=[
                {"role": "system", "content": _SYSTEM_COMPARE},
                {"role": "user", "content": user_message},
            ],
            model_name="deepseek-v3",
            temperature=0.1,
            max_tokens=8000,
        )

        data = self._safe_parse(raw, "compare")
        highlights_a = _build_highlights(data.get("highlights_a", []), prefix="a")
        highlights_b = _build_highlights(data.get("highlights_b", []), prefix="b")
        metrics = _build_metrics(data.get("metrics", {}), highlights_a + highlights_b)

        logger.success(
            f"[DocumentAnalysis] Compare done | "
            f"highlights_a={len(highlights_a)} | highlights_b={len(highlights_b)} | "
            f"risk_score={metrics.risk_score}"
        )

        return AnalyzeDocumentResponse(
            document_id=req.document_id,
            analysis_type="compare",
            highlights=highlights_a,
            metrics=metrics,
            compare_highlights=highlights_b,
            compare_summary=str(data.get("compare_summary", "")),
        )

    def _safe_parse(self, raw: Optional[str], analysis_type: str) -> dict:
        """Parse JSON from model output, logging and raising on failure."""
        try:
            return _parse_json(raw or "{}")
        except Exception as exc:
            logger.error(
                f"[DocumentAnalysis] JSON parse failed | type={analysis_type} | "
                f"error={exc} | raw_preview={repr((raw or '')[:300])}"
            )
            raise ValueError(f"Analysis response could not be parsed: {exc}") from exc

document_analysis_service = DocumentAnalysisService()
