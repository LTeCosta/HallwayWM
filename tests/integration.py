#!/usr/bin/env python3
"""Exercise KVM and optional persistent placement inside a private GNOME session."""

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

try:
    from gi.repository import Gio, GLib
except ImportError as error:
    raise SystemExit("Integration tests require Python 3 with PyGObject, Gio and GLib") from error

PROJECT = Path(__file__).resolve().parents[1]
METADATA = json.loads((PROJECT / "src/metadata.json").read_text())
SOURCE = PROJECT / "dist"
UUID = METADATA["uuid"]
SETTINGS_SCHEMA = METADATA["settings-schema"]
BROWSER = os.environ.get("HALLWAYWM_TEST_BROWSER", "")
MAIN_WINDOW = sys.argv[1:] == ["--main-window"] or (
    sys.argv[1:2] == ["worker"] and os.environ.get("HALLWAYWM_TEST_MAIN_WINDOW") == "1"
)
WORKSPACES = sys.argv[1:] == ["--workspaces"] or (
    sys.argv[1:2] == ["worker"] and os.environ.get("HALLWAYWM_TEST_WORKSPACES") == "1"
)
PROFILES = sys.argv[1:] == ["--profiles"] or (
    sys.argv[1:2] == ["worker"] and os.environ.get("HALLWAYWM_TEST_PROFILES") == "1"
)
HALF_SCREEN = sys.argv[1:] == ["--half-screen"] or (
    sys.argv[1:2] == ["worker"] and os.environ.get("HALLWAYWM_TEST_HALF_SCREEN") == "1"
)
PLACEMENT = (
    PROFILES
    or WORKSPACES
    or MAIN_WINDOW
    or HALF_SCREEN
    or sys.argv[1:] == ["--placement"]
    or (sys.argv[1:2] == ["worker"] and os.environ.get("HALLWAYWM_TEST_PLACEMENT") == "1")
)


def preflight():
    """Reject unavailable test capabilities before building or creating a session."""
    global BROWSER
    commands = ["npm", "gnome-shell", "dbus-run-session", "glib-compile-schemas", "Xwayland"]
    missing = [command for command in commands if shutil.which(command) is None]
    if missing:
        raise SystemExit("Missing integration test executables: " + ", ".join(missing))
    if not (PROJECT / "node_modules/typescript/bin/tsc").is_file():
        raise SystemExit("Install project dependencies with npm ci --ignore-scripts")
    version = subprocess.check_output(["gnome-shell", "--version"], text=True)
    major = re.search(r"\b(\d+)(?:\.\d+)*\b", version)
    if major is None or major.group(1) not in METADATA["shell-version"]:
        raise SystemExit(
            "Integration tests require GNOME Shell " + ", ".join(METADATA["shell-version"])
        )
    schema_source = Gio.SettingsSchemaSource.get_default()
    for name in ["org.gnome.shell", "org.gnome.mutter", "org.gnome.desktop.wm.preferences"]:
        if schema_source is None or schema_source.lookup(name, True) is None:
            raise SystemExit("Missing system GSettings schema: " + name)
    full_placement = PLACEMENT and not (HALF_SCREEN or MAIN_WINDOW or WORKSPACES or PROFILES)
    gtk_versions = ["4.0", "3.0"] if WORKSPACES or full_placement else ["4.0"]
    for version in gtk_versions:
        result = subprocess.run(
            [sys.executable, "-B", "-c",
             "import gi; gi.require_version('Gtk', " + repr(version) + "); from gi.repository import Gtk"],
            capture_output=True, text=True,
        )
        if result.returncode:
            raise SystemExit("Integration tests require the GTK " + version + " Python GI bindings")
    if HALF_SCREEN or full_placement:
        candidates = [BROWSER] if BROWSER else [
            "chromium", "chromium-browser", "google-chrome-stable", "google-chrome",
            "microsoft-edge-stable", "microsoft-edge",
        ]
        BROWSER = next((path for name in candidates if (path := shutil.which(name))), "")
        if not BROWSER:
            raise SystemExit(
                "This scenario requires a Chromium-family browser; set HALLWAYWM_TEST_BROWSER "
                "to its executable path or command name"
            )


if len(sys.argv) == 1 or sys.argv[1:] in [
    ["--placement"],
    ["--half-screen"],
    ["--main-window"],
    ["--workspaces"],
    ["--profiles"],
]:
    preflight()
    subprocess.run(["npm", "run", "build"], cwd=PROJECT, check=True)
    built_metadata = json.loads((SOURCE / "metadata.json").read_text())
    if built_metadata["uuid"] != UUID or built_metadata["settings-schema"] != SETTINGS_SCHEMA:
        raise SystemExit("Built metadata does not match the project source")
    temporary = tempfile.TemporaryDirectory(prefix="hallwaywm-test-")
    ROOT = Path(temporary.name)
    runtime = ROOT / "isolated"
    runtime.mkdir(exist_ok=True)
    env = os.environ.copy()
    for name, folder in [
        ("HOME", "home"),
        ("XDG_CONFIG_HOME", "config"),
        ("XDG_DATA_HOME", "data"),
        ("XDG_CACHE_HOME", "cache"),
        ("XDG_STATE_HOME", "state"),
        ("XDG_RUNTIME_DIR", "run"),
    ]:
        target = runtime / folder
        target.mkdir(mode=0o700, exist_ok=True)
        env[name] = str(target)
    dest = runtime / "data/gnome-shell/extensions" / UUID
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(SOURCE, dest, ignore=shutil.ignore_patterns(".git"))
    subprocess.run(["glib-compile-schemas", str(dest / "schemas")], check=True)
    env["GSETTINGS_SCHEMA_DIR"] = str(dest / "schemas")
    env["HALLWAYWM_TEST_BROWSER"] = BROWSER
    env["HALLWAYWM_TEST_PLACEMENT"] = "1" if PLACEMENT else "0"
    env["HALLWAYWM_TEST_HALF_SCREEN"] = "1" if HALF_SCREEN else "0"
    env["HALLWAYWM_TEST_MAIN_WINDOW"] = "1" if MAIN_WINDOW else "0"
    env["HALLWAYWM_TEST_WORKSPACES"] = "1" if WORKSPACES else "0"
    env["HALLWAYWM_TEST_PROFILES"] = "1" if PROFILES else "0"
    helper = runtime / "data/gnome-shell/extensions/hallwaywm-test@local"
    helper.mkdir(exist_ok=True)
    (helper / "metadata.json").write_text(
        json.dumps(
            {
                "uuid": "hallwaywm-test@local",
                "name": "Isolated test access",
                "description": "Temporary access inside a private headless session",
                "shell-version": METADATA["shell-version"],
                "session-modes": ["user", "unlock-dialog"],
            }
        )
    )
    (
        helper / "extension.js"
    ).write_text("""import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import Meta from 'gi://Meta';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Clutter from 'gi://Clutter';
import St from 'gi://St';
import * as WindowMenu from 'resource:///org/gnome/shell/ui/windowMenu.js';
export default class TestAccess extends Extension {
    enable() {
        global.context.unsafe_mode = true;
        globalThis.hallwaywmTest = {Main, Meta, Gio, GLib, Clutter, St, WindowMenu, uuid: __TEST_UUID__};
    }
    disable() {
        global.context.unsafe_mode = false;
        delete globalThis.hallwaywmTest;
    }
}
""".replace("__TEST_UUID__", json.dumps(UUID)))
    env.update(
        {
            "GSETTINGS_BACKEND": "keyfile",
            "LIBGL_ALWAYS_SOFTWARE": "1",
            "GALLIUM_DRIVER": "llvmpipe",
            "GNOME_SHELL_SESSION_MODE": "user",
        }
    )
    env["HALLWAYWM_TEST_ROOT"] = str(ROOT)
    env["HALLWAYWM_TEST_HOST_BUS"] = env.get("DBUS_SESSION_BUS_ADDRESS", "")
    env.pop("DISPLAY", None)
    env.pop("WAYLAND_DISPLAY", None)
    with (ROOT / "bus.log").open("w") as buslog:
        process = subprocess.Popen(
            ["dbus-run-session", "--", sys.executable, "-B", str(__file__), "worker", str(ROOT)],
            env=env,
            stderr=buslog,
            start_new_session=True,
        )
        try:
            returncode = process.wait(timeout=420 if PLACEMENT else 120)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            returncode = 124
    if returncode:
        for name in ["bus.log", "shell.log"]:
            path = ROOT / name
            if path.exists():
                print(
                    name + ":\n" + "\n".join(path.read_text().splitlines()[-30:]), file=sys.stderr
                )
    temporary.cleanup()
    sys.exit(returncode)

if len(sys.argv) != 3:
    raise SystemExit(
        "Run this test with no arguments, --placement, --half-screen, --main-window or --workspaces or --profiles"
    )
ROOT = Path(sys.argv[2]).resolve()
if (
    sys.argv[1] != "worker"
    or os.environ.get("HALLWAYWM_TEST_ROOT") != str(ROOT)
    or os.environ.get("HOME") != str(ROOT / "isolated/home")
    or os.environ.get("XDG_RUNTIME_DIR") != str(ROOT / "isolated/run")
    or os.environ.get("DBUS_SESSION_BUS_ADDRESS") == os.environ.get("HALLWAYWM_TEST_HOST_BUS")
):
    raise SystemExit("The test worker requires an isolated runtime and D-Bus session")


def emit(label, value):
    print(label + ": " + json.dumps(value), flush=True)


def placement_settings():
    directory = Path(os.environ["XDG_DATA_HOME"]) / "gnome-shell/extensions" / UUID / "schemas"
    source = Gio.SettingsSchemaSource.new_from_directory(
        str(directory), Gio.SettingsSchemaSource.get_default(), False
    )
    return Gio.Settings.new_full(
        source.lookup(SETTINGS_SCHEMA, False), None, None
    )


