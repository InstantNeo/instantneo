# InstantNeo Skills Guide

## Introduction to Skills

Skills are the foundational capability-building blocks in InstantNeo that empower your LLM agents to perform specific functions. They represent a powerful abstraction built on top of the "function calling" or "tool use" capability of modern large language models.

### What Are Skills?

Skills in InstantNeo are Python functions decorated with metadata that:

1. Define their purpose (description)
2. Specify their parameters and types
3. Categorize functionality (via tags)
4. Determine whether they can be executed by LLMs

When an LLM agent encounters a task that matches a skill's purpose, it can invoke that skill, passing the appropriate arguments to perform tasks that might otherwise be beyond the model's capabilities.

### Relationship to Function Calling

Skills are InstantNeo's implementation of the function calling/tool use capability that providers like OpenAI, Anthropic, and others have introduced. These capabilities allow LLMs to:

1. Recognize when a specific tool or function should be used
2. Generate the correct parameters to call that function
3. Integrate the results back into their responses

InstantNeo's skill system expands on this concept with additional features:

- Consistent interface across different LLM providers
- Rich metadata for better skill discovery and usage
- Execution control (synchronous, asynchronous, simulation)
- Skill composition and organization tools

### The Core Purpose of Skills

Skills extend your agent's capabilities beyond text generation to include:

- **Performing calculations**: Mathematical operations, conversions, statistics
- **Accessing external systems**: Databases, APIs, file systems
- **Processing data**: Transformations, filtering, analysis
- **Interacting with tools**: Web searches, image generation, notifications
- **Custom business logic**: Domain-specific algorithms and workflows

## The @skill Decorator

The heart of InstantNeo's skill system is the `@skill` decorator, which transforms regular Python functions into capabilities that LLM agents can discover and use.

### What the Decorator Does

When you apply `@skill` to a function, it:

1. **Captures metadata**: Stores description, parameter info, and tags
2. **Extracts type information**: Uses Python type hints to identify parameter types
3. **Creates execution tracking**: Adds functionality to monitor calls and results
4. **Formats for LLMs**: Prepares the function for discovery by language models

### Decorator Syntax

```python
@skill(
    description: Optional[str] = None,
    parameters: Optional[Dict[str, Dict[str, Any]]] = None,
    tags: Optional[List[str]] = None,
    version: Optional[str] = "1.0",
    **additional_metadata
)
```

## Creating Skills

Let's examine how to create effective skills for your InstantNeo agents.

### Basic Skill Creation

The simplest skill requires just a function with the `@skill` decorator:

```python
from instantneo.skills import skill

@skill(
    description="Add two numbers and return the result"
)
def add(a: int, b: int) -> int:
    return a + b
```

### Required and Optional Metadata

Technically, the only required parameter is the function itself. However, for effective skill usage:

- **description**: Highly recommended to help the LLM understand when to use the skill
- **parameters**: Optional but recommended for better parameter descriptions
- **tags**: Optional but useful for organizing and filtering skills
- **version**: Optional for tracking changes (defaults to "1.0")

### The Importance of Good Descriptions

A well-crafted description is crucial for proper skill usage:

```python
@skill(
    description="Calculate the distance between two geographical coordinates using the Haversine formula, returning the result in kilometers"
)
def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    # Implementation...
```

### Parameter Descriptions

While not mandatory, parameter descriptions greatly help the LLM understand what arguments to provide:

```python
@skill(
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

### Type Hints: Essential for Skills

Type hints are crucial in skills as they:

1. Tell the LLM what data types to provide as arguments
2. Enable validation of inputs
3. Provide better IDE support and documentation

```python
@skill(
    description="Filter a list to keep only values within a specified range"
)
def filter_range(values: List[float], min_value: float, max_value: float) -> List[float]:
    return [v for v in values if min_value <= v <= max_value]
