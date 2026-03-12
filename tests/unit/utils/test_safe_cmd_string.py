"""Tests for SafeCmdString."""

import pytest

from in_cluster_checks.utils.safe_cmd_string import SafeCmdString


def test_safe_cmd_string_static():
    """Test static command (no placeholders)."""
    cmd = SafeCmdString("cat /etc/hostname")
    assert str(cmd) == "cat /etc/hostname"


def test_safe_cmd_string_format_returns_safe_cmd_string():
    """Test that format() returns SafeCmdString."""
    cmd = SafeCmdString("echo {message}")
    result = cmd.format(message="hello")

    assert isinstance(result, SafeCmdString)
    assert str(result) == "echo hello"


def test_safe_cmd_string_escapes_special_chars():
    """Test that dangerous characters are rejected."""
    cmd = SafeCmdString("find {path}")

    # Semicolons and spaces are dangerous and should be rejected
    with pytest.raises(ValueError) as exc_info:
        cmd.format(path="/tmp; rm -rf /")

    error_msg = str(exc_info.value)
    assert "dangerous character" in error_msg
    assert ";" in error_msg


def test_safe_cmd_string_multiple_vars():
    """Test multiple variables with safe characters."""
    cmd = SafeCmdString("curl --key {key} --cert {cert} {url}")
    result = cmd.format(
        key="/path/key",
        cert="/path/cert",
        url="http://example.com/api"
    )

    # All variables are safe (no dangerous chars)
    result_str = str(result)
    assert result_str == "curl --key /path/key --cert /path/cert http://example.com/api"


def test_safe_cmd_string_format_no_kwargs_returns_self():
    """Test that format() with no kwargs returns self."""
    cmd = SafeCmdString("cat /etc/hostname")
    result = cmd.format()

    assert result is cmd


def test_safe_cmd_string_spaces_in_value():
    """Test that values with spaces are rejected."""
    cmd = SafeCmdString("echo {message}")

    # Spaces are dangerous and should be rejected
    with pytest.raises(ValueError) as exc_info:
        cmd.format(message="hello world")

    error_msg = str(exc_info.value)
    assert "dangerous character" in error_msg


def test_safe_cmd_string_empty_value():
    """Test that empty values are handled."""
    cmd = SafeCmdString("cmd {arg}")
    result = cmd.format(arg="")

    result_str = str(result)
    # Empty string is inserted as-is (no quoting needed)
    assert result_str == "cmd "


@pytest.mark.parametrize(
    "dangerous_char,test_value",
    [
        (";", "test;rm"),
        ("|", "test|cat"),
        ("&", "test&"),
        ("$", "test$VAR"),
        ("`", "test`cmd`"),
        ("<", "test<file"),
        (">", "test>file"),
        ('"', 'test"quoted'),
        ("'", "test'quoted"),
        ("{", "test{brace"),
        ("}", "test}brace"),
        ("\\", "test\\escape"),
        ("!", "test!"),
        (" ", "test value"),
        ("\t", "test\tvalue"),
        ("\n", "test\nvalue"),
        ("#", "test#comment"),
        ("=", "test=value"),
    ],
)
def test_safe_cmd_string_blocks_dangerous_characters(dangerous_char, test_value):
    """Test that all dangerous shell metacharacters are blocked."""
    cmd = SafeCmdString("echo {value}")

    with pytest.raises(ValueError) as exc_info:
        cmd.format(value=test_value)

    error_msg = str(exc_info.value)
    assert "dangerous character" in error_msg.lower()
    assert dangerous_char in error_msg or repr(dangerous_char) in error_msg


def test_safe_cmd_string_repr():
    """Test repr output."""
    cmd = SafeCmdString("test command")
    assert repr(cmd) == "SafeCmdString('test command')"


def test_safe_cmd_string_pipeline():
    """Test command with pipe (literal, not placeholder)."""
    # Pipe is part of static command, not a placeholder
    cmd = SafeCmdString("cat /proc/meminfo | grep HugePages")
    assert str(cmd) == "cat /proc/meminfo | grep HugePages"


