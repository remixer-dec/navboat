import psutil


def get_open_host_ports(process):
    pid = process.pid
    process = psutil.Process(pid)
    if process.status() != psutil.STATUS_RUNNING:
        return []
    connections = process.connections()
    open_host_ports = set(
        f"{conn.laddr.ip.replace('::1', '0.0.0.0')}:{conn.laddr.port}"
        for conn in connections
        if conn.status != psutil.CONN_ESTABLISHED and conn.laddr.port <= 50000
    )

    for sub in process.children():
        open_host_ports.update(get_open_host_ports(sub))

    return list(open_host_ports)


def health_check(process, callback_when_dead):
    if process.poll() is not None:
        callback_when_dead()


def get_process_memory(action, config):
    if not config["options"]["show_memory_usage"]:
        return ""
    runner = action.get("_runner")
    if runner:
        try:
            process = psutil.Process(runner.pid)
            used = process.memory_info().rss
            for sub in process.children():
                used += sub.memory_info().rss
        except Exception:
            used = 0
        return f" [{round(used / (1024**3), 2)}G]"
    return ""


def get_status_emoji(action):
    if action.get("background"):
        return (
            int(bool(action.get("_runner", False))) * " ⏳" * int(not action.get("_is_running", False))
            + int(action.get("_is_running", False)) * " 🟢"
        )
    return ""
