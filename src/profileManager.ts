import GLib from 'gi://GLib';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import type HallwayWMExtension from './extension.js';
import type {ApplicationStates, LayoutState} from './types.js';
import {canLinkProfile, copyProfileStates, defaultMonitorMapping, deviceIdentity, displayProfileKey,
    legacyProfile, resolveProfileState, validateMapping} from './displayProfiles.js';
import type {DisplayProfile, ProfileCatalog, ProfileMonitor, ProfileRequest} from './displayProfiles.js';

/** Read native device identities without changing Mutter's display configuration. */
export function currentDisplayProfile(): DisplayProfile | null {
    const manager = global.backend.get_monitor_manager();
    const logical = manager.get_logical_monitors() ?? [];
    if (logical.length !== Main.layoutManager.monitors.length || logical.length === 0) return null;
    const physical = logical.flatMap(monitor => monitor.get_monitors());
    const identity = (monitor: (typeof physical)[number]) => deviceIdentity(
        monitor.get_vendor(), monitor.get_product(), monitor.get_serial(), monitor.get_connector(), monitor.is_builtin());
    const identities = physical.map(identity);
    const monitors: ProfileMonitor[] = [];
    for (const screen of Main.layoutManager.monitors) {
        const group = logical.find(monitor => monitor.get_number() === screen.index)?.get_monitors();
        if (!group?.length) return null;
        const ids = group.map(monitor => {
            const id = identity(monitor);
            return identities.filter(value => value === id).length > 1 ? `${id}:${monitor.get_connector()}` : id;
        }).sort();
        const rect = global.display.get_monitor_geometry(screen.index);
        if (rect.x !== screen.x || rect.y !== screen.y || rect.width !== screen.width || rect.height !== screen.height) return null;
        const area = global.workspace_manager.get_active_workspace().get_work_area_for_monitor(screen.index);
        monitors.push({
            id: JSON.stringify(ids), name: group.map(monitor => monitor.get_display_name()).join(' / '),
            index: screen.index, builtin: group.every(monitor => monitor.is_builtin()),
            primary: screen.index === Main.layoutManager.primaryIndex,
            scale: global.display.get_monitor_scale(screen.index),
            geometry: {x: rect.x, y: rect.y, width: rect.width, height: rect.height},
            workArea: {x: area.x, y: area.y, width: area.width, height: area.height}
        });
    }
    return {name: monitors.map(monitor => monitor.builtin ? 'Notebook' : monitor.name).join(' + '), monitors};
}

export class DisplayProfiles {
    catalog: ProfileCatalog;

    constructor(private readonly extension: HallwayWMExtension) {
        this.catalog = this.readCatalog();
        this.sync(true);
        extension._settings!.connectObject('changed::profile-request', () => this.handleRequest(), this);
    }

    private readCatalog(): ProfileCatalog {
        try {
            return JSON.parse(this.extension._settings!.get_string('display-profiles')) || {};
        } catch {
            return {};
        }
    }

    private readStates(): ApplicationStates {
        try {
            return JSON.parse(this.extension._settings!.get_string('window-app-states')) || {};
        } catch {
            return {};
        }
    }

    key() {
        const current = currentDisplayProfile();
        return current ? displayProfileKey(current.monitors) : 'display-transition';
    }

    sync(initial = false) {
        const current = currentDisplayProfile();
        if (!current) return;
        const key = displayProfileKey(current.monitors);
        const firstDiscovery = initial && Object.keys(this.catalog).length === 0;
        if (firstDiscovery) {
            for (const application of Object.values(this.readStates())) {
                for (const savedKey of Object.keys(application.layouts ?? {})) {
                    const saved = legacyProfile(savedKey);
                    if (saved) this.catalog[savedKey] = saved;
                }
            }
        }
        this.catalog[key] = {...current, ...this.catalog[key], monitors: current.monitors};
        // Geometry alone can identify the connected setup during this initial
        // adoption only. Unidentified saved layouts remain available as templates.
        const legacyKey = JSON.stringify(Main.layoutManager.monitors.map(monitor =>
            [monitor.x, monitor.y, monitor.width, monitor.height]));
        if (firstDiscovery && this.catalog[legacyKey]) this.catalog[key].legacyKey = legacyKey;
        this.writeCatalog();
        const settings = this.extension._settings!;
        if (settings.get_string('active-display-profile') !== key) settings.set_string('active-display-profile', key);
    }

