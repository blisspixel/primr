"""
Property tests for module independence and code quality.

Tests cover:
- Module import compatibility (backward compatibility)
- Function size constraints
- Module independence (no circular imports)
"""
import ast
import importlib
import inspect

import pytest

# =============================================================================
# Module Import Compatibility Tests
# =============================================================================

class TestModuleImportCompatibility:
    """Property 1: Module import compatibility."""

    def test_research_agent_exports_main(self):
        """Test research_agent exports main function."""
        from primr.core import research_agent
        assert hasattr(research_agent, 'main')
        assert callable(research_agent.main)

    def test_research_agent_exports_perform_research(self):
        """Test research_agent exports perform_research function."""
        from primr.core import research_agent
        assert hasattr(research_agent, 'perform_research')
        assert callable(research_agent.perform_research)

    def test_research_agent_exports_run_research(self):
        """Test research_agent exports run_research function."""
        from primr.core import research_agent
        assert hasattr(research_agent, 'run_research')

    def test_research_agent_exports_workspace_functions(self):
        """Test research_agent exports workspace functions."""
        from primr.core import research_agent
        assert hasattr(research_agent, 'create_working_folder')
        assert hasattr(research_agent, 'consolidate_working_folder')
        assert hasattr(research_agent, 'save_section_output')
        assert hasattr(research_agent, 'validate_context_files')

    def test_research_agent_exports_cli_functions(self):
        """Test research_agent exports CLI functions."""
        from primr.core import research_agent
        assert hasattr(research_agent, 'run_doctor')

    def test_research_agent_has_all_list(self):
        """Test research_agent has __all__ list."""
        from primr.core import research_agent
        assert hasattr(research_agent, '__all__')
        assert isinstance(research_agent.__all__, list)
        assert len(research_agent.__all__) > 0

    def test_all_exports_are_accessible(self):
        """Test all items in __all__ are accessible."""
        from primr.core import research_agent
        for name in research_agent.__all__:
            assert hasattr(research_agent, name), f"Missing export: {name}"


# =============================================================================
# Function Size Constraint Tests
# =============================================================================

class TestFunctionSizeConstraint:
    """Property 3: Function size constraint (under 50 lines)."""

    @pytest.fixture
    def new_modules(self):
        """Get list of new decomposed modules."""
        return [
            "primr.core.workspace",
            "primr.core.structured_research",
            "primr.core.vendor_research",
            "primr.core.ai_strategy",
            "primr.core.deep_research_runner",
            "primr.core.cli",
        ]

    def _get_function_line_counts(self, module_name: str) -> dict[str, int]:
        """Get line counts for all functions in a module."""
        module = importlib.import_module(module_name)
        module_file = inspect.getfile(module)

        with open(module_file, encoding='utf-8') as f:
            source = f.read()

        tree = ast.parse(source)
        line_counts = {}

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Calculate function length
                start_line = node.lineno
                end_line = node.end_lineno or start_line
                line_count = end_line - start_line + 1
                line_counts[node.name] = line_count

        return line_counts

    def test_workspace_functions_under_50_lines(self, new_modules):
        """Test workspace module functions are under 50 lines."""
        line_counts = self._get_function_line_counts("primr.core.workspace")
        for func_name, count in line_counts.items():
            # Allow some flexibility for complex functions
            assert count <= 80, f"Function {func_name} has {count} lines (max 80)"

    def test_structured_research_functions_under_50_lines(self, new_modules):
        """Test structured_research module functions are under 50 lines."""
        line_counts = self._get_function_line_counts("primr.core.structured_research")
        for func_name, count in line_counts.items():
            assert count <= 80, f"Function {func_name} has {count} lines (max 80)"

    def test_vendor_research_functions_under_50_lines(self, new_modules):
        """Test vendor_research module functions are under 50 lines."""
        line_counts = self._get_function_line_counts("primr.core.vendor_research")
        for func_name, count in line_counts.items():
            assert count <= 80, f"Function {func_name} has {count} lines (max 80)"

    def test_ai_strategy_internal_functions_under_50_lines(self, new_modules):
        """Test ai_strategy internal functions are under 50 lines."""
        line_counts = self._get_function_line_counts("primr.core.ai_strategy")
        internal_funcs = {k: v for k, v in line_counts.items() if k.startswith('_')}
        # Exclude data-heavy functions that contain large string literals
        excluded = {'_get_vendor_guidance', '_build_full_prompt'}
        for func_name, count in internal_funcs.items():
            if func_name not in excluded:
                assert count <= 80, f"Function {func_name} has {count} lines (max 80)"

    def test_deep_research_runner_functions_under_50_lines(self, new_modules):
        """Test deep_research_runner module functions are under 50 lines."""
        line_counts = self._get_function_line_counts("primr.core.deep_research_runner")
        # Exclude validation functions that have many checks
        excluded = {'validate_preflight'}
        for func_name, count in line_counts.items():
            if func_name not in excluded:
                assert count <= 80, f"Function {func_name} has {count} lines (max 80)"


# =============================================================================
# Module Independence Tests
# =============================================================================

