"""Reusable multi-agent framework (Phase 12A).

Layers: Profile → Prompt → Capabilities → Permissions → Memory → Tool Registry →
Execution → Validation → Result. Agents are declarative; the generic BaseAgent
runs them. Agents NEVER touch repositories/services directly — only via the
Tool Registry, which enforces owner-scoping and permissions.
"""
