import Adw from 'gi://Adw';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Gtk from 'gi://Gtk';
import {defaultMonitorMapping} from './displayProfiles.js';
import type {DisplayProfile, ProfileCatalog, ProfileRequest} from './displayProfiles.js';

export class DisplayProfilesPage {
    readonly page = new Adw.PreferencesPage({title: 'Display Profiles', icon_name: 'video-display-symbolic'});
    private groups: Adw.PreferencesGroup[] = [];
    private signalIds: number[] = [];
    private refreshId = 0;
    private timeoutId = 0;
    private pendingId = '';
    private sourceKey = '';
    private reuseMode = 0;
    private closed = false;

    constructor(private readonly settings: Gio.Settings, private readonly window: Adw.PreferencesWindow) {
        this.signalIds = ['display-profiles', 'active-display-profile'].map(key =>
            settings.connect(`changed::${key}`, () => this.queueRefresh()));
        this.signalIds.push(settings.connect('changed::profile-request', () => this.receive()));
        window.connect('close-request', () => {
            this.destroy();
            return false;
        });
        this.refresh();
    }

    private catalog(): ProfileCatalog {
        try {
            return JSON.parse(this.settings.get_string('display-profiles')) || {};
        } catch {
            return {};
        }
    }

    private group(title: string, description = '') {
        const group = new Adw.PreferencesGroup({title, description});
        this.page.add(group);
        this.groups.push(group);
        return group;
    }

    private queueRefresh() {
        if (this.refreshId || this.closed) return;
        this.refreshId = GLib.idle_add(GLib.PRIORITY_DEFAULT, () => {
            this.refreshId = 0;
            this.refresh();
            return GLib.SOURCE_REMOVE;
        });
    }

