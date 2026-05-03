from __future__ import annotations

import json
import zipfile
from pathlib import Path

import typer
import yaml

from .benchmark import benchmark_dataset_package
from .bundle_score import score_bundle_inputs, score_bundle_zip
from .config import load_config
from .contract_model import TransactionContract, contract_to_dict
from .dataset_model import init_dataset_package
from .dataset_validate import validate_dataset_package
from .drift_compare import compare_contract_to_trace
from .field_map import load_field_map
from .flow_extract import extract_transaction
from .label_sheet import generate_label_sheet
from .openapi_gen import generate_openapi
from .openapi_validate import run_external_openapi_validator, validate_openapi_document, validate_openapi_file
from .package_extract import extract_dataset_package
from .parse_trace import load_trace
from .privacy_report import generate_privacy_report
from .redact import REDACTED
from .real_world_data_generator import coverage_report, generate_adversarial_corpus, generate_real_world_corpus
from .realism_report import corpus_realism_report, package_realism_report
from .replay_driver import TraceReplayDriver
from .replay_gen import generate_pytest
from .replay_model import ReplayCase, replay_case_to_dict
from .report import write_json, write_text, write_yaml
from .review_package import build_review_package
from .sanitize_trace import sanitize_trace_events, write_sanitized_trace
from .trace_mutation import mutate_trace_events, parse_field_moves, parse_label_changes
from .trace_schema import ActionEvent, ScreenEvent
from .validate_trace import validate_trace

app = typer.Typer(help="Extract offline screen contracts from recorded terminal traces.")
dataset_app = typer.Typer(help="Create and validate local screen contract data packages.")
app.add_typer(dataset_app, name="dataset")


def _parse_screen_size(value: str | None) -> tuple[int, int] | None:
    if not value:
        return None
    try:
        rows, cols = value.lower().split("x", 1)
        return int(rows), int(cols)
    except Exception as exc:  # noqa: BLE001 - Typer shows concise error
        raise typer.BadParameter("screen size must look like 24x80") from exc


@app.command("validate-trace")
def validate_trace_command(
    trace: Path = typer.Option(..., "--trace", exists=True, dir_okay=False),
    strict: bool = typer.Option(False, "--strict"),
    screen_size: str | None = typer.Option(None, "--screen-size"),
    config: Path | None = typer.Option(None, "--config", exists=True, dir_okay=False),
) -> None:
    cfg = load_config(config)
    events = load_trace(trace)
    _ = cfg
    result = validate_trace(events, strict=strict, screen_size=_parse_screen_size(screen_size))
    payload = {
        "ok": result.ok,
        "warnings": result.warnings,
        "blockers": result.blockers,
    }
    typer.echo(json.dumps(payload, indent=2))
    if not result.ok:
        raise typer.Exit(1)


@app.command("extract")
def extract_command(
    trace: Path = typer.Option(..., "--trace", exists=True, dir_okay=False),
    field_map_path: Path | None = typer.Option(None, "--field-map", exists=True, dir_okay=False),
    transaction_id: str = typer.Option(..., "--transaction-id"),
    case_id: str | None = typer.Option(None, "--case-id"),
    case_kind: str = typer.Option("happy_path", "--case-kind"),
    output_contract: Path = typer.Option(..., "--output-contract"),
    output_openapi: Path = typer.Option(..., "--output-openapi"),
    output_replay_test: Path = typer.Option(..., "--output-replay-test"),
    output_replay_case: Path | None = typer.Option(None, "--output-replay-case"),
    summary: Path = typer.Option(..., "--summary"),
    redact: bool = typer.Option(False, "--redact"),
    strict: bool = typer.Option(False, "--strict"),
    screen_size: str | None = typer.Option(None, "--screen-size"),
    openapi_path: str | None = typer.Option(None, "--openapi-path"),
    config: Path | None = typer.Option(None, "--config", exists=True, dir_okay=False),
) -> None:
    cfg = load_config(config)
    events = load_trace(trace)
    field_map = load_field_map(field_map_path)
    replay_case_path = output_replay_case or output_contract.with_name(f"{output_contract.stem}.case.yml")
    outputs = {
        "contract": str(output_contract),
        "openapi": str(output_openapi),
        "replay_test": str(output_replay_test),
        "replay_case": str(replay_case_path),
    }
    result = extract_transaction(
        events,
        transaction_id=transaction_id,
        case_id=case_id,
        case_kind=case_kind,
        field_map=field_map,
        strict=strict,
        redact=redact,
        screen_size=_parse_screen_size(screen_size),
        openapi_path=openapi_path,
        config=cfg,
        output_paths=outputs,
    )
    if strict and result.contract.blockers:
        typer.echo(json.dumps({"ok": False, "blockers": result.contract.blockers}, indent=2))
        raise typer.Exit(1)

    write_yaml(output_contract, contract_to_dict(result.contract))
    openapi_doc = generate_openapi(result.contract)
    openapi_errors = validate_openapi_document(openapi_doc)
    if strict and openapi_errors:
        typer.echo(json.dumps({"ok": False, "blockers": openapi_errors}, indent=2))
        raise typer.Exit(1)
    write_yaml(output_openapi, openapi_doc)
    write_yaml(replay_case_path, replay_case_to_dict(result.replay_case))
    write_text(output_replay_test, generate_pytest(trace, output_contract, result.replay_case, replay_case_path))
    write_json(summary, result.summary)
    typer.echo(json.dumps({"ok": True, "summary": str(summary)}, indent=2))


