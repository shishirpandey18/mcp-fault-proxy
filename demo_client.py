
import asyncio
import sys
import time

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


#params = StdioServerParameters(command=sys.executable, args=["toy_server.py"])

if "--no-proxy" in sys.argv:
    params = StdioServerParameters(command=sys.executable, args=["toy_server.py"]) #self-start the server without going through proxy
else:
    #start the proxy and tell it how to start the server (after "--")
    params=StdioServerParameters(
        command=sys.executable,
        args=["proxy.py","--",sys.executable,"toy_server.py"],
    )

# The tool calls "agent" will make, in this order.
CALLS = [
    ("get_revenue", {"company": "esewaa"}),
    ("get_revenue", {"company": "nepeu"}),
    ("calculator", {"expression": "(546.6-432.0)/432.0"}),
    ("calculator", {"expression": "(95.4-89.7)/89.7"}),
    ("get_revenue", {"company": "esewaa"}),
    ("calculator", {"expression": "2*21"}),
    ("calculator", {"expression": "100/8"}),
    ("get_revenue", {"company": "nepeu"}),
]


async def main():
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize() 
            tools = await session.list_tools()
            print("tools:", [t.name for t in tools.tools])

            for i, (name, args) in enumerate(CALLS, 1):
                start = time.time()
                try:
                    result = await session.call_tool(name, args)
                    text = result.content[0].text
                    status = "ERROR(tool)" if result.is_error else "ok"
                except Exception as e:
                    text, status = str(e), "ERROR(rpc)"
                ms = int((time.time() - start) * 1000)
                print(f"{i}. {name}({args}) -> [{status}, {ms} ms] {text}")


asyncio.run(main())