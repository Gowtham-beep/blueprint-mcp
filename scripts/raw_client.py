import json
import subprocess
import sys

proc = subprocess.Popen(
    [sys.executable,"-m","blueprint_mcp.server"],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    text=True,
    bufsize=1,
)

def send(msg:dict)->None:
    print(">>>Client:", json.dumps(msg))
    proc.stdin.write(json.dumps(msg) + "\n")
    proc.stdin.flush()


def recv()->dict:
    line= proc.stdout.readline()
    print("<<<Server:",line.strip())
    return json.loads(line)
    

# Request: client proposes a protocol version and declares its capabilities
send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
    "protocolVersion": "2025-06-18",
    "capabilities": {},
    "clientInfo": {"name": "raw-client", "version": "0.0.1"},
}})
recv()

# Notification: no id, so the server sends nothing back
send({"jsonrpc": "2.0", "method": "notifications/initialized"})

# Request: discovery
send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
recv()

# Request: invocation
send({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
    "name": "ping", "arguments": {"message": "hello"}}})
recv()

proc.stdin.close()
proc.wait(timeout=5)