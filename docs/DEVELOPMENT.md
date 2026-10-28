# HallwayWM development and validation

HallwayWM is a standalone GNOME Shell extension. Its build, tests and installation use this checkout and the native dependencies described below. Run the commands from the project root.

The build manages persistent application placement and live window layouts in one GNOME extension. It selects the first normal window per application for persistent rules, saves separate monitor-layout profiles, restores half-screen geometry correctly, and keeps rule editing available in normal window menus. Its extension identity is `hallwaywm@ltecosta.github.io`. Application identities, titles, rules and captured geometry stay in the user's private dconf database.

The placement engine is in `src/extension.ts` and `src/sessionLayouts.ts`. `src/displayProfiles.ts` supplies profile identity, copying and linked resolution; `src/profileManager.ts` integrates native monitor discovery and profile actions. `src/profilePreferences.ts`, `src/prefs.ts` and `src/windowMenu.ts` implement the native controls, sharing restore terminology through `src/restoreOptions.ts`. `src/types.d.ts` shares the rule, capture and monitor-profile contracts. The original GPL-3.0 license is in [LICENSE](../LICENSE); [project credits](../CREDITS.md) identify the source projects and contributions. The stable `org.gnome.shell.extensions.deja-window` GSettings schema and private dconf path preserve existing application rules and layout profiles.

Manual capture saves the currently selected normal, non-transient, taskbar-visible window, including a window excluded from automatic tracking as secondary. The title-bar menu captures its own window; preferences capture the most recently used matching window. Locked rules remain locked. Capture does not promote, move or automatically track a secondary window. Dialogs and utility surfaces remain ineligible, and capture reports failure while monitor-layout writes are suspended.

Workspace restoration follows Mutter's current workspace policy and the intended destination monitor. With workspaces restricted to the primary monitor, restoring an application to a secondary monitor preserves the active workspace. Primary-monitor windows retain their rule's workspace restoration and switching behavior, including when the laptop is the only display. When every monitor participates in workspaces, secondary-monitor rules restore and switch normally. Monitor and window events complete workspace, sticky and maximized state only after the destination monitor is effective. A changed frame on the old monitor triggers a bounded retry for late Wayland configurations; unchanged frames do not repeat the request. Successful restores activate their requested workspace without a fixed delay. Automatic learning stays paused until restoration completes; pending work is cancelled on closure, disable, monitor-layout changes, user moves or a two-second transition deadline.

## Open-window layouts

`src/sessionLayouts.ts` captures the current geometry, monitor, workspace, maximized, minimized, fullscreen, above and sticky state of every normal, non-transient, taskbar-visible window. This includes additional windows of the same application and windows without persistent rules. Snapshots stay in memory, use the device-aware display-profile key, and are removed when their windows close. Disabling the extension clears them.

After a monitor change, one three-second settling callback restores saved main-window positions for the automatically detected display profile. Persistent profiles take precedence over temporary live snapshots. Live snapshots restore additional windows and main windows without saved positions in that profile. All monitor-profile restores preserve the active workspace and follow Mutter's primary-monitor workspace policy. Persistent learning and snapshot updates remain paused during the transition, including late Wayland configurations.

The extension participates in the user and unlock-dialog session modes to retain window identities and live layouts while the screen is locked. Lock mode hides the indicator, removes the window-menu integration and suspends restoration and saving. On unlock, monitor changes made while locked are restored; an unchanged monitor arrangement keeps its current placement. The Active switch pauses both application rules and session-layout handling.

## Persistent display profiles

Native Mutter monitor getters provide device identities. Logical screen position, size, scale and primary status complete the profile key; monitor enumeration order does not. Saved windows also retain the destination monitor identity. `display-profiles` stores names, monitor descriptions and optional source links, `active-display-profile` identifies the connected setup, and `profile-request` carries native preference actions and replies. These values and `window-app-states` remain private in dconf.

Independent copies adapt geometry through explicit source-to-destination screen mappings. Linked profiles resolve source positions on use, including linked chains, and reject cycles. Saving into a linked profile is disabled. Detaching makes an independent copy of its currently resolved positions. Profile copying and link operations apply to main-window placement; unrelated display profiles remain intact. Application matching rules and restore flags apply across profiles.

**Save Positions** captures managed main windows without changing their rules. **Save & Lock** captures the same eligible windows, then locks only successfully saved applications. Existing enabled rules retain their matching and restore flags. Default-managed apps receive exact-class rules with their current default restore flags; an existing disabled exact-class slot is reused. Global Defaults, exclusions, unrelated rules and other profiles' saved positions remain unchanged. Locks apply per application across profiles, and explicit captures continue to work while locked. Unlock the rule in **Applications** to resume automatic learning. Deferred saves recheck the effective rule before writing, so a pending automatic capture respects a newly applied lock. Both actions reject linked profiles and monitor transitions.

