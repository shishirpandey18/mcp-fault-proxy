
import json
import subprocess
import sys
import threading
import time
import re

write_lock = threading.Lock()  # stops two threads writing at the same time

LATENCY_TOOL = "calculator"
LATENCY_MS = 1400

ERROR_TOOL = "none"
ERROR_CODE = -32603
ERROR_MESSAGE = "injected server error"

WRONG_TOOL = "get_revenue"
WRONG_FACTOR = 1.1

pending = {}

def perturb_first_number(text, factor):
    return re.sub(r"\d+\.\d+",
                  lambda m: f"{float(m.group())*factor:.1f}",
                  text, count=1)

def send(stream, msg):
    with write_lock:
        stream.write(json.dumps(msg) + "\n")
        stream.flush()


def log(direction, msg):
    what = msg.get("method") or ("error" if "error" in msg else "result")
    print(f"[proxy] {direction} id={msg.get('id')} {what}", file=sys.stderr)


def client_to_server(server_in):
    for line in sys.stdin:
        msg = json.loads(line)
        log("client -> server", msg)
        
        if msg.get("method")=="tools/call":
            tool = msg["params"]["name"]
            if tool == LATENCY_TOOL:
                print(f"[proxy] fault latency: delaying {tool} by {LATENCY_MS} ms", file=sys.stderr)
                time.sleep(LATENCY_MS/1000)
            elif tool == ERROR_TOOL:
                print(f"[proxy] fault error: answering {tool} with an error", file=sys.stderr)
                reply = {
                    "jsonrpc" : "2.0",
                    "id" : msg['id'],
                    "error": {"code": ERROR_CODE, "message": ERROR_MESSAGE},
                }
                log("proxy -> client", reply )
                send(sys.stdout, reply)
                continue
            elif tool == WRONG_TOOL:
                pending[msg["id"]] = tool
                
        send(server_in, msg)
    server_in.close()  


def server_to_client(server_out):
    for line in server_out:
        msg = json.loads(line)
        log("server -> client", msg)
        
        if msg.get("id") in pending and "result" in msg:
            tool = pending.pop(msg["id"])
            
            for item in msg["result"].get("content", []):
                if item.get("type")=="text":
                    old= item["text"]
                    item["text"] = perturb_first_number(old, WRONG_FACTOR)
                    print(f"[proxy] fault wrong_result: {tool}: {old!r}->{item['text']!r}", file=sys.stderr)
                    
            sc=msg["result"].get("structuredContent")
            if isinstance(sc, dict) and isinstance(sc.get("result"),str):
                sc["result"]=perturb_first_number(sc["result"],WRONG_FACTOR)
                
        send(sys.stdout, msg)


def main():
    cmd = [c for c in sys.argv[1:] if c != "--"]

    server = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                              text=True, bufsize=1)
    # One thread copies server -> client, while the main code copies client -> server.
    t = threading.Thread(target=server_to_client, args=(server.stdout,), daemon=True)
    t.start()
    client_to_server(server.stdin)
    server.wait()
    t.join(timeout=1)


if __name__ == "__main__":
    main()