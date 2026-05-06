from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from .synthetic_package import SyntheticCaseSpec, SyntheticPackageBuilder, SyntheticPackageSpec, case_spec


ROWS = 24
COLS = 80
REQUIRED_COVERAGE_TAGS = {
    "inquiry",
    "update",
    "confirmation",
    "error_path",
    "not_found",
    "validation_error",
    "permission_denied",
    "cancel_fkey",
    "same_screen_loop",
    "volatile_region",
    "label_drift",
    "field_move_drift",
    "attribute_drift",
    "hidden_field",
    "absent_hidden_field",
    "hidden_field_absence_pair",
    "subfile",
    "paging",
    "screen_size_27x132",
    "date_field",
    "leading_zero_identifier",
    "long_truncated_value",
    "optional_input",
    "multiple_request_screens",
    "plain_text_only",
    "low_confidence",
    "unsupported_aid",
    "sensitive",
    "navigation",
    "multi_value",
    "boundary_values",
    "blank_optional_input",
    "max_length_input",
    "invalid_date",
    "negative_amount",
    "decimal_amount",
    "currency_format",
    "locale_formats",
    "repeated_labels",
    "field_reuse_ambiguity",
}


def _line(text: str, cols: int = COLS) -> str:
    return text[:cols].ljust(cols)


def _write_jsonl(path: Path, events: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(event, separators=(",", ":")) for event in events) + "\n")


def _write_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def _make_dirs(package: Path) -> None:
    for child in ("traces", "field_maps", "cases", "expected", "review", "privacy", "provenance"):
        (package / child).mkdir(parents=True, exist_ok=True)


def _write_provenance(package: Path, *, scenario: str) -> None:
    _write_yaml(
        package / "provenance/generation.yml",
        {
            "schema_version": "1.0",
            "generated_by": "host-screen-contracts",
            "data_kind": "deterministic_synthetic",
            "scenario": scenario,
            "contains_customer_data": False,
            "contains_live_host_capture": False,
            "network_access_used": False,
        },
    )


def _domain_package(
    root: Path,
    *,
    package_id: str,
    transaction_id: str,
    description: str,
    scenario: str,
    cases: list[SyntheticCaseSpec],
    tags: list[str],
    simulates_maturity_level: str = "L3",
    business_process: str,
    operator_goal: str,
    known_limitations: list[str] | None = None,
) -> SyntheticPackageBuilder:
    builder = SyntheticPackageBuilder(
        root,
        SyntheticPackageSpec(
            package_id=package_id,
            transaction_id=transaction_id,
            maturity_level="L1",
            evidence_kind="domain_realistic_synthetic",
            actual_maturity_level="L1",
            simulates_maturity_level=simulates_maturity_level,
            description=description,
            tags=tags,
            business_process=business_process,
            operator_goal=operator_goal,
            known_limitations=known_limitations or ["Synthetic values preserve field shape but do not represent a live host capture."],
        ),
        scenario=scenario,
    )
    builder.write_provenance()
    builder.write_manifest(cases)
    return builder


def _guardrail_package(
    root: Path,
    *,
    package_id: str,
    transaction_id: str,
    description: str,
    scenario: str,
    cases: list[SyntheticCaseSpec],
    tags: list[str],
    field_map: str | None = None,
    known_limitations: list[str] | None = None,
) -> SyntheticPackageBuilder:
    builder = SyntheticPackageBuilder(
        root,
        SyntheticPackageSpec(
            package_id=package_id,
            transaction_id=transaction_id,
            maturity_level="L0",
            evidence_kind="deterministic_synthetic",
            actual_maturity_level="L0",
            simulates_maturity_level="L0",
            description=description,
            tags=tags,
            field_map=field_map,
            business_process="validation guardrail",
            operator_goal="exercise parser and extractor failure handling",
            known_limitations=known_limitations or ["Guardrail data is intentionally incomplete or invalid."],
        ),
        scenario=scenario,
    )
    builder.write_provenance()
    builder.write_manifest(cases)
    return builder


def _with_volatile(screen: dict[str, Any], value: str) -> dict[str, Any]:
    row = screen["text"][0].ljust(COLS)
    screen["text"][0] = row[:64] + value[:15].ljust(15) + row[79:]
    return screen


def _screen(seq: int, title: str, text: list[str], fields: list[dict[str, Any]], *, rows: int = ROWS, cols: int = COLS) -> dict[str, Any]:
    return {
        "type": "screen",
        "seq": seq,
        "timestamp": f"2026-01-01T12:00:0{seq}Z",
        "rows": rows,
        "cols": cols,
        "cursor": {"row": min(20, rows), "col": 2},
        "text": [_line("", cols), _line(title.center(55), cols), *text],
        "fields": fields,
    }


def _action(seq: int, aid: str, inputs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "type": "action",
        "seq": seq,
        "timestamp": f"2026-01-01T12:00:0{seq}Z",
        "aid": aid,
        "cursor": {"row": 4, "col": 32},
        "inputs": inputs or [],
    }


def generate_real_world_corpus(output_dir: str | Path, *, seed: int = 123) -> dict[str, Any]:
    _ = seed
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    packages = [
        _generate_order_inquiry(root),
        _generate_customer_update(root),
        _generate_account_list(root),
        _generate_inventory_plain_text(root),
        _generate_exception_paths(root),
        _generate_navigation(root),
        _generate_boundary_locale(root),
        _generate_repeated_labels(root),
        _generate_low_confidence(root),
    ]
    report = coverage_report(root)
    return {"schema_version": "1.0", "package_count": len(packages), "packages": packages, "coverage": report}


def generate_adversarial_corpus(output_dir: str | Path) -> dict[str, Any]:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    packages = [
        _generate_malformed_manifest(root),
        _generate_invalid_jsonl(root),
        _generate_duplicate_sequence(root),
        _generate_out_of_bounds_field(root),
        _generate_bad_field_map(root),
    ]
    return {
        "schema_version": "1.0",
        "package_count": len(packages),
        "packages": packages,
        "purpose": "negative validation corpus",
    }


def _write_minimal_manifest(package: Path, package_id: str, *, field_map: str | None = None) -> None:
    _write_yaml(
        package / "manifest.yml",
        {
            "schema_version": "1.0",
            "package_id": package_id,
            "transaction_id": package_id,
            "maturity_level": "L0",
            "evidence_kind": "deterministic_synthetic",
            "actual_maturity_level": "L0",
            "simulates_maturity_level": "L0",
            "description": "Generated adversarial validation package.",
            "traces": {"bad_case": "traces/bad_case.trace.jsonl"},
            "cases": {"bad_case": {"trace": "traces/bad_case.trace.jsonl", "purpose": "guardrail", "case_kind": "bad_case"}},
            "field_map": field_map,
            "replay_cases": {},
            "tags": ["adversarial"],
        },
    )


