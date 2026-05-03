from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest
import yaml

from host_screen_contracts.adapter_protocol import ScreenFieldSnapshot, ScreenSnapshot, TraceWriter
from host_screen_contracts.benchmark import benchmark_dataset_package
from host_screen_contracts.bundle_score import score_bundle_zip
from host_screen_contracts.contract_model import TransactionContract, contract_to_dict
from host_screen_contracts.dataset_model import init_dataset_package
from host_screen_contracts.dataset_validate import validate_dataset_package
from host_screen_contracts.drift_compare import compare_contract_to_trace
from host_screen_contracts.field_map import load_field_map
from host_screen_contracts.label_sheet import generate_label_sheet
from host_screen_contracts.package_extract import extract_dataset_package
from host_screen_contracts.parse_trace import load_trace
from host_screen_contracts.openapi_validate import validate_openapi_document
from host_screen_contracts.privacy_report import generate_privacy_report
from host_screen_contracts.real_world_data_generator import coverage_report, generate_adversarial_corpus, generate_real_world_corpus
from host_screen_contracts.realism_report import corpus_realism_report, package_realism_report
from host_screen_contracts.replay_driver import TraceReplayDriver
from host_screen_contracts.sanitize_trace import sanitize_trace_events, write_sanitized_trace
from host_screen_contracts.screen_hash import compute_screen_hashes
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

    assert result["package_count"] == 5
    assert all(not report["ok"] for report in reports.values())
    assert any("MANIFEST_INVALID" in blocker for blocker in reports["pkg_bad_manifest"]["blockers"])
    assert any("TRACE_JSON_INVALID" in blocker for blocker in reports["pkg_invalid_jsonl"]["blockers"])
    assert "bad_case:TRACE_SEQUENCE_INVALID" in reports["pkg_duplicate_sequence"]["blockers"]
    assert "bad_case:FIELD_COORDINATES_OUT_OF_BOUNDS" in reports["pkg_out_of_bounds_field"]["blockers"]
    assert any("FIELD_MAP_INVALID" in blocker for blocker in reports["pkg_bad_field_map"]["blockers"])


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
        )
    )
    writer.write_action("ENTER", [{"field_id": "f_01_01", "value": "A"}])
    writer.close()
    lines = [json.loads(line) for line in path.read_text().splitlines()]
    assert [line["type"] for line in lines] == ["screen", "action"]


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
