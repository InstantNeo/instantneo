# InstantNeo Core Reference

## Core Concepts

InstantNeo provides a unified interface for creating AI agents that can interact with various Large Language Model (LLM) providers. The library is designed around a few key concepts:

### Agent Architecture

An InstantNeo agent consists of:

1. **Base Configuration**: Defined when you create an instance, including the LLM provider, model, system prompt, and default parameters.
2. **Skills Registry**: Functions that the agent can call to perform specific tasks.
3. **Execution Engine**: Handles communication with the LLM and executes skills as needed.

### Instance and Run Relationship

The key to understanding InstantNeo is the relationship between **Instance creation** and **Run method execution**

Think of the instance as defining an agent's identity and general capabilities, while each `run()` call represents a specific task or query with optional specialized configurations.

## Creating an InstantNeo Instance

### Constructor

```python
InstantNeo(
    provider: str,
    api_key: str,
    model: str,
    role_setup: str,
    skills: Optional[Union[List[str], SkillManager]] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = 200,
    presence_penalty: Optional[float] = None,
    frequency_penalty: Optional[float] = None,
    stop: Optional[Union[str, List[str]]] = None,
    logit_bias: Optional[Dict[int, float]] = None,
    seed: Optional[int] = None,
    stream: bool = False,
    images: Optional[Union[str, List[str]]] = None,
    image_detail: str = "auto"
)
```

### Key Parameters

- **provider**: Selects the LLM provider. Options: "openai", "anthropic", "groq"
- **api_key**: Your API key for the selected provider
- **model**: The specific model to use (e.g., "gpt-4o", "claude-3-opus-20240229")
- **role_setup**: The system prompt that defines your agent's personality and instructions
- **skills**: Optional skills to make available to the agent from the start
- **temperature**: Controls randomness in responses (higher = more creative, lower = more deterministic)
- **max_tokens**: Maximum length of the response
- **images**: Default images to include with prompts (for multimodal models)

Creating an InstantNeo instance gives you several advantages:

1. **Agent Reusability**: Configure once, use many times with different prompts
2. **Consistent Identity**: Maintain a consistent role and behavior across interactions
3. **Skill Management**: Register skills once and use them across multiple prompts
4. **Default Settings**: Set sensible defaults for model parameters

### Example: Creating Different Agent Types

```python
# Creating a coding assistant
coding_assistant = InstantNeo(
    provider="anthropic",
    api_key="your-api-key",
    model="claude-3-opus-20240229",
    role_setup="""You are a Python coding assistant. 
    You help write clean, efficient, and well-documented code.
    You explain your reasoning and suggest improvements.""",
    temperature=0.2,  # Lower temperature for more precise coding
    max_tokens=4000   # Longer responses for detailed code
)

# Creating a creative writing assistant
creative_assistant = InstantNeo(
    provider="openai",
    api_key="your-api-key",
    model="gpt-4",
    role_setup="""You are a creative writing assistant.
    You help brainstorm ideas, develop characters, and craft engaging prose.
    Your tone is imaginative and enthusiastic.""",
    temperature=0.8,  # Higher temperature for more creative responses
    max_tokens=1000
)

# Creating a multimodal research assistant
research_assistant = InstantNeo(
    provider="openai",
    api_key="your-api-key",
    model="gpt-4-vision-preview",
    role_setup="""You are a research assistant that can analyze documents and images.
    You help extract key information, summarize content, and provide insights.""",
    temperature=0.3,
    max_tokens=2000
)
```

## The Run Method: Core of InstantNeo's Functionality

The `run()` method is where most of the action happens in InstantNeo. It's how you interact with the agent, provide prompts, and get responses.

### Method Signature

```python
run(
    prompt: str,
    execution_mode: str = "wait_response",
    async_execution: bool = False,
    return_full_response: bool = False,
    skills: Optional[List[str]] = None,
    images: Optional[Union[str, List[str]]] = None,
    image_detail: Optional[str] = None,
    stream: bool = False,
    **additional_params
) -> Any
```

### Understanding the Run Method

When you call `run()`, several important things happen:

1. **Parameter Resolution**:
   - The method first takes the instance's default parameters
   - Then applies any overrides you've specified in the `run()` call
   - This allows flexibility while maintaining consistent defaults

2. **Skills Selection**:
   - If you specify `skills`, only those skills are available for this specific run
   - If not, all skills registered with the agent are available
   - This allows you to control exactly which capabilities are available for each run

3. **Message Preparation**:
   - The system prompt (role_setup) is sent to the model with your prompt
   - Any images are processed and added to the message
   - Skills are formatted for the LLM to understand

4. **LLM Interaction**:
   - The prepared message is sent to the appropriate LLM provider
   - Responses are processed according to the execution mode
   - Results are returned in the requested format

### Why Adjust Parameters at Runtime?

The ability to override parameters at run time gives InstantNeo exceptional flexibility:

1. **Task-Specific Configurations**: Adjust temperature, tokens, etc. based on the specific task
2. **Selective Skill Usage**: Only expose the skills needed for a specific query
3. **Dynamic Content**: Include different images or additional context as needed
4. **Execution Control**: Choose how skills are executed based on the use case

