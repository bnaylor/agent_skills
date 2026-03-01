import subprocess
import sys
import json
import time

def run_ssh(host, command, user=None, timeout=10):
    ssh_cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5"]
    if user:
        ssh_cmd.append(f"{user}@{host}")
    else:
        ssh_cmd.append(host)
    ssh_cmd.append(command)
    
    try:
        result = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=timeout)
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {"error": "Timeout", "exit_code": -1}
    except Exception as e:
        return {"error": str(e), "exit_code": -1}

def check_node(host, user=None):
    # Check if Ubuntu/Debian and has sudo
    cmd = "cat /etc/os-release && sudo -n true"
    res = run_ssh(host, cmd, user)
    if res["exit_code"] != 0:
        return {"status": "error", "message": "Connection failed or no passwordless sudo", "details": res}
    
    is_ubuntu = "Ubuntu" in res["stdout"] or "Debian" in res["stdout"]
    return {"status": "ok", "is_ubuntu": is_ubuntu}

def audit_node(host, user=None, dist_upgrade=False):
    # Check for updates
    cmd_type = "dist-upgrade" if dist_upgrade else "upgrade"
    upgrade_cmd = f"sudo apt-get update > /dev/null && apt-get -s {cmd_type} | grep -P '^\\d+ upgraded'"
    up_res = run_ssh(host, upgrade_cmd, user, timeout=30)
    
    # Check for reboot status
    reboot_cmd = "[ -f /var/run/reboot-required ] && echo 'reboot-required' || echo 'no-reboot'"
    rb_res = run_ssh(host, reboot_cmd, user, timeout=10)
    
    if up_res["exit_code"] != 0 and up_res["exit_code"] != 1: # 1 means grep found nothing
        return {"status": "error", "message": "Upgrade check failed", "details": up_res}
    
    upgrade_summary = up_res["stdout"].strip() if up_res["exit_code"] == 0 else f"0 upgraded, 0 newly installed, 0 to remove and 0 not upgraded (mode: {cmd_type})."
    reboot_pending = "reboot-required" in rb_res["stdout"]
    
    return {
        "status": "ok",
        "upgrades": upgrade_summary,
        "reboot_pending": reboot_pending,
        "debug": {"stdout": up_res["stdout"], "stderr": up_res["stderr"], "exit_code": up_res["exit_code"]}
    }

def upgrade_node(host, user=None, dist_upgrade=False):
    upgrade_cmd = "upgrade" if not dist_upgrade else "dist-upgrade"
    cmd = f"sudo apt-get update && sudo apt-get {upgrade_cmd} -y && sudo apt-get autoremove -y"
    res = run_ssh(host, cmd, user, timeout=600) # Long timeout for upgrades
    if res["exit_code"] != 0:
        return {"status": "error", "message": "Upgrade failed", "details": res}
    return {"status": "ok"}

def reboot_node(host, user=None):
    print(f"Initiating reboot for {host}...")
    run_ssh(host, "sudo reboot", user)
    return {"status": "rebooting"}

def verify_health(host, user=None):
    # Check for common services that should be running
    services = ["microk8s", "docker", "ssh", "systemd-journald"]
    results = {}
    
    for svc in services:
        res = run_ssh(host, f"systemctl is-active {svc}", user)
        results[svc] = res["stdout"].strip() if res["exit_code"] == 0 else "inactive/failed"
        
    # Check disk space and load
    sys_check = run_ssh(host, "df -h / | tail -1 && uptime", user)
    
    return {
        "services": results,
        "system": sys_check["stdout"].strip() if sys_check["exit_code"] == 0 else "check failed"
    }

def wait_for_host(host, user=None, timeout=300):
    start = time.time()
    print(f"Waiting for {host} to return (timeout {timeout}s)...")
    while time.time() - start < timeout:
        res = run_ssh(host, "uptime", user, timeout=5)
        if res["exit_code"] == 0:
            health = verify_health(host, user)
            return {
                "status": "online", 
                "uptime": res["stdout"].strip(),
                "health": health
            }
        time.sleep(10)
    return {"status": "timeout", "message": f"Host failed to return within {timeout} seconds"}

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: ubuntu_maintenance.py <mode> <host> [user] [--dist-upgrade]")
        sys.exit(1)
    
    mode = sys.argv[1]
    host = sys.argv[2]
    user = sys.argv[3] if len(sys.argv) > 3 and not sys.argv[3].startswith("--") else None
    dist_upgrade = "--dist-upgrade" in sys.argv
    
    if mode == "check":
        print(json.dumps(check_node(host, user)))
    elif mode == "audit":
        print(json.dumps(audit_node(host, user, dist_upgrade)))
    elif mode == "upgrade":
        print(json.dumps(upgrade_node(host, user, dist_upgrade)))
    elif mode == "reboot":
        print(json.dumps(reboot_node(host, user)))
    elif mode == "wait":
        print(json.dumps(wait_for_host(host, user)))
    else:
        print(f"Unknown mode: {mode}")
        sys.exit(1)
