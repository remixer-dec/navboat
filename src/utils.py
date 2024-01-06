import psutil


def get_open_host_ports(process):
    pid = process.pid
    if process.poll() is not None:
        return []
    connections = psutil.Process(pid).connections()
    open_host_ports = set(f"{conn.laddr.ip}:{conn.laddr.port}" for conn in connections)
    return list(open_host_ports)


def health_check(process, callback_when_dead):
    if process.poll() is not None:
        callback_when_dead()


def get_process_memory(action, config):
    if not config["options"]["show_memory_usage"]:
        return ""
    runner = action.get("_runner")
    if runner:
        process = psutil.Process(runner.pid)
        used = process.memory_info().rss
        return f" [{round(used / (1024**3), 3)}G]"
    return ""


def get_status_emoji(action):
    if action.get("background"):
        return (
            int(bool(action.get("_runner", False))) * " ⏳" * int(not action.get("_is_running", False))
            + int(action.get("_is_running", False)) * " 🟢"
        )
    return ""
