"""
Tests for K8s/OpenShift validations.

Adapted from HealthChecks test patterns for AllPodsReadyAndRunning.
"""

import json

import pytest
from unittest.mock import Mock

from in_cluster_checks.rules.k8s.k8s_validations import (
    AllDeploymentsAvailable,
    AllPodsReadyAndRunning,
    CheckDeploymentsReplicaStatus,
    NodesAreReady,
    NodesCpuAndMemoryStatus,
    OpenshiftOperatorStatus,
    ValidateAllDaemonsetsScheduled,
    ValidateNamespaceStatus,
)
from in_cluster_checks.utils.enums import Status


def create_mock_pod(namespace, name, phase, ready_containers, total_containers):
    """Create a mock pod object."""
    mock_pod = Mock()
    container_statuses = [
        {"ready": i < ready_containers} for i in range(total_containers)
    ]
    mock_pod.as_dict.return_value = {
        "metadata": {"namespace": namespace, "name": name},
        "status": {
            "phase": phase,
            "containerStatuses": container_statuses,
        },
    }
    return mock_pod


class TestAllPodsReadyAndRunning:
    """Test AllPodsReadyAndRunning rule."""

    @pytest.fixture
    def tested_object(self):
        """Create instance of AllPodsReadyAndRunning for testing."""
        return AllPodsReadyAndRunning(host_executor=Mock(), node_executors={})

    def test_all_pods_running_and_ready(self, tested_object):
        """Test when all pods are running and ready."""
        tested_object.get_all_pods = Mock(
            return_value=[
                create_mock_pod("default", "pod1", "Running", 2, 2),
                create_mock_pod("kube-system", "pod2", "Running", 1, 1),
            ]
        )

        result = tested_object.run_rule()
        assert result.status == Status.PASSED

    def test_some_pods_not_running(self, tested_object):
        """Test when some pods are not in Running state."""
        tested_object.get_all_pods = Mock(
            return_value=[
                create_mock_pod("default", "running-pod", "Running", 1, 1),
                create_mock_pod("default", "pending-pod", "Pending", 0, 1),
            ]
        )

        result = tested_object.run_rule()
        assert result.status == Status.FAILED
        assert "pending-pod" in result.message
        assert "Pending" in result.message

    def test_completed_pods_ignored(self, tested_object):
        """Test that completed/succeeded pods are ignored."""
        tested_object.get_all_pods = Mock(
            return_value=[
                create_mock_pod("default", "running-pod", "Running", 1, 1),
                create_mock_pod("default", "completed-job", "Succeeded", 0, 1),
            ]
        )

        result = tested_object.run_rule()
        # Should pass because completed jobs are ignored
        assert result.status == Status.PASSED

    def test_no_pods_found(self, tested_object):
        """Test when no pods are found in the cluster."""
        tested_object.get_all_pods = Mock(return_value=[])

        result = tested_object.run_rule()
        assert result.status == Status.FAILED
        assert "Did not get any pods" in result.message


def create_mock_node(name, ready_status, other_conditions=None):
    """Create a mock node object."""
    mock_node = Mock()
    conditions = [{"type": "Ready", "status": ready_status}]

    if other_conditions:
        conditions.extend(other_conditions)

    mock_node.as_dict.return_value = {
        "metadata": {"name": name},
        "status": {"conditions": conditions},
    }
    return mock_node