settings = Gio.Settings.new("org.gnome.shell")
settings.set_strv("enabled-extensions", [UUID, "hallwaywm-test@local"])
settings.set_boolean("disable-user-extensions", False)
settings.set_boolean("disable-extension-version-validation", False)
Gio.Settings.new("org.gnome.mutter").set_boolean("dynamic-workspaces", False)
Gio.Settings.new("org.gnome.desktop.wm.preferences").set_int("num-workspaces", 4)
if PLACEMENT:
    placement_prefs = placement_settings()
    placement_prefs.set_boolean("functionality-enabled", True)
    placement_prefs.set_boolean("show-indicator", True)
    placement_prefs.set_string("window-global-defaults", json.dumps({
        "enabled": True,
        "restore_size": True,
        "restore_pos": True,
        "restore_maximized": True,
        "restore_workspace": True,
        "switch_to_workspace": True,
        "restore_minimized": False,
        "restore_above": True,
        "restore_sticky": True,
        "avoid_overlap": True,
    }))
Gio.Settings.sync()
bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
log = (ROOT / "shell.log").open("w")
shell = subprocess.Popen(
    [
        "gnome-shell",
        "--wayland",
        "--headless",
        "--virtual-monitor",
        "2560x1600",
        "--virtual-monitor",
        "3440x1440",
        "--wayland-display",
        "hallwaywm-test",
    ],
    stdout=log,
    stderr=subprocess.STDOUT,
)


def call(dest, path, interface, method, signature=None, args=()):
    return bus.call_sync(
        dest,
        path,
        interface,
        method,
        GLib.Variant(signature, args) if signature else None,
        None,
        Gio.DBusCallFlags.NONE,
        5000,
        None,
    ).unpack()


def ev(code):
    ok, value = call(
        "org.gnome.Shell", "/org/gnome/Shell", "org.gnome.Shell", "Eval", "(s)", (code,)
    )
    if not ok:
        raise RuntimeError(value)
    result = json.loads(value) if value else None
    if isinstance(result, str):
        try:
            return json.loads(result)
        except ValueError:
            pass
    return result


client = None
xclient = None


def display_state():
    return call(
        "org.gnome.Mutter.DisplayConfig",
        "/org/gnome/Mutter/DisplayConfig",
        "org.gnome.Mutter.DisplayConfig",
        "GetCurrentState",
    )


def layout(external, primary=None):
    state = display_state()
    monitors = state[1]
    configs = []
    for index, monitor in enumerate(monitors[: 2 if external else 1]):
        spec, modes, _ = monitor
        mode = next(m for m in modes if m[6].get("is-preferred", False))
        scale = min(mode[5], key=lambda value: abs(value - 4 / 3)) if index == 0 else 1.0
        configs.append(
            (
                0 if index == 0 else 1920,
                0,
                scale,
                0,
                index == (primary if primary is not None else (1 if external else 0)),
                [(spec[0], mode[0], {})],
            )
        )
    call(
        "org.gnome.Mutter.DisplayConfig",
        "/org/gnome/Mutter/DisplayConfig",
        "org.gnome.Mutter.DisplayConfig",
        "ApplyMonitorsConfig",
        "(uua(iiduba(ssa{sv}))a{sv})",
        (state[0], 1, configs, {"layout-mode": GLib.Variant("u", 1)}),
    )
    time.sleep(4)


def snapshot():
    return ev("""
        JSON.stringify(global.get_window_actors()
            .map(actor => actor.meta_window)
            .filter(window => window.get_title()?.startsWith("HallwayWM Test"))
            .map(window => {
                const rect = window.get_frame_rect();
                return {
                    title: window.get_title(),
                    x: rect.x, y: rect.y, width: rect.width, height: rect.height,
                    maximized: window.is_maximized(), minimized: window.minimized,
                    fullscreen: window.fullscreen,
                    workspace: window.get_workspace().index(),
                    monitor: window.get_monitor(), clientType: window.get_client_type()
                };
            })
            .sort((left, right) => left.title.localeCompare(right.title)))
    """)


