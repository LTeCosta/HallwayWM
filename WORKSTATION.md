# Deja Window workstation build

This branch maintains `17-workstation.6`, based on upstream commit `c2cac5444a1bd56e6a287f0d688728cfea4bf7c4` and GNOME Extensions release 17. The release archive SHA-256 is `3842806146a7193d4caab3c3b0ed78c163214a4269a09d29cd51deafcb4e3a17`.

The build selects the first normal window per application, saves separate monitor-layout profiles, restores half-screen geometry correctly, waits for monitor transitions to settle, and keeps rule editing available in normal window menus. It uses `deja-window@workstation.local` so catalog updates do not replace the custom build. Application identities, titles, rules and captured geometry stay in the user's private dconf database.

Sources were maintained in `LTeCosta/linux-cachyos-rogstrix` at commit `2ec31da982ac557bc06a3e1d2c299013800cfb67`, under `configs/user/.local/share/gnome-shell/extensions/deja-window@workstation.local/`. The original GPL-3.0 license is in `LICENSE`.

Manual capture saves the currently selected normal, non-transient, taskbar-visible window, including a window excluded from automatic tracking as secondary. The title-bar menu captures its own window; preferences capture the most recently used matching window. Locked rules remain locked. Capture does not promote, move or automatically track a secondary window. Dialogs and utility surfaces remain ineligible, and capture reports failure while monitor-layout writes are suspended.

Workspace restoration follows Mutter's current workspace policy and the intended destination monitor. With workspaces restricted to the primary monitor, restoring an application to a secondary monitor preserves the active workspace. Primary-monitor windows retain their rule's workspace restoration and switching behavior, including when the laptop is the only display. When every monitor participates in workspaces, secondary-monitor rules restore and switch normally. The delayed activation rechecks the window's current monitor and workspace.

## Installation and validation

Run `bash scripts/install.sh` as the desktop user. It installs regular files in `${XDG_DATA_HOME:-$HOME/.local/share}/gnome-shell/extensions/deja-window@workstation.local` and compiles the schema. It preserves dconf preferences and does not reload the active Shell. Enable the extension and sign in again when deploying a changed build.

Run `bash -n scripts/install.sh scripts/pack.sh`, `glib-compile-schemas --strict --dry-run src/schemas`. `bash scripts/pack.sh` creates the extension archive under `temp/`. Installation can be checked with a temporary `XDG_DATA_HOME` without changing the desktop.

The workstation repository's `tests/gnome_window_state_manager_integration.py` exercises the pinned builds together in an isolated GNOME session. Its `--placement`, `--half-screen`, `--main-window` and `--workspaces` cases cover persistence, monitor transitions and window eligibility. Physical monitor/KVM acceptance remains a separate check.

JavaScript syntax is checked with the installed GJS parser (`Reflect.parse` with `target: "module"`); the isolated integration suite validates the Shell imports and behavior.
