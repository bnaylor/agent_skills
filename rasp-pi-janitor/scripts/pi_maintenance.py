#!/usr/bin/env python3
"""
Raspberry Pi + Pi-hole maintenance automation.
"""

import subprocess
import sys
import time
import argparse
import concurrent.futures
import io
from typing import List, Tuple

def run_ssh(node: str, command: str, timeout: int = 300) -> Tuple[int, str, str]:
    """Run a command on a remote node via SSH."""
    full_cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", node, command]
    try:
        result = subprocess.run(
            full_cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"Command timed out after {timeout}s"
    except Exception as e:
        return -1, "", str(e)

def check_connectivity(node: str) -> bool:
    """Verify SSH connectivity and sudo privileges."""
    code, out, err = run_ssh(node, "sudo -n true")
    if code == 0:
        return True
    # If sudo requires password, try a non-interactive check
    code, out, err = run_ssh(node, "echo ok")
    if code != 0:
        return False
    code, out, err = run_ssh(node, "sudo whoami")
    return code == 0 and "root" in out

def kernel_reboot_needed(node: str) -> bool:
    """Detect a staged kernel update that requires a reboot.

    Raspberry Pi OS does not create /var/run/reboot-required on kernel
    updates, so compare the running kernel (uname -r) against the newest
    installed kernel in /lib/modules (matching flavor).
    """
    cmd = (
        'running=$(uname -r); '
        'flavor=${running##*-rpi-}; '
        'newest=$(ls -1v /lib/modules | grep "rpi-${flavor}$" | tail -n1); '
        'if [ "$running" = "$newest" ]; then echo no; else echo yes; fi'
    )
    code, out, _ = run_ssh(node, cmd)
    return code == 0 and out.strip() == "yes"


def preflight_checks(node: str) -> dict:
    """Run pre-flight checks."""
    checks = {
        "reboot_required": False,
        "disk_space_ok": False,
        "apt_lock": False,
        "pi_hole_available": False,
        "boot_id": ""
    }

    # Check reboot status. RPi OS does not create /var/run/reboot-required on
    # kernel updates, so also compare running vs newest installed kernel.
    code, out, _ = run_ssh(node, "test -f /var/run/reboot-required && echo yes || echo no")
    checks["reboot_required"] = out.strip() == "yes" or kernel_reboot_needed(node)

    # Get boot ID
    code, out, _ = run_ssh(node, "cat /proc/sys/kernel/random/boot_id")
    if code == 0:
        checks["boot_id"] = out.strip()

    # Check disk space (need at least 500MB free on / and boot directory)
    boot_check_cmd = (
        'boot_dir="/boot"; '
        '[ -d "/boot/firmware" ] && boot_dir="/boot/firmware"; '
        'df -P / "$boot_dir" | tail -n +2 | awk \'{print $4}\''
    )
    code, out, _ = run_ssh(node, boot_check_cmd)
    if code == 0:
        try:
            parts = out.strip().split()
            if len(parts) >= 2:
                checks["disk_space_ok"] = int(parts[0]) >= 500000 and int(parts[1]) >= 500000
        except ValueError:
            checks["disk_space_ok"] = False

    # Check apt lock
    code, out, _ = run_ssh(node, "sudo fuser /var/lib/dpkg/lock /var/lib/apt/lists/lock /var/cache/apt/archives/lock 2>/dev/null | wc -l")
    checks["apt_lock"] = (code == 0 and out.strip() != "0")

    # Check Pi-hole availability
    code, out, _ = run_ssh(node, "command -v pihole")
    checks["pi_hole_available"] = code == 0

    return checks

def run_updates(node: str, preflight: dict, dist_upgrade: bool = False, dry_run: bool = False) -> dict:
    """Execute maintenance routine."""
    results = {
        "node": node,
        "apt_update": False,
        "apt_upgrade": False,
        "apt_dist_upgrade": False,
        "apt_autoremove": False,
        "apt_clean": False,
        "pi_hole_update": False,
        "reboot_triggered": False,
        "reboot_success": False,
        "issues": []
    }

    if dry_run:
        results["issues"].append("Dry run mode - no changes made")
        return results

    # 1. apt update
    code, out, err = run_ssh(node, "sudo apt-get update -y", timeout=120)
    results["apt_update"] = code == 0
    if code != 0:
        results["issues"].append(f"apt update failed: {err}")

    # 2. apt upgrade
    code, out, err = run_ssh(node, "sudo apt-get upgrade -y", timeout=300)
    results["apt_upgrade"] = code == 0
    if code != 0:
        results["issues"].append(f"apt upgrade failed: {err}")

    # 3. apt dist-upgrade
    if dist_upgrade:
        code, out, err = run_ssh(node, "sudo apt-get dist-upgrade -y", timeout=300)
        results["apt_dist_upgrade"] = code == 0
        if code != 0:
            results["issues"].append(f"apt dist-upgrade failed: {err}")

    # 4. Pi-hole update
    if preflight.get("pi_hole_available", False):
        code, out, err = run_ssh(node, "sudo pihole -up", timeout=300)
        results["pi_hole_update"] = code == 0
        if code != 0:
            results["issues"].append(f"pihole -up failed: {err}")
    else:
        results["issues"].append("Pi-hole CLI not found on node")

    # 5. Cleanup
    code, out, err = run_ssh(node, "sudo apt-get autoremove -y", timeout=120)
    results["apt_autoremove"] = code == 0
    if code != 0:
        results["issues"].append(f"apt autoremove failed: {err}")

    code, out, err = run_ssh(node, "sudo apt-get clean", timeout=120)
    results["apt_clean"] = code == 0
    if code != 0:
        results["issues"].append(f"apt clean failed: {err}")

    # 6. Check if reboot needed (also detects staged kernel updates on RPi OS)
    code, out, _ = run_ssh(node, "test -f /var/run/reboot-required && echo yes || echo no")
    reboot_needed = out.strip() == "yes" or kernel_reboot_needed(node)

    if reboot_needed:
        results["reboot_triggered"] = True
        initial_boot_id = preflight.get("boot_id", "")
        # Initiate reboot
        code, _, err = run_ssh(node, "sudo reboot", timeout=10)
        if code == 0 or "Connection closed" in err:
            # Wait for node to come back
            time.sleep(30)
            for attempt in range(12):
                code, out, _ = run_ssh(node, "cat /proc/sys/kernel/random/boot_id")
                if code == 0:
                    current_boot_id = out.strip()
                    if initial_boot_id and current_boot_id == initial_boot_id:
                        # Re-connected, but boot ID hasn't changed yet
                        pass
                    else:
                        if check_connectivity(node):
                            results["reboot_success"] = True
                            break
                time.sleep(10)
            if not results["reboot_success"]:
                results["issues"].append("Node did not come back after reboot")
        else:
            results["issues"].append(f"Reboot command failed: {err}")

    return results

def postflight_checks(node: str) -> dict:
    """Verify system health after maintenance."""
    checks = {
        "uptime": "",
        "pi_hole_running": False,
        "disk_usage": ""
    }

    code, out, _ = run_ssh(node, "uptime -p")
    checks["uptime"] = out.strip() if code == 0 else "unknown"

    code, out, _ = run_ssh(node, "systemctl is-active pihole-FTL 2>/dev/null || pihole status 2>/dev/null | head -n1")
    checks["pi_hole_running"] = (
        "active" in out.lower() or "running" in out.lower() or code == 0
    )

    boot_check_cmd = (
        'boot_dir="/boot"; '
        '[ -d "/boot/firmware" ] && boot_dir="/boot/firmware"; '
        'df -h / "$boot_dir" | tail -n +2'
    )
    code, out, _ = run_ssh(node, boot_check_cmd)
    checks["disk_usage"] = out.strip() if code == 0 else "unknown"

    return checks

def process_node(node: str, args) -> Tuple[bool, str]:
    """Process a single node and return success status and log output."""
    output = io.StringIO()
    def log(msg: str):
        print(msg, file=output)

    log(f"\n{'='*60}")
    log(f"Node: {node}")
    log(f"{'='*60}")

    log("[1/4] Checking connectivity...")
    if not check_connectivity(node):
        log(f"FAILED: Cannot connect to {node} or insufficient privileges")
        return False, output.getvalue()

    log("[2/4] Running pre-flight checks...")
    preflight = preflight_checks(node)
    log(f"  Reboot pending: {preflight['reboot_required']}")
    log(f"  Disk space OK: {preflight['disk_space_ok']}")
    log(f"  Pi-hole available: {preflight['pi_hole_available']}")
    log(f"  Apt lock: {preflight['apt_lock']}")
    if preflight.get("boot_id"):
        log(f"  Boot ID: {preflight['boot_id']}")

    # Check apt lock and wait if necessary
    apt_lock_attempts = 5
    while preflight["apt_lock"] and apt_lock_attempts > 0:
        log(f"WARNING: Apt lock detected on {node}. Waiting 30s... ({apt_lock_attempts} attempts remaining)")
        time.sleep(30)
        code, out, _ = run_ssh(node, "sudo fuser /var/lib/dpkg/lock /var/lib/apt/lists/lock /var/cache/apt/archives/lock 2>/dev/null | wc -l")
        preflight["apt_lock"] = (code == 0 and out.strip() != "0")
        apt_lock_attempts -= 1

    if preflight["apt_lock"]:
        log(f"FAILED: Apt lock on {node} persisted after waiting. Aborting updates.")
        return False, output.getvalue()

    log("[3/4] Running updates...")
    run_results = run_updates(node, preflight, dist_upgrade=args.dist_upgrade, dry_run=args.dry_run)
    log(f"  Apt update: {'OK' if run_results['apt_update'] else 'FAILED'}")
    log(f"  Apt upgrade: {'OK' if run_results['apt_upgrade'] else 'FAILED'}")
    if args.dist_upgrade:
        log(f"  Apt dist-upgrade: {'OK' if run_results['apt_dist_upgrade'] else 'FAILED'}")
    log(f"  Apt autoremove: {'OK' if run_results['apt_autoremove'] else 'FAILED'}")
    log(f"  Apt clean: {'OK' if run_results['apt_clean'] else 'FAILED'}")
    log(f"  Pi-hole update: {'OK' if run_results['pi_hole_update'] else 'FAILED'}")
    log(f"  Reboot triggered: {run_results['reboot_triggered']}")
    if run_results['reboot_triggered']:
        log(f"  Reboot success: {'OK' if run_results['reboot_success'] else 'FAILED'}")

    if run_results["issues"]:
        log("  Issues:")
        for issue in run_results["issues"]:
            log(f"    - {issue}")

    log("[4/4] Running post-flight checks...")
    postflight = postflight_checks(node)
    log(f"  Uptime: {postflight['uptime']}")
    log(f"  Pi-hole running: {postflight['pi_hole_running']}")
    log(f"  Disk usage:\n{postflight['disk_usage']}")

    # Node is considered successful if all updates passed and reboot (if triggered) succeeded
    success = (
        run_results["apt_update"]
        and run_results["apt_upgrade"]
        and (not args.dist_upgrade or run_results["apt_dist_upgrade"])
        and (not run_results["reboot_triggered"] or run_results["reboot_success"])
    )
    return success, output.getvalue()

def main():
    parser = argparse.ArgumentParser(description="Raspberry Pi Janitor - Maintain Pi-hole nodes")
    parser.add_argument("nodes", nargs="+", help="Hostnames or IPs of Pi nodes")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without making changes")
    parser.add_argument("--parallel", action="store_true", help="Process nodes in parallel (not recommended for Pi clusters)")
    parser.add_argument("--dist-upgrade", action="store_true", help="Perform a distribution upgrade (dist-upgrade) to apply kernel/major updates")
    args = parser.parse_args()

    success_count = 0
    failure_count = 0

    if args.parallel:
        print(f"Processing {len(args.nodes)} nodes in parallel...")
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(args.nodes)) as executor:
            future_to_node = {executor.submit(process_node, node, args): node for node in args.nodes}
            for future in concurrent.futures.as_completed(future_to_node):
                node = future_to_node[future]
                try:
                    success, log_output = future.result()
                    print(log_output)
                    if success:
                        success_count += 1
                    else:
                        failure_count += 1
                except Exception as exc:
                    print(f"\nNode {node} generated an exception: {exc}")
                    failure_count += 1
    else:
        for node in args.nodes:
            success, log_output = process_node(node, args)
            print(log_output)
            if success:
                success_count += 1
            else:
                failure_count += 1

    print(f"\n{'='*60}")
    print(f"Maintenance complete. Success: {success_count}, Failed: {failure_count}")
    print(f"{'='*60}")

    if failure_count > 0:
        sys.exit(1)

if __name__ == "__main__":
    main()
