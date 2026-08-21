# Telemetry Privacy + Data Quality Hardening Plan

## Objective
Implement comprehensive fixes so `openadapt-telemetry` remains **opt-out by default** while ensuring uploaded telemetry is privacy-safe and metrics are trustworthy.

## Non-Goals
- Replacing Sentry/PostHog providers in this phase.
- Redesigning event taxonomy across downstream repos.
- Introducing fallback telemetry clients in consuming packages.

## Scope
This plan covers four known gaps:
1. Unscrubbed top-level event message fields.
2. Potential PII in tag/context values.
3. Over-classification of users as `internal`.
4. Weakness of unsalted deterministic identifier hashing.

## Current Status
Already fixed in PR #3 and follow-up commits:
- `DO_NOT_TRACK` precedence over explicit enable.
- `send_default_pii` forced to `false` in client init.
- Custom `before_send` cannot bypass privacy scrubber (composed after base filter).
- User object reduced to anonymized ID only.

## Constraints
- Keep global opt-out behavior (`enabled=true` by default).
- Preserve kill switches: `DO_NOT_TRACK=1` and `OPENADAPT_TELEMETRY_ENABLED=false`.
- Avoid breaking existing package integrations.
- Keep telemetry useful for product metrics and debugging.

## Final Decisions (Locked)
1. `DO_NOT_TRACK` always wins over all enable paths.
2. Privacy scrubbing remains centralized in one non-bypassable `before_send`.
3. Internal classification defaults to explicit/env/CI signals only (no implicit git heuristic unless explicitly enabled).
4. Identifier pseudonymization moves to versioned HMAC format with per-install salt.

## Design Principles
1. **Centralized enforcement**: privacy checks should happen in one unavoidable path (`before_send`).
2. **Fail closed**: if privacy logic cannot run, drop/neutralize risky fields.
3. **Compatibility first**: preserve current API surface where practical.
4. **Measurable rollout**: add explicit tests for each risk and each policy guarantee.

## Workstream A: Scrub Top-Level Message Fields
### Problem
`capture_message(...)` content can be sent in `event["message"]`/`logentry` without current scrubbing.

### Options
1. Scrub at call sites (`capture_message`, `capture_event`).
2. Scrub centrally in `before_send` for all event shapes.

### Tradeoff
- Option 1 is easier locally but can miss future call paths.
- Option 2 gives stronger guarantees and lower long-term risk.

### Decision
Use **Option 2** (centralized `before_send` scrubbing).

### Implementation
- Extend `create_before_send_filter()` to scrub:
  - `event["message"]` if string
  - `event["logentry"]["message"]` and `event["logentry"]["formatted"]` if present
- Apply `scrub_string` to those fields.

### Acceptance Criteria
- Messages containing emails/phones/tokens are redacted before send.
- Unit tests cover multiple event payload shapes.

## Workstream B: Context + Tag Value Privacy
### Problem
Current logic scrubs keys but not all string values in tags/contexts.

### Options
1. Keep key-only scrubbing (status quo).
2. Scrub all string values in tags/contexts.
3. Drop tags/contexts entirely.

### Tradeoff
- Option 1 preserves fidelity but has privacy risk.
- Option 3 is safest but removes important observability.
- Option 2 balances privacy and utility.

### Decision
Use **Option 2** with a **strict allowlist for key names** and **no value bypasses**.

### Implementation
- In `before_send`:
  - For `tags`: apply value scrubbing for strings (`scrub_values=True` path or equivalent loop).
  - For `contexts`: scrub nested string values with PII pattern replacement.
- Preserve expected operational tag keys (`package`, `package_version`, `python_version`, `os`, `os_version`, `ci`, `internal`) but still sanitize their values defensively.
- Add a module-level `ALLOWED_OBSERVABILITY_KEYS` constant; additions require:
  - rationale in PR description,
  - test coverage for non-sensitive behavior,
  - explicit reviewer sign-off.

### Acceptance Criteria
- Non-sensitive tags still appear.
- PII-like values in tags/contexts are redacted.
- Tests confirm both preservation and redaction.

## Workstream C: Internal Classification Accuracy
### Problem
Git-repo heuristic can classify normal users as internal.

### Options
1. Explicit-only (`OPENADAPT_INTERNAL`, `OPENADAPT_DEV`, CI).
2. Keep git heuristic but behind opt-in flag.
3. Keep current behavior.

### Tradeoff
- Option 1 gives clean external metrics but may miss some dev runs.
- Option 2 retains flexibility with explicit control.

### Decision
Use **Option 2**:
- default: no git heuristic
- optional enable: `OPENADAPT_INTERNAL_FROM_GIT=true`
- CI remains internal by default.

### Implementation
- Remove unconditional git heuristic from default path.
- Add optional env flag to re-enable it for teams that want this behavior.
- Update docs and tests for both modes.

### Acceptance Criteria
- Standard pip users are not auto-tagged internal.
- Teams can re-enable git-based internal tagging intentionally.