def _generate_malformed_manifest(root: Path) -> str:
    package = root / "pkg_bad_manifest"
    _make_dirs(package)
    _write_provenance(package, scenario="malformed manifest negative test")
    _write_yaml(
        package / "manifest.yml",
        {
            "schema_version": "1.0",
            "package_id": "bad_manifest",
            "transaction_id": "bad_manifest",
            "maturity_level": "LX",
            "traces": {"bad_case": "traces/bad_case.trace.jsonl"},
            "field_map": None,
        },
    )
    _write_jsonl(package / "traces/bad_case.trace.jsonl", [_screen(1, "BAD", [], []), _action(2, "ENTER"), _screen(3, "BAD", [], [])])
    return str(package)


def _generate_invalid_jsonl(root: Path) -> str:
    package = root / "pkg_invalid_jsonl"
    _make_dirs(package)
    _write_provenance(package, scenario="invalid JSONL negative test")
    _write_minimal_manifest(package, "invalid_jsonl")
    (package / "traces/bad_case.trace.jsonl").write_text('{"type":"screen","seq":1,"rows":24,"cols":80,"text":["BAD"]}\nnot-json\n')
    return str(package)


def _generate_duplicate_sequence(root: Path) -> str:
    package = root / "pkg_duplicate_sequence"
    _make_dirs(package)
    _write_provenance(package, scenario="duplicate sequence negative test")
    _write_minimal_manifest(package, "duplicate_sequence")
    _write_jsonl(package / "traces/bad_case.trace.jsonl", [_screen(1, "DUP", [], []), _action(1, "ENTER"), _screen(3, "DUP", [], [])])
    return str(package)


def _generate_out_of_bounds_field(root: Path) -> str:
    package = root / "pkg_out_of_bounds_field"
    _make_dirs(package)
    _write_provenance(package, scenario="out-of-bounds field negative test")
    _write_minimal_manifest(package, "out_of_bounds_field")
    _write_jsonl(
        package / "traces/bad_case.trace.jsonl",
        [
            _screen(
                1,
                "OUT OF BOUNDS",
                [],
                [{"id": "f_25_01", "row": 25, "col": 1, "length": 1, "value": "", "protected": False, "display_only": False, "hidden": False, "attributes": []}],
            ),
            _action(2, "ENTER", [{"field_id": "f_25_01", "row": 25, "col": 1, "value": "X"}]),
            _screen(3, "OUT OF BOUNDS", [], []),
        ],
    )
    return str(package)


def _generate_bad_field_map(root: Path) -> str:
    package = root / "pkg_bad_field_map"
    _make_dirs(package)
    _write_provenance(package, scenario="invalid field-map negative test")
    _write_minimal_manifest(package, "bad_field_map", field_map="field_maps/transaction.fields.yml")
    _write_yaml(
        package / "field_maps/transaction.fields.yml",
        {
            "transaction_id": "bad_field_map",
            "fields": [{"screen_ref": "screen_001", "row": 1, "col": 1, "length": 1, "name": "bad", "role": "not_a_role"}],
        },
    )
    _write_jsonl(package / "traces/bad_case.trace.jsonl", [_screen(1, "BAD MAP", [], []), _action(2, "ENTER"), _screen(3, "BAD MAP", [], [])])
    return str(package)