```

### Complete Skill Example

Here's a complete, well-designed skill:

```python
@skill(
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

### Advantages of InstantNeo Skills

1. **Simplicity**: Write regular Python functions with added metadata
2. **No docstrings required**: Metadata is provided directly in the decorator
3. **Type safety**: Type hints ensure correct argument types
4. **Discoverability**: Rich metadata helps LLMs find and use the right skill
5. **Reusability**: Skills can be shared across different agents

## The SkillManager

The SkillManager is a registry system that organizes and manages skills for use by InstantNeo agents.

### Purpose of SkillManager

The SkillManager:

1. Provides a centralized registry for skills
2. Handles skill registration and discovery
3. Manages skill metadata
4. Resolves potential name conflicts
5. Enables organization through tags
6. Facilitates dynamic skill loading

### Creating and Using a SkillManager

```python
from instantneo.skills import SkillManager, skill

# Create a skill manager
manager = SkillManager()

@skill(description="Calculate the square of a number")
def square(x: float) -> float:
    return x * x

# Register the skill
manager.register_skill(square)

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

### Key SkillManager Methods

#### register_skill

Adds a skill to the registry.

```python
manager.register_skill(my_function)
```

#### get_skill_names

Returns a list of all registered skill names.

```python
skill_names = manager.get_skill_names()
print(f"Available skills: {skill_names}")
```

#### get_skill_by_name

Retrieves a skill function by its name.

```python
calculation_skill = manager.get_skill_by_name("calculate_tax")
if calculation_skill:
    result = calculation_skill(amount=100, rate=0.07)
```

#### get_skills_by_tag

Retrieves skills that have a specific tag.

```python
finance_skills = manager.get_skills_by_tag("finance")
print(f"Finance skills: {finance_skills}")
```

#### remove_skill

Removes a skill from the registry.

```python
manager.remove_skill("deprecated_function")
```

#### clear_registry

Removes all skills from the registry.

```python
manager.clear_registry()  # Start fresh
```

### Loading Skills Dynamically

SkillManager provides methods to load skills from various sources:

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

### Practical Example: Specialized Skill Sets

```python
# Create specialized managers for different domains
math_manager = SkillManager()
math_manager.load_skills.from_file("./math_skills.py")

finance_manager = SkillManager()
finance_manager.load_skills.from_file("./finance_skills.py")

data_manager = SkillManager()
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

## InstantNeo and SkillManager Integration

Every InstantNeo instance automatically creates and maintains an internal SkillManager.

### Internal SkillManager Structure

When you create an InstantNeo agent, it:

1. Initializes a SkillManager instance internally
2. Registers any skills provided during initialization
3. Provides access to SkillManager methods through proxy methods

This internal integration allows you to use SkillManager methods directly on the InstantNeo instance.

### Accessing SkillManager Methods via InstantNeo

Most SkillManager methods are available directly through the InstantNeo instance:

```python
# These do the same thing:
agent.register_skill(my_function)  # Via InstantNeo
agent.skill_manager.register_skill(my_function)  # Direct access to the internal manager

# More examples
names = agent.get_skill_names()
agent.remove_skill("obsolete_function")
agent.clear_registry()
```

### Direct Access to the Internal SkillManager

You can access the internal SkillManager directly:

```python
# Get the internal manager
manager = agent.skill_manager

# Use manager methods
metadata = manager.get_all_skills_metadata()
duplicates = manager.get_duplicate_skills()
```

### Practical Example: Building an Agent's Capabilities

```python
from instantneo import InstantNeo
from instantneo.skills import skill

# Create an agent
agent = InstantNeo(
    provider="anthropic",
    api_key="your-api-key",
    model="claude-3-opus-20240229",
    role_setup="You are a data analysis assistant."
)

# Define and register skills
@skill(description="Calculate mean of a list of numbers")
def mean(numbers: List[float]) -> float:
    return sum(numbers) / len(numbers)

@skill(description="Calculate median of a list of numbers")
def median(numbers: List[float]) -> float:
    sorted_nums = sorted(numbers)
    n = len(sorted_nums)
    if n % 2 == 0:
        return (sorted_nums[n//2 - 1] + sorted_nums[n//2]) / 2
    return sorted_nums[n//2]

# Register directly with the agent
agent.register_skill(mean)
agent.register_skill(median)

# Load more skills from files
agent.load_skills_from_file("./statistics_skills.py")
agent.load_skills_from_folder("./data_visualization_skills")

# Check available skills
print(f"Agent capabilities: {agent.get_skill_names()}")
```

## SkillManager Operations

SkillManager Operations provide powerful set-based operations for combining, comparing, and manipulating skill collections.

### Available Operations

The SkillManagerOperations class provides these key methods:

- **union**: Combines skills from multiple managers
- **intersection**: Keeps only skills that exist in all managers
- **difference**: Keeps skills from one manager that don't exist in another
- **symmetric_difference**: Keeps skills that exist in only one of two managers
- **compare**: Identifies common and unique skills between managers

### Using Operations with Standalone Managers

Let's start with the simplest case - operations between standalone SkillManager instances:

```python
from instantneo.skills import SkillManager
from instantneo.skills.skill_manager_operations import SkillManagerOperations

# Create specialized managers
web_skills = SkillManager()
web_skills.load_skills.from_file("./web_skills.py")

database_skills = SkillManager()
database_skills.load_skills.from_file("./database_skills.py")

# Create a manager with combined skills
backend_skills = SkillManagerOperations.union(web_skills, database_skills)
print(f"Combined backend skills: {backend_skills.get_skill_names()}")

# Find common skills between managers
common_skills = SkillManagerOperations.intersection(web_skills, database_skills)
print(f"Skills in both web and database: {common_skills.get_skill_names()}")

# Find skills unique to web development
web_only = SkillManagerOperations.difference(web_skills, database_skills)
print(f"Web-only skills: {web_only.get_skill_names()}")

# Compare skill sets
comparison = SkillManagerOperations.compare(web_skills, database_skills)
print(f"Common skills: {comparison['common_skills']}")
print(f"Web-only skills: {comparison['unique_to_a']}")
print(f"Database-only skills: {comparison['unique_to_b']}")
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

# Combine skills from both specialized agents
fullstack_agent.sm_ops_union(frontend_agent, backend_agent)
print(f"Full-stack skills: {fullstack_agent.get_skill_names()}")

# Compare skill coverage
comparison = fullstack_agent.sm_ops_compare(frontend_agent)
print(f"Skills unique to fullstack: {comparison['unique_to_a']}")
print(f"Skills in both: {comparison['common_skills']}")
```

### Mixing Managers and Agents

You can also combine SkillManagers with InstantNeo agents:

```python
# Create a standalone utility skill manager
utility_manager = SkillManager()
utility_manager.load_skills.from_file("./utility_skills.py")

# Add these utility skills to an existing agent
data_agent = InstantNeo(
    provider="anthropic",
    api_key="your-api-key",
    model="claude-3-opus-20240229",
    role_setup="You are a data science assistant."
)
data_agent.load_skills_from_file("./data_science_skills.py")

# Add utility skills to the data agent
data_agent.sm_ops_union(utility_manager)
print(f"Data agent skills after adding utilities: {data_agent.get_skill_names()}")
```

### Real-World Example: Building a Specialized Research Assistant

```python
from instantneo import InstantNeo
from instantneo.skills import SkillManager, skill

# Create managers for different research domains
statistics_manager = SkillManager()
statistics_manager.load_skills.from_file("./statistics_skills.py")

nlp_manager = SkillManager()
nlp_manager.load_skills.from_file("./nlp_skills.py")

visualization_manager = SkillManager()
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

# Add project-specific custom skills
@skill(
    description="Load dataset from the project repository",
    parameters={"dataset_name": "Name of the dataset to load"}
)
def load_project_dataset(dataset_name: str) -> dict:
    # Implementation...
    return {"data": [...], "metadata": {...}}

research_agent.register_skill(load_project_dataset)

# Check the final skill set
print(f"Research assistant capabilities: {research_agent.get_skill_names()}")

# Use the agent with its specialized skill set
response = research_agent.run(
    prompt="Analyze the sentiment distribution in our customer feedback dataset"
)
```

## Conclusion

InstantNeo's skill system provides a powerful framework for extending LLM capabilities with custom functions. The combination of the `@skill` decorator for defining capabilities and the SkillManager for organizing them creates a flexible architecture that can adapt to a wide range of use cases.

By understanding how to create well-described skills, manage them efficiently, and compose them using operations like union and intersection, you can build highly capable AI agents tailored to your specific needs.