The first connected setup can adopt a matching geometry-only record. Unidentified saved layouts remain available as templates and are not automatically assigned to new physical devices. A new setup without saved positions keeps the desktop's current arrangement until positions are learned or explicitly saved.

## Build, installation and validation

The build requires Node.js 22 or newer, npm and the native `glib-compile-schemas` command. Python 3 supplies the installation/archive helpers. Install the locked development dependencies with `npm ci --ignore-scripts`, run `npm run check` for strict type checking, then `npm run build`. The compiler and GNOME declarations are pinned in `package-lock.json`. The narrow `types/window-menu.d.ts` declaration covers the internal Shell window-menu module. Native GNOME 51 integration tests validate the declarations against the installed APIs.

`dist/` contains the generated JavaScript, metadata, icons, license and compiled schema. It and `node_modules/` remain outside Git; TypeScript is the only maintained implementation source. The build preserves the GNOME import paths and runtime class fields. Preferences implement the asynchronous native entry point. Rules and private profiles retain their native GSettings format.

Run `bash scripts/install.sh` as the desktop user after dependency installation. It builds the payload, installs regular files in `${XDG_DATA_HOME:-$HOME/.local/share}/gnome-shell/extensions/hallwaywm@ltecosta.github.io` and compiles the installed schema. It preserves dconf preferences and does not reload the active Shell. After the first installation, sign out and back in so GNOME discovers the extension, then enable it with `gnome-extensions enable hallwaywm@ltecosta.github.io`. Subsequent JavaScript updates also require a new graphical login. `bash scripts/pack.sh` builds the same payload and creates the extension archive under `temp/`.

Run `bash -n scripts/install.sh scripts/pack.sh` and `glib-compile-schemas --strict --dry-run src/schemas`. Installation can be checked with a temporary `XDG_DATA_HOME`. The native preferences smoke test requires GJS, GTK 4, libadwaita, D-Bus and an accessible graphical session. It discovers GNOME Shell libraries from the installation; set `GNOME_SHELL_LIBDIR` for a custom library location. It constructs all four pages using isolated D-Bus, temporary configuration directories and memory-backed rules, without showing a window:

```sh
npm run test:preferences
```

The self-contained `tests/integration.py` suite builds this checkout and exercises HallwayWM alone in an isolated GNOME session. It reads the local extension metadata and uses explicit disposable preferences. It accepts uncommitted source changes for development. Run the base workload or select a scenario:

```sh
npm run test:profiles
npm run test:integration
npm run test:integration -- --placement
npm run test:integration -- --half-screen
npm run test:integration -- --main-window
npm run test:integration -- --workspaces
npm run test:integration -- --profiles
```

The native integration suite requires GNOME Shell 51 with headless virtual monitors, D-Bus, Python 3 with PyGObject, GTK 3/4, XWayland and software rendering. Browser scenarios use a Chromium-compatible executable discovered on `PATH`; set `HALLWAYWM_TEST_BROWSER` to select one explicitly. Missing required dependencies fail the selected check rather than count as a successful test. Temporary XDG directories, a separate D-Bus session, disposable windows and a private browser profile isolate the fixture from the desktop session. Test processes and temporary files are cleaned up after completion.

The base workload covers repeated monitor transitions, primary-monitor changes, changes while locked and immediate capture on enable. The placement modes cover persistence, half-screen geometry, main-window eligibility and workspaces. The profile workload covers Save & Lock, queued-save cancellation, explicit resaving, reopening, unlock learning, exclusions, separate display records, saved-profile priority, equal geometry with distinct device identities, copy/link/detach actions and proportional monitor mapping. Virtual monitor sizes and application identities are deterministic fixtures. Physical monitor/KVM acceptance and a fresh graphical login remain separate checks.

JavaScript syntax is checked with the installed GJS parser (`Reflect.parse` with `target: "module"`); the isolated integration suite validates the Shell imports and behavior.

## Visual identity

The panel uses the supplied `hallwaywm-tray-dark.png` and `hallwaywm-tray-light.png` variants, selecting them from the panel icon's effective foreground color. The preferences show `hallwaywm.png`; the README uses the supplied wordmark in dark mode and the application icon in light mode. Assets are copied unchanged from the supplied identity pack and recorded in [credits](../CREDITS.md).
