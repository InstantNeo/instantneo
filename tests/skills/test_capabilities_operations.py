"""
Tests for CapabilitiesOperations (set operations on AgentCapabilities).

Covers: union, intersection, difference, symmetric_difference, compare.
"""
import pytest
from instantneo.skills.agent_capabilities import AgentCapabilities
from instantneo.skills.capabilities_operations import CapabilitiesOperations
from instantneo.skills.tool_decorators import tool


# ── Shared tools ─────────────────────────────────────────────────

@tool(description="Op-test tool A")
def _op_tool_a(x: int) -> int:
    return x


@tool(description="Op-test tool B")
def _op_tool_b(y: str) -> str:
    return y


@tool(description="Op-test tool C")
def _op_tool_c(z: float) -> float:
    return z


# ════════════════════════════════════════════════════════════════════
# union
# ════════════════════════════════════════════════════════════════════

def test_union_merges_tools():
    caps_a = AgentCapabilities(skills=[_op_tool_a, _op_tool_b])
    caps_b = AgentCapabilities(skills=[_op_tool_b, _op_tool_c])
    result = CapabilitiesOperations.union(caps_a, caps_b)
    names = set(result.get_tool_names())
    assert "_op_tool_a" in names
    assert "_op_tool_b" in names
    assert "_op_tool_c" in names


def test_union_no_managers_empty():
    result = CapabilitiesOperations.union()
    assert result.get_tool_names() == []


def test_union_single_manager():
    caps = AgentCapabilities(skills=[_op_tool_a])
    result = CapabilitiesOperations.union(caps)
    assert "_op_tool_a" in result.get_tool_names()


def test_union_concatenates_global_instructions():
    caps_a = AgentCapabilities(skills=[_op_tool_a], global_instructions="Do A")
    caps_b = AgentCapabilities(skills=[_op_tool_b], global_instructions="Do B")
    result = CapabilitiesOperations.union(caps_a, caps_b)
    instr = result.get_global_instructions()
    assert "Do A" in instr
    assert "Do B" in instr


def test_union_deduplicates_global_instructions():
    caps_a = AgentCapabilities(skills=[_op_tool_a], global_instructions="Same")
    caps_b = AgentCapabilities(skills=[_op_tool_b], global_instructions="Same")
    result = CapabilitiesOperations.union(caps_a, caps_b)
    assert result.get_global_instructions().count("Same") == 1


def test_union_empty_instructions_not_included():
    caps_a = AgentCapabilities(skills=[_op_tool_a])  # no global_instructions
    caps_b = AgentCapabilities(skills=[_op_tool_b], global_instructions="Some instruction")
    result = CapabilitiesOperations.union(caps_a, caps_b)
    assert result.get_global_instructions() == "Some instruction"


# ════════════════════════════════════════════════════════════════════
# intersection
# ════════════════════════════════════════════════════════════════════

def test_intersection_common_tools():
    caps_a = AgentCapabilities(skills=[_op_tool_a, _op_tool_b])
    caps_b = AgentCapabilities(skills=[_op_tool_b, _op_tool_c])
    result = CapabilitiesOperations.intersection(caps_a, caps_b)
    names = set(result.get_tool_names())
    assert names == {"_op_tool_b"}


def test_intersection_no_common_tools():
    caps_a = AgentCapabilities(skills=[_op_tool_a])
    caps_b = AgentCapabilities(skills=[_op_tool_c])
    result = CapabilitiesOperations.intersection(caps_a, caps_b)
    assert result.get_tool_names() == []


def test_intersection_no_managers():
    result = CapabilitiesOperations.intersection()
    assert result.get_tool_names() == []


def test_intersection_single_manager():
    caps = AgentCapabilities(skills=[_op_tool_a])
    result = CapabilitiesOperations.intersection(caps)
    assert "_op_tool_a" in result.get_tool_names()


