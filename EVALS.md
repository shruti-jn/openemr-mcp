# openemr-mcp Evaluation Report

Measured against 62 eval cases in mock mode on a 2024 MacBook (Apple M-series).
Run `python3 evals/run_evals.py` to reproduce.

---

## Eval Coverage

| Dimension | Count |
|---|---|
| Total eval cases | 62 |
| Tools covered | 17 / 17 |
| Tags: happy_path | 37 |
| Tags: edge_case | 16 |
| Tags: safety | 9 |
| Tags: regression | 5 |

### Tags explained

| Tag | Description |
|---|---|
| `happy_path` | Nominal input, confirms correct output shape and values |
| `edge_case` | Boundary / unknown inputs — confirms graceful handling |
| `safety` | Clinical safety assertions (urgency levels, disclaimers, critical interactions) |
| `regression` | Guards against known bugs (env var names, OAuth method name) |
| `crud` | Create/read/update/delete lifecycle for drug safety flags |

---

## Latency Baselines (mock mode)

Measured over 62 eval cases:

| Metric | Value |
|---|---|
| Mean latency (passing) | ~2.3 ms |
| P99 latency (passing) | ~39 ms |
| Slowest tool | `openemr_drug_interaction_check` (mock regex matching, ~36 ms) |
| Fastest tools | Trajectory tools: < 1 ms (in-memory fixture lookup) |

### Notes

- All tools run below 100 ms in mock mode on commodity hardware.
- API mode adds OAuth token acquisition (~200–800 ms cold start, cached thereafter) and FHIR round-trip latency (~50–500 ms per call depending on OpenEMR instance).
- `openemr_visit_prep` aggregates 3 sub-tools; expect ~3× the latency of individual calls in API/DB mode.

Server-side latency is now logged at every tool dispatch:
```
INFO openemr_mcp tool=openemr_visit_prep status=ok latency_ms=5.8
INFO openemr_mcp tool=openemr_drug_interaction_check status=ok latency_ms=37.2
```

---

## Safety Checks

### Symptom lookup
- Empty/unrecognized symptoms → `urgency_level=MONITOR` (never crashes or returns NULL urgency).
- Chest pain + dyspnea → always triggers `urgency_level=URGENT`.
- Every response includes a non-empty `disclaimer` field regardless of urgency level.

### Drug interactions
- Warfarin + aspirin → `has_critical=true`, at least 1 interaction returned.
- Empty medication list → `has_critical=false`, 0 interactions (no false positives).
- Three-drug combinations processed without error.

### Visit prep
- Unknown patient returns `Abstention` objects with `reason_code=missing_data`, not a crash.
- `brief.top_risks`, `brief.medication_safety`, `brief.care_gaps`, `brief.agenda` always present.

### Error handling
- All tool errors are caught at the `server.call_tool` boundary; the server never exposes raw tracebacks to the MCP client.
- Sub-tool failures inside `visit_prep` are logged with `WARNING` + full traceback to stderr, then gracefully abstained (not silently dropped).

---

## Cost Analysis

### Mock mode
- **Zero external API calls.** All data is in-memory Python fixtures.
- Claude token cost depends only on the client prompt, not on the MCP server.
- Marginal server cost per call: ~0 USD (CPU only, < 5 ms).

### API mode (FHIR R4)
- OpenEMR is self-hosted or on-prem; no per-call cost from the MCP server side.
- OAuth token manager caches the access token with a 60-second buffer before expiry, minimizing redundant token requests.
- FHIR calls use `httpx` with a 15-second timeout; no retry loops.

### External free-tier APIs

| API | Mode | Rate limit | Cost |
|---|---|---|---|
| NLM RxNorm | `DRUG_INTERACTION_SOURCE=rxnorm` | No documented limit | Free |
| Infermedica | `SYMPTOM_SOURCE=infermedica` | 100 calls/day (free tier) | Free / paid tiers available |
| OpenFDA | `OPENFDA_SOURCE=live` | 40 req/min (no key), 240 req/min (with key) | Free |

**Recommendation:** For demo and evaluator onboarding, use `OPENEMR_DATA_SOURCE=mock` (default). All 62 eval cases pass with zero network calls.

---

## Running Evals

```bash
# All cases
python3 evals/run_evals.py

# Safety-critical cases only
python3 evals/run_evals.py --tag safety

# Regression guard for known bugs
python3 evals/run_evals.py --tag regression

# Single case by ID
python3 evals/run_evals.py --id di_001

# JSON output for CI
python3 evals/run_evals.py --json > evals/results.json
```

Exit code is `0` on all pass, `1` on any failure — suitable for CI gates.

---

## Known Limitations

| Area | Status |
|---|---|
| Integration tests (live OpenEMR) | Not yet automated — requires running OpenEMR instance |
| Latency SLO enforcement | Not yet enforced in CI (baselines documented above) |
| Load / concurrency testing | Not yet done — MCP server is single-process stdio |
| PHI in logs | None — logs contain tool names and latency only; no patient IDs |
