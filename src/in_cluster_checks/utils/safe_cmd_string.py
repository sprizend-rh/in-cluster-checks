"""Safe command template for preventing shell injection."""

import re


class SafeCmdString:
    """Safe command template for preventing shell injection.

    Enforces secure command construction through two mechanisms:
    1. Pre-commit linter: Ensures templates are literal strings (not variables/f-strings/expressions)
    2. Runtime validation: Blocks dangerous shell metacharacters in format() variables

    SAFE patterns:
        SafeCmdString("cat /etc/hostname")                      # Static command
        SafeCmdString("find {path}").format(path="/tmp")        # Template with safe variables
        SafeCmdString("ls {pattern}").format(pattern="*.log")   # Glob patterns allowed

    UNSAFE patterns (blocked by pre-commit linter):
        template = "cat {file}"
        SafeCmdString(template)                                 # Variable - BLOCKED
        SafeCmdString(f"cat {file}")                            # f-string - BLOCKED
        SafeCmdString("cat " + file)                            # Concatenation - BLOCKED
        SafeCmdString("cat {f}".format(f=file))                 # Pre-formatted - BLOCKED
        cmd1, cmd2 = SafeCmdString("a"), SafeCmdString("b")     # Multiple per line - BLOCKED

    Runtime protection (format() method):
        Validates all variables to block dangerous shell metacharacters:
        - Semicolons, pipes, redirects (;|&<>)
        - Quotes, backticks ("'`)
        - Variable expansion ($)
        - Escapes, braces (\\{})
        - Whitespace, exclamation (! space tab newline)

        Safe glob patterns (* ? [ ]) are allowed for file matching.
    """

    def __init__(self, template: str):
        """Initialize with command template.

        Args:
            template: Command template with {placeholder} syntax, or static command
                      MUST be a string literal - pre-commit linter enforces this
        """
        self._template = template

    def format(self, **kwargs):
        """Format template with validated variables.

        Variables are validated to NOT contain dangerous shell metacharacters.
        This allows glob patterns (*, ?, [, ]) while preventing shell injection.

        Blocked characters: ; | & $ ` < > " ' { } \\ ! space tab newline # =

        Args:
            **kwargs: Variables to insert (must not contain dangerous characters)

        Returns:
            SafeCmdString object with formatted command (for type safety)

        Raises:
            ValueError: If value contains dangerous shell metacharacters
        """
        if not kwargs:
            # No variables to format - return self
            return self

        # Block dangerous shell metacharacters
        # Dangerous: command separators, redirects, quotes, escapes, whitespace
        unsafe_pattern = re.compile(r'[;|&$`<>"\'{}\\!\s#=]')

        safe_kwargs = {}
        for key, value in kwargs.items():
            # Allow SafeCmdString instances - already validated by linter
            if isinstance(value, SafeCmdString):
                safe_kwargs[key] = str(value)
                continue

            value_str = str(value).strip() if value else ""

            # Check for dangerous characters
            match = unsafe_pattern.search(value_str)
            if match:
                raise ValueError(
                    f"Parameter '{key}' contains dangerous character: {match.group()!r}. "
                    f"Blocked: ; | & $ ` < > \" ' {{ }} \\ ! space tab newline # =\n"
                    f"Got: {value_str!r}"
                )

            # Use validated value directly (no quoting - it's been validated as safe)
            safe_kwargs[key] = value_str

        # Format template with validated values
        formatted_str = self._template.format(**safe_kwargs)

        # Return new SafeCmdString object (not string!) for type safety
        return SafeCmdString(formatted_str)

    def __str__(self):
        """Return command string."""
        return self._template

    def __repr__(self):
        """Return representation."""
        # Handle edge case where __repr__ is called before _template is set
        template = getattr(self, "_template", "<uninitialized>")
        return f"SafeCmdString({template!r})"