def _generate_order_inquiry(root: Path) -> str:
    tags = ["inquiry", "error_path", "not_found", "label_drift", "field_move_drift", "volatile_region", "leading_zero_identifier", "date_field", "multi_value"]
    builder = _domain_package(
        root,
        package_id="synthetic_order_inquiry_multi_case",
        transaction_id="order_inquiry",
        description="Generated order inquiry with success, not-found, and drift cases.",
        scenario="order inquiry with success, not-found, and drift cases",
        cases=[
            case_spec("happy_path", purpose="canonical_success", case_kind="happy_path"),
            case_spec("happy_path_alt_value", purpose="canonical_success", case_kind="happy_path"),
            case_spec("not_found", purpose="canonical_error", case_kind="not_found"),
            case_spec("label_drift", purpose="drift_evidence", case_kind="label_drift"),
            case_spec("field_move_drift", purpose="drift_evidence", case_kind="field_move_drift"),
        ],
        tags=tags,
        simulates_maturity_level="L4",
        business_process="order service inquiry",
        operator_goal="enter an order number and review fulfillment status, customer name, total, and order date",
    )
    package = builder.package
    builder.write_field_map(
        display_name="Order Inquiry",
        endpoint_path="/transactions/order-inquiry",
        volatile_regions=[{"screen_ref": "*", "row": 1, "col": 65, "length": 15, "reason": "clock_or_session_id"}],
        fields=[
            {"screen_ref": "screen_001", "field_id": "f_04_34", "name": "order_number", "role": "input", "type": "string", "required": True, "sensitive": False},
            {"screen_ref": "screen_003", "field_id": "f_04_34", "name": "order_number", "role": "output", "type": "string", "required": False, "sensitive": False, "optional": True},
            {"screen_ref": "screen_003", "field_id": "f_05_34", "name": "customer_name", "role": "output", "type": "string", "required": False, "sensitive": False, "optional": True},
            {"screen_ref": "screen_003", "field_id": "f_06_34", "name": "order_status", "role": "output", "type": "string", "required": False, "sensitive": False, "optional": True},
            {"screen_ref": "screen_003", "field_id": "f_07_34", "name": "order_total", "role": "output", "type": "string", "required": False, "sensitive": False, "optional": True},
            {"screen_ref": "screen_003", "field_id": "f_08_34", "name": "order_date", "role": "output", "type": "date", "required": False, "sensitive": False, "optional": True},
            {"screen_ref": "screen_003", "field_id": "f_22_08", "name": "message_text", "role": "error_message", "type": "string", "required": False, "sensitive": False, "optional": True},
        ],
    )
    start = _with_volatile(_screen(1, "ORDER INQUIRY", [_line(""), _line("   Order number . . . . . . . .  ________"), _line("   F3=Exit   F12=Cancel")], [{"id": "f_04_34", "row": 4, "col": 34, "length": 8, "value": "", "protected": False, "display_only": False, "hidden": False, "attributes": []}]), "SESSION000001")
    action_ok = _action(2, "ENTER", [{"field_id": "f_04_34", "row": 4, "col": 34, "value": "00123456"}])
    action_nf = _action(2, "ENTER", [{"field_id": "f_04_34", "row": 4, "col": 34, "value": "00999999"}])
    detail_text = [_line(""), _line("   Order number . . . . . . . .  00123456"), _line("   Customer . . . . . . . . . .  SAMPLE DISTRIBUTION"), _line("   Status . . . . . . . . . . .  SHIPPED"), _line("   Total . . . . . . . . . . . .  001250.00"), _line("   Order date . . . . . . . . .  2026-01-15"), _line("   F3=Exit   F12=Cancel")]
    detail_fields = [
        {"id": "f_04_34", "row": 4, "col": 34, "length": 8, "value": "00123456", "protected": True, "display_only": True, "hidden": False, "attributes": []},
        {"id": "f_05_34", "row": 5, "col": 34, "length": 20, "value": "SAMPLE DISTRIBUTION", "protected": True, "display_only": True, "hidden": False, "attributes": []},
        {"id": "f_06_34", "row": 6, "col": 34, "length": 12, "value": "SHIPPED", "protected": True, "display_only": True, "hidden": False, "attributes": []},
        {"id": "f_07_34", "row": 7, "col": 34, "length": 10, "value": "001250.00", "protected": True, "display_only": True, "hidden": False, "attributes": []},
        {"id": "f_08_34", "row": 8, "col": 34, "length": 10, "value": "2026-01-15", "protected": True, "display_only": True, "hidden": False, "attributes": []},
    ]
    builder.write_trace("happy_path", [start, action_ok, _with_volatile(_screen(3, "ORDER DETAIL", detail_text, detail_fields), "SESSION000002")])
    alt_text = [_line(""), _line("   Order number . . . . . . . .  00123457"), _line("   Customer . . . . . . . . . .  SAMPLE REGIONAL"), _line("   Status . . . . . . . . . . .  PENDING"), _line("   Total . . . . . . . . . . . .  000045.50"), _line("   Order date . . . . . . . . .  2026-01-16"), _line("   F3=Exit   F12=Cancel")]
    alt_fields = [
        {"id": "f_04_34", "row": 4, "col": 34, "length": 8, "value": "00123457", "protected": True, "display_only": True, "hidden": False, "attributes": []},
        {"id": "f_05_34", "row": 5, "col": 34, "length": 20, "value": "SAMPLE REGIONAL", "protected": True, "display_only": True, "hidden": False, "attributes": []},
        {"id": "f_06_34", "row": 6, "col": 34, "length": 12, "value": "PENDING", "protected": True, "display_only": True, "hidden": False, "attributes": []},
        {"id": "f_07_34", "row": 7, "col": 34, "length": 10, "value": "000045.50", "protected": True, "display_only": True, "hidden": False, "attributes": []},
        {"id": "f_08_34", "row": 8, "col": 34, "length": 10, "value": "2026-01-16", "protected": True, "display_only": True, "hidden": False, "attributes": []},
    ]
    builder.write_trace("happy_path_alt_value", [start, _action(2, "ENTER", [{"field_id": "f_04_34", "row": 4, "col": 34, "value": "00123457"}]), _with_volatile(_screen(3, "ORDER DETAIL", alt_text, alt_fields), "SESSION000006")])
    builder.write_trace("label_drift", [start, action_ok, _with_volatile(_screen(3, "ORDER DETAIL", [row.replace("Status", "Order state") for row in detail_text], detail_fields), "SESSION000003")])
    moved_fields = [field.copy() for field in detail_fields]
    moved_fields[1]["col"] = 36
    builder.write_trace("field_move_drift", [start, action_ok, _with_volatile(_screen(3, "ORDER DETAIL", detail_text, moved_fields), "SESSION000004")])
    nf_text = [_line(""), _line("   Order number . . . . . . . .  00999999"), _line(""), _line("   F3=Exit   F12=Cancel"), *[_line("") for _ in range(15)], _line("       Order not found for entered value")]
    nf_fields = [
        {"id": "f_04_34", "row": 4, "col": 34, "length": 8, "value": "00999999", "protected": True, "display_only": True, "hidden": False, "attributes": []},
        {"id": "f_22_08", "row": 22, "col": 8, "length": 35, "value": "Order not found for entered value", "protected": True, "display_only": True, "hidden": False, "attributes": ["message"]},
    ]
    builder.write_trace("not_found", [start, action_nf, _with_volatile(_screen(3, "ORDER DETAIL", nf_text, nf_fields), "SESSION000005")])
    return str(package)