@app.command("replay")
def replay_command(
    trace: Path = typer.Option(..., "--trace", exists=True, dir_okay=False),
    contract: Path = typer.Option(..., "--contract", exists=True, dir_okay=False),
    case: Path = typer.Option(..., "--case", exists=True, dir_okay=False),
    strict: bool = typer.Option(False, "--strict"),
    screen_size: str | None = typer.Option(None, "--screen-size"),
    config: Path | None = typer.Option(None, "--config", exists=True, dir_okay=False),
) -> None:
    cfg = load_config(config)
    _ = (cfg, strict, screen_size)
    events = load_trace(trace)
    loaded_contract = TransactionContract(**yaml.safe_load(contract.read_text()))
    replay_case = ReplayCase(**yaml.safe_load(case.read_text()))
    driver = TraceReplayDriver(events, loaded_contract)
    if driver.current_screen_hash() != replay_case.start_screen_hash:
        typer.echo("start screen hash mismatch", err=True)
        raise typer.Exit(1)
    for step in replay_case.steps:
        if driver.current_screen_hash() != step.expect_screen_hash:
            typer.echo("expected screen hash mismatch", err=True)
            raise typer.Exit(1)
        next_hash = driver.apply(step.aid, step.inputs)
        if next_hash != step.expect_next_screen_hash:
            typer.echo("next screen hash mismatch", err=True)
            raise typer.Exit(1)
    response = driver.extract_response()
    for name, expected in replay_case.expected_response.items():
        if expected != REDACTED and response.get(name) != expected:
            typer.echo(f"response mismatch for {name}", err=True)
            raise typer.Exit(1)
    driver.assert_no_unexpected_transition()
    typer.echo(json.dumps({"ok": True, "case_id": replay_case.case_id}, indent=2))


@app.command("validate-openapi")
def validate_openapi_command(
    openapi: Path = typer.Option(..., "--openapi", exists=True, dir_okay=False),
    output: Path | None = typer.Option(None, "--output"),
    external_validator_command: str | None = typer.Option(None, "--external-validator-command"),
) -> None:
    local_errors = validate_openapi_file(openapi)
    external = run_external_openapi_validator(openapi, external_validator_command)
    external_ok = external.get("skipped", False) or external.get("ok", False)
    result = {
        "schema_version": "1.0",
        "ok": not local_errors and external_ok,
        "local_errors": local_errors,
        "external": external,
    }
    if output:
        write_json(output, result)
    typer.echo(json.dumps(result, indent=2))
    if not result["ok"]:
        raise typer.Exit(1)


@dataset_app.command("init")
def dataset_init_command(
    package: Path = typer.Option(..., "--package"),
    transaction_id: str = typer.Option(..., "--transaction-id"),
    maturity_level: str = typer.Option("L0", "--maturity-level"),
) -> None:
    manifest = init_dataset_package(package, transaction_id=transaction_id, maturity_level=maturity_level)  # type: ignore[arg-type]
    typer.echo(json.dumps({"ok": True, "manifest": str(package / "manifest.yml"), "package_id": manifest.package_id}, indent=2))