def run_placement_cases():
    """Check persisted geometry without launching apps or mixing monitor profiles."""
    global shell
    clients = []

    def wait_ready():
        for _ in range(100):
            if shell.poll() is not None:
                raise RuntimeError("Isolated Shell exited")
            try:
                info = call(
                    "org.gnome.Shell.Extensions",
                    "/org/gnome/Shell/Extensions",
                    "org.gnome.Shell.Extensions",
                    "GetExtensionInfo",
                    "(s)",
                    (UUID,),
                )[0]
                if info.get("state") == 1:
                    assert not info.get("error"), info
                    return
            except GLib.Error:
                pass
            time.sleep(0.2)
        raise RuntimeError("HallwayWM did not become active")

    def open_client(backend):
        env = os.environ.copy()
        env.update(
            WAYLAND_DISPLAY="hallwaywm-test",
            GDK_BACKEND="wayland" if backend == "gtk3" else backend,
            GSK_RENDERER="cairo",
        )
        if backend == "x11":
            env["DISPLAY"] = ev('hallwaywmTest.GLib.getenv("DISPLAY")')
            env["XAUTHORITY"] = ev('hallwaywmTest.GLib.getenv("XAUTHORITY")')
        if backend == "browser":
            page = ROOT / "browser-test.html"
            page.write_text(
                "<!doctype html><title>HallwayWM Test Browser</title><p>Disposable placement test</p>"
            )
            process = subprocess.Popen(
                [
                    BROWSER,
                    "--ozone-platform=wayland",
                    "--user-data-dir=" + str(ROOT / "browser-profile"),
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--disable-background-networking",
                    "--disable-sync",
                    "--disable-component-update",
                    "--disable-background-mode",
                    "--password-store=basic",
                    "--new-window",
                    page.as_uri(),
                ],
                env=env,
                stdout=log,
                stderr=log,
            )
            clients.append(process)
            return process
        if backend == "gtk3":
            code = """import gi
gi.require_version('Gtk', '3.0')
from gi.repository import GLib
GLib.set_prgname('hallwaywm-workspace-test')
from gi.repository import Gtk
app = Gtk.Application(application_id='org.hallwaywm.WorkspaceTest')
def activate(app):
    window = Gtk.ApplicationWindow(application=app, title='HallwayWM Test gtk3', default_width=1720, default_height=1371)
    window.add(Gtk.Label(label='Large GTK 3 workspace restoration'))
    window.show_all()
app.connect('activate', activate)
app.run(None)
"""
            env.pop("GDK_SCALE", None)
            process = subprocess.Popen(
                [sys.executable, "-c", code], env=env, stdout=log, stderr=log
            )
            clients.append(process)
            return process
        code = """import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk
app = Gtk.Application(application_id='org.hallwaywm.TestBACKEND')
def activate(app):
    window = Gtk.ApplicationWindow(application=app, title='HallwayWM Test BACKEND', default_width=650, default_height=400)
    window.set_child(Gtk.Label(label='Disposable placement test'))
    window.present()
app.connect('activate', activate)
app.run(None)
""".replace("BACKEND", backend)
        process = subprocess.Popen([sys.executable, "-c", code], env=env, stdout=log, stderr=log)
        clients.append(process)
        return process

    def stop_client(process):
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)

    def windows():
        return {window["title"]: window for window in snapshot()}

    def wait_window(title, expected=None):
        for _ in range(60):
            value = windows().get(title)
            if value is not None and (
                expected is None or all(value[key] == item for key, item in expected.items())
            ):
                return value
            time.sleep(0.15)
        raise AssertionError({"expected": expected, "actual": windows()})

    def wait_learning(title):
        for _ in range(50):
            ready = ev(
                """(() => {
                const window = global.get_window_actors().map(a=>a.meta_window)
                    .find(w=>w.get_title()===%s);
                const handle = hallwaywmTest.Main.extensionManager.lookup(hallwaywmTest.uuid)
                    .stateObj._handles.get(window);
                return !!handle?.isRestoreApplied;
            })()"""
                % json.dumps(title)
            )
            if ready:
                return
            time.sleep(0.1)
        raise AssertionError("Startup placement did not settle")

    def run_profile_cases():
        """Exercise device identities, persistent KVM profiles and copy/link controls."""
        title = "HallwayWM Test wayland"

        def inspect_profile(code):
            return ev(
                """(() => {
                const e=hallwaywmTest.Main.extensionManager.lookup(hallwaywmTest.uuid).stateObj;
                const w=global.get_window_actors().map(a=>a.meta_window)
                    .find(w=>w.get_title()==='HallwayWM Test wayland');
                const identity=w?.get_wm_class();
                """
                + code
                + "})()"
            )

        def request(action, **values):
            payload = {
                "id": str(time.monotonic_ns()),
                "action": action,
                "target": inspect_profile("return e._layoutKey();"),
                **values,
            }
            inspect_profile(
                "e._settings.set_string('profile-request',"
                + json.dumps(json.dumps(payload))
                + "); return true;"
            )
            for _ in range(40):
                reply = inspect_profile("return e._settings.get_string('profile-request');")
                if reply.get("id") == payload["id"] and reply.get("status"):
                    return reply
                time.sleep(0.1)
            raise AssertionError("Profile action did not respond")

        def current_state():
            return inspect_profile(
                "return e._profiles.getState(JSON.parse(e._settings.get_string('window-app-states')), identity);"
            )

        def change_identity(office):
            inspect_profile(
                """
                if (!globalThis.hallwayProfileTest) {
                    const monitor=global.backend.get_monitor_manager().get_logical_monitors()
                        .find(m=>m.get_number()===1).get_monitors()[0];
                    globalThis.hallwayProfileTest={connector:monitor.get_connector(),
                        getSerial:hallwaywmTest.Meta.Monitor.prototype.get_serial};
                }
                const fixture=globalThis.hallwayProfileTest;
                hallwaywmTest.Meta.Monitor.prototype.get_serial="""
                + (
                    """function() {
                    return this.get_connector()===fixture.connector ? 'office-test-serial' : fixture.getSerial.call(this);
                }"""
                    if office
                    else "fixture.getSerial"
                )
                + """;
                e._profiles.sync();
                e._layoutRestorePending=true;
                e._sessionLayouts.topologyChanged();
                e._scheduleLayoutRestore();
                return true;
            """
            )
            time.sleep(5.5)

        def run_save_lock_cases():
            original = inspect_profile("""return {
                configs:e._settings.get_string('window-app-configs'),
                defaults:e._settings.get_string('window-global-defaults'),
                states:e._settings.get_string('window-app-states')};""")
            opened = []
            try:
                for backend in ("wayland", "x11", "gtk3"):
                    opened.append(open_client(backend))
                    wait_window("HallwayWM Test " + backend)
                fixture = inspect_profile("""
                    const windows=global.get_window_actors().map(a=>a.meta_window);
                    const x=windows.find(w=>w.get_title()==='HallwayWM Test x11');
                    const excluded=windows.find(w=>w.get_title()==='HallwayWM Test gtk3');
                    const defaults={enabled:true,restore_pos:true,restore_size:true,
                        restore_maximized:true,restore_workspace:false,switch_to_workspace:false,
                        restore_minimized:false,restore_above:false,restore_sticky:true,avoid_overlap:false,
                        excluded_apps:[{wm_class:excluded.get_wm_class()}]};
                    const rules=[{wm_class:'^HallwayWM Test wayland$',match_mode:'title',is_regex:true,
                        enabled:true,locked:false,restore_pos:true,restore_size:true,restore_workspace:false},
                        {wm_class:x.get_wm_class(),enabled:false,restore_pos:false,restore_size:false},
                        {wm_class:'closed.application',enabled:true,locked:false,restore_size:true}];
                    const states={'closed.application':{layouts:{unconnected:{x:50,y:60,width:500,height:400}}},
                        '^HallwayWM Test wayland$':{layouts:{unconnected:{x:90,y:100,width:800,height:600}}}};
                    e._settings.set_string('window-app-configs',JSON.stringify(rules));
                    e._settings.set_string('window-global-defaults',JSON.stringify(defaults));
                    e._settings.set_string('window-app-states',JSON.stringify(states));
                    hallwaywmTest.Main.overview.hide();
                    return {rules,defaults,states,xIdentity:x.get_wm_class(),excludedIdentity:excluded.get_wm_class()};
                """)
                wait_learning(title)
                wait_learning("HallwayWM Test x11")
                assert request("save")["status"] == "ok"
                assert (
                    inspect_profile(
                        "return JSON.parse(e._settings.get_string('window-app-configs'));"
                    )
                    == fixture["rules"]
                )
                failed = inspect_profile("""
                    const original=e.captureWindowState;
                    const before=e._settings.get_string('window-app-configs');
                    try {
                        e.captureWindowState=()=>false;
                        return {count:e._saveCurrentProfile(true),unchanged:before===e._settings.get_string('window-app-configs')};
                    } finally {e.captureWindowState=original;}
                """)
                assert failed == {"count": 0, "unchanged": True}, failed
                inspect_profile("w.move_frame(false,340,220); return true;")
                wait_window(title, {"x": 340, "y": 220})
                assert inspect_profile("return e._handles.get(w).timeoutId > 0;"), (
                    "Expected a pending automatic save"
                )
                result = request("save-and-lock")
                assert result["status"] == "ok" and "2 applications" in result["message"], result
                captured = inspect_profile(
                    "return JSON.parse(e._settings.get_string('window-app-states'));"
                )
                locked = inspect_profile(
                    "return JSON.parse(e._settings.get_string('window-app-configs'));"
                )
                assert locked[0] == {**fixture["rules"][0], "locked": True}
                assert locked[2] == fixture["rules"][2]
                assert len(locked) == len(fixture["rules"]), (
                    "Disabled exact-class slot was duplicated"
                )
                assert locked[1]["enabled"] and locked[1]["locked"]
                for flag, value in fixture["defaults"].items():
                    if flag not in ("enabled", "excluded_apps"):
                        assert locked[1][flag] == value, (flag, locked[1])
                assert "excluded_apps" not in locked[1]
                assert captured["closed.application"] == fixture["states"]["closed.application"]
                assert (
                    captured["^HallwayWM Test wayland$"]["layouts"]["unconnected"]
                    == fixture["states"]["^HallwayWM Test wayland$"]["layouts"]["unconnected"]
                )
                assert fixture["excludedIdentity"] not in captured
                assert (
                    inspect_profile(
                        "return JSON.parse(e._settings.get_string('window-global-defaults'));"
                    )
                    == fixture["defaults"]
                )
                inspect_profile("""
                    globalThis.saveLockProbe={original:e._performSave,writes:0};
                    e._performSave=function(...args) {
                        globalThis.saveLockProbe.writes++;
                        return globalThis.saveLockProbe.original.apply(this,args);
                    };
                    return true;
                """)
                time.sleep(0.7)
                assert inspect_profile("return globalThis.saveLockProbe.writes;") == 0, (
                    "Queued save ignored the new lock"
                )
                inspect_profile("""
                    e._performSave=globalThis.saveLockProbe.original;
                    delete globalThis.saveLockProbe;
                    w.move_frame(false,480,300);
                    return true;
                """)
                wait_window(title, {"x": 480, "y": 300})
                time.sleep(0.7)
                assert (
                    inspect_profile(
                        "return JSON.parse(e._settings.get_string('window-app-states'));"
                    )
                    == captured
                )
                assert request("apply")["status"] == "ok"
                wait_window(title, {"x": 340, "y": 220})
                time.sleep(2.2)
                inspect_profile("w.move_frame(false,420,260); return true;")
                wait_window(title, {"x": 420, "y": 260})
                assert request("save")["status"] == "ok"
                assert (
                    inspect_profile(
                        "return JSON.parse(e._settings.get_string('window-app-configs'));"
                    )
                    == locked
                )
                stop_client(opened[0])
                opened[0] = open_client("wayland")
                wait_window(title, {"x": 420, "y": 260})
                wait_learning(title)
                inspect_profile("""
                    const rules=JSON.parse(e._settings.get_string('window-app-configs'));
                    rules[0].locked=false;
                    e._settings.set_string('window-app-configs',JSON.stringify(rules));
                    w.move_frame(false,520,320);
                    return true;
                """)
                wait_window(title, {"x": 520, "y": 320})
                time.sleep(0.7)
                learned = inspect_profile(
                    "return e._profiles.getState(JSON.parse(e._settings.get_string('window-app-states')), '^HallwayWM Test wayland$');"
                )
                assert learned["x"] == 520 and learned["y"] == 320, learned
                emit(
                    "profile-save-lock",
                    {
                        "matched": True,
                        "applications": 2,
                        "pending_save_respected": True,
                        "unrelated_state_preserved": True,
                        "manual_resave": True,
                        "reopen_restored": True,
                        "unlock_resumed_learning": True,
                    },
                )
            finally:
                inspect_profile("""
                    if (globalThis.saveLockProbe) {
                        e._performSave=globalThis.saveLockProbe.original;
                        delete globalThis.saveLockProbe;
                    }
                    return true;
                """)
                for client in opened:
                    if client.poll() is None:
                        stop_client(client)
                for name, key in [
                    ("configs", "window-app-configs"),
                    ("defaults", "window-global-defaults"),
                    ("states", "window-app-states"),
                ]:
                    inspect_profile(
                        "e._settings.set_string("
                        + json.dumps(key)
                        + ","
                        + json.dumps(original[name])
                        + "); return true;"
                    )

        layout(True)
        time.sleep(2)
        run_save_lock_cases()
        process = open_client("wayland")
        wait_window(title)
        wait_learning(title)
        inspect_profile("""
            e._settings.set_string('window-app-configs',JSON.stringify([{wm_class:identity,
                enabled:true,locked:true,restore_pos:true,restore_size:true,
                restore_maximized:true,restore_workspace:true,switch_to_workspace:true,avoid_overlap:false}]));
            hallwaywmTest.Main.overview.hide();
            w.unmaximize(); w.move_to_monitor(1); w.move_resize_frame(false,2400,200,1000,600);
            return true;
        """)
        home_rect = {"monitor": 1, "x": 2400, "y": 200, "width": 1000, "height": 600}
        wait_window(title, home_rect)
        assert request("save")["status"] == "ok"
        home_key = inspect_profile("return e._layoutKey();")
        layout(False)
        time.sleep(2)
        notebook_key = inspect_profile("return e._layoutKey();")
        assert home_key != notebook_key
        inspect_profile("w.move_resize_frame(false,140,180,800,500); return true;")
        notebook_rect = {"monitor": 0, "x": 140, "y": 180, "width": 800, "height": 500}
        wait_window(title, notebook_rect)
        assert request("save")["status"] == "ok"
        layout(True)
        wait_window(title, home_rect)
        inspect_profile("w.move_resize_frame(false,2800,350,900,500); return true;")
        time.sleep(2)
        layout(False)
        wait_window(title, notebook_rect)
        layout(True)
        wait_window(title, home_rect)
        emit("profile-kvm-persistent-priority", {"matched": True, "setups": 2})

        try:
            change_identity(True)
            office_key = inspect_profile("return e._layoutKey();")
            assert office_key != home_key, "Different devices with equal geometry must be distinct"
            assert current_state() is None, (
                "A new device must not inherit another device's positions"
            )
            assert request("rename", name="Office")["status"] == "ok"
            assert request("copy", source=home_key)["status"] == "ok"
            time.sleep(2.2)
            wait_window(title, home_rect)
            copied = current_state()
            inspect_profile(
                """
                const states=JSON.parse(e._settings.get_string('window-app-states'));
                states[identity].layouts["""
                + json.dumps(home_key)
                + """].x=2550;
                e._settings.set_string('window-app-states',JSON.stringify(states)); return true;
            """
            )
            assert current_state() == copied, "Independent copies followed a source edit"
            emit("profile-device-and-copy", {"matched": True})
            assert request("link", source=home_key)["status"] == "ok"
            time.sleep(2.2)
            wait_window(title, {**home_rect, "x": 2550})
            assert request("save")["status"] == "error", (
                "Linked targets must not overwrite the source"
            )
            assert request("save-and-lock")["status"] == "error", (
                "Linked targets must not create or lock application rules"
            )
            change_identity(False)
            rejected = request("link", source=office_key)
            assert rejected["status"] == "error" and "cycle" in rejected["message"]
            change_identity(True)
            assert current_state()["x"] == 2550
            assert request("unlink")["status"] == "ok"
            independent = current_state()
            inspect_profile(
                """
                const states=JSON.parse(e._settings.get_string('window-app-states'));
                states[identity].layouts["""
                + json.dumps(home_key)
                + """].x=2700;
                e._settings.set_string('window-app-states',JSON.stringify(states)); return true;
            """
            )
            assert current_state() == independent, (
                "Detaching changed or retained a link to the source"
            )
            emit("profile-link-and-detach", {"matched": True})
            layout(False)
            time.sleep(2)
            assert request("copy", source=home_key)["status"] == "ok"
            time.sleep(2.2)
            projected = current_state()
            wait_window(
                title, {key: projected[key] for key in ["monitor", "x", "y", "width", "height"]}
            )
            assert projected["monitor"] == 0 and projected["width"] < home_rect["width"]
            assert projected["x"] >= 0 and projected["x"] + projected["width"] <= 1920
            emit("profile-copy-to-notebook", {"matched": True})
        finally:
            inspect_profile("""
                if (globalThis.hallwayProfileTest) {
                    hallwaywmTest.Meta.Monitor.prototype.get_serial=globalThis.hallwayProfileTest.getSerial;
                    delete globalThis.hallwayProfileTest;
                }
                return true;
            """)
            stop_client(process)

    def run_monitor_workspace_cases():
        """Restore a large GTK 3 window after asynchronous monitor configuration."""
        layout(True, 1)
        time.sleep(2)
        title = "HallwayWM Test gtk3"
        identity = "hallwaywm-workspace-test"
        state = {
            "workspace": 2,
            "monitor": 1,
            "x": 1920,
            "y": 32,
            "width": 1720,
            "height": 1408,
            "maximized": False,
            "sticky": False,
        }

        def prepare(locked, switch):
            config = {
                "wm_class": identity,
                "enabled": True,
                "locked": locked,
                "restore_size": True,
                "restore_pos": True,
                "restore_workspace": True,
                "switch_to_workspace": switch,
                "restore_maximized": True,
                "restore_sticky": True,
                "avoid_overlap": False,
            }
            ev(
                """(() => {
                const e=hallwaywmTest.Main.extensionManager.lookup(hallwaywmTest.uuid).stateObj;
                globalThis.dejaRestoreTest ??= {};
                const state=%s;
                e._settings.set_string('window-app-configs', JSON.stringify([%s]));
                const states=JSON.parse(e._settings.get_string('window-app-states'));
                states[%s]={...state,layouts:{[e._layoutKey()]:state}};
                e._settings.set_string('window-app-states',JSON.stringify(states));
                globalThis.dejaRestoreTest.settings=e._settings;
                globalThis.dejaRestoreTest.saved=JSON.stringify(states[%s]);
                new hallwaywmTest.Gio.Settings({schema_id:'org.gnome.mutter'})
                    .set_boolean('workspaces-only-on-primary',true);
                global.workspace_manager.get_workspace_by_index(3).activate(global.get_current_time());
                hallwaywmTest.Main.overview.hide();
                global.stage.get_context().get_backend().get_default_seat().warp_pointer(400,350);
                globalThis.dejaRestoreTest.workspaceSaves=[];
                globalThis.dejaRestoreTest.workspaceSaveSignal=e._settings.connect('changed::window-app-states',()=>{
                    globalThis.dejaRestoreTest.workspaceSaves.push(JSON.parse(e._settings.get_string('window-app-states'))[%s]);
                });
                return true;
            })()"""
                % (
                    json.dumps(state),
                    json.dumps(config),
                    json.dumps(identity),
                    json.dumps(identity),
                    json.dumps(identity),
                )
            )
            time.sleep(0.4)
            ev(
                "global.workspace_manager.get_workspace_by_index(3).activate(global.get_current_time()); true"
            )
            time.sleep(0.3)

        def status():
            return ev(
                """(() => {
                const e=hallwaywmTest.Main.extensionManager.lookup(hallwaywmTest.uuid).stateObj;
                const w=global.get_window_actors().map(a=>a.meta_window).find(w=>w.get_title()===%s);
                const h=e?._handles.get(w) ?? globalThis.dejaRestoreTest.pendingHandle;
                return {active:global.workspace_manager.get_active_workspace_index(),
                    pending:!!h?.pendingRestore, idle:h?.restoreIdleId, timeout:h?.restoreTimeoutId,
                    applied:h?.isRestoreApplied,saves:globalThis.dejaRestoreTest.workspaceSaves,
                    profileUnchanged:JSON.stringify(JSON.parse(globalThis.dejaRestoreTest.settings
                        .get_string('window-app-states'))['hallwaywm-workspace-test'])===globalThis.dejaRestoreTest.saved};
            })()"""
                % json.dumps(title)
            )

        def disconnect_save_signal():
            ev("""hallwaywmTest.Main.extensionManager.lookup(hallwaywmTest.uuid).stateObj
                ._settings.disconnect(globalThis.dejaRestoreTest.workspaceSaveSignal); true""")

        for locked, switch in [(True, True), (True, False), (False, True)]:
            prepare(locked, switch)
            process = open_client("gtk3")
            wait_window(title)
            ev("hallwaywmTest.Main.overview.hide(); true")
            actual_identity = ev(
                "global.get_window_actors().map(a=>a.meta_window).find(w=>w.get_title()==='HallwayWM Test gtk3').get_wm_class()"
            )
            assert actual_identity == identity, actual_identity
            wait_window(
                title,
                {key: state[key] for key in ["monitor", "workspace", "x", "y", "width", "height"]},
            )
            wait_learning(title)
            if not locked:
                ev(
                    "global.get_window_actors().map(a=>a.meta_window).find(w=>w.get_title()==='HallwayWM Test gtk3').move_frame(false,1940,32); true"
                )
                wait_window(title, {"x": 1940, "workspace": 2})
            time.sleep(0.8)
            result = status()
            assert result["active"] == (2 if switch else 3), result
            assert not result["pending"] and result["idle"] == result["timeout"] == 0, result
            assert all(
                saved["workspace"] == 2 and saved["monitor"] == 1 for saved in result["saves"]
            ), result
            if locked:
                assert not result["saves"] and result["profileUnchanged"], result
            else:
                assert result["saves"], result
            emit("large-gtk3-workspace", {"locked": locked, "switch": switch, "matched": True})
            disconnect_save_signal()
            stop_client(process)
            time.sleep(0.3)

        for action in ["close", "disable", "layout", "timeout", "bypass"]:
            prepare(False, True)
            ev("""(() => {
                const e=hallwaywmTest.Main.extensionManager.lookup(hallwaywmTest.uuid).stateObj;
                globalThis.dejaRestoreTest.finishRestore=e._finishRestore;
                e._finishRestore=()=>{};
                return true;
            })()""")
            process = open_client("gtk3")
            wait_window(title)
            ev("hallwaywmTest.Main.overview.hide(); true")
            for _ in range(40):
                if status()["pending"]:
                    break
                time.sleep(0.05)
            assert status()["pending"], status()
            ev("""(() => {
                const e=hallwaywmTest.Main.extensionManager.lookup(hallwaywmTest.uuid).stateObj;
                const w=global.get_window_actors().map(a=>a.meta_window).find(w=>w.get_title()==='HallwayWM Test gtk3');
                globalThis.dejaRestoreTest.pendingHandle=e._handles.get(w);
                globalThis.dejaRestoreTest.pendingExtension=e;
                return true;
            })()""")
            disconnect_save_signal()
            if action == "close":
                stop_client(process)
                time.sleep(0.2)
            elif action == "disable":
                call(
                    "org.gnome.Shell.Extensions",
                    "/org/gnome/Shell/Extensions",
                    "org.gnome.Shell.Extensions",
                    "DisableExtension",
                    "(s)",
                    (UUID,),
                )
            elif action == "layout":
                layout(False)
            elif action == "bypass":
                ev(
                    "globalThis.dejaRestoreTest.settings.set_boolean('functionality-enabled',false); true"
                )
            else:
                time.sleep(2.2)
            result = status()
            assert not result["pending"] and result["idle"] == result["timeout"] == 0, result
            assert not result["saves"] and result["active"] == 3, result
            assert result["profileUnchanged"], result
            ev(
                "globalThis.dejaRestoreTest.pendingExtension._finishRestore=globalThis.dejaRestoreTest.finishRestore; true"
            )
            if action == "bypass":
                ev(
                    "globalThis.dejaRestoreTest.settings.set_boolean('functionality-enabled',true); true"
                )
                wait_window(title, {"workspace": 2, "monitor": 1, "x": 1920, "width": 1720})
                wait_learning(title)
                assert status()["active"] == 2, status()
            stop_client(process)
            if action == "disable":
                call(
                    "org.gnome.Shell.Extensions",
                    "/org/gnome/Shell/Extensions",
                    "org.gnome.Shell.Extensions",
                    "EnableExtension",
                    "(s)",
                    (UUID,),
                )
                wait_ready()
            if action == "layout":
                layout(True, 1)
                time.sleep(2)
            emit("pending-restore-" + action, {"matched": True})
        ev("delete globalThis.dejaRestoreTest; true")

    def run_workspace_cases():
        """Restore workspaces only on participating destination monitors."""
        cases = [
            (True, 1, True, 0, True, 0, "secondary-without-workspaces"),
            (True, 1, True, 1, True, 2, "external-primary"),
            (True, 1, False, 0, True, 2, "secondary-with-workspaces"),
            (True, 1, True, 1, False, 0, "switch-disabled"),
            (True, 0, True, 0, True, 2, "internal-primary"),
            (True, 0, True, 1, True, 0, "external-secondary"),
            (False, 0, True, 0, True, 2, "laptop-only"),
        ]
        for backend in ["wayland", "x11"]:
            current_layout = None
            for external, primary, primary_only, monitor, switch, active, label in cases:
                if current_layout != (external, primary):
                    layout(external, primary)
                    time.sleep(2)
                    current_layout = (external, primary)
                ev(
                    """(() => {
                    const settings = new hallwaywmTest.Gio.Settings({schema_id: 'org.gnome.mutter'});
                    settings.set_boolean('workspaces-only-on-primary', %s);
                    global.workspace_manager.get_workspace_by_index(0)
                        .activate(global.get_current_time());
                    return true;
                })()"""
                    % json.dumps(primary_only)
                )
                time.sleep(0.3)
                assert ev("hallwaywmTest.Meta.prefs_get_workspaces_only_on_primary()") == primary_only
                process = open_client(backend)
                title = "HallwayWM Test " + backend
                wait_window(title)
                wait_learning(title)
                identity = ev(
                    """global.get_window_actors().map(a=>a.meta_window)
                    .find(w=>w.get_title()===%s).get_wm_class()"""
                    % json.dumps(title)
                )
                stop_client(process)
                for _ in range(40):
                    if title not in windows():
                        break
                    time.sleep(0.1)
                assert title not in windows()
                x = 2400 if monitor == 1 else 150
                config = {
                    "wm_class": identity,
                    "enabled": True,
                    "locked": True,
                    "restore_size": True,
                    "restore_pos": True,
                    "restore_workspace": True,
                    "switch_to_workspace": switch,
                    "restore_maximized": True,
                    "avoid_overlap": False,
                }
                state = {
                    "monitor": monitor,
                    "workspace": 2,
                    "x": x,
                    "y": 180,
                    "width": 900,
                    "height": 600,
                    "maximized": False,
                }
                saved = ev(
                    """(() => {
                    const extension = hallwaywmTest.Main.extensionManager.lookup(
                        hallwaywmTest.uuid).stateObj;
                    const state = %s;
                    extension._settings.set_string('window-app-configs', JSON.stringify([%s]));
                    const states = JSON.parse(extension._settings.get_string('window-app-states'));
                    states[%s] = {...state, layouts: {[extension._layoutKey()]: state}};
                    extension._settings.set_string('window-app-states', JSON.stringify(states));
                    global.workspace_manager.get_workspace_by_index(0)
                        .activate(global.get_current_time());
                    return states;
                })()"""
                    % (json.dumps(state), json.dumps(config), json.dumps(identity))
                )
                time.sleep(0.3)
                ev("""hallwaywmTest.workspaceChanges = [];
                    hallwaywmTest.workspaceSignal = global.workspace_manager.connect(
                        'active-workspace-changed', () => hallwaywmTest.workspaceChanges.push(
                            global.workspace_manager.get_active_workspace_index())); true""")
                process = open_client(backend)
                wait_window(title, {"monitor": monitor, "x": x, "y": 180, "width": 900})
                wait_learning(title)
                time.sleep(1)
                result = ev("""(() => {
                    const extension = hallwaywmTest.Main.extensionManager.lookup(
                        hallwaywmTest.uuid).stateObj;
                    global.workspace_manager.disconnect(hallwaywmTest.workspaceSignal);
                    return {
                        active: global.workspace_manager.get_active_workspace_index(),
                        changes: hallwaywmTest.workspaceChanges,
                        states: JSON.parse(extension._settings.get_string('window-app-states')),
                        configs: JSON.parse(extension._settings.get_string('window-app-configs')),
                    };
                })()""")
                assert result["active"] == active, (label, result)
                assert result["changes"] == ([] if active == 0 else [2]), (label, result)
                assert result["states"] == saved, (label, result)
                assert result["configs"] == [config], (label, result)
                if not primary_only or monitor == primary:
                    assert windows()[title]["workspace"] == 2, (label, windows())
                emit("workspace-" + backend + "-" + label, {"matched": True})
                stop_client(process)

    def window_menu(title):
        return ev(
            """(() => {
                const window = global.get_window_actors().map(a=>a.meta_window)
                    .find(w=>w.get_title()===%s);
                const extension = hallwaywmTest.Main.extensionManager.lookup(
                    hallwaywmTest.uuid).stateObj;
                const source = new hallwaywmTest.St.Widget();
                const menu = new hallwaywmTest.WindowMenu.WindowMenu(window, source);
                try {
                    return {
                        present: menu._getMenuItems().some(
                            item=>item.label?.text === 'HallwayWM'),
                        secondary: extension._secondaryWindows.has(window)
                    };
                } finally {
                    menu.destroy();
                    source.destroy();
                }
            })()"""
            % json.dumps(title)
        )

    def run_main_window_cases():
        """Keep automatic selection conservative while allowing explicit capture."""
        for backend in ["wayland", "x11"]:
            env = os.environ.copy()
            env.update(WAYLAND_DISPLAY="hallwaywm-test", GDK_BACKEND=backend, GSK_RENDERER="cairo")
            if backend == "x11":
                env["DISPLAY"] = ev('hallwaywmTest.GLib.getenv("DISPLAY")')
                env["XAUTHORITY"] = ev('hallwaywmTest.GLib.getenv("XAUTHORITY")')
            code = """import sys
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib
app = Gtk.Application(application_id='org.hallwaywm.MainOnlyBACKEND')
windows = {}
def make_window(kind):
    window = Gtk.ApplicationWindow(application=app, title='HallwayWM Test BACKEND ' + kind,
        default_width=650 if kind == 'main' else 330,
        default_height=400 if kind == 'main' else 210)
    window.set_child(Gtk.Label(label='Disposable main-window test'))
    if kind in ('popup', 'dialog'):
        window.set_transient_for(windows['main'])
    if kind == 'dialog':
        window.set_modal(True)
    windows[kind] = window
    window.present()
def command(stream, condition):
    action = stream.readline().strip()
    if action == 'close-main':
        windows['main'].destroy()
    elif action:
        make_window(action)
    return True
def activate(app):
    make_window('main')
    GLib.io_add_watch(sys.stdin, GLib.IO_IN, command)
app.connect('activate', activate)
app.run(None)
""".replace("BACKEND", backend)
            process = subprocess.Popen(
                [sys.executable, "-c", code],
                env=env,
                stdin=subprocess.PIPE,
                text=True,
                stdout=log,
                stderr=log,
            )
            clients.append(process)
            title = "HallwayWM Test " + backend + " main"

            def command(action):
                process.stdin.write(action + "\n")
                process.stdin.flush()

            def runtime():
                return ev("""(() => {
                    const extension = hallwaywmTest.Main.extensionManager.lookup(
                        hallwaywmTest.uuid).stateObj;
                    return {
                        managed: [...extension._handles.keys()].map(w=>w.get_title()).sort(),
                        states: JSON.parse(extension._settings.get_string("window-app-states")),
                        configs: JSON.parse(extension._settings.get_string("window-app-configs"))
                    };
                })()""")

            def current_state(window_title):
                return ev(
                    """(() => {
                        const window = global.get_window_actors().map(a=>a.meta_window)
                            .find(w=>w.get_title()===%s);
                        const rect = window.get_frame_rect();
                        const extension = hallwaywmTest.Main.extensionManager.lookup(
                            hallwaywmTest.uuid).stateObj;
                        return {
                            x: rect.x, y: rect.y, width: rect.width, height: rect.height,
                            workspace: window.get_workspace().index(), monitor: window.get_monitor(),
                            monitorId: extension._profiles.monitorId(window.get_monitor()),
                            maximized: window.is_maximized(), minimized: window.minimized,
                            above: window.above, sticky: window.on_all_workspaces
                        };
                    })()"""
                    % json.dumps(window_title)
                )

            def capture_window(window_title, identity):
                return ev(
                    """(() => {
                        const extension = hallwaywmTest.Main.extensionManager.lookup(
                            hallwaywmTest.uuid).stateObj;
                        const window = global.get_window_actors().map(a=>a.meta_window)
                            .find(w=>w.get_title()===%s);
                        return extension.captureWindowState(window, %s);
                    })()"""
                    % (json.dumps(window_title), json.dumps(identity))
                )

            def capture_request(identity, match_mode):
                request = {"wm_class": identity, "match_mode": match_mode}
                # Keep keyfile writes in the Shell process; a second writer can
                # overwrite newer fixture values with its cached keyfile contents.
                ev(
                    """hallwaywmTest.Main.extensionManager.lookup(hallwaywmTest.uuid)
                        .stateObj._settings.set_string('capture-state-request', %s)"""
                    % json.dumps(json.dumps(request))
                )
                for _ in range(40):
                    reply = ev("""hallwaywmTest.Main.extensionManager.lookup(
                        hallwaywmTest.uuid).stateObj._settings
                        .get_string('capture-state-request')""")
                    if isinstance(reply, dict) and "status" in reply:
                        assert reply["wm_class"] == identity and reply["match_mode"] == match_mode
                        ev("""hallwaywmTest.Main.extensionManager.lookup(
                            hallwaywmTest.uuid).stateObj._settings
                            .set_string('capture-state-request', '')""")
                        return reply["status"]
                    time.sleep(0.1)
                raise AssertionError({"capture_request": request, "reply": reply})

            def set_rule(identity, match_mode):
                configs = [
                    {
                        "wm_class": identity,
                        "match_mode": match_mode,
                        "enabled": True,
                        "locked": True,
                        "restore_pos": True,
                        "restore_size": True,
                    }
                ]
                ev(
                    """hallwaywmTest.Main.extensionManager.lookup(hallwaywmTest.uuid)
                        .stateObj._settings.set_string('window-app-configs', %s)"""
                    % json.dumps(json.dumps(configs))
                )
                assert runtime()["configs"] == configs, runtime()
                return configs

            def assert_capture(window_title, identity, expected, previous, configs):
                actual = runtime()
                assert actual["states"][identity]["layouts"][layout_key] == expected, actual
                assert {
                    key: value for key, value in actual["states"].items() if key != identity
                } == {key: value for key, value in previous.items() if key != identity}, actual
                assert actual["configs"] == configs, actual
                assert window_title not in actual["managed"], actual
                assert window_menu(window_title)["secondary"], window_menu(window_title)
                assert current_state(window_title) == expected, current_state(window_title)

            def restore_fixture():
                ev(
                    """(() => {
                        const settings = hallwaywmTest.Main.extensionManager.lookup(
                            hallwaywmTest.uuid).stateObj._settings;
                        settings.set_string('window-app-configs', %s);
                        settings.set_string('window-app-states', %s);
                        return true;
                    })()"""
                    % (json.dumps(json.dumps(original_configs)), json.dumps(json.dumps(saved)))
                )
                assert runtime()["states"] == saved, runtime()
                assert runtime()["configs"] == original_configs, runtime()

            wait_window(title)
            wait_learning(title)
            menu = window_menu(title)
            assert menu["present"], menu
            ev(
                """global.get_window_actors().map(a=>a.meta_window)
                .filter(w=>w.get_title()===%s).forEach(w=>{
                    w.unmaximize();
                    w.move_to_monitor(1);
                    w.move_resize_frame(false, 2400, 180, 900, 600);
                }); true"""
                % json.dumps(title)
            )
            time.sleep(1.5)
            main_geometry = wait_window(title, {"x": 2400, "y": 180, "width": 900})
            saved = runtime()["states"]
            original_configs = runtime()["configs"]
            layout_key = ev("""hallwaywmTest.Main.extensionManager.lookup(
                hallwaywmTest.uuid).stateObj._settings
                .get_string('active-display-profile')""")
            for kind in ["popup", "dialog", "secondary", "hidden"]:
                command(kind)
                secondary_title = "HallwayWM Test " + backend + " " + kind
                wait_window(secondary_title)
                time.sleep(0.4)
                state = wait_window(secondary_title)
                # XWayland client pixels follow the private compositor's scale.
                assert state["width"] < main_geometry["width"] / 2 and not state["maximized"], state
                assert secondary_title not in runtime()["managed"], runtime()
                menu = window_menu(secondary_title)
                assert menu["present"] == (kind in {"secondary", "hidden"}), (kind, menu)
                assert menu["secondary"], (kind, menu)
            assert runtime()["states"] == saved, runtime()
            emit("normal-window-menu-" + backend, {"matched": True})
            emit("main-only-open-" + backend, {"matched": True})

            ev("""global.get_window_actors().map(a=>a.meta_window)
                .filter(w=>w.get_title()?.endsWith(' secondary')).forEach(w=>{
                    w.move_resize_frame(false, 300, 260, 470, 300);
                }); true""")
            time.sleep(1)
            assert runtime()["states"] == saved, runtime()
            # Re-adoption must select by age even when the secondary was focused last.
            # Forget roles to exercise adoption of an already populated desktop too.
            ev("""hallwaywmTest.Main.extensionManager.lookup(hallwaywmTest.uuid)
                .stateObj._secondaryWindows = new WeakSet(); true""")
            for method in ["DisableExtension", "EnableExtension"]:
                call(
                    "org.gnome.Shell.Extensions",
                    "/org/gnome/Shell/Extensions",
                    "org.gnome.Shell.Extensions",
                    method,
                    "(s)",
                    (UUID,),
                )
            time.sleep(1)
            assert title in runtime()["managed"], runtime()
            assert not any(
                name.endswith((" popup", " dialog", " secondary", " hidden"))
                for name in runtime()["managed"]
            ), runtime()
            assert runtime()["states"] == saved, runtime()

            emit("main-only-readoption-" + backend, {"matched": True})

            # An explicit capture chooses the current window without adopting it.
            secondary_title = "HallwayWM Test " + backend + " secondary"
            configs = set_rule(secondary_title, "title")
            expected = current_state(secondary_title)
            assert capture_window(secondary_title, secondary_title)
            assert_capture(secondary_title, secondary_title, expected, saved, configs)
            captured = runtime()["states"]
            ev(
                """global.get_window_actors().map(a=>a.meta_window)
                    .find(w=>w.get_title()===%s).move_resize_frame(false, 360, 300, 490, 320); true"""
                % json.dumps(secondary_title)
            )
            wait_window(secondary_title, {"x": 360, "y": 300, "width": 490})
            time.sleep(1)
            assert runtime()["states"] == captured, runtime()
            assert secondary_title not in runtime()["managed"], runtime()

            # A monitor transition must report failure instead of a successful no-op.
            previous_guard = ev("""(() => {
                const extension = hallwaywmTest.Main.extensionManager.lookup(
                    hallwaywmTest.uuid).stateObj;
                const previous = extension._layoutSaveAfter;
                extension._layoutSaveAfter = hallwaywmTest.GLib.get_monotonic_time() + 5000000;
                return previous;
            })()""")
            try:
                assert capture_window(secondary_title, secondary_title) is False
                assert capture_request(secondary_title, "title") == "save-failed"
            finally:
                ev(
                    """hallwaywmTest.Main.extensionManager.lookup(hallwaywmTest.uuid)
                        .stateObj._layoutSaveAfter = %s; true"""
                    % json.dumps(previous_guard)
                )
            assert runtime()["states"] == captured, runtime()
            emit("manual-capture-layout-guard-" + backend, {"matched": True})

            # Preferences select the most recent normal match, including a secondary.
            identity = ev(
                """global.get_window_actors().map(a=>a.meta_window)
                    .find(w=>w.get_title()===%s).get_wm_class()"""
                % json.dumps(secondary_title)
            )
            configs = set_rule(identity, "wm_class")
            ev(
                """global.get_window_actors().map(a=>a.meta_window)
                    .find(w=>w.get_title()===%s).activate(global.get_current_time()); true"""
                % json.dumps(secondary_title)
            )
            time.sleep(0.2)
            most_recent = ev(
                """global.display.get_tab_list(hallwaywmTest.Meta.TabList.NORMAL, null)
                    .find(w=>w.get_wm_class()===%s && !w.get_transient_for()).get_title()"""
                % json.dumps(identity)
            )
            assert most_recent == secondary_title, most_recent
            expected = current_state(secondary_title)
            assert capture_request(identity, "wm_class") == "saved"
            assert_capture(secondary_title, identity, expected, captured, configs)
            emit("manual-capture-secondary-" + backend, {"matched": True})

            hidden_title = "HallwayWM Test " + backend + " hidden"
            assert ev(
                """(() => {
                    const window = global.get_window_actors().map(a=>a.meta_window)
                        .find(w=>w.get_title()===%s);
                    window.hide_from_window_list();
                    return window.is_skip_taskbar();
                })()"""
                % json.dumps(hidden_title)
            )
            for kind in ["popup", "dialog", "hidden"]:
                rejected_title = "HallwayWM Test " + backend + " " + kind
                configs = set_rule(rejected_title, "title")
                previous = runtime()["states"]
                assert capture_window(rejected_title, rejected_title) is False, kind
                assert capture_request(rejected_title, "title") == "no-window", kind
                assert runtime()["states"] == previous, runtime()
                assert runtime()["configs"] == configs, runtime()
                assert rejected_title not in runtime()["managed"], runtime()
            assert capture_request("HallwayWM Test " + backend + " missing", "title") == "no-rule"
            assert runtime()["states"] == previous, runtime()
            emit("manual-capture-reject-auxiliary-" + backend, {"matched": True})
            restore_fixture()

            command("close-main")
            for _ in range(40):
                if title not in windows():
                    break
                time.sleep(0.1)
            assert title not in windows()
            ev("""(() => {
                const extension = hallwaywmTest.Main.extensionManager.lookup(
                    hallwaywmTest.uuid).stateObj;
                extension._settings.set_string('window-app-configs', '[]');
                extension._adoptUnmanagedWindows();
                return true;
            })()""")
            time.sleep(1)
            assert not any(
                name.endswith((" popup", " dialog", " secondary", " hidden"))
                for name in runtime()["managed"]
            ), runtime()
            assert runtime()["states"] == saved, runtime()
            configs = set_rule(secondary_title, "title")
            expected = current_state(secondary_title)
            assert capture_window(secondary_title, secondary_title)
            assert_capture(secondary_title, secondary_title, expected, saved, configs)
            emit("manual-capture-after-main-close-" + backend, {"matched": True})
            restore_fixture()
            command("main")
            expected = {
                key: main_geometry[key]
                for key in ["x", "y", "width", "height", "workspace", "monitor", "maximized"]
            }
            wait_window(title, expected)
            wait_learning(title)
            emit("main-only-reopen-" + backend, {"matched": True})
            stop_client(process)
            process.stdin.close()

    try:
        wait_ready()
        indicator_enabled = ev("""hallwaywmTest.Main.extensionManager.lookup(hallwaywmTest.uuid)
            .stateObj._settings.get_boolean('show-indicator')""")
        ev("""hallwaywmTest.Main.extensionManager.lookup(hallwaywmTest.uuid)
            .stateObj._settings.set_boolean('show-indicator',true); true""")
        time.sleep(0.2)
        for color, variant in [("#ffffff", "dark"), ("#101010", "light")]:
            ev(
                """const e=hallwaywmTest.Main.extensionManager.lookup(hallwaywmTest.uuid).stateObj;
                e._indicator.get_children().find(actor=>actor instanceof hallwaywmTest.St.Icon)
                    .set_style(%s); true"""
                % json.dumps("color: " + color + ";")
            )
            time.sleep(0.2)
            icon = ev("""hallwaywmTest.Main.extensionManager.lookup(hallwaywmTest.uuid).stateObj
                ._indicator.get_children().find(actor=>actor instanceof hallwaywmTest.St.Icon).gicon.to_string()""")
            assert icon.endswith("hallwaywm-tray-" + variant + ".png"), icon
        ev(
            """const e=hallwaywmTest.Main.extensionManager.lookup(hallwaywmTest.uuid).stateObj;
            e._indicator.get_children().find(actor=>actor instanceof hallwaywmTest.St.Icon).set_style(null);
            e._settings.set_boolean('show-indicator',%s); true"""
            % json.dumps(indicator_enabled)
        )
        emit("hallwaywm-panel-identity", {"dark": True, "light": True})
        if PROFILES:
            run_profile_cases()
            emit("profiles-result", "PASS")
            return
        if WORKSPACES:
            run_monitor_workspace_cases()
            run_workspace_cases()
            emit("workspaces-result", "PASS")
            return
        layout(True)
        time.sleep(2)
        if not HALF_SCREEN:
            run_main_window_cases()
        if MAIN_WINDOW:
            emit("main-window-result", "PASS")
            return
        if not HALF_SCREEN:
            run_monitor_workspace_cases()
        if not HALF_SCREEN:
            baseline = {}
            for backend in ["wayland", "x11"]:
                process = open_client(backend)
                title = "HallwayWM Test " + backend
                wait_window(title)
                wait_learning(title)
                ev(
                    """hallwaywmTest.Main.overview.hide();
                    global.get_window_actors().map(a => a.meta_window)
                      .filter(w => w.get_title() === %s).forEach(w => {
                        w.unmaximize();
                        w.move_to_monitor(1);
                        w.change_workspace_by_index(2, false);
                        w.move_resize_frame(false, 2400, 180, 900, 600);
                    }); true"""
                    % json.dumps(title)
                )
                time.sleep(2)
                state = wait_window(title)
                baseline[title] = {
                    key: state[key]
                    for key in ["x", "y", "width", "height", "workspace", "monitor", "maximized"]
                }
                assert state["workspace"] == 2 and state["monitor"] == 1, state
                stop_client(process)
                ev(
                    "global.workspace_manager.get_workspace_by_index(0).activate(global.get_current_time()); true"
                )
                time.sleep(0.5)
                process = open_client(backend)
                wait_window(title, baseline[title])
                emit("reopen-" + backend, {"matched": True, **baseline[title]})
                stop_client(process)

            layout(False)
            time.sleep(2)
            process = open_client("wayland")
            wait_window("HallwayWM Test wayland")
            wait_learning("HallwayWM Test wayland")
            ev("""global.get_window_actors().map(a => a.meta_window)
                .filter(w => w.get_title() === 'HallwayWM Test wayland').forEach(w => {
                    w.move_to_monitor(0);
                    w.change_workspace_by_index(1, false);
                    w.move_resize_frame(false, 100, 150, 800, 500);
                }); true""")
            time.sleep(2)
            notebook = wait_window("HallwayWM Test wayland")
            assert notebook["monitor"] == 0 and notebook["x"] + notebook["width"] <= 1920, notebook
            # A window born without the external monitor uses its docked app profile on reconnect.
            layout(True)
            wait_window("HallwayWM Test wayland", baseline["HallwayWM Test wayland"])
            wait_learning("HallwayWM Test wayland")
            time.sleep(2)
            stop_client(process)
            emit("opened-without-external-then-reconnected", {"matched": True})
            for backend in ["wayland", "x11"]:
                open_client(backend)
                wait_window("HallwayWM Test " + backend, baseline["HallwayWM Test " + backend])
            time.sleep(4)
            before = windows()
            for cycle in range(2):
                layout(False)
                for window in snapshot():
                    assert (
                        window["monitor"] == 0
                        and window["x"] >= 0
                        and window["y"] >= 0
                        and window["x"] + window["width"] <= 1920
                        and window["y"] + window["height"] <= 1200
                    ), window
                layout(True)
                assert windows() == before, {"before": before, "after": windows()}
                emit("placement-kvm-cycle-" + str(cycle + 1), {"matched": True})
            for process in clients:
                stop_client(process)
            # Read the Shell's live settings: this synchronous worker has no GLib
            # main loop to refresh its own keyfile-backend cache after another process writes.
            stored = ev(
                'hallwaywmTest.Main.extensionManager.lookup("'
                + UUID
                + '").stateObj._settings.get_string("window-app-states")'
            )
            assert any(len(state.get("layouts", {})) >= 2 for state in stored.values()), stored
            profiles = [
                profile
                for state in stored.values()
                for profile in state.get("layouts", {}).values()
            ]
            assert any(
                profile.get("x") == 100 and profile.get("width") == 800 for profile in profiles
            ), stored
            assert any(
                profile.get("x") == 2400 and profile.get("width") == 900 for profile in profiles
            ), stored
            emit("separate-layout-profiles", {"matched": True})
            ev("hallwaywmTest.GLib.MainContext.default().iteration(false); true")
            shell.terminate()
            shell.wait(timeout=10)
            time.sleep(1)
            shell = subprocess.Popen(
                [
                    "gnome-shell",
                    "--wayland",
                    "--headless",
                    "--virtual-monitor",
                    "2560x1600",
                    "--virtual-monitor",
                    "3440x1440",
                    "--wayland-display",
                    "hallwaywm-test",
                ],
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            wait_ready()
            layout(True)
            time.sleep(2)
            assert not snapshot(), "Deja must not reopen applications itself"
            for backend in ["wayland", "x11"]:
                process = open_client(backend)
                wait_window("HallwayWM Test " + backend, baseline["HallwayWM Test " + backend])
                emit("new-shell-" + backend, {"matched": True})
                stop_client(process)
            errors = call(
                "org.gnome.Shell.Extensions",
                "/org/gnome/Shell/Extensions",
                "org.gnome.Shell.Extensions",
                "GetExtensionErrors",
                "(s)",
                (UUID,),
            )[0]
            assert not errors, errors
            process = open_client("wayland")
            wait_window("HallwayWM Test wayland", baseline["HallwayWM Test wayland"])
            wait_learning("HallwayWM Test wayland")
            ev("""global.get_window_actors().map(a => a.meta_window)
                .filter(w => w.get_title() === 'HallwayWM Test wayland').forEach(w => {
                    w.move_to_monitor(0);
                    w.move_resize_frame(false, 200, 200, 800, 500);
                }); true""")
            time.sleep(2)
            # GNOME keeps secondary monitors on all workspaces by default.
            notebook_docked = {
                "x": 200,
                "y": 200,
                "width": 800,
                "height": 500,
                "monitor": 0,
            }
            wait_window("HallwayWM Test wayland", notebook_docked)
            stop_client(process)
            process = open_client("wayland")
            wait_window("HallwayWM Test wayland", notebook_docked)
            stop_client(process)
            emit("notebook-placement-with-external-connected", {"matched": True})

        def browser_title():
            for _ in range(100):
                for title in windows():
                    if title.startswith("HallwayWM Test Browser"):
                        return title
                time.sleep(0.15)
            raise AssertionError("Private browser window did not appear")

        def close_window(title, process):
            ev(
                """global.get_window_actors().map(a=>a.meta_window)
                .filter(w=>w.get_title()===%s)
                .forEach(w=>w.delete(global.get_current_time())); true"""
                % json.dumps(title)
            )
            for _ in range(50):
                if title not in windows():
                    break
                time.sleep(0.1)
            assert title not in windows()
            # Let Chromium commit its own window-placement preferences before restart.
            time.sleep(0.5)
            stop_client(process)

        for backend in ["wayland", "x11", "browser"]:
            for direction in ["Left", "Right"]:
                process = open_client(backend)
                title = browser_title() if backend == "browser" else "HallwayWM Test " + backend
                wait_window(title)
                wait_learning(title)
                ev(
                    """hallwaywmTest.Main.overview.hide();
                    global.get_window_actors().map(a=>a.meta_window)
                    .filter(w=>w.get_title()===%s).forEach(w=>{
                        w.unmaximize();
                        w.move_to_monitor(1);
                        w.change_workspace(global.workspace_manager.get_workspace_by_index(2));
                        global.workspace_manager.get_workspace_by_index(2).activate(global.get_current_time());
                        w.move_resize_frame(false,2400,180,900,600);
                        w.activate(global.get_current_time());
                    }); true"""
                    % json.dumps(title)
                )
                time.sleep(1)
                ev(
                    """globalThis.hallwaywmTest.keyboard ??= global.stage.get_context().get_backend()
                        .get_default_seat().create_virtual_device(hallwaywmTest.Clutter.InputDeviceType.KEYBOARD_DEVICE);
                    hallwaywmTest.keyboard.notify_keyval(hallwaywmTest.GLib.get_monotonic_time(),hallwaywmTest.Clutter.KEY_Super_L,hallwaywmTest.Clutter.KeyState.PRESSED);
                    hallwaywmTest.keyboard.notify_keyval(hallwaywmTest.GLib.get_monotonic_time(),hallwaywmTest.Clutter.KEY_%s,hallwaywmTest.Clutter.KeyState.PRESSED);
                    hallwaywmTest.keyboard.notify_keyval(hallwaywmTest.GLib.get_monotonic_time(),hallwaywmTest.Clutter.KEY_%s,hallwaywmTest.Clutter.KeyState.RELEASED);
                    hallwaywmTest.keyboard.notify_keyval(hallwaywmTest.GLib.get_monotonic_time(),hallwaywmTest.Clutter.KEY_Super_L,hallwaywmTest.Clutter.KeyState.RELEASED); true"""
                    % (direction, direction)
                )
                time.sleep(2)
                half = wait_window(title)
                assert half["monitor"] == 1 and not half["maximized"], half
                assert half["width"] == 1720, half
                expected = {
                    key: half[key]
                    for key in ["x", "y", "width", "height", "monitor", "workspace", "maximized"]
                }
                close_window(title, process)
                process = open_client(backend)
                wait_window(title, expected)
                # Check settled geometry rather than a transient opening frame.
                time.sleep(1)
                wait_window(title, expected)
                emit("half-screen-" + backend + "-" + direction.lower(), {"matched": True})
                if backend == "browser" and direction == "Left":
                    time.sleep(3)
                    layout(False)
                    notebook = wait_window(title)
                    assert (
                        notebook["monitor"] == 0
                        and 0 <= notebook["x"] < 1920
                        and 0 <= notebook["y"] < 1200
                    ), notebook
                    layout(True)
                    wait_window(title, expected)
                    emit("browser-half-screen-kvm", {"matched": True})
                close_window(title, process)
            process = open_client(backend)
            title = browser_title() if backend == "browser" else "HallwayWM Test " + backend
            wait_window(title)
            wait_learning(title)
            ev(
                """global.get_window_actors().map(a=>a.meta_window)
                .filter(w=>w.get_title()===%s).forEach(w=>w.maximize()); true"""
                % json.dumps(title)
            )
            time.sleep(2)
            wait_window(title, {"maximized": True, "monitor": 1})
            if backend == "browser":
                browser_identity = ev(
                    "global.get_window_actors().map(a=>a.meta_window)"
                    ".find(w=>w.get_title()===%s).get_wm_class()" % json.dumps(title)
                )
                assert browser_identity, "The browser window has no application identity"
            close_window(title, process)
            process = open_client(backend)
            wait_window(title, {"maximized": True, "monitor": 1})
            emit("full-maximize-" + backend, {"matched": True})
            close_window(title, process)
            if backend == "browser":
                # The browser retains maximized startup state in its own private profile.
                # HallwayWM's saved half-screen placement must still win on the next launch.
                ev("""(() => {
                    const e=hallwaywmTest.Main.extensionManager.lookup(hallwaywmTest.uuid).stateObj;
                    const states=JSON.parse(e._settings.get_string('window-app-states'));
                    const state=states[%s];
                    state.maximized=false;
                    state.layouts[e._layoutKey()].maximized=false;
                    e._settings.set_string('window-app-states',JSON.stringify(states));
                    return true;
                })()""" % json.dumps(browser_identity))
                process = open_client(backend)
                wait_window(title, expected)
                wait_learning(title)
                emit("browser-maximized-start-to-half-screen", {"matched": True})
                close_window(title, process)

        emit("placement-result", "PASS")
    finally:
        for process in clients:
            stop_client(process)


try:
    if HALF_SCREEN or MAIN_WINDOW or WORKSPACES or PROFILES:
        run_placement_cases()
        emit("result", "PASS")
        raise SystemExit(0)
    for attempt in range(100):
        if shell.poll() is not None:
            raise RuntimeError("Isolated GNOME exited: " + str(shell.returncode))
        try:
            info = call(
                "org.gnome.Shell.Extensions",
                "/org/gnome/Shell/Extensions",
                "org.gnome.Shell.Extensions",
                "GetExtensionInfo",
                "(s)",
                (UUID,),
            )[0]
            # Metadata can be visible before asynchronous extension activation finishes.
            if info.get("state") == 1 or info.get("error"):
                break
        except GLib.Error:
            pass
        time.sleep(0.2)
    else:
        raise RuntimeError("Isolated GNOME did not initialize")
    emit("extension", info)
    assert info["state"] == 1 and not info["error"], "Extension must be active without errors"
    emit(
        "api",
        ev(
            'JSON.stringify({size: global.display.get_size(), methods: ["get_frame_rect", "is_maximized", "maximize", "unmaximize", "move_resize_frame", "get_workspace", "change_workspace_by_index"].map(m => [m, typeof hallwaywmTest.Meta.Window.prototype[m]])})'
        ),
    )
    layout(True)
    client_code = """import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib
Gtk.init()
windows = []
for title in ['Notebook', 'External', 'Maximized', 'Minimized', 'Fullscreen', 'Workspace']:
    window = Gtk.Window(title='HallwayWM Test '+title, default_width=800, default_height=500)
    window.set_child(Gtk.Label(label=title))
    window.present()
    windows.append(window)
GLib.MainLoop().run()
"""
    client_env = os.environ.copy()
    client_env.update(
        {"WAYLAND_DISPLAY": "hallwaywm-test", "GDK_BACKEND": "wayland", "GSK_RENDERER": "cairo"}
    )
    client = subprocess.Popen(
        [sys.executable, "-c", client_code], env=client_env, stdout=log, stderr=log
    )
    xclient_env = client_env.copy()
    xclient_env.update(
        {
            "DISPLAY": ev('hallwaywmTest.GLib.getenv("DISPLAY")'),
            "XAUTHORITY": ev('hallwaywmTest.GLib.getenv("XAUTHORITY")'),
            "GDK_BACKEND": "x11",
        }
    )
    xclient = subprocess.Popen(
        [
            sys.executable,
            "-c",
            client_code.replace(
                "['Notebook', 'External', 'Maximized', 'Minimized', 'Fullscreen', 'Workspace']",
                "['XWayland']",
            ),
        ],
        env=xclient_env,
        stdout=log,
        stderr=log,
    )
    for attempt in range(50):
        if len(snapshot()) == 7:
            break
        time.sleep(0.2)
    # Meta actors appear before GTK has completed its initial size negotiation.
    # Start the KVM workload only after mapped clients accept programmatic placement.
    time.sleep(2)
    assert ev("global.workspace_manager.n_workspaces") == 4
    ev(
        """
        hallwaywmTest.Main.overview.hide();
        global.get_window_actors().map(actor => actor.meta_window)
            .filter(window => window.get_title()?.startsWith("HallwayWM Test"))
            .forEach(window => {
                const title = window.get_title();
                window.unmaximize();
                window.move_to_monitor(title.endsWith("Notebook") ? 0 : 1);
                window.move_resize_frame(false, title.endsWith("Notebook") ? 200 : 2400,
                    title.endsWith("Minimized") ? 400 : 200, 1000, 700);
            });
        true
        """
    )
    time.sleep(1)
    ev(
        """
        global.get_window_actors().map(actor => actor.meta_window)
            .filter(window => window.get_title()?.startsWith("HallwayWM Test"))
            .forEach(window => {
                const title = window.get_title();
                if (title.endsWith("Maximized")) {
                    window.maximize();
                }
                if (title.endsWith("Minimized")) {
                    window.minimize();
                }
                if (title.endsWith("Fullscreen")) {
                    window.make_fullscreen();
                }
                if (title.endsWith("Workspace")) {
                    window.change_workspace(global.workspace_manager.get_workspace_by_index(2));
                }
            });
        true
        """
    )
    ev(
        'hallwaywmTest.Main.extensionManager.lookup("'
        + UUID
        + '").stateObj._sessionLayouts.scheduleSave(); true'
    )
    time.sleep(5)
    baseline = snapshot()
    emit(
        "baseline",
        {
            "windows": len(baseline),
            "wayland": sum(w["clientType"] == 0 for w in baseline),
            "xwayland": sum(w["clientType"] == 1 for w in baseline),
        },
    )
    assert len(baseline) == 7
    assert (
        next(window for window in baseline if window["title"].endswith("Workspace"))["workspace"]
        == 2
    )
    assert all(
        window["monitor"] == (0 if window["title"].endswith("Notebook") else 1)
        for window in baseline
    ), baseline
    for cycle in range(3):
        layout(False)
        notebook = snapshot()
        assert len(notebook) == len(baseline)
        assert all(
            w["monitor"] == 0
            and w["x"] >= 0
            and w["y"] >= 0
            and w["x"] + w["width"] <= 1920
            and w["y"] + w["height"] <= 1200
            for w in notebook
        ), "Windows must remain inside the notebook display"
        layout(True)
        restored = snapshot()
        if restored != baseline:
            emit("expected", baseline)
            emit("actual", restored)
        emit(
            "restored-" + str(cycle + 1),
            {"matched": restored == baseline, "windows": len(restored)},
        )
        assert restored == baseline, "Window layout mismatch after reconnect"

    # Equal desktop bounds with another primary monitor must have independent snapshots.
    layout(True, primary=0)
    ev("""global.get_window_actors().map(a=>a.meta_window)
        .filter(w=>w.get_title()==='HallwayWM Test External')
        .forEach(w=>w.move_resize_frame(false,2700,350,900,600)); true""")
    time.sleep(2)
    layout(True, primary=1)
    assert snapshot() == baseline, "Primary-monitor layouts collided"
    emit("primary-monitor-layout", {"matched": True})

    # Keep live layouts through lock mode, including monitor changes while locked.
    ev("hallwaywmTest.Main.sessionMode.pushMode('unlock-dialog'); true")
    lock_state = ev("""const e=hallwaywmTest.Main.extensionManager.lookup(hallwaywmTest.uuid).stateObj;
        JSON.stringify({locked:e._sessionLocked, indicator:e._indicator===null,
            saved:e._sessionLayouts.layouts.get(e._sessionLayouts.key()).size})""")
    assert lock_state == {"locked": True, "indicator": True, "saved": 7}, lock_state
    layout(False)
    layout(True)
    ev("hallwaywmTest.Main.sessionMode.popMode('unlock-dialog'); true")
    time.sleep(4)
    assert snapshot() == baseline, "Locked monitor transitions lost the live layout"
    emit("lock-monitor-transition", {"matched": True})
    call(
        "org.gnome.Shell.Extensions",
        "/org/gnome/Shell/Extensions",
        "org.gnome.Shell.Extensions",
        "DisableExtension",
        "(s)",
        (UUID,),
    )
    call(
        "org.gnome.Shell.Extensions",
        "/org/gnome/Shell/Extensions",
        "org.gnome.Shell.Extensions",
        "EnableExtension",
        "(s)",
        (UUID,),
    )
    captured = ev(
        'const e=hallwaywmTest.Main.extensionManager.lookup("'
        + UUID
        + '").stateObj._sessionLayouts; JSON.stringify(e.layouts.get(e.key()).size)'
    )
    emit("captured-on-enable", captured)
    assert captured >= 7, "Existing windows were not captured on enable"
    call(
        "org.gnome.Shell.Extensions",
        "/org/gnome/Shell/Extensions",
        "org.gnome.Shell.Extensions",
        "DisableExtension",
        "(s)",
        (UUID,),
    )
    time.sleep(3)
    call(
        "org.gnome.Shell.Extensions",
        "/org/gnome/Shell/Extensions",
        "org.gnome.Shell.Extensions",
        "EnableExtension",
        "(s)",
        (UUID,),
    )
    errors = call(
        "org.gnome.Shell.Extensions",
        "/org/gnome/Shell/Extensions",
        "org.gnome.Shell.Extensions",
        "GetExtensionErrors",
        "(s)",
        (UUID,),
    )[0]
    emit("errors", errors)
    assert not errors, "The extension reported a runtime error"
    if PLACEMENT:
        client.terminate()
        client.wait(timeout=5)
        client = None
        xclient.terminate()
        xclient.wait(timeout=5)
        xclient = None
        time.sleep(1)
        run_placement_cases()
    emit("result", "PASS")
finally:
    if client is not None:
        client.terminate()
        client.wait(timeout=5)
    if xclient is not None:
        xclient.terminate()
        xclient.wait(timeout=5)
    shell.terminate()
    try:
        shell.wait(timeout=10)
    except subprocess.TimeoutExpired:
        shell.kill()
        shell.wait()
    log.close()