class TestNodesAreReady:
    """Test NodesAreReady rule."""

    @pytest.fixture
    def tested_object(self):
        """Create instance of NodesAreReady for testing."""
        return NodesAreReady(host_executor=Mock(), node_executors={})

    def test_all_nodes_ready(self, tested_object):
        """Test when all nodes are ready."""
        tested_object.get_all_nodes = Mock(
            return_value=[
                create_mock_node("node1", "True"),
                create_mock_node("node2", "True"),
            ]
        )

        result = tested_object.run_rule()
        assert result.status == Status.PASSED

    def test_some_nodes_not_ready(self, tested_object):
        """Test when some nodes are not ready."""
        tested_object.get_all_nodes = Mock(
            return_value=[
                create_mock_node("node1", "True"),
                create_mock_node("node2", "False"),
                create_mock_node("node3", "Unknown"),
            ]
        )

        result = tested_object.run_rule()
        assert result.status == Status.FAILED
        assert "node2" in result.message
        assert "node3" in result.message
        assert "not ready" in result.message

    def test_nodes_with_warnings(self, tested_object):
        """Test when nodes have warning conditions."""
        tested_object.get_all_nodes = Mock(
            return_value=[
                create_mock_node("node1", "True"),
                create_mock_node(
                    "node2",
                    "True",
                    [{"type": "DiskPressure", "status": "True"}],
                ),
            ]
        )

        result = tested_object.run_rule()
        assert result.status == Status.FAILED
        assert "node2" in result.message
        assert "DiskPressure" in result.message

    def test_no_nodes_found(self, tested_object):
        """Test when no nodes are found."""
        tested_object.get_all_nodes = Mock(return_value=[])

        result = tested_object.run_rule()
        assert result.status == Status.FAILED
        assert "Did not get nodes list" in result.message


class TestNodesCpuAndMemoryStatus:
    """Test NodesCpuAndMemoryStatus rule."""

    @pytest.fixture
    def tested_object(self):
        """Create instance of NodesCpuAndMemoryStatus for testing."""
        return NodesCpuAndMemoryStatus(host_executor=Mock(), node_executors={})

    def test_all_nodes_normal_usage(self, tested_object):
        """Test when all nodes have normal CPU/memory usage."""
        tested_object.run_oc_command = Mock(
            return_value=(0, "node1    100m    5%     2000Mi   10%\nnode2    200m    10%    3000Mi   15%", "")
        )

        result = tested_object.run_rule()
        assert result.status == Status.PASSED

    def test_high_cpu_usage(self, tested_object):
        """Test when some nodes have high CPU usage."""
        tested_object.run_oc_command = Mock(
            return_value=(0, "node1    10000m  85%    2000Mi   10%\nnode2    200m    10%    3000Mi   15%", "")
        )

        result = tested_object.run_rule()
        assert result.status == Status.FAILED
        assert "node1" in result.message
        assert "85%" in result.message
        assert "high CPU usage" in result.message

    def test_high_memory_usage(self, tested_object):
        """Test when some nodes have high memory usage."""
        tested_object.run_oc_command = Mock(
            return_value=(0, "node1    100m    5%     50000Mi  90%\nnode2    200m    10%    3000Mi   15%", "")
        )

        result = tested_object.run_rule()
        assert result.status == Status.FAILED
        assert "node1" in result.message
        assert "90%" in result.message
        assert "high memory usage" in result.message

    def test_critical_threshold_exceeded(self, tested_object):
        """Test when critical threshold is exceeded."""
        tested_object.run_oc_command = Mock(
            return_value=(0, "node1    10000m  95%    2000Mi   10%", "")
        )

        result = tested_object.run_rule()
        assert result.status == Status.FAILED
        assert "CRITICAL" in result.message
        assert "95%" in result.message

    def test_no_metrics_available(self, tested_object):
        """Test when no metrics are available."""
        tested_object.run_oc_command = Mock(return_value=(0, "", ""))

        result = tested_object.run_rule()
        assert result.status == Status.FAILED
        assert "No node metrics available" in result.message


def create_mock_namespace(name, phase):
    """Create a mock namespace object."""
    mock_ns = Mock()
    mock_ns.as_dict.return_value = {
        "metadata": {"name": name},
        "status": {"phase": phase},
    }
    return mock_ns


