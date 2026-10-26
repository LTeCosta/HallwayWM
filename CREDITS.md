# HallwayWM credits

HallwayWM brings together the application-placement and monitor-layout behavior developed in the workstation's customized Deja Window and Window State Manager solutions.

## Deja Window

[Deja Window](https://github.com/ihpled/deja-window), by its original authors and contributors, supplies the codebase from which HallwayWM is derived. Application rules, preferences, the native window-menu integration and the global-defaults globe icon originate in that project. Its Git history and GPL-3.0 license are retained. The workstation fork added TypeScript, per-layout profiles, primary-monitor workspace handling and robust asynchronous Wayland placement.

## Window State Manager

[Window State Manager](https://github.com/kishorviswanathan/window-state-manager), by Kishor Viswanathan and contributors, supplies the monitor/KVM layout-restoration concept consolidated here. Its monitor-restoration workflow informs the handling of already-open windows, immediate capture and repeated monitor transitions. HallwayWM implements this responsibility in a new TypeScript session-layout module coordinated with its shared placement engine.

## HallwayWM

Lucas Costa maintains HallwayWM and its workstation integration. Contributions to the unified layout engine, lifecycle handling, integration tests and project identity are covered by the GPL-3.0 license in `LICENSE`.

## Visual identity

The HallwayWM application icon, full wordmark and light/dark panel variants were supplied by Lucas Costa for this project. The original PNG assets are preserved, and the panel chooses a variant from its actual foreground color.
