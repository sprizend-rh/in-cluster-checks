"""Unit tests for profilers module."""

import tempfile
from pathlib import Path

import pytest
import yaml

from src.profilers.loader import ProfilerLoader
from src.profilers.profiler import Profilers


@pytest.fixture
def mock_profilers_yaml():
    """Create a mock profilers.yaml file for testing.

    Structure:
    - general: base level (no dependencies)
    - telco: includes general, rh-nokia, telco-base
    - rh-nokia: includes general, telco-base
    - telco-base: includes general
    - ai: includes ai-base, gpu, general
    - ai-base: includes general
    - gpu: includes general
    - nvidia: includes ai, general
    """
    config = {
        "profilers": {
            "general": None,
            "telco": {
                "include": ["general", "rh-nokia", "telco-base"]
            },
            "rh-nokia": {
                "include": ["general", "telco-base"]
            },
            "telco-base": {
                "include": ["general"]
            },
            "ai": {
                "include": ["ai-base", "gpu"]
            },
            "ai-base": {
                "include": ["general"]
            },
            "gpu": {
                "include": ["general"]
            },
            "nvidia": {
                "include": ["ai", "general"]
            },
        }
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config, f)
        temp_path = f.name

    yield temp_path

    # Cleanup
    Path(temp_path).unlink()


class TestProfilerLoader:
    """Test ProfilerLoader functionality."""

    def test_general_is_base_profiler(self, mock_profilers_yaml):
        """Test that 'general' profiler is the base with no dependencies."""
        profiler = Profilers()
        ProfilerLoader.load(profiler, mock_profilers_yaml)

        # General should only include itself (no other dependencies)
        general_includes = profiler["general"]
        assert general_includes == {"general"}, (
            f"'general' profiler should only include itself. "
            f"Got: {sorted(general_includes)}"
        )

        # Verify all profilers include themselves and general (directly or transitively)
        for profiler_name in profiler.keys():
            profiler_includes = profiler[profiler_name]
            assert profiler_name in profiler_includes, (
                f"Profiler '{profiler_name}' should include itself. "
                f"Includes: {sorted(profiler_includes)}"
            )
            assert "general" in profiler_includes, (
                f"Profiler '{profiler_name}' should include 'general'. "
                f"Includes: {sorted(profiler_includes)}"
            )

    def test_recursion_3_levels(self, mock_profilers_yaml):
        """Test that recursion works up to 3 levels deep.

        Example path: telco -> rh-nokia -> telco-base -> general
        """
        profiler = Profilers()
        ProfilerLoader.load(profiler, mock_profilers_yaml)

        # Test 'telco' resolved dependencies
        telco_deps = profiler["telco"]
        assert "general" in telco_deps  # Direct include
        assert "rh-nokia" in telco_deps  # Direct include
        assert "telco-base" in telco_deps  # Transitive (via rh-nokia)

        # Test 'rh-nokia' resolved dependencies
        rh_nokia_deps = profiler["rh-nokia"]
        assert "general" in rh_nokia_deps  # Direct include
        assert "telco-base" in rh_nokia_deps  # Direct include

        # Test 'telco-base' resolved dependencies
        telco_base_deps = profiler["telco-base"]
        assert "general" in telco_base_deps  # Direct include
        assert "telco-base" in telco_base_deps  # Includes itself
        assert len(telco_base_deps) == 2  # Includes general and itself

        # Test 'general' only includes itself
        general_deps = profiler["general"]
        assert general_deps == {"general"}  # Only includes itself

    def test_non_existent_profiler_raises_exception(self, mock_profilers_yaml):
        """Test that accessing a non-existent profiler raises KeyError."""
        profiler = Profilers()
        ProfilerLoader.load(profiler, mock_profilers_yaml)

        with pytest.raises(KeyError) as exc_info:
            _ = profiler["non_existent_profiler"]

        error_message = str(exc_info.value)
        assert "non_existent_profiler" in error_message
        assert "not found" in error_message
        assert "Available profilers" in error_message

    def test_circular_dependency_detection(self):
        """Test that circular dependencies are detected and raise ValueError."""
        config = {
            "profilers": {
                "a": {"include": ["b"]},
                "b": {"include": ["c"]},
                "c": {"include": ["a"]},  # Creates cycle: a -> b -> c -> a
            }
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config, f)
            temp_path = f.name

        try:
            profiler = Profilers()
            with pytest.raises(ValueError) as exc_info:
                ProfilerLoader.load(profiler, temp_path)

            error_message = str(exc_info.value)
            assert "Circular dependency" in error_message
        finally:
            Path(temp_path).unlink()

    def test_missing_dependency_raises_exception(self):
        """Test that referencing undefined profiler raises KeyError."""
        config = {
            "profilers": {
                "valid": {"include": ["undefined_profiler"]},
            }
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config, f)
            temp_path = f.name

        try:
            profiler = Profilers()
            with pytest.raises(KeyError) as exc_info:
                ProfilerLoader.load(profiler, temp_path)

            error_message = str(exc_info.value)
            assert "undefined_profiler" in error_message
        finally:
            Path(temp_path).unlink()

    def test_empty_profiler_has_no_dependencies(self, mock_profilers_yaml):
        """Test that profiler with no includes only includes itself."""
        profiler = Profilers()
        ProfilerLoader.load(profiler, mock_profilers_yaml)

        general_deps = profiler["general"]
        assert general_deps == {"general"}
        assert len(general_deps) == 1

    def test_transitive_dependencies_no_duplicates(self, mock_profilers_yaml):
        """Test that transitive dependencies don't create duplicates.

        Example: 'ai' includes both 'ai-base' and 'gpu', and both include 'general'.
        'general' should only appear once in the resolved set.
        """
        profiler = Profilers()
        ProfilerLoader.load(profiler, mock_profilers_yaml)

        ai_deps = profiler["ai"]

        # Count how many times 'general' appears (should be 1)
        general_count = list(ai_deps).count("general")
        assert general_count == 1, "Transitive dependencies should not create duplicates"

        # Verify ai includes itself, ai-base, gpu, and general (transitively)
        assert "ai" in ai_deps  # Includes itself
        assert "ai-base" in ai_deps
        assert "gpu" in ai_deps
        assert "general" in ai_deps
        assert len(ai_deps) == 4

    def test_get_available_profilers(self, mock_profilers_yaml):
        """Test getting list of available profilers without resolution."""
        available = ProfilerLoader.get_available_profilers(mock_profilers_yaml)

        # Should return sorted list of profiler names
        assert isinstance(available, list)
        assert available == sorted(available)  # Verify it's sorted

        # Should contain all profilers from the mock YAML
        expected_profilers = ['ai', 'ai-base', 'general', 'gpu', 'nvidia', 'rh-nokia', 'telco', 'telco-base']
        assert available == expected_profilers


