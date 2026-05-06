from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest
import yaml

from host_screen_contracts.adapter_protocol import ScreenFieldSnapshot, ScreenSnapshot, TraceWriter
from host_screen_contracts.benchmark import benchmark_dataset_package
from host_screen_contracts.bundle_score import score_bundle_members, score_bundle_zip
from host_screen_contracts.config import load_config
from host_screen_contracts.contract_model import TransactionContract, contract_to_dict
from host_screen_contracts import pipeline
from host_screen_contracts import dataset_validate
from host_screen_contracts.dataset_model import DatasetManifest, infer_case_kind, infer_case_purpose, init_dataset_package, load_dataset_manifest, manifest_cases
from host_screen_contracts.dataset_validate import validate_dataset_package
from host_screen_contracts.drift_compare import compare_contract_to_trace
from host_screen_contracts.executive_summary import render_executive_summary
from host_screen_contracts.field_map import load_field_map
from host_screen_contracts.label_sheet import generate_label_sheet
from host_screen_contracts.package_extract import extract_dataset_package
from host_screen_contracts.parse_trace import load_trace
from host_screen_contracts.openapi_validate import validate_openapi_document
from host_screen_contracts.privacy_report import generate_privacy_report
from host_screen_contracts.readiness import assess_review_readiness
from host_screen_contracts.real_world_data_generator import coverage_report, generate_adversarial_corpus, generate_real_world_corpus
from host_screen_contracts.realism_report import corpus_realism_report, package_realism_report
from host_screen_contracts.replay_driver import TraceReplayDriver
from host_screen_contracts.sanitize_trace import sanitize_trace_events, write_sanitized_trace
from host_screen_contracts.screen_hash import compute_screen_hashes
from host_screen_contracts.synthetic_package import SyntheticPackageBuilder, SyntheticPackageSpec, case_spec
from host_screen_contracts.tokenize import stable_token
from host_screen_contracts.trace_mutation import mutate_trace_events, parse_field_moves, parse_label_changes


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


def test_sanitize_trace_redacts_sensitive_values_and_reports_findings():
    events = load_trace(EXAMPLES / "customer_update.trace.jsonl")
    fmap = load_field_map(EXAMPLES / "customer_update.fields.yml")
    sanitized, report = sanitize_trace_events(events, field_map=fmap)
    action = sanitized[1]
    assert action["inputs"][0]["value"] == "<REDACTED>"
    assert action["inputs"][1]["value"] == "5550100"
    assert report["unredacted_sensitive_value_count"] == 0


def test_tokenized_sanitization_is_deterministic():
    events = load_trace(EXAMPLES / "customer_update.trace.jsonl")
    fmap = load_field_map(EXAMPLES / "customer_update.fields.yml")
    first, _ = sanitize_trace_events(events, field_map=fmap, tokenize=True, salt="test")
    second, _ = sanitize_trace_events(events, field_map=fmap, tokenize=True, salt="test")
    assert first[1]["inputs"][0]["value"] == second[1]["inputs"][0]["value"]
    assert first[1]["inputs"][0]["value"].startswith("<REDACTED:")
    assert stable_token("abc", salt="x") == stable_token("abc", salt="x")


def test_privacy_report_flags_unredacted_sensitive_values():
    events = load_trace(EXAMPLES / "customer_update.trace.jsonl")
    fmap = load_field_map(EXAMPLES / "customer_update.fields.yml")
    report = generate_privacy_report(events, fmap)
    assert report["unredacted_sensitive_value_count"] == 1
    assert report["findings"][0]["name"] == "account_number"
    assert report["findings"][0]["severity"] == "HIGH"
    assert report["unredacted_severity_counts"]["HIGH"] == 1
    assert report["highest_unredacted_severity"] == "HIGH"


def test_label_sheet_generates_reviewable_fields(order_events, order_field_map):
    sheet = generate_label_sheet(order_events, field_map=order_field_map)
    assert sheet["field_count"] >= 3
    assert any(field["proposed_name"] == "order_number" for field in sheet["fields"])


