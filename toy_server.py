from mcp.server.mcpserver import MCPServer

server = MCPServer("toy-server")

# Fake "annual report" data, so there is no need of internet.
REVENUE = {
    "esewaa": "Esewaa FY2025 revenue: EUR 546.6 million (FY2024: EUR 432.0 million).",
    "nepeu": "NepEU FY2025 revenue: EUR 95.4 million (FY2024: EUR 89.7 million).",
}


@server.tool()
def calculator(expression: str) -> str:
    """Evaluate a simple arithmetic expression, e.g. '(412.6-371.0)/371.0'."""
    allowed = set("0123456789.+-*/() ")
    if not set(expression) <= allowed:
        raise ValueError("only numbers and + - * / ( ) are allowed")
    return str(round(eval(expression), 6))


@server.tool()
def get_revenue(company: str) -> str:
    """Return the revenue line from a company's annual report."""
    return REVENUE.get(company.lower(), f"No report found for {company}.")


if __name__ == "__main__":
    server.run()  # default transport is stdio
