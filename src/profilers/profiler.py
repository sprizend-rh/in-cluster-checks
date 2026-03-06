"""Profilers configuration for managing rule dependencies."""

import json


class Profilers(dict):
    """Profilers configuration mapping profiler names to their included dependencies.

    Inherits from dict[str, set[str]] where:
    - key: profiler name
    - value: set of all transitive dependencies (flat, fully resolved)

    Dependencies are resolved at load time by ProfilerLoader, which flattens
    the dependency tree and detects circular dependencies.
    """

    def __getitem__(self, key: str) -> set:
        """Get profiler dependencies with helpful error message.

        Args:
            key: Profiler name.

        Returns:
            Set of all transitive dependencies.

        Raises:
            KeyError: If profiler doesn't exist, with list of available profilers.
        """
        if key not in self:
            available = self.format_profilers()
            raise KeyError(
                f"Profiler '{key}' not found.\n\n"
                f"Available profilers:\n{available}"
            )
        return super().__getitem__(key)

    def format_profilers(self) -> str:
        """Format profilers as a JSON-formatted dict representation.

        Returns:
            JSON-formatted string representation of the profiler dict.
        """
        if not self:
            return "{}"

        # Convert sets to sorted lists for JSON serialization
        regular_dict = {
            name: sorted(super().__getitem__(name))
            for name in sorted(self.keys())
        }
        return json.dumps(regular_dict, indent=4)

    def __str__(self) -> str:
        """Return formatted string representation."""
        return self.format_profilers()

    def __repr__(self) -> str:
        """Return detailed representation."""
        return f"<Profilers with {len(self)} profiler(s)>"
