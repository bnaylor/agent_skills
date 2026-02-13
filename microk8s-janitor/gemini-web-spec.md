Specification: microk8s-janitor Agent Skill
Goal

To automate the coordinated, rolling upgrade of a 3-node High Availability (HA) MicroK8s cluster running on Ubuntu from a remote macOS workstation using SSH.
Cluster Context

    Nodes: 3 Linux hosts (configured in HA mode via Dqlite).

    Control Plane: Distributed across all nodes.

    Management Tooling: snap (for MicroK8s lifecycle) and microk8s kubectl.

    Source Machine: macOS (remote execution via SSH).

Skill Requirements
1. Connectivity & Environment

    Use SSH keys for passwordless authentication from the Mac to the nodes.

    Handle the microk8s command prefixing (e.g., microk8s kubectl instead of kubectl).

    Account for sudo requirements when running snap refresh.

2. Implementation Logic (Rolling Upgrade Workflow)

The skill must follow a strictly sequential "serial" execution to maintain cluster quorum:

    Pre-flight Check: Verify all nodes are in Ready status and the cluster is healthy (microk8s status).

    Targeting: Identify the update channel or version (e.g., latest/stable).

    The Loop (Repeat for Node 1, 2, and 3):

        Cordon: Mark node as unschedulable.

        Drain: Evict pods (ignore daemonsets and use --delete-emptydir-data).

        Upgrade: Execute sudo snap refresh microk8s --channel=X.

        Wait: Poll microk8s status --wait-ready until the node is back.

        Uncordon: Bring the node back into the scheduling pool.

    Final Validation: Confirm all nodes match the target version and the cluster is stable.

3. Safety Constraints

    Stop on Failure: If any node fails to upgrade or return to Ready status, abort the entire process immediately. Do not proceed to the next node.

    One-at-a-time: Strictly enforce a concurrency limit of 1.

    Logging: Output the stdout/stderr of each node's upgrade process for visibility.

Files to Generate in ~/src/skills/microk8s-janitor/

    config.json: Store node hostnames/IPs, SSH user, and preferred MicroK8s channel.

    skill_main.py (or .sh): The core script that orchestrates the SSH commands and logic.

    manifest.md: A short description for Gemini-CLI to register the tool and understand when to invoke it.
