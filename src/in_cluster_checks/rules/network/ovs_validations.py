"""
OVS (Open vSwitch) network validations.

Ported from support/HealthChecks/flows/Network/ovs_validations.py
"""

import re

from in_cluster_checks.core.operations import DataCollector
from in_cluster_checks.core.rule import OrchestratorRule, PrerequisiteResult, Rule
from in_cluster_checks.core.rule_result import RuleResult
from in_cluster_checks.utils.enums import Objectives
from in_cluster_checks.utils.safe_cmd_string import SafeCmdString


class OvsInterfaceAndPortFound(Rule):
    """
    Verify that OVS interface and port are managed by NetworkManager.

    Checks for presence of:
    - ovs-if-phys (OVS interface)
    - ovs-port-phys (OVS port)

    These should be present in nmcli connection show output on nodes.
    """

    objective_hosts = [Objectives.ALL_NODES]
    unique_name = "ovs_interface_and_port_managed_by_network_manager"
    title = "Verify that ovs interface and port are managed by network manager"

    def run_rule(self):
        """
        Run rule check.

        Returns:
            RuleResult indicating if both ovs-if-phys and ovs-port-phys exist
        """
        # Get NetworkManager connections
        connections = self.get_output_from_run_cmd(SafeCmdString("nmcli connection show")).splitlines()

        # Check for ovs-if-phys and ovs-port-phys
        is_interface_exist = any(line.startswith("ovs-if-phys") for line in connections)
        is_port_exist = any(line.startswith("ovs-port-phys") for line in connections)

        # Build failure message if either is missing
        missing_items = []
        if not is_interface_exist:
            missing_items.append("ovs-if-phys doesn't exist in network manager connections")

        if not is_port_exist:
            missing_items.append("ovs-port-phys doesn't exist in network manager connections")

        if missing_items:
            return RuleResult.failed(".\n".join(missing_items) + ".")

        return RuleResult.passed()


class BondDnsCollector(DataCollector):
    """
    Collect DNS server information from all bond network interfaces.

    Discovers all bond interfaces dynamically and extracts IPv4 and IPv6
    DNS servers configured on each bond interface (including VLANs).
    Used by BondDnsServersComparison validator.
    """

    objective_hosts = [Objectives.ALL_NODES]

    def _extract_bond_devices(self, nmcli_output: str) -> list[str]:
        """
        Extract bond device names from nmcli connection show output.

        Args:
            nmcli_output: Output from 'nmcli -t -f TYPE,DEVICE connection show --active'
                         Format: "bond:bond0" or "bond:bond0.110"

        Returns:
            List of bond device names (e.g., ['bond0', 'bond0.110'])
        """
        bond_devices = []
        for line in nmcli_output.splitlines():
            if ":" in line:
                conn_type, device = line.split(":", 1)
                if conn_type == "bond" and device:
                    bond_devices.append(device)
        return bond_devices

    def _collect_dns_for_bonds(self, bond_devices: list[str]) -> dict:
        """
        Collect DNS server information for each bond interface.

        Args:
            bond_devices: List of bond device names (e.g., ['bond0', 'bond0.110'])

        Returns:
            Dictionary mapping bond interfaces to DNS configuration
            Example: {
                'bond0': {'ipv4': {'8.8.8.8'}, 'ipv6': set()},
                'bond0.110': {'ipv4': {'8.8.8.8'}, 'ipv6': set()}
            }
        """
        all_bonds_dns = {}
        for bond in bond_devices:
            cmd = SafeCmdString("nmcli conn show {bond}").format(bond=bond)
            rc, out, err = self.run_cmd(cmd)

            if rc != 0:
                self.add_to_rule_log(f"Failed to get DNS info for {bond}: {err.strip()}")
                continue

            # Extract DNS servers using regex
            ipv4_dns_servers = set(re.findall(r"ipv4\.dns:\s+([\d\.]+)", out))
            ipv6_dns_servers = set(re.findall(r"ipv6\.dns:\s+([\da-fA-F:]+)", out))

            all_bonds_dns[bond] = {"ipv4": ipv4_dns_servers, "ipv6": ipv6_dns_servers}

        return all_bonds_dns

    def collect_data(self, **kwargs) -> dict:
        """
        Collect DNS server data from all bond interfaces.

        Returns:
            Dictionary mapping bond interfaces to DNS configuration
            Example: {
                'bond0': {'ipv4': {'8.8.8.8'}, 'ipv6': set()},
                'bond0.110': {'ipv4': {'8.8.8.8'}, 'ipv6': set()},
                'bond1': {'ipv4': {'8.8.4.4'}, 'ipv6': set()}
            }
            Returns None if no bond connections exist
        """
        # Discover all bond interfaces (including VLANs)
        out = self.get_output_from_run_cmd(SafeCmdString("nmcli -t -f TYPE,DEVICE connection show --active"))

        bond_devices = self._extract_bond_devices(out)

        if not bond_devices:
            # No bond connections found (common on SNO or clusters without bonded interfaces)
            self.add_to_rule_log("No bond connections found on this node")
            return None

        all_bonds_dns = self._collect_dns_for_bonds(bond_devices)

        return all_bonds_dns if all_bonds_dns else None