@dataset_app.command("validate")
def dataset_validate_command(
    package: Path = typer.Option(..., "--package", exists=True, file_okay=False),
    strict: bool = typer.Option(False, "--strict"),
) -> None:
    result = validate_dataset_package(package, strict=strict)
    typer.echo(json.dumps(result, indent=2))
    if not result["ok"]:
        raise typer.Exit(1)


@app.command("sanitize-trace")
def sanitize_trace_command(
    trace: Path = typer.Option(..., "--trace", exists=True, dir_okay=False),
    output: Path = typer.Option(..., "--output"),
    field_map_path: Path | None = typer.Option(None, "--field-map", exists=True, dir_okay=False),
    report: Path | None = typer.Option(None, "--report"),
    tokenize: bool = typer.Option(False, "--tokenize"),
    token_salt: str = typer.Option("", "--token-salt"),
) -> None:
    field_map = load_field_map(field_map_path)
    sanitized, privacy_report = sanitize_trace_events(
        load_trace(trace),
        field_map=field_map,
        tokenize=tokenize,
        salt=token_salt,
    )
    write_sanitized_trace(output, sanitized)
    if report:
        write_json(report, privacy_report)
    typer.echo(json.dumps({"ok": True, "output": str(output), "report": str(report) if report else None}, indent=2))


@app.command("privacy-report")
def privacy_report_command(
    trace: Path = typer.Option(..., "--trace", exists=True, dir_okay=False),
    output: Path = typer.Option(..., "--output"),
    field_map_path: Path | None = typer.Option(None, "--field-map", exists=True, dir_okay=False),
    fail_on_sensitive_unredacted: bool = typer.Option(False, "--fail-on-sensitive-unredacted"),
) -> None:
    report = generate_privacy_report(load_trace(trace), load_field_map(field_map_path))
    write_json(output, report)
    typer.echo(json.dumps({"ok": True, "output": str(output), "unredacted_sensitive_value_count": report["unredacted_sensitive_value_count"]}, indent=2))
    if fail_on_sensitive_unredacted and report["unredacted_sensitive_value_count"]:
        raise typer.Exit(1)


@app.command("label-sheet")
def label_sheet_command(
    trace: Path = typer.Option(..., "--trace", exists=True, dir_okay=False),
    output: Path = typer.Option(..., "--output"),
    field_map_path: Path | None = typer.Option(None, "--field-map", exists=True, dir_okay=False),
    include_values: bool = typer.Option(False, "--include-values"),
) -> None:
    sheet = generate_label_sheet(load_trace(trace), field_map=load_field_map(field_map_path), include_values=include_values)
    write_yaml(output, sheet)
    typer.echo(json.dumps({"ok": True, "output": str(output), "field_count": sheet["field_count"]}, indent=2))


@app.command("compare")
def compare_command(
    contract: Path = typer.Option(..., "--contract", exists=True, dir_okay=False),
    trace: Path = typer.Option(..., "--trace", exists=True, dir_okay=False),
    output: Path = typer.Option(..., "--output"),
    field_map_path: Path | None = typer.Option(None, "--field-map", exists=True, dir_okay=False),
    config: Path | None = typer.Option(None, "--config", exists=True, dir_okay=False),
) -> None:
    result = compare_contract_to_trace(
        TransactionContract(**yaml.safe_load(contract.read_text())),
        load_trace(trace),
        field_map=load_field_map(field_map_path),
        config=load_config(config),
    )
    write_json(output, result)
    typer.echo(json.dumps({"ok": True, "status": result["status"], "output": str(output)}, indent=2))


@app.command("mutate-trace")
def mutate_trace_command(
    trace: Path = typer.Option(..., "--trace", exists=True, dir_okay=False),
    output: Path = typer.Option(..., "--output"),
    change_label: list[str] | None = typer.Option(None, "--change-label"),
    move_field: list[str] | None = typer.Option(None, "--move-field"),
) -> None:
    try:
        label_changes = parse_label_changes(change_label)
        field_moves = parse_field_moves(move_field)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    mutated = mutate_trace_events(load_trace(trace), label_changes=label_changes, field_moves=field_moves)
    write_sanitized_trace(output, mutated)
    typer.echo(json.dumps({"ok": True, "output": str(output), "event_count": len(mutated)}, indent=2))


@app.command("benchmark")
def benchmark_command(
    package: Path = typer.Option(..., "--package", exists=True, file_okay=False),
    output: Path = typer.Option(..., "--output"),
) -> None:
    _benchmark_package(package, output)


