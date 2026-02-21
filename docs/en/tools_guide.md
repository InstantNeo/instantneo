# InstantNeo Tools Guide

## Introduction to Tools

Tools are the foundational capability-building blocks in InstantNeo that empower your LLM agents to perform specific functions. They represent a powerful abstraction built on top of the "function calling" or "tool use" capability of modern large language models.

### What Are Tools?

Tools in InstantNeo are Python functions decorated with metadata that:

1. Define their purpose (description)
2. Specify their parameters and types
3. Categorize functionality (via tags)
4. Determine whether they can be executed by LLMs

When an LLM agent encounters a task that matches a tool's purpose, it can invoke that tool, passing the appropriate arguments to perform tasks that might otherwise be beyond the model's capabilities.

### Relationship to Function Calling

Tools are InstantNeo's implementation of the function calling/tool use capability that providers like OpenAI, Anthropic, and others have introduced. These capabilities allow LLMs to:

1. Recognize when a specific tool or function should be used
2. Generate the correct parameters to call that function
3. Integrate the results back into their responses

InstantNeo's tool system expands on this concept with additional features:

- Consistent interface across different LLM providers
- Rich metadata for better tool discovery and usage
- Execution control (synchronous, asynchronous, simulation)
- Tool composition and organization utilities

### The Core Purpose of Tools

Tools extend your agent's capabilities beyond text generation to include:

- **Performing calculations**: Mathematical operations, conversions, statistics
- **Accessing external systems**: Databases, APIs, file systems
- **Processing data**: Transformations, filtering, analysis
- **Interacting with tools**: Web searches, image generation, notifications
- **Custom business logic**: Domain-specific algorithms and workflows

## The @tool Decorator

The heart of InstantNeo's tool system is the `@tool` decorator, which transforms regular Python functions into capabilities that LLM agents can discover and use.

### What the Decorator Does

When you apply `@tool` to a function, it:

1. **Captures metadata**: Stores description, parameter info, and tags
2. **Extracts type information**: Uses Python type hints to identify parameter types
3. **Creates execution tracking**: Adds functionality to monitor calls and results
4. **Formats for LLMs**: Prepares the function for discovery by language models

### Decorator Syntax

```python
@tool(
    description: Optional[str] = None,
    parameters: Optional[Dict[str, Dict[str, Any]]] = None,
    tags: Optional[List[str]] = None,
    version: Optional[str] = "1.0",
    **additional_metadata
)
```

## Creating Tools

Let's examine how to create effective tools for your InstantNeo agents.

### Basic Tool Creation

The simplest tool requires just a function with the `@tool` decorator:

```python
from instantneo.skills import tool

@tool(
    description="Add two numbers and return the result"
)
def add(a: int, b: int) -> int:
    return a + b
```

### Required and Optional Metadata

Technically, the only required parameter is the function itself. However, for effective tool usage:

- **description**: Highly recommended to help the LLM understand when to use the tool
- **parameters**: Optional but recommended for better parameter descriptions
- **tags**: Optional but useful for organizing and filtering tools
- **version**: Optional for tracking changes (defaults to "1.0")

### The Importance of Good Descriptions

A well-crafted description is crucial for proper tool usage:

```python
@tool(
    description="Calculate the distance between two geographical coordinates using the Haversine formula, returning the result in kilometers"
)
def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    # Implementation...
```

### Parameter Descriptions

While not mandatory, parameter descriptions greatly help the LLM understand what arguments to provide:

```python
@tool(
    description="Send an email notification",
    parameters={
        "recipient": "Email address of the recipient",
        "subject": "Email subject line",
        "body": "Main content of the email",
        "priority": "Importance level (low, normal, high)"
    }
)
def send_email(recipient: str, subject: str, body: str, priority: str = "normal") -> bool:
    # Implementation...
```

Note that parameter descriptions don't include type information - that comes from the function's typehints.

### Type Hints: Essential for Tools

Type hints are crucial in tools as they:

1. Tell the LLM what data types to provide as arguments
2. Enable validation of inputs
3. Provide better IDE support and documentation

