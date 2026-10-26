from mcp.server import MCPServer

mcp = MCPServer("blueprint-mcp")

@mcp.tool()
def ping(message:str)->str:
    """Echo back the message."""
    return f"pong:{message}"


@mcp.tool()
def blast():
    """Always fails"""
    raise ValueError("DB connection failed")

if __name__ == "__main__":
    mcp.run(transport="stdio")