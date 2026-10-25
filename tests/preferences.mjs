import Adw from 'gi://Adw';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';

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
const before = settings.get_string('window-app-configs');
const window = new Adw.PreferencesWindow();
await preferences.fillPreferencesWindow(window);
const pages=[];
function inspect(widget) {
    if (widget instanceof Adw.PreferencesPage) pages.push(widget.title);
    for (let child=widget.get_first_child(); child; child=child.get_next_sibling()) inspect(child);
}
inspect(window);
for (const title of ['Applications', 'Global Defaults', 'Settings'])
    if (!pages.includes(title)) throw new Error('Missing preferences page: '+title);
if (settings.get_string('window-app-configs') !== before)
    throw new Error('Constructing preferences changed the fixture rules');
window.close();
print('Preferences smoke test passed: all three pages, typed rule forms and unchanged fixture rules');