def test_intersection_all_three_managers():
    caps_a = AgentCapabilities(skills=[_op_tool_a, _op_tool_b, _op_tool_c])
    caps_b = AgentCapabilities(skills=[_op_tool_b, _op_tool_c])
    caps_c = AgentCapabilities(skills=[_op_tool_c])
    result = CapabilitiesOperations.intersection(caps_a, caps_b, caps_c)
    assert set(result.get_tool_names()) == {"_op_tool_c"}


# ════════════════════════════════════════════════════════════════════
# difference
# ════════════════════════════════════════════════════════════════════

def test_difference_returns_only_base_unique():
    caps_a = AgentCapabilities(skills=[_op_tool_a, _op_tool_b])
    caps_b = AgentCapabilities(skills=[_op_tool_b])
    result = CapabilitiesOperations.difference(caps_a, caps_b)
    names = set(result.get_tool_names())
    assert names == {"_op_tool_a"}


def test_difference_nothing_excluded():
    caps_a = AgentCapabilities(skills=[_op_tool_a])
    caps_b = AgentCapabilities()
    result = CapabilitiesOperations.difference(caps_a, caps_b)
    assert "_op_tool_a" in result.get_tool_names()


def test_difference_all_excluded():
    caps_a = AgentCapabilities(skills=[_op_tool_a])
    caps_b = AgentCapabilities(skills=[_op_tool_a])
    result = CapabilitiesOperations.difference(caps_a, caps_b)
    assert result.get_tool_names() == []


# ════════════════════════════════════════════════════════════════════
# symmetric_difference
# ════════════════════════════════════════════════════════════════════

def test_symmetric_difference_unique_in_either():
    caps_a = AgentCapabilities(skills=[_op_tool_a, _op_tool_b])
    caps_b = AgentCapabilities(skills=[_op_tool_b, _op_tool_c])
    result = CapabilitiesOperations.symmetric_difference(caps_a, caps_b)
    names = set(result.get_tool_names())
    assert names == {"_op_tool_a", "_op_tool_c"}


def test_symmetric_difference_identical_returns_empty():
    caps_a = AgentCapabilities(skills=[_op_tool_a, _op_tool_b])
    caps_b = AgentCapabilities(skills=[_op_tool_a, _op_tool_b])
    result = CapabilitiesOperations.symmetric_difference(caps_a, caps_b)
    assert result.get_tool_names() == []


def test_symmetric_difference_disjoint():
    caps_a = AgentCapabilities(skills=[_op_tool_a])
    caps_b = AgentCapabilities(skills=[_op_tool_c])
    result = CapabilitiesOperations.symmetric_difference(caps_a, caps_b)
    names = set(result.get_tool_names())
    assert names == {"_op_tool_a", "_op_tool_c"}


# ════════════════════════════════════════════════════════════════════
# compare
# ════════════════════════════════════════════════════════════════════

def test_compare_all_buckets():
    caps_a = AgentCapabilities(skills=[_op_tool_a, _op_tool_b])
    caps_b = AgentCapabilities(skills=[_op_tool_b, _op_tool_c])
    result = CapabilitiesOperations.compare(caps_a, caps_b)
    assert result["common_skills"] == {"_op_tool_b"}
    assert result["unique_to_a"] == {"_op_tool_a"}
    assert result["unique_to_b"] == {"_op_tool_c"}


def test_compare_identical_managers():
    caps_a = AgentCapabilities(skills=[_op_tool_a])
    caps_b = AgentCapabilities(skills=[_op_tool_a])
    result = CapabilitiesOperations.compare(caps_a, caps_b)
    assert result["common_skills"] == {"_op_tool_a"}
    assert result["unique_to_a"] == set()
    assert result["unique_to_b"] == set()


def test_compare_empty_managers():
    caps_a = AgentCapabilities()
    caps_b = AgentCapabilities()
    result = CapabilitiesOperations.compare(caps_a, caps_b)
    assert result["common_skills"] == set()
    assert result["unique_to_a"] == set()
    assert result["unique_to_b"] == set()