class BondDnsServersComparison(OrchestratorRule):
    """
    Compare bond DNS servers across all cluster nodes.

    Ensures all nodes have consistent DNS server configuration for all
    bond interfaces including VLANs (bond0, bond0.110, bond1, etc.).
    Orchestrator validator - coordinates data collection across nodes.
    """

    objective_hosts = [Objectives.ORCHESTRATOR]
    unique_name = "bond_dns_servers_comparison"
    title = "Compare bond DNS servers across hosts"

    def run_rule(self):
        """
        Run rule check.

        Collects DNS data from all nodes and compares for consistency.

        Returns:
            RuleResult with status and optional message
        """
        # Collect DNS data from all nodes
        dns_servers = self.run_data_collector(BondDnsCollector)

        # Compare DNS across nodes
        return self._compare_dns_across_hosts(dns_servers)

    def _find_dns_mismatches_for_bond(self, nodes_with_bond: dict) -> tuple[list, list]:
        """
        Find DNS mismatches for a single bond interface across nodes.

        Args:
            nodes_with_bond: Dict of {hostname: {'ipv4': set, 'ipv6': set}}

        Returns:
            Tuple of (ipv4_mismatches, ipv6_mismatches)
            Each mismatch is a dict with 'host' and 'dns_server' keys
        """
        reference_host = next(iter(nodes_with_bond))
        reference_dns = nodes_with_bond[reference_host]

        ipv4_mismatch = []
        ipv6_mismatch = []

        for host, dns in nodes_with_bond.items():
            if dns["ipv4"] != reference_dns["ipv4"]:
                ipv4_mismatch.append({"host": host, "dns_server": dns["ipv4"]})

            if dns["ipv6"] != reference_dns["ipv6"]:
                ipv6_mismatch.append({"host": host, "dns_server": dns["ipv6"]})

        return ipv4_mismatch, ipv6_mismatch

    def _build_mismatch_message(
        self, bond_name: str, reference_host: str, reference_dns: dict, ipv4_mismatch: list, ipv6_mismatch: list
    ) -> str:
        """
        Build formatted mismatch message for a bond interface.

        Args:
            bond_name: Name of the bond interface
            reference_host: Hostname used as reference
            reference_dns: Reference DNS config {'ipv4': set, 'ipv6': set}
            ipv4_mismatch: List of IPv4 mismatches
            ipv6_mismatch: List of IPv6 mismatches

        Returns:
            Formatted multi-line string describing the mismatches
        """
        bond_mismatch = [f"Bond interface: {bond_name}"]

        if ipv4_mismatch:
            bond_mismatch.append(f"  IPv4 DNS mismatch (reference: {reference_host} = {list(reference_dns['ipv4'])}):")
            for mismatch in ipv4_mismatch:
                if mismatch["host"] != reference_host:
                    bond_mismatch.append(f"    {mismatch['host']}: {list(mismatch['dns_server'])}")

        if ipv6_mismatch:
            bond_mismatch.append(f"  IPv6 DNS mismatch (reference: {reference_host} = {list(reference_dns['ipv6'])}):")
            for mismatch in ipv6_mismatch:
                if mismatch["host"] != reference_host:
                    bond_mismatch.append(f"    {mismatch['host']}: {list(mismatch['dns_server'])}")

        return "\n".join(bond_mismatch)

    def _compare_dns_across_hosts(self, dns_servers: dict):
        """
        Compare DNS servers across all hosts for all bond interfaces.

        Args:
            dns_servers: Dictionary of {hostname: {bond_name: {'ipv4': set, 'ipv6': set}} or None}

        Returns:
            RuleResult with status and optional message
        """
        valid_dns_servers = {host: dns for host, dns in dns_servers.items() if dns is not None}

        if not valid_dns_servers:
            self.add_to_rule_log("No bond interfaces found on any node - validation not applicable")
            return RuleResult.not_applicable("No bond interfaces found on any node")

        all_bond_names = set()
        for host_bonds in valid_dns_servers.values():
            all_bond_names.update(host_bonds.keys())

        all_mismatches = []

        for bond_name in sorted(all_bond_names):
            nodes_with_bond = {
                host: bonds[bond_name] for host, bonds in valid_dns_servers.items() if bond_name in bonds
            }

            if not nodes_with_bond:
                continue

            ipv4_mismatch, ipv6_mismatch = self._find_dns_mismatches_for_bond(nodes_with_bond)

            if ipv4_mismatch or ipv6_mismatch:
                reference_host = next(iter(nodes_with_bond))
                reference_dns = nodes_with_bond[reference_host]
                mismatch_msg = self._build_mismatch_message(
                    bond_name, reference_host, reference_dns, ipv4_mismatch, ipv6_mismatch
                )
                all_mismatches.append(mismatch_msg)

        if all_mismatches:
            message = "DNS server mismatch found across nodes:\n\n" + "\n\n".join(all_mismatches)
            return RuleResult.failed(message)

        return RuleResult.passed(
            f"DNS configuration consistent across all nodes for {len(all_bond_names)} bond interfaces"
        )