def test_safe_cmd_string_with_env_vars():
    """Test command with environment variables (not placeholders)."""
    # $VAR is part of static command, will be expanded by shell
    cmd = SafeCmdString("curl --key $ETCDCTL_KEY {url}")
    result = cmd.format(url="http://example.com")

    result_str = str(result)
    assert "$ETCDCTL_KEY" in result_str  # Env var preserved
    assert "http://example.com" in result_str  # URL inserted


def test_runtime_internal_format_call_allowed():
    """Internal calls from format() should be allowed."""
    # This should not raise - format() internally creates SafeCmdString
    cmd = SafeCmdString("echo {msg}")
    result = cmd.format(msg="test")

    assert isinstance(result, SafeCmdString)
    assert str(result) == "echo test"


def test_runtime_multiline_literal_allowed():
    """Multiline literal strings should be allowed."""
    cmd = SafeCmdString(
        "cat /etc/hostname"
    )
    assert str(cmd) == "cat /etc/hostname"


def test_runtime_injection_escaping():
    """Injection attempts should be rejected."""
    cmd = SafeCmdString("cat {file}")

    # Dangerous characters should be rejected, not escaped
    with pytest.raises(ValueError) as exc_info:
        cmd.format(file="; rm -rf /")

    error_msg = str(exc_info.value)
    assert "dangerous character" in error_msg
    assert ";" in error_msg


def test_safe_cmd_string_glob_patterns():
    """Test that glob patterns work (not quoted)."""
    cmd = SafeCmdString("ls {pattern}")
    result = cmd.format(pattern="/sys/class/thermal/thermal_zone*/temp")

    result_str = str(result)
    # Glob should NOT be quoted (allows shell expansion)
    assert result_str == "ls /sys/class/thermal/thermal_zone*/temp"
    assert "'" not in result_str  # No quotes


def test_safe_cmd_string_multiple_glob_wildcards():
    """Test various glob wildcards are allowed."""
    cmd = SafeCmdString("find {path} -name {pattern}")
    result = cmd.format(
        path="/var/log",
        pattern="*.log"
    )

    result_str = str(result)
    assert result_str == "find /var/log -name *.log"


def test_safe_cmd_string_bracket_globs():
    """Test bracket globs are allowed."""
    cmd = SafeCmdString("ls {pattern}")
    result = cmd.format(pattern="/etc/[a-z]*.conf")

    result_str = str(result)
    assert result_str == "ls /etc/[a-z]*.conf"


def test_safe_cmd_string_question_mark_glob():
    """Test question mark glob is allowed."""
    cmd = SafeCmdString("ls {pattern}")
    result = cmd.format(pattern="/tmp/file?.txt")

    result_str = str(result)
    assert result_str == "ls /tmp/file?.txt"


def test_safe_cmd_string_composition():
    """Test that SafeCmdString can be composed with other SafeCmdStrings."""
    # Create inner command
    inner_cmd = SafeCmdString("ceph health")

    # Compose with outer command
    result = SafeCmdString("{cmd} -c {conf}").format(
        cmd=inner_cmd,
        conf="/var/lib/rook/openshift-storage/openshift-storage.config"
    )

    result_str = str(result)
    assert result_str == "ceph health -c /var/lib/rook/openshift-storage/openshift-storage.config"
    assert isinstance(result, SafeCmdString)


def test_safe_cmd_string_composition_mixed():
    """Test composition with both SafeCmdString and regular parameters."""
    base_cmd = SafeCmdString("echo {message}")
    formatted_cmd = base_cmd.format(message="hello")

    # Compose formatted command with additional args
    result = SafeCmdString("{cmd} > {output}").format(
        cmd=formatted_cmd,
        output="/tmp/output.txt"
    )

    result_str = str(result)
    assert result_str == "echo hello > /tmp/output.txt"
