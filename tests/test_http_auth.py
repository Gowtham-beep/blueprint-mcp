"""End-to-end: start the real HTTP server and attack it with raw requests."""
import asyncio
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from blueprint_mcp.auth import hash_token, new_token
from blueprint_mcp.server import DATABASE_URL

ROOT = Path(__file__).resolve().parent.parent


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def db(sql: str, **params):
    """Run committed SQL (the server is another process, so rollback tricks can't be used)."""

    async def run():
        engine = create_async_engine(DATABASE_URL)
        try:
            async with engine.begin() as conn:
                result = await conn.execute(text(sql), params)
                return result.all() if result.returns_rows else None
        finally:
            await engine.dispose()

    return asyncio.run(run())


@pytest.fixture(scope="module")
def server_url():
    port = _free_port()
    # This variable must be IGNORED in http mode: identity may only come from a token.
    env = dict(os.environ, BLUEPRINT_USER_EMAIL="alice@acme.test")
    proc = subprocess.Popen(
        [sys.executable, "-W", "ignore", "-m", "blueprint_mcp.server",
         "--transport", "http", "--port", str(port)],
        cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}/mcp"
    for _ in range(100):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=1)
        except urllib.error.HTTPError:
            break  # got an HTTP answer, so it is up
        except OSError:
            time.sleep(0.2)
    yield url
    proc.terminate()
    proc.wait(timeout=10)


@pytest.fixture
def issue():
    """Create a real token for a user; remove it afterwards."""
    created = []

    def _issue(email: str, expires_sql: str = "NULL") -> str:
        token = new_token()
        db(
            f"""INSERT INTO api_tokens (tenant_id, user_id, token_hash, label, expires_at)
                SELECT tenant_id, id, :h, 'pytest', {expires_sql} FROM users WHERE email = :e""",
            h=hash_token(token), e=email,
        )
        created.append(hash_token(token))
        return token

    yield _issue
    for h in created:
        db("DELETE FROM api_tokens WHERE token_hash = :h", h=h)


def post(url, body, token=None, headers=None):
    h = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    h.update(headers or {})
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=h, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
    "protocolVersion": "2025-06-18", "capabilities": {},
    "clientInfo": {"name": "pytest", "version": "0"}}}


def call_metadata(url, token, doc_id, headers=None):
    """Returns ('http', status) if the transport refused, else ('revs', [...]) or ('error', msg)."""
    status, _ = post(url, INIT, token, headers)
    if status != 200:
        return "http", status
    status, body = post(url, {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
        "name": "get_document_metadata", "arguments": {"document_id": doc_id}}}, token, headers)
    if status != 200:
        return "http", status
    result = json.loads(body)["result"]
    if result["isError"]:
        return "error", result["content"][0]["text"]
    return "revs", [r["rev"] for r in result["structuredContent"]["revisions"]]


@pytest.fixture(scope="module")
def acme_doc():
    return str(db("""SELECT d.id FROM documents d JOIN tenants t ON t.id = d.tenant_id
                     WHERE t.name = 'Acme Steel' AND d.kind = 'drawing'""")[0][0])


# ---- the transport rejects before any tool code runs ----

def test_no_token_is_401(server_url, acme_doc):
    assert call_metadata(server_url, None, acme_doc) == ("http", 401)


def test_garbage_token_is_401(server_url, acme_doc):
    assert call_metadata(server_url, "bpk_not_a_real_token", acme_doc) == ("http", 401)


def test_leaked_hash_cannot_be_used_as_a_token(server_url, issue, acme_doc):
    token = issue("alice@acme.test")
    stored_hash = hash_token(token)  # what a database leak would reveal
    assert call_metadata(server_url, stored_hash, acme_doc) == ("http", 401)


def test_env_identity_is_ignored_over_http(server_url, acme_doc):
    # the server was started with BLUEPRINT_USER_EMAIL=alice; no token still means 401
    assert call_metadata(server_url, None, acme_doc) == ("http", 401)


def test_token_is_never_stored_in_plaintext(issue):
    token = issue("alice@acme.test")
    rows = db("SELECT count(*) FROM api_tokens WHERE api_tokens::text LIKE :p", p=f"%{token}%")
    assert rows[0][0] == 0


def test_revoked_token_is_401(server_url, issue, acme_doc):
    token = issue("alice@acme.test")
    assert call_metadata(server_url, token, acme_doc)[0] == "revs"
    db("UPDATE api_tokens SET revoked_at = now() WHERE token_hash = :h", h=hash_token(token))
    assert call_metadata(server_url, token, acme_doc) == ("http", 401)


def test_expired_token_is_401(server_url, issue, acme_doc):
    token = issue("alice@acme.test", expires_sql="now() - interval '1 second'")
    assert call_metadata(server_url, token, acme_doc) == ("http", 401)


# ---- the token picks the identity; the database picks the permissions ----

def test_engineer_viewer_and_foreign_tenant(server_url, issue, acme_doc):
    assert call_metadata(server_url, issue("alice@acme.test"), acme_doc) == ("revs", ["C", "B", "A"])
    assert call_metadata(server_url, issue("vik@acme.test"), acme_doc) == ("revs", ["B"])
    kind, message = call_metadata(server_url, issue("bob@birla.test"), acme_doc)
    assert kind == "error" and "not found" in message


def test_demotion_applies_to_the_same_token(server_url, issue, acme_doc):
    token = issue("alice@acme.test")
    assert call_metadata(server_url, token, acme_doc) == ("revs", ["C", "B", "A"])
    db("UPDATE users SET role = 'viewer' WHERE email = 'alice@acme.test'")
    try:
        assert call_metadata(server_url, token, acme_doc) == ("revs", ["B"])
    finally:
        db("UPDATE users SET role = 'engineer' WHERE email = 'alice@acme.test'")


# ---- browser-style attacks on a local server ----

def test_foreign_origin_is_rejected(server_url, issue, acme_doc):
    token = issue("alice@acme.test")
    assert call_metadata(server_url, token, acme_doc, {"Origin": "http://evil.example"}) == ("http", 403)


def test_foreign_host_header_is_rejected(server_url, issue, acme_doc):
    token = issue("alice@acme.test")
    assert call_metadata(server_url, token, acme_doc, {"Host": "evil.example"}) == ("http", 421)