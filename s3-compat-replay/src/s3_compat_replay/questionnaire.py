from __future__ import annotations

import csv
from pathlib import Path

from .capabilities import capability_for_family, family_for_feature, family_for_mismatch_code
from .models import Mismatch, Questionnaire, QuestionnaireItem, UsageProfile
from .report import MISMATCH_COLUMNS


FEATURE_QUESTIONS: dict[str, tuple[str, str]] = {
    "PRESIGNED_OBSERVED": ("presigned", "Are presigned URLs used by external users, partners, browsers, or batch integrations?"),
    "CORS": ("cors", "Which browser origins, methods, and request headers must be supported?"),
    "OBJECT_LOCK": ("object_lock", "Which scratch or target buckets have Object Lock support already enabled for lab validation?"),
    "VERSIONING": ("versioning", "Does application logic depend on version IDs, delete markers, or only operational tooling?"),
    "OBJECT_TAGGING": ("tagging", "Which object tags are required by application logic, lifecycle routing, or access policy?"),
    "METADATA_HEADERS": ("metadata", "Which metadata headers are read by application logic after object writes?"),
    "LIFECYCLE": ("lifecycle", "Which lifecycle side effects must be independently validated outside this short replay?"),
    "CONDITIONAL_REQUESTS": ("conditional_requests", "Which clients rely on If-Match or If-None-Match semantics?"),
    "RANGE_GETS": ("range_gets", "Which clients rely on partial reads or resumable downloads?"),
    "PRESIGNED_EXPIRATION_BUCKETS": ("presigned_expiry", "What presigned URL expiration ranges are required by external flows?"),
    "PAGINATION_TOKENS": ("list_pagination", "How large are production listings and do clients depend on continuation tokens?"),
    "CONSISTENCY_EXPECTATIONS": ("consistency", "Which flows assume immediate visibility after write or delete?"),
    "REQUESTER_PAYS_TRAFFIC": ("requester_pays", "Which clients send requester-pays headers and for which operations?"),
    "OWNERSHIP_CONTROLS": ("ownership_controls", "Are ACL calls required or should ownership controls replace them?"),
    "ENCRYPTION_HEADERS": ("encryption_headers", "Do applications inspect encryption headers or only require encryption at rest?"),
}


def load_mismatches_csv(path: str | Path | None) -> list[Mismatch]:
    if not path:
        return []
    target = Path(path)
    if not target.exists():
        return []
    with target.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != MISMATCH_COLUMNS:
            raise ValueError("mismatches CSV has unexpected columns")
        return [Mismatch(**row) for row in reader]


def generate_questionnaire(profile: UsageProfile, mismatches: list[Mismatch] | None = None) -> Questionnaire:
    questions: list[QuestionnaireItem] = []
    seen: set[str] = set()
    mismatches = mismatches or []
    mismatch_categories = {family_for_mismatch_code(mismatch.mismatch_code, mismatch.operation_family) for mismatch in mismatches}
    for mismatch in mismatches:
        family = family_for_mismatch_code(mismatch.mismatch_code, mismatch.operation_family)
        definition = capability_for_family(family)
        qid = f"mismatch_{mismatch.mismatch_code.lower()}"
        dedupe_key = _question_key(definition.owner_role, mismatch.suggested_human_question)
        if qid in seen or dedupe_key in seen:
            continue
        seen.add(qid)
        seen.add(dedupe_key)
        questions.append(
            QuestionnaireItem(
                id=qid,
                severity=mismatch.severity,
                category=family,
                owner_role=definition.owner_role,
                question=mismatch.suggested_human_question,
                reason=mismatch.reason_text,
                answer_required=mismatch.severity in {"BLOCKER", "REVIEW"},
                blocks_cutover_if_unanswered=mismatch.severity == "BLOCKER",
                evidence_source=[mismatch.evidence_source],
                related_codes=[mismatch.mismatch_code],
                related_probe_ids=[mismatch.probe_id],
            )
        )
    for feature in sorted(set(profile.observed_features) | set(profile.request_hint_features) | set(profile.bucket_config_features)):
        if feature not in FEATURE_QUESTIONS:
            continue
        category, question = FEATURE_QUESTIONS[feature]
        family = family_for_feature(feature)
        if category in mismatch_categories or family in mismatch_categories:
            continue
        definition = capability_for_family(family)
        qid = f"feature_{category}"
        dedupe_key = _question_key(definition.owner_role, question)
        if qid in seen or dedupe_key in seen:
            continue
        seen.add(qid)
        seen.add(dedupe_key)
        questions.append(
            QuestionnaireItem(
                id=qid,
                severity="REVIEW",
                category=category,
                owner_role=definition.owner_role,
                question=question,
                reason=f"{feature} appears in observed evidence or user-supplied context.",
                answer_required=True,
                blocks_cutover_if_unanswered=False,
                evidence_source=_feature_evidence_sources(profile, feature),
                related_codes=[feature],
            )
        )
    return Questionnaire(
        source_bucket_redacted=profile.source_bucket,
        generated_from={"profile": "usage-profile.json", "mismatches": "mismatches.csv"},
        questions=sorted(questions, key=lambda q: (_severity_order(q.severity), q.owner_role, q.category, q.id)),
    )


def questionnaire_to_markdown(questionnaire: Questionnaire) -> str:
    lines = ["# Application Owner Questions", ""]
    if not questionnaire.questions:
        lines.append("- No feature-specific questions were generated.")
    grouped: dict[str, list[QuestionnaireItem]] = {}
    for item in questionnaire.questions:
        grouped.setdefault(item.owner_role, []).append(item)
    for owner in sorted(grouped):
        lines.append(f"## {owner}")
        lines.append("")
        for item in grouped[owner]:
            flag = "blocks cutover" if item.blocks_cutover_if_unanswered else "answer required" if item.answer_required else "optional"
            lines.append(f"- [{item.severity}] {item.question}")
            lines.append(f"  - Category: {item.category}")
            lines.append(f"  - Decision: {flag}")
            lines.append(f"  - Reason: {item.reason}")
        lines.append("")
    return "\n".join(lines) + "\n"


def _feature_evidence_sources(profile: UsageProfile, feature: str) -> list[str]:
    sources: set[str] = set()
    if feature in profile.request_hint_features:
        sources.add("REQUEST_HINTS")
    if feature in profile.bucket_config_features:
        sources.add("BUCKET_CONFIG")
    if any(feature in family.observed_features for family in profile.operation_families.values()):
        sources.add("CLOUDTRAIL")
    return sorted(sources) or ["CLOUDTRAIL"]


def _severity_order(severity: str) -> int:
    return {"BLOCKER": 0, "REVIEW": 1, "INFO": 2}.get(severity, 3)


def _question_key(owner_role: str, question: str) -> str:
    return owner_role.strip().lower() + ":" + " ".join(question.lower().replace("?", "").split())