def test_compare_contract_to_trace_reports_compatible(order_events, order_result, order_field_map):
    result = compare_contract_to_trace(order_result().contract, order_events, field_map=order_field_map)
    assert result["status"] == "compatible"
    assert result["changes"] == []


def test_mutation_and_compare_detect_label_drift(order_events, order_result, order_field_map):
    mutated = mutate_trace_events(order_events, label_changes=[("Status", "State")])
    result = compare_contract_to_trace(
        order_result().contract,
        [type(event).model_validate(item) for event, item in zip(order_events, mutated, strict=False)],
        field_map=order_field_map,
    )
    assert result["status"] == "review_required"
    assert result["changes"][0]["kind"] == "labels_changed"


def test_mutation_and_compare_detect_field_move(order_events, order_result, order_field_map):
    moves = parse_field_moves(["f_05_32:+0,+2"])
    mutated = mutate_trace_events(order_events, field_moves=moves)
    result = compare_contract_to_trace(
        order_result().contract,
        [type(event).model_validate(item) for event, item in zip(order_events, mutated, strict=False)],
        field_map=order_field_map,
    )
    assert result["status"] == "breaking_change"
    assert any(change["kind"] == "field_moved_or_resized" for change in result["changes"])


def test_compare_contract_to_trace_detects_count_unknown_and_path_changes(order_events, order_result, order_field_map):
    contract = order_result().contract
    missing_screen = compare_contract_to_trace(contract, order_events[:-1], field_map=order_field_map)
    assert any(change["kind"] == "screen_count_changed" for change in missing_screen["changes"])

    extra_screen = order_events + [order_events[-1].model_copy(update={"seq": 5})]
    unknown = compare_contract_to_trace(contract, extra_screen, field_map=order_field_map)
    assert any(change["kind"] == "unknown_screen" for change in unknown["changes"])

    changed_action = [
        event.model_copy(update={"aid": "F3"}) if getattr(event, "type", None) == "action" else event
        for event in order_events
    ]
    path_changed = compare_contract_to_trace(contract, changed_action, field_map=order_field_map)
    assert any(change["kind"] == "replay_path_changed" for change in path_changed["changes"])


def test_parse_label_changes_requires_old_new():
    assert parse_label_changes(["Status:State"]) == [("Status", "State")]


def test_dataset_package_validate_and_benchmark(tmp_path):
    package = tmp_path / "pkg"
    init_dataset_package(package, transaction_id="order_lookup", maturity_level="L1")
    (package / "traces" / "happy_path.trace.jsonl").write_text((EXAMPLES / "order_lookup.trace.jsonl").read_text())
    (package / "field_maps" / "transaction.fields.yml").write_text((EXAMPLES / "order_lookup.fields.yml").read_text())
    validation = validate_dataset_package(package)
    benchmark = benchmark_dataset_package(package)
    assert validation["ok"]
    assert benchmark["trace_count"] == 1
    assert benchmark["contract_ready_count"] == 1


def test_dataset_validation_and_benchmark_report_parse_failures(tmp_path):
    package = tmp_path / "bad_pkg"
    init_dataset_package(package, transaction_id="order_lookup", maturity_level="L1")
    (package / "traces" / "happy_path.trace.jsonl").write_text('{"type":"screen","seq":1}\n')
    (package / "field_maps" / "transaction.fields.yml").write_text((EXAMPLES / "order_lookup.fields.yml").read_text())

    validation = validate_dataset_package(package)
    benchmark = benchmark_dataset_package(package)

    assert not validation["ok"]
    assert any("TRACE_PARSE_FAILED" in blocker for blocker in validation["blockers"])
    assert any("TRACE_PARSE_FAILED" in blocker for blocker in benchmark["blockers"])


