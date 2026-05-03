from __future__ import annotations

import csv
import json
import re
from collections import Counter
from pathlib import Path
from typing import Optional

import typer

from .analysis import generated_at_from, run_cabinet_analysis
from .bundle import redact_bundle, write_evidence_bundle
from .config import BUILTIN_POLICY_PACKS
from .doctor import build_doctor_report, render_doctor_markdown
from .drift import compare_envelopes, render_drift_markdown
from .models import CabinetEnvelope, Summary
from .packet import write_assessment_packet
from .pilot import build_pilot_report, load_pilot_outcomes, render_pilot_markdown
from .portfolio import find_cabinet_cases, portfolio_row, write_portfolio_csv, write_portfolio_json
from .redact import Redactor
from .release import build_release_report
from .report import (
    redact_envelope,
    redact_summary,
    write_explanation_markdown,
    write_explanation_json,
    write_aligned_timeseries_csv,
    write_guardrail_markdown,
    write_json,
)
from .synthesize import SYNTHETIC_NOW, generate_all_scenarios, generate_scenario, list_scenarios
from .validators import LoadedInputs
from .worksheet import render_facility_review_worksheet


app = typer.Typer(
    help="Local-only cabinet burst-envelope estimator. Produces review-only outputs from normalized CSV and YAML files.",
    no_args_is_help=True,
)


@app.command("policy-packs")
def policy_packs_command() -> None:
    """List built-in threshold policy packs."""
    for name in sorted(BUILTIN_POLICY_PACKS):
        typer.echo(name)


def _generated_at(now: str | None, fallback):
    return generated_at_from(now, fallback)


def _print_warnings(warnings: list[str]) -> None:
    for warning in warnings:
        typer.echo(f"warning: {warning}", err=True)


def _prepare_estimate(
    power: Path,
    temperature: Path,
    cabinet_profile: Path,
    config_path: Path | None,
    window_days: int,
    bucket_minutes: int,
    strict: bool,
    now: str | None,
    policy_pack: str | Path | None = None,
) -> tuple[LoadedInputs, object, object, object]:
    result = run_cabinet_analysis(
        power,
        temperature,
        cabinet_profile,
        config_path,
        window_days,
        bucket_minutes,
        strict,
        now,
        policy_pack,
    )
    return result.loaded, result.alignment, result.envelope, result.summary


@app.command("validate-inputs")
def validate_inputs_command(
    power: Path = typer.Option(..., "--power", exists=False, help="Normalized PDU power CSV."),
    temperature: Path = typer.Option(..., "--temperature", exists=False, help="Normalized inlet-temperature CSV."),
    cabinet_profile: Path = typer.Option(..., "--cabinet-profile", exists=False, help="Cabinet profile YAML."),
    config_path: Optional[Path] = typer.Option(None, "--config", help="Optional threshold override YAML."),
    policy_pack: Optional[str] = typer.Option(None, "--policy-pack", help="Built-in policy pack name or YAML path."),
    window_days: int = typer.Option(7, "--window-days"),
    bucket_minutes: int = typer.Option(5, "--bucket-minutes"),
    strict: bool = typer.Option(False, "--strict", help="Fail on missing or ambiguous inputs."),
    now: Optional[str] = typer.Option(None, "--now", help="Analysis window end in ISO 8601."),
    format_: str = typer.Option("text", "--format", help="Use json for machine-readable validation output."),
) -> None:
    try:
        loaded, alignment, envelope, _summary = _prepare_estimate(
            power,
            temperature,
            cabinet_profile,
            config_path,
            window_days,
            bucket_minutes,
            strict,
            now,
            policy_pack,
        )
    except Exception as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc

    payload = {
        "cabinet_id": loaded.cabinet_id,
        "valid": envelope.envelope_status != "INSUFFICIENT_DATA",
        "envelope_status": envelope.envelope_status,
        "confidence": envelope.confidence,
        "coverage": alignment.coverage.model_dump(mode="json"),
        "reason_codes": envelope.reason_codes,
        "warnings": envelope.warnings,
        "blockers": envelope.blockers,
        "missing_data": envelope.missing_data,
    }
    if format_ == "json":
        typer.echo(json.dumps(payload, indent=2))
    else:
        _print_warnings(envelope.warnings)
        typer.echo(f"cabinet_id: {loaded.cabinet_id}")
        typer.echo(f"valid: {payload['valid']}")
        typer.echo(f"envelope_status: {envelope.envelope_status}")
        typer.echo(f"confidence: {envelope.confidence}")


