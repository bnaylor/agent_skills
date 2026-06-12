"""
Unit tests for rasp-pi-janitor maintenance script.
"""

import builtins
import types
from unittest.mock import MagicMock, patch

import pytest

import pi_maintenance as pm

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class FakeSubprocessResult:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


# ---------------------------------------------------------------------------
# run_ssh
# ---------------------------------------------------------------------------

class TestRunSSH:
    def test_success(self):
        with patch("pi_maintenance.subprocess.run") as mock_run:
            mock_run.return_value = FakeSubprocessResult(
                returncode=0, stdout="ok\n", stderr=""
            )
            code, out, err = pm.run_ssh("host", "echo ok")
        assert code == 0
        assert out == "ok\n"
        assert err == ""

    def test_non_zero_exit(self):
        with patch("pi_maintenance.subprocess.run") as mock_run:
            mock_run.return_value = FakeSubprocessResult(
                returncode=1, stdout="", stderr="failed\n"
            )
            code, out, err = pm.run_ssh("host", "false")
        assert code == 1
        assert out == ""
        assert err == "failed\n"

    def test_timeout_returns_error(self):
        import subprocess
        with patch("pi_maintenance.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="ssh host", timeout=10)
            code, out, err = pm.run_ssh("host", "long cmd", timeout=10)
        assert code == -1
        assert out == ""
        assert "timed out" in err.lower()

    def test_exception_returns_error(self):
        with patch("pi_maintenance.subprocess.run") as mock_run:
            mock_run.side_effect = RuntimeError("boom")
            code, out, err = pm.run_ssh("host", "cmd")
        assert code == -1
        assert out == ""
        assert "boom" in err


# ---------------------------------------------------------------------------
# check_connectivity
# ---------------------------------------------------------------------------

class TestCheckConnectivity:
    def test_passwordless_sudo_succeeds(self):
        with patch("pi_maintenance.run_ssh") as mock_ssh:
            mock_ssh.return_value = (0, "", "")
            assert pm.check_connectivity("host") is True
            mock_ssh.assert_called_with("host", "sudo -n true")

    def test_password_sudo_falls_back(self):
        with patch("pi_maintenance.run_ssh") as mock_ssh:
            # First call fails (password prompt), second and third succeed
            mock_ssh.side_effect = [
                (1, "", "password prompt"),
                (0, "ok\n", ""),
                (0, "root\n", ""),
            ]
            assert pm.check_connectivity("host") is True
            assert mock_ssh.call_count == 3

    def test_unreachable_host(self):
        with patch("pi_maintenance.run_ssh") as mock_ssh:
            mock_ssh.side_effect = [
                (-1, "", "Connection refused"),
                (-1, "", "Connection refused"),
            ]
            assert pm.check_connectivity("host") is False


# ---------------------------------------------------------------------------
# preflight_checks
# ---------------------------------------------------------------------------

class TestPreflightChecks:
    def test_no_reboot_disk_ok_no_lock_pihole_present(self):
        boot_check_cmd = (
            'boot_dir="/boot"; '
            '[ -d "/boot/firmware" ] && boot_dir="/boot/firmware"; '
            'df -P / "$boot_dir" | tail -n +2 | awk \'{print $4}\''
        )
        responses = {
            "test -f /var/run/reboot-required && echo yes || echo no": (0, "no\n", ""),
            "cat /proc/sys/kernel/random/boot_id": (0, "initial-boot-id\n", ""),
            boot_check_cmd: (0, "500000 500000\n", ""),
            "sudo fuser /var/lib/dpkg/lock /var/lib/apt/lists/lock /var/cache/apt/archives/lock 2>/dev/null | wc -l": (0, "0\n", ""),
            "command -v pihole": (0, "/usr/local/bin/pihole\n", ""),
        }

        def fake_run_ssh(node, command, timeout=None):
            return responses.get(command, (-1, "", f"unexpected: {command}"))

        with patch("pi_maintenance.run_ssh", side_effect=fake_run_ssh):
            checks = pm.preflight_checks("host")

        assert checks["reboot_required"] is False
        assert checks["boot_id"] == "initial-boot-id"
        assert checks["disk_space_ok"] is True
        assert checks["apt_lock"] is False
        assert checks["pi_hole_available"] is True

    def test_disk_space_value_error(self):
        boot_check_cmd = (
            'boot_dir="/boot"; '
            '[ -d "/boot/firmware" ] && boot_dir="/boot/firmware"; '
            'df -P / "$boot_dir" | tail -n +2 | awk \'{print $4}\''
        )
        responses = {
            "test -f /var/run/reboot-required && echo yes || echo no": (0, "no\n", ""),
            "cat /proc/sys/kernel/random/boot_id": (0, "initial-boot-id\n", ""),
            boot_check_cmd: (0, "500000 abc\n", ""),  # Contains non-integer
            "sudo fuser /var/lib/dpkg/lock /var/lib/apt/lists/lock /var/cache/apt/archives/lock 2>/dev/null | wc -l": (0, "0\n", ""),
            "command -v pihole": (0, "/usr/local/bin/pihole\n", ""),
        }

        def fake_run_ssh(node, command, timeout=None):
            return responses.get(command, (-1, "", f"unexpected: {command}"))

        with patch("pi_maintenance.run_ssh", side_effect=fake_run_ssh):
            checks = pm.preflight_checks("host")

        assert checks["disk_space_ok"] is False

    def test_reboot_pending(self):
        with patch("pi_maintenance.run_ssh") as mock_ssh:
            mock_ssh.return_value = (0, "yes\n", "")
            checks = pm.preflight_checks("host")
        assert checks["reboot_required"] is True

    def test_pihole_missing(self):
        with patch("pi_maintenance.run_ssh") as mock_ssh:
            mock_ssh.return_value = (1, "", "not found")
            checks = pm.preflight_checks("host")
        assert checks["pi_hole_available"] is False


# ---------------------------------------------------------------------------
# run_updates
# ---------------------------------------------------------------------------

class TestRunUpdates:
    def test_dry_run(self):
        result = pm.run_updates("host", {}, dry_run=True)
        assert result["issues"] == ["Dry run mode - no changes made"]
        assert result["apt_update"] is False
        assert result["pi_hole_update"] is False

    def test_happy_path_no_dist_upgrade(self):
        preflight = {
            "reboot_required": False,
            "disk_space_ok": True,
            "apt_lock": False,
            "pi_hole_available": True,
        }

        responses = {
            "sudo apt-get update -y": (0, "", ""),
            "sudo apt-get upgrade -y": (0, "", ""),
            "sudo pihole -up": (0, "", ""),
            "sudo apt-get autoremove -y": (0, "", ""),
            "sudo apt-get clean": (0, "", ""),
            "test -f /var/run/reboot-required && echo yes || echo no": (0, "no\n", ""),
        }

        def fake_run_ssh(node, command, timeout=None):
            return responses.get(command, (-1, "", f"unexpected: {command}"))

        with patch("pi_maintenance.run_ssh", side_effect=fake_run_ssh), \
             patch("pi_maintenance.check_connectivity", return_value=True):
            result = pm.run_updates("host", preflight, dist_upgrade=False)

        assert result["apt_update"] is True
        assert result["apt_upgrade"] is True
        assert result["apt_dist_upgrade"] is False
        assert result["apt_autoremove"] is True
        assert result["apt_clean"] is True
        assert result["pi_hole_update"] is True
        assert result["reboot_triggered"] is False
        assert result["issues"] == []

    def test_happy_path_with_dist_upgrade(self):
        preflight = {
            "reboot_required": False,
            "disk_space_ok": True,
            "apt_lock": False,
            "pi_hole_available": True,
        }

        responses = {
            "sudo apt-get update -y": (0, "", ""),
            "sudo apt-get upgrade -y": (0, "", ""),
            "sudo apt-get dist-upgrade -y": (0, "", ""),
            "sudo pihole -up": (0, "", ""),
            "sudo apt-get autoremove -y": (0, "", ""),
            "sudo apt-get clean": (0, "", ""),
            "test -f /var/run/reboot-required && echo yes || echo no": (0, "no\n", ""),
        }

        def fake_run_ssh(node, command, timeout=None):
            return responses.get(command, (-1, "", f"unexpected: {command}"))

        with patch("pi_maintenance.run_ssh", side_effect=fake_run_ssh), \
             patch("pi_maintenance.check_connectivity", return_value=True):
            result = pm.run_updates("host", preflight, dist_upgrade=True)

        assert result["apt_update"] is True
        assert result["apt_upgrade"] is True
        assert result["apt_dist_upgrade"] is True
        assert result["apt_autoremove"] is True
        assert result["apt_clean"] is True
        assert result["pi_hole_update"] is True
        assert result["reboot_triggered"] is False
        assert result["issues"] == []

    def test_apt_upgrade_failure(self):
        preflight = {
            "pi_hole_available": True,
        }

        def fake_run_ssh(node, command, timeout=None):
            if command == "sudo apt-get update -y":
                return (0, "", "")
            if command == "sudo apt-get upgrade -y":
                return (1, "", "upgrade failed")
            return (0, "", "")

        with patch("pi_maintenance.run_ssh", side_effect=fake_run_ssh):
            result = pm.run_updates("host", preflight)

        assert result["apt_upgrade"] is False
        assert any("upgrade failed" in issue for issue in result["issues"])

    def test_pihole_update_failure(self):
        preflight = {
            "pi_hole_available": True,
        }

        def fake_run_ssh(node, command, timeout=None):
            if command == "sudo apt-get update -y":
                return (0, "", "")
            if command == "sudo apt-get upgrade -y":
                return (0, "", "")
            if command == "sudo pihole -up":
                return (1, "", "pihole update failed")
            return (0, "", "")

        with patch("pi_maintenance.run_ssh", side_effect=fake_run_ssh):
            result = pm.run_updates("host", preflight)

        assert result["pi_hole_update"] is False
        assert any("pihole -up failed" in issue for issue in result["issues"])

    def test_reboot_triggered_and_succeeds(self):
        preflight = {
            "pi_hole_available": True,
            "boot_id": "old-boot-id"
        }

        reboot_issued = {}

        def fake_run_ssh(node, command, timeout=None):
            if command == "sudo apt-get update -y":
                return (0, "", "")
            if command == "sudo apt-get upgrade -y":
                return (0, "", "")
            if command == "sudo pihole -up":
                return (0, "", "")
            if command == "sudo apt-get autoremove -y":
                return (0, "", "")
            if command == "sudo apt-get clean":
                return (0, "", "")
            if command == "test -f /var/run/reboot-required && echo yes || echo no":
                return (0, "yes\n", "")
            if command == "sudo reboot":
                reboot_issued["called"] = True
                return (0, "", "Connection closed")
            if command == "cat /proc/sys/kernel/random/boot_id":
                return (0, "new-boot-id\n", "")
            return (0, "", "")

        with patch("pi_maintenance.run_ssh", side_effect=fake_run_ssh), \
             patch("pi_maintenance.check_connectivity", return_value=True), \
             patch("time.sleep", return_value=None):
            result = pm.run_updates("host", preflight)

        assert reboot_issued.get("called") is True
        assert result["reboot_triggered"] is True
        assert result["reboot_success"] is True

    def test_reboot_triggered_but_node_never_returns(self):
        preflight = {
            "pi_hole_available": True,
            "boot_id": "old-boot-id"
        }

        def fake_run_ssh(node, command, timeout=None):
            if command == "sudo apt-get update -y":
                return (0, "", "")
            if command == "sudo apt-get upgrade -y":
                return (0, "", "")
            if command == "sudo pihole -up":
                return (0, "", "")
            if command == "sudo apt-get autoremove -y":
                return (0, "", "")
            if command == "sudo apt-get clean":
                return (0, "", "")
            if command == "test -f /var/run/reboot-required && echo yes || echo no":
                return (0, "yes\n", "")
            if command == "sudo reboot":
                return (0, "", "Connection closed")
            if command == "cat /proc/sys/kernel/random/boot_id":
                return (-1, "", "Connection timed out")
            return (0, "", "")

        with patch("pi_maintenance.run_ssh", side_effect=fake_run_ssh), \
             patch("pi_maintenance.check_connectivity", return_value=False), \
             patch("time.sleep", return_value=None):
            result = pm.run_updates("host", preflight)

        assert result["reboot_triggered"] is True
        assert result["reboot_success"] is False
        assert any("did not come back" in issue for issue in result["issues"])

    def test_pihole_skipped_when_cli_missing(self):
        preflight = {
            "pi_hole_available": False,
        }

        def fake_run_ssh(node, command, timeout=None):
            if command == "sudo apt-get update -y":
                return (0, "", "")
            if command == "sudo apt-get upgrade -y":
                return (0, "", "")
            if command == "sudo apt-get autoremove -y":
                return (0, "", "")
            if command == "sudo apt-get clean":
                return (0, "", "")
            if command == "test -f /var/run/reboot-required && echo yes || echo no":
                return (0, "no\n", "")
            return (0, "", "")

        with patch("pi_maintenance.run_ssh", side_effect=fake_run_ssh):
            result = pm.run_updates("host", preflight)

        assert result["pi_hole_update"] is False
        assert any("Pi-hole CLI not found" in issue for issue in result["issues"])


# ---------------------------------------------------------------------------
# postflight_checks
# ---------------------------------------------------------------------------

class TestPostflightChecks:
    def test_uptime_and_pihole_running(self):
        boot_check_cmd_post = (
            'boot_dir="/boot"; '
            '[ -d "/boot/firmware" ] && boot_dir="/boot/firmware"; '
            'df -h / "$boot_dir" | tail -n +2'
        )
        responses = {
            "uptime -p": (0, "up 1 hour\n", ""),
            "systemctl is-active pihole-FTL 2>/dev/null || pihole status 2>/dev/null | head -n1": (0, "active\n", ""),
            boot_check_cmd_post: (0, "/dev/root 14G 5.3G 8.3G 40% /\n", ""),
        }

        def fake_run_ssh(node, command, timeout=None):
            return responses.get(command, (0, "", ""))

        with patch("pi_maintenance.run_ssh", side_effect=fake_run_ssh):
            checks = pm.postflight_checks("host")

        assert checks["uptime"] == "up 1 hour"
        assert checks["pi_hole_running"] is True
        assert "40%" in checks["disk_usage"]

    def test_pihole_status_not_found(self):
        boot_check_cmd_post = (
            'boot_dir="/boot"; '
            '[ -d "/boot/firmware" ] && boot_dir="/boot/firmware"; '
            'df -h / "$boot_dir" | tail -n +2'
        )
        responses = {
            "uptime -p": (0, "up 1 hour\n", ""),
            "systemctl is-active pihole-FTL 2>/dev/null || pihole status 2>/dev/null | head -n1": (1, "", ""),
            boot_check_cmd_post: (0, "/dev/root 14G 5.3G 8.3G 40% /\n", ""),
        }

        def fake_run_ssh(node, command, timeout=None):
            return responses.get(command, (0, "", ""))

        with patch("pi_maintenance.run_ssh", side_effect=fake_run_ssh):
            checks = pm.postflight_checks("host")

        assert checks["pi_hole_running"] is False
        assert checks["uptime"] == "up 1 hour"


# ---------------------------------------------------------------------------
# main & process_node
# ---------------------------------------------------------------------------

class TestMain:
    def test_single_node_output(self, capsys):
        fake_preflight = {
            "reboot_required": False,
            "disk_space_ok": True,
            "apt_lock": False,
            "pi_hole_available": True,
        }
        fake_run_results = {
            "apt_update": True,
            "apt_upgrade": True,
            "apt_dist_upgrade": False,
            "apt_autoremove": True,
            "apt_clean": True,
            "pi_hole_update": True,
            "reboot_triggered": False,
            "reboot_success": False,
            "issues": [],
            "node": "host",
        }
        fake_postflight = {
            "uptime": "up 1 minute",
            "pi_hole_running": True,
            "disk_usage": "/dev/root 14G 5.3G 8.3G 40% /",
        }

        fake_args = types.SimpleNamespace(
            nodes=["host"], dry_run=False, parallel=False, dist_upgrade=False
        )

        with patch("pi_maintenance.check_connectivity", return_value=True), \
             patch("pi_maintenance.preflight_checks", return_value=fake_preflight), \
             patch("pi_maintenance.run_updates", return_value=fake_run_results), \
             patch("pi_maintenance.postflight_checks", return_value=fake_postflight), \
             patch("pi_maintenance.argparse.ArgumentParser.parse_args", return_value=fake_args):
            pm.main()

        captured = capsys.readouterr()
        assert "host" in captured.out
        assert "Apt update: OK" in captured.out
        assert "Pi-hole update: OK" in captured.out
        assert "Maintenance complete" in captured.out

    def test_parallel_nodes_output(self, capsys):
        fake_preflight = {
            "reboot_required": False,
            "disk_space_ok": True,
            "apt_lock": False,
            "pi_hole_available": True,
        }
        fake_run_results = {
            "apt_update": True,
            "apt_upgrade": True,
            "apt_dist_upgrade": False,
            "apt_autoremove": True,
            "apt_clean": True,
            "pi_hole_update": True,
            "reboot_triggered": False,
            "reboot_success": False,
            "issues": [],
            "node": "host1",
        }
        fake_postflight = {
            "uptime": "up 1 minute",
            "pi_hole_running": True,
            "disk_usage": "/dev/root 14G 5.3G 8.3G 40% /",
        }

        fake_args = types.SimpleNamespace(
            nodes=["host1", "host2"], dry_run=False, parallel=True, dist_upgrade=False
        )

        with patch("pi_maintenance.check_connectivity", return_value=True), \
             patch("pi_maintenance.preflight_checks", return_value=fake_preflight), \
             patch("pi_maintenance.run_updates", return_value=fake_run_results), \
             patch("pi_maintenance.postflight_checks", return_value=fake_postflight), \
             patch("pi_maintenance.argparse.ArgumentParser.parse_args", return_value=fake_args):
            pm.main()

        captured = capsys.readouterr()
        assert "Processing 2 nodes in parallel..." in captured.out
        assert "host1" in captured.out
        assert "host2" in captured.out
        assert "Maintenance complete" in captured.out

    def test_connectivity_failure_skips_rest(self, capsys):
        fake_args = types.SimpleNamespace(
            nodes=["host"], dry_run=False, parallel=False, dist_upgrade=False
        )
        with patch("pi_maintenance.check_connectivity", return_value=False), \
             patch("pi_maintenance.argparse.ArgumentParser.parse_args", return_value=fake_args), \
             pytest.raises(SystemExit) as excinfo:
            pm.main()

        captured = capsys.readouterr()
        assert "FAILED" in captured.out
        assert excinfo.value.code == 1

    def test_dist_upgrade_flag_passed(self):
        fake_args = types.SimpleNamespace(
            nodes=["host"], dry_run=True, parallel=False, dist_upgrade=True
        )
        fake_preflight = {
            "reboot_required": False,
            "disk_space_ok": True,
            "apt_lock": False,
            "pi_hole_available": True,
            "boot_id": "mock-boot-id"
        }
        fake_postflight = {
            "uptime": "up 1 minute",
            "pi_hole_running": True,
            "disk_usage": "/dev/root 14G 5.3G 8.3G 40% /",
        }
        with patch("pi_maintenance.check_connectivity", return_value=True), \
             patch("pi_maintenance.preflight_checks", return_value=fake_preflight), \
             patch("pi_maintenance.run_updates") as mock_run_updates, \
             patch("pi_maintenance.postflight_checks", return_value=fake_postflight), \
             patch("pi_maintenance.argparse.ArgumentParser.parse_args", return_value=fake_args):
            try:
                pm.main()
            except SystemExit:
                pass

        mock_run_updates.assert_called_once()
        _, kwargs = mock_run_updates.call_args
        assert kwargs["dist_upgrade"] is True
