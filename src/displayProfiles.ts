import type {ApplicationStates, LayoutState, WindowGeometry} from './types.js';

export interface ProfileMonitor {
    id: string;
    name: string;
    index: number;
    builtin: boolean;
    primary: boolean;
    scale: number;
    geometry: WindowGeometry;
    workArea: WindowGeometry;
}
export interface DisplayProfile {
    name: string;
    monitors: ProfileMonitor[];
    legacy?: boolean;
    legacyKey?: string;
    link?: {source: string; mapping: Record<string, string>};
}
export type ProfileCatalog = Record<string, DisplayProfile>;
export interface ProfileRequest {
    id: string;
    action: 'rename' | 'copy' | 'link' | 'unlink' | 'save' | 'save-and-lock' | 'apply';
    target: string;
    source?: string;
    name?: string;
    mapping?: Record<string, string>;
    status?: 'ok' | 'error';
    message?: string;
}

export function deviceIdentity(vendor: string, product: string, serial: string, connector: string, builtin: boolean) {
    const usefulSerial = serial.trim() && !/^(unknown|0x0+|0+|none)$/i.test(serial.trim());
    return JSON.stringify([builtin, vendor, product, usefulSerial ? serial : `connector:${connector}`]);
}

/** Device order and connector changes do not rename a uniquely identified setup. */
export function displayProfileKey(monitors: ProfileMonitor[]) {
    return 'display-v1:' + JSON.stringify(monitors.map(monitor => [
        monitor.id, monitor.geometry.x, monitor.geometry.y,
        monitor.geometry.width, monitor.geometry.height, monitor.scale, monitor.primary
    ]).sort((a, b) => JSON.stringify(a).localeCompare(JSON.stringify(b))));
}

export function legacyProfile(key: string): DisplayProfile | null {
    try {
        const rectangles: unknown = JSON.parse(key);
        if (!Array.isArray(rectangles) || rectangles.length === 0 || !rectangles.every(rect =>
            Array.isArray(rect) && rect.length === 4 && rect.every(Number.isFinite) && rect[2] > 0 && rect[3] > 0)) return null;
        const monitors = rectangles.map((rect, index) => {
            const [x, y, width, height] = rect as number[];
            const geometry = {x, y, width, height};
            return {id: `saved-screen-${index}`, name: `Screen ${index + 1}`, index,
                builtin: false, primary: index === 0, scale: 1, geometry, workArea: geometry};
        });
        return {name: `Saved layout (${monitors.length} screen${monitors.length === 1 ? '' : 's'})`, monitors, legacy: true};
    } catch {
        return null;
    }
}

export function defaultMonitorMapping(source: DisplayProfile, target: DisplayProfile) {
    const mapping: Record<string, string> = {};
    const used = new Set<string>();
    for (const monitor of source.monitors) {
        const candidates = target.monitors.filter(candidate => !used.has(candidate.id));
        const match = target.monitors.find(candidate => candidate.id === monitor.id) ??
            candidates.find(candidate => candidate.builtin && monitor.builtin) ??
            candidates.find(candidate => candidate.primary === monitor.primary && candidate.builtin === monitor.builtin) ??
            candidates.find(candidate => candidate.builtin === monitor.builtin) ?? candidates[0] ??
            target.monitors.find(candidate => candidate.primary) ?? target.monitors[0];
        if (!match) throw new Error('The destination has no active screens.');
        mapping[monitor.id] = match.id;
        used.add(match.id);
    }
    return mapping;
}

export function validateMapping(source: DisplayProfile, target: DisplayProfile, mapping: Record<string, string>) {
    return source.monitors.every(monitor => target.monitors.some(candidate => candidate.id === mapping[monitor.id]));
}

export function canLinkProfile(catalog: ProfileCatalog, source: string, target: string) {
    const visited = new Set([target]);
    let current: string | undefined = source;
    while (current) {
        if (visited.has(current) || !catalog[current]) return false;
        visited.add(current);
        current = catalog[current].link?.source;
    }
    return true;
}

/** Adapt size and relative position to the selected destination screen's usable area. */
export function projectState(state: LayoutState, source: DisplayProfile, target: DisplayProfile, mapping: Record<string, string>): LayoutState | undefined {
    const from = source.monitors.find(monitor => monitor.id === state.monitorId) ??
        source.monitors.find(monitor => monitor.index === state.monitor) ?? source.monitors.find(monitor => monitor.primary);
    const to = from && target.monitors.find(monitor => monitor.id === mapping[from.id]);
    if (!from || !to) return undefined;
    const result = {...state, monitor: to.index, monitorId: to.id};
    const old = from.workArea;
    const area = to.workArea;
    for (const [position, size, origin, extent] of [
        ['x', 'width', 'x', 'width'], ['y', 'height', 'y', 'height']
    ] as const) {
        if (state[size] !== undefined) {
            result[size] = Math.round(Math.max(Math.min(100, area[extent]),
                Math.min(area[extent], state[size]! / old[extent] * area[extent])));
        }
        if (state[position] !== undefined) {
            const oldTravel = Math.max(0, old[extent] - (state[size] ?? 0));
            const fraction = oldTravel > 0 ? (state[position]! - old[origin]) / oldTravel : 0;
            const newTravel = Math.max(0, area[extent] - (result[size] ?? 0));
            result[position] = Math.round(area[origin] + Math.max(0, Math.min(1, fraction)) * newTravel);
        }
    }
    return result;
}

export function resolveProfileState(states: ApplicationStates, identity: string, key: string, catalog: ProfileCatalog, visited = new Set<string>()): LayoutState | undefined {
    const profile = catalog[key];
    if (!profile || visited.has(key)) return undefined;
    visited.add(key);
    if (profile.link) {
        const source = catalog[profile.link.source];
        const state = source && resolveProfileState(states, identity, profile.link.source, catalog, visited);
        return state && projectState(state, source, profile, profile.link.mapping);
    }
    const layouts = states[identity]?.layouts;
    const state = layouts?.[key] ?? (profile.legacyKey ? layouts?.[profile.legacyKey] : undefined);
    if (!state) return undefined;
    const monitor = profile.monitors.find(candidate => candidate.id === state.monitorId) ??
        profile.monitors.find(candidate => candidate.index === state.monitor);
    return monitor ? {...state, monitor: monitor.index, monitorId: monitor.id} : {...state};
}

/** Replace only the destination's positions; every other profile remains intact. */
export function copyProfileStates(states: ApplicationStates, sourceKey: string, targetKey: string, catalog: ProfileCatalog, mapping: Record<string, string>) {
    const source = catalog[sourceKey];
    const target = catalog[targetKey];
    if (!source || !target || !validateMapping(source, target, mapping))
        throw new Error('Choose a destination for every source screen.');
    const result: ApplicationStates = {};
    for (const [identity, application] of Object.entries(states)) {
        const layouts = {...application.layouts};
        delete layouts[targetKey];
        const original = resolveProfileState(states, identity, sourceKey, catalog);
        const copied = original && projectState(original, source, target, mapping);
        if (copied) layouts[targetKey] = copied;
        result[identity] = {...application, ...copied, layouts};
    }
    return result;
}