def _generate_customer_update(root: Path) -> str:
    builder = _domain_package(
        root,
        package_id="synthetic_customer_update_sensitive",
        transaction_id="customer_update",
        description="Generated sensitive update with confirmation, hidden field, and multiple request screens.",
        scenario="sensitive update with confirmation and hidden field",
        cases=[
            case_spec("happy_path", purpose="canonical_success", case_kind="happy_path"),
            case_spec("hidden_absent", purpose="canonical_success", case_kind="recorded_path"),
            case_spec("cancel", purpose="non_contract", case_kind="cancel"),
        ],
        tags=[
            "update",
            "confirmation",
            "sensitive",
            "hidden_field",
            "absent_hidden_field",
            "hidden_field_absence_pair",
            "multiple_request_screens",
            "optional_input",
            "long_truncated_value",
        ],
        simulates_maturity_level="L4",
        business_process="customer contact update",
        operator_goal="enter an account number and phone update, confirm the change, and verify the update status",
        known_limitations=["Account and token values are fake but intentionally exercise sensitive-field handling."],
    )
    package = builder.package
    builder.write_field_map(
        display_name="Customer Update",
        endpoint_path="/transactions/customer-update",
        fields=[
            {"screen_ref": "screen_001", "field_id": "f_05_30", "name": "account_number", "role": "input", "type": "string", "required": True, "sensitive": True},
            {"screen_ref": "screen_001", "field_id": "f_06_30", "name": "phone_number", "role": "input", "type": "string", "required": True, "sensitive": False},
            {"screen_ref": "screen_001", "field_id": "f_07_30", "name": "mailing_note", "role": "input", "type": "string", "required": False, "sensitive": False},
            {"screen_ref": "screen_001", "field_id": "f_23_02", "name": "hidden_session_token", "role": "hidden", "type": "string", "required": False, "sensitive": True},
            {"screen_ref": "screen_005", "field_id": "f_05_30", "name": "update_status", "role": "output", "type": "string", "sensitive": False},
        ],
    )
    s1 = _screen(1, "CUSTOMER UPDATE", [_line(""), _line("   Account number . . . . .  __________"), _line("   Phone . . . . . . . . . .  __________"), _line("   Mailing note . . . . . .  ____________________"), _line("   F3=Exit   F12=Cancel")], [
        {"id": "f_05_30", "row": 4, "col": 30, "length": 10, "value": "", "protected": False, "display_only": False, "hidden": False, "attributes": []},
        {"id": "f_06_30", "row": 5, "col": 30, "length": 10, "value": "", "protected": False, "display_only": False, "hidden": False, "attributes": []},
        {"id": "f_07_30", "row": 6, "col": 30, "length": 20, "value": "", "protected": False, "display_only": False, "hidden": False, "attributes": []},
        {"id": "f_23_02", "row": 23, "col": 2, "length": 16, "value": "CSRF1234567890", "protected": True, "display_only": False, "hidden": True, "attributes": ["hidden"]},
    ])
    s3 = _screen(3, "CONFIRM UPDATE", [_line(""), _line("   Press ENTER to confirm or F12 to cancel"), _line("   F3=Exit   F12=Cancel")], [])
    s5 = _screen(5, "CUSTOMER RESULT", [_line(""), _line("   Update status . . . . . .  UPDATED"), _line("   F3=Exit   F12=Cancel")], [{"id": "f_05_30", "row": 4, "col": 30, "length": 10, "value": "UPDATED", "protected": True, "display_only": True, "hidden": False, "attributes": []}])
    builder.write_trace("happy_path", [s1, _action(2, "ENTER", [{"field_id": "f_05_30", "row": 4, "col": 30, "value": "1234567890"}, {"field_id": "f_06_30", "row": 5, "col": 30, "value": "5550100"}]), s3, _action(4, "ENTER"), s5])
    s1_without_hidden = _screen(1, "CUSTOMER UPDATE", [_line(""), _line("   Account number . . . . .  __________"), _line("   Phone . . . . . . . . . .  __________"), _line("   Mailing note . . . . . .  ____________________"), _line("   F3=Exit   F12=Cancel")], [
        {"id": "f_05_30", "row": 4, "col": 30, "length": 10, "value": "", "protected": False, "display_only": False, "hidden": False, "attributes": []},
        {"id": "f_06_30", "row": 5, "col": 30, "length": 10, "value": "", "protected": False, "display_only": False, "hidden": False, "attributes": []},
        {"id": "f_07_30", "row": 6, "col": 30, "length": 20, "value": "", "protected": False, "display_only": False, "hidden": False, "attributes": []},
    ])
    builder.write_trace("hidden_absent", [s1_without_hidden, _action(2, "ENTER", [{"field_id": "f_05_30", "row": 4, "col": 30, "value": "1234567890"}, {"field_id": "f_06_30", "row": 5, "col": 30, "value": "5550100"}]), s3, _action(4, "ENTER"), s5])
    cancel_screen = _screen(5, "CUSTOMER MENU", [_line(""), _line("   Selection . . .  _"), _line("   F3=Exit")], [])
    builder.write_trace("cancel", [s1, _action(2, "ENTER", [{"field_id": "f_05_30", "row": 4, "col": 30, "value": "1234567890"}, {"field_id": "f_06_30", "row": 5, "col": 30, "value": "5550100"}]), s3, _action(4, "F12"), cancel_screen])
    return str(package)


def _generate_account_list(root: Path) -> str:
    builder = _domain_package(
        root,
        package_id="synthetic_account_list_subfile",
        transaction_id="account_list_select",
        description="Generated subfile selection with paging.",
        scenario="subfile selection with paging indicators",
        cases=[
            case_spec("happy_path", purpose="canonical_success", case_kind="happy_path"),
            case_spec("paged_selection", purpose="canonical_success", case_kind="recorded_path"),
        ],
        tags=["subfile", "selection", "paging", "sensitive"],
        simulates_maturity_level="L3",
        business_process="account work queue selection",
        operator_goal="select an account row from a paged list and review the account status detail",
        known_limitations=["Subfile row-selection and pagination semantics require human review before wrapper design."],
    )
    package = builder.package
    builder.write_field_map(display_name="Account List Select", endpoint_path="/transactions/account-list-select", fields=[
        {"screen_ref": "screen_001", "field_id": "f_05_03", "name": "selected_option", "role": "input", "type": "string", "required": True, "sensitive": False},
        {"screen_ref": "screen_003", "field_id": "f_05_03", "name": "selected_option", "role": "input", "type": "string", "required": True, "sensitive": False, "optional": True, "case_refs": ["paged_selection"]},
        {"screen_ref": "screen_003", "field_id": "f_04_28", "name": "account_number", "role": "output", "type": "string", "sensitive": True, "case_refs": ["happy_path"]},
        {"screen_ref": "screen_003", "field_id": "f_05_28", "name": "account_status", "role": "output", "type": "string", "sensitive": False, "case_refs": ["happy_path"]},
        {"screen_ref": "screen_005", "field_id": "f_04_28", "name": "account_number", "role": "output", "type": "string", "sensitive": True, "optional": True, "case_refs": ["paged_selection"]},
        {"screen_ref": "screen_005", "field_id": "f_05_28", "name": "account_status", "role": "output", "type": "string", "sensitive": False, "optional": True, "case_refs": ["paged_selection"]},
    ])
    list_text = [_line(""), _line("   Opt  Account     Name                 Status"), _line("   _    44550001    SAMPLE ONE           OPEN"), _line("   _    44550002    SAMPLE TWO           HOLD"), _line("   _    44550003    SAMPLE THREE         OPEN"), _line("   _    44550004    SAMPLE FOUR          OPEN"), _line("   More...   F8=PageDown   F7=PageUp   F12=Cancel")]
    detail_text = [_line(""), _line("   Account number . . . . .  44550002"), _line("   Account status . . . . .  HOLD"), _line("   F3=Exit   F12=Cancel")]
    builder.write_trace("happy_path", [
        _screen(1, "ACCOUNT LIST", list_text, [{"id": f"f_0{row}_03", "row": row, "col": 3, "length": 1, "value": "", "protected": False, "display_only": False, "hidden": False, "attributes": []} for row in range(5, 9)]),
        _action(2, "ENTER", [{"field_id": "f_05_03", "row": 5, "col": 3, "value": "1"}]),
        _screen(3, "ACCOUNT DETAIL", detail_text, [{"id": "f_04_28", "row": 4, "col": 28, "length": 8, "value": "44550002", "protected": True, "display_only": True, "hidden": False, "attributes": []}, {"id": "f_05_28", "row": 5, "col": 28, "length": 10, "value": "HOLD", "protected": True, "display_only": True, "hidden": False, "attributes": []}]),
    ])
    page2_text = [_line(""), _line("   Opt  Account     Name                 Status"), _line("   _    44550005    SAMPLE FIVE          OPEN"), _line("   _    44550006    SAMPLE SIX           REVIEW"), _line("   _    44550007    SAMPLE SEVEN         OPEN"), _line("   _    44550008    SAMPLE EIGHT         OPEN"), _line("   Bottom   F7=PageUp   F12=Cancel")]
    page2_detail_text = [_line(""), _line("   Account number . . . . .  44550006"), _line("   Account status . . . . .  REVIEW"), _line("   F3=Exit   F12=Cancel")]
    builder.write_trace("paged_selection", [
        _screen(1, "ACCOUNT LIST", list_text, [{"id": f"f_0{row}_03", "row": row, "col": 3, "length": 1, "value": "", "protected": False, "display_only": False, "hidden": False, "attributes": []} for row in range(5, 9)]),
        _action(2, "PAGEDOWN"),
        _screen(3, "ACCOUNT LIST", page2_text, [{"id": f"f_0{row}_03", "row": row, "col": 3, "length": 1, "value": "", "protected": False, "display_only": False, "hidden": False, "attributes": []} for row in range(5, 9)]),
        _action(4, "ENTER", [{"field_id": "f_05_03", "row": 5, "col": 3, "value": "1"}]),
        _screen(5, "ACCOUNT DETAIL", page2_detail_text, [{"id": "f_04_28", "row": 4, "col": 28, "length": 8, "value": "44550006", "protected": True, "display_only": True, "hidden": False, "attributes": []}, {"id": "f_05_28", "row": 5, "col": 28, "length": 10, "value": "REVIEW", "protected": True, "display_only": True, "hidden": False, "attributes": []}]),
    ])
    return str(package)