@app.command("estimate")
def estimate_command(
    power: Path = typer.Option(..., "--power", exists=False, help="Normalized PDU power CSV."),
    temperature: Path = typer.Option(..., "--temperature", exists=False, help="Normalized inlet-temperature CSV."),
    cabinet_profile: Path = typer.Option(..., "--cabinet-profile", exists=False, help="Cabinet profile YAML."),
    output_envelope: Optional[Path] = typer.Option(None, "--output-envelope", help="Output envelope JSON."),
    output_timeseries: Optional[Path] = typer.Option(None, "--output-timeseries", help="Output aligned timeseries CSV."),
    output_guardrail: Optional[Path] = typer.Option(None, "--output-guardrail", help="Output sales/ops guardrail Markdown."),
    summary: Optional[Path] = typer.Option(None, "--summary", help="Output summary JSON."),
    config_path: Optional[Path] = typer.Option(None, "--config", help="Optional threshold override YAML."),
    policy_pack: Optional[str] = typer.Option(None, "--policy-pack", help="Built-in policy pack name or YAML path."),
    window_days: int = typer.Option(7, "--window-days"),
    bucket_minutes: int = typer.Option(5, "--bucket-minutes"),
    strict: bool = typer.Option(False, "--strict", help="Fail on missing or ambiguous inputs."),
    redact: bool = typer.Option(False, "--redact", help="Redact IDs in generated outputs."),
    now: Optional[str] = typer.Option(None, "--now", help="Analysis window end in ISO 8601."),
    format_: str = typer.Option("text", "--format", help="Use json to print the envelope to stdout."),
) -> None:
    try:
        _loaded, alignment, envelope, summary_model = _prepare_estimate(
            power,
            temperature,
            cabinet_profile,
            config_path,
            window_days,
            bucket_minutes,
            strict,
            now,
            policy_pack,
        )
    except Exception as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc

    if format_ != "json":
        _print_warnings(envelope.warnings)
    redactor = Redactor()
    output_envelope_model = redact_envelope(envelope, redactor) if redact else envelope
    output_summary_model = redact_summary(summary_model, redactor) if redact else summary_model

    if output_envelope:
        write_json(output_envelope, output_envelope_model)
    if output_timeseries:
        write_aligned_timeseries_csv(output_timeseries, alignment, redact=redact, redactor=redactor)
    if output_guardrail:
        write_guardrail_markdown(output_guardrail, output_envelope_model)
    if summary:
        write_json(summary, output_summary_model)

    if format_ == "json" or not any([output_envelope, output_timeseries, output_guardrail, summary]):
        typer.echo(json.dumps(output_envelope_model.model_dump(mode="json"), indent=2))
    else:
        typer.echo(f"{output_envelope_model.envelope_status}: {output_envelope_model.sales_ops_guardrail.text}")


@app.command("assess")
def assess_command(
    case_dir: Path = typer.Option(..., "--case-dir", exists=True, file_okay=False, help="Directory containing pdu_power.csv, inlet_temps.csv, and cabinet_profile.yml."),
    output_dir: Path = typer.Option(..., "--output-dir", help="Directory for the complete cabinet review packet."),
    config_path: Optional[Path] = typer.Option(None, "--config", help="Optional threshold override YAML. Defaults to case_dir/thresholds.yml when present."),
    policy_pack: Optional[str] = typer.Option(None, "--policy-pack", help="Built-in policy pack name or YAML path."),
    window_days: int = typer.Option(7, "--window-days"),
    bucket_minutes: int = typer.Option(5, "--bucket-minutes"),
    strict: bool = typer.Option(False, "--strict", help="Fail on missing or ambiguous inputs."),
    redact: bool = typer.Option(False, "--redact", help="Redact IDs in generated outputs."),
    now: Optional[str] = typer.Option(None, "--now", help="Analysis window end in ISO 8601."),
    format_: str = typer.Option("json", "--format", help="Use json for machine-readable stdout."),
) -> None:
    power = case_dir / "pdu_power.csv"
    temperature = case_dir / "inlet_temps.csv"
    cabinet_profile = case_dir / "cabinet_profile.yml"
    case_config = config_path or ((case_dir / "thresholds.yml") if (case_dir / "thresholds.yml").exists() else None)
    case_manifest = (case_dir / "case_manifest.yml") if (case_dir / "case_manifest.yml").exists() else None
    try:
        result = run_cabinet_analysis(
            power,
            temperature,
            cabinet_profile,
            case_config,
            window_days,
            bucket_minutes,
            strict,
            now,
            policy_pack,
        )
        manifest = write_assessment_packet(
            output_dir,
            result,
            {
                "power": power,
                "temperature": temperature,
                "cabinet_profile": cabinet_profile,
                "config": case_config,
                "case_manifest": case_manifest,
            },
            redact=redact,
        )
    except Exception as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc

    payload = {
        "cabinet_id": Redactor().redact("cabinet", result.envelope.cabinet_id) if redact else result.envelope.cabinet_id,
        "review_lane": result.review_lane.lane,
        "envelope_status": result.envelope.envelope_status,
        "confidence": result.envelope.confidence,
        "primary_constraint": result.review_lane.primary_constraint,
        "business_action": result.review_lane.business_action,
        "output_dir": str(output_dir),
        "manifest": manifest.files.get("manifest"),
    }
    if format_ == "json":
        typer.echo(json.dumps(payload, indent=2))
    else:
        typer.echo(f"{payload['review_lane']}: {payload['business_action']}")


@app.command("doctor")
def doctor_command(
    power: Path = typer.Option(..., "--power", exists=False, help="Normalized PDU power CSV."),
    temperature: Path = typer.Option(..., "--temperature", exists=False, help="Normalized inlet-temperature CSV."),
    cabinet_profile: Path = typer.Option(..., "--cabinet-profile", exists=False, help="Cabinet profile YAML."),
    output_json: Optional[Path] = typer.Option(None, "--output-json", help="Optional doctor JSON output."),
    output_markdown: Optional[Path] = typer.Option(None, "--output-markdown", help="Optional doctor Markdown output."),
    config_path: Optional[Path] = typer.Option(None, "--config", help="Optional threshold override YAML."),
    policy_pack: Optional[str] = typer.Option(None, "--policy-pack", help="Built-in policy pack name or YAML path."),
    window_days: int = typer.Option(7, "--window-days"),
    bucket_minutes: int = typer.Option(5, "--bucket-minutes"),
    strict: bool = typer.Option(False, "--strict", help="Fail on missing or ambiguous inputs."),
    now: Optional[str] = typer.Option(None, "--now", help="Analysis window end in ISO 8601."),
    format_: str = typer.Option("text", "--format", help="Use json for machine-readable stdout."),
) -> None:
    try:
        _loaded, alignment, envelope, _summary = _prepare_estimate(
            power,
            temperature,
            cabinet_profile,
            config_path,
            window_days,
            bucket_minutes,
            strict,
            now,
            policy_pack,
        )
    except Exception as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    report = build_doctor_report(envelope, alignment)
    if output_json:
        write_json(output_json, report)
    if output_markdown:
        Path(output_markdown).parent.mkdir(parents=True, exist_ok=True)
        Path(output_markdown).write_text(render_doctor_markdown(report), encoding="utf-8")
    if format_ == "json":
        typer.echo(json.dumps(report, indent=2))
    else:
        typer.echo(render_doctor_markdown(report))