@dataset_app.command("benchmark")
def dataset_benchmark_command(
    package: Path = typer.Option(..., "--package", exists=True, file_okay=False),
    output: Path = typer.Option(..., "--output"),
) -> None:
    _benchmark_package(package, output)


def _benchmark_package(package: Path, output: Path) -> None:
    result = benchmark_dataset_package(package)
    write_json(output, result)
    typer.echo(json.dumps({"ok": True, "output": str(output), "trace_count": result["trace_count"]}, indent=2))


@app.command("extract-package")
def extract_package_command(
    package: Path = typer.Option(..., "--package", exists=True, file_okay=False),
    output_dir: Path = typer.Option(..., "--output-dir"),
    output_contract: Path | None = typer.Option(None, "--output-contract"),
    output_openapi: Path | None = typer.Option(None, "--output-openapi"),
    output_replay_test: Path | None = typer.Option(None, "--output-replay-test"),
    output_drift_baseline: Path | None = typer.Option(None, "--output-drift-baseline"),
    summary: Path | None = typer.Option(None, "--summary"),
    strict: bool = typer.Option(False, "--strict"),
) -> None:
    result = extract_dataset_package(
        package,
        output_dir=output_dir,
        output_contract=output_contract,
        output_openapi=output_openapi,
        output_replay_test=output_replay_test,
        output_drift_baseline=output_drift_baseline,
        output_summary=summary,
        strict=strict,
    )
    typer.echo(
        json.dumps(
            {
                "ok": not result.get("blockers"),
                "case_count": result["case_count"],
                "canonical_case_count": result.get("canonical_case_count"),
                "drift_case_count": result.get("drift_case_count"),
                "canonical_contract": result.get("canonical_contract"),
                "api_candidate": result.get("api_candidate"),
                "drift_evidence": result.get("drift_evidence"),
                "flow_graph": result.get("flow_graph"),
                "replay_test": result.get("combined_replay_test"),
                "legacy_contract": result.get("combined_contract"),
                "legacy_openapi": result.get("combined_openapi"),
                "drift_baseline": result.get("drift_baseline"),
            },
            indent=2,
        )
    )
    if strict and result.get("blockers"):
        raise typer.Exit(1)


@app.command("review-package")
def review_package_command(
    package: Path = typer.Option(..., "--package", exists=True, file_okay=False),
    output_dir: Path = typer.Option(..., "--output-dir"),
    strict: bool = typer.Option(False, "--strict"),
) -> None:
    result = build_review_package(package, output_dir=output_dir, strict=strict)
    typer.echo(
        json.dumps(
            {
                "ok": result["ok"],
                "review_package_status": result["review_package_status"],
                "output_dir": result["output_dir"],
                "readiness": result["readiness"],
                "executive_summary": result["executive_summary"],
                "bundle": result["bundle"]["path"],
            },
            indent=2,
        )
    )
    if strict and not result["ok"]:
        raise typer.Exit(1)


@app.command("generate-corpus")
def generate_corpus_command(
    output: Path = typer.Option(..., "--output"),
    seed: int = typer.Option(123, "--seed"),
) -> None:
    result = generate_real_world_corpus(output, seed=seed)
    write_json(output / "coverage.json", result["coverage"])
    typer.echo(json.dumps({"ok": True, "output": str(output), "package_count": result["package_count"], "coverage_complete": result["coverage"]["complete"]}, indent=2))


@app.command("generate-adversarial-corpus")
def generate_adversarial_corpus_command(
    output: Path = typer.Option(..., "--output"),
) -> None:
    result = generate_adversarial_corpus(output)
    write_json(output / "adversarial.json", result)
    typer.echo(json.dumps({"ok": True, "output": str(output), "package_count": result["package_count"]}, indent=2))


@app.command("coverage-report")
def coverage_report_command(
    package_root: Path = typer.Option(..., "--package-root", exists=True, file_okay=False),
    output: Path | None = typer.Option(None, "--output"),
) -> None:
    result = coverage_report(package_root)
    if output:
        write_json(output, result)
    typer.echo(json.dumps(result, indent=2))
    if not result["complete"]:
        raise typer.Exit(1)


@app.command("realism-report")
def realism_report_command(
    package: Path | None = typer.Option(None, "--package", exists=True, file_okay=False),
    package_root: Path | None = typer.Option(None, "--package-root", exists=True, file_okay=False),
    output: Path | None = typer.Option(None, "--output"),
) -> None:
    if bool(package) == bool(package_root):
        raise typer.BadParameter("provide exactly one of --package or --package-root")
    result = package_realism_report(package) if package else corpus_realism_report(package_root)  # type: ignore[arg-type]
    if output:
        write_json(output, result)
    typer.echo(json.dumps(result, indent=2))


