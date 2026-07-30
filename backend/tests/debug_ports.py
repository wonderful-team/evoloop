"""
Full environment block output with real data.
"""
import warnings
from collections import defaultdict
from datetime import datetime, timezone

import psutil


def get_ports():
    ports = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        for p in psutil.process_iter(['pid', 'name']):
            try:
                for conn in p.connections(kind='inet'):
                    if conn.status == 'LISTEN':
                        ports.append({
                            "port": conn.laddr.port,
                            "pid": p.info['pid'],
                            "process": p.info['name'] or "Unknown",
                        })
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                continue
    seen = {}
    for p in ports:
        port = p["port"]
        if port not in seen or (p["pid"] and not seen[port]["pid"]):
            seen[port] = p
    by_process = defaultdict(list)
    for p in seen.values():
        by_process[p["process"]].append(p["port"])
    return sorted(
        [{"name": name, "ports": sorted(ports), "port_count": len(ports)}
         for name, ports in by_process.items()],
        key=lambda x: x["name"]
    )


def get_docker():
    import subprocess
    try:
        res = subprocess.run(
            ['docker', 'ps', '--format', '{{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'],
            capture_output=True, text=True, timeout=1.5
        )
        if res.returncode == 0 and res.stdout.strip():
            containers = []
            for line in res.stdout.strip().split('\n'):
                parts = line.split('\t')
                if len(parts) >= 4:
                    containers.append({"name": parts[0], "image": parts[1], "status": parts[2], "ports": parts[3]})
            return containers
    except Exception:
        pass
    return []


def get_docker_host_ports(docker):
    import re
    host_ports = set()
    for c in docker:
        for mapping in c.get("ports", "").split(","):
            m = re.search(r':(\d+)->', mapping.strip())
            if m:
                host_ports.add(int(m.group(1)))
    return host_ports


if __name__ == "__main__":
    import platform
    import subprocess

    # Host info
    cpu = platform.processor()
    model = "Unknown"
    try:
        r = subprocess.run(['sysctl', '-n', 'machdep.cpu.brand_string'], capture_output=True, text=True, timeout=3)
        if r.returncode == 0:
            cpu = r.stdout.strip()
        r = subprocess.run(['system_profiler', 'SPHardwareDataType'], capture_output=True, text=True, timeout=5)
        for line in r.stdout.split('\n'):
            if 'Model Name' in line:
                model = line.split(':')[1].strip()
    except Exception:
        pass
    os_ver = platform.mac_ver()[0] or "Unknown"

    # Docker
    docker = get_docker()
    docker_host_ports = get_docker_host_ports(docker)

    # Ports with Docker filtering
    ports = get_ports()
    if docker_host_ports:
        filtered = []
        for svc in ports:
            non_docker = [p for p in svc["ports"] if p not in docker_host_ports]
            if non_docker:
                filtered.append({"name": svc["name"], "ports": non_docker, "port_count": len(non_docker)})
        ports = filtered

    service_labels = [
        f"{svc['name']} ({svc['port_count']})" if svc["port_count"] > 1 else svc["name"]
        for svc in ports
    ]

    # Running apps
    running_apps = []
    try:
        from AppKit import NSWorkspace
        apps = NSWorkspace.sharedWorkspace().runningApplications()
        running_apps = [app.localizedName() for app in apps if app.localizedName()][:5]
    except ImportError:
        pass

    now = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")

    print("=" * 60)
    print("FULL ENVIRONMENT AWARENESS OUTPUT")
    print("=" * 60)
    print()
    print(f"## ENVIRONMENT AWARENESS")
    print(f"- **Current Time**: {now}")
    print(f"- Host: {model} ({cpu}), macOS {os_ver}")
    print(f"  Use `list_app_atlas()` to see apps with structural UI maps.")
    print(f"- Network: Online")
    if service_labels or docker or running_apps:
        print(f"\n### Active Services")
        if service_labels:
            print(f"  Services: {', '.join(service_labels)}")
        if docker:
            print(f"  Docker: {', '.join(c['name'] for c in docker)}")
        if running_apps:
            print(f"  Running: {', '.join(running_apps)}")
    print()
print(f"---")
print(f"Rough token estimate: ~200")