"""
Tests for HW validations ported from healthcheck-backup.

Adapted from healthcheck-backup/HealthChecks/tests/pytest/flows/HW/test_hw_validations.py
"""

import pytest

from in_cluster_checks import global_config
from in_cluster_checks.rules.hw.hw_validations import (
    BasicFreeMemoryValidation,
    CheckDiskUsage,
    CPUfreqScalingGovernorValidation,
    CpuSpeedValidation,
    HwSysClockCompare,
    TemperatureValidation,
)
from in_cluster_checks.utils.enums import Status
from profiles.loader import ProfileLoader
from profiles.profile import Profiles
from tests.pytest_tools.test_operator_base import CmdOutput
from tests.pytest_tools.test_rule_base import (
    RuleTestBase,
    RuleScenarioParams,
)


class TestCheckDiskUsage(RuleTestBase):
    """Test CheckDiskUsage validator."""

    tested_type = CheckDiskUsage

    # df -hT output includes filesystem Type column
    df_output_ok = """Filesystem     Type      Size  Used Avail Use% Mounted on
/dev/sda1      ext4       50G   30G   18G  63% /
/dev/sdb1      xfs       100G   50G   46G  53% /data
"""

    df_output_warn = """Filesystem     Type      Size  Used Avail Use% Mounted on
/dev/sda1      ext4       50G   42G    6G  88% /
"""

    df_output_error = """Filesystem     Type      Size  Used Avail Use% Mounted on
/dev/sda1      ext4       50G   47G    1G  98% /
"""

    # Real-world scenario with composefs, efivarfs - should pass since real disks are healthy
    df_output_with_pseudo_fs = """Filesystem     Type      Size  Used Avail Use% Mounted on
/dev/sda4      xfs       430G   12G  419G   3% /etc
/dev/sdb1      xfs       430G  3.6G  426G   1% /var/lib/etcd
/dev/sdb2      xfs       465G   11G  454G   3% /var/lib/prometheus/data
/dev/sda5      xfs       464G   49G  416G  11% /var/lib/containers
/dev/sda3      ext4      350M  127M  201M  39% /boot
"""

    df_cmd = "df -hT -x tmpfs -x devtmpfs -x overlay -x composefs -x efivarfs -x squashfs -x iso9660"

    scenario_passed = [
        RuleScenarioParams(
            "disk usage below warning threshold",
            {df_cmd: CmdOutput(df_output_ok)},
        ),
        RuleScenarioParams(
            "real disks healthy despite pseudo-fs at 100% (composefs filtered out)",
            {df_cmd: CmdOutput(df_output_with_pseudo_fs)},
        ),
    ]

    scenario_warning = [
        RuleScenarioParams(
            "disk usage above warning threshold (80-90%)",
            {df_cmd: CmdOutput(df_output_warn)},
            failed_msg="Disk usage warning:\n/dev/sda1 (mounted on: /) usage is 88% (threshold: 80%)",
        ),
    ]

    scenario_failed = [
        RuleScenarioParams(
            "disk usage above error threshold (>90%)",
            {df_cmd: CmdOutput(df_output_error)},
            failed_msg="Disk usage critical:\n/dev/sda1 (mounted on: /) usage is 98% (threshold: 90%)",
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_warning)
    def test_scenario_warning(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_warning(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)


class TestBasicFreeMemoryValidation(RuleTestBase):
    """Test BasicFreeMemoryValidation validator."""

    tested_type = BasicFreeMemoryValidation

    scenario_passed = [
        RuleScenarioParams(
            "sufficient free memory (20%)",
            {
                "cat /proc/meminfo |grep MemTotal": CmdOutput("MemTotal:       100000 kB"),
                "cat /proc/meminfo |grep MemAvailable": CmdOutput("MemAvailable:    20000 kB"),
                "cat /proc/meminfo |grep HugePages_Total": CmdOutput("HugePages_Total:     0"),
                "cat /proc/meminfo |grep HugePages_Free": CmdOutput("HugePages_Free:      0"),
            },
        ),
    ]

    scenario_failed = [
        RuleScenarioParams(
            "insufficient free memory (10%)",
            {
                "cat /proc/meminfo |grep MemTotal": CmdOutput("MemTotal:       100000 kB"),
                "cat /proc/meminfo |grep MemAvailable": CmdOutput("MemAvailable:    10000 kB"),
                "cat /proc/meminfo |grep HugePages_Total": CmdOutput("HugePages_Total:     0"),
                "cat /proc/meminfo |grep HugePages_Free": CmdOutput("HugePages_Free:      0"),
            },
            failed_msg="Available memory is only 10.0%",
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)


class TestCPUfreqScalingGovernorValidation(RuleTestBase):
    """Test CPUfreqScalingGovernorValidation validator."""

    tested_type = CPUfreqScalingGovernorValidation

    lscpu_4_cpus = "CPU(s):              4"

    # Command outputs for non-performance governors
    _non_performance_cmds = {
        "sudo /bin/lscpu|grep '^CPU(s):'": CmdOutput(lscpu_4_cpus),
        "sudo cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor": CmdOutput("performance"),
        "sudo cat /sys/devices/system/cpu/cpu1/cpufreq/scaling_governor": CmdOutput("powersave"),
        "sudo cat /sys/devices/system/cpu/cpu2/cpufreq/scaling_governor": CmdOutput("performance"),
        "sudo cat /sys/devices/system/cpu/cpu3/cpufreq/scaling_governor": CmdOutput("ondemand"),
    }

    @pytest.fixture(autouse=True)
    def setup_profiles(self):
        """Load profiles for testing."""
        profiles = Profiles()
        ProfileLoader.load(profiles)
        global_config.profiles_hierarchy = profiles
        # Default to general profile
        global_config.active_profile = "general"
        yield profiles

    scenario_passed = [
        RuleScenarioParams(
            "all CPUs set to performance",
            {
                "sudo /bin/lscpu|grep '^CPU(s):'": CmdOutput(lscpu_4_cpus),
                "sudo cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor": CmdOutput("performance"),
                "sudo cat /sys/devices/system/cpu/cpu1/cpufreq/scaling_governor": CmdOutput("performance"),
                "sudo cat /sys/devices/system/cpu/cpu2/cpufreq/scaling_governor": CmdOutput("performance"),
                "sudo cat /sys/devices/system/cpu/cpu3/cpufreq/scaling_governor": CmdOutput("performance"),
            },
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    def test_telco_profile_returns_failed(self, tested_object):
        """Test that telco profiles return FAILED when CPUs not set to performance."""
        global_config.active_profile = "telco-base"

        scenario = RuleScenarioParams(
            "telco profile - non-performance CPUs",
            self._non_performance_cmds,
        )

        self._init_validation_object(tested_object, scenario)

        with self._apply_patches(scenario, tested_object):
            result = tested_object.run_rule()

        assert result.status == Status.FAILED
        assert "CPU Governor not set to PERFORMANCE" in result.message
        assert "CPU1 -> powersave" in result.message
        assert "CPU3 -> ondemand" in result.message

    def test_telco_derivative_profile_returns_failed(self, tested_object):
        """Test that telco derivative profiles (e.g., rh-nokia) return FAILED."""
        global_config.active_profile = "rh-nokia"

        scenario = RuleScenarioParams(
            "rh-nokia profile - non-performance CPUs",
            self._non_performance_cmds,
        )

        self._init_validation_object(tested_object, scenario)

        with self._apply_patches(scenario, tested_object):
            result = tested_object.run_rule()

        assert result.status == Status.FAILED
        assert "CPU Governor not set to PERFORMANCE" in result.message

    def test_non_telco_profile_returns_warning(self, tested_object):
        """Test that non-telco profiles return WARNING when CPUs not set to performance."""
        global_config.active_profile = "general"

        scenario = RuleScenarioParams(
            "general profile - non-performance CPUs",
            self._non_performance_cmds,
        )

        self._init_validation_object(tested_object, scenario)

        with self._apply_patches(scenario, tested_object):
            result = tested_object.run_rule()

        assert result.status == Status.WARNING
        assert "CPU Governor not set to PERFORMANCE" in result.message
        assert "CPU1 -> powersave" in result.message
        assert "CPU3 -> ondemand" in result.message

    def test_ai_profile_returns_warning(self, tested_object):
        """Test that ai-base profile returns WARNING (not telco-related)."""
        global_config.active_profile = "ai-base"

        scenario = RuleScenarioParams(
            "ai-base profile - non-performance CPUs",
            self._non_performance_cmds,
        )

        self._init_validation_object(tested_object, scenario)

        with self._apply_patches(scenario, tested_object):
            result = tested_object.run_rule()

        assert result.status == Status.WARNING
        assert "CPU Governor not set to PERFORMANCE" in result.message


class TestTemperatureValidation(RuleTestBase):
    """Test TemperatureValidation validator."""

    tested_type = TemperatureValidation

    scenario_passed = [
        RuleScenarioParams(
            "all temperatures below 100",
            {
                "ls /sys/class/thermal/thermal_zone*/temp": CmdOutput(
                    "/sys/class/thermal/thermal_zone0/temp\n/sys/class/thermal/thermal_zone1/temp"
                ),
                "cat /sys/class/thermal/thermal_zone0/type": CmdOutput("x86_pkg_temp"),
                "cat /sys/class/thermal/thermal_zone0/temp": CmdOutput("55000"),
                "cat /sys/class/thermal/thermal_zone1/type": CmdOutput("acpitz"),
                "cat /sys/class/thermal/thermal_zone1/temp": CmdOutput("27800"),
            },
        ),
    ]

    scenario_failed = [
        RuleScenarioParams(
            "temperature above 100",
            {
                "ls /sys/class/thermal/thermal_zone*/temp": CmdOutput(
                    "/sys/class/thermal/thermal_zone0/temp\n/sys/class/thermal/thermal_zone1/temp"
                ),
                "cat /sys/class/thermal/thermal_zone0/type": CmdOutput("x86_pkg_temp"),
                "cat /sys/class/thermal/thermal_zone0/temp": CmdOutput("105000"),
                "cat /sys/class/thermal/thermal_zone1/type": CmdOutput("acpitz"),
                "cat /sys/class/thermal/thermal_zone1/temp": CmdOutput("27800"),
            },
            failed_msg="Temperature sensor(s) exceeded threshold (100°C):\nx86_pkg_temp: 105.0°C",
        ),
    ]

    scenario_unexpected_system_output = [
        RuleScenarioParams(
            "invalid temperature value",
            {
                "ls /sys/class/thermal/thermal_zone*/temp": CmdOutput(
                    "/sys/class/thermal/thermal_zone0/temp"
                ),
                "cat /sys/class/thermal/thermal_zone0/type": CmdOutput("x86_pkg_temp"),
                "cat /sys/class/thermal/thermal_zone0/temp": CmdOutput("invalid_value"),
            },
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_unexpected_system_output)
    def test_scenario_unexpected_system_output(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_unexpected_system_output(self, scenario_params, tested_object)


class TestCpuSpeedValidation(RuleTestBase):
    """Test CpuSpeedValidation validator."""

    tested_type = CpuSpeedValidation

    lscpu_4_cpus = "CPU(s):              4"
    lscpu_2_cpus = "CPU(s):              2"

    scenario_passed = [
        RuleScenarioParams(
            "all CPUs running at max speed",
            {
                "test -f /sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq": CmdOutput(""),
                "sudo /bin/lscpu|grep '^CPU(s):'": CmdOutput(lscpu_4_cpus),
                "cat /sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq": CmdOutput("2400000"),
                "cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq": CmdOutput("2400000"),
                "cat /sys/devices/system/cpu/cpu1/cpufreq/cpuinfo_max_freq": CmdOutput("2400000"),
                "cat /sys/devices/system/cpu/cpu1/cpufreq/scaling_cur_freq": CmdOutput("2400000"),
                "cat /sys/devices/system/cpu/cpu2/cpufreq/cpuinfo_max_freq": CmdOutput("2400000"),
                "cat /sys/devices/system/cpu/cpu2/cpufreq/scaling_cur_freq": CmdOutput("2400000"),
                "cat /sys/devices/system/cpu/cpu3/cpufreq/cpuinfo_max_freq": CmdOutput("2400000"),
                "cat /sys/devices/system/cpu/cpu3/cpufreq/scaling_cur_freq": CmdOutput("2400000"),
            },
        ),
    ]

    scenario_prerequisite_not_fulfilled = [
        RuleScenarioParams(
            "cpufreq files not available (VM)",
            {
                "test -f /sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq": CmdOutput("", return_code=1),
            },
        ),
    ]

    scenario_failed = [
        RuleScenarioParams(
            "some CPUs not at max speed",
            {
                "test -f /sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq": CmdOutput(""),
                "sudo /bin/lscpu|grep '^CPU(s):'": CmdOutput(lscpu_2_cpus),
                "cat /sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq": CmdOutput("2400000"),
                "cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq": CmdOutput("1200000"),
                "cat /sys/devices/system/cpu/cpu1/cpufreq/cpuinfo_max_freq": CmdOutput("2400000"),
                "cat /sys/devices/system/cpu/cpu1/cpufreq/scaling_cur_freq": CmdOutput("2400000"),
            },
            failed_msg="Some CPUs are not running on maximum speed.\nPlease note that the compute is not configured with maximum performance and therefore\nwe might be facing performance impact on the VM's/containers that are hosted in this compute.\n\nCPU ID 0 has speed of 1200000.0 KHz (expected max: 2400000.0 KHz)",
        ),
    ]

    scenario_unexpected_system_output = [
        RuleScenarioParams(
            "cpuinfo_max_freq returns non-numeric value",
            {
                "test -f /sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq": CmdOutput(""),
                "sudo /bin/lscpu|grep '^CPU(s):'": CmdOutput(lscpu_2_cpus),
                "cat /sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq": CmdOutput("invalid"),
                "cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq": CmdOutput("2400000"),
                "cat /sys/devices/system/cpu/cpu1/cpufreq/cpuinfo_max_freq": CmdOutput("2400000"),
                "cat /sys/devices/system/cpu/cpu1/cpufreq/scaling_cur_freq": CmdOutput("2400000"),
            },
        ),
        RuleScenarioParams(
            "scaling_cur_freq returns non-numeric value",
            {
                "test -f /sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq": CmdOutput(""),
                "sudo /bin/lscpu|grep '^CPU(s):'": CmdOutput(lscpu_2_cpus),
                "cat /sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq": CmdOutput("2400000"),
                "cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq": CmdOutput("invalid"),
                "cat /sys/devices/system/cpu/cpu1/cpufreq/cpuinfo_max_freq": CmdOutput("2400000"),
                "cat /sys/devices/system/cpu/cpu1/cpufreq/scaling_cur_freq": CmdOutput("2400000"),
            },
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_prerequisite_not_fulfilled)
    def test_prerequisite_not_fulfilled(self, scenario_params, tested_object):
        RuleTestBase.test_prerequisite_not_fulfilled(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_unexpected_system_output)
    def test_scenario_unexpected_system_output(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_unexpected_system_output(self, scenario_params, tested_object)


class TestHwSysClockCompare(RuleTestBase):
    """Test HwSysClockCompare validator."""

    tested_type = HwSysClockCompare

    hwclock_ok = "2024-02-08 18:12:44.404676-05:00"
    sysclock_ok = "2024-02-08 18:12:45 -0500"

    hwclock_diff = "2024-02-08 18:12:44.404676-05:00"
    sysclock_diff = "2024-02-08 20:12:45 -0500"  # 2 hours difference

    scenario_passed = [
        RuleScenarioParams(
            "clocks within acceptable range",
            {
                "sudo hwclock": CmdOutput(hwclock_ok),
                "date +'%Y-%m-%d %H:%M:%S %z'": CmdOutput(sysclock_ok),
            },
        ),
    ]

    scenario_failed = [
        RuleScenarioParams(
            "clocks differ significantly",
            {
                "sudo hwclock": CmdOutput(hwclock_diff),
                "date +'%Y-%m-%d %H:%M:%S %z'": CmdOutput(sysclock_diff),
            },
            failed_msg="There is a significant difference between the hw clock (RTC) and the system clock.\nHW Clock:     2024-02-08 18:12:44.404676-05:00\nSystem Clock: 2024-02-08 20:12:45-05:00\nCriteria: 3600.0 seconds",
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)