    private send(request: Omit<ProfileRequest, 'id'>) {
        if (this.pendingId) return;
        this.pendingId = GLib.uuid_string_random();
        this.timeoutId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 4000, () => {
            this.timeoutId = 0;
            this.pendingId = '';
            this.window.add_toast(new Adw.Toast({title: 'HallwayWM did not respond. Check that it is enabled.'}));
            return GLib.SOURCE_REMOVE;
        });
        this.settings.set_string('profile-request', JSON.stringify({...request, id: this.pendingId}));
    }

    private receive() {
        let response: ProfileRequest;
        try {
            response = JSON.parse(this.settings.get_string('profile-request'));
        } catch {
            return;
        }
        if (!response?.status || response.id !== this.pendingId) return;
        if (this.timeoutId) GLib.source_remove(this.timeoutId);
        this.timeoutId = 0;
        this.pendingId = '';
        this.window.add_toast(new Adw.Toast({title: response.message ?? 'Profile updated.'}));
        this.queueRefresh();
    }

    private screenDescription(profile: DisplayProfile) {
        return profile.monitors.map(monitor =>
            `${monitor.name}${monitor.primary ? ' (primary)' : ''}: ${monitor.geometry.width} × ${monitor.geometry.height}`
        ).join('\n');
    }

    private renameRow(key: string, profile: DisplayProfile) {
        const row = new Adw.EntryRow({title: 'Profile name', text: profile.name, show_apply_button: true});
        row.connect('apply', () => this.send({action: 'rename', target: key, name: row.text}));
        return row;
    }

    private refresh() {
        if (this.closed) return;
        for (const group of this.groups) this.page.remove(group);
        this.groups = [];
        const catalog = this.catalog();
        const activeKey = this.settings.get_string('active-display-profile');
        const active = catalog[activeKey];
        const current = this.group('Connected Setup',
            'Profiles are selected automatically from the connected screens, their positions and the primary display.');
        if (!active) {
            current.add(new Adw.ActionRow({title: 'No active display profile',
                subtitle: 'Enable the current HallwayWM build to detect the connected screens.'}));
            return;
        }
        current.add(this.renameRow(activeKey, active));
        current.add(new Adw.ActionRow({title: 'Screens', subtitle: this.screenDescription(active), use_markup: false}));
        const status = new Adw.ActionRow({
            title: active.link ? `Linked to ${catalog[active.link.source]?.name ?? 'unavailable profile'}` : 'Independent profile',
            subtitle: active.link ? 'Saved positions follow the source. Make this profile independent before saving local changes.' :
                'Saving a window position updates only this screen setup.',
            use_markup: false
        });
        if (active.link) {
            const independent = new Gtk.Button({label: 'Make Independent', valign: Gtk.Align.CENTER});
            independent.connect('clicked', () => this.send({action: 'unlink', target: activeKey}));
            status.add_suffix(independent);
        }
        current.add(status);
        const actions = new Adw.ActionRow({title: 'Application Positions',
            subtitle: 'Save the main windows of managed applications, or restore this profile now.'});
        const save = new Gtk.Button({label: 'Save Positions', valign: Gtk.Align.CENTER, sensitive: !active.link});
        save.connect('clicked', () => this.send({action: 'save', target: activeKey}));
        const apply = new Gtk.Button({label: 'Restore', valign: Gtk.Align.CENTER});
        apply.connect('clicked', () => this.send({action: 'apply', target: activeKey}));
        actions.add_suffix(save);
        actions.add_suffix(apply);
        current.add(actions);

        // Geometry-only records already adopted by a device profile need no duplicate row.
        const visible = Object.entries(catalog).filter(([key, profile]) =>
            !profile.legacy || !Object.values(catalog).some(candidate => candidate.legacyKey === key));
        const sources = visible.filter(([key]) => key !== activeKey);
        const reuse = this.group('Reuse a Saved Layout',
            'Copy a layout to edit it separately, or link it to follow changes to the source.');
        if (!sources.length) {
            reuse.add(new Adw.ActionRow({title: 'No other layouts yet',
                subtitle: 'Connect another screen setup and save its positions to make it available here.'}));
        } else {
            let selected = sources.findIndex(([key]) => key === this.sourceKey);
            if (selected < 0) selected = 0;
            this.sourceKey = sources[selected][0];
            const sourceRow = new Adw.ComboRow({title: 'Source profile',
                model: Gtk.StringList.new(sources.map(([, profile]) => profile.name)), selected});
            sourceRow.connect('notify::selected', () => {
                const source = sources[sourceRow.selected];
                if (source && this.sourceKey !== source[0]) {
                    this.sourceKey = source[0];
                    this.queueRefresh();
                }
            });
            reuse.add(sourceRow);
            const mode = new Adw.ComboRow({title: 'Reuse mode',
                model: Gtk.StringList.new(['Independent copy', 'Linked to source']), selected: this.reuseMode});
            mode.connect('notify::selected', () => { this.reuseMode = mode.selected; });
            reuse.add(mode);
            const source = catalog[this.sourceKey];
            const mapping = defaultMonitorMapping(source, active);
            const targets = active.monitors;
            for (const monitor of source.monitors) {
                const targetIndex = targets.findIndex(target => target.id === mapping[monitor.id]);
                const row = new Adw.ComboRow({title: `Source: ${monitor.name}`, use_markup: false,
                    subtitle: 'Destination screen',
                    model: Gtk.StringList.new(targets.map(target => `${target.name}${target.primary ? ' (primary)' : ''}`)),
                    selected: Math.max(0, targetIndex)});
                row.connect('notify::selected', () => {
                    if (targets[row.selected]) mapping[monitor.id] = targets[row.selected].id;
                });
                reuse.add(row);
            }
            const replace = new Adw.ActionRow({title: 'Apply to Connected Setup',
                subtitle: 'Replaces this profile’s saved positions. Sizes and positions adapt to the selected destination screens.'});
            const use = new Gtk.Button({label: 'Use Layout…', valign: Gtk.Align.CENTER});
            use.connect('clicked', () => {
                const linked = this.reuseMode === 1;
                const sourceKey = this.sourceKey;
                const dialog = new Adw.MessageDialog({transient_for: this.window, modal: true,
                    heading: linked ? 'Link this display profile?' : 'Copy this layout?',
                    body: `${source.name} → ${active.name}\n\n` + (linked ?
                        'The connected profile will follow the source’s saved positions. Make it independent to save local changes.' :
                        'The connected profile’s saved positions will be replaced by an independent copy.' )});
                dialog.add_response('cancel', 'Cancel');
                dialog.add_response('apply', linked ? 'Link and Restore' : 'Copy and Restore');
                dialog.set_response_appearance('apply', Adw.ResponseAppearance.SUGGESTED);
                dialog.connect('response', (_dialog: Adw.MessageDialog, response: string) => {
                    if (response === 'apply') this.send({action: linked ? 'link' : 'copy',
                        target: activeKey, source: sourceKey, mapping: {...mapping}});
                });
                dialog.present();
            });
            replace.add_suffix(use);
            reuse.add(replace);
        }
        const saved = this.group('Saved Profiles', 'Connect a matching setup to select its profile automatically.');
        for (const [key, profile] of visible.filter(([key]) => key !== activeKey)) {
            const row = new Adw.ExpanderRow({title: profile.name, use_markup: false,
                subtitle: profile.link ? `Linked to ${catalog[profile.link.source]?.name ?? 'unavailable profile'}` :
                    `${profile.monitors.length} screen${profile.monitors.length === 1 ? '' : 's'}`});
            row.add_row(this.renameRow(key, profile));
            row.add_row(new Adw.ActionRow({title: 'Screens', subtitle: this.screenDescription(profile), use_markup: false}));
            saved.add(row);
        }
    }

    private destroy() {
        this.closed = true;
        for (const id of this.signalIds) this.settings.disconnect(id);
        this.signalIds = [];
        if (this.refreshId) GLib.source_remove(this.refreshId);
        if (this.timeoutId) GLib.source_remove(this.timeoutId);
        this.refreshId = this.timeoutId = 0;
    }
}
