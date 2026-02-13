---
name: microk8s-janitor
description: Automates rolling upgrades and maintenance for HA MicroK8s clusters on Ubuntu via SSH. Supports node discovery, channel selection, pre-flight checks, and stateful recovery.
---

# MicroK8s Janitor

This skill manages the lifecycle of a MicroK8s cluster, specifically focusing on safe, rolling upgrades of nodes to ensure high availability is maintained throughout the process.

## Prerequisites

- SSH access to at least one node in the cluster (the "seed" node).
- Passwordless `sudo` or SSH key-based authentication for the user.
- The `microk8s` snap must be installed on the target nodes.

## Core Workflows

### 1. Cluster Discovery & Environment Setup

Starting from a single seed node provided by the user, the janitor discovers the full cluster state.

1. **Seed Connection:** Connect to the seed node and run `microk8s kubectl get nodes -o json`.
2. **Node Mapping:** Parse the output to identify all nodes, their roles, and current statuses.
3. **Connectivity Check:** Verify SSH and `sudo` access to every node in the cluster.
4. **Channel Discovery:** Run `snap info microk8s` on the seed node to list available tracking channels (e.g., `1.28/stable`, `latest/edge`).

### 2. Pre-flight Checks (The "Dry Run")

Before any disruptive action, the janitor ensures the cluster is healthy:

- All nodes must be in the `Ready` status.
- Check for any "critical" pods (e.g., `Longhorn`, `Calico`, `CoreDNS`) that are currently in a non-running state.
- Verify that `dqlite` (the HA backend) has a healthy quorum.

### 3. Interactive Planning

Present the plan to the user:
- Current version vs. Target channel.
- The order of nodes to be upgraded.
- Ask for confirmation before proceeding.

### 4. Rolling Upgrade Loop (Sequential Execution)

For each node in the sequence:

1. **Cordon:** `microk8s kubectl cordon <node-name>`
2. **Drain:** `microk8s kubectl drain <node-name> --ignore-daemonsets --delete-emptydir-data --force`
3. **Upgrade:** `sudo snap refresh microk8s --channel=<channel>`
4. **Wait for Ready:** Poll `microk8s status --wait-ready` (max 5 minutes).
5. **Health Check:** Verify local pods are starting and node status is `Ready`.
6. **Uncordon:** `microk8s kubectl uncordon <node-name>`

### 5. Resume & Recovery

If a step fails:
- **Abort:** Stop immediately. Do not move to the next node.
- **Log:** Capture and display the error from the node.
- **State Check:** On re-invocation, the janitor detects if any nodes are still cordoned and offers to "Resume" the upgrade from the failed node.

## Best Practices

- **Quorum First:** Never upgrade more than one node at a time in a 3-node HA cluster to avoid losing quorum.
- **Drain Timeout:** If a drain hangs, report the specific pod causing the delay to the user.
- **Snap Rollback:** If `snap refresh` fails, attempts `snap revert microk8s` if appropriate.
