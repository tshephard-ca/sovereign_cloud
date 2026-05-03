# Architecture

`cabinet-burst-envelope` is organized around a narrow local workflow:

```text
case directory
  -> validation
  -> time alignment
  -> power and inlet-temperature statistics
  -> electrical and thermal envelopes
  -> cabinet envelope
  -> review lane
  -> action queue
  -> assessment packet
```

## Core Boundary

The core accepts normalized CSV and YAML files. It does not collect telemetry, connect to facility systems, reserve capacity, approve capacity, quote, price, control equipment, or invoke proprietary tooling.

## Main Modules

- `analysis.py`: explicit single-cabinet analysis pipeline.
- `electrical.py`: site-limit and feed-risk calculation.
- `thermal.py`: inlet-temperature and simple thermal-slope calculation.
- `envelope.py`: conservative sustained and burst envelope plus evidence quality.
- `decision.py`: review-lane classification and decision trace.
- `remediation.py`: deterministic reason-code to action-queue mapping.
- `packet.py`: complete assessment packet writer.
- `report.py`: JSON, CSV, and Markdown report rendering.
- `portfolio.py`: multi-case review-lane and remediation summary.
- `synthesize.py`: deterministic local scenario generation.

## Business Throughline

The product is not centered on a kW number. It is centered on moving a cabinet into the right business workflow:

- start facility review
- remediate operational risk
- stop expansion discussion
- collect missing evidence

All outputs must preserve the boundary that the packet is review-only and not approval, reservation, quote, customer commitment, or operational instruction.