    private writeCatalog() {
        const settings = this.extension._settings!;
        const value = JSON.stringify(this.catalog);
        if (settings.get_string('display-profiles') !== value) settings.set_string('display-profiles', value);
    }

    canSave() {
        const profile = this.catalog[this.key()];
        return !!profile && !profile.link;
    }

    isLinked() {
        return !!this.catalog[this.key()]?.link;
    }

    getState(states: ApplicationStates, identity: string) {
        return resolveProfileState(states, identity, this.key(), this.catalog);
    }

    monitorId(index: number) {
        return this.catalog[this.key()]?.monitors.find(monitor => monitor.index === index)?.id;
    }

    remapMonitor(state: LayoutState): LayoutState {
        const monitor = this.catalog[this.key()]?.monitors.find(candidate => candidate.id === state.monitorId);
        return monitor ? {...state, monitor: monitor.index} : state;
    }

    private handleRequest() {
        const settings = this.extension._settings;
        if (!settings) return;
        let request: ProfileRequest;
        try {
            request = JSON.parse(settings.get_string('profile-request'));
        } catch {
            return;
        }
        if (!request?.id || request.status) return;
        let message = '';
        let status: 'ok' | 'error' = 'ok';
        try {
            this.sync();
            const target = this.catalog[request.target];
            if (!target) throw new Error('The selected profile is no longer available.');
            if (request.action === 'rename') {
                const name = request.name?.trim().slice(0, 80);
                if (!name) throw new Error('Enter a profile name.');
                target.name = name;
                this.writeCatalog();
                message = 'Profile renamed.';
            } else {
                if (request.target !== this.key()) throw new Error('The connected screens changed. Select the current profile again.');
                if (this.extension._sessionLocked || GLib.get_monotonic_time() < this.extension._layoutSaveAfter)
                    throw new Error('The display layout is settling. Try again in a moment.');
                if (request.action === 'copy' || request.action === 'link') {
                    const sourceKey = request.source ?? '';
                    const source = this.catalog[sourceKey];
                    if (!source || sourceKey === request.target) throw new Error('Select another saved profile.');
                    const mapping = request.mapping ?? defaultMonitorMapping(source, target);
                    if (!validateMapping(source, target, mapping)) throw new Error('Choose a destination for every source screen.');
                    if (request.action === 'link') {
                        if (!canLinkProfile(this.catalog, sourceKey, request.target)) throw new Error('This link would create a profile cycle.');
                        target.link = {source: sourceKey, mapping};
                        message = 'Profile linked. Saved positions follow the source; make it independent before saving local changes.';
                    } else {
                        const states = copyProfileStates(this.readStates(), sourceKey, request.target, this.catalog, mapping);
                        settings.set_string('window-app-states', JSON.stringify(states));
                        delete target.link;
                        message = 'Layout copied. This profile can now be edited independently.';
                    }
                    delete target.legacyKey;
                    this.writeCatalog();
                    this.extension._restoreCurrentProfile();
                } else if (request.action === 'unlink') {
                    const mapping = defaultMonitorMapping(target, target);
                    const states = copyProfileStates(this.readStates(), request.target, request.target, this.catalog, mapping);
                    settings.set_string('window-app-states', JSON.stringify(states));
                    delete target.link;
                    delete target.legacyKey;
                    this.writeCatalog();
                    message = 'Profile is independent. Its current saved layout is preserved.';
                } else if (request.action === 'save') {
                    if (!this.canSave()) throw new Error('Make this profile independent before saving local positions.');
                    if (!this.extension._functionalityEnabled) throw new Error('Enable HallwayWM before saving window positions.');
                    const count = this.extension._saveCurrentProfile();
                    message = `Saved positions for ${count} application${count === 1 ? '' : 's'}.`;
                } else if (request.action === 'apply') {
                    if (!this.extension._functionalityEnabled) throw new Error('Enable HallwayWM before restoring window positions.');
                    const count = this.extension._restoreCurrentProfile();
                    message = `Restoring ${count} application${count === 1 ? '' : 's'} in this profile.`;
                } else {
                    throw new Error('Unknown profile action.');
                }
            }
        } catch (error) {
            status = 'error';
            message = error instanceof Error ? error.message : 'The profile could not be updated.';
        }
        settings.set_string('profile-request', JSON.stringify({id: request.id, status, message}));
    }

    destroy() {
        this.extension._settings?.disconnectObject(this);
    }
}
