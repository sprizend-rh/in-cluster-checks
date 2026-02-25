"""
Network rule domain for OpenShift cluster.

Orchestrates network-related healthcheck validators.
Based on support/HealthChecks/flows/Network/network_flows_openshift.py
"""

from typing import List

from openshift_in_cluster_checks.core.domain import RuleDomain
from openshift_in_cluster_checks.rules.network.ovs_validations import (
    Bond0DnsServersComparison,
    OvsInterfaceAndPortFound,
)


class NetworkValidationDomain(RuleDomain):
    """
    Network rule domain for OpenShift.

    Phase 1B-E2E: Starting with just OvsInterfaceAndPortFound for testing.
    """

    def domain_name(self) -> str:
        """Get domain name."""
        return "network"

    def get_rule_classes(self) -> List[type]:
        """
        Get list of network validators to run.

        Returns:
            List of Rule classes
        """
        return [
            OvsInterfaceAndPortFound,
            Bond0DnsServersComparison,
        ]