@app.command("evidence-bundle")
def evidence_bundle_command(
    power: Path = typer.Option(..., "--power", exists=False, help="Normalized PDU power CSV."),
    temperature: Path = typer.Option(..., "--temperature", exists=False, help="Normalized inlet-temperature CSV."),
    cabinet_profile: Path = typer.Option(..., "--cabinet-profile", exists=False, help="Cabinet profile YAML."),
    output_dir: Path = typer.Option(..., "--output-dir", help="Evidence bundle output directory."),
    config_path: Optional[Path] = typer.Option(None, "--config", help="Optional threshold override YAML."),
    policy_pack: Optional[str] = typer.Option(None, "--policy-pack", help="Built-in policy pack name or YAML path."),
    window_days: int = typer.Option(7, "--window-days"),
    bucket_minutes: int = typer.Option(5, "--bucket-minutes"),
    strict: bool = typer.Option(False, "--strict", help="Fail on missing or ambiguous inputs."),
    redact: bool = typer.Option(False, "--redact", help="Redact generated bundle outputs."),
    now: Optional[str] = typer.Option(None, "--now", help="Analysis window end in ISO 8601."),
) -> None:
    try:
        _loaded, alignment, envelope, summary_model = _prepare_estimate(
            power,
            temperature,
            cabinet_profile,
            config_path,
            window_days,
            bucket_minutes,
            strict,
            now,
            policy_pack,
        )
        manifest = write_evidence_bundle(
            output_dir,
            envelope,
            summary_model,
            alignment,
            _generated_at(now, alignment.window_end),
            {
                "power": power,
                "temperature": temperature,
                "cabinet_profile": cabinet_profile,
                "config": config_path,
            },
            redact=redact,
        )
    except Exception as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"wrote evidence bundle for {manifest.cabinet_id} to {output_dir}")


@app.command("synthesize")
def synthesize_command(
    output_dir: Optional[Path] = typer.Option(None, "--output-dir", help="Scenario output directory."),
    scenario: str = typer.Option("healthy_margin", "--scenario", help="Synthetic scenario name."),
    all_scenarios: bool = typer.Option(False, "--all", help="Generate every built-in scenario."),
    list_only: bool = typer.Option(False, "--list", help="List available scenarios."),
    cabinet_id: Optional[str] = typer.Option(None, "--cabinet-id"),
    days: int = typer.Option(7, "--days"),
    bucket_minutes: int = typer.Option(5, "--bucket-minutes"),
    seed: int = typer.Option(1, "--seed"),
    base_kw: Optional[float] = typer.Option(None, "--base-kw"),
    burst_kw: Optional[float] = typer.Option(None, "--burst-kw"),
    burst_frequency: Optional[int] = typer.Option(None, "--burst-frequency"),
    thermal_slope: Optional[float] = typer.Option(None, "--thermal-slope"),
    thermal_lag_minutes: Optional[int] = typer.Option(None, "--thermal-lag-minutes"),
    noise: Optional[float] = typer.Option(None, "--noise"),
    missing_power_pct: Optional[float] = typer.Option(None, "--missing-power-pct"),
    missing_temp_pct: Optional[float] = typer.Option(None, "--missing-temp-pct"),
    sensor_set: Optional[str] = typer.Option(None, "--sensor-set", help="Comma list: top,middle,bottom."),
    feed_imbalance_pct: Optional[float] = typer.Option(None, "--feed-imbalance-pct"),
    reading_scope: Optional[str] = typer.Option(None, "--reading-scope"),
    write_expected_envelope: bool = typer.Option(True, "--write-expected-envelope/--no-write-expected-envelope"),
) -> None:
    if list_only:
        for name in list_scenarios():
            typer.echo(name)
        return
    if output_dir is None:
        typer.echo("error: --output-dir is required unless --list is used", err=True)
        raise typer.Exit(1)
    overrides = {
        "base_kw": base_kw,
        "burst_kw": burst_kw,
        "burst_frequency": burst_frequency,
        "thermal_slope": thermal_slope,
        "thermal_lag_minutes": thermal_lag_minutes,
        "noise": noise,
        "missing_power_pct": missing_power_pct,
        "missing_temp_pct": missing_temp_pct,
        "sensor_set": tuple(part.strip() for part in sensor_set.split(",") if part.strip()) if sensor_set else None,
        "feed_imbalance_pct": feed_imbalance_pct,
        "reading_scope": reading_scope,
    }
    try:
        manifests = (
            generate_all_scenarios(output_dir, days=days, bucket_minutes=bucket_minutes, seed=seed)
            if all_scenarios
            else [generate_scenario(output_dir, scenario, cabinet_id=cabinet_id, days=days, bucket_minutes=bucket_minutes, seed=seed, overrides=overrides)]
        )
        if write_expected_envelope:
            for manifest in manifests:
                case_dir = output_dir / manifest.scenario if all_scenarios else output_dir
                _loaded, _alignment, envelope, _summary = _prepare_estimate(
                    case_dir / "pdu_power.csv",
                    case_dir / "inlet_temps.csv",
                    case_dir / "cabinet_profile.yml",
                    case_dir / "thresholds.yml",
                    days,
                    bucket_minutes,
                    False,
                    SYNTHETIC_NOW.isoformat().replace("+00:00", "Z"),
                )
                write_json(case_dir / "expected_envelope.json", envelope)
    except Exception as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"generated {len(manifests)} synthetic scenario(s) in {output_dir}")


