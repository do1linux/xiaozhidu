# server.py
from mcp.server.fastmcp import FastMCP
import logging
logger = logging.getLogger('test_mcp')

import math
import random

# Create an MCP server
mcp = FastMCP("Calculator")

# Add an addition tool
@mcp.tool()
def calculator(python_expression: str) -> dict:
    """For mathematical calculation, always use this tool to calculate the result of a python expression. `math` and `random` are available."""
    try:
        # Safe evaluation with limited globals
        allowed_globals = {
            'math': math,
            'random': random,
            '__builtins__': {}
        }
        result = eval(python_expression, allowed_globals)
        logger.info(f"Calculating formula: {python_expression}, result: {result}")
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"Calculation error: {e}")
        return {"success": False, "error": str(e)}

# Start the server
if __name__ == "__main__":
    mcp.run(transport="stdio")
