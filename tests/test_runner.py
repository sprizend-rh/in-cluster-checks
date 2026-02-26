"""Tests for runner.py - InClusterCheckRunner class."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from openshift_in_cluster_checks.interfaces.config import InClusterCheckConfig
from openshift_in_cluster_checks.runner import InClusterCheckRunner


class TestInClusterCheckRunner:
    """Test InClusterCheckRunner class."""

    def test_init_default_config(self):
        """Test runner initialization with default config."""
        runner = InClusterCheckRunner()

        assert runner.config is not None
        assert isinstance(runner.config, InClusterCheckConfig)
        assert runner.config.parallel_execution is True
        assert runner.config.filter_secrets is True

    def test_init_custom_config(self):
        """Test runner initialization with custom config."""
        custom_config = InClusterCheckConfig(
            parallel_execution=False,
            max_workers=5,
            command_timeout=60,
            filter_secrets=False,
        )

        runner = InClusterCheckRunner(config=custom_config)

        assert runner.config == custom_config
        assert runner.config.parallel_execution is False
        assert runner.config.max_workers == 5

    @patch('openshift_in_cluster_checks.runner.ParallelRunner')
    @patch('openshift_in_cluster_checks.runner.ExecutorFactory')
    def test_run_success(self, mock_executor_factory, mock_parallel_runner):
        """Test successful run."""
        # Mock executor factory
        mock_factory_instance = Mock()
        mock_executor_factory.return_value = mock_factory_instance

        # Mock parallel runner
        mock_runner_instance = Mock()
        mock_parallel_runner.return_value = mock_runner_instance
        mock_runner_instance.run.return_value = {"results": "data"}

        runner = InClusterCheckRunner()
        output_path = Path("/tmp/test-results.json")

        with patch('openshift_in_cluster_checks.runner.Path.write_text') as mock_write:
            with patch('openshift_in_cluster_checks.runner.Path.absolute') as mock_absolute:
                mock_absolute.return_value = output_path
                result = runner.run(output_path=output_path)

                assert result == str(output_path)
                mock_write.assert_called_once()
