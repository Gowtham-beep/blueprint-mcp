import json
import subprocess
import sys

def session(init_version:str,calls:list)->None:
    p = subprocess.Popen(
        [sys.executable,"-m","blueprint_mcp.server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        bufsize=1,
    )

    def send(m:dict)->None:
        p.stdin.write(json.dumps(m) + "\n")
        p.stdin.flush()

    def recv()->str:
        return p.stdout.readline().strip()

    send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": init_version, "capabilities": {},
        "clientInfo": {"name": "x", "version": "0"}}})
    print("INIT", init_version, "->", recv())
    send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    for i,(lable,method,params) in enumerate(calls,start=2):
        send({"jsonrpc": "2.0", "id": i, "method": method, "params": params})
        print(lable,"->",recv())

    p.stdin.close()
    p.wait(timeout=5)

session("1999-01-01", [])
session("2025-06-18", [
    ("unknown tool", "tools/call", {"name": "nope", "arguments": {}}),
    ("wrong arg type", "tools/call", {"name": "ping", "arguments": {"message": 123}}),
    ("missing arg", "tools/call", {"name": "ping", "arguments": {}}),
    ("tool raises", "tools/call", {"name": "blast", "arguments": {}}),
    ("unknown method", "bogus/method", {}),
])