def test_dataset_validation_reports_missing_artifacts_and_schema_edges(tmp_path, monkeypatch):
    missing = tmp_path / "missing_manifest"
    missing.mkdir()
    assert validate_dataset_package(missing)["blockers"] == ["MISSING_MANIFEST"]
    assert any("MANIFEST_INVALID" in blocker for blocker in benchmark_dataset_package(missing)["blockers"])

    package = tmp_path / "missing_artifacts"
    init_dataset_package(package, transaction_id="missing_artifacts", maturity_level="L4")
    manifest_path = package / "manifest.yml"
    manifest = yaml.safe_load(manifest_path.read_text())
    manifest["field_map"] = "field_maps/missing.yml"
    manifest["traces"] = {"happy_path": "traces/missing.trace.jsonl"}
    manifest["cases"] = {"happy_path": {"trace": "traces/missing.trace.jsonl", "purpose": "canonical_success", "case_kind": "happy_path"}}
    manifest["replay_cases"] = {"happy_path": "cases/missing.case.yml"}
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False))
    report = validate_dataset_package(package)
    assert "MISSING_FIELD_MAP" in report["blockers"]
    assert "MISSING_TRACE:happy_path" in report["blockers"]
    assert "MISSING_REPLAY_CASE:happy_path" in report["blockers"]
    assert "MATURITY_LEVEL_EXPECTS_MULTI_CASE_PACKAGE" in report["warnings"]
    assert "MATURITY_LEVEL_REQUIRES_FIELD_MAP" in report["blockers"]

    schema_root = tmp_path / "empty_schemas"
    schema_root.mkdir()
    monkeypatch.setattr(dataset_validate, "_schema_root", lambda: schema_root)
    schema_report = validate_dataset_package(package)
    assert any(blocker.startswith("MISSING_SCHEMA:dataset_manifest.schema.json") for blocker in schema_report["blockers"])

    monkeypatch.setattr(dataset_validate, "jsonschema", None)
    assert dataset_validate._validate_json_schema({}, "missing.schema.json") is None


def test_realism_report_surfaces_invalid_and_missing_context_packages(tmp_path):
    package = tmp_path / "realism_gap"
    init_dataset_package(package, transaction_id="realism_gap", maturity_level="L4")
    manifest_path = package / "manifest.yml"
    manifest = yaml.safe_load(manifest_path.read_text())
    manifest["actual_maturity_level"] = "L4"
    manifest["simulates_maturity_level"] = "L4"
    manifest["evidence_kind"] = "real_multi_case"
    manifest["business_process"] = ""
    manifest["operator_goal"] = ""
    manifest["traces"] = {"happy_path": "traces/missing.trace.jsonl"}
    manifest["cases"] = {"happy_path": {"trace": "traces/missing.trace.jsonl", "purpose": "canonical_success", "case_kind": "happy_path"}}
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False))

    report = package_realism_report(package)
    assert report["provenance"] == {}
    assert "package_has_blockers" in report["gaps"]
    assert "missing_business_process_or_operator_goal" in report["gaps"]
    assert "high_maturity_package_needs_multiple_cases" in report["gaps"]
    assert "record_validation_error_or_not_found_case" in report["recommended_next_data"]
    assert "record_or_mutate_label_and_field_move_drift_case" in report["recommended_next_data"]


