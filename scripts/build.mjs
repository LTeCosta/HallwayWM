import {execFileSync} from 'node:child_process';
import {cpSync, mkdirSync, rmSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {join} from 'node:path';

const root = fileURLToPath(new URL('../', import.meta.url));
const destination = join(root, 'dist');
rmSync(destination, {recursive: true, force: true});
execFileSync(process.execPath, [join(root, 'node_modules/typescript/bin/tsc'), '-p', join(root, 'tsconfig.json')], {stdio: 'inherit'});
mkdirSync(destination, {recursive: true});
for (const file of ['metadata.json', 'icons/hallwaywm-symbolic.png', 'icons/globe-symbolic.svg', 'schemas/org.gnome.shell.extensions.deja-window.gschema.xml']) {
    cpSync(join(root, 'src', file), join(destination, file), {recursive: true});
}
for (const file of ['LICENSE', 'CREDITS.md']) cpSync(join(root, file), join(destination, file));
execFileSync('glib-compile-schemas', ['--strict', join(destination, 'schemas')], {stdio: 'inherit'});
