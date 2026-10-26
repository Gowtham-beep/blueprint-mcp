from mcp.server import MCPServer

mcp = MCPServer("blueprint-mcp")

@mcp.tool()
def ping(message:str)->str:
    """Echo back the messaage."""
    return f"pong:{message}"

if __name__ == "__main__":
    mcp.run(transport="stdio")