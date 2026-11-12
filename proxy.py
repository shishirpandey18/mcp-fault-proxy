
import json
import subprocess
import sys
import threading
import time

write_lock = threading.Lock()  # stops two threads writing at the same time

LATENCY_TOOL = "calculator"
LATENCY_MS = 1400

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
                
        send(server_in, msg)
    server_in.close()  


def server_to_client(server_out):
    for line in server_out:
        msg = json.loads(line)
        log("server -> client", msg)
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