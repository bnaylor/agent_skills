import json
import subprocess
import sys

def run_ssh(host, command, user=None):
    ssh_cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5"]
    if user:
        ssh_cmd.append(f"{user}@{host}")
    else:
        ssh_cmd.append(host)
    ssh_cmd.append(command)
    
    try:
        result = subprocess.run(ssh_cmd, capture_output=True, text=True, check=True)
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f"Error running command on {host}: {e.stderr}", file=sys.stderr)
        return None

def get_nodes(seed_host, user=None):
    output = run_ssh(seed_host, "microk8s kubectl get nodes -o json", user)
    if not output:
        return None
    return json.loads(output)

def get_channels(seed_host, user=None):
    output = run_ssh(seed_host, "snap info microk8s", user)
    if not output:
        return None
    
    channels = []
    # Simplified parsing for snap info
    lines = output.splitlines()
    found_channels = False
    for line in lines:
        if line.strip().startswith("channels:"):
            found_channels = True
            continue
        if found_channels:
            if not line.startswith("  "):
                break
            parts = line.strip().split()
            if parts:
                channels.append(parts[0])
    return channels

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: cluster_info.py <seed_host> [user]")
        sys.exit(1)
    
    seed = sys.argv[1]
    user = sys.argv[2] if len(sys.argv) > 2 else None
    
    nodes_data = get_nodes(seed, user)
    channels = get_channels(seed, user)
    
    if nodes_data and channels:
        print(json.dumps({
            "nodes": nodes_data,
            "channels": channels
        }, indent=2))
    else:
        sys.exit(1)
