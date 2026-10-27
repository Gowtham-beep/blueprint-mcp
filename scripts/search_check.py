import json
import os
import subprocess
import sys


def run(email, args):
    env = {k: v for k, v in os.environ.items() if k != "BLUEPRINT_USER_EMAIL"}
    if email:
        env["BLUEPRINT_USER_EMAIL"] = email
    p = subprocess.Popen(
        [sys.executable, "-m", "blueprint_mcp.server"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=None, text=True, bufsize=1, env=env,
    )

    def send(m):
        p.stdin.write(json.dumps(m) + "\n")
        p.stdin.flush()

    send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2025-06-18", "capabilities": {},
        "clientInfo": {"name": "x", "version": "0"}}})
    p.stdout.readline()
    send({"jsonrpc": "2.0", "method": "notifications/initialized"})
    send({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
          "params": {"name": "search_documents", "arguments": args}})
    out = json.loads(p.stdout.readline())
    p.stdin.close()
    p.wait(timeout=5)
    return out["result"]


CASES = [
    ("engineer", "alice@acme.test", {"query": "frame"}),
    ("viewer", "vik@acme.test", {"query": "frame"}),
    ("birla engineer", "bob@birla.test", {"query": "frame"}),
    ("no match", "alice@acme.test", {"query": "zzz"}),
    ("wildcard", "alice@acme.test", {"query": "%"}),
    ("no identity", None, {"query": "frame"}),
    ("sneaky tenant arg", "alice@acme.test", {"query": "frame", "tenant_id": "x"}),
]

for label, email, args in CASES:
    r = run(email, args)
    body = r.get("structuredContent") or r["content"][0]["text"]
    print(f"{label:18} isError={r['isError']}  {json.dumps(body)[:200]}")