```python
@tool(
    description="Filter a list to keep only values within a specified range"
)
def filter_range(values: List[float], min_value: float, max_value: float) -> List[float]:
    return [v for v in values if min_value <= v <= max_value]
```

### Complete Tool Example

Here's a complete, well-designed tool:

```python
@tool(
    description="Calculate monthly loan payment amount",
    parameters={
        "principal": "Total loan amount in dollars",
        "annual_rate": "Annual interest rate (as a decimal, e.g., 0.05 for 5%)",
        "years": "Loan term in years",
    },
    tags=["finance", "loans", "calculation"]
)
def calculate_monthly_payment(principal: float, annual_rate: float, years: int) -> float:
    monthly_rate = annual_rate / 12
    num_payments = years * 12
    if monthly_rate == 0:
        return principal / num_payments
    return principal * (monthly_rate * (1 + monthly_rate)**num_payments) / ((1 + monthly_rate)**num_payments - 1)
```

### Advantages of InstantNeo Tools

1. **Simplicity**: Write regular Python functions with added metadata
2. **No docstrings required**: Metadata is provided directly in the decorator
3. **Type safety**: Type hints ensure correct argument types
4. **Discoverability**: Rich metadata helps LLMs find and use the right tool
5. **Reusability**: Tools can be shared across different agents

## AgentCapabilities

AgentCapabilities is a registry system that organizes and manages tools for use by InstantNeo agents.

### Purpose of AgentCapabilities

AgentCapabilities:

1. Provides a centralized registry for tools
2. Handles tool registration and discovery
3. Manages tool metadata
4. Resolves potential name conflicts
5. Enables organization through tags
6. Facilitates dynamic tool loading

### Creating and Using AgentCapabilities

```python
from instantneo.skills import AgentCapabilities, tool

# Create an agent capabilities instance
manager = AgentCapabilities()

@tool(description="Calculate the square of a number")
def square(x: float) -> float:
    return x * x

# Register the tool
manager.register_tool(square)

# Use the manager with an InstantNeo agent
from instantneo import InstantNeo

agent = InstantNeo(
    provider="anthropic",
    api_key="your-api-key",
    model="claude-3-sonnet-20240229",
    role_setup="You are a helpful assistant.",
    skills=manager  # Pass the entire manager
)
```

### Key AgentCapabilities Methods

#### register_tool

Adds a tool to the registry.

```python
manager.register_tool(my_function)
```

#### get_tool_names

Returns a list of all registered tool names.

```python
tool_names = manager.get_tool_names()
print(f"Available tools: {tool_names}")
```

#### get_tool_by_name

Retrieves a tool function by its name.

```python
calculation_tool = manager.get_tool_by_name("calculate_tax")
if calculation_tool:
    result = calculation_tool(amount=100, rate=0.07)
```

#### get_tools_by_tag

Retrieves tools that have a specific tag.

```python
finance_tools = manager.get_tools_by_tag("finance")
print(f"Finance tools: {finance_tools}")
```

#### remove_tool

Removes a tool from the registry.

```python
manager.remove_tool("deprecated_function")
```

#### clear_registry

Removes all tools from the registry.

```python
manager.clear_registry()  # Start fresh
```

### Loading Tools Dynamically

AgentCapabilities provides methods to load tools from various sources:

```python
# Load from a specific file
manager.load_skills.from_file("./math_skills.py")

# Load from the current module
manager.load_skills.from_current()

# Load from a folder
manager.load_skills.from_folder("./my_skills_library")

# Load with filtering
manager.load_skills.from_folder(
    "./skills_library",
    by_tags=["data_processing"]
)
```

### Practical Example: Specialized Tool Sets

```python
# Create specialized managers for different domains
math_manager = AgentCapabilities()
math_manager.load_skills.from_file("./math_skills.py")

finance_manager = AgentCapabilities()
finance_manager.load_skills.from_file("./finance_skills.py")

data_manager = AgentCapabilities()
data_manager.load_skills.from_folder("./data_skills")

# Create agents with specialized capabilities
math_agent = InstantNeo(
    provider="anthropic",
    api_key="your-api-key",
    model="claude-3-sonnet-20240229",
    role_setup="You are a mathematics assistant.",
    skills=math_manager
)

finance_agent = InstantNeo(
    provider="anthropic",
    api_key="your-api-key",
    model="claude-3-opus-20240229",
    role_setup="You are a financial analysis assistant.",
    skills=finance_manager
)
```

