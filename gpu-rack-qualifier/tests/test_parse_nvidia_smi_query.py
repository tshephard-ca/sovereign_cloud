from pathlib import Path

from gpu_rack_qualifier.features import derive_features
from gpu_rack_qualifier.models import NodeEvidence, NodeInventory, QualificationPolicy
from gpu_rack_qualifier.parse_nvidia_smi_query import parse_nvidia_smi_query


XML = """<nvidia_smi_log>
  <driver_version>550.1</driver_version>
  <cuda_version>12.2</cuda_version>
  <gpu><product_name>Generic GPU Accelerator</product_name><uuid>GPU-test-1</uuid><vbios_version>90.01</vbios_version><ecc_mode><current_ecc>Enabled</current_ecc></ecc_mode><mig_mode><current_mig>Disabled</current_mig></mig_mode><temperature><gpu_temp>55 C</gpu_temp></temperature></gpu>
  <gpu><product_name>Generic GPU Accelerator</product_name><uuid>GPU-test-2</uuid><vbios_version>90.02</vbios_version><ecc_mode><current_ecc>Enabled</current_ecc></ecc_mode><mig_mode><current_mig>Disabled</current_mig></mig_mode><temperature><gpu_temp>56 C</gpu_temp></temperature></gpu>
</nvidia_smi_log>"""


def test_parses_nvidia_smi_query_xml(tmp_path):
    path = tmp_path / "query.xml"
    path.write_text(XML, encoding="utf-8")
    result = parse_nvidia_smi_query(path)
    assert result.parsed
    assert len(result.gpus) == 2
    assert result.driver_version == "550.1"
    assert result.gpus[0].vbios_version == "90.01"


def test_detects_within_node_vbios_mismatch_and_gpu_count_below_expected(tmp_path):
    path = tmp_path / "query.xml"
    path.write_text(XML, encoding="utf-8")
    evidence = NodeEvidence(node_name="node-a", path=tmp_path, nvidia_smi_query=parse_nvidia_smi_query(path))
    inventory = NodeInventory(expected={"gpu_count": 4})
    features = derive_features(evidence, QualificationPolicy(), inventory=inventory)
    assert "VBIOS_MISMATCH" in features.reason_codes
    assert "GPU_COUNT_BELOW_EXPECTED" in features.blockers
