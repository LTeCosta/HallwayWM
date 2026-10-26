import type Meta from 'gi://Meta';

export type MatchMode = 'wm_class' | 'title';
export interface MatchRule {
    wm_class: string;
    match_mode?: MatchMode;
    is_regex?: boolean;
}
export interface RestoreFlags {
    restore_size?: boolean;
    restore_pos?: boolean;
    restore_maximized?: boolean;
    restore_workspace?: boolean;
    switch_to_workspace?: boolean;
    restore_minimized?: boolean;
    restore_above?: boolean;
    restore_sticky?: boolean;
    avoid_overlap?: boolean;
}
export type RestoreKey = keyof RestoreFlags;
export interface WindowRule extends MatchRule, RestoreFlags {
    enabled?: boolean;
    locked?: boolean;
}
export interface GlobalDefaults extends RestoreFlags {
    locked?: boolean;
    enabled?: boolean;
    excluded_apps?: MatchRule[];
}
export interface RestoreOption {
    key: RestoreKey;
    label: string;
    subtitle?: string;
    dependsOn?: RestoreKey;
    defaultOn?: boolean;
}
export interface LayoutState {
    monitor?: number;
    workspace?: number;
    x?: number;
    y?: number;
    width?: number;
    height?: number;
    maximized?: boolean;
    minimized?: boolean;
    above?: boolean;
    sticky?: boolean;
}
export interface ApplicationState extends LayoutState {
    layouts?: Record<string, LayoutState>;
}
export type ApplicationStates = Record<string, ApplicationState>;
export interface WindowGeometry {
    x: number;
    y: number;
    width: number;
    height: number;
}
export interface PendingRestore {
    identity: string;
    layoutKey: string;
    monitor: number;
    geometry: WindowGeometry | null;
    monitorFrame: WindowGeometry;
    config: RestoreFlags;
    state: LayoutState;
}
export interface WindowHandle {
    visitedLayouts: Set<string>;
    timeoutId: number;
    restoreTimeoutId: number;
    restoreIdleId: number;
    pendingRestore: PendingRestore | null;
    isRestoreApplied: boolean;
    actors: Meta.WindowActor[];
}
export type CaptureStatus = 'saved' | 'no-rule' | 'no-window' | 'save-failed';
export interface CaptureRequest {
    wm_class: string;
    match_mode?: MatchMode;
    status?: CaptureStatus;
}
export type RuleState = 'class' | 'name' | 'excluded-class' | 'excluded-title' | 'unmanaged';