## Workstream D: Stronger User-ID Pseudonymization
### Problem
Unsalted deterministic hashing is vulnerable to dictionary attacks.

### Options
1. Keep unsalted SHA-256 (current).
2. Global static salt in code.
3. Per-install random secret persisted locally and used for HMAC.

### Tradeoff
- Option 1 is weakest.
- Option 2 improves little (salt is public in code).
- Option 3 materially improves privacy while preserving per-install stability.

### Decision
Use **Option 3**.

### Implementation
- Add `anon_salt` to local config (generate once if missing).
- Replace `sha256(id)` with `HMAC-SHA256(anon_salt, id)` (truncated output ok).
- Introduce explicit versioning: output format `anon:v2:<digest>`.
- Keep legacy `anon:<digest>` and `anon:v1:<digest>` inputs idempotent (do not re-hash).
- Migration policy:
  - New emissions always use `anon:v2:*`.
  - Legacy IDs remain accepted but are not emitted by new code.
- Keep idempotence (`anon:*` input should not be re-hashed).

### Acceptance Criteria
- IDs are stable per installation.
- Same raw ID hashes differently across installations.
- Salt is never sent in telemetry payloads.
- On missing/corrupt salt: generate replacement salt, emit warning, continue safely.

## Rollout Plan
1. Baseline current dashboard metrics before changing internal classification behavior.
2. Implement A + B first (highest privacy exposure).
3. Implement D with migration notes and hash-version docs.
4. Implement C using staged rollout (`OPENADAPT_INTERNAL_FROM_GIT` fallback available).
5. Update README privacy section and env variable docs.
6. Run full test suite + add regression tests per workstream.

## Release Gates (Must Pass)
1. Privacy gate: 0 known unsanitized PII leaks in test corpus.
2. Reliability gate: telemetry init/scrub path test pass rate 100% on CI.
3. Data-quality gate: internal-tag share does not increase unexpectedly after C rollout; acceptable delta documented in release notes.
4. Compatibility gate: no breaking API changes for downstream repos (`openadapt-evals`, `openadapt-web`, `openadapt-capture`).

## Test Matrix
- Unit tests:
  - `before_send` scrubbing for message/logentry/tags/contexts/user/request/extra.
  - `DO_NOT_TRACK` precedence over explicit enable.
  - `before_send` composition cannot bypass scrubbing.
  - `send_default_pii` always false.
  - internal classification default vs optional git mode.
  - HMAC anonymization stability and cross-salt divergence.
  - hash version behavior (`anon`, `anon:v1`, `anon:v2` idempotence and emission).
  - missing/corrupted salt recovery behavior.
- Integration smoke:
  - initialize telemetry with custom `before_send` and verify final payload remains scrubbed.
  - simulate downstream package usage with no extra config changes.

## Migration + Compatibility Notes
- Existing APIs remain available.
- Internal-tag behavior changes by default (more accurate external classification).
- User pseudonymous IDs migrate to `anon:v2:*`; one-time continuity break is expected and documented.
- Downstream dashboards should group both legacy and v2 during transition window.

## Risks
1. Over-scrubbing may reduce debugging context.
2. Internal-tag behavior change can shift dashboard baselines.
3. Salt generation/persistence bugs can fragment identity metrics.
4. Allowlist sprawl can gradually reintroduce leakage risk.

## Risk Mitigations
- Add targeted allowlist tests for non-sensitive observability fields.
- Announce metric baseline change in release notes.
- Add robust salt read/write fallback and test corrupted config behavior.
- Require explicit review for allowlist expansion PRs.

## Implementation Checklist
- [ ] A: top-level message/logentry scrubbing
- [ ] B: tag/context value scrubbing
- [ ] C: internal classification flag redesign
- [ ] D: per-install salted HMAC anonymization
- [ ] D1: hash versioning (`anon:v2`) and migration tests
- [ ] D2: salt corruption/missing recovery tests
- [ ] B1: `ALLOWED_OBSERVABILITY_KEYS` introduced + governance note
- [ ] Release gates documented in PR description
- [x] `DO_NOT_TRACK` precedence enforcement
- [x] `send_default_pii=false` enforcement in client init
- [x] custom `before_send` composition with privacy filter
- [x] tests for existing invariants added/updated
- [x] README updates for current invariants
- [ ] PR notes include telemetry-baseline impact

---

## Plan Self-Review
### Strengths
- Centralized privacy enforcement reduces bypass risk.
- Preserves opt-out default while hardening anonymity.
- Explicit acceptance criteria and tests make regressions visible.

### Potential Gaps
- Need to confirm whether per-install pseudonym stability is sufficient for all product analytics use-cases.
- Might require a short “privacy mode strictness” guide for downstream repos.
- May need an explicit dashboard migration playbook for `anon`/`anon:v1` to `anon:v2`.

### Recommended Adjustment Before Implementation
Run a no-code dry run for Workstream C first (baseline-only), then execute A/B/D implementation before enabling C changes broadly.
