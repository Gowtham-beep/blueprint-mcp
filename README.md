# Blueprint MCP

This is a small MCP server in Python I built as a learning project to understand how the Model Context Protocol works in practice. I used multi-tenant engineering documents—drawings and inspection reports—as the example domain to test boundaries between users and tenants.

## What I wanted to understand

- What actually happens on the wire when a client talks to an MCP server?
- When is something a tool, a resource or a prompt?
- How do you stop one company's data reaching another when the caller is an AI model?
- What changes when the same server moves from local stdio to HTTP?

## Run it

1. Start Postgres:
```bash
docker compose up -d
```

2. Apply schemas, seeds, and token tables in order:
```bash
docker compose exec -T db psql -U blueprint -d blueprint < db/001_schema.sql
docker compose exec -T db psql -U blueprint -d blueprint < db/002_seed.sql
docker compose exec -T db psql -U blueprint -d blueprint < db/003_api_tokens.sql
docker compose exec -T db psql -U blueprint -d blueprint < db/004_audit_log.sql
```

3. Generate sample PDF files for seeded revisions:
```bash
uv run python scripts/make_sample_files.py
```

4. Install dependencies:
```bash
uv sync
```

5. Create a token:
```bash
uv run python scripts/create_token.py alice@acme.test "alice-dev" 30
```

6. Start the HTTP server on port 8000:
```bash
uv run python -m blueprint_mcp.server --transport http --port 8000
```

7. Query `tools/list` with the token:
```bash
curl -s -X POST http://127.0.0.1:8000/mcp \
  -H "Content-Type: application/json" -H "Accept: application/json" \
  -H "Authorization: Bearer <TOKEN>" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}'
```
Returns `{"jsonrpc":"2.0","id":1,"result":{"tools":[...]}}`.

8. Query without the token:
```bash
curl -i -s -X POST http://127.0.0.1:8000/mcp \
  -H "Content-Type: application/json" -H "Accept: application/json" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}' | head -n 1
```
Returns `HTTP/1.1 401 Unauthorized`.

9. Run the test suite:
```bash
uv run pytest -q
```
Outputs `57 passed`.

## What's in it

- Tools: `search_documents` (by title), `get_document_metadata` (details and revisions), `get_latest_approved_drawings` (by project), `compare_revisions` (metadata diff), `check_document_access` (boolean check).
- Resource: `blueprint://documents/{document_id}/revisions/{rev}` (reads raw PDF bytes from disk).
- Prompts: `review_inspection_report` (structured review instructions), `compare_drawing_revisions` (revision comparison instructions).
- Transports: `--transport stdio` reads identity from `BLUEPRINT_USER_EMAIL` for local debugging; `--transport http` verifies Bearer tokens on every call.

## What I learned

- MCP is JSON-RPC: requests have ids, notifications don't; `initialize` -> `notifications/initialized` -> `tools/list` -> `tools/call`; the server proposes a protocol version and the client decides.
- Protocol errors (e.g. method not found) and tool errors (`isError: true`) are different things; the SDK hides crash details from the client.
- Tool vs resource vs prompt = model-controlled vs application-controlled vs user-controlled; a tool locates, a resource reads, a prompt carries instructions and ids, never content.
- Identity never comes from tool arguments; it comes from the verified token and the role is re-read from the database on every call, so demotion applies immediately.
- "Not found" for missing, cross-tenant and hidden documents, so a caller cannot tell them apart (tested).
- `tenant_id` on every table with composite foreign keys, so the database is the backstop if application code forgets a filter.
- HTTP is stateless, so the token goes on every request; tokens are stored as SHA-256 hashes (fine for 256-bit random tokens, not for passwords).
- Running a file with `python -m` makes it `__main__`, and a later import loads a second copy; that is why prompts use a `register(mcp)` function.
- Mutation checking: deleting a protection and confirming a test fails found tests that passed for the wrong reason; removing only the SQL expiry check is not caught because the SDK also enforces `AccessToken.expires_at` (two layers).
- An audit log is its own design problem: write it on its own connection, log fixed reasons and validated ids only, and remember unauthenticated requests can flood it.

## What it isn't

- No TLS (would sit behind a reverse proxy in production).
- No rate limiting.
- No structured logging, request IDs, or timings.
- No full MCP OAuth flow (uses pre-issued bearer tokens).
- No token rotation tooling.
- The audit table is append-only by convention only (the application DB user has full permissions).
- `search_documents` is deliberately not audited (all other tools and the revision resource call `audit.record`).

## Layout

```text
blueprint-mcp/
├── blueprint_mcp/  # Server, auth verifier, DB access, and audit logger
├── db/             # Schemas, seed data, token tables, audit log table
├── scripts/        # CLI scripts for token creation and sample files
├── storage/        # Local PDF files mapped by document revision
└── tests/          # HTTP auth, multi-tenant access, and storage tests
```
