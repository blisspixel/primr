"""
Property-based tests for the agentic architecture.

This package contains property-based tests using the Hypothesis library.
Each test file corresponds to a component and validates universal
correctness properties.

Property tests complement unit tests by:
- Testing across the entire input space (not just examples)
- Finding edge cases automatically through shrinking
- Providing reproducible counterexamples

Test files:
- test_memory_properties.py: Properties 9-12 (Research Memory)
- test_roadmap_properties.py: Properties 1-4 (Roadmap API)
- test_hook_properties.py: Properties 6-8 (Hook System)
- test_orchestrator_properties.py: Properties 13-15 (Orchestrator)
"""