def _generate_inventory_plain_text(root: Path) -> str:
    builder = _domain_package(
        root,
        package_id="synthetic_inventory_plain_text",
        transaction_id="inventory_lookup",
        description="Plain-text-only inventory lookup with field-map coordinates.",
        scenario="plain-text-only inventory lookup",
        cases=[case_spec("happy_path", purpose="canonical_success", case_kind="happy_path")],
        tags=["plain_text_only", "absent_hidden_field"],
        simulates_maturity_level="L2",
        business_process="inventory availability lookup",
        operator_goal="enter an item number and confirm description and available quantity",
        known_limitations=["Trace text has no structured field metadata; coordinates come from the field map."],
    )
    package = builder.package
    builder.write_field_map(display_name="Inventory Lookup", endpoint_path="/transactions/inventory-lookup", fields=[
        {"screen_ref": "screen_001", "row": 4, "col": 24, "length": 8, "name": "item_number", "role": "input", "type": "string", "required": True, "sensitive": False},
        {"screen_ref": "screen_003", "row": 5, "col": 24, "length": 20, "name": "item_description", "role": "output", "type": "string", "sensitive": False},
        {"screen_ref": "screen_003", "row": 6, "col": 24, "length": 6, "name": "quantity_available", "role": "output", "type": "string", "sensitive": False},
    ])
    builder.write_trace("happy_path", [
        _screen(1, "INVENTORY LOOKUP", [_line(""), _line("   Item number . . .  ________"), _line("   F3=Exit   F12=Cancel")], []),
        _action(2, "ENTER", [{"row": 4, "col": 24, "value": "ITM00042"}]),
        _screen(3, "INVENTORY DETAIL", [_line(""), _line("   Item number . . .  ITM00042"), _line("   Description . . .  SAMPLE PART"), _line("   Quantity . . . . . 000125"), _line("   F3=Exit   F12=Cancel")], []),
    ])
    return str(package)


def _generate_low_confidence(root: Path) -> str:
    builder = _guardrail_package(
        root,
        package_id="synthetic_low_confidence_guardrail",
        transaction_id="unknown_transaction",
        description="Plain-text low-confidence trace without field metadata or field map.",
        scenario="low-confidence plain-text trace",
        cases=[case_spec("low_confidence", purpose="guardrail", case_kind="low_confidence")],
        tags=["low_confidence"],
        field_map=None,
    )
    package = builder.package
    builder.write_trace("low_confidence", [
        _screen(1, "UNKNOWN", [_line(""), _line("                         ________")], []),
        _action(2, "ENTER", [{"row": 4, "col": 26, "value": "X"}]),
        _screen(3, "UNKNOWN", [_line(""), _line("                         OK")], []),
    ])
    return str(package)


def _generate_navigation(root: Path) -> str:
    builder = _domain_package(
        root,
        package_id="synthetic_navigation_no_credentials",
        transaction_id="menu_navigation",
        description="Generated menu navigation trace with no credentials or host login automation.",
        scenario="login/menu navigation without credential capture",
        cases=[case_spec("menu_to_transaction", purpose="navigation", case_kind="recorded_path")],
        tags=["navigation", "menu", "no_credentials"],
        simulates_maturity_level="L2",
        business_process="operator menu navigation",
        operator_goal="navigate from a neutral entry screen to a transaction screen without capturing credentials",
        known_limitations=["Navigation trace is useful setup evidence, not a contract-ready business transaction by itself."],
    )
    package = builder.package
    builder.write_field_map(
        display_name="Menu Navigation",
        endpoint_path="/transactions/menu-navigation",
        fields=[
            {"screen_ref": "screen_003", "field_id": "f_04_20", "name": "menu_selection", "role": "input", "type": "string", "required": True, "sensitive": False},
            {"screen_ref": "screen_005", "field_id": "f_04_28", "name": "selected_transaction", "role": "output", "type": "string", "required": False, "sensitive": False},
        ],
    )
    entry_screen = _screen(1, "SESSION ENTRY", [_line(""), _line("   Approved offline capture - credentials not recorded"), _line("   Press ENTER to continue")], [])
    menu_screen = _screen(3, "MAIN MENU", [_line(""), _line("   Selection . . .  _"), _line("   1. Order inquiry"), _line("   2. Account list"), _line("   F3=Exit")], [{"id": "f_04_20", "row": 4, "col": 20, "length": 1, "value": "", "protected": False, "display_only": False, "hidden": False, "attributes": []}])
    ready_screen = _screen(5, "TRANSACTION READY", [_line(""), _line("   Selected transaction . .  ORDER INQUIRY"), _line("   F3=Exit   F12=Cancel")], [{"id": "f_04_28", "row": 4, "col": 28, "length": 20, "value": "ORDER INQUIRY", "protected": True, "display_only": True, "hidden": False, "attributes": []}])
    builder.write_trace("menu_to_transaction", [entry_screen, _action(2, "ENTER"), menu_screen, _action(4, "ENTER", [{"field_id": "f_04_20", "row": 4, "col": 20, "value": "1"}]), ready_screen])
    return str(package)