@app.command("batch")
def batch_command(
    input_root: Path = typer.Option(..., "--input-root", exists=True, help="Root containing cabinet case directories."),
    output_csv: Optional[Path] = typer.Option(None, "--output-csv", help="Portfolio CSV output."),
    output_json: Optional[Path] = typer.Option(None, "--output-json", help="Portfolio JSON output."),
    config_path: Optional[Path] = typer.Option(None, "--config", help="Optional threshold override YAML."),
    policy_pack: Optional[str] = typer.Option(None, "--policy-pack", help="Built-in policy pack name or YAML path."),
    window_days: int = typer.Option(7, "--window-days"),
    bucket_minutes: int = typer.Option(5, "--bucket-minutes"),
    strict: bool = typer.Option(False, "--strict", help="Fail on the first invalid case."),
    now: Optional[str] = typer.Option(None, "--now", help="Analysis window end in ISO 8601."),
) -> None:
    rows = []
    for case_dir in find_cabinet_cases(input_root):
        case_config = config_path or ((case_dir / "thresholds.yml") if (case_dir / "thresholds.yml").exists() else None)
        try:
            _loaded, _alignment, envelope, _summary = _prepare_estimate(
                case_dir / "pdu_power.csv",
                case_dir / "inlet_temps.csv",
                case_dir / "cabinet_profile.yml",
                case_config,
                window_days,
                bucket_minutes,
                strict,
                now,
                policy_pack,
            )
            rows.append(portfolio_row(case_dir, envelope))
        except Exception as exc:
            if strict:
                typer.echo(f"error in {case_dir}: {exc}", err=True)
                raise typer.Exit(1) from exc
            rows.append(
                {
                    "cabinet_id": case_dir.name,
                    "case_dir": str(case_dir),
                    "envelope_status": "INSUFFICIENT_DATA",
                    "confidence": "LOW",
                    "blockers": f"ERROR:{exc}",
                }
            )
    if output_csv:
        write_portfolio_csv(output_csv, rows)
    if output_json:
        write_portfolio_json(output_json, rows)
    typer.echo(json.dumps({"cabinet_count": len(rows), "output_csv": str(output_csv) if output_csv else None, "output_json": str(output_json) if output_json else None}, indent=2))


BENCHMARK_POWER_REQUIRED = {"timestamp", "cabinet_id", "reading_kw"}
BENCHMARK_TEMPERATURE_REQUIRED = {"timestamp", "cabinet_id", "sensor_id", "inlet_temp_c"}
BENCHMARK_FORBIDDEN_LANGUAGE = re.compile(
    r"safe to sell|guaranteed|approved capacity|facility capacity confirmed|customer-ready commitment|engineering-approved",
    re.IGNORECASE,
)


def _csv_counter(path: Path, field: str) -> Counter[str]:
    counter: Counter[str] = Counter()
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            counter[row.get(field) or "<blank>"] += 1
    return counter