class BondVlanOvsAttachmentCheck(Rule):
    """
    Verify bond VLAN interfaces are attached to OVS bridge.

    Validates that all bond VLAN interfaces (bond0.110, bond1.200, etc.)
    remain properly attached to OVS bridges. Detects when nmcli commands
    cause VLANs to detach from OVS.

    RCA symptom: "bond0.110 is removed from the bridge. This means bond 0.110
                  is no longer managed by OVS"
    Reference: https://access.redhat.com/solutions/6250271
    """

    objective_hosts = [Objectives.ALL_NODES]
    unique_name = "bond_vlan_ovs_attachment_check"
    title = "Verify bond VLAN interfaces are attached to OVS bridge"

    def is_prerequisite_fulfilled(self) -> PrerequisiteResult:
        """
        Check if bond VLAN interfaces exist on this node.

        Returns:
            PrerequisiteResult indicating if bond VLANs are present
        """
        bond_vlans = self._get_bond_vlans()
        if not bond_vlans:
            return PrerequisiteResult.not_met("No bond VLAN interfaces found on this node")

        return PrerequisiteResult.met()

    def run_rule(self) -> RuleResult:
        """
        Check if bond VLAN interfaces are attached to OVS bridge.

        Returns:
            RuleResult indicating bond VLAN attachment status
        """
        # Get bond VLANs (prerequisite ensures they exist)
        bond_vlans = self._get_bond_vlans()

        # Get OVS bridge ports
        ovs_ports = self._get_ovs_bridge_ports()
        if not ovs_ports:
            return RuleResult.failed("Bond VLANs exist but no OVS bridges found - OVS may not be configured properly")

        # Check for missing VLANs
        missing_vlans = [vlan for vlan in bond_vlans if vlan not in ovs_ports]

        if missing_vlans:
            return RuleResult.failed(f"Bond VLAN detached from OVS bridge: {', '.join(missing_vlans)}")

        return RuleResult.passed(f"All {len(bond_vlans)} bond VLAN interfaces are properly attached to OVS bridge")

    def _get_bond_vlans(self) -> list[str]:
        """
        Get active bond VLAN devices from NetworkManager.

        Returns:
            List of bond VLAN device names (e.g., ['bond0.110', 'bond1.200'])
            Empty list if none found or on error
        """
        connections = self.get_output_from_run_cmd(
            SafeCmdString("nmcli -t -f NAME,DEVICE connection show --active")
        ).splitlines()

        bond_vlans = []
        for line in connections:
            if ":" in line:
                parts = line.split(":", 1)
                if len(parts) == 2:
                    device = parts[1]
                    if "bond" in device and "." in device:
                        bond_vlans.append(device)

        return bond_vlans

    def _get_ovs_bridge_ports(self) -> list[str]:
        """
        Get list of ports attached to OVS bridge.

        Returns:
            List of OVS port names
            Empty list if no OVS bridges found or on error
        """
        rc, ports_out, _ = self.run_cmd(SafeCmdString("ovs-vsctl list-ports br-ex"))
        if rc != 0:
            rc_br, br_out, _ = self.run_cmd(SafeCmdString("ovs-vsctl list-br"))
            if rc_br != 0:
                return []

            bridges = br_out.strip().splitlines()
            if bridges:
                first_bridge = bridges[0]
                rc, ports_out, _ = self.run_cmd(
                    SafeCmdString("ovs-vsctl list-ports {bridge}").format(bridge=first_bridge)
                )
                if rc != 0:
                    return []

        return [port.strip() for port in ports_out.strip().splitlines()]


