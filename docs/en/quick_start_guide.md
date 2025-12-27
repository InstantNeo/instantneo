# InstantNeo Quick Start Guide

## Installation

```bash
pip install instantneo
```

## Creating a Simple Agent

Let's start by creating a basic agent without any skills:

```python
from instantneo import InstantNeo

# Create a simple agent with Anthropic's Claude
agent = InstantNeo(
    provider="anthropic",  # Options: "openai", "anthropic", "groq"
    api_key="your_api_key_here",
    model="claude-3-sonnet-20240229",
    role_setup="You are a helpful assistant focused on answering questions clearly and concisely.",
    temperature=0.7,
    max_tokens=500
)

# Use the agent for a basic conversation
response = agent.run(
    prompt="What is the capital of France?"
)

print(response)
```

## Creating a Simple Skill

Skills enable your agent to perform specific functions. Let's create a basic skill:

```python
from instantneo.skills import skill

@skill(
    description="Add two numbers and return the result",
    parameters={
        "a": "First number to add",
        "b": "Second number to add"
    },
    tags=["math", "arithmetic"]
)
def add(a: int, b: int) -> int:
    return a + b
```

Notice that:

- The `@skill` decorator adds metadata to the function
- Type information comes from Python type hints (`: int`)
- Parameter descriptions come from the `parameters` dictionary in the decorator
- Docstrings are optional - the metadata in the decorator is sufficient

## Adding Skills to Your Agent

Now let's add the skill to our agent:

```python
# Register the skill with the agent
agent.register_skill(add)

# Verify available skills
print(f"Available skills: {agent.get_skill_names()}")

# Use the agent with the new skill
response = agent.run(
    prompt="I need to add 42 and 28, what's the result?"
)

print(response)
```

## Creating Multiple Skills

Let's create a few more skills:

```python
@skill(
    description="Check if a text contains a keyword",
    parameters={
        "text": "The text to search in",
        "keyword": "The keyword to look for"
    },
    tags=["text", "search"]
)
def find_keyword(text: str, keyword: str) -> bool:
    return keyword.lower() in text.lower()

@skill(
    description="Calculate the length of a text string",
    parameters={
        "text": "The input text"
    },
    tags=["text", "utility"]
)
def text_length(text: str) -> int:
    return len(text)

# Register the new skills
agent.register_skill(find_keyword)
agent.register_skill(text_length)
```

## Controlling Which Skills Are Used

You can control which skills are available for each run:

```python
# Use only specific skills for a particular query
response = agent.run(
    prompt="How many characters are in the word 'Python'?",
    skills=["text_length"]  # Only use the text_length skill for this query
)

print(response)

# Use multiple specific skills
response = agent.run(
    prompt="Is the word 'language' in this text: 'Python is a programming language'?",
    skills=["find_keyword", "text_length"]  # Use these two skills
)
```

## Execution Modes

InstantNeo supports three execution modes:

```python
# Wait for skill execution and return results (default)
response = agent.run(
    prompt="Add 5 and 7",
    execution_mode="wait_response"
)

# Execute skills without waiting for results
agent.run(
    prompt="Process this data in the background",
    execution_mode="execution_only"
)

# Just get the arguments without executing the skills
args = agent.run(
    prompt="Add 10 and 20",
    execution_mode="get_args"
)
print(args)  # Will show the skill name and arguments
```

## Using SkillManager

For more organized skill management, use SkillManager:

```python
from instantneo.skills import SkillManager

# Create specialized skill managers
math_skills = SkillManager()
text_skills = SkillManager()

# Register skills in appropriate managers
math_skills.register_skill(add)
text_skills.register_skill(find_keyword)
text_skills.register_skill(text_length)

# Create agent with specific skills
agent = InstantNeo(
    provider="openai",
    api_key="your_api_key",
    model="gpt-4",
    role_setup="You are a helpful assistant.",
    skills=math_skills  # Initialize with math skills only
)

# Later, combine skills from different managers
agent.sm_ops_union(text_skills)

# Compare skill sets
comparison = agent.sm_ops_compare(math_skills)
print(comparison)  # Shows common and unique skills
```

## Loading Skills Dynamically

Load skills from files or folders:

```python
# Load from a specific file
agent.load_skills_from_file("./my_skills.py")

# Load from an entire folder
agent.load_skills_from_folder("./skills_library")

# Load with filtering
agent.skill_manager.load_skills.from_folder(
    "./skills_library", 
    by_tags=["math"]  # Only load skills with this tag
)
```

## Streaming Responses

Get responses in real-time:

```python
for chunk in agent.run(
    prompt="Explain the concept of AI agents",
    stream=True
):
    print(chunk, end="", flush=True)
```

## Working with Images (Multimodal)

```python
agent = InstantNeo(
    provider="openai",
    api_key="your_api_key",
    model="gpt-4-vision-preview",
    role_setup="You are a vision-capable assistant.",
    images=["./default_image.jpg"]  # Default image
)

response = agent.run(
    prompt="What can you see in this image?",
    images=["./specific_image.jpg"]  # Override for this run
)
```

## Asynchronous Execution

Execute skills in the background:

```python
response = agent.run(
    prompt="Process this large dataset",
    async_execution=True,
    execution_mode="wait_response"
)
```

For more detailed information, check out the full documentation and examples in the docs folder of this repository.