def _benchmark_input_coverage(scenario_root: Path) -> tuple[dict[str, object], list[str]]:
    failures: list[str] = []
    scope_counts: Counter[str] = Counter()
    power_quality_counts: Counter[str] = Counter()
    position_counts: Counter[str] = Counter()
    role_counts: Counter[str] = Counter()
    temp_quality_counts: Counter[str] = Counter()
    power_rows = 0
    temp_rows = 0
    optional_power_fields_present: set[str] = set()
    optional_temp_fields_present: set[str] = set()
    annotation_files = 0
    for case_dir in sorted(path for path in scenario_root.iterdir() if path.is_dir()):
        power_path = case_dir / "pdu_power.csv"
        temp_path = case_dir / "inlet_temps.csv"
        with power_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            missing = BENCHMARK_POWER_REQUIRED - set(reader.fieldnames or [])
            if missing:
                failures.append(f"{case_dir.name} power CSV missing required columns: {sorted(missing)}")
            for row in reader:
                power_rows += 1
                scope_counts[row.get("reading_scope") or "<blank>"] += 1
                power_quality_counts[row.get("reading_quality") or "<blank>"] += 1
                for field in ("phase", "voltage_v", "current_a", "apparent_power_kva", "power_factor"):
                    if row.get(field):
                        optional_power_fields_present.add(field)
        with temp_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            missing = BENCHMARK_TEMPERATURE_REQUIRED - set(reader.fieldnames or [])
            if missing:
                failures.append(f"{case_dir.name} temperature CSV missing required columns: {sorted(missing)}")
            for row in reader:
                temp_rows += 1
                position_counts[row.get("position") or "<blank>"] += 1
                role_counts[row.get("sensor_role") or "<blank>"] += 1
                temp_quality_counts[row.get("reading_quality") or "<blank>"] += 1
                for field in ("humidity_pct", "dewpoint_c"):
                    if row.get(field):
                        optional_temp_fields_present.add(field)
        if (case_dir / "annotations.csv").exists():
            annotation_files += 1
    coverage = {
        "power_rows": power_rows,
        "temperature_rows": temp_rows,
        "power_scope_counts": dict(sorted(scope_counts.items())),
        "power_quality_counts": dict(sorted(power_quality_counts.items())),
        "temperature_position_counts": dict(sorted(position_counts.items())),
        "temperature_role_counts": dict(sorted(role_counts.items())),
        "temperature_quality_counts": dict(sorted(temp_quality_counts.items())),
        "optional_power_fields_present": sorted(optional_power_fields_present),
        "optional_temperature_fields_present": sorted(optional_temp_fields_present),
        "annotation_files": annotation_files,
    }
    required_scopes = {"feed_total", "outlet", "total_cabinet", "unknown"}
    required_positions = {"front_top", "front_middle", "front_bottom", "ambient"}
    if not required_scopes.issubset(scope_counts):
        failures.append(f"input corpus missing power scopes: {sorted(required_scopes - set(scope_counts))}")
    if not required_positions.issubset(position_counts):
        failures.append(f"input corpus missing temperature positions: {sorted(required_positions - set(position_counts))}")
    if not {"estimated", "stale"}.issubset(power_quality_counts):
        failures.append("input corpus missing estimated or stale power quality rows")
    if not {"estimated", "stale"}.issubset(temp_quality_counts):
        failures.append("input corpus missing estimated or stale temperature quality rows")
    if len(optional_power_fields_present) < 5:
        failures.append("input corpus does not exercise all optional electrical-detail fields")
    if len(optional_temp_fields_present) < 2:
        failures.append("input corpus does not exercise humidity and dewpoint fields")
    if annotation_files < 3:
        failures.append("input corpus does not include enough offline annotation examples")
    return coverage, failures


def _benchmark_schema_failures(envelope: CabinetEnvelope, summary: Summary) -> list[str]:
    failures: list[str] = []
    try:
        CabinetEnvelope.model_validate(envelope.model_dump(mode="json"))
    except Exception as exc:
        failures.append(f"envelope schema validation failed: {exc}")
    try:
        Summary.model_validate(summary.model_dump(mode="json"))
    except Exception as exc:
        failures.append(f"summary schema validation failed: {exc}")
    required_envelope = {
        "cabinet_id",
        "generated_at",
        "window",
        "envelope_status",
        "confidence",
        "recommended_sustained_kw",
        "recommended_short_burst_kw",
        "limiting_factor",
        "observed_power",
        "observed_temperature",
        "electrical",
        "thermal",
        "review_lane",
        "sales_ops_guardrail",
        "reason_codes",
        "warnings",
        "blockers",
        "missing_data",
        "assumptions",
    }
    payload = envelope.model_dump(mode="json")
    missing = required_envelope - set(payload)
    if missing:
        failures.append(f"envelope missing required fields: {sorted(missing)}")
    return failures


def _benchmark_language_failures(case_dir: Path, envelope: CabinetEnvelope) -> list[str]:
    failures: list[str] = []
    guardrail = envelope.sales_ops_guardrail.text
    if "review-only" not in guardrail.lower():
        failures.append("guardrail text missing review-only language")
    if BENCHMARK_FORBIDDEN_LANGUAGE.search(guardrail):
        failures.append("guardrail text contains forbidden commitment language")
    return failures


def _benchmark_output_coverage(results: list[dict[str, object]], envelopes: list[CabinetEnvelope]) -> tuple[dict[str, object], list[str]]:
    failures: list[str] = []
    status_counts = Counter(str(row["envelope_status"]) for row in results)
    review_lane_counts = Counter(str((envelope.review_lane or {}).get("lane")) for envelope in envelopes if envelope.review_lane)
    confidence_counts = Counter(str(row["confidence"]) for row in results)
    limiting_counts = Counter(str(row["limiting_factor"]) for row in results)
    warning_counts: Counter[str] = Counter()
    blocker_counts: Counter[str] = Counter()
    insufficient_with_recommendations: list[str] = []
    missing_action_queue: list[str] = []
    for envelope in envelopes:
        warning_counts.update(envelope.warnings)
        blocker_counts.update(envelope.blockers)
        if envelope.envelope_status == "INSUFFICIENT_DATA" and (
            envelope.recommended_sustained_kw is not None or envelope.recommended_short_burst_kw is not None
        ):
            insufficient_with_recommendations.append(envelope.cabinet_id)
        if not (envelope.review_lane or {}).get("next_actions"):
            missing_action_queue.append(envelope.cabinet_id)
    required_statuses = {"READY_FOR_REVIEW", "REVIEW_REQUIRED", "DO_NOT_EXPAND", "INSUFFICIENT_DATA"}
    required_lanes = {"READY_FOR_FACILITY_REVIEW", "NEEDS_REMEDIATION", "STOP_EXPANSION_DISCUSSION", "COLLECT_EVIDENCE"}
    required_limiters = {"ELECTRICAL", "THERMAL", "DATA_QUALITY"}
    if not required_statuses.issubset(status_counts):
        failures.append(f"output corpus missing statuses: {sorted(required_statuses - set(status_counts))}")
    if not required_lanes.issubset(review_lane_counts):
        failures.append(f"output corpus missing review lanes: {sorted(required_lanes - set(review_lane_counts))}")
    if not required_limiters.issubset(limiting_counts):
        failures.append(f"output corpus missing limiting factors: {sorted(required_limiters - set(limiting_counts))}")
    if status_counts["READY_FOR_REVIEW"] < 3:
        failures.append("output corpus needs at least three ready-for-review cases")
    if limiting_counts["THERMAL"] < 3:
        failures.append("output corpus needs at least three thermal-limited cases")
    if insufficient_with_recommendations:
        failures.append(f"insufficient-data envelopes exposed numeric recommendations: {insufficient_with_recommendations}")
    if missing_action_queue:
        failures.append(f"envelopes missing action queue: {missing_action_queue}")
    if warning_counts["REVIEW_ONLY_OUTPUT"]:
        failures.append("REVIEW_ONLY_OUTPUT must not appear as a warning")
    coverage = {
        "status_counts": dict(sorted(status_counts.items())),
        "review_lane_counts": dict(sorted(review_lane_counts.items())),
        "confidence_counts": dict(sorted(confidence_counts.items())),
        "limiting_factor_counts": dict(sorted(limiting_counts.items())),
        "top_warnings": warning_counts.most_common(12),
        "top_blockers": blocker_counts.most_common(12),
        "insufficient_data_with_numeric_recommendations": insufficient_with_recommendations,
    }
    return coverage, failures