class TestValidateNamespaceStatus:
    """Test ValidateNamespaceStatus rule."""

    @pytest.fixture
    def tested_object(self):
        """Create instance of ValidateNamespaceStatus for testing."""
        return ValidateNamespaceStatus(host_executor=Mock(), node_executors={})

    def test_all_namespaces_active(self, tested_object):
        """Test when all namespaces are active."""
        tested_object.get_all_namespaces = Mock(
            return_value=[
                create_mock_namespace("default", "Active"),
                create_mock_namespace("kube-system", "Active"),
            ]
        )

        result = tested_object.run_rule()
        assert result.status == Status.PASSED

    def test_some_namespaces_terminating(self, tested_object):
        """Test when some namespaces are terminating."""
        tested_object.get_all_namespaces = Mock(
            return_value=[
                create_mock_namespace("default", "Active"),
                create_mock_namespace("old-ns", "Terminating"),
            ]
        )

        result = tested_object.run_rule()
        assert result.status == Status.WARNING
        assert "old-ns" in result.message
        assert "Terminating" in result.message

    def test_no_namespaces_found(self, tested_object):
        """Test when no namespaces are found."""
        tested_object.get_all_namespaces = Mock(return_value=[])

        result = tested_object.run_rule()
        assert result.status == Status.FAILED
        assert "No namespaces found" in result.message


class TestValidateAllDaemonsetsScheduled:
    """Test ValidateAllDaemonsetsScheduled rule."""

    @pytest.fixture
    def tested_object(self):
        """Create instance of ValidateAllDaemonsetsScheduled for testing."""
        return ValidateAllDaemonsetsScheduled(host_executor=Mock(), node_executors={})

    def test_all_daemonsets_scheduled(self, tested_object):
        """Test when all daemonsets have desired number of pods and none unavailable."""
        daemonsets_data = {
            "items": [
                {
                    "metadata": {"name": "ds1", "namespace": "kube-system"},
                    "status": {
                        "desiredNumberScheduled": 3,
                        "currentNumberScheduled": 3,
                        "numberUnavailable": 0,
                    },
                },
                {
                    "metadata": {"name": "ds2", "namespace": "default"},
                    "status": {
                        "desiredNumberScheduled": 2,
                        "currentNumberScheduled": 2,
                        "numberUnavailable": 0,
                    },
                },
            ]
        }
        tested_object.run_oc_command = Mock(return_value=(0, json.dumps(daemonsets_data), ""))

        result = tested_object.run_rule()
        assert result.status == Status.PASSED

    def test_some_daemonsets_not_fully_scheduled(self, tested_object):
        """Test when some daemonsets don't have desired number of pods."""
        daemonsets_data = {
            "items": [
                {
                    "metadata": {"name": "ds1", "namespace": "kube-system"},
                    "status": {
                        "desiredNumberScheduled": 3,
                        "currentNumberScheduled": 2,
                        "numberUnavailable": 0,
                    },
                },
                {
                    "metadata": {"name": "ds2", "namespace": "default"},
                    "status": {
                        "desiredNumberScheduled": 2,
                        "currentNumberScheduled": 2,
                        "numberUnavailable": 0,
                    },
                },
            ]
        }
        tested_object.run_oc_command = Mock(return_value=(0, json.dumps(daemonsets_data), ""))

        result = tested_object.run_rule()
        assert result.status == Status.FAILED
        assert "ds1" in result.message
        assert "kube-system" in result.message
        assert "Desired: 3" in result.message
        assert "Current: 2" in result.message
        assert "pods not being scheduled" in result.message

    def test_daemonset_with_zero_desired_is_skipped(self, tested_object):
        """Test that daemonsets with 0 desired pods are skipped (no matching nodes)."""
        daemonsets_data = {
            "items": [
                {
                    "metadata": {"name": "vg-manager", "namespace": "openshift-storage"},
                    "status": {
                        "desiredNumberScheduled": 0,
                        "currentNumberScheduled": 0,
                        "numberUnavailable": 0,
                    },
                },
                {
                    "metadata": {"name": "ds2", "namespace": "default"},
                    "status": {
                        "desiredNumberScheduled": 2,
                        "currentNumberScheduled": 2,
                        "numberUnavailable": 0,
                    },
                },
            ]
        }
        tested_object.run_oc_command = Mock(return_value=(0, json.dumps(daemonsets_data), ""))

        result = tested_object.run_rule()
        assert result.status == Status.PASSED

    def test_daemonset_pods_initializing_passes(self, tested_object):
        """Test that daemonsets with pods still initializing pass (not explicitly unavailable)."""
        daemonsets_data = {
            "items": [
                {
                    "metadata": {"name": "vg-manager", "namespace": "openshift-storage"},
                    "status": {
                        "desiredNumberScheduled": 1,
                        "currentNumberScheduled": 1,
                        "numberUnavailable": 0,
                    },
                },
            ]
        }
        tested_object.run_oc_command = Mock(return_value=(0, json.dumps(daemonsets_data), ""))

        result = tested_object.run_rule()
        assert result.status == Status.PASSED

    def test_daemonset_with_unavailable_pods(self, tested_object):
        """Test when daemonset has pods marked as unavailable (real issue)."""
        daemonsets_data = {
            "items": [
                {
                    "metadata": {"name": "ds1", "namespace": "kube-system"},
                    "status": {
                        "desiredNumberScheduled": 3,
                        "currentNumberScheduled": 3,
                        "numberUnavailable": 2,
                    },
                },
            ]
        }
        tested_object.run_oc_command = Mock(return_value=(0, json.dumps(daemonsets_data), ""))

        result = tested_object.run_rule()
        assert result.status == Status.FAILED
        assert "ds1" in result.message
        assert "kube-system" in result.message
        assert "2 pod(s) unavailable" in result.message


