
import json
import subprocess
import sys
import threading
import time
import re
import random
import argparse

write_lock = threading.Lock()  # stops two threads writing at the same time

# LATENCY_TOOL = "calculator"
# LATENCY_MS = 1400

# ERROR_TOOL = "none"
# ERROR_CODE = -32603
# ERROR_MESSAGE = "injected server error"

# WRONG_TOOL = "get_revenue"
# WRONG_FACTOR = 1.1

pending = {}

def perturb_first_number(text, factor):
    return re.sub(r"\d+\.\d+",
                  lambda m: f"{float(m.group())*factor:.1f}",
                  text, count=1)
    
def pick_fault(rules, rng, tool):
    chosen = None
    for rule in rules:
        roll = rng.random()                   
        matches = rule["tool"] in ("*", tool)   
        if chosen is None and matches and roll < rule["probability"]:
            chosen = rule                   
    return chosen

def send(stream, msg):
    with write_lock:
        stream.write(json.dumps(msg) + "\n")
        stream.flush()


def log(direction, msg):
    what = msg.get("method") or ("error" if "error" in msg else "result")
    print(f"[proxy] {direction} id={msg.get('id')} {what}", file=sys.stderr)


def client_to_server(server_in, rules, rng):
    for line in sys.stdin:
        msg = json.loads(line)
        log("client -> server", msg)
        
        if msg.get("method")=="tools/call":
            tool = msg["params"]["name"]
            rule = pick_fault(rules,rng,tool)
            
            if rule is None:
                pass
            elif rule["fault"] == "latency":
                ms= rule.get("delay_ms", 1400)
                print(f"[proxy] fault latency: delaying {tool} by {ms} ms", file=sys.stderr)
                time.sleep(ms/1000)
                
            elif rule["fault"] == "error":
                print(f"[proxy] fault error: answering {tool} with an error", file=sys.stderr)
                reply = {
                    "jsonrpc" : "2.0",
                    "id" : msg['id'],
                    "error": {"code": rule.get("code", -32603), "message": rule.get("message", "Injected server error")},
                }
                log("proxy -> client", reply )
                send(sys.stdout, reply)
                continue
            
            elif rule["fault"] == "wrong_result":
                pending[msg["id"]] = rule
                
        send(server_in, msg)
    server_in.close()  


def server_to_client(server_out):
    for line in server_out:
        msg = json.loads(line)
        log("server -> client", msg)
        
        if msg.get("id") in pending and "result" in msg:
            rule = pending.pop(msg["id"])
            factor = rule.get("factor", 1.1)
            
            for item in msg["result"].get("content", []):
                if item.get("type")=="text":
                    old= item["text"]
                    item["text"] = perturb_first_number(old, factor)
                    print(f"[proxy] fault wrong_result: {old!r}->{item['text']!r}", file=sys.stderr)
                    
            sc=msg["result"].get("structuredContent")
            if isinstance(sc, dict) and isinstance(sc.get("result"),str):
                sc["result"]=perturb_first_number(sc["result"], factor)
                
        send(sys.stdout, msg)


def main():
    parser = argparse.ArgumentParser(description="Fault-injecting MCP proxy")
    parser.add_argument("--config", required=True, help="path to the JSON config file")
    parser.add_argument("server_cmd", nargs=argparse.REMAINDER,
                        help="command that starts the real server, after --")
    args = parser.parse_args()
    cmd = [c for c in args.server_cmd if c != "--"]
    
    with open(args.config) as f:
        config = json.load(f)
    rules = config["rules"]
    rng = random.Random(config.get("seed", 0))

    server = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                              text=True, bufsize=1)
    # One thread copies server -> client, while the main code copies client -> server.
    t = threading.Thread(target=server_to_client, args=(server.stdout,), daemon=True)
    t.start()
    client_to_server(server.stdin, rules, rng)
    server.wait()
    t.join(timeout=1)


if __name__ == "__main__":
    main()