## InstantNeo and AgentCapabilities Integration

Every InstantNeo instance automatically creates and maintains an internal AgentCapabilities.

### Internal AgentCapabilities Structure

When you create an InstantNeo agent, it:

1. Initializes an AgentCapabilities instance internally
2. Registers any tools provided during initialization
3. Provides access to AgentCapabilities methods through proxy methods

This internal integration allows you to use AgentCapabilities methods directly on the InstantNeo instance.

### Accessing AgentCapabilities Methods via InstantNeo

Most AgentCapabilities methods are available directly through the InstantNeo instance:

```python
# These do the same thing:
agent.register_tool(my_function)  # Via InstantNeo
agent.capabilities.register_tool(my_function)  # Direct access to the internal manager

# More examples
names = agent.get_tool_names()
agent.remove_tool("obsolete_function")
agent.clear_registry()
```

### Direct Access to the Internal AgentCapabilities

You can access the internal AgentCapabilities directly:

```python
# Get the internal manager
manager = agent.capabilities

# Use manager methods
metadata = manager.get_all_tools_metadata()
duplicates = manager.get_duplicate_tools()
```

### Practical Example: Building an Agent's Capabilities

```python
from instantneo import InstantNeo
from instantneo.skills import tool

# Create an agent
agent = InstantNeo(
    provider="anthropic",
    api_key="your-api-key",
    model="claude-3-opus-20240229",
    role_setup="You are a data analysis assistant."
)

# Define and register tools
@tool(description="Calculate mean of a list of numbers")
def mean(numbers: List[float]) -> float:
    return sum(numbers) / len(numbers)

@tool(description="Calculate median of a list of numbers")
def median(numbers: List[float]) -> float:
    sorted_nums = sorted(numbers)
    n = len(sorted_nums)
    if n % 2 == 0:
        return (sorted_nums[n//2 - 1] + sorted_nums[n//2]) / 2
    return sorted_nums[n//2]

# Register directly with the agent
agent.register_tool(mean)
agent.register_tool(median)

# Load more skills from files
agent.load_skills_from_file("./statistics_skills.py")
agent.load_skills_from_folder("./data_visualization_skills")

# Check available tools
print(f"Agent capabilities: {agent.get_tool_names()}")
```

## Capabilities Operations

Capabilities Operations provide powerful set-based operations for combining, comparing, and manipulating tool collections.

### Available Operations

The CapabilitiesOperations class provides these key methods:

- **union**: Combines tools from multiple managers
- **intersection**: Keeps only tools that exist in all managers
- **difference**: Keeps tools from one manager that don't exist in another
- **symmetric_difference**: Keeps tools that exist in only one of two managers
- **compare**: Identifies common and unique tools between managers

### Using Operations with Standalone AgentCapabilities

Let's start with the simplest case - operations between standalone AgentCapabilities instances:

```python
from instantneo.skills import AgentCapabilities
from instantneo.skills import CapabilitiesOperations

# Create specialized managers
web_skills = AgentCapabilities()
web_skills.load_skills.from_file("./web_skills.py")

database_skills = AgentCapabilities()
database_skills.load_skills.from_file("./database_skills.py")

# Create a manager with combined tools
backend_skills = CapabilitiesOperations.union(web_skills, database_skills)
print(f"Combined backend tools: {backend_skills.get_tool_names()}")

# Find common tools between managers
common_skills = CapabilitiesOperations.intersection(web_skills, database_skills)
print(f"Tools in both web and database: {common_skills.get_tool_names()}")

# Find tools unique to web development
web_only = CapabilitiesOperations.difference(web_skills, database_skills)
print(f"Web-only tools: {web_only.get_tool_names()}")

# Compare tool sets
comparison = CapabilitiesOperations.compare(web_skills, database_skills)
print(f"Common tools: {comparison['common_skills']}")
print(f"Web-only tools: {comparison['unique_to_a']}")
print(f"Database-only tools: {comparison['unique_to_b']}")
```