class OVNNodeBase(Rule):
    """
    Base class for OVN-Kubernetes node-level rules.

    Provides common prerequisite checking for rules that validate
    OVN-Kubernetes components on cluster nodes.
    """

    objective_hosts = [Objectives.ALL_NODES]

    def is_prerequisite_fulfilled(self) -> PrerequisiteResult:
        """
        Check if node is using OVN-Kubernetes networking.

        Checks for ovn-k8s-mp0 management port interface, which is always
        present on OVN-Kubernetes nodes and never on other CNI types.

        Returns:
            PrerequisiteResult indicating if OVN-Kubernetes is detected
        """
        # ovn-k8s-mp0 is hardcoded in OVN-Kubernetes (ManagementPortName constant)
        rc, _, _ = self.run_cmd(SafeCmdString("ip link show ovn-k8s-mp0"))

        if rc == 0:
            return PrerequisiteResult.met()

        return PrerequisiteResult.not_met(
            "Not applicable: OVN-Kubernetes not detected (ovn-k8s-mp0 interface not found)"
        )

    def _check_link_state(self, interface_name: str) -> tuple[bool, str]:
        """
        Check if network interface exists and is UP.

        Args:
            interface_name: Interface name to check

        Returns:
            Tuple of (success: bool, error_message: str)
        """
        rc, out, err = self.run_cmd(SafeCmdString("ip link show {iface}").format(iface=interface_name))

        if rc != 0:
            return False, f"{interface_name} interface does not exist: {err.strip()}"

        if "state UP" not in out and "state UNKNOWN" not in out:
            return False, f"{interface_name} interface is DOWN"

        return True, ""


