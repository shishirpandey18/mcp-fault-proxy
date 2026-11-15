# mcp-fault-proxy

I built a minimal fault-injecting proxy for MCP (Model Context Protocol) servers that use the stdio transport.
Written for the CHAOS-MAS doctoral researcher assignment (Part 2, Option A).

```
MCP client  <-->  proxy.py  <-->  MCP server
               (injects faults)
```

The client starts the proxy instead of the server. The proxy starts the real server as a subprocess and copies JSON-RPC messages in both directions, one message per line. Only tools/call requests can receive faults. Everything else (initialize, tools/list, notifications) is forwarded as it is.

## How to run

Requires Python 3.10 or newer and the official MCP Python SDK, version 2.x. Tested on macOS with Python 3.14.4 and mcp 2.3.0.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install mcp

python3 demo_client.py --no-proxy   # no proxy: correct results (baseline)
python3 demo_client.py            # through the proxy: faults injected
```


## Files

| File | Purpose |
|---|---|
| `proxy.py` | The fault-injecting proxy. |
| `config.json` | Which faults to inject, on which tool, how often, and the random seed. |
| `toy_server.py` | A toy MCP server built with the official SDK. Tools: `calculator` and `get_revenue` (invented companies and figures). |
| `demo_client.py` | An MCP client that makes 8 fixed tool calls and prints status, latency and result for each. |
| `demo_run.txt` | Output of a demo run through the proxy. |
| `faults.log` | The fault log written by the proxy during demo run. |

## Fault types

| Fault | What the proxy does | What the client sees |
|---|---|---|
| `latency` | Holds the request for `delay_ms`, then forwards it. | A correct answer that arrives late. |
| `error` | Replies itself with a JSON-RPC error (same `id` as the request). The server never sees the call. | A failed call. |
| `wrong_result` | Forwards the call, then multiplies the **first** decimal number in the reply by `factor`. | A call that looks successful, with a believable but wrong number. |

At most one fault is injected per call.

## Configuration

```json
{
  "seed": 42,
  "log_file": "faults.log",
  "rules": [
    {"tool": "calculator",  "fault": "latency",      "probability": 0.5, "delay_ms": 1400},
    {"tool": "calculator",  "fault": "error",        "probability": 0.4, "code": -32603, "message": "Calculator service crashed"},
    {"tool": "get_revenue", "fault": "error",        "probability": 0.2, "code": -32001, "message": "Request timed out"},
    {"tool": "get_revenue", "fault": "wrong_result", "probability": 0.5, "factor": 1.1}
  ]
}
```

- `tool` is a tool name, or `*` for every tool.
- `probability` (0 to 1) is the chance that the rule fires **when it is reached**.
- Rules are checked in order and the **first rule that fires wins**. A later rule for the same tool therefore fires less often than its own number suggests.
- Optional settings have defaults: `delay_ms` 1400, `code` -32603, `message` "Injected server error", `factor` 1.1.

Real chance per call with this config:

| Tool | latency | error | wrong_result | no fault |
|---|---|---|---|---|
| `calculator` | 50% | 50% × 40% = 20% | – | 30% |
| `get_revenue` | – | 20% | 80% × 50% = 40% | 40% |

## Demo run

With seed 42, the 8 demo calls get these faults (full output in `demo_run.txt` and `faults.log`):

| Call | Tool | Fault | Result seen by the client |
|---|---|---|---|
| 1 | get_revenue | wrong_result | `ok`, Esewaa revenue 601.3 instead of 546.6 |
| 2 | get_revenue | wrong_result | `ok`, NepEU revenue 104.9 instead of 95.4 |
| 3 | calculator | latency | `ok`, correct result, about 1412 ms |
| 4 | calculator | latency | `ok`, correct result, about 1409 ms |
| 5 | get_revenue | wrong_result | `ok`, 601.3 instead of 546.6 |
| 6 | calculator | none | `ok`, 42 |
| 7 | calculator | error | `ERROR(rpc)`, "Calculator service crashed" |
| 8 | get_revenue | none | `ok`, correct 95.4 |

Calls 1 and 5 are identical and both got a wrong result, while call 8 (identical to call 2) got the correct one. The `get_revenue` error rule did not fire in this short run.

## Fault log

Every injected fault is written as one JSON object per line (JSON Lines) to log file, and also printed to stderr:

```json
{"time": "01:18:23", "call_number": 1, "request_id": 3, "tool": "get_revenue", "fault": "wrong_result", "detail": "numbers x1.1: 'Esewaa FY2025 revenue: EUR 546.6 million (FY2024: EUR 432.0 million).' -> 'Esewaa FY2025 revenue: EUR 601.3 million (FY2024: EUR 432.0 million).'"}

```

`call_number` counts tool calls (1 to 8 in the demo); `request_id` is the JSON-RPC id. For `wrong_result`, `detail` contains the text before and after the change. The file is opened in append mode, so several runs add up. Delete it for a clean log.

## Design choices

- **Works at JSON-RPC level:** Proxy does not use any SDK and does not require any understanding of internal functioning of the MCP server. It reads JSON messages line by line, optionally changes them and forwards them.  This allows it to be used with any stdio based MCP server, no matter what programming language it is written in.
- **Reproducible results:** All random decisions are carried out with `random.Random(seed)`, which means the same seed and configuration will yield the same results. On each tool call the proxy draws one random number per rule, even for rules that target a different tool. So the random numbers for call N are always the same, whichever tools were called before it. Changing the rules changes the sequence, though.  I've tried this by executing the demo multiple times and looking at the logs from them. The outcome was the same, with the exception of timestamps. I also confirmed that the same configuration gives the same faults on two different machines.
- **Wrong results affect only the first number:** I tried scaling every number by the same factor. This caused a problem because even though the revenue values for FY2025 and FY2024 were both incorrect, their growth rate remained the same which made the fault difficult to notice. Now, only the first number (FY2025 revenue) is changed, which also affects the calculated growth rate. For example, a client computing Esewaa's growth rate would get 39.2% instead of 26.5%.
- **Both result formats are updated:** There are two locations where the SDK returns tool results: content (text displayed to the client) and structuredContent (structured data provided to the programs). Both are updated by proxy, so as a result they always have consistent results.
- **Uses two threads and a lock:** The proxy uses two threads where one forwards messages from the client to the server and other forwards messages from the server back to the client. A lock prevents both threads from writing to stdout or the log file at the same time.
- **Logs are written to stderr:** All logs go to stderr, never to stdout. This is important because stdout is reserved for communication between the proxy and the client. Writing anything else there could break the JSON-RPC connection.

## Known limitations

- **Only supports stdio:** the current proxy that I built works only with stdio-based MCP servers. HTTP based transports such as streamable HTTP and SSE are not supported.
- **Reproducibility depends on the calls being the same:** The demo client always makes the same tool calls, which makes it easy to reproduce the same faults. A real LLM agent, though, might select other tools or order the calls differently every time. In that case, even with the same seed, the faults may affect different calls.
- **Delays can block other requests:** If one request is delayed, other requests sent at the same time have to wait too. This is not an issue for the demo, since the demo client makes tool calls one after another, but it could matter when handling multiple requests in parallel.
- **Limited testing so far:** The proxy has only been tested with the example server and demo client. Automated tests have not been added yet.