@app.command("benchmark")
def benchmark_command(
    output_dir: Path = typer.Option(..., "--output-dir", help="Benchmark corpus output directory."),
    days: int = typer.Option(7, "--days"),
    bucket_minutes: int = typer.Option(5, "--bucket-minutes"),
    seed: int = typer.Option(1, "--seed"),
) -> None:
    try:
        scenario_root = output_dir / "scenarios"
        manifests = generate_all_scenarios(scenario_root, days=days, bucket_minutes=bucket_minutes, seed=seed)
        results = []
        envelopes: list[CabinetEnvelope] = []
        schema_failures: list[str] = []
        for manifest in manifests:
            case_dir = scenario_root / manifest.scenario
            _loaded, _alignment, envelope, summary_model = _prepare_estimate(
                case_dir / "pdu_power.csv",
                case_dir / "inlet_temps.csv",
                case_dir / "cabinet_profile.yml",
                case_dir / "thresholds.yml",
                days,
                bucket_minutes,
                False,
                SYNTHETIC_NOW.isoformat().replace("+00:00", "Z"),
            )
            envelopes.append(envelope)
            write_json(case_dir / "expected_envelope.json", envelope)
            expected = manifest.expected
            failures: list[str] = []
            failures.extend(_benchmark_schema_failures(envelope, summary_model))
            failures.extend(_benchmark_language_failures(case_dir, envelope))
            if expected.get("envelope_status") and expected["envelope_status"] != envelope.envelope_status:
                failures.append(f"envelope_status expected {expected['envelope_status']} got {envelope.envelope_status}")
            if expected.get("confidence") and expected["confidence"] != envelope.confidence:
                failures.append(f"confidence expected {expected['confidence']} got {envelope.confidence}")
            if expected.get("limiting_factor") and expected["limiting_factor"] != envelope.limiting_factor:
                failures.append(f"limiting_factor expected {expected['limiting_factor']} got {envelope.limiting_factor}")
            if expected.get("recommended_sustained_kw_range"):
                low, high = expected["recommended_sustained_kw_range"]
                if envelope.recommended_sustained_kw is None or not (low <= envelope.recommended_sustained_kw <= high):
                    failures.append(f"recommended_sustained_kw expected range {low}..{high} got {envelope.recommended_sustained_kw}")
            if expected.get("recommended_short_burst_kw_range"):
                low, high = expected["recommended_short_burst_kw_range"]
                if envelope.recommended_short_burst_kw is None or not (low <= envelope.recommended_short_burst_kw <= high):
                    failures.append(f"recommended_short_burst_kw expected range {low}..{high} got {envelope.recommended_short_burst_kw}")
            for key in ("reason_codes", "warnings", "missing_data", "blockers"):
                actual = set(getattr(envelope, key))
                for code in expected.get(key, []):
                    if code not in actual:
                        failures.append(f"{key} missing {code}")
            results.append(
                {
                    "scenario": manifest.scenario,
                    "cabinet_id": envelope.cabinet_id,
                    "envelope_status": envelope.envelope_status,
                    "confidence": envelope.confidence,
                    "limiting_factor": envelope.limiting_factor,
                    "passed": not failures,
                    "failures": failures,
                }
            )
            schema_failures.extend(f"{manifest.scenario}: {failure}" for failure in failures if "schema" in failure or "missing required fields" in failure)
        input_coverage, input_failures = _benchmark_input_coverage(scenario_root)
        output_coverage, output_failures = _benchmark_output_coverage(results, envelopes)
        realism_failures = input_failures + output_failures
        benchmark = {
            "schema_version": "cabinet-burst-envelope.benchmark.v1",
            "scenario_count": len(results),
            "schema_checks_passed": not schema_failures,
            "realism_checks_passed": not realism_failures,
            "passed": all(row["passed"] for row in results) and not schema_failures and not realism_failures,
            "failed_scenarios": [row["scenario"] for row in results if not row["passed"]],
            "schema_failures": schema_failures,
            "realism_failures": realism_failures,
            "input_coverage": input_coverage,
            "output_coverage": output_coverage,
            "results": results,
        }
        write_json(output_dir / "benchmark.json", benchmark)
        lines = [
            "# Synthetic Benchmark",
            "",
            f"- Scenario count: {len(results)}",
            f"- Scenario contracts passed: {all(row['passed'] for row in results)}",
            f"- Schema checks passed: {benchmark['schema_checks_passed']}",
            f"- Realism checks passed: {benchmark['realism_checks_passed']}",
            f"- Passed: {benchmark['passed']}",
            "",
        ]
        if realism_failures:
            lines.append("## Realism Failures")
            lines.extend(f"- {failure}" for failure in realism_failures)
            lines.append("")
        lines.extend(f"- {row['scenario']}: {'PASS' if row['passed'] else 'FAIL'}" for row in results)
        (output_dir / "benchmark.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    except Exception as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(json.dumps({"scenario_count": len(results), "passed": benchmark["passed"], "output_dir": str(output_dir)}, indent=2))


@app.command("pilot-intake")
def pilot_intake_command(
    input_root: Path = typer.Option(..., "--input-root", exists=True, help="Root containing anonymized normalized pilot cabinet cases."),
    output_json: Path = typer.Option(..., "--output-json", help="Pilot report JSON output."),
    output_markdown: Optional[Path] = typer.Option(None, "--output-markdown", help="Pilot report Markdown output."),
    outcomes_csv: Optional[Path] = typer.Option(None, "--outcomes-csv", exists=False, help="Optional anonymized facility outcome CSV."),
    config_path: Optional[Path] = typer.Option(None, "--config", help="Optional threshold override YAML."),
    policy_pack: Optional[str] = typer.Option(None, "--policy-pack", help="Built-in policy pack name or YAML path."),
    window_days: int = typer.Option(7, "--window-days"),
    bucket_minutes: int = typer.Option(5, "--bucket-minutes"),
    now: Optional[str] = typer.Option(None, "--now", help="Analysis window end in ISO 8601."),
    format_: str = typer.Option("text", "--format", help="Use json for stdout."),
) -> None:
    envelopes: list[CabinetEnvelope] = []
    summaries: list[Summary] = []
    errors: list[dict[str, str]] = []
    for case_dir in find_cabinet_cases(input_root):
        case_config = config_path or ((case_dir / "thresholds.yml") if (case_dir / "thresholds.yml").exists() else None)
        try:
            _loaded, _alignment, envelope, summary_model = _prepare_estimate(
                case_dir / "pdu_power.csv",
                case_dir / "inlet_temps.csv",
                case_dir / "cabinet_profile.yml",
                case_config,
                window_days,
                bucket_minutes,
                False,
                now,
                policy_pack,
            )
            envelopes.append(envelope)
            summaries.append(summary_model)
        except Exception as exc:
            errors.append({"case_dir": str(case_dir), "error": str(exc)})
    outcomes = load_pilot_outcomes(outcomes_csv)
    report = build_pilot_report(envelopes, summaries, outcomes)
    report["case_errors"] = errors
    write_json(output_json, report)
    if output_markdown:
        output_markdown.parent.mkdir(parents=True, exist_ok=True)
        output_markdown.write_text(render_pilot_markdown(report), encoding="utf-8")
    if format_ == "json":
        typer.echo(json.dumps(report, indent=2))
    else:
        typer.echo(json.dumps({"cabinet_count": report["cabinet_count"], "outcome_count": report["outcome_count"], "case_errors": len(errors)}, indent=2))


@app.command("business-impact")
def business_impact_command(
    input_root: Path = typer.Option(..., "--input-root", exists=True, help="Root containing normalized cabinet case directories."),
    output_json: Path = typer.Option(..., "--output-json", help="Business-impact report JSON output."),
    output_markdown: Optional[Path] = typer.Option(None, "--output-markdown", help="Business-impact report Markdown output."),
    config_path: Optional[Path] = typer.Option(None, "--config", help="Optional threshold override YAML."),
    policy_pack: Optional[str] = typer.Option(None, "--policy-pack", help="Built-in policy pack name or YAML path."),
    window_days: int = typer.Option(7, "--window-days"),
    bucket_minutes: int = typer.Option(5, "--bucket-minutes"),
    now: Optional[str] = typer.Option(None, "--now", help="Analysis window end in ISO 8601."),
    format_: str = typer.Option("text", "--format", help="Use json for stdout."),
) -> None:
    envelopes: list[CabinetEnvelope] = []
    summaries: list[Summary] = []
    errors: list[dict[str, str]] = []
    for case_dir in find_cabinet_cases(input_root):
        case_config = config_path or ((case_dir / "thresholds.yml") if (case_dir / "thresholds.yml").exists() else None)
        try:
            _loaded, _alignment, envelope, summary_model = _prepare_estimate(
                case_dir / "pdu_power.csv",
                case_dir / "inlet_temps.csv",
                case_dir / "cabinet_profile.yml",
                case_config,
                window_days,
                bucket_minutes,
                False,
                now,
                policy_pack,
            )
            envelopes.append(envelope)
            summaries.append(summary_model)
        except Exception as exc:
            errors.append({"case_dir": str(case_dir), "error": str(exc)})
    pilot_report = build_pilot_report(envelopes, summaries, {})
    impact = {
        "schema_version": "cabinet-burst-envelope.business_impact.v1",
        "cabinet_count": pilot_report["cabinet_count"],
        "status_counts": pilot_report["status_counts"],
        "review_lane_counts": pilot_report["review_lane_counts"],
        "confidence_counts": pilot_report["confidence_counts"],
        "limiting_factor_counts": pilot_report["limiting_factor_counts"],
        "remediation_category_counts": pilot_report["remediation_category_counts"],
        "action_owner_counts": pilot_report["action_owner_counts"],
        "business_impact": pilot_report["business_impact"],
        "generator_calibration_hints": pilot_report["generator_calibration_hints"],
        "case_errors": errors,
        "caveat": "Review-only workflow metrics. This report is not capacity approval, pricing, quoting, or a customer commitment.",
    }
    write_json(output_json, impact)
    if output_markdown:
        lines = [
            "# Business Impact Report",
            "",
            impact["caveat"],
            "",
            f"- Cabinets: {impact['cabinet_count']}",
            f"- Status counts: {impact['status_counts']}",
            f"- Review lane counts: {impact['review_lane_counts']}",
            f"- Limiting factor counts: {impact['limiting_factor_counts']}",
            f"- Remediation categories: {impact['remediation_category_counts']}",
            f"- Action owners: {impact['action_owner_counts']}",
            "",
            "## Workflow Metrics",
        ]
        lines.extend(f"- {key}: {value}" for key, value in impact["business_impact"].items())
        lines.extend(["", "## Calibration Hints"])
        lines.extend(f"- {hint}" for hint in impact["generator_calibration_hints"] or ["No calibration hints generated."])
        output_markdown.parent.mkdir(parents=True, exist_ok=True)
        output_markdown.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if format_ == "json":
        typer.echo(json.dumps(impact, indent=2))
    else:
        typer.echo(json.dumps({"cabinet_count": impact["cabinet_count"], "case_errors": len(errors)}, indent=2))


@app.command("explain")
def explain_command(
    envelope: Path = typer.Option(..., "--envelope", exists=True, help="Envelope JSON from estimate."),
    output_markdown: Optional[Path] = typer.Option(None, "--output-markdown", help="Output explanation Markdown."),
    output_json: Optional[Path] = typer.Option(None, "--output-json", help="Output machine-readable explanation JSON."),
    format_: str = typer.Option("text", "--format", help="Use json for stdout."),
) -> None:
    try:
        with envelope.open("r", encoding="utf-8") as handle:
            loaded = json.load(handle)
        envelope_model = CabinetEnvelope.model_validate(loaded)
    except Exception as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc

    if output_markdown:
        write_explanation_markdown(output_markdown, envelope_model)
        typer.echo(f"wrote {output_markdown}")
    if output_json:
        write_explanation_json(output_json, envelope_model)
        typer.echo(f"wrote {output_json}")
    if not output_markdown and not output_json:
        from .report import render_explanation_json, render_explanation_markdown

        if format_ == "json":
            typer.echo(json.dumps(render_explanation_json(envelope_model), indent=2, default=str))
        else:
            typer.echo(render_explanation_markdown(envelope_model))


@app.command("drift")
def drift_command(
    previous_envelope: Path = typer.Option(..., "--previous-envelope", exists=True, help="Previous envelope JSON."),
    current_envelope: Path = typer.Option(..., "--current-envelope", exists=True, help="Current envelope JSON."),
    output_json: Optional[Path] = typer.Option(None, "--output-json", help="Output drift JSON."),
    output_markdown: Optional[Path] = typer.Option(None, "--output-markdown", help="Output drift Markdown."),
    format_: str = typer.Option("text", "--format", help="Use json for stdout."),
) -> None:
    try:
        previous = CabinetEnvelope.model_validate(json.loads(previous_envelope.read_text(encoding="utf-8")))
        current = CabinetEnvelope.model_validate(json.loads(current_envelope.read_text(encoding="utf-8")))
        drift = compare_envelopes(previous, current)
    except Exception as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    if output_json:
        write_json(output_json, drift)
    if output_markdown:
        Path(output_markdown).parent.mkdir(parents=True, exist_ok=True)
        Path(output_markdown).write_text(render_drift_markdown(drift), encoding="utf-8")
    typer.echo(json.dumps(drift, indent=2) if format_ == "json" else render_drift_markdown(drift))


@app.command("worksheet")
def worksheet_command(
    envelope: Path = typer.Option(..., "--envelope", exists=True, help="Envelope JSON from estimate."),
    output_markdown: Path = typer.Option(..., "--output-markdown", help="Facility worksheet Markdown."),
) -> None:
    try:
        envelope_model = CabinetEnvelope.model_validate(json.loads(envelope.read_text(encoding="utf-8")))
    except Exception as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    output_markdown.parent.mkdir(parents=True, exist_ok=True)
    output_markdown.write_text(render_facility_review_worksheet(envelope_model), encoding="utf-8")
    typer.echo(f"wrote {output_markdown}")


@app.command("redact-bundle")
def redact_bundle_command(
    input_dir: Path = typer.Option(..., "--input", exists=True, help="Input bundle or case directory."),
    output_dir: Path = typer.Option(..., "--output", help="Redacted output directory."),
) -> None:
    try:
        manifest = redact_bundle(input_dir, output_dir)
    except Exception as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"wrote redacted bundle to {output_dir} with {len(manifest.files)} file(s)")


@app.command("release-report")
def release_report_command(
    repo_root: Path = typer.Option(Path("."), "--repo-root", exists=True, help="Repository root to inventory."),
    output_dir: Path = typer.Option(..., "--output-dir", help="Release report output directory."),
) -> None:
    try:
        report = build_release_report(repo_root, output_dir)
    except Exception as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(json.dumps({"file_count": report["file_count"], "output_dir": str(output_dir)}, indent=2))
