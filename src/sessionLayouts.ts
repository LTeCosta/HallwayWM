import GLib from 'gi://GLib';
import type Meta from 'gi://Meta';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import type DejaWindowExtension from './extension.js';
import type {LayoutState} from './types.js';

/** Keep each open window's placement for the monitor arrangements in this session. */
export class SessionLayouts {
    readonly layouts = new Map<string, Map<Meta.Window, LayoutState>>();
    readonly windows = new Set<Meta.Window>();
    saveId = 0;
    private activeLayout: string;

    constructor(private readonly extension: DejaWindowExtension) {
        this.activeLayout = this.key();
        for (const actor of global.get_window_actors()) this.track(actor.meta_window);
        this.capture();
    }

    key() {
        return JSON.stringify([this.extension._layoutKey(), Main.layoutManager.primaryIndex]);
    }

    track(window: Meta.Window | null) {
        if (!window || this.windows.has(window) || window.is_override_redirect()) return;
        this.windows.add(window);
        const changed = () => {
            this.extension._queueRestoreCompletion(window);
            this.scheduleSave();
        };
        for (const signal of ['position-changed', 'size-changed', 'workspace-changed',
            'notify::minimized', 'notify::maximized-horizontally', 'notify::maximized-vertically',
            'notify::fullscreen', 'notify::above', 'notify::on-all-workspaces',
            'notify::window-type', 'notify::transient-for']) {
            window.connectObject(signal, changed, this);
        }
        window.connectObject('unmanaging', () => {
            window.disconnectObject(this);
            this.windows.delete(window);
            for (const states of this.layouts.values()) states.delete(window);
            this.extension._forgetSessionWindow(window);
        }, this);
        this.scheduleSave();
    }

    suspend() {
        if (this.saveId) GLib.source_remove(this.saveId);
        this.saveId = 0;
    }

    topologyChanged() {
        this.suspend();
        this.activeLayout = this.key();
    }

    scheduleSave() {
        this.suspend();
        if (!this.extension._functionalityEnabled || this.extension._sessionLocked) return;
        // A frame change can arrive before the layout manager's monitor signal.
        if (this.activeLayout !== this.key()) return;
        const remaining = (this.extension._layoutSaveAfter - GLib.get_monotonic_time()) / 1000;
        this.saveId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, Math.max(500, Math.ceil(remaining)), () => {
            this.saveId = 0;
            this.capture();
            return GLib.SOURCE_REMOVE;
        });
    }

    capture() {
        if (!this.extension._functionalityEnabled || this.extension._sessionLocked ||
            this.activeLayout !== this.key() ||
            GLib.get_monotonic_time() < this.extension._layoutSaveAfter) return;
        const states = this.layouts.get(this.activeLayout) ?? new Map<Meta.Window, LayoutState>();
        this.layouts.set(this.activeLayout, states);
        for (const window of this.windows) {
            if (!this.extension._isMainWindowCandidate(window) || !window.get_workspace()) {
                states.delete(window);
                continue;
            }
            const handle = this.extension._getRestoreHandle(window);
            if (handle && (!handle.isRestoreApplied || handle.pendingRestore || handle.restoreIdleId)) continue;
            const rect = window.get_frame_rect();
            states.set(window, {
                x: rect.x, y: rect.y, width: rect.width, height: rect.height,
                monitor: window.get_monitor(), workspace: window.get_workspace().index(),
                maximized: window.is_maximized(), minimized: window.minimized,
                fullscreen: window.fullscreen, above: window.above, sticky: window.on_all_workspaces
            });
        }
    }

    restore() {
        const restored = new Set<Meta.Window>();
        const states = this.layouts.get(this.key());
        if (!states) return restored;
        for (const [window, state] of states) {
            if (!this.windows.has(window) || !this.extension._isMainWindowCandidate(window) ||
                !window.get_workspace()) continue;
            this.extension._restoreSessionWindow(window, state);
            restored.add(window);
        }
        return restored;
    }

    destroy() {
        this.suspend();
        for (const window of this.windows) window.disconnectObject(this);
        this.windows.clear();
        this.layouts.clear();
    }
}
