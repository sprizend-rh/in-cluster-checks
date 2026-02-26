"""Tests for __main__.py module entry point."""

from unittest.mock import patch
import sys


def test_main_module_entry_point():
    """Test that __main__ module calls cli.main() when run as main."""
    with patch('openshift_in_cluster_checks.cli.main') as mock_main:
        # Simulate running as __main__
        with patch.object(sys, 'argv', ['__main__']):
            # Import and execute
            exec(open('src/openshift_in_cluster_checks/__main__.py').read())
            mock_main.assert_called_once()