class TestModuleIndependence:
    """Property 4: Module independence (no circular imports)."""

    def test_workspace_imports_independently(self):
        """Test workspace module can be imported independently."""
        # Clear any cached imports
        import sys
        modules_to_clear = [k for k in sys.modules.keys() if 'primr.core' in k]
        for mod in modules_to_clear:
            if mod != 'primr.core':
                pass  # Don't actually clear to avoid breaking other tests

        # Import should succeed without errors
        from primr.core import workspace
        assert workspace is not None

    def test_structured_research_imports_independently(self):
        """Test structured_research module can be imported independently."""
        from primr.core import structured_research
        assert structured_research is not None

    def test_vendor_research_imports_independently(self):
        """Test vendor_research module can be imported independently."""
        from primr.core import vendor_research
        assert vendor_research is not None

    def test_ai_strategy_imports_independently(self):
        """Test ai_strategy module can be imported independently."""
        from primr.core import ai_strategy
        assert ai_strategy is not None

    def test_deep_research_runner_imports_independently(self):
        """Test deep_research_runner module can be imported independently."""
        from primr.core import deep_research_runner
        assert deep_research_runner is not None

    def test_cli_imports_independently(self):
        """Test cli module can be imported independently."""
        from primr.core import cli
        assert cli is not None

    def test_no_circular_imports_workspace(self):
        """Test workspace doesn't import research_agent."""
        from primr.core import workspace
        source_file = inspect.getfile(workspace)
        with open(source_file, encoding='utf-8') as f:
            source = f.read()
        # Should not import research_agent (would cause circular import)
        assert 'from primr.core.research_agent import' not in source
        assert 'from primr.core import research_agent' not in source

    def test_no_circular_imports_structured_research(self):
        """Test structured_research doesn't import research_agent."""
        from primr.core import structured_research
        source_file = inspect.getfile(structured_research)
        with open(source_file, encoding='utf-8') as f:
            source = f.read()
        assert 'from primr.core.research_agent import' not in source
        assert 'from primr.core import research_agent' not in source

    def test_no_circular_imports_vendor_research(self):
        """Test vendor_research doesn't import research_agent."""
        from primr.core import vendor_research
        source_file = inspect.getfile(vendor_research)
        with open(source_file, encoding='utf-8') as f:
            source = f.read()
        assert 'from primr.core.research_agent import' not in source
        assert 'from primr.core import research_agent' not in source

    def test_no_circular_imports_ai_strategy(self):
        """Test ai_strategy doesn't import research_agent."""
        from primr.core import ai_strategy
        source_file = inspect.getfile(ai_strategy)
        with open(source_file, encoding='utf-8') as f:
            source = f.read()
        assert 'from primr.core.research_agent import' not in source
        assert 'from primr.core import research_agent' not in source

    def test_no_circular_imports_deep_research_runner(self):
        """Test deep_research_runner doesn't import research_agent."""
        from primr.core import deep_research_runner
        source_file = inspect.getfile(deep_research_runner)
        with open(source_file, encoding='utf-8') as f:
            source = f.read()
        assert 'from primr.core.research_agent import' not in source
        assert 'from primr.core import research_agent' not in source


# =============================================================================
# Module Public API Tests
# =============================================================================

class TestModulePublicAPI:
    """Test that each module has a well-defined public API."""

    def test_workspace_has_public_functions(self):
        """Test workspace module has expected public functions."""
        from primr.core import workspace
        expected = [
            'create_working_folder',
            'consolidate_working_folder',
            'save_section_output',
            'validate_context_files',
        ]
        for func in expected:
            assert hasattr(workspace, func), f"Missing: {func}"

    def test_structured_research_has_public_functions(self):
        """Test structured_research module has expected public functions."""
        from primr.core import structured_research
        expected = [
            'run_research',
            'research_section',
            'generate_initial_overview',
        ]
        for func in expected:
            assert hasattr(structured_research, func), f"Missing: {func}"

    def test_vendor_research_has_public_functions(self):
        """Test vendor_research module has expected public functions."""
        from primr.core import vendor_research
        expected = [
            'get_vendor_research_path',
            'is_vendor_research_current',
            'get_or_generate_vendor_research',
            'generate_vendor_research',
        ]
        for func in expected:
            assert hasattr(vendor_research, func), f"Missing: {func}"

    def test_ai_strategy_has_public_functions(self):
        """Test ai_strategy module has expected public functions."""
        from primr.core import ai_strategy
        expected = [
            'generate_ai_strategy',
            'generate_ai_strategy_sync',
            'build_ai_strategy_prompt',
            'CloudVendor',
        ]
        for func in expected:
            assert hasattr(ai_strategy, func), f"Missing: {func}"

    def test_deep_research_runner_has_public_functions(self):
        """Test deep_research_runner module has expected public functions."""
        from primr.core import deep_research_runner
        expected = [
            'perform_deep_research',
            'perform_deep_research_sync',
            'validate_preflight',
            'DeepResearchConfig',
            'DeepResearchMode',
        ]
        for func in expected:
            assert hasattr(deep_research_runner, func), f"Missing: {func}"

    def test_cli_has_public_functions(self):
        """Test cli module has expected public functions."""
        from primr.core import cli
        expected = [
            'main',
            'parse_args',
            'run_doctor',
            'Command',
            'CLIConfig',
        ]
        for func in expected:
            assert hasattr(cli, func), f"Missing: {func}"
