# Security Policy

## Supported versions

Security fixes land in the latest release on PyPI. Older versions are not
patched; upgrade with `pip install -U evalcraft`.

## Reporting a vulnerability

Please report vulnerabilities privately through GitHub's
[private vulnerability reporting](https://github.com/beyhangl/evalcraft/security/advisories/new)
rather than a public issue. If that page is unavailable, open an issue that
only says you have a security report to share, without any details, and a
private channel will be arranged. Include the evalcraft version, what you did,
and what happened. You should get a first response within a week.

## What to keep in mind

- **Cassettes can contain secrets and personal data.** They record what your
  agent sent and received. Review a cassette before committing it, and use
  `evalcraft sanitize` (or `CaptureContext(redact=True)`) to redact known
  secret and PII patterns. Redaction is pattern-based and not a guarantee.
- **Replay never calls a model**, but the live scorers (LLM-as-judge, RAG,
  pairwise) and `live-eval` do, and they send cassette content to the model
  provider you configure.
