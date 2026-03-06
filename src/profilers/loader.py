"""Profilers configuration loader and dependency resolver."""

from pathlib import Path

import yaml

from .profiler import Profilers

class ProfilerLoader:
    """Load profiler configurations from YAML into a Profilers instance."""

    @staticmethod
    def _resolve_and_populate(profilers_instance: Profilers, raw_profilers: dict) -> None:
        """Resolve all dependencies and populate the profilers instance with flat sets.

        Args:
            profilers_instance: Profilers instance to populate.
            raw_profilers: Dictionary of profiler configurations from YAML.

        Raises:
            ValueError: If circular dependency detected.
        """
        # First pass: populate with direct includes
        direct_includes = {}
        for name, config in raw_profilers.items():
            if config is None:
                direct_includes[name] = set()
            else:
                includes = config.get("include", [])
                direct_includes[name] = set(includes)

        # Second pass: resolve all transitive dependencies
        profilers_instance.clear()
        for name in direct_includes:
            resolved = ProfilerLoader._resolve_recursive(name, direct_includes, set(), [])
            resolved.add(name)  # Add the profiler itself to its includes
            profilers_instance[name] = resolved

    @staticmethod
    def _resolve_recursive(
        name: str,
        direct_includes: dict,
        visiting: set,
        path: list,
    ) -> set:
        """Recursively resolve all dependencies for a profiler.

        Args:
            name: Profiler name to resolve.
            direct_includes: Dictionary mapping profiler names to their direct includes.
            visiting: Set of profilers currently being visited (for cycle detection).
            path: Current path in the dependency graph (for error messages).

        Returns:
            Set of all transitive dependencies (not including the profiler itself).

        Raises:
            ValueError: If circular dependency detected.
            KeyError: If profiler references undefined dependency.
        """
        if name in visiting:
            cycle = " -> ".join(path + [name])
            raise ValueError(f"Circular dependency detected: {cycle}")

        if name not in direct_includes:
            raise KeyError(f"Profiler not found: {name}")

        visiting.add(name)
        resolved = set()

        for include in direct_includes[name]:
            resolved.add(include)
            sub_resolved = ProfilerLoader._resolve_recursive(
                include, direct_includes, visiting, path + [name]
            )
            resolved.update(sub_resolved)

        visiting.remove(name)
        return resolved

    @staticmethod
    def load(profilers_instance: Profilers, config_path: str | None = None) -> None:
        """Load profiler configuration from YAML file into the provided Profilers instance.

        Args:
            profilers_instance: Profilers instance to populate.
            config_path: Path to profilers.yaml. If None, uses default location.

        Raises:
            FileNotFoundError: If config file doesn't exist.
            ValueError: If circular dependency detected.
        """
        if config_path is None:
            config_path = Path(__file__).parent / "profilers.yaml"
        else:
            config_path = Path(config_path)

        if not config_path.exists():
            raise FileNotFoundError(f"Profiler config not found: {config_path}")

        with open(config_path, "r") as f:
            data = yaml.safe_load(f)
            raw_profilers = data.get("profilers", {})

        ProfilerLoader._resolve_and_populate(profilers_instance, raw_profilers)

    @staticmethod
    def get_available_profilers(config_path: str | None = None) -> list[str]:
        """Get list of available profiler names from YAML configuration.

        This method returns profiler names without resolving dependencies.
        Useful for listing available profilers for UI/CLI selection.

        Args:
            config_path: Path to profilers.yaml. If None, uses default location.

        Returns:
            Sorted list of available profiler names.

        Raises:
            FileNotFoundError: If config file doesn't exist.

        Example:
            >>> ProfilerLoader.get_available_profilers()
            ['ai', 'ai-base', 'general', 'gpu', 'nvidia', 'rh-nokia', 'telco', 'telco-base']
        """
        if config_path is None:
            config_path = Path(__file__).parent / "profilers.yaml"
        else:
            config_path = Path(config_path)

        if not config_path.exists():
            raise FileNotFoundError(f"Profiler config not found: {config_path}")

        with open(config_path, "r") as f:
            data = yaml.safe_load(f)
            raw_profilers = data.get("profilers", {})

        return sorted(raw_profilers.keys())