def test_synthetic_package_builder_writes_business_context_and_artifacts(tmp_path):
    builder = SyntheticPackageBuilder(
        tmp_path,
        SyntheticPackageSpec(
            package_id="synthetic_test_package",
            transaction_id="test_transaction",
            maturity_level="L1",
            evidence_kind="domain_realistic_synthetic",
            actual_maturity_level="L1",
            simulates_maturity_level="L2",
            description="Generated package for builder coverage.",
            tags=["inquiry"],
            business_process="test inquiry review",
            operator_goal="enter a test key and verify the resulting status",
            known_limitations=["synthetic builder fixture"],
        ),
        scenario="builder unit test",
    )
    builder.write_provenance()
    builder.write_manifest([case_spec("happy_path", purpose="canonical_success", case_kind="happy_path", description="covers generated descriptions")])
    builder.write_field_map(
        display_name="Test Transaction",
        endpoint_path="/transactions/test-transaction",
        fields=[{"screen_ref": "screen_001", "field_id": "f_04_20", "name": "test_key", "role": "input", "type": "string", "required": True}],
    )
    builder.write_trace(
        "happy_path",
        [
            {
                "type": "screen",
                "seq": 1,
                "rows": 24,
                "cols": 80,
                "text": ["TEST".center(80), "   Test key . . .  ____".ljust(80)],
                "fields": [],
            }
        ],
    )

    manifest = load_dataset_manifest(builder.package)
    trace_line = json.loads((builder.package / "traces/happy_path.trace.jsonl").read_text().splitlines()[0])
    field_map = yaml.safe_load((builder.package / "field_maps/transaction.fields.yml").read_text())
    provenance = yaml.safe_load((builder.package / "provenance/generation.yml").read_text())

    assert manifest.business_process == "test inquiry review"
    assert manifest.operator_goal == "enter a test key and verify the resulting status"
    assert manifest.cases["happy_path"].case_kind == "happy_path"
    assert manifest.cases["happy_path"].description == "covers generated descriptions"
    assert trace_line["type"] == "screen"
    assert field_map["fields"][0]["name"] == "test_key"
    assert provenance["network_access_used"] is False


def test_dataset_manifest_inference_config_bundle_levels_and_pipeline(tmp_path, monkeypatch):
    manifest = DatasetManifest(
        package_id="inferred",
        transaction_id="inferred",
        traces={
            "label_drift_case": "traces/label.trace.jsonl",
            "cancel_case": "traces/cancel.trace.jsonl",
            "not_found_case": "traces/not_found.trace.jsonl",
            "menu_case": "traces/menu.trace.jsonl",
            "happy_path": "traces/happy.trace.jsonl",
            "unknown_case": "traces/unknown.trace.jsonl",
        },
    )
    cases = manifest_cases(manifest)
    assert cases["label_drift_case"].purpose == "drift_evidence"
    assert cases["cancel_case"].purpose == "non_contract"
    assert cases["not_found_case"].purpose == "canonical_error"
    assert cases["menu_case"].purpose == "navigation"
    assert cases["happy_path"].purpose == "canonical_success"
    assert cases["unknown_case"].case_kind == "recorded_path"
    assert infer_case_kind("unsupported_aid_case") == "unsupported_aid"
    assert infer_case_purpose("low_confidence_case") == "guardrail"

    config_path = tmp_path / "thresholds.yml"
    config_path.write_text("label_scan_left_chars: 12\ngenerated_hash_length: 10\n")
    config = load_config(config_path)
    assert config.label_scan_left_chars == 12
    assert config.generated_hash_length == 10
    assert config.detect_subfile_min_repeated_rows == 4

    complete = score_bundle_members(["manifest.json", "contract.yml", "openapi.yml", "replay_test.py", "replay_case.yml", "summary.json", "privacy_report.json"])
    review_ready = score_bundle_members(["manifest.json", "contract.yml", "openapi.yml", "replay_test.py", "summary.json"])
    incomplete = score_bundle_members(["manifest.json"])
    no_manifest = score_bundle_members(["contract.yml", "openapi.yml", "replay_test.py", "summary.json"])
    assert complete["level"] == "complete"
    assert review_ready["level"] == "review_ready_with_gaps"
    assert incomplete["level"] == "incomplete"
    assert "MISSING_CORE_ARTIFACT:manifest.json" in no_manifest["blockers"]

    def fake_review_package(package_dir, *, output_dir, strict=False):
        return {"package_dir": str(package_dir), "output_dir": str(output_dir), "strict": strict}

    monkeypatch.setattr(pipeline, "build_review_package", fake_review_package)
    result = pipeline.run_review_pipeline("pkg", output_dir="out", strict=True)
    assert result == {"package_dir": "pkg", "output_dir": "out", "strict": True}


