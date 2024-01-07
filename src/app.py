import rumps
import yaml
from functools import partial
import subprocess
import os
import signal
import shlex
import atexit
import webbrowser
import select
import threading
from utils import get_open_host_ports, health_check, get_status_emoji, get_process_memory
from time import time

config = None
known_actions = {}
autorun = {}
total_running = 0


def cleanup():
    timer.stop()
    os.killpg(os.getpgid(os.getpid()), signal.SIGTERM)
    return True


atexit.register(cleanup)


def status_checker(t):
    global total_running
    should_rebuild_menu = time() // 1 % 60 < 6
    prev_running = total_running
    total_running = 0
    for i in list(known_actions):
        action = known_actions[i]
        process = action.get("_runner", None)
        if process and action.get("background"):
            health_check(process, partial(stop_subprocess, action))
            if int(time() - action.get("_started", 0)) < 60 or should_rebuild_menu:
                action["_hosts"] = get_open_host_ports(process)
                should_rebuild_menu = True
        if process:
            total_running += 1
    if prev_running != total_running:
        should_rebuild_menu = True
    if should_rebuild_menu:
        build_menu()


timer = rumps.Timer(status_checker, 5)


def custom_args_window(action, caller):
    result = rumps.Window(
        f"""Please specify the arguments to run {action["command"]}\nRunning in {action["dir"]}""",
        "Edit arguments",
        action.get("arguments"),
    ).run()
    action["arguments"] = result.text
    build_menu()


def setup_env(action):
    action_env = action.get("env")
    if not action_env:
        return None
    if action_env.get("_clean") is True:
        return action_env
    else:
        return {**os.environ.copy(), **action_env}


def get_subaction_executor(action: dict, subaction):
    action_base = action.copy()
    action_base["bakground"] = False
    action_base["window"] = subaction.get("window", False)
    action_base["shell"] = not action_base["window"]
    command = subaction.get("command", "").strip().replace("\n", " && ")
    return get_subprocess(action_base, command)


def get_subprocess(action, run_command):
    if action.get("venv"):
        run_command = f'source {action.get("venv")} && ' + (" ").join(run_command)
        action["shell"] = True
    if action.get("window"):
        if isinstance(run_command, list):
            run_command = shlex.join(run_command)
        run_command = ["osascript", "-e", f'tell app "Terminal" to do script "cd {action.get("dir")} && {run_command}"']
    return partial(
        subprocess.Popen,
        run_command,
        cwd=action.get("dir", os.getcwd()),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        close_fds=True,
        universal_newlines=True,
        shell=action.get("shell", False),
        env=setup_env(action),
        start_new_session=False,
    )


def stop_subprocess(action):
    process = action["_runner"]
    try:
        process.send_signal(signal.SIGINT)
        process.wait(timeout=5)

    except subprocess.TimeoutExpired:
        process.send_signal(signal.SIGKILL)
        process.wait()

    finally:
        action["_runner"] = False
        action["_is_running"] = False
        del action["_started"]
        if action.get("_hosts"):
            del action["_hosts"]
        build_menu()


