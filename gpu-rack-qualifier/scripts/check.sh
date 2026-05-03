#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

python -m pytest -q

PYTHONPATH=src python -m gpu_rack_qualifier.cli validate-schemas --schemas-dir schemas >/dev/null
PYTHONPATH=src python -m gpu_rack_qualifier.cli runtime-guard --src-dir src/gpu_rack_qualifier >/dev/null

SCENARIOS=(
  pass
  missing_pairwise_nccl
  weak_pairwise
  topology_weak_path
  topology_review_path
  sensor_warning
  correctness_error
  wrong_count
  timeout
  missing_gpu
  vbios_mismatch
  cuda_drift
  ecc_mismatch
  mig_mismatch
  missing_topology
  malformed_nccl
  malformed_xml
  rack_wide_slow_baseline
  partial_evidence
  bmc_critical
  temperature_warning
  temperature_critical
  sensor_critical
  fan_failure
  driver_drift
  mixed_commissioning
)

for scenario in "${SCENARIOS[@]}"; do
  work_dir="/tmp/rackq-check-${scenario}"
  PYTHONPATH=src python -m gpu_rack_qualifier.cli generate-fixtures \
    --output-dir "${work_dir}" \
    --nodes 8 \
    --gpus-per-node 4 \
    --scenario "${scenario}" \
    --seed 11 \
    --force >/dev/null

  PYTHONPATH=src python -m gpu_rack_qualifier.cli qualify \
    --evidence "${work_dir}/evidence" \
    --node-inventory "${work_dir}/node_inventory.yml" \
    --policy "${work_dir}/qualification_policy.yml" \
    --output-labels "${work_dir}/run/slurm_node_labels.csv" \
    --output-quarantine "${work_dir}/run/quarantine.csv" \
    --output-slurm-fragment "${work_dir}/run/slurm_features.conf.snippet" \
    --output-drain-review "${work_dir}/run/drain_review.sh" \
    --summary "${work_dir}/run/summary.json" \
    --evidence-bundle "${work_dir}/run/evidence_bundle.json" >/dev/null

  PYTHONPATH=src python -m gpu_rack_qualifier.cli validate-schemas \
    --schemas-dir schemas \
    --policy "${work_dir}/qualification_policy.yml" \
    --node-inventory "${work_dir}/node_inventory.yml" \
    --summary "${work_dir}/run/summary.json" \
    --labels "${work_dir}/run/slurm_node_labels.csv" \
    --quarantine "${work_dir}/run/quarantine.csv" \
    --review-queue "${work_dir}/run/review_queue.csv" \
    --evidence-bundle "${work_dir}/run/evidence_bundle.json" \
    --slurm-fragment "${work_dir}/run/slurm_features.conf.snippet" \
    --drain-review "${work_dir}/run/drain_review.sh" >/dev/null
done

echo "rackq local checks passed"