def _generate_boundary_locale(root: Path) -> str:
    tags = [
            "boundary_values",
            "blank_optional_input",
            "max_length_input",
            "invalid_date",
            "negative_amount",
            "decimal_amount",
            "currency_format",
            "locale_formats",
            "leading_zero_identifier",
            "validation_error",
    ]
    builder = _domain_package(
        root,
        package_id="synthetic_boundary_locale_values",
        transaction_id="payment_review",
        description="Generated boundary and locale variants for fixed-width payment review screens.",
        scenario="boundary values and locale-formatted business fields",
        cases=[
            case_spec("blank_optional", purpose="canonical_success", case_kind="recorded_path"),
            case_spec("max_length_decimal", purpose="canonical_success", case_kind="recorded_path"),
            case_spec("negative_amount", purpose="canonical_success", case_kind="recorded_path"),
            case_spec("invalid_date", purpose="canonical_error", case_kind="validation_error"),
            case_spec("locale_variant", purpose="canonical_success", case_kind="recorded_path"),
        ],
        tags=tags,
        simulates_maturity_level="L2",
        business_process="payment review",
        operator_goal="enter invoice, amount, requested date, and optional discount values and verify the host response",
        known_limitations=["Synthetic payment amounts preserve common fixed-width and locale edge cases but are not financial records."],
    )
    package = builder.package
    builder.write_field_map(
        display_name="Payment Review",
        endpoint_path="/transactions/payment-review",
        fields=[
            {"screen_ref": "screen_001", "field_id": "f_04_30", "name": "invoice_code", "role": "input", "type": "string", "required": True, "sensitive": False},
            {"screen_ref": "screen_001", "field_id": "f_05_30", "name": "amount_text", "role": "input", "type": "string", "required": True, "sensitive": False, "description": "Fixed-width business amount preserved as text."},
            {"screen_ref": "screen_001", "field_id": "f_06_30", "name": "requested_date", "role": "input", "type": "string", "required": True, "sensitive": False},
            {"screen_ref": "screen_001", "field_id": "f_07_30", "name": "discount_code", "role": "input", "type": "string", "required": False, "sensitive": False},
            {"screen_ref": "screen_003", "field_id": "f_04_30", "name": "invoice_code", "role": "output", "type": "string", "required": False, "sensitive": False, "optional": True},
            {"screen_ref": "screen_003", "field_id": "f_05_30", "name": "posted_amount", "role": "output", "type": "string", "required": False, "sensitive": False, "optional": True},
            {"screen_ref": "screen_003", "field_id": "f_06_30", "name": "posted_date", "role": "output", "type": "string", "required": False, "sensitive": False, "optional": True},
            {"screen_ref": "screen_003", "field_id": "f_07_30", "name": "discount_applied", "role": "output", "type": "string", "required": False, "sensitive": False, "optional": True},
            {"screen_ref": "screen_003", "field_id": "f_22_08", "name": "message_text", "role": "error_message", "type": "string", "required": False, "sensitive": False, "optional": True},
        ],
    )
    entry = _screen(1, "PAYMENT REVIEW", [
        _line(""),
        _line("   Invoice code . . . . . .  __________"),
        _line("   Amount . . . . . . . . .  ____________"),
        _line("   Requested date . . . . .  __________"),
        _line("   Discount code . . . . .   ________"),
        _line("   F3=Exit   F12=Cancel"),
    ], [
        {"id": "f_04_30", "row": 4, "col": 30, "length": 10, "value": "", "protected": False, "display_only": False, "hidden": False, "attributes": []},
        {"id": "f_05_30", "row": 5, "col": 30, "length": 12, "value": "", "protected": False, "display_only": False, "hidden": False, "attributes": []},
        {"id": "f_06_30", "row": 6, "col": 30, "length": 10, "value": "", "protected": False, "display_only": False, "hidden": False, "attributes": []},
        {"id": "f_07_30", "row": 7, "col": 30, "length": 8, "value": "", "protected": False, "display_only": False, "hidden": False, "attributes": []},
    ])

    def ok_screen(invoice: str, amount: str, date_text: str, discount: str) -> dict[str, Any]:
        return _screen(3, "PAYMENT RESULT", [
            _line(""),
            _line(f"   Invoice code . . . . . .  {invoice}"),
            _line(f"   Posted amount . . . . . . {amount}"),
            _line(f"   Posted date . . . . . . . {date_text}"),
            _line(f"   Discount applied . . . .  {discount}"),
            _line("   F3=Exit   F12=Cancel"),
        ], [
            {"id": "f_04_30", "row": 4, "col": 30, "length": 10, "value": invoice, "protected": True, "display_only": True, "hidden": False, "attributes": []},
            {"id": "f_05_30", "row": 5, "col": 30, "length": 12, "value": amount, "protected": True, "display_only": True, "hidden": False, "attributes": []},
            {"id": "f_06_30", "row": 6, "col": 30, "length": 10, "value": date_text, "protected": True, "display_only": True, "hidden": False, "attributes": []},
            {"id": "f_07_30", "row": 7, "col": 30, "length": 8, "value": discount, "protected": True, "display_only": True, "hidden": False, "attributes": []},
        ])

    def payment_action(invoice: str, amount: str, date_text: str, discount: str = "") -> dict[str, Any]:
        return _action(2, "ENTER", [
            {"field_id": "f_04_30", "row": 4, "col": 30, "value": invoice},
            {"field_id": "f_05_30", "row": 5, "col": 30, "value": amount},
            {"field_id": "f_06_30", "row": 6, "col": 30, "value": date_text},
            {"field_id": "f_07_30", "row": 7, "col": 30, "value": discount},
        ])

    builder.write_trace("blank_optional", [
        entry,
        payment_action("INV0000001", "00000000.01", "2026-01-15", ""),
        ok_screen("INV0000001", "00000000.01", "2026-01-15", "NONE"),
    ])
    builder.write_trace("max_length_decimal", [
        entry,
        payment_action("INV1234567", "99999999.99", "2026-12-31", "DISC2026"),
        ok_screen("INV1234567", "99999999.99", "2026-12-31", "DISC2026"),
    ])
    builder.write_trace("negative_amount", [
        entry,
        payment_action("CRD0000001", "-000045.50", "2026-01-15", ""),
        ok_screen("CRD0000001", "-000045.50", "2026-01-15", "CREDIT"),
    ])
    builder.write_trace("locale_variant", [
        entry,
        payment_action("LOC0000001", "1.234,56", "15/01/2026", "EURO2026"),
        ok_screen("LOC0000001", "1.234,56", "15/01/2026", "EURO2026"),
    ])
    invalid_message = "Requested date invalid - use approved format"
    builder.write_trace("invalid_date", [
        entry,
        payment_action("INV0000002", "00000010.00", "31/02/2026", ""),
        _screen(3, "PAYMENT REVIEW", [
            _line(""),
            _line("   Invoice code . . . . . .  __________"),
            _line("   Amount . . . . . . . . .  ____________"),
            _line("   Requested date . . . . .  __________"),
            _line("   Discount code . . . . .   ________"),
            *[_line("") for _ in range(13)],
            _line("       " + invalid_message),
        ], [
            {"id": "f_04_30", "row": 4, "col": 30, "length": 10, "value": "", "protected": False, "display_only": False, "hidden": False, "attributes": ["error"]},
            {"id": "f_05_30", "row": 5, "col": 30, "length": 12, "value": "", "protected": False, "display_only": False, "hidden": False, "attributes": ["error"]},
            {"id": "f_06_30", "row": 6, "col": 30, "length": 10, "value": "", "protected": False, "display_only": False, "hidden": False, "attributes": ["error"]},
            {"id": "f_07_30", "row": 7, "col": 30, "length": 8, "value": "", "protected": False, "display_only": False, "hidden": False, "attributes": []},
            {"id": "f_22_08", "row": 22, "col": 8, "length": len(invalid_message), "value": invalid_message, "protected": True, "display_only": True, "hidden": False, "attributes": ["message"]},
        ]),
    ])
    return str(package)


