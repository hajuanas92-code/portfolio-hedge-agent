"""
Step 1: Connect to alpaca-mcp-server as an MCP client 
and list every tool it exposes, with its exact name and description.
"""

import asyncio, os
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from dotenv import load_dotenv

load_dotenv()

ALPACA_MCP_SERVER_DIR = os.getenv("LOCAL_ALPACA_MCP_SERVER_DIR") 
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")
# --------------------------------

async def main():
    server_params = StdioServerParameters(
        command="uv",
        args=[
            "--directory", ALPACA_MCP_SERVER_DIR,
            "run", "alpaca-mcp-server",
        ],
        env={
            "ALPACA_API_KEY": ALPACA_API_KEY,
            "ALPACA_SECRET_KEY": ALPACA_SECRET_KEY,
        },
    )

    print("Connecting to alpaca-mcp-server...")
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("Connected. Fetching tool list...\n")

            result = await session.list_tools()

            print(f"Found {len(result.tools)} tools:\n")
            for tool in result.tools:
                print(f"- {tool.name}")
                if tool.description:
                    # Print only the first line of description to keep output readable
                    first_line = tool.description.strip().split("\n")[0]
                    print(f"    {first_line}")

            print("\nDone. Copy the exact tool names you need (e.g. positions, account, options) for the next script.")


if __name__ == "__main__":
    asyncio.run(main())