### Key Run Parameters

- **prompt**: The instruction, user's input or query
- **execution_mode**: How skills should be executed (`wait_response`, `execution_only`, or `get_args`)
- **async_execution**: Whether to execute skills asynchronously
- **skills**: List of skill names to make available for this run (overrides instance defaults)
- **images**: Images to include with this specific prompt
- **stream**: Whether to stream the response in chunks

### Examples of Run Method Usage

#### Basic Usage

```python
# Simple conversation
response = agent.run("What is the capital of France?")
print(response)

# With specific skills enabled
response = agent.run(
    prompt="What's 125 + 437?",
    skills=["add"]  # Only make the add skill available
)
```

#### Overriding Parameters for Specific Tasks

```python
# Default parameters for most interactions
agent = InstantNeo(
    provider="anthropic",
    api_key="your-api-key",
    model="claude-3-sonnet-20240229",
    role_setup="You are a helpful assistant.",
    temperature=0.7,
    max_tokens=500
)

# Override for creative tasks
creative_response = agent.run(
    prompt="Write a short story about a robot discovering emotions",
    temperature=0.9,  # Higher temperature for more creativity
    max_tokens=2000   # Longer response for the story
)

# Override for precise tasks
precise_response = agent.run(
    prompt="Explain the difference between precision and recall in machine learning",
    temperature=0.2,  # Lower temperature for more precise explanation
    model="claude-3-opus-20240229"  # Use a more capable model for this complex topic
)
```

#### Working with Images

```python
# Instance without default images
agent = InstantNeo(
    provider="openai",
    api_key="your-api-key",
    model="gpt-4-vision-preview",
    role_setup="You are a visual analysis assistant."
)

# Analyze a single image
image_response = agent.run(
    prompt="What can you see in this image?",
    images=["./photo.jpg"],
    image_detail="high"  # Request high detail analysis
)

# Compare multiple images
comparison_response = agent.run(
    prompt="What's different between these two diagrams?",
    images=["./diagram1.jpg", "./diagram2.jpg"]
)

# Provide text and visual context together
context_response = agent.run(
    prompt="""This is a screenshot of an error message I'm getting.
    What might be causing it and how can I fix it?""",
    images=["./error_screenshot.png"]
)
```

#### Different Execution Modes

```python
# Wait for response (default) - blocks until skill execution completes
result = agent.run(
    prompt="Calculate the area of a circle with radius 5",
    skills=["circle_area"],
    execution_mode="wait_response"
)
print(f"The area is: {result}")

# Execute without waiting - fires the skill and continues immediately
agent.run(
    prompt="Log this user activity in the database",
    skills=["log_activity"],
    execution_mode="execution_only"
)
print("Logging requested (continuing immediately)")

# Get arguments without executing - useful for validation or custom handling
args = agent.run(
    prompt="Send an email to john@example.com with subject 'Meeting Tomorrow'",
    skills=["send_email"],
    execution_mode="get_args"
)
print(f"Would call function: {args[0]['name']}")
print(f"With arguments: {args[0]['arguments']}")
```

#### Streaming Responses

```python
# Stream the response in real-time
for chunk in agent.run(
    prompt="Explain quantum computing in simple terms",
    stream=True
):
    print(chunk, end="", flush=True)
```

## Other Key Methods in InstantNeo

InstantNeo provides several other important methods beyond `run()`. Here's a brief overview of the most commonly used ones:

### Modifying Agent Behavior

#### mod_role

Changes the agent's system prompt (role setup).

```python
agent.mod_role("You are now a mathematics tutor focused on explaining concepts simply.")
```

**Utility**: Allows you to repurpose an existing agent for a different role without creating a new instance.

### Skill Management

These methods help manage the skills available to the agent. A more detailed guide on skills will be provided separately.

#### register_skill

Adds a skill to the agent's available skills.

```python
from instantneo.skills import skill

@skill(
    description="Calculate the area of a circle",
    parameters={"radius": "The radius of the circle"}
)
def circle_area(radius: float) -> float:
    import math
    return math.pi * radius**2

agent.register_skill(circle_area)
```

**Utility**: Expands the agent's capabilities with new functions it can call.

#### get_skill_names

Lists all the registered skill names.

```python
available_skills = agent.get_skill_names()
print(f"Available skills: {available_skills}")
```

**Utility**: Useful for debugging or dynamically selecting skills to use in a run.

#### load_skills_from_file, load_skills_from_folder

Loads skills from external Python files or folders.

```python
# Load from a specific file
agent.load_skills_from_file("./math_skills.py")

# Load from an entire folder
agent.load_skills_from_folder("./skills_library")
```

**Utility**: Allows modular organization of skills and loading them as needed.

### Skill Manager Operations

These methods provide set operations for managing skill collections. They'll be covered in more detail in the dedicated skills guide.

```python
# Combine skills from another agent
agent1.sm_ops_union(agent2)

# Keep only skills that exist in both agents
agent1.sm_ops_intersection(agent2)

# Compare skill sets
comparison = agent1.sm_ops_compare(agent2)
```

**Utility**: Enables sophisticated management of skill collections between agents.
