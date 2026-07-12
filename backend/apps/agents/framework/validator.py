"""Agent output validator — guards against ungrounded / malformed answers."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Validation:
    ok: bool
    issues: list[str]


class AgentValidator:
    def validate(self, *, answer: str, confidence: float, evidence: list[dict],
                 sources: list[dict], found: bool) -> Validation:
        issues: list[str] = []
        if not (answer or "").strip():
            issues.append("empty_answer")
        if not (0 <= confidence <= 100):
            issues.append("confidence_out_of_range")
        # An answer claiming to be found must rest on some evidence.
        if found and not evidence:
            issues.append("claimed_found_without_evidence")
        # Sources must not be fabricated beyond what evidence supports.
        if len(sources) > max(1, len(evidence)) + 1:
            issues.append("more_sources_than_evidence")
        return Validation(ok=not issues, issues=issues)


validator = AgentValidator()
