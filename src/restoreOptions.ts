import type {RestoreOption} from './types.js';

// Shared wording for application rules, default rules and the native window menu.
export const RESTORE_OPTIONS: RestoreOption[] = [
    { key: 'restore_size', label: 'Restore Size', subtitle: 'Restore the saved width and height for the active display profile.' },
    { key: 'restore_pos', label: 'Restore Position and Monitor', subtitle: 'Use the saved screen and position instead of default centering.' },
    {
        key: 'avoid_overlap',
        label: 'Avoid Same-App Overlap',
        subtitle: 'Allow the restored main window to shift when another window of the same app occupies that position.',
        dependsOn: 'restore_pos',
        defaultOn: true,
    },
    { key: 'restore_maximized', label: 'Restore Maximized State', subtitle: 'Restore whether the window was maximized or in its normal size.' },
    { key: 'restore_workspace', label: 'Restore Workspace', subtitle: 'Move to the saved workspace when the destination screen supports workspaces.' },
    {
        key: 'switch_to_workspace',
        label: 'Follow Window to Its Workspace',
        subtitle: 'Also take you to that workspace when the application opens. Display-profile changes keep your current workspace.',
        dependsOn: 'restore_workspace',
    },
    { key: 'restore_minimized', label: 'Restore Minimized State', subtitle: 'Restore whether the window was minimized; a saved minimized window can open hidden.' },
    { key: 'restore_above', label: 'Restore Always on Top State', subtitle: 'Restore whether the window was pinned above other windows.' },
    { key: 'restore_sticky', label: 'Restore Visibility Across Workspaces', subtitle: 'Restore whether the window was pinned to appear on every workspace.' },
];
