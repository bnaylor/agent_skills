---
name: ubuntu-janitor
description: Remotely maintains and upgrades Ubuntu systems via SSH. Handles apt updates, upgrades, kernel patches, and safe reboots across multiple nodes. Use when you need to synchronize OS versions or apply security patches to a fleet of Ubuntu servers.
---

# Ubuntu Janitor

This skill automates the maintenance of Ubuntu servers, focusing on safe package updates and system reboots.

## Prerequisites

- SSH access to the target nodes.
- Passwordless `sudo` or SSH key-based authentication for the user.
- Target systems must be running Ubuntu/Debian-based distributions.

## Core Workflows

### 1. Host Discovery & Connectivity
- **Input**: Accept a list of hostnames, IPs, or a CIDR range.
- **Verification**: Verify SSH connectivity and `sudo` privileges on all nodes.
- **OS Check**: Confirm the OS is Ubuntu/Debian.

### 2. Audit & Pre-flight
- **Update Check**: Run `sudo apt-get update` to refresh package lists.
- **Pending Updates**: Identify packages that will be upgraded or installed.
- **Reboot Status**: Check if a reboot is already pending (`/var/run/reboot-required`).
- **Disk Space**: Verify sufficient disk space in `/` and `/boot`.

### 3. Execution (The Maintenance Window)
For each node (or in parallel if requested):

1. **Package Upgrade**:
   - `sudo apt-get update`
   - `sudo apt-get upgrade -y`
   - `sudo apt-get dist-upgrade -y` (optional, for kernel/major updates)
2. **Cleanup**:
   - `sudo apt-get autoremove -y`
   - `sudo apt-get clean`
3. **Reboot Management**:
   - If `/var/run/reboot-required` exists or a kernel was updated, initiate `sudo reboot`.
   - Wait for the node to become reachable again via SSH.
   - **Mandatory Health Check**: Verify system health (uptime, essential services like microk8s/docker, and disk space).

### 4. Verification
- Confirm all nodes are on the latest available versions.
- Report any nodes that failed to update or reboot.

## Best Practices
- **Sequential Updates**: For clusters (like K8s), update nodes one at a time.
- **Kernel Checks**: Always check for `reboot-required` after a `dist-upgrade`.
- **Locking**: Be aware of `flock` or `apt` locks; wait or report if the frontend is locked.