def _generate_repeated_labels(root: Path) -> str:
    builder = _domain_package(
        root,
        package_id="synthetic_repeated_labels",
        transaction_id="status_review",
        description="Generated status review screen with repeated labels requiring field-map disambiguation.",
        scenario="screen with repeated labels disambiguated by field map",
        cases=[case_spec("happy_path", purpose="canonical_success", case_kind="happy_path")],
        tags=["repeated_labels", "field_reuse_ambiguity", "inquiry"],
        simulates_maturity_level="L2",
        business_process="cross-record status review",
        operator_goal="enter a review key and compare similarly labeled account, order, code, and amount fields",
        known_limitations=["Repeated labels are intentionally ambiguous without the supplied field map."],
    )
    package = builder.package
    builder.write_field_map(
        display_name="Status Review",
        endpoint_path="/transactions/status-review",
        fields=[
            {"screen_ref": "screen_001", "field_id": "f_04_30", "name": "review_key", "role": "input", "type": "string", "required": True, "sensitive": False},
            {"screen_ref": "screen_003", "field_id": "f_04_30", "name": "account_status", "role": "output", "type": "string", "required": False, "sensitive": False},
            {"screen_ref": "screen_003", "field_id": "f_05_30", "name": "order_status", "role": "output", "type": "string", "required": False, "sensitive": False},
            {"screen_ref": "screen_003", "field_id": "f_06_30", "name": "account_code", "role": "output", "type": "string", "required": False, "sensitive": False},
            {"screen_ref": "screen_003", "field_id": "f_07_30", "name": "order_code", "role": "output", "type": "string", "required": False, "sensitive": False},
            {"screen_ref": "screen_003", "field_id": "f_08_30", "name": "base_amount", "role": "output", "type": "string", "required": False, "sensitive": False},
            {"screen_ref": "screen_003", "field_id": "f_09_30", "name": "adjusted_amount", "role": "output", "type": "string", "required": False, "sensitive": False},
        ],
    )
    builder.write_trace("happy_path", [
        _screen(1, "STATUS REVIEW", [
            _line(""),
            _line("   Review key . . . . . . .  ______"),
            _line("   F3=Exit   F12=Cancel"),
        ], [{"id": "f_04_30", "row": 4, "col": 30, "length": 6, "value": "", "protected": False, "display_only": False, "hidden": False, "attributes": []}]),
        _action(2, "ENTER", [{"field_id": "f_04_30", "row": 4, "col": 30, "value": "SRV001"}]),
        _screen(3, "STATUS REVIEW DETAIL", [
            _line(""),
            _line("   Account status . . . . .  ACTIVE"),
            _line("   Order status . . . . . .  HELD"),
            _line("   Code . . . . . . . . . .  ACCT01"),
            _line("   Code . . . . . . . . . .  ORD99"),
            _line("   Amount . . . . . . . . .  000010.00"),
            _line("   Amount . . . . . . . . .  000250.00"),
            _line("   F3=Exit   F12=Cancel"),
        ], [
            {"id": "f_04_30", "row": 4, "col": 30, "length": 8, "value": "ACTIVE", "protected": True, "display_only": True, "hidden": False, "attributes": []},
            {"id": "f_05_30", "row": 5, "col": 30, "length": 8, "value": "HELD", "protected": True, "display_only": True, "hidden": False, "attributes": []},
            {"id": "f_06_30", "row": 6, "col": 30, "length": 6, "value": "ACCT01", "protected": True, "display_only": True, "hidden": False, "attributes": []},
            {"id": "f_07_30", "row": 7, "col": 30, "length": 6, "value": "ORD99", "protected": True, "display_only": True, "hidden": False, "attributes": []},
            {"id": "f_08_30", "row": 8, "col": 30, "length": 10, "value": "000010.00", "protected": True, "display_only": True, "hidden": False, "attributes": []},
            {"id": "f_09_30", "row": 9, "col": 30, "length": 10, "value": "000250.00", "protected": True, "display_only": True, "hidden": False, "attributes": []},
        ]),
    ])
    return str(package)


