"""
Custom tools example — define your own MCP tools for the agent to use.

Uses `tool()` and `create_sdk_mcp_server()` to expose custom functions
to the agent. Requires `ClaudeSDKClient` for full lifecycle control.
"""

import anyio
from claude_agent_sdk import (
    tool,
    create_sdk_mcp_server,
    ClaudeSDKClient,
    ClaudeAgentOptions,
    AssistantMessage,
    TextBlock,
)


@tool("get_weather", "Get the current weather for a city", {"city": str})
async def get_weather(args):
    city = args["city"]
    # Stub — replace with a real API call
    weather_data = {
        "Paris": "18°C, partly cloudy",
        "London": "12°C, rainy",
        "Tokyo": "24°C, sunny",
        "New York": "20°C, clear skies",
    }
    forecast = weather_data.get(city, f"No data for {city}")
    return {"content": [{"type": "text", "text": f"Weather in {city}: {forecast}"}]}


@tool("get_population", "Get the population of a city", {"city": str})
async def get_population(args):
    city = args["city"]
    populations = {
        "Paris": "2.1 million",
        "London": "8.8 million",
        "Tokyo": "13.9 million",
        "New York": "8.3 million",
    }
    pop = populations.get(city, "unknown")
    return {"content": [{"type": "text", "text": f"Population of {city}: {pop}"}]}


server = create_sdk_mcp_server(
    "city-tools", tools=[get_weather, get_population]
)


async def main():
    print("=== Custom Tools Agent ===\n")

    options = ClaudeAgentOptions(
        mcp_servers={"city-tools": server},
    )

    async with ClaudeSDKClient(options=options) as client:
        await client.query(
            "Compare the weather and population of Paris and Tokyo."
        )
        async for message in client.receive_response():
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        print(block.text)


if __name__ == "__main__":
    anyio.run(main)