class OvsPhysicalPortHealthCheck(OVNNodeBase):
    """
    Verify OVS physical port is UP and correctly configured (OVN-Kubernetes only).

    Validates that the physical network port attached to OVS:
    - Exists in NetworkManager (ovs-if-phys*)
    - Link state is UP
    - Has NO IP address (OVS ports forward traffic, bridge has IPs)

    Physical ports in OVS should NOT have IP addresses - they are just
    forwarding interfaces. The IP addressing is on the bridge (br-ex).

    RCA symptom: "ovs-if-phys0 interface does not start automatically after reboot"
    Reference: https://access.redhat.com/solutions/6250271
    """

    unique_name = "ovs_physical_port_health_check"
    title = "Verify OVS physical port is UP and has no IP"

    def run_rule(self) -> RuleResult:
        """
        Check OVS physical port health on this node.

        Returns:
            RuleResult indicating port health status
        """
        # Step 1: Find physical port name
        port_name = self._get_physical_port_name()
        if not port_name:
            return RuleResult.failed("No OVS physical port (ovs-if-phys*) found in NetworkManager")

        # Step 2: Check link state
        link_ok, link_msg = self._check_link_state(port_name)
        if not link_ok:
            return RuleResult.failed(f"Physical port issue: {link_msg}")

        # Step 3: Verify no IP address (ports should not have IPs)
        ip_ok, ip_msg = self._check_no_ip_address(port_name)
        if not ip_ok:
            return RuleResult.failed(f"Physical port configuration issue: {ip_msg}")

        return RuleResult.passed(f"OVS physical port {port_name} is UP with correct configuration (no IP)")

    def _get_physical_port_name(self) -> str:
        """
        Discover OVS physical port device name from NetworkManager.

        Returns:
            Device name (e.g., 'enp1s0') or connection name (e.g., 'ovs-if-phys0')
            Empty string if not found
        """
        connections = self.get_output_from_run_cmd(SafeCmdString("nmcli connection show")).splitlines()

        for line in connections:
            if "ovs-if-phys" in line:
                parts = line.split()
                if len(parts) >= 4:
                    device = parts[3]
                    return device if device != "--" else parts[0]

        return ""

    def _check_no_ip_address(self, port_name: str) -> tuple[bool, str]:
        """
        Verify physical port has NO IPv4 address.

        Physical OVS ports should only forward traffic, not have IPs.
        Link-local IPv6 addresses (fe80::) are acceptable.

        Args:
            port_name: Port interface name to check

        Returns:
            Tuple of (success: bool, error_message: str)
        """
        rc, out, err = self.run_cmd(SafeCmdString("ip addr show {iface}").format(iface=port_name))

        if rc != 0:
            return False, f"Cannot query {port_name} addressing: {err.strip()}"

        # Check for IPv4 address (should NOT exist on physical port)
        if "inet " in out:
            ip_match = re.search(r"inet (\S+)", out)
            ip_addr = ip_match.group(1) if ip_match else "unknown"
            return False, (
                f"{port_name} has IP address {ip_addr} - physical OVS ports should not have IPs "
                f"(IPs belong on the bridge interface)"
            )

        return True, ""


