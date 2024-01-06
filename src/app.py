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
from utils import get_open_host_ports, health_check, get_status_emoji
from time import time

config = None
known_actions = {}


def cleanup():
    timer.stop()
    os.killpg(os.getpgid(os.getpid()), signal.SIGTERM)
    return True


atexit.register(cleanup)


def timer_checker(t):
    for i in list(known_actions):
        action = known_actions[i]
        process = action.get("_runner", None)
        if process and action.get("background"):
            health_check(process, partial(stop_subprocess, action))
            print("health heck")
            if int(time() - action.get("_started")) < 60:
                action["_hosts"] = get_open_host_ports(process)
                build_menu(app)


timer = rumps.Timer(timer_checker, 5)


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
        if action.get("_timer"):
            action["_timer"].stop()
        if action.get("_hosts"):
            del action["_hosts"]
        build_menu(app)


def generate_action_menu(action):
    known_actions.setdefault(action["name"], action)
    is_running = False
    is_service = False

    if action.get("background", False):
        is_service = True
        if action.get("_is_running", False):
            is_running = True
    running_function = None
    if action.get("_started") and not is_running:
        return []

    if action.get("type", "subprocess") == "subprocess":
        runner = action.get("_runner", None)
        if runner:
            running_function = partial(stop_subprocess, action)
            if runner.poll() is not None:
                is_running = False
                stop_subprocess(action)

        if not runner:
            cwd = action.get("dir", os.getcwd())

            process_runner = partial(
                subprocess.Popen,
                [action.get("command")] + shlex.split(action.get("arguments")),
                cwd=cwd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                close_fds=True,
                universal_newlines=True,
                shell=False,
                start_new_session=False,
            )

            def run_subprocess(action, runner):
                global timer
                process = runner()
                wait_for_text = action.get("wait_for")
                action["_runner"] = process
                action["_started"] = time()
                if action.get("background") and not wait_for_text:
                    action["_is_running"] = True
                build_menu(app)
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
                    build_menu(app)

            if config["options"]["use_threads"]:
                running_function = partial(threading.Thread(target=run_subprocess, args=(action, process_runner)).start)
            else:
                running_function = partial(run_subprocess, action, process_runner)
    toggle_action_text = "⏹ Stop service" if is_running else ("▶️ Start service" if is_service else "🚀 Run")

    action_menu = [rumps.MenuItem(toggle_action_text, callback=(lambda x: running_function()) if running_function else None)]
    hosts = action.get("_hosts", [])
    for host in hosts:
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
            subitem = rumps.MenuItem(item.get("name", "Unknown") + get_status_emoji(item))
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


def build_menu(app):
    main_menu = []
    build_nested_menu(config.get("actions", []), main_menu)
    main_menu.append(rumps.MenuItem(title="Quit", callback=rumps.quit_application))
    app.menu.clear()
    app.menu.update(main_menu)


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
