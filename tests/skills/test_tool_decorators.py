"""
Tests for the @tool decorator (and its alias @skill).

Covers:
- Metadata extraction: name, description, tags, version, required params
- Description sources: explicit > docstring short_description > full docstring > fallback
- Parameter sources: explicit dict > annotations + docstring
- Non-dict parameter (value becomes description)
- Required vs optional parameters
- Sync wrapper: captures result, captures exception
- Async wrapper: works correctly, captures result and exception
- Helper methods: get_last_call, get_last_result, get_last_params
- `skill` is an alias for `tool` producing the same metadata dict
"""
import asyncio
import pytest
from instantneo.skills.tool_decorators import tool, skill


# ════════════════════════════════════════════════════════════════════
# Metadata — basic
# ════════════════════════════════════════════════════════════════════

def test_tool_name_equals_function_name():
    @tool(description="test")
    def my_func():
        pass

    assert my_func.tool_metadata["name"] == "my_func"


def test_tool_explicit_description():
    @tool(description="Explicit description")
    def my_func():
        pass

    assert my_func.tool_metadata["description"] == "Explicit description"


def test_tool_description_from_short_docstring():
    @tool()
    def my_func():
        """Short description from doc."""
        pass

    assert my_func.tool_metadata["description"] == "Short description from doc."


def test_tool_description_from_full_docstring_when_no_short():
    @tool()
    def my_func():
        """Full docstring text here."""
        pass

    # short_description should be parsed as "Full docstring text here."
    assert "Full docstring text here." in my_func.tool_metadata["description"]


def test_tool_description_fallback_when_no_docstring():
    @tool()
    def no_doc():
        pass

    desc = no_doc.tool_metadata["description"]
    assert isinstance(desc, str)
    assert len(desc) > 0


# ════════════════════════════════════════════════════════════════════
# Metadata — tags, version, additional kwargs
# ════════════════════════════════════════════════════════════════════

def test_tool_tags():
    @tool(description="t", tags=["data", "search"])
    def tagged_search(q: str) -> list:
        return []

    assert "data" in tagged_search.tool_metadata["tags"]
    assert "search" in tagged_search.tool_metadata["tags"]


def test_tool_empty_tags_by_default():
    @tool(description="t")
    def func():
        pass

    assert func.tool_metadata["tags"] == []


def test_tool_version():
    @tool(description="t", version="2.0")
    def func():
        pass

    assert func.tool_metadata["version"] == "2.0"


def test_tool_additional_metadata_kwargs():
    @tool(description="t", author="alice")
    def func():
        pass

    assert func.tool_metadata["author"] == "alice"


# ════════════════════════════════════════════════════════════════════
# Metadata — parameters
# ════════════════════════════════════════════════════════════════════

def test_tool_explicit_parameters():
    @tool(description="t", parameters={
        "x": {"description": "The x value", "type": "int"}
    })
    def func(x: int):
        pass

    params = func.tool_metadata["parameters"]
    assert "x" in params
    assert params["x"]["description"] == "The x value"
    assert params["x"]["type"] == "int"


def test_tool_parameter_type_inferred_from_annotation():
    @tool(description="t", parameters={
        "x": {"description": "A number"}
        # no "type" key — should be inferred from annotation
    })
    def func(x: int):
        pass

    assert func.tool_metadata["parameters"]["x"]["type"] == "int"


def test_tool_non_dict_parameter_becomes_description():
    @tool(description="t", parameters={"x": "A plain string description"})
    def func(x: int):
        pass

    p = func.tool_metadata["parameters"]["x"]
    assert p["description"] == "A plain string description"


def test_tool_required_params_no_defaults():
    @tool(description="t")
    def func(a: int, b: str):
        pass

    assert sorted(func.tool_metadata["required"]) == ["a", "b"]


def test_tool_optional_params_excluded_from_required():
    @tool(description="t")
    def func(required: str, optional: str = "default"):
        pass

    assert "required" in func.tool_metadata["required"]
    assert "optional" not in func.tool_metadata["required"]


def test_tool_params_from_docstring():
    @tool()
    def greet(name: str) -> str:
        """Greet someone.

        Args:
            name: The person's name.
        """
        return f"Hello {name}"

    params = greet.tool_metadata["parameters"]
    assert "name" in params
    # Should pick up description from docstring
    assert params["name"]["description"] != ""


# ════════════════════════════════════════════════════════════════════
# Sync wrapper behaviour
# ════════════════════════════════════════════════════════════════════

def test_sync_wrapper_returns_result():
    @tool(description="t")
    def double(x: int) -> int:
        return x * 2

    assert double(5) == 10


def test_sync_wrapper_captures_result():
    @tool(description="t")
    def double(x: int) -> int:
        return x * 2

    double(7)
    assert double.get_last_result() == 14


def test_sync_wrapper_captures_exception():
    @tool(description="t")
    def fail():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        fail()

    last = fail.get_last_call()
    assert isinstance(last["exception"], RuntimeError)


def test_sync_get_last_call_captures_args_kwargs():
    @tool(description="t")
    def func(a: int, b: int = 0) -> int:
        return a + b

    func(1, b=2)
    last = func.get_last_call()
    assert last["args"] == (1,)
    assert last["kwargs"] == {"b": 2}


def test_sync_get_last_params():
    @tool(description="t")
    def func(x: int) -> int:
        return x

    func(99)
    params = func.get_last_params()
    assert params is not None
    assert params["args"] == (99,)


def test_sync_get_last_result_before_call_is_none():
    @tool(description="t")
    def fresh(x: int) -> int:
        return x

    # Never called — get_last_call returns None
    assert fresh.get_last_call() is None
    assert fresh.get_last_result() is None
    assert fresh.get_last_params() is None


# ════════════════════════════════════════════════════════════════════
# Async wrapper behaviour
# ════════════════════════════════════════════════════════════════════

def test_async_wrapper_returns_result():
    @tool(description="async t")
    async def async_double(x: int) -> int:
        return x * 2

    result = asyncio.run(async_double(5))
    assert result == 10


def test_async_wrapper_propagates_exception():
    @tool(description="async t")
    async def async_fail():
        raise ValueError("async boom")

    # The wrapper must re-raise the exception — not swallow it.
    with pytest.raises(ValueError, match="async boom"):
        asyncio.run(async_fail())


# ════════════════════════════════════════════════════════════════════
# skill alias
# ════════════════════════════════════════════════════════════════════

def test_skill_alias_produces_same_metadata():
    @skill(description="via skill alias")
    def my_skill(x: int) -> int:
        return x

    assert my_skill.tool_metadata is my_skill.skill_metadata
    assert my_skill.tool_metadata["description"] == "via skill alias"


def test_skill_alias_function_works():
    @skill(description="t")
    def my_skill(x: int) -> int:
        return x + 1

    assert my_skill(10) == 11


# ════════════════════════════════════════════════════════════════════
# functools.wraps — name and docstring preserved
# ════════════════════════════════════════════════════════════════════

def test_tool_preserves_function_name():
    @tool(description="t")
    def original_name(x: int) -> int:
        return x

    assert original_name.__name__ == "original_name"


def test_tool_preserves_docstring():
    @tool(description="t")
    def documented():
        """The docstring."""
        pass

    assert documented.__doc__ == "The docstring."
