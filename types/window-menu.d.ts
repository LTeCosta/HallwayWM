// WindowMenu is an internal Shell module missing from the upstream declarations.
// Keep this boundary aligned with the installed GNOME window-menu implementation.
declare module 'resource:///org/gnome/shell/ui/windowMenu.js' {
    import type Meta from 'gi://Meta';
    import type Clutter from 'gi://Clutter';
    import {PopupMenu} from 'resource:///org/gnome/shell/ui/popupMenu.js';
    export class WindowMenu extends PopupMenu {
        constructor(window: Meta.Window, sourceActor: Clutter.Actor);
        _buildMenu(window: Meta.Window): void;
    }
}