def generate_action_menu(action):
    known_actions.setdefault(action["name"], action)
    is_running = False
    is_service = False
    is_started = action.get("_started", False)

    if action.get("background", False):
        is_service = True
        if action.get("_is_running", False):
            is_running = True
    if action.get("_started") and not is_running:
        return []

    if action.get("type", "subprocess") == "subprocess":
        runner = action.get("_runner", None)
        stop_function = partial(stop_subprocess, action)
        if runner:
            if runner.poll() is not None:
                is_running = False
                stop_subprocess(action)

        process_runner = get_subprocess(action, [action.get("command")] + shlex.split(action.get("arguments")))

        def run_subprocess(action, runner):
            process = runner()
            wait_for_text = action.get("wait_for")
            action["_runner"] = process
            action["_started"] = time()
            if action.get("background") and not wait_for_text:
                action["_is_running"] = True
            build_menu()
            if wait_for_text:
                while True:
                    ready, _, _ = select.select([process.stdout], [], [], config["options"]["wait_for_timeout"])
                    if not ready:
                        break
                    line = process.stdout.readline()
                    print(line, end="")
                    if not line:
                        break
                    if wait_for_text in line:
                        break
                action["_hosts"] = get_open_host_ports(process)
                action["_is_running"] = True
                build_menu()

        if config["options"]["use_threads"]:
            start_function = partial(threading.Thread(target=run_subprocess, args=(action, process_runner)).start)
        else:
            start_function = partial(run_subprocess, action, process_runner)
    toggle_action_text = "⏹ Stop service" if is_running else ("▶️ Start service" if is_service else "🚀 Run")
    if action.get("autorun") and not autorun.get(action["name"]):
        autorun[action["name"]] = True
        start_function()
    toggle_action_function = start_function if not runner else stop_function
    action_menu = [rumps.MenuItem(toggle_action_text, callback=lambda x: toggle_action_function())]
    if not is_started:
        action_menu.append(rumps.MenuItem("🎚️ Edit args", callback=partial(custom_args_window, action)))
    elif is_running:
        action_menu.append(rumps.MenuItem("🔄 Restart", callback=lambda x: [stop_function(), start_function()]))

    for subaction in action.get("subactions", []):
        executor = get_subaction_executor(action, subaction)
        when = subaction.get("when", None)
        if (when == "stopped" and not is_started) or (when != "stopped" and is_running) or when is None:
            action_menu.append(rumps.MenuItem(subaction.get("name"), callback=lambda x: executor()))

    hosts = action.get("_hosts", [])
    for host in hosts:
        if config["options"]["replace_ip_with_localhost"]:
            host = host.replace("127.0.0.1", "localhost")
        action_menu.insert(
            0,
            rumps.MenuItem(
                f"🌐 {host}",
                callback=lambda x, h="http://" + host: webbrowser.get(config["options"]["preferred_browser"]).open_new_tab(h),
            ),
        )
    return action_menu


def build_nested_menu(menu_items, menu):
    for item in menu_items:
        if isinstance(item, dict):
            memory_used = get_process_memory(item, config)
            subitem = rumps.MenuItem(item.get("name", "Unknown") + get_status_emoji(item) + memory_used)
            subitem.update(generate_action_menu(item))
            menu.append(subitem)
        elif isinstance(item, str):
            if isinstance(menu_items[item], dict):
                action_menu_item = rumps.MenuItem(item, callback=None)
                sm = build_nested_menu(menu_items[item], [])
                action_menu_item.update(sm)
                menu.append(action_menu_item)
            else:
                menu.append(rumps.MenuItem(item, callback=None))
                build_nested_menu(menu_items[item], menu)
                menu.append(None)
    return menu


def build_menu(custom_app=None):
    global app
    main_menu = []
    build_nested_menu(config.get("actions", []), main_menu)
    main_menu.append(rumps.MenuItem(title="Quit", callback=rumps.quit_application))
    if custom_app:
        app = custom_app
    app.menu.clear()
    app.menu.update(main_menu)
    if config["options"]["show_active_tasks"]:
        app.title = str(total_running)


def parse_config():
    with open("config.yaml", "r") as yaml_file:
        config = yaml.safe_load(yaml_file)
        return config


class NavBoatApp(rumps.App):
    def __init__(self, *args, **kwargs):
        global config
        config = parse_config()
        super().__init__(*args, **kwargs)
        build_menu(self)

    @rumps.events.before_quit
    def terminate(self):
        cleanup()
        rumps.quit_application()


if __name__ == "__main__":
    app = NavBoatApp("TestApp", template=True, quit_button=None)
    app.icon = "icon.png"
    app.title = ""
    timer.start()
    app.run()