def test_readiness_and_executive_summary_cover_status_variants():
    blocked = assess_review_readiness(
        validation={"ok": False, "warnings": ["W"], "blockers": ["B"]},
        benchmark={"review_required_count": 1, "field_map_coverage": 0.5, "contract_ready_rate": 0.0},
        extraction={"warnings": ["EW"], "blockers": ["EB"], "drift_case_count": 1, "non_contract_case_count": 1, "canonical_case_count": 1},
        realism={"synthetic": True, "business_impact_score": 25, "recommended_next_data": ["add_trace"]},
        privacy={"unredacted_sensitive_value_count": 2},
        openapi_validation={"ok": False},
    )
    assert blocked["review_package_status"] == "blocked"
    assert "OPENAPI_VALIDATION_FAILED" in blocked["blockers"]
    assert "sanitize_or_tokenize_trace_values_before_sharing" in blocked["recommended_next_actions"]
    assert "keep_navigation_cancel_paths_out_of_api_contract_shape" in blocked["recommended_next_actions"]

    ready = assess_review_readiness(
        validation={"ok": True},
        benchmark={"review_required_count": 0, "field_map_coverage": 1, "contract_ready_rate": 1.0},
        extraction={"drift_case_count": 0, "non_contract_case_count": 0, "canonical_case_count": 1},
        realism={"synthetic": False, "business_impact_score": 90, "recommended_next_data": ["ready_for_human_contract_review"]},
        privacy={"unredacted_sensitive_value_count": 0},
        openapi_validation={"ok": True},
    )
    assert ready["review_package_status"] == "ready_for_review"

    summary = render_executive_summary(
        package_id="pkg",
        transaction_id="txn",
        readiness=blocked,
        realism={"evidence_kind": "domain_realistic_synthetic", "actual_maturity_level": "L1", "simulates_maturity_level": "L4", "synthetic": True, "business_impact_score": 25},
        extraction={"canonical_case_count": 1, "drift_case_count": 1, "non_contract_case_count": 1, "canonical_contract": "contract.yml", "api_candidate": "api.yml", "combined_replay_test": "test.py", "drift_evidence": "drift.yml", "flow_graph": "flow.yml"},
        privacy={"unredacted_sensitive_value_count": 2},
        validation={"warnings": ["W"]},
        benchmark={"contract_ready_rate": 0.5, "field_map_coverage": 0.75},
    )
    assert "## Blockers" in summary
    assert "## Review Items" in summary
    assert "## Validation Warnings" in summary


def test_generated_real_world_corpus_has_complete_coverage_and_surfaces_blockers(tmp_path):
    root = tmp_path / "corpus"
    result = generate_real_world_corpus(root)
    coverage = coverage_report(root)
    low_confidence = benchmark_dataset_package(root / "synthetic_low_confidence_guardrail")
    account_events = load_trace(root / "synthetic_account_list_subfile" / "traces" / "happy_path.trace.jsonl")
    account_map = load_field_map(root / "synthetic_account_list_subfile" / "field_maps" / "transaction.fields.yml")
    sanitized, privacy = sanitize_trace_events(account_events, field_map=account_map)
    sanitized_text = json.dumps(sanitized)

    assert result["coverage"]["complete"]
    assert coverage["coverage_pct"] == 100.0
    assert "low_confidence:extract:NO_FINAL_OUTPUT_FIELDS" in low_confidence["blockers"]
    assert privacy["unredacted_sensitive_value_count"] == 0
    assert "44550001" not in sanitized_text
    assert "44550002" not in sanitized_text