class TestOpenshiftOperatorStatus:
    """Test OpenshiftOperatorStatus rule."""

    @pytest.fixture
    def tested_object(self):
        """Create instance of OpenshiftOperatorStatus for testing."""
        return OpenshiftOperatorStatus(host_executor=Mock(), node_executors={})

    def test_all_operators_available(self, tested_object):
        """Test when all operators are available and not progressing."""
        operator_output = """authentication                             4.15.29    True        False         False      14d
baremetal                                  4.15.29    True        False         False      14d
cloud-controller-manager                   4.15.29    True        False         False      14d
cluster-autoscaler                         4.15.29    True        False         False      14d"""

        tested_object.run_oc_command = Mock(return_value=(0, operator_output, ""))

        result = tested_object.run_rule()
        assert result.status == Status.INFO
        assert result.table_headers is not None
        assert result.table_data is not None
        assert result.table_headers == [
            "Name",
            "Version",
            "Available",
            "Progressing",
            "Degraded",
            "Since",
            "Message",
        ]
        assert len(result.table_data) == 4
        assert "All operators are available and stable" in result.message

    def test_some_operators_unavailable(self, tested_object):
        """Test when some operators are unavailable (Available=False)."""
        operator_output = """authentication                             4.15.29    True        False         False      14d
baremetal                                  4.15.29    False       False         False      14d     Operator is degraded
cloud-controller-manager                   4.15.29    True        False         False      14d"""

        tested_object.run_oc_command = Mock(return_value=(0, operator_output, ""))

        result = tested_object.run_rule()
        assert result.status == Status.FAILED
        assert "baremetal" in result.message
        assert "not available" in result.message
        assert result.table_headers is not None
        assert result.table_data is not None

    def test_some_operators_progressing(self, tested_object):
        """Test when some operators are progressing (Progressing=True)."""
        operator_output = """authentication                             4.15.29    True        False         False      14d
baremetal                                  4.15.29    True        True          False      14d     Rolling out new pods
cloud-controller-manager                   4.15.29    True        False         False      14d"""

        tested_object.run_oc_command = Mock(return_value=(0, operator_output, ""))

        result = tested_object.run_rule()
        assert result.status == Status.FAILED
        assert "baremetal" in result.message
        assert "in progress" in result.message
        assert result.table_headers is not None
        assert result.table_data is not None

    def test_operators_unavailable_and_progressing(self, tested_object):
        """Test when some operators are both unavailable and others progressing."""
        operator_output = """authentication                             4.15.29    False       False         False      14d     Auth issues
baremetal                                  4.15.29    True        True          False      14d     Rolling out
cloud-controller-manager                   4.15.29    True        False         False      14d"""

        tested_object.run_oc_command = Mock(return_value=(0, operator_output, ""))

        result = tested_object.run_rule()
        assert result.status == Status.FAILED
        assert "authentication" in result.message
        assert "baremetal" in result.message
        assert "not available" in result.message
        assert "in progress" in result.message
        assert result.table_headers is not None
        assert result.table_data is not None

    def test_no_operators_found(self, tested_object):
        """Test when no cluster operators are found."""
        tested_object.run_oc_command = Mock(return_value=(0, "", ""))

        result = tested_object.run_rule()
        assert result.status == Status.FAILED
        assert "No cluster operators found" in result.message

    def test_table_sorting(self, tested_object):
        """Test that operators are sorted with problematic ones first."""
        operator_output = """good-operator                              4.15.29    True        False         False      14d
bad-operator                               4.15.29    False       False         False      14d     Problem
progressing-operator                       4.15.29    True        True          False      14d     Working
another-good-operator                      4.15.29    True        False         False      14d"""

        tested_object.run_oc_command = Mock(return_value=(0, operator_output, ""))

        result = tested_object.run_rule()
        assert result.status == Status.FAILED

        # Check that table is sorted: Available=False first, then Progressing=True
        assert result.table_data is not None
        assert len(result.table_data) == 4

        # bad-operator (Available=False) should be first
        assert result.table_data[0][0] == "bad-operator"
        assert result.table_data[0][2] == "False"

        # progressing-operator (Progressing=True) should be second
        assert result.table_data[1][0] == "progressing-operator"
        assert result.table_data[1][3] == "True"


