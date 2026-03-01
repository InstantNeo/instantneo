# InstantNeo

<div align="center">

![InstantNeo Logo](https://raw.githubusercontent.com/dponcedeleonf/instantneo/refs/heads/desarrollo/docs/img/logo_instantneo.png)

[![PyPI version](https://img.shields.io/pypi/v/instantneo.svg)](https://pypi.org/project/instantneo/)
[![Python Versions](https://img.shields.io/pypi/pyversions/instantneo.svg)](https://pypi.org/project/instantneo/)
[![License](https://img.shields.io/github/license/dponcedeleonf/instantneo.svg)](https://github.com/dponcedeleonf/instantneo/blob/main/LICENSE)

<div align="center">

  <h2><b>Build instant agents to compose intelligent systems</b></h2>
  <p><i>"I know kung fu." - Neo</i></p>
</div>
</div>

## What is InstantNeo?

InstantNeo is a Python library that lets you create LLM-based agents quickly and concisely, designed as components for intelligent systems. It offers a clean, direct interface for granular control over agent behavior, abstracting away provider complexity. Like Neo in *The Matrix* downloading skills instantly, InstantNeo lets you build agents with instant capabilities, simple to start and powerful when composed. Unlike rigid or overly-elaborated frameworks, InstantNeo draws from Marvin Minsky's 'Society of Mind' to deliver modular building blocks, letting you craft multi-agent systems your way.

## Features

- **Unified Provider Interface:** Switch seamlessly between models providers with consistent syntax. The library handles different API requirements behind the scenes.
- **Quick and powerful Tool Management:** Define agent capabilities using simple Python decorators that transform functions into tools with metadata, descriptions, and parameter validation. Add, remove, and list tools dynamically as your agent's needs evolve.
- **Flexible Execution Modes:** Control exactly how tools are executed with three modes: wait for results, fire tools in the background, or just extract arguments without execution for planning purposes.
- **Text and Image Support:** Process both text and images through a single consistent API. Send images alongside prompts to vision-capable models and control the level of image analysis detail as needed.
- **Customizable Agent Settings:** Modify agent behavior on-the-fly by overriding temperature, max tokens, role setup, and other parameters for specific interactions without recreating the entire agent.

## Installation

```bash
pip install instantneo
```

That's it. Works with OpenAI, Anthropic, Groq, Gemini, and Vertex AI out of the box.

## Quickstart

### Wake Neo Up

```python
from instantneo import InstantNeo

neo = InstantNeo(
    provider="openai",
    api_key="your-api-key",
    model="gpt-4o",
    role_setup="You are Neo, the chosen one. Ready to learn anything."
)

print(neo.run("What's the Matrix?"))
```

### Teach Him Kung Fu

```python
from instantneo import InstantNeo, tool

@tool(description="Execute a kung fu move", parameters={"move": "e.g., dragon punch", "intensity": "1-10"})
def kung_fu(move: str, intensity: int = 5) -> str:
    return f"Hit {move} at intensity {intensity}. I know kung fu!"

neo = InstantNeo(
    provider="anthropic",
    api_key="your-api-key",
    model="claude-3-7-sonnet-20250219",
    role_setup="You are Neo, martial arts downloaded.",
    skills=[kung_fu]
)

print(neo.run("Three agents ahead. What move?"))
```

### Use Vertex AI

```python
from instantneo import InstantNeo

neo = InstantNeo(
    provider="vertexai",
    model="gemini-2.5-flash",
    role_setup="You are Neo, the chosen one.",
    location="us-central1",
    service_account_file="path/to/service-account.json"
)

print(neo.run("I need an exit."))
```

## API Reference

- **InstantNeo Class**: Set provider, api_key, model, role_setup, plus tools and tuning params (temperature, max_tokens, etc.).
- **run() Method**: Feed it a prompt, pick an execution_mode (WAIT_RESPONSE, EXECUTION_ONLY, GET_ARGS), override settings as needed.

Details in the docs.

## Architecture and Philosophy

InstantNeo leans on Minsky's "Society of Mind": small, specialized agents you connect to make something bigger. Each agent's a tool—give it a role, add skills, and weave them together. The smarts come from your coordination, not ours.

## Documentation

Full scoop at /docs, including tutorials on multi-agent setups and advanced skills.

## Contributing

Fork, branch, commit, push, PR. Update tests and docs if you're adding something.

## License

MIT License—check LICENSE.

<div align="center">
  <p><i>"I'm trying to free your mind, Neo. But I can only show you the door. You're the one that has to walk through it." - Morpheus</i></p>
</div>
