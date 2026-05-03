# Adapter Authoring Boundary

Adapters may transform authorized site-specific exports into the normalized CSV and YAML consumed by core.

Adapters must remain outside the core package when they depend on a proprietary format, device API, facility-management system, credential, or live collection mechanism.

Core adapter contract:

- Write `pdu_power.csv` with normalized active kW readings.
- Write `inlet_temps.csv` with normalized inlet-temperature readings.
- Write `cabinet_profile.yml` with site-supplied limits.
- Preserve source row identifiers where possible.
- Do not infer electrical topology unless the source explicitly provides it.
- Do not call live controls.
- Do not store credentials.
- Do not alter PDU, BMS, DCIM, cooling, contract, reservation, or allocation state.

Recommended adapter output directory:

```text
case/
  pdu_power.csv
  inlet_temps.csv
  cabinet_profile.yml
  adapter_notes.md
```

Run `cabinet-burst-envelope doctor` before sharing the case.
