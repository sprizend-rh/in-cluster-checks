"""Global configuration for in-cluster checks."""

# Global configuration values
debug_rule_flag: bool = False
debug_rule_name: str = ""
filter_secrets: bool = True
max_workers: int = 50


def set_config(
    debug_rule_flag_val: bool = False,
    debug_rule_name_val: str = "",
    filter_secrets_val: bool = True,
    max_workers_val: int = 50,
):
    """Update global configuration values."""
    global debug_rule_flag, debug_rule_name, filter_secrets, max_workers
    debug_rule_flag = debug_rule_flag_val
    debug_rule_name = debug_rule_name_val
    filter_secrets = filter_secrets_val
    max_workers = max_workers_val
