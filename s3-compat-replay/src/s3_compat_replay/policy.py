from __future__ import annotations

from pathlib import Path

import yaml

from .config import load_yaml_file
from .models import PolicyEvaluation, PolicyPack, UsageProfile
from .questionnaire import generate_questionnaire
from .report import collect_mismatches
from .models import ProbeResults


BUILTIN_POLICY_DIR = Path(__file__).resolve().parent / "policy_packs"


def load_policy(path: str | Path) -> PolicyPack:
    return PolicyPack(**load_yaml_file(path))


def list_policy_files(policy_dir: str | Path | None = None) -> list[Path]:
    root = Path(policy_dir) if policy_dir else BUILTIN_POLICY_DIR
    if not root.exists():
        return []
    return sorted(root.glob("*.yml"))


def evaluate_policy(policy: PolicyPack, profile: UsageProfile, results: ProbeResults | None = None) -> PolicyEvaluation:
    observed_families = {name for name, family in profile.operation_families.items() if family.count > 0}
    missing_families = sorted(set(policy.required_families) - observed_families)
    observed_hint_names = _profile_hint_names(profile)
    missing_hints = sorted(set(policy.required_hints) - observed_hint_names)
    overrides_applied: dict[str, str] = {}
    blocker_codes: list[str] = []
    review_codes: list[str] = []
    if results:
        for mismatch in collect_mismatches(results):
            effective_severity = policy.severity_overrides.get(mismatch.mismatch_code, mismatch.severity)
            if mismatch.mismatch_code in policy.severity_overrides:
                overrides_applied[mismatch.mismatch_code] = effective_severity
            if effective_severity == "BLOCKER":
                blocker_codes.append(mismatch.mismatch_code)
            elif effective_severity == "REVIEW":
                review_codes.append(mismatch.mismatch_code)
    questions = list(policy.human_questions)
    generated = generate_questionnaire(profile, collect_mismatches(results) if results else [])
    for question in generated.questions:
        if question.question not in questions:
            questions.append(question.question)
    evidence_status = _evidence_policy_status(policy, profile, missing_families, missing_hints)
    target_status = _target_policy_status(results, blocker_codes, review_codes)
    status = _overall_status(evidence_status, target_status)
    return PolicyEvaluation(
        policy_name=policy.name,
        status=status,
        evidence_policy_status=evidence_status,
        target_policy_status=target_status,
        missing_required_families=missing_families,
        missing_required_hints=missing_hints,
        severity_overrides_applied=overrides_applied,
        blocker_mismatch_codes=sorted(set(blocker_codes)),
        review_mismatch_codes=sorted(set(review_codes)),
        recommended_questions=questions[:20],
        notes=["Policy evaluation is a report preset and evidence checklist, not an endpoint ranking."],
    )


def policy_to_yaml(policy: PolicyPack | PolicyEvaluation) -> str:
    return yaml.safe_dump(policy.model_dump(mode="json"), sort_keys=False)


def _profile_hint_names(profile: UsageProfile) -> set[str]:
    mapping = {
        "PRESIGNED_OBSERVED": "presigned",
        "CORS": "cors",
        "OBJECT_LOCK": "object_lock",
        "OBJECT_TAGGING": "object_tags",
        "METADATA_HEADERS": "metadata_headers",
        "CONTENT_TYPES": "content_types",
        "CONDITIONAL_REQUESTS": "conditional_requests",
        "RANGE_GETS": "range_gets",
        "VERSIONING": "versioning",
        "LIFECYCLE": "lifecycle",
    }
    return {mapping.get(feature, feature.lower()) for feature in set(profile.observed_features) | set(profile.request_hint_features) | set(profile.bucket_config_features)}


def _evidence_policy_status(policy: PolicyPack, profile: UsageProfile, missing_families: list[str], missing_hints: list[str]) -> str:
    if missing_families or missing_hints:
        return "REVIEW"
    confidence = "HIGH"
    if profile.processed_event_count == 0:
        confidence = "LOW"
    elif profile.evidence_quality.truncated_or_missing_fields:
        confidence = "MEDIUM"
    return "PASS" if _quality_rank(confidence) >= _quality_rank(policy.evidence_quality_minimum) else "REVIEW"


def _target_policy_status(results: ProbeResults | None, blocker_codes: list[str], review_codes: list[str]) -> str:
    if not results:
        return "NOT_RUN"
    if blocker_codes or results.probes_failed:
        return "FAIL"
    if review_codes or results.probes_skipped:
        return "REVIEW"
    return "PASS"


def _overall_status(evidence_status: str, target_status: str) -> str:
    if target_status == "FAIL":
        return "FAIL"
    if evidence_status != "PASS" or target_status in {"REVIEW", "NOT_RUN"}:
        return "REVIEW"
    return "PASS"


def _quality_rank(value: str) -> int:
    return {"LOW": 1, "MEDIUM": 2, "HIGH": 3}.get(value.upper(), 0)