### Operations Between InstantNeo Agents

InstantNeo agents provide direct access to these operations:

```python
from instantneo import InstantNeo

# Create specialized agents
frontend_agent = InstantNeo(
    provider="anthropic",
    api_key="your-api-key",
    model="claude-3-sonnet-20240229",
    role_setup="You are a frontend development assistant."
)
frontend_agent.load_skills_from_file("./frontend_skills.py")

backend_agent = InstantNeo(
    provider="anthropic",
    api_key="your-api-key",
    model="claude-3-sonnet-20240229",
    role_setup="You are a backend development assistant."
)
backend_agent.load_skills_from_file("./backend_skills.py")

# Create a full-stack agent
fullstack_agent = InstantNeo(
    provider="anthropic",
    api_key="your-api-key",
    model="claude-3-opus-20240229",
    role_setup="You are a full-stack development assistant."
)

# Combine tools from both specialized agents
fullstack_agent.sm_ops_union(frontend_agent, backend_agent)
print(f"Full-stack tools: {fullstack_agent.get_tool_names()}")

# Compare tool coverage
comparison = fullstack_agent.sm_ops_compare(frontend_agent)
print(f"Tools unique to fullstack: {comparison['unique_to_a']}")
print(f"Tools in both: {comparison['common_skills']}")
```

### Mixing AgentCapabilities and Agents

You can also combine AgentCapabilities with InstantNeo agents:

```python
# Create a standalone utility capabilities
utility_manager = AgentCapabilities()
utility_manager.load_skills.from_file("./utility_skills.py")

# Add these utility tools to an existing agent
data_agent = InstantNeo(
    provider="anthropic",
    api_key="your-api-key",
    model="claude-3-opus-20240229",
    role_setup="You are a data science assistant."
)
data_agent.load_skills_from_file("./data_science_skills.py")

# Add utility tools to the data agent
data_agent.sm_ops_union(utility_manager)
print(f"Data agent tools after adding utilities: {data_agent.get_tool_names()}")
```

### Real-World Example: Building a Specialized Research Assistant

```python
from instantneo import InstantNeo
from instantneo.skills import AgentCapabilities, tool

# Create managers for different research domains
statistics_manager = AgentCapabilities()
statistics_manager.load_skills.from_file("./statistics_skills.py")

nlp_manager = AgentCapabilities()
nlp_manager.load_skills.from_file("./nlp_skills.py")

visualization_manager = AgentCapabilities()
visualization_manager.load_skills.from_file("./visualization_skills.py")

# Create a base research agent
research_agent = InstantNeo(
    provider="anthropic",
    api_key="your-api-key",
    model="claude-3-opus-20240229",
    role_setup="""You are a research assistant specializing in data analysis.
    You help process data, run statistical analyses, and interpret results."""
)

# Add specialized domains according to the research needs
project_type = "text_analysis"  # Could be determined dynamically

if project_type == "statistical_analysis":
    research_agent.sm_ops_union(statistics_manager, visualization_manager)
elif project_type == "text_analysis":
    research_agent.sm_ops_union(nlp_manager, visualization_manager)
elif project_type == "comprehensive":
    research_agent.sm_ops_union(statistics_manager, nlp_manager, visualization_manager)

# Add project-specific custom tools
@tool(
    description="Load dataset from the project repository",
    parameters={"dataset_name": "Name of the dataset to load"}
)
def load_project_dataset(dataset_name: str) -> dict:
    # Implementation...
    return {"data": [...], "metadata": {...}}

research_agent.register_tool(load_project_dataset)

# Check the final tool set
print(f"Research assistant capabilities: {research_agent.get_tool_names()}")

# Use the agent with its specialized tool set
response = research_agent.run(
    prompt="Analyze the sentiment distribution in our customer feedback dataset"
)
```

## Conclusion

InstantNeo's tool system provides a powerful framework for extending LLM capabilities with custom functions. The combination of the `@tool` decorator for defining capabilities and AgentCapabilities for organizing them creates a flexible architecture that can adapt to a wide range of use cases.

By understanding how to create well-described tools, manage them efficiently, and compose them using operations like union and intersection, you can build highly capable AI agents tailored to your specific needs.
