"""
Tests for OVS network validations.

Adapted from healthcheck-backup/HealthChecks/tests/pytest/flows/network/test_ovs_validations.py
"""

import pytest

from in_cluster_checks.rules.network.ovs_validations import (
    Bond0Dns,
    BondDnsServersComparison,
    BondVlanOvsAttachmentCheck,
    OvnRoutingHealthCheck,
    OvsBridgeInterfaceHealthCheck,
    OvsInterfaceAndPortFound,
    OvsPhysicalPortHealthCheck,
)
from tests.pytest_tools.test_data_collector_base import (
    DataCollectorTestBase,
    DataCollectorScenarioParams,
)
from tests.pytest_tools.test_operator_base import CmdOutput
from tests.pytest_tools.test_rule_base import (
    RuleTestBase,
    RuleScenarioParams,
)


class TestOvsInterfaceAndPortFound(RuleTestBase):
    """Test OvsInterfaceAndPortFound validator."""

    tested_type = OvsInterfaceAndPortFound

    # Sample nmcli connection show output
    nmcli_out = """        NAME                UUID                                  TYPE           DEVICE   .
ovs-if-br-ex        a003bd38-993b-4381-a045-a73cbb95d5a1  ovs-interface  br-ex    .
lo                  1cb462ac-9545-4df8-ab39-6b2b502d0b6d  loopback       lo       .
bond1.62            2741b63b-d8fd-597b-bb9a-ba40524d86a3  vlan           bond1.62 .
bond1.63            b04d9161-cbee-500f-80ec-63b61d24d7a7  vlan           bond1.63 .
bond1.64            0194209d-6bdd-5309-ae06-effdb22b83b7  vlan           bond1.64 .
br-ex               5d63c53e-6560-4d31-b00d-251652d1864d  ovs-bridge     br-ex    .
{}0        87e16a88-908a-4f07-ace4-797d12db7a52  vlan           bond0.61 .
ovs-port-br-ex      cf7a7335-b894-44c7-bb24-3691f90ab92a  ovs-port       br-ex    .
{}0      1ebbf722-3615-44b8-b379-b370e606a9a3  ovs-port       bond0.61 .
Wired connection 1  f149efb7-660c-3f27-abca-0017b5c485df  ethernet       --       .
bond0.61            0720fef3-957e-5bd2-a053-9a27413e3870  vlan           --       .
"""

    scenario_passed = [
        RuleScenarioParams(
            "ovs-if-phys and ovs-port-phys exist",
            {
                "nmcli connection show": CmdOutput(
                    nmcli_out.format("ovs-if-phys", "ovs-port-phys")
                )
            },
        )
    ]

    scenario_failed = [
        RuleScenarioParams(
            "ovs-if-phys does not exist and ovs-port-phys exists",
            {
                "nmcli connection show": CmdOutput(
                    nmcli_out.format("ovs-vlan-phys", "ovs-port-phys")
                )
            },
        ),
        RuleScenarioParams(
            "ovs-if-phys and ovs-port-phys dont exist",
            {
                "nmcli connection show": CmdOutput(
                    nmcli_out.format("ovs-vlan-phys", "ovs-porti-phys")
                )
            },
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)


class TestBond0Dns(DataCollectorTestBase):
    """Test Bond0Dns data collector."""

    tested_type = Bond0Dns

    # Sample nmcli -t -f TYPE,DEVICE connection show --active output
    nmcli_active = "bond:bond0\nbond:bond0.110\nethernet:eth0\n"
    nmcli_active_single = "bond:bond0\nethernet:eth0\n"

    # Sample nmcli conn show bond0 output
    bond0_out = """connection.id:                          bond0
802-3-ethernet.port:                    --
ipv4.method:                            manual
ipv4.dns:                               {}
ipv4.dns:                               {}
ipv4.dns:                               {}
ipv6.method:                            manual
ipv6.dns:                               {}
ipv6.dns-search:                        --
"""

    bond0_110_out = """connection.id:                          bond0.110
ipv4.method:                            manual
ipv4.dns:                               8.8.8.8
ipv6.method:                            manual
"""

    scenarios = [
        DataCollectorScenarioParams(
            "single bond with DNS",
            {
                "nmcli -t -f TYPE,DEVICE connection show --active": CmdOutput(nmcli_active_single),
                "nmcli conn show bond0": CmdOutput(
                    bond0_out.format(
                        "192.168.22.424",
                        "192.168.22.424",
                        "192.168.22.424",
                        "fd00:2023:22::4",
                    )
                )
            },
            scenario_res={"bond0": {"ipv4": {"192.168.22.424"}, "ipv6": {"fd00:2023:22::4"}}},
        ),
        DataCollectorScenarioParams(
            "multiple bonds with VLAN",
            {
                "nmcli -t -f TYPE,DEVICE connection show --active": CmdOutput(nmcli_active),
                "nmcli conn show bond0": CmdOutput(
                    bond0_out.format(
                        "192.168.22.422",
                        "192.168.22.423",
                        "192.168.22.424",
                        "fd00:2023:22::4",
                    )
                ),
                "nmcli conn show bond0.110": CmdOutput(bond0_110_out),
            },
            scenario_res={
                "bond0": {
                    "ipv4": {"192.168.22.422", "192.168.22.423", "192.168.22.424"},
                    "ipv6": {"fd00:2023:22::4"},
                },
                "bond0.110": {"ipv4": {"8.8.8.8"}, "ipv6": set()},
            },
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenarios)
    def test_collect_data(self, scenario_params, tested_object):
        DataCollectorTestBase.test_collect_data(self, scenario_params, tested_object)


class TestBondDnsServersComparison(RuleTestBase):
    """Test BondDnsServersComparison validator."""

    tested_type = BondDnsServersComparison

    scenario_not_applicable = [
        RuleScenarioParams(
            "no bond interfaces on any node",
            data_collector_dict={
                Bond0Dns: {
                    "manager0": None,
                    "manager1": None,
                }
            },
            failed_msg="No bond interfaces found on any node",
        ),
    ]

    scenario_passed = [
        RuleScenarioParams(
            "empty dns across all bonds",
            data_collector_dict={
                Bond0Dns: {
                    "manager0": {"bond0": {"ipv4": set(), "ipv6": set()}},
                    "manager1": {"bond0": {"ipv4": set(), "ipv6": set()}},
                }
            },
        ),
        RuleScenarioParams(
            "equal dns across all bonds",
            data_collector_dict={
                Bond0Dns: {
                    "manager0": {
                        "bond0": {
                            "ipv4": {"192.168.22.422", "192.168.22.423", "192.168.22.424"},
                            "ipv6": {"fd00:2023:22::4"},
                        },
                    },
                    "manager1": {
                        "bond0": {
                            "ipv4": {"192.168.22.422", "192.168.22.423", "192.168.22.424"},
                            "ipv6": {"fd00:2023:22::4"},
                        },
                    },
                }
            },
        ),
        RuleScenarioParams(
            "equal dns on bond0 and bond0.110",
            data_collector_dict={
                Bond0Dns: {
                    "manager0": {
                        "bond0": {"ipv4": {"8.8.8.8"}, "ipv6": set()},
                        "bond0.110": {"ipv4": {"8.8.8.8"}, "ipv6": set()},
                    },
                    "manager1": {
                        "bond0": {"ipv4": {"8.8.8.8"}, "ipv6": set()},
                        "bond0.110": {"ipv4": {"8.8.8.8"}, "ipv6": set()},
                    },
                }
            },
        ),
    ]

    scenario_failed = [
        RuleScenarioParams(
            "different dns on bond0",
            data_collector_dict={
                Bond0Dns: {
                    "manager0": {
                        "bond0": {"ipv4": set(), "ipv6": set()},
                    },
                    "manager1": {
                        "bond0": {
                            "ipv4": {"192.168.22.422", "192.168.22.423", "192.168.22.424"},
                            "ipv6": set(),
                        },
                    },
                }
            },
            failed_msg=(
                "DNS server mismatch found across nodes:\n\n"
                "Bond interface: bond0\n"
                "  IPv4 DNS mismatch (reference: manager0 = []):\n"
                "    manager1: ['192.168.22.422', '192.168.22.423', '192.168.22.424']"
            ),
        ),
        RuleScenarioParams(
            "different dns on bond0.110 VLAN",
            data_collector_dict={
                Bond0Dns: {
                    "manager0": {
                        "bond0": {"ipv4": {"8.8.8.8"}, "ipv6": set()},
                        "bond0.110": {"ipv4": {"8.8.8.8"}, "ipv6": set()},
                    },
                    "manager1": {
                        "bond0": {"ipv4": {"8.8.8.8"}, "ipv6": set()},
                        "bond0.110": {"ipv4": {"1.1.1.1"}, "ipv6": set()},  # Different DNS on VLAN
                    },
                }
            },
            failed_msg=(
                "DNS server mismatch found across nodes:\n\n"
                "Bond interface: bond0.110\n"
                "  IPv4 DNS mismatch (reference: manager0 = ['8.8.8.8']):\n"
                "    manager1: ['1.1.1.1']"
            ),
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_not_applicable)
    def test_scenario_not_applicable(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_not_applicable(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)


class TestOvsPhysicalPortHealthCheck(RuleTestBase):
    """Test OvsPhysicalPortHealthCheck rule."""

    tested_type = OvsPhysicalPortHealthCheck

    # Healthy outputs - physical port with NO IP
    nmcli_good = (
        "NAME                UUID                                  TYPE           DEVICE\n"
        "ovs-if-phys0        uuid123                               ethernet       enp1s0\n"
        "bond0               uuid456                               bond           bond0\n"
    )
    link_good = "2: enp1s0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 state UP\n"
    addr_no_ip = (
        "2: enp1s0: <BROADCAST,MULTICAST,UP> mtu 1500 state UP\n"
        "    link/ether aa:bb:cc:dd:ee:ff brd ff:ff:ff:ff:ff:ff\n"
    )

    # Failure outputs
    nmcli_missing = (
        "NAME                UUID                                  TYPE           DEVICE\n"
        "bond0               uuid456                               bond           bond0\n"
    )
    link_down = "2: enp1s0: <BROADCAST,MULTICAST> mtu 1500 state DOWN\n"
    addr_has_ip = (
        "2: enp1s0: <BROADCAST,MULTICAST,UP> mtu 1500 state UP\n"
        "    link/ether aa:bb:cc:dd:ee:ff brd ff:ff:ff:ff:ff:ff\n"
        "    inet 10.0.0.5/24 brd 10.0.0.255 scope global enp1s0\n"
    )

    scenario_passed = [
        RuleScenarioParams(
            "physical port UP with no IP",
            {
                "nmcli connection show": CmdOutput(nmcli_good),
                "ip link show enp1s0": CmdOutput(link_good),
                "ip addr show enp1s0": CmdOutput(addr_no_ip),
            },
        ),
    ]

    scenario_failed = [
        RuleScenarioParams(
            "physical port not found",
            {
                "nmcli connection show": CmdOutput(nmcli_missing),
            },
            failed_msg="No OVS physical port (ovs-if-phys*) found in NetworkManager",
        ),
        RuleScenarioParams(
            "physical port down",
            {
                "nmcli connection show": CmdOutput(nmcli_good),
                "ip link show enp1s0": CmdOutput(link_down),
                "ip addr show enp1s0": CmdOutput(addr_no_ip),
            },
            failed_msg="Physical port issue: enp1s0 interface is DOWN",
        ),
        RuleScenarioParams(
            "physical port has IP (incorrect)",
            {
                "nmcli connection show": CmdOutput(nmcli_good),
                "ip link show enp1s0": CmdOutput(link_good),
                "ip addr show enp1s0": CmdOutput(addr_has_ip),
            },
            failed_msg=(
                "Physical port configuration issue: enp1s0 has IP address 10.0.0.5/24 - "
                "physical OVS ports should not have IPs (IPs belong on the bridge interface)"
            ),
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        """Test scenarios where rule should pass."""
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        """Test scenarios where rule should fail."""
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)


class TestOvsBridgeInterfaceHealthCheck(RuleTestBase):
    """Test OvsBridgeInterfaceHealthCheck rule."""

    tested_type = OvsBridgeInterfaceHealthCheck

    # Healthy outputs - bridge with link-local IPs
    nmcli_good = (
        "NAME                UUID                                  TYPE           DEVICE\n"
        "ovs-if-br-ex        uuid123                               ovs-interface  br-ex\n"
        "br-ex               uuid789                               ovs-bridge     br-ex\n"
    )
    link_good = "6: br-ex: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 state UP\n"

    # Multiple valid link-local IP ranges
    addr_good_169_254_169 = (
        "6: br-ex: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 state UP\n"
        "    link/ether 52:54:00:3a:8a:3a brd ff:ff:ff:ff:ff:ff\n"
        "    inet 192.168.122.10/24 brd 192.168.122.255 scope global br-ex\n"
        "    inet 169.254.169.2/29 brd 169.254.169.7 scope global br-ex\n"
    )
    addr_good_169_254_0 = (
        "6: br-ex: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 state UP\n"
        "    link/ether 52:54:00:3a:8a:3a brd ff:ff:ff:ff:ff:ff\n"
        "    inet 192.168.122.10/24 brd 192.168.122.255 scope global br-ex\n"
        "    inet 169.254.0.2/17 brd 169.254.127.255 scope global br-ex\n"
    )

    # Failure outputs
    nmcli_missing = (
        "NAME                UUID                                  TYPE           DEVICE\n"
        "bond0               uuid456                               bond           bond0\n"
    )
    link_down = "6: br-ex: <BROADCAST,MULTICAST> mtu 1500 state DOWN\n"
    addr_no_ip = (
        "6: br-ex: <BROADCAST,MULTICAST,UP> mtu 1500 state UP\n"
        "    link/ether 52:54:00:3a:8a:3a brd ff:ff:ff:ff:ff:ff\n"
    )
    addr_wrong_subnet = (
        "6: br-ex: <BROADCAST,MULTICAST,UP> mtu 1500 state UP\n"
        "    link/ether 52:54:00:3a:8a:3a brd ff:ff:ff:ff:ff:ff\n"
        "    inet 10.0.0.5/24 brd 10.0.0.255 scope global br-ex\n"
    )

    scenario_passed = [
        RuleScenarioParams(
            "bridge healthy with 169.254.169.x IP",
            {
                "nmcli connection show": CmdOutput(nmcli_good),
                "ip link show br-ex": CmdOutput(link_good),
                "ip addr show br-ex": CmdOutput(addr_good_169_254_169),
            },
        ),
        RuleScenarioParams(
            "bridge healthy with 169.254.0.x IP",
            {
                "nmcli connection show": CmdOutput(nmcli_good),
                "ip link show br-ex": CmdOutput(link_good),
                "ip addr show br-ex": CmdOutput(addr_good_169_254_0),
            },
        ),
    ]

    scenario_failed = [
        RuleScenarioParams(
            "bridge not found",
            {
                "nmcli connection show": CmdOutput(nmcli_missing),
            },
            failed_msg="No OVS bridge interface (br-ex) found in NetworkManager",
        ),
        RuleScenarioParams(
            "bridge down",
            {
                "nmcli connection show": CmdOutput(nmcli_good),
                "ip link show br-ex": CmdOutput(link_down),
                "ip addr show br-ex": CmdOutput(addr_good_169_254_0),
            },
            failed_msg="Bridge interface issue: br-ex interface is DOWN",
        ),
        RuleScenarioParams(
            "no IP address",
            {
                "nmcli connection show": CmdOutput(nmcli_good),
                "ip link show br-ex": CmdOutput(link_good),
                "ip addr show br-ex": CmdOutput(addr_no_ip),
            },
            failed_msg="Bridge addressing issue: br-ex has no IP address (OVN not initialized)",
        ),
        RuleScenarioParams(
            "wrong IP subnet (not link-local)",
            {
                "nmcli connection show": CmdOutput(nmcli_good),
                "ip link show br-ex": CmdOutput(link_good),
                "ip addr show br-ex": CmdOutput(addr_wrong_subnet),
            },
            failed_msg=(
                "Bridge addressing issue: br-ex has unexpected IP addressing (10.0.0.5/24) - "
                "expected 169.254.x.x (link-local) for OVN"
            ),
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        """Test scenarios where rule should pass."""
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        """Test scenarios where rule should fail."""
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)


class TestBondVlanOvsAttachmentCheck(RuleTestBase):
    """Test BondVlanOvsAttachmentCheck rule."""

    tested_type = BondVlanOvsAttachmentCheck

    # Healthy outputs
    nmcli_active_with_vlan = "bond0.110:bond0.110\nbond0:bond0\n"
    nmcli_active_no_vlan = "bond0:bond0\n"
    ovs_ports_with_vlan = "bond0\nbond0.110\n"
    ovs_ports_missing_vlan = "bond0\n"

    scenario_prerequisite_not_fulfilled = [
        RuleScenarioParams(
            "no bond VLANs configured",
            {
                "nmcli -t -f NAME,DEVICE connection show --active": CmdOutput(nmcli_active_no_vlan),
            },
            failed_msg="No bond VLAN interfaces found on this node",
        ),
    ]

    scenario_prerequisite_fulfilled = [
        RuleScenarioParams(
            "bond VLANs exist",
            {
                "nmcli -t -f NAME,DEVICE connection show --active": CmdOutput(nmcli_active_with_vlan),
            },
        ),
    ]

    scenario_passed = [
        RuleScenarioParams(
            "bond VLAN attached to OVS",
            {
                "nmcli -t -f NAME,DEVICE connection show --active": CmdOutput(nmcli_active_with_vlan),
                "ovs-vsctl list-ports br-ex": CmdOutput(ovs_ports_with_vlan),
            },
        ),
    ]

    scenario_failed = [
        RuleScenarioParams(
            "bond VLANs exist but no OVS bridges",
            {
                "nmcli -t -f NAME,DEVICE connection show --active": CmdOutput(nmcli_active_with_vlan),
                "ovs-vsctl list-ports br-ex": CmdOutput("", return_code=1),
                "ovs-vsctl list-br": CmdOutput("", return_code=1),
            },
            failed_msg="Bond VLANs exist but no OVS bridges found - OVS may not be configured properly",
        ),
        RuleScenarioParams(
            "bond VLAN detached from OVS",
            {
                "nmcli -t -f NAME,DEVICE connection show --active": CmdOutput(nmcli_active_with_vlan),
                "ovs-vsctl list-ports br-ex": CmdOutput(ovs_ports_missing_vlan),
            },
            failed_msg="Bond VLAN detached from OVS bridge: bond0.110",
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_prerequisite_not_fulfilled)
    def test_prerequisite_not_fulfilled(self, scenario_params, tested_object):
        """Test scenarios where prerequisites are not fulfilled."""
        RuleTestBase.test_prerequisite_not_fulfilled(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_prerequisite_fulfilled)
    def test_prerequisite_fulfilled(self, scenario_params, tested_object):
        """Test scenarios where prerequisites are fulfilled."""
        RuleTestBase.test_prerequisite_fulfilled(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        """Test scenarios where rule should pass."""
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        """Test scenarios where rule should fail."""
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)


class TestOvnRoutingHealthCheck(RuleTestBase):
    """Test OvnRoutingHealthCheck rule."""

    tested_type = OvnRoutingHealthCheck

    # Healthy output
    routes_good = "default via 10.0.0.1 dev ovn-k8s-mp0\n10.244.0.0/16 dev ovn-k8s-mp0\n"

    # Broken output
    routes_missing = "default via 10.0.0.1 dev eth0\n10.0.0.0/24 dev eth0\n"

    scenario_passed = [
        RuleScenarioParams(
            "ovn routes present",
            {
                "ip route show": CmdOutput(routes_good),
            },
        ),
    ]

    scenario_failed = [
        RuleScenarioParams(
            "ovn routes missing",
            {
                "ip route show": CmdOutput(routes_missing),
            },
            failed_msg="No routes via ovn-k8s-mp0 interface found",
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        """Test scenarios where rule should pass."""
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        """Test scenarios where rule should fail."""
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)