def test_generated_corpus_realism_and_package_contract_metadata(tmp_path):
    root = tmp_path / "corpus"
    generate_real_world_corpus(root)
    corpus_report = corpus_realism_report(root)
    account_report = package_realism_report(root / "synthetic_account_list_subfile")
    extract_summary = extract_dataset_package(
        root / "synthetic_account_list_subfile",
        output_dir=tmp_path / "account_out",
    )
    contract = yaml.safe_load(Path(extract_summary["combined_contract"]).read_text())
    openapi = yaml.safe_load(Path(extract_summary["combined_openapi"]).read_text())
    replay_test = Path(extract_summary["combined_replay_test"])
    drift_baseline = json.loads(Path(extract_summary["drift_baseline"]).read_text())

    assert corpus_report["package_count"] == 9
    assert corpus_report["synthetic_package_count"] == 9
    assert "portfolio" in corpus_report
    assert "synthetic_order_inquiry_multi_case" in corpus_report["portfolio"]["quick_win_candidates"]
    assert "synthetic_account_list_subfile" in corpus_report["portfolio"]["subfile_heavy_candidates"]
    assert "synthetic_boundary_locale_values" in corpus_report["portfolio"]["boundary_locale_candidates"]
    assert account_report["evidence_level"] == "domain_realistic_synthetic"
    assert account_report["actual_maturity_level"] == "L1"
    assert account_report["simulates_maturity_level"] == "L3"
    assert not any("FIELD_MAP_INVALID" in warning for warning in account_report["warnings"])
    assert contract["flow_graph"]["case_count"] == 2
    assert contract["flow_graph"]["edge_count"] == 3
    assert contract["screens"][0]["subfile_regions"][0]["review_required"] is True
    assert any(edge["aid"] == "PAGEDOWN" for edge in contract["flow_graph"]["edges"])
    assert openapi["openapi"] == "3.1.0"
    assert openapi["paths"]["/transactions/account-list-select"]["post"]["x-screen-flow-graph"]["case_count"] == 2
    assert validate_openapi_document(openapi) == []
    assert replay_test.exists()
    assert pytest.main([str(replay_test), "-q"]) == 0
    assert drift_baseline["screen_count"] == len(contract["screens"])
    assert drift_baseline["flow_graph"]["case_count"] == 2
    assert drift_baseline["comparison_policy"]["field_layout_hash_change"] == "breaking"
    navigation = package_realism_report(root / "synthetic_navigation_no_credentials")
    assert navigation["tags"] == ["menu", "navigation", "no_credentials"]
    boundary = package_realism_report(root / "synthetic_boundary_locale_values")
    assert "boundary_values" in boundary["tags"]
    assert "locale_formats" in boundary["tags"]
    repeated = package_realism_report(root / "synthetic_repeated_labels")
    assert "repeated_labels" in repeated["tags"]


def test_generated_corpus_declares_business_context_for_every_package(tmp_path):
    root = tmp_path / "corpus"
    generate_real_world_corpus(root)

    for manifest_path in sorted(root.glob("synthetic_*/manifest.yml")):
        report = package_realism_report(manifest_path.parent)
        assert report["business_process"]
        assert report["operator_goal"]
        assert report["score_dimensions"]["business_context"] == 4
        assert "business_context_declared" in report["strengths"]
        assert "missing_business_process_or_operator_goal" not in report["gaps"]



def test_generated_multi_value_order_variants_keep_screen_hashes_stable(tmp_path):
    root = tmp_path / "corpus"
    generate_real_world_corpus(root)
    package = root / "synthetic_order_inquiry_multi_case"
    fmap = load_field_map(package / "field_maps" / "transaction.fields.yml")
    happy = load_trace(package / "traces" / "happy_path.trace.jsonl")
    alt = load_trace(package / "traces" / "happy_path_alt_value.trace.jsonl")

    happy_hashes = [compute_screen_hashes(event, f"screen_{event.seq:03d}", fmap).screen_hash for event in happy if event.type == "screen"]
    alt_hashes = [compute_screen_hashes(event, f"screen_{event.seq:03d}", fmap).screen_hash for event in alt if event.type == "screen"]

    assert happy_hashes == alt_hashes


