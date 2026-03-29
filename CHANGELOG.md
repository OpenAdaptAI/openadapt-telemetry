# CHANGELOG


## v0.3.0 (2026-03-29)

### Features

- Disable telemetry via pyproject.toml [tool.openadapt]
  ([#5](https://github.com/OpenAdaptAI/openadapt-telemetry/pull/5),
  [`a4ffd34`](https://github.com/OpenAdaptAI/openadapt-telemetry/commit/a4ffd34265d78edbf29effb051dbdf1537c23b15))

Enterprises can commit one file to disable telemetry for all devs:

[tool.openadapt] telemetry = false

Walks up from cwd to find nearest pyproject.toml. Uses tomllib (stdlib 3.11+) or tomli fallback.
  Only checks the first pyproject.toml found (nearest to cwd).

Priority: DO_NOT_TRACK > OPENADAPT_TELEMETRY_ENABLED > pyproject.toml > CI detection.

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>


## v0.2.0 (2026-03-17)


## v0.1.0 (2026-03-05)

### Bug Fixes

- Add README badges for license and Python version
  ([`afb480b`](https://github.com/OpenAdaptAI/openadapt-telemetry/commit/afb480b9f71dc488c875da87bdab54b99451f109))

Add standard badges for license and Python version. PyPI badges are commented out until the package
  is published.

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>

- Add README badges for license and Python version
  ([#1](https://github.com/OpenAdaptAI/openadapt-telemetry/pull/1),
  [`5e867d5`](https://github.com/OpenAdaptAI/openadapt-telemetry/commit/5e867d5644028cb97762a0ce53a830d8c0cd96ac))

Add standard badges for license and Python version. PyPI badges are commented out until the package
  is published.

Co-authored-by: Claude Sonnet 4.5 <noreply@anthropic.com>

- Avoid misclassifying non-binary users as internal
  ([`7d64d77`](https://github.com/OpenAdaptAI/openadapt-telemetry/commit/7d64d77423a970c12be06a79ec157a2ab2e6e145))

- Enforce do-not-track precedence and avoid rehashing anon IDs
  ([`6dce201`](https://github.com/OpenAdaptAI/openadapt-telemetry/commit/6dce201e2f1cd2be05606ef1fc71d22c1cead16c))

- Enforce privacy filter precedence for sentry init overrides
  ([`a8f2a57`](https://github.com/OpenAdaptAI/openadapt-telemetry/commit/a8f2a57e1f0287154d98c1cd4c2d7cd00d55e4ac))

- Guard non-dict telemetry config payloads
  ([`8e9a3e1`](https://github.com/OpenAdaptAI/openadapt-telemetry/commit/8e9a3e10d3d9eca92dfbfaef8570c66226e5f0cf))

- Guard request shape and enforce tag cap semantics
  ([`5620452`](https://github.com/OpenAdaptAI/openadapt-telemetry/commit/5620452cfc56336042b3c74d3dc4e52cf2ae0318))

- Harden anon id validation and preserve safe custom tags
  ([`a8c752d`](https://github.com/OpenAdaptAI/openadapt-telemetry/commit/a8c752dba04ff3dc550d7998d990d47f2e9bb785))

- Scrub request header variants and dedupe salt warnings
  ([`2c0b007`](https://github.com/OpenAdaptAI/openadapt-telemetry/commit/2c0b0072882227184ed12108da102e70f074f94f))

- **ci**: Correct semantic-release version targets
  ([`c51d7c0`](https://github.com/OpenAdaptAI/openadapt-telemetry/commit/c51d7c0c5a1d502b8f910d78273963812b3bf759))

### Chores

- Fix existing ruff violations in decorators
  ([`216f6d0`](https://github.com/OpenAdaptAI/openadapt-telemetry/commit/216f6d09337149b2aeec5c50b1e29ff4a940c05c))

### Code Style

- Clear legacy ruff violations
  ([`70afe50`](https://github.com/OpenAdaptAI/openadapt-telemetry/commit/70afe507194d8f0dacd30a77b7145ae090c7a317))

### Continuous Integration

- Scope telemetry tests to PostHog additions
  ([`22663de`](https://github.com/OpenAdaptAI/openadapt-telemetry/commit/22663de436cd4284323d2eaba0ca52c8f8ba99f9))

### Features

- Add PostHog usage events and release automation
  ([`7a204a4`](https://github.com/OpenAdaptAI/openadapt-telemetry/commit/7a204a4a3c264ff1d3d8e448e8cf115fd4ac622f))

- Harden telemetry privacy filters and anon ID policy
  ([`2d9dfa6`](https://github.com/OpenAdaptAI/openadapt-telemetry/commit/2d9dfa64253219a640f100a28111879f281fd31a))

- Make telemetry opt-out and enforce anonymized user IDs
  ([`278e091`](https://github.com/OpenAdaptAI/openadapt-telemetry/commit/278e091b480190b4201e5faed3bca13f6faf11cd))
