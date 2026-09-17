# Security plan (draft)

- Keep API keys and permission emails outside Git.
- Redact secrets and personal data before logs or public artifacts.
- Treat startup briefs and extracted document text as untrusted content.
- Apply request-size, output-length, timeout, and concurrency limits.
- Test prompt-injection attempts in both source documents and user briefs.
- Never place private source text in error messages or telemetry by default.
- Keep model, adapter, prompt, and data revisions separately versioned.
- Provide an immediate fallback or rollback when a model release regresses.
