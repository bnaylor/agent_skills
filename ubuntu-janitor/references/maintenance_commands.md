# Common Ubuntu Maintenance Commands

## Package Management
- `sudo apt update`: Refresh package lists.
- `sudo apt upgrade`: Upgrade all packages (safe).
- `sudo apt dist-upgrade`: Upgrade packages, handling changing dependencies (required for kernel updates).
- `sudo apt autoremove`: Remove unused packages and dependencies.
- `sudo apt clean`: Clear out the local repository of retrieved package files.

## System Status
- `lsb_release -a`: Show Ubuntu version.
- `uname -r`: Show current kernel version.
- `cat /var/run/reboot-required`: Check if a reboot is needed (file exists if yes).
- `cat /var/run/reboot-required.pkgs`: See which packages triggered the reboot requirement.

## Troubleshooting
- `sudo dpkg --configure -a`: Fix interrupted package configurations.
- `sudo apt install -f`: Fix broken dependencies.
- `tail -f /var/log/apt/history.log`: View history of apt actions.
- `tail -f /var/log/apt/term.log`: View terminal output of apt actions.