@app.command("bundle")
def bundle_command(
    output: Path = typer.Option(..., "--output"),
    contract: Path | None = typer.Option(None, "--contract", exists=True, dir_okay=False),
    openapi: Path | None = typer.Option(None, "--openapi", exists=True, dir_okay=False),
    replay_case: Path | None = typer.Option(None, "--replay-case", exists=True, dir_okay=False),
    replay_test: Path | None = typer.Option(None, "--replay-test", exists=True, dir_okay=False),
    summary: Path | None = typer.Option(None, "--summary", exists=True, dir_okay=False),
    privacy_report_path: Path | None = typer.Option(None, "--privacy-report", exists=True, dir_okay=False),
) -> None:
    files = {
        "contract.yml": contract,
        "openapi.yml": openapi,
        "replay_case.yml": replay_case,
        "replay_test.py": replay_test,
        "summary.json": summary,
        "privacy_report.json": privacy_report_path,
    }
    included = {name: path for name, path in files.items() if path is not None}
    completeness = score_bundle_inputs(files)
    manifest = {"schema_version": "1.0", "generated_by": "host-screen-contracts", "files": sorted(included), "completeness": completeness}
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for archive_name, path in included.items():
            bundle.write(path, archive_name)
        bundle.writestr("manifest.json", json.dumps(manifest, indent=2) + "\n")
    typer.echo(json.dumps({"ok": True, "output": str(output), "file_count": len(included), "completeness": completeness}, indent=2))


@app.command("bundle-score")
def bundle_score_command(
    bundle: Path = typer.Option(..., "--bundle", exists=True, dir_okay=False),
    output: Path | None = typer.Option(None, "--output"),
) -> None:
    result = score_bundle_zip(bundle)
    if output:
        write_json(output, result)
    typer.echo(json.dumps(result, indent=2))


@app.command("record-manual")
def record_manual_command(
    output: Path = typer.Option(..., "--output"),
    rows: int = typer.Option(24, "--rows"),
    cols: int = typer.Option(80, "--cols"),
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    events: list[dict] = []
    seq = 1
    while True:
        typer.echo("Paste screen text. End with a single '.' line.")
        lines: list[str] = []
        while True:
            line = typer.prompt("")
            if line == ".":
                break
            lines.append(line)
        fields: list[dict] = []
        while typer.confirm("Add a screen field?", default=False):
            row = int(typer.prompt("row"))
            col = int(typer.prompt("col"))
            length = int(typer.prompt("length"))
            protected = typer.confirm("protected?", default=False)
            value = typer.prompt("value", default="")
            fields.append(
                {
                    "id": f"f_{row:02d}_{col:02d}",
                    "row": row,
                    "col": col,
                    "length": length,
                    "value": value,
                    "protected": protected,
                    "display_only": protected,
                    "hidden": False,
                    "attributes": [],
                }
            )
        events.append(
            ScreenEvent(
                type="screen",
                seq=seq,
                rows=rows,
                cols=cols,
                cursor=None,
                text=lines,
                fields=fields,
            ).model_dump(mode="json", exclude_none=True)
        )
        seq += 1
        if not typer.confirm("Add action and continue?", default=True):
            break
        aid = typer.prompt("AID", default="ENTER").upper()
        inputs: list[dict] = []
        while typer.confirm("Add action input?", default=False):
            field_id = typer.prompt("field_id", default="")
            row_text = typer.prompt("row", default="")
            col_text = typer.prompt("col", default="")
            value = typer.prompt("value", default="")
            item = {"value": value}
            if field_id:
                item["field_id"] = field_id
            if row_text and col_text:
                item["row"] = int(row_text)
                item["col"] = int(col_text)
            inputs.append(item)
        events.append(
            ActionEvent(type="action", seq=seq, aid=aid, cursor=None, inputs=inputs).model_dump(
                mode="json", exclude_none=True
            )
        )
        seq += 1
    output.write_text("\n".join(json.dumps(event) for event in events) + "\n")
    typer.echo(json.dumps({"ok": True, "output": str(output)}, indent=2))


if __name__ == "__main__":
    app()
