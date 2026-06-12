---
name: rasp-pi-janitor
description: Remotely maintains and upgrades Raspberry Pi systems running Pi-hole via SSH. Handles apt updates, upgrades, Pi-hole software updates, kernel patches, and safe reboots. Use when you need to synchronize OS versions or apply updates to a fleet of Raspberry Pi systems running Pi-hole.
---

# Raspberry Pi Janitor

This skill is a fork of [`ubuntu-janitor`](../ubuntu-janitor/SKILL.md) adapted for Raspberry Pi systems running Pi-hole. It preserves the Ubuntu update workflow and adds Pi-hole-specific update steps.

## Prerequisites

- SSH access to the target Pi(s).
- Passwordless `sudo` or SSH key-based authentication for the user.
- Target systems must be Raspberry Pi OS (Debian-based).
- Pi-hole must be installed and the `pihole` CLI must be available.

## Core Workflows

### 1. Host Discovery & Connectivity
- **Input**: Accept a list of hostnames, IPs, or a CIDR range.
- **Verification**: Verify SSH connectivity and `sudo` privileges on all nodes.
- **OS Check**: Confirm the OS is Raspberry Pi OS / Debian-based.

### 2. Audit & Pre-flight
- **Update Check**: Run `sudo apt-get update` to refresh package lists.
- **Pending Updates**: Identify packages that will be upgraded or installed.
- **Pi-hole Update Check**: Check if Pi-hole updates are available.
- **Reboot Status**: Check if a reboot is already pending (`/var/run/reboot-required`).
- **Disk Space**: Verify sufficient disk space in `/` and the boot directory (`/boot` or `/boot/firmware` on Bookworm+).

### 3. Execution (The Maintenance Window)
For each node (or in parallel if requested):

1. **System Package Upgrade**:
   - `sudo apt-get update`
   - `sudo apt-get upgrade -y`
   - `sudo apt-get dist-upgrade -y` (optional, for kernel/major updates)
2. **Pi-hole Update**:
   - `sudo pihole -up`
3. **Cleanup**:
   - `sudo apt-get autoremove -y`
   - `sudo apt-get clean`
4. **Reboot Management**:
   - If `/var/run/reboot-required` exists or a kernel was updated, initiate `sudo reboot`.
   - Wait for the node to become reachable again via SSH, comparing boot ID (`/proc/sys/kernel/random/boot_id`) to confirm a successful restart.
   - **Mandatory Health Check**: Verify system health (uptime, Pi-hole service status, and disk space).

### 4. Verification
- Confirm all nodes are on the latest available versions.
- Report any nodes that failed to update or reboot.
- Verify Pi-hole is functioning correctly after updates.

## Usage

Run the maintenance script using:
```bash
python3 scripts/pi_maintenance.py [nodes ...] [options]
```

### Arguments and Options:
* `nodes`: Space-separated list of hostnames or IP addresses of the target Raspberry Pi systems.
* `--dry-run`: Show what would be done without making any changes.
* `--parallel`: Process target nodes in parallel (useful for large sets of nodes, but sequential updates are recommended for primary/secondary DNS clusters to prevent downtime).
* `--dist-upgrade`: Perform a full distribution upgrade (`sudo apt-get dist-upgrade -y`) to apply kernel and firmware updates.

## Best Practices
- **Sequential Updates**: For clusters, update nodes one at a time to maintain service availability.
- **Kernel Checks**: Always check for `reboot-required` after a `dist-upgrade`.
- **Pi-hole Service**: Ensure `pihole-FTL` service is active after reboot.
- **Locking**: Be aware of `flock` or `apt` locks; wait or report if the frontend is locked.
