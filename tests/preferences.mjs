import Adw from 'gi://Adw';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Gtk from 'gi://Gtk';

if (GLib.getenv('GSETTINGS_BACKEND') !== 'memory')
    throw new Error('Run with GSETTINGS_BACKEND=memory to isolate test preferences');
const resource = Gio.Resource.load('/usr/share/gnome-shell/org.gnome.Shell.Extensions.src.gresource');
Gio.resources_register(resource);
const directory = Gio.File.new_for_path(ARGV[0] ?? GLib.build_filenamev([GLib.get_current_dir(), 'dist']));
const [, data] = directory.get_child('metadata.json').load_contents(null);
const metadata = JSON.parse(new TextDecoder().decode(data));
const {default: Preferences} = await import(directory.get_child('prefs.js').get_uri());
Adw.init();
const preferences = new Preferences({...metadata, dir: directory, path: directory.get_path()});
const settings = preferences.getSettings();
settings.set_value('known-wm-classes', new GLib.Variant('as', ['org.workstation.PreferenceTest']));
settings.set_value('known-window-titles', new GLib.Variant('as', ['Disposable title']));
settings.set_string('window-app-configs', JSON.stringify([
    {wm_class: 'org.workstation.PreferenceTest', enabled: true, locked: true, restore_size: true},
    {wm_class: 'Disposable title', match_mode: 'title', enabled: false, restore_workspace: true},
]));
settings.set_string('window-global-defaults', JSON.stringify({enabled: true, restore_pos: true,
    excluded_apps: [{wm_class: 'org.workstation.Excluded', match_mode: 'wm_class'}]}));
const screen = (id, name, primary) => ({id, name, primary, builtin: false, index: 0,
    scale: 1, geometry: {x: 0, y: 0, width: 1920, height: 1080},
    workArea: {x: 0, y: 32, width: 1920, height: 1048}});
settings.set_string('display-profiles', JSON.stringify({
    home: {name: 'Home', monitors: [screen('home-screen', 'Home screen', true)]},
    office: {name: 'Office', monitors: [screen('office-screen', 'Office screen', true)]}
}));
settings.set_string('active-display-profile', 'home');
const preserved = ['window-app-configs', 'window-global-defaults', 'window-app-states', 'display-profiles'];
const before = preserved.map(key => settings.get_string(key));
const window = new Adw.PreferencesWindow();
await preferences.fillPreferencesWindow(window);
const pages=[];
function inspect(widget) {
    if (widget instanceof Adw.PreferencesPage) pages.push(widget.title);
    for (let child=widget.get_first_child(); child; child=child.get_next_sibling()) inspect(child);
}
inspect(window);
for (const title of ['Applications', 'Global Defaults', 'Display Profiles', 'Settings'])
    if (!pages.includes(title)) throw new Error('Missing preferences page: '+title);
if (preserved.some((key, index) => settings.get_string(key) !== before[index]))
    throw new Error('Constructing preferences changed the fixture rules or profiles');
function button(label) {
    const found = [];
    function visit(widget) {
        if (widget instanceof Gtk.Button && widget.label === label) found.push(widget);
        for (let child = widget.get_first_child(); child; child = child.get_next_sibling()) visit(child);
    }
    visit(window);
    if (found.length !== 1) throw new Error('Expected one button: ' + label);
    return found[0];
}
for (const [label, action] of [['Save Positions', 'save'], ['Save & Lock', 'save-and-lock']]) {
    if (!button(label).sensitive) throw new Error('Independent profile cannot save: ' + label);
    button(label).emit('clicked');
    const request = JSON.parse(settings.get_string('profile-request'));
    if (request.action !== action || request.target !== 'home' || !request.id)
        throw new Error('Incorrect profile action: ' + JSON.stringify(request));
    settings.set_string('profile-request', JSON.stringify({id: request.id, status: 'ok', message: 'Test saved.'}));
}
if (preserved.some((key, index) => settings.get_string(key) !== before[index]))
    throw new Error('Profile controls changed rules before a runtime response');
const catalog = JSON.parse(settings.get_string('display-profiles'));
catalog.home.link = {source: 'office', mapping: {'office-screen': 'home-screen'}};
settings.set_string('display-profiles', JSON.stringify(catalog));
const context = GLib.MainContext.default();
while (context.pending()) context.iteration(false);
for (const label of ['Save Positions', 'Save & Lock'])
    if (button(label).sensitive) throw new Error('Linked profile permits local saves: ' + label);
if (!button('Restore').sensitive) throw new Error('Linked profile cannot restore');
window.close();
print('Preferences smoke test passed: four pages, both save requests, linked-profile guards and unchanged rules');
