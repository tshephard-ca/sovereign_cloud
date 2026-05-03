"""JUnit XML writer for CI."""

from __future__ import annotations

from pathlib import Path
import xml.etree.ElementTree as ET

from .models import RunResults


def write_junit(path: str | Path, results: RunResults, *, fail_on_review: bool = False) -> None:
    suite = ET.Element(
        "testsuite",
        {
            "name": results.pack_id,
            "tests": str(len(results.test_results)),
            "failures": str(sum(item.status == "FAIL" or (fail_on_review and item.status == "REVIEW") for item in results.test_results)),
            "skipped": str(sum(item.status == "SKIPPED" or (item.status == "REVIEW" and not fail_on_review) for item in results.test_results)),
        },
    )
    for item in results.test_results:
        case = ET.SubElement(suite, "testcase", {"classname": results.endpoint_id, "name": item.test_case_id})
        message = "|".join(item.reason_codes)
        if item.status == "FAIL" or (fail_on_review and item.status == "REVIEW"):
            failure = ET.SubElement(case, "failure", {"message": message})
            failure.text = "\n".join(finding.redacted_evidence for finding in item.leakage_findings)
        elif item.status in {"REVIEW", "SKIPPED"}:
            skipped = ET.SubElement(case, "skipped", {"message": message})
            skipped.text = "|".join(item.warnings)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(suite).write(path, encoding="utf-8", xml_declaration=True)