class TestAllDeploymentsAvailable:
    """Test AllDeploymentsAvailable rule."""

    @pytest.fixture
    def tested_object(self):
        """Create instance of AllDeploymentsAvailable for testing."""
        return AllDeploymentsAvailable(host_executor=Mock(), node_executors={})

    def test_all_deployments_available(self, tested_object):
        """Test when all deployments are available."""
        deployments_data = {
            "items": [
                {
                    "metadata": {"name": "deployment1", "namespace": "default"},
                    "status": {
                        "conditions": [
                            {"type": "Available", "status": "True"},
                            {"type": "Progressing", "status": "False"},
                        ]
                    },
                },
                {
                    "metadata": {"name": "deployment2", "namespace": "kube-system"},
                    "status": {
                        "conditions": [
                            {"type": "Available", "status": "True"},
                            {"type": "Progressing", "status": "False"},
                        ]
                    },
                },
            ]
        }
        tested_object.run_oc_command = Mock(return_value=(0, json.dumps(deployments_data), ""))

        result = tested_object.run_rule()
        assert result.status == Status.PASSED

    def test_some_deployments_unavailable(self, tested_object):
        """Test when some deployments are not available."""
        deployments_data = {
            "items": [
                {
                    "metadata": {"name": "deployment1", "namespace": "default"},
                    "status": {
                        "conditions": [
                            {"type": "Available", "status": "True"},
                        ]
                    },
                },
                {
                    "metadata": {"name": "deployment2", "namespace": "kube-system"},
                    "status": {
                        "conditions": [
                            {
                                "type": "Available",
                                "status": "False",
                                "reason": "MinimumReplicasUnavailable",
                                "message": "Deployment does not have minimum availability.",
                            },
                        ]
                    },
                },
            ]
        }
        tested_object.run_oc_command = Mock(return_value=(0, json.dumps(deployments_data), ""))

        result = tested_object.run_rule()
        assert result.status == Status.FAILED
        assert "deployment2" in result.message
        assert "kube-system" in result.message
        assert "MinimumReplicasUnavailable" in result.message

    def test_deployment_without_available_condition(self, tested_object):
        """Test when deployment has no Available condition."""
        deployments_data = {
            "items": [
                {
                    "metadata": {"name": "deployment1", "namespace": "default"},
                    "status": {
                        "conditions": [
                            {"type": "Progressing", "status": "True"},
                        ]
                    },
                },
            ]
        }
        tested_object.run_oc_command = Mock(return_value=(0, json.dumps(deployments_data), ""))

        result = tested_object.run_rule()
        assert result.status == Status.FAILED
        assert "deployment1" in result.message
        assert "No Available condition found" in result.message

    def test_no_deployments_found(self, tested_object):
        """Test when no deployments are found in cluster."""
        deployments_data = {"items": []}
        tested_object.run_oc_command = Mock(return_value=(0, json.dumps(deployments_data), ""))

        result = tested_object.run_rule()
        assert result.status == Status.FAILED
        assert "No deployments found" in result.message

    def test_mixed_deployment_states(self, tested_object):
        """Test when deployments are in mixed states."""
        deployments_data = {
            "items": [
                {
                    "metadata": {"name": "good-deployment", "namespace": "default"},
                    "status": {
                        "conditions": [
                            {"type": "Available", "status": "True"},
                        ]
                    },
                },
                {
                    "metadata": {"name": "bad-deployment", "namespace": "app-ns"},
                    "status": {
                        "conditions": [
                            {
                                "type": "Available",
                                "status": "False",
                                "reason": "DeploymentFailure",
                                "message": "Pod failures",
                            },
                        ]
                    },
                },
                {
                    "metadata": {"name": "no-condition-deployment", "namespace": "test-ns"},
                    "status": {"conditions": []},
                },
            ]
        }
        tested_object.run_oc_command = Mock(return_value=(0, json.dumps(deployments_data), ""))

        result = tested_object.run_rule()
        assert result.status == Status.FAILED
        assert "bad-deployment" in result.message
        assert "no-condition-deployment" in result.message
        assert "good-deployment" not in result.message