def test_drift_cases_do_not_change_canonical_openapi_shape(tmp_path):
    root = tmp_path / "corpus"
    generate_real_world_corpus(root)
    package = root / "synthetic_order_inquiry_multi_case"
    result = extract_dataset_package(package, output_dir=tmp_path / "order_out")
    contract = yaml.safe_load(Path(result["canonical_contract"]).read_text())
    openapi = yaml.safe_load(Path(result["api_candidate"]).read_text())
    drift_evidence = yaml.safe_load(Path(result["drift_evidence"]).read_text())

    titles = {screen["title"] for screen in contract["screens"]}
    customer_name = openapi["components"]["schemas"]["OrderInquiryResponse"]["properties"]["customer_name"]

    assert "ORDER INQUIRY" in titles
    assert customer_name["x-screen-field"]["col"] == 34
    assert result["drift_case_count"] == 2
    assert drift_evidence["drift_case_count"] == 2
    assert any(item["comparison_to_canonical"]["status"] in {"review_required", "breaking_change"} for item in drift_evidence["drift_cases"])


def test_generated_boundary_locale_package_contains_realistic_value_variants(tmp_path):
    root = tmp_path / "corpus"
    generate_real_world_corpus(root)
    package = root / "synthetic_boundary_locale_values"
    validation = validate_dataset_package(package)
    benchmark = benchmark_dataset_package(package)

    blank_optional = (package / "traces" / "blank_optional.trace.jsonl").read_text()
    max_decimal = (package / "traces" / "max_length_decimal.trace.jsonl").read_text()
    negative = (package / "traces" / "negative_amount.trace.jsonl").read_text()
    invalid = (package / "traces" / "invalid_date.trace.jsonl").read_text()
    locale = (package / "traces" / "locale_variant.trace.jsonl").read_text()

    assert validation["ok"]
    assert benchmark["trace_count"] == 5
    assert '"value":""' in blank_optional
    assert "INV1234567" in max_decimal
    assert "-000045.50" in negative
    assert "31/02/2026" in invalid
    assert "1.234,56" in locale
    assert "15/01/2026" in locale


def test_generated_customer_update_pairs_hidden_field_present_and_absent(tmp_path):
    root = tmp_path / "corpus"
    generate_real_world_corpus(root)
    package = root / "synthetic_customer_update_sensitive"
    validation = validate_dataset_package(package)
    present = load_trace(package / "traces" / "happy_path.trace.jsonl")
    absent = load_trace(package / "traces" / "hidden_absent.trace.jsonl")

    present_hidden = [field for field in present[0].fields if field.hidden]
    absent_hidden = [field for field in absent[0].fields if field.hidden]

    assert validation["ok"]
    assert present_hidden and present_hidden[0].id == "f_23_02"
    assert absent_hidden == []
    assert len(present[0].fields) == len(absent[0].fields) + 1


def test_generated_repeated_label_package_disambiguates_output_fields(tmp_path):
    root = tmp_path / "corpus"
    generate_real_world_corpus(root)
    package = root / "synthetic_repeated_labels"
    validation = validate_dataset_package(package)
    result = extract_dataset_package(package, output_dir=tmp_path / "repeated_out")
    contract = yaml.safe_load(Path(result["combined_contract"]).read_text())
    response_names = {field["name"] for field in contract["response_fields"]}

    assert validation["ok"]
    assert response_names == {
        "account_status",
        "order_status",
        "account_code",
        "order_code",
        "base_amount",
        "adjusted_amount",
    }


def test_low_confidence_generated_trace_still_replays_recorded_steps(tmp_path):
    root = tmp_path / "corpus"
    generate_real_world_corpus(root)
    events = load_trace(root / "synthetic_low_confidence_guardrail" / "traces" / "low_confidence.trace.jsonl")
    extraction = extract_dataset_package(
        root / "synthetic_low_confidence_guardrail",
        output_dir=tmp_path / "low_confidence_out",
    )
    contract = TransactionContract(**yaml.safe_load(Path(extraction["combined_contract"]).read_text()))
    driver = TraceReplayDriver(events, contract)

    assert driver.current_screen_hash() == contract.replay_cases[0].start_screen_hash
    step_contract = yaml.safe_load((tmp_path / "low_confidence_out" / "low_confidence.case.yml").read_text())
    step = step_contract["steps"][0]
    assert driver.apply(step["aid"], step["inputs"]) == step["expect_next_screen_hash"]