class TestRuleProfilerEnablement:
    """Test Rule.is_enabled_for_active_profiler() functionality."""

    @pytest.fixture
    def rule_profilers_yaml(self):
        """Create a mock profilers.yaml file for rule enablement testing.

        Structure (independent copy to avoid coupling with real profilers.yaml):
        - general: base level (no dependencies)
        - telco: includes general, rh-nokia, telco-base
        - rh-nokia: includes general, telco-base
        - telco-base: includes general
        - ai: includes ai-base, gpu
        - ai-base: includes general
        - gpu: includes general
        - nvidia: includes ai, general
        """
        config = {
            "profilers": {
                "general": None,
                "telco": {
                    "include": ["general", "rh-nokia", "telco-base"]
                },
                "rh-nokia": {
                    "include": ["general", "telco-base"]
                },
                "telco-base": {
                    "include": ["general"]
                },
                "ai": {
                    "include": ["ai-base", "gpu"]
                },
                "ai-base": {
                    "include": ["general"]
                },
                "gpu": {
                    "include": ["general"]
                },
                "nvidia": {
                    "include": ["ai", "general"]
                },
            }
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config, f)
            temp_path = f.name

        yield temp_path

        # Cleanup
        Path(temp_path).unlink()

    @pytest.fixture
    def loaded_profilers(self, rule_profilers_yaml):
        """Load profilers for testing."""
        from in_cluster_checks import global_config

        profiler = Profilers()
        ProfilerLoader.load(profiler, rule_profilers_yaml)
        global_config.profilers_hierarchy = profiler
        global_config.active_profiler = "general"
        return profiler

    def test_default_rule_runs_for_all_profilers(self, loaded_profilers):
        """Test that default rule (supported_profilers={'general'}) runs for all profilers."""
        from in_cluster_checks import global_config
        from in_cluster_checks.core.rule import Rule

        class DefaultRule(Rule):
            title = "Default Rule"
            supported_profilers = {'general'}

            def run_rule(self):
                pass

        # Default rule should run for all profilers since all include 'general'
        for profiler_name in loaded_profilers.keys():
            global_config.active_profiler = profiler_name
            assert DefaultRule.is_enabled_for_active_profiler() is True, (
                f"Default rule should run for '{profiler_name}' profiler"
            )

    def test_nvidia_rule_only_runs_for_nvidia_ai(self, loaded_profilers):
        """Test that nvidia-specific rule only runs for nvidia/ai profilers."""
        from in_cluster_checks import global_config
        from in_cluster_checks.core.rule import Rule

        class NvidiaRule(Rule):
            title = "Nvidia Rule"
            supported_profilers = {'nvidia', 'ai'}

            def run_rule(self):
                pass

        # Should run for nvidia and ai
        for profiler_name in ['nvidia', 'ai']:
            global_config.active_profiler = profiler_name
            assert NvidiaRule.is_enabled_for_active_profiler() is True, (
                f"Nvidia rule should run for '{profiler_name}' profiler"
            )

        # Should NOT run for general or telco
        for profiler_name in ['general', 'telco', 'rh-nokia']:
            global_config.active_profiler = profiler_name
            assert NvidiaRule.is_enabled_for_active_profiler() is False, (
                f"Nvidia rule should NOT run for '{profiler_name}' profiler"
            )

    def test_telco_rule_only_runs_for_telco(self, loaded_profilers):
        """Test that telco-specific rule only runs for telco profilers."""
        from in_cluster_checks import global_config
        from in_cluster_checks.core.rule import Rule

        class TelcoRule(Rule):
            title = "Telco Rule"
            supported_profilers = {'telco'}

            def run_rule(self):
                pass

        # Should run for telco
        global_config.active_profiler = 'telco'
        assert TelcoRule.is_enabled_for_active_profiler() is True

        # Should NOT run for general, nvidia, or rh-nokia
        for profiler_name in ['general', 'nvidia', 'rh-nokia', 'ai']:
            global_config.active_profiler = profiler_name
            assert TelcoRule.is_enabled_for_active_profiler() is False, (
                f"Telco rule should NOT run for '{profiler_name}' profiler"
            )

    def test_multi_profiler_rule(self, loaded_profilers):
        """Test rule that supports multiple profilers."""
        from in_cluster_checks import global_config
        from in_cluster_checks.core.rule import Rule

        class MultiRule(Rule):
            title = "Multi Profiler Rule"
            supported_profilers = {'ai-base', 'gpu', 'telco-base'}

            def run_rule(self):
                pass

        # Should run for profilers that include ai-base, gpu, or telco-base
        test_cases = {
            'ai': True,        # includes ai-base and gpu
            'gpu': True,       # includes gpu
            'nvidia': True,    # includes ai-base and gpu
            'telco': True,     # includes telco-base
            'rh-nokia': True,  # includes telco-base
            'general': False,  # doesn't include any of the supported profilers
        }

        for profiler_name, should_run in test_cases.items():
            global_config.active_profiler = profiler_name
            result = MultiRule.is_enabled_for_active_profiler()
            assert result is should_run, (
                f"Multi rule should {'run' if should_run else 'NOT run'} "
                f"for '{profiler_name}' profiler (got {result})"
            )

    def test_transitive_inclusion(self, loaded_profilers):
        """Test that rules work with transitive profiler inclusion."""
        from in_cluster_checks import global_config
        from in_cluster_checks.core.rule import Rule

        class TelcoBaseRule(Rule):
            title = "Telco Base Rule"
            supported_profilers = {'telco-base'}

            def run_rule(self):
                pass

        # telco-base is transitively included by telco and rh-nokia
        for profiler_name in ['telco', 'rh-nokia', 'telco-base']:
            global_config.active_profiler = profiler_name
            assert TelcoBaseRule.is_enabled_for_active_profiler() is True, (
                f"Telco-base rule should run for '{profiler_name}' profiler "
                "(telco-base is included transitively)"
            )

        # Should NOT run for ai/nvidia/general
        for profiler_name in ['general', 'ai', 'nvidia']:
            global_config.active_profiler = profiler_name
            assert TelcoBaseRule.is_enabled_for_active_profiler() is False, (
                f"Telco-base rule should NOT run for '{profiler_name}' profiler"
            )


class TestGlobalConfig:
    """Test global_config.set_config() functionality."""

    def test_set_config_requires_active_profiler(self):
        """Test that set_config() raises ValueError when active_profiler is empty."""
        from in_cluster_checks import global_config

        with pytest.raises(ValueError) as exc_info:
            global_config.set_config(active_profiler_val="")

        error_message = str(exc_info.value)
        assert "active_profiler" in error_message
        assert "cannot be empty" in error_message

    def test_set_config_with_valid_profiler(self):
        """Test that set_config() works correctly with a valid profiler."""
        from in_cluster_checks import global_config

        # Should not raise any exception
        global_config.set_config(active_profiler_val="general")

        # Verify values are set
        assert global_config.active_profiler == "general"
        assert len(global_config.profilers_hierarchy) > 0
        assert "general" in global_config.profilers_hierarchy

    def test_set_config_with_custom_profiler(self):
        """Test that set_config() works with different profiler values."""
        from in_cluster_checks import global_config

        # Test with nvidia profiler
        global_config.set_config(active_profiler_val="nvidia")
        assert global_config.active_profiler == "nvidia"

        # Test with telco profiler
        global_config.set_config(active_profiler_val="telco")
        assert global_config.active_profiler == "telco"
