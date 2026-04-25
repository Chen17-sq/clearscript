# Security Policy

## Reporting a vulnerability

If you discover a security or privacy vulnerability, please **do not open a public issue**. Instead:

1. Open a GitHub Security Advisory on the repository, **or**
2. Email the maintainer directly (see GitHub profile)

We will acknowledge receipt within 7 days and aim to provide an initial assessment within 14 days.

## Privacy commitments

clearscript is **local-first by architecture**, not just by claim:

- No telemetry of any kind ships with the project
- No data leaves your machine except calls to the LLM provider you explicitly configured
- API keys are read from environment variables, config files, or your OS keyring — never logged
- Project files (transcripts, library, change logs) live entirely on your local disk
- The local web UI binds to `127.0.0.1` only by default

If you find any code path that violates the above, please report it as a security issue.

## Scope

In-scope vulnerabilities include:

- Code paths that send user data to unintended destinations
- Logging of API keys or sensitive content
- Insecure default configurations
- Path traversal, injection, or similar issues in the local web UI or CLI

Out of scope:

- Vulnerabilities in upstream LLM providers
- Issues in dependencies (please report to the upstream project; we'll bump our pin once fixed)