def _generate_exception_paths(root: Path) -> str:
    builder = _domain_package(
        root,
        package_id="synthetic_exception_paths",
        transaction_id="access_review",
        description="Generated negative paths and function-key traces.",
        scenario="negative paths and function-key traces",
        cases=[
            case_spec("validation_error", purpose="canonical_error", case_kind="validation_error"),
            case_spec("permission_denied", purpose="canonical_error", case_kind="permission_denied"),
            case_spec("cancel", purpose="non_contract", case_kind="cancel"),
            case_spec("unsupported_aid", purpose="guardrail", case_kind="unsupported_aid"),
            case_spec("screen_27x132", purpose="canonical_success", case_kind="recorded_path"),
            case_spec("attribute_drift", purpose="drift_evidence", case_kind="attribute_drift"),
        ],
        tags=[
            "validation_error",
            "permission_denied",
            "cancel_fkey",
            "same_screen_loop",
            "unsupported_aid",
            "screen_size_27x132",
            "attribute_drift",
        ],
        simulates_maturity_level="L3",
        business_process="access exception review",
        operator_goal="enter a review code and capture validation, permission, cancel, and wide-screen exception outcomes",
        known_limitations=["Exception paths are synthetic but model practical error and function-key handling."],
    )
    package = builder.package
    builder.write_field_map(display_name="Access Review", endpoint_path="/transactions/access-review", fields=[
        {"screen_ref": "screen_001", "field_id": "f_04_30", "name": "review_code", "role": "input", "type": "string", "required": True, "sensitive": False},
        {"screen_ref": "screen_003", "field_id": "f_22_08", "name": "message_text", "role": "error_message", "type": "string", "optional": True, "sensitive": False},
    ])
    start = _screen(1, "ACCESS REVIEW", [_line(""), _line("   Review code . . . . . .  ______"), _line("   F3=Exit   F12=Cancel")], [{"id": "f_04_30", "row": 4, "col": 30, "length": 6, "value": "", "protected": False, "display_only": False, "hidden": False, "attributes": []}])
    for case, value, message, aid in [
        ("validation_error", "", "Review code required - press reset", "ENTER"),
        ("permission_denied", "DENIED", "Permission denied for this review", "ENTER"),
        ("unsupported_aid", "HELP", "Unsupported aid preserved as raw value", "ROLLUP"),
    ]:
        builder.write_trace(case, [start, _action(2, aid, [{"field_id": "f_04_30", "row": 4, "col": 30, "value": value}]), _screen(3, "ACCESS REVIEW", [_line(""), _line("   Review code . . . . . .  ______"), *[_line("") for _ in range(15)], _line("       " + message)], [{"id": "f_04_30", "row": 4, "col": 30, "length": 6, "value": "", "protected": False, "display_only": False, "hidden": False, "attributes": ["error"]}, {"id": "f_22_08", "row": 22, "col": 8, "length": min(len(message), 40), "value": message, "protected": True, "display_only": True, "hidden": False, "attributes": ["message"]}])])
    builder.write_trace("cancel", [start, _action(2, "F12"), _screen(3, "ACCESS MENU", [_line(""), _line("   Selection . . .  _"), _line("   F3=Exit")], [])])
    builder.write_trace("screen_27x132", [_screen(1, "WIDE ACCESS REVIEW", [_line("   Review code . . . . . .  ______", 132)], [{"id": "f_04_30", "row": 4, "col": 30, "length": 6, "value": "", "protected": False, "display_only": False, "hidden": False, "attributes": []}], rows=27, cols=132), _action(2, "ENTER", [{"field_id": "f_04_30", "row": 4, "col": 30, "value": "ABC123"}]), _screen(3, "WIDE ACCESS RESULT", [_line("   Result . . . . . . . .  OK", 132)], [{"id": "f_04_30", "row": 4, "col": 30, "length": 6, "value": "ABC123", "protected": True, "display_only": True, "hidden": False, "attributes": []}], rows=27, cols=132)])
    attr_start = _screen(1, "ACCESS REVIEW", [_line(""), _line("   Review code . . . . . .  ______"), _line("   F3=Exit   F12=Cancel")], [{"id": "f_04_30", "row": 4, "col": 30, "length": 6, "value": "", "protected": False, "display_only": False, "hidden": False, "attributes": ["reverse_image"]}])
    attr_message = "Attribute change detected for review"
    builder.write_trace("attribute_drift", [attr_start, _action(2, "ENTER", [{"field_id": "f_04_30", "row": 4, "col": 30, "value": "ATTR01"}]), _screen(3, "ACCESS REVIEW", [_line(""), _line("   Review code . . . . . .  ______"), *[_line("") for _ in range(15)], _line("       " + attr_message)], [{"id": "f_04_30", "row": 4, "col": 30, "length": 6, "value": "", "protected": False, "display_only": False, "hidden": False, "attributes": ["reverse_image"]}, {"id": "f_22_08", "row": 22, "col": 8, "length": len(attr_message), "value": attr_message, "protected": True, "display_only": True, "hidden": False, "attributes": ["message", "changed_attribute"]}])])
    return str(package)


def coverage_report(package_root: str | Path) -> dict[str, Any]:
    root = Path(package_root)
    tags: set[str] = set()
    packages: list[dict[str, Any]] = []
    for manifest_path in sorted(root.glob("*/manifest.yml")):
        data = yaml.safe_load(manifest_path.read_text()) or {}
        package_tags = set(data.get("tags", []))
        tags.update(package_tags)
        packages.append({
            "package_id": data.get("package_id"),
            "maturity_level": data.get("maturity_level"),
            "actual_maturity_level": data.get("actual_maturity_level"),
            "simulates_maturity_level": data.get("simulates_maturity_level"),
            "evidence_kind": data.get("evidence_kind"),
            "tags": sorted(package_tags),
        })
    missing = sorted(REQUIRED_COVERAGE_TAGS - tags)
    covered_required = tags.intersection(REQUIRED_COVERAGE_TAGS)
    return {
        "schema_version": "1.0",
        "package_count": len(packages),
        "covered_tag_count": len(covered_required),
        "required_tag_count": len(REQUIRED_COVERAGE_TAGS),
        "coverage_pct": round((len(covered_required) / len(REQUIRED_COVERAGE_TAGS)) * 100, 2) if REQUIRED_COVERAGE_TAGS else 100.0,
        "covered_tags": sorted(tags),
        "missing_tags": missing,
        "complete": not missing,
        "packages": packages,
    }