class OvsBridgeInterfaceHealthCheck(OVNNodeBase):
    """
    Verify OVS bridge is UP and has proper OVN IP configuration.

    Validates OVS bridge (br-ex) health:
    - Bridge interface exists in NetworkManager
    - Link state is UP
    - Link-local IP address is assigned (169.254.x.x)

    The bridge is where OVN assigns IPs, not the physical ports.
    Different OVN deployments use different link-local subnets within
    the 169.254.0.0/16 range (both 169.254.169.x/29 and 169.254.0.x/17
    are valid OVN configurations).
    """

    unique_name = "ovs_bridge_interface_health_check"
    title = "Verify OVS bridge is UP with OVN link-local IP"

    def run_rule(self) -> RuleResult:
        """
        Check OVS bridge health on this node.

        Returns:
            RuleResult indicating bridge health status
        """
        # Step 1: Find bridge interface name
        bridge_name = self._get_bridge_name()
        if not bridge_name:
            return RuleResult.failed("No OVS bridge interface (br-ex) found in NetworkManager")

        # Step 2: Check link state
        link_ok, link_msg = self._check_link_state(bridge_name)
        if not link_ok:
            return RuleResult.failed(f"Bridge interface issue: {link_msg}")

        # Step 3: Check IP addressing
        addr_ok, addr_msg = self._check_bridge_addressing(bridge_name)
        if not addr_ok:
            return RuleResult.failed(f"Bridge addressing issue: {addr_msg}")

        return RuleResult.passed(f"OVS bridge {bridge_name} is UP with proper OVN link-local IP")

    def _get_bridge_name(self) -> str:
        """
        Discover OVS bridge interface from NetworkManager.

        OVN assigns link-local IPs to the bridge interface (br-ex),
        not the physical port.

        Returns:
            Bridge device name (e.g., 'br-ex')
            Empty string if not found
        """
        connections = self.get_output_from_run_cmd(SafeCmdString("nmcli connection show")).splitlines()

        # Look for OVS bridge interface connection (ovs-if-br-ex)
        for line in connections:
            if "ovs-if-br-ex" in line:
                parts = line.split()
                if len(parts) >= 4:
                    device = parts[3]
                    return device if device != "--" else parts[0]

        # Fallback: look for br-ex bridge directly
        for line in connections:
            if line.startswith("br-ex"):
                parts = line.split()
                if len(parts) >= 4 and parts[2] == "ovs-bridge":
                    return "br-ex"

        return ""

    def _check_bridge_addressing(self, bridge_name: str) -> tuple[bool, str]:
        """
        Verify bridge has link-local IP address (169.254.x.x).

        Different OVN deployments use different subnets within the
        169.254.0.0/16 link-local range. Both 169.254.169.x/29 and
        169.254.0.x/17 are valid configurations.

        Args:
            bridge_name: Bridge interface name to check

        Returns:
            Tuple of (success: bool, error_message: str)
        """
        rc, out, err = self.run_cmd(SafeCmdString("ip addr show {iface}").format(iface=bridge_name))

        if rc != 0:
            return False, f"Cannot query {bridge_name} addressing: {err.strip()}"

        # Check for IPv4 address
        if "inet " not in out:
            return False, f"{bridge_name} has no IP address (OVN not initialized)"

        # Check for link-local subnet (169.254.0.0/16)
        # Accept any address in this range (different deployments use different subnets)
        if "inet 169.254." not in out:
            ip_match = re.search(r"inet (\S+)", out)
            ip_addr = ip_match.group(1) if ip_match else "unknown"
            return False, (
                f"{bridge_name} has unexpected IP addressing ({ip_addr}) - "
                f"expected 169.254.x.x (link-local) for OVN"
            )

        return True, ""


class OvnRoutingHealthCheck(OVNNodeBase):
    """
    Verify OVN-learned routes are present in routing table.

    Validates that routing table contains routes via OVN interfaces
    (ovn-k8s-mp0), which are essential for pod-to-pod communication
    and cluster networking.

    RCA symptom: "node not able to reach openshift API. Therefore the nodes
                  remains in 'NotReady' state"
    Reference: https://access.redhat.com/solutions/6250271
    """

    unique_name = "ovn_routing_health_check"
    title = "Verify OVN-learned routes are present"

    def run_rule(self) -> RuleResult:
        """
        Check for OVN routes in routing table.

        Returns:
            RuleResult indicating routing health status
        """
        routes = self.get_output_from_run_cmd(SafeCmdString("ip route show"))

        # Check for ovn-k8s management interface
        if "ovn-k8s-mp0" not in routes:
            return RuleResult.failed("No routes via ovn-k8s-mp0 interface found")

        return RuleResult.passed("OVN routes are present (routes via ovn-k8s-mp0 found)")