def test_generated_adversarial_corpus_reports_expected_blockers(tmp_path):
    root = tmp_path / "adversarial"
    result = generate_adversarial_corpus(root)
    reports = {path.name: validate_dataset_package(path) for path in sorted(root.glob("pkg_*"))}
    bad_map_benchmark = benchmark_dataset_package(root / "pkg_bad_field_map")

    assert result["package_count"] == 5
    assert all(not report["ok"] for report in reports.values())
    assert any("MANIFEST_INVALID" in blocker for blocker in reports["pkg_bad_manifest"]["blockers"])
    assert any("TRACE_JSON_INVALID" in blocker for blocker in reports["pkg_invalid_jsonl"]["blockers"])
    assert "bad_case:TRACE_SEQUENCE_INVALID" in reports["pkg_duplicate_sequence"]["blockers"]
    assert "bad_case:FIELD_COORDINATES_OUT_OF_BOUNDS" in reports["pkg_out_of_bounds_field"]["blockers"]
    assert any("FIELD_MAP_INVALID" in blocker for blocker in reports["pkg_bad_field_map"]["blockers"])
    assert any("FIELD_MAP_INVALID" in blocker for blocker in bad_map_benchmark["blockers"])


def test_packaged_schemas_match_repo_schemas():
    repo_schemas = ROOT / "schemas"
    package_schemas = ROOT / "src" / "host_screen_contracts" / "schemas"

    for schema_path in repo_schemas.glob("*.schema.json"):
        packaged = package_schemas / schema_path.name
        assert packaged.exists()
        assert packaged.read_text() == schema_path.read_text()


def test_write_sanitized_trace_outputs_jsonl(tmp_path, order_events):
    path = tmp_path / "trace.jsonl"
    events = [event.model_dump(mode="json", exclude_none=True) for event in order_events]
    write_sanitized_trace(path, events)
    assert len(path.read_text().splitlines()) == 3


def test_trace_writer_creates_neutral_jsonl(tmp_path):
    path = tmp_path / "manual.trace.jsonl"
    writer = TraceWriter(path)
    writer.write_screen(
        ScreenSnapshot(
            rows=24,
            cols=80,
            text=["START"],
            fields=[ScreenFieldSnapshot(id="f_01_01", row=1, col=1, length=5, value="", protected=False)],
            cursor_row=1,
            cursor_col=1,
        )
    )
    writer.write_action("ENTER", [{"field_id": "f_01_01", "value": "A"}])
    writer.write_note("offline note")
    writer.close()
    lines = [json.loads(line) for line in path.read_text().splitlines()]
    assert [line["type"] for line in lines] == ["screen", "action", "note"]
    assert lines[0]["cursor"] == {"row": 1, "col": 1}


def test_bundle_zip_contains_manifest(tmp_path, order_result):
    contract_path = tmp_path / "contract.yml"
    summary_path = tmp_path / "summary.json"
    bundle_path = tmp_path / "handoff.zip"
    contract_path.write_text(yaml.safe_dump(contract_to_dict(order_result().contract), sort_keys=False))
    summary_path.write_text(json.dumps(order_result().summary))
    with zipfile.ZipFile(bundle_path, "w") as bundle:
        bundle.write(contract_path, "contract.yml")
        bundle.write(summary_path, "summary.json")
        bundle.writestr("manifest.json", json.dumps({"schema_version": "1.0"}))
    with zipfile.ZipFile(bundle_path) as bundle:
        assert "manifest.json" in bundle.namelist()
    score = score_bundle_zip(bundle_path)
    assert score["score"] == 45
    assert "MISSING_CORE_ARTIFACT:openapi.yml" in score["blockers"]
