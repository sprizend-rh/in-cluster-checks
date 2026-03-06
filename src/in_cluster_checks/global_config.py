"""Global configuration for in-cluster checks."""

from profilers.loader import ProfilerLoader
from profilers.profiler import Profilers

# Global configuration values
debug_rule_flag: bool = False
debug_rule_name: str = ""
max_workers: int = 50
profilers_hierarchy = Profilers()
active_profiler: str = ""  # Must be set via set_config() - no default


def set_config(
    active_profiler_val: str,
    debug_rule_flag_val: bool = False,
    debug_rule_name_val: str = "",
    max_workers_val: int = 50,
):
    """Update global configuration values.

    Args:
        active_profiler_val: Active profiler name (required, no default)
        debug_rule_flag_val: Enable debug mode for detailed output
        debug_rule_name_val: Name of specific rule to run in debug mode
        max_workers_val: Maximum number of concurrent workers

    Raises:
        ValueError: If active_profiler_val is not provided or is empty
    """
    global debug_rule_flag, debug_rule_name, max_workers, profilers_hierarchy, active_profiler

    # Validate active_profiler is set
    if not active_profiler_val:
        raise ValueError("active_profiler must be provided and cannot be empty")

    debug_rule_flag = debug_rule_flag_val
    debug_rule_name = debug_rule_name_val
    max_workers = max_workers_val
    active_profiler = active_profiler_val
    ProfilerLoader.load(profilers_hierarchy)

