# HallwayWM

Window placement and monitor-layout management for GNOME Wayland.

HallwayWM remembers where applications belong and keeps open windows organized when monitors connect, disconnect or switch through a KVM. One extension coordinates application rules, live window layouts, workspaces and asynchronous Wayland configuration.

## Features

- Persistent position, size, monitor and workspace rules for each application's main window.
- Per-session layouts for all normal open windows, including additional windows of the same application.
- Independent layouts for different monitor arrangements and primary displays.
- Maximized, minimized, fullscreen, above and sticky state restoration.
- Workspace handling that respects GNOME's primary-monitor workspace policy.
- A **HallwayWM** submenu in the native window menu (`Alt+Space`) for rules and manual capture.
- Preferences with application overrides, global defaults, configuration import/export and an Active switch.
- Window-layout retention through screen locking, with restoration deferred until unlock.

Rules and captured application profiles remain private in the user's dconf database. Live window snapshots stay in memory and expire when their windows close or the extension is disabled. HallwayWM opens no applications.

## Build and install

The supported environment is GNOME Shell 51, Node.js 22 or newer, npm, Python 3 and `glib-compile-schemas`.

From this checkout:

```sh
npm ci --ignore-scripts --workspaces=false
npm run check
bash scripts/install.sh
gnome-extensions enable hallwaywm@workstation.local
```

Sign out and back in to discover a new local extension or load changed JavaScript. The installer preserves private settings and copies generated JavaScript and assets as regular files. Open preferences with:

```sh
gnome-extensions prefs hallwaywm@workstation.local
```

`bash scripts/pack.sh` builds `temp/hallwaywm.zip`. Generated `dist/`, `node_modules/` and release archives stay outside Git. TypeScript is the maintained source.

See [operation, build validation and recovery](WORKSTATION.md) for the placement rules, session-layout lifecycle and isolated GNOME test matrix. The stable `org.gnome.shell.extensions.deja-window` settings schema preserves existing private rules and profiles.

## Credits and license

HallwayWM is derived from [Deja Window](https://github.com/ihpled/deja-window) and consolidates the open-window layout behavior of [Window State Manager](https://github.com/kishorviswanathan/window-state-manager). See [CREDITS.md](CREDITS.md) for their distinct contributions and project lineage.

The original Deja Window history and [GNU GPL version 3 license](LICENSE) are preserved.