class TestCheckDeploymentsReplicaStatus:
    """Test CheckDeploymentsReplicaStatus rule."""

    @pytest.fixture
    def tested_object(self):
        """Create instance of CheckDeploymentsReplicaStatus for testing."""
        return CheckDeploymentsReplicaStatus(host_executor=Mock(), node_executors={})

    def test_all_replicas_ready(self, tested_object):
        """Test when all deployments have correct replica counts."""
        deployments_data = {
            "items": [
                {
                    "metadata": {"name": "deployment1", "namespace": "default"},
                    "spec": {"replicas": 3},
                    "status": {
                        "replicas": 3,
                        "readyReplicas": 3,
                        "availableReplicas": 3,
                        "updatedReplicas": 3,
                    },
                },
                {
                    "metadata": {"name": "deployment2", "namespace": "kube-system"},
                    "spec": {"replicas": 1},
                    "status": {
                        "replicas": 1,
                        "readyReplicas": 1,
                        "availableReplicas": 1,
                        "updatedReplicas": 1,
                    },
                },
            ]
        }
        tested_object.run_oc_command = Mock(return_value=(0, json.dumps(deployments_data), ""))

        result = tested_object.run_rule()
        assert result.status == Status.PASSED

    def test_not_all_replicas_ready(self, tested_object):
        """Test when some deployments don't have all replicas ready."""
        deployments_data = {
            "items": [
                {
                    "metadata": {"name": "deployment1", "namespace": "default"},
                    "spec": {"replicas": 3},
                    "status": {
                        "replicas": 3,
                        "readyReplicas": 2,
                        "availableReplicas": 2,
                        "updatedReplicas": 3,
                    },
                },
            ]
        }
        tested_object.run_oc_command = Mock(return_value=(0, json.dumps(deployments_data), ""))

        result = tested_object.run_rule()
        assert result.status == Status.FAILED
        assert "deployment1" in result.message
        assert "default" in result.message
        assert "Desired: 3" in result.message
        assert "Ready: 2" in result.message

    def test_not_all_replicas_available(self, tested_object):
        """Test when some deployments don't have all replicas available."""
        deployments_data = {
            "items": [
                {
                    "metadata": {"name": "deployment2", "namespace": "app-ns"},
                    "spec": {"replicas": 5},
                    "status": {
                        "replicas": 5,
                        "readyReplicas": 5,
                        "availableReplicas": 4,
                        "updatedReplicas": 5,
                    },
                },
            ]
        }
        tested_object.run_oc_command = Mock(return_value=(0, json.dumps(deployments_data), ""))

        result = tested_object.run_rule()
        assert result.status == Status.FAILED
        assert "deployment2" in result.message
        assert "app-ns" in result.message
        assert "Desired: 5" in result.message
        assert "Available: 4" in result.message

    def test_rollout_in_progress(self, tested_object):
        """Test when deployment has rollout in progress."""
        deployments_data = {
            "items": [
                {
                    "metadata": {"name": "deployment3", "namespace": "prod"},
                    "spec": {"replicas": 3},
                    "status": {
                        "replicas": 3,
                        "readyReplicas": 3,
                        "availableReplicas": 3,
                        "updatedReplicas": 2,
                    },
                },
            ]
        }
        tested_object.run_oc_command = Mock(return_value=(0, json.dumps(deployments_data), ""))

        result = tested_object.run_rule()
        assert result.status == Status.FAILED
        assert "deployment3" in result.message
        assert "prod" in result.message
        assert "Desired: 3" in result.message
        assert "Updated: 2" in result.message
        assert "rollout in progress" in result.message

    def test_zero_replicas_deployment(self, tested_object):
        """Test deployment with zero replicas (scaled down) passes."""
        deployments_data = {
            "items": [
                {
                    "metadata": {"name": "scaled-down", "namespace": "default"},
                    "spec": {"replicas": 0},
                    "status": {
                        "replicas": 0,
                        "readyReplicas": 0,
                        "availableReplicas": 0,
                        "updatedReplicas": 0,
                    },
                },
                {
                    "metadata": {"name": "normal-deployment", "namespace": "default"},
                    "spec": {"replicas": 2},
                    "status": {
                        "replicas": 2,
                        "readyReplicas": 2,
                        "availableReplicas": 2,
                        "updatedReplicas": 2,
                    },
                },
            ]
        }
        tested_object.run_oc_command = Mock(return_value=(0, json.dumps(deployments_data), ""))

        result = tested_object.run_rule()
        assert result.status == Status.PASSED

    def test_mixed_deployment_states(self, tested_object):
        """Test multiple deployments with different issues."""
        deployments_data = {
            "items": [
                {
                    "metadata": {"name": "good-deployment", "namespace": "default"},
                    "spec": {"replicas": 2},
                    "status": {
                        "replicas": 2,
                        "readyReplicas": 2,
                        "availableReplicas": 2,
                        "updatedReplicas": 2,
                    },
                },
                {
                    "metadata": {"name": "not-ready-deployment", "namespace": "app1"},
                    "spec": {"replicas": 3},
                    "status": {
                        "replicas": 3,
                        "readyReplicas": 1,
                        "availableReplicas": 1,
                        "updatedReplicas": 3,
                    },
                },
                {
                    "metadata": {"name": "updating-deployment", "namespace": "app2"},
                    "spec": {"replicas": 4},
                    "status": {
                        "replicas": 4,
                        "readyReplicas": 4,
                        "availableReplicas": 4,
                        "updatedReplicas": 2,
                    },
                },
            ]
        }
        tested_object.run_oc_command = Mock(return_value=(0, json.dumps(deployments_data), ""))

        result = tested_object.run_rule()
        assert result.status == Status.FAILED
        assert "not-ready-deployment" in result.message
        assert "updating-deployment" in result.message
        assert "good-deployment" not in result.message

    def test_no_deployments_found(self, tested_object):
        """Test when no deployments exist in cluster."""
        deployments_data = {"items": []}
        tested_object.run_oc_command = Mock(return_value=(0, json.dumps(deployments_data), ""))

        result = tested_object.run_rule()
        assert result.status == Status.FAILED
        assert "No deployments found" in result.message
