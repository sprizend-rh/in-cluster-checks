"""
Storage validations ported from healthcheck-backup.

Direct port from: healthcheck-backup/HealthChecks/flows/Storage/ceph/Ceph.py
Adapted for OpenShift/OpenShift use case.
"""

import openshift_client as oc

from openshift_in_cluster_checks.core.rule import OrchestratorRule
from openshift_in_cluster_checks.core.rule_result import PrerequisiteResult, RuleResult
from openshift_in_cluster_checks.utils.enums import Objectives


class CephRule(OrchestratorRule):
    """
    Base class for Ceph-related validation rules.

    Provides common functionality for all Ceph rules:
    - Prerequisite check for openshift-storage namespace
    - Ceph command detection (_get_ceph_command)

    Ported from CephValidation base class in healthcheck-backup.
    """

    def _get_ceph_pod(self) -> tuple:
        """
        Get the appropriate ceph pod for executing commands.

        For OpenShift with Rook-Ceph, we need to execute commands inside the
        rook-ceph-tools pod or ceph operator pod.

        Returns:
            Tuple of (namespace, pod_name, ceph_config_args)
            - namespace: Namespace where the pod is located
            - pod_name: Name of the pod
            - ceph_config_args: Additional ceph arguments (e.g., "-c /path/to/config" or "")
        """
        namespace = "openshift-storage"

        # First, try to find the rook-ceph-tools pod (preferred)
        pod_name = self._get_pod_name(namespace, {"app": "rook-ceph-tools"})
        if pod_name:
            return namespace, pod_name, ""

        # Fallback: use ceph operator pod (guaranteed to exist by prerequisite check)
        pod_name = self._get_pod_name(namespace, {"app": "rook-ceph-operator"})
        ceph_conf = "/var/lib/rook/openshift-storage/openshift-storage.config"
        return namespace, pod_name, f"-c {ceph_conf}"

    def is_prerequisite_fulfilled(self) -> PrerequisiteResult:
        """
        Check if Ceph is being used in the cluster.

        Verifies:
        1. openshift-storage namespace exists
        2. rook-ceph-operator pod exists (tools pod is optional)

        Returns:
            PrerequisiteResult indicating if Ceph storage is present
        """

        try:
            # Check if openshift-storage namespace exists (Rook-Ceph namespace)
            with oc.timeout(10):
                namespaces = oc.selector("namespace/openshift-storage").objects()
                if not namespaces:
                    return PrerequisiteResult.not_met(
                        "OpenShift Storage namespace not found. Ceph is not deployed in this cluster."
                    )
        except Exception:
            return PrerequisiteResult.not_met(
                "OpenShift Storage namespace not found. Ceph is not deployed in this cluster."
            )

        # Check for operator pod (required - tools pod is optional)
        namespace = "openshift-storage"
        operator_pod = self._get_pod_name(namespace, {"app": "rook-ceph-operator"})

        if not operator_pod:
            return PrerequisiteResult.not_met(
                "No rook-ceph-operator pod found in openshift-storage namespace. Ceph operator is not running."
            )

        return PrerequisiteResult.met()


class CephOsdTreeWorks(CephRule):
    """
    Check if ceph osd tree command is working.

    Ported from: CephOsdTreeWorks in healthcheck-backup/HealthChecks/flows/Storage/ceph/Ceph.py (lines 89-108)

    This validation ensures that the Ceph cluster is accessible and the 'ceph osd tree'
    command executes successfully. This is a fundamental check for Ceph storage health.

    For OpenShift/OpenShift, we use MANAGERS (control plane) nodes as they typically have
    access to the Ceph cluster via rook-ceph operators.
    """

    objective_hosts = [Objectives.ORCHESTRATOR]
    unique_name = "ceph_osd_tree_valid"
    title = "Check if ceph osd tree working"

    def run_rule(self) -> RuleResult:
        """
        Execute 'ceph osd tree' command and verify it works.

        Returns:
            RuleResult.passed() if command succeeds
            RuleResult.failed() with error message if command fails
        """
        # Get ceph pod information
        namespace, pod_name, ceph_config_args = self._get_ceph_pod()

        # Build ceph command
        if ceph_config_args:
            cmd = f"ceph {ceph_config_args} osd tree"
        else:
            cmd = "ceph osd tree"

        print(f"Executing in pod {namespace}/{pod_name}: {cmd}")

        # Execute command in pod using rsh
        return_code, stdout, stderr = self.run_rsh_cmd(namespace, pod_name, cmd, timeout=30)

        if return_code == 0:
            return RuleResult.passed()
        else:
            error_msg = "ceph osd tree is not working."
            if stderr:
                error_msg += f"\nError: {stderr}"
            if stdout:
                error_msg += f"\nOutput: {stdout}"
            return RuleResult.failed(error_msg)
