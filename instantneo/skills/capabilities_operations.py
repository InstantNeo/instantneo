from typing import List, Dict, Set, Optional, Union
from .agent_capabilities import AgentCapabilities


class CapabilitiesOperations:
    """Provides set operations on AgentCapabilities instances."""

    @staticmethod
    def union(*managers: "AgentCapabilities") -> "AgentCapabilities":
        """
        Returns an AgentCapabilities that contains the union of all tools
        registered in the managers passed and concatenates their instructions.
        """
        unified_manager = AgentCapabilities()
        collected_instructions = []
        seen_instructions = set()

        for m in managers:
            for func in m.registry.values():
                unified_manager.register_tool(func)

            if hasattr(m, 'get_global_instructions'):
                instr = m.get_global_instructions()
                if instr and instr not in seen_instructions:
                    collected_instructions.append(instr)
                    seen_instructions.add(instr)

        if collected_instructions:
            final_instructions = "\n\n".join(collected_instructions)
            unified_manager.set_global_instructions(final_instructions)

        return unified_manager

    @staticmethod
    def intersection(*managers: "AgentCapabilities") -> "AgentCapabilities":
        """
        Returns an AgentCapabilities with the tools that appear in ALL managers passed.
        """
        if not managers:
            return AgentCapabilities()

        common_names = set(managers[0].get_tool_names())
        for m in managers[1:]:
            common_names &= set(m.get_tool_names())

        intersection_manager = AgentCapabilities()

        for name in common_names:
            func = managers[0].get_tool_by_name(name)
            if callable(func):
                intersection_manager.register_tool(func)

        return intersection_manager

    @staticmethod
    def difference(base_manager: "AgentCapabilities", exclude_manager: "AgentCapabilities") -> "AgentCapabilities":
        """
        Returns an AgentCapabilities with tools in base_manager but NOT in exclude_manager.
        """
        base_names = set(base_manager.get_tool_names())
        exclude_names = set(exclude_manager.get_tool_names())

        diff_names = base_names - exclude_names

        diff_manager = AgentCapabilities()
        for name in diff_names:
            func = base_manager.get_tool_by_name(name)
            if callable(func):
                diff_manager.register_tool(func)
        return diff_manager

    @staticmethod
    def symmetric_difference(manager_a: "AgentCapabilities", manager_b: "AgentCapabilities") -> "AgentCapabilities":
        """
        Returns an AgentCapabilities with the symmetric difference of tools.
        """
        a_names = set(manager_a.get_tool_names())
        b_names = set(manager_b.get_tool_names())

        sym_diff_names = a_names ^ b_names

        sym_diff_manager = AgentCapabilities()
        for name in sym_diff_names:
            func_a = manager_a.get_tool_by_name(name)
            func_b = manager_b.get_tool_by_name(name)

            if func_a and not func_b:
                if callable(func_a):
                    sym_diff_manager.register_tool(func_a)
            elif func_b and not func_a:
                if callable(func_b):
                    sym_diff_manager.register_tool(func_b)

        return sym_diff_manager

    @staticmethod
    def compare(manager_a: "AgentCapabilities", manager_b: "AgentCapabilities") -> Dict[str, Set[str]]:
        """
        Returns a dict with common_skills, unique_to_a, unique_to_b.
        """
        a_names = set(manager_a.get_tool_names())
        b_names = set(manager_b.get_tool_names())

        return {
            "common_skills": a_names & b_names,
            "unique_to_a": a_names - b_names,
            "unique_to_b": b_names - a_names
        }


# Backward compatibility alias
SkillManagerOperations = CapabilitiesOperations
