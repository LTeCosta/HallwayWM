import assert from 'node:assert/strict';
import {canLinkProfile, copyProfileStates, defaultMonitorMapping, deviceIdentity, displayProfileKey,
    legacyProfile, projectState, resolveProfileState} from '../dist/displayProfiles.js';

const screen = (id, index, primary, geometry, builtin = false) => ({
    id, name: id, index, primary, builtin, scale: 1, geometry, workArea: geometry
});
const notebook = screen('panel', 0, false, {x: 0, y: 0, width: 1600, height: 1000}, true);
const home = screen('home-monitor', 1, true, {x: 1600, y: 0, width: 2000, height: 1200});
const office = {...home, id: 'office-monitor'};
const a = {name: 'Home', monitors: [notebook, home]};
const b = {name: 'Office', monitors: [notebook, office]};
assert.notEqual(displayProfileKey(a.monitors), displayProfileKey(b.monitors));
assert.equal(displayProfileKey(a.monitors), displayProfileKey([
    {...home, index: 0}, {...notebook, index: 1}
]));
assert.notEqual(displayProfileKey(a.monitors), displayProfileKey(a.monitors.map(m => ({...m, primary: !m.primary}))));
assert.notEqual(displayProfileKey(a.monitors), displayProfileKey([notebook, {...home, geometry: {...home.geometry, x: -2000}}]));
assert.equal(deviceIdentity('LG', 'display', '123', 'DP-1', false), deviceIdentity('LG', 'display', '123', 'DP-4', false));
assert.notEqual(deviceIdentity('LG', 'display', '', 'DP-1', false), deviceIdentity('LG', 'display', '', 'DP-4', false));
assert.deepEqual(defaultMonitorMapping(a, b), {'panel': 'panel', 'home-monitor': 'office-monitor'});

const source = {name: 'Source', monitors: [screen('source', 0, true, {x: 0, y: 30, width: 2000, height: 1000})]};
const target = {name: 'Target', monitors: [screen('target', 1, true, {x: 100, y: 40, width: 1000, height: 500})]};
const position = {x: 500, y: 280, width: 1000, height: 500, monitor: 0,
    monitorId: 'source', workspace: 2, maximized: false, minimized: false};
const transformed = projectState(position, source, target, {'source': 'target'});
assert.deepEqual(transformed, {...position, x: 350, y: 165, width: 500, height: 250,
    monitor: 1, monitorId: 'target'});
const beyond = projectState({...position, x: -900, y: 9000, width: 9000}, source, target, {'source': 'target'});
assert.equal(beyond.width, 1000);
assert.equal(beyond.x, 100);
assert.equal(beyond.y + beyond.height, 540);

const catalog = {source, target, unrelated: {...source, name: 'Unrelated'}};
const states = {app: {layouts: {source: position, unrelated: {...position, x: 33}, target: {...position, x: 99}}},
    other: {layouts: {target: position}}};
const before = JSON.stringify(states);
const copied = copyProfileStates(states, 'source', 'target', catalog, {'source': 'target'});
assert.equal(JSON.stringify(states), before);
assert.deepEqual(copied.app.layouts.source, position);
assert.deepEqual(copied.app.layouts.unrelated, states.app.layouts.unrelated);
assert.deepEqual(copied.app.layouts.target, transformed);
assert.equal(copied.other.layouts.target, undefined);
states.app.layouts.source = {...position, x: 100};
assert.equal(copied.app.layouts.target.x, 350, 'An independent copy must not follow later source changes');

catalog.target.link = {source: 'source', mapping: {'source': 'target'}};
assert.equal(resolveProfileState(states, 'app', 'target', catalog).x, 150);
states.app.layouts.source.x = 600;
assert.equal(resolveProfileState(states, 'app', 'target', catalog).x, 400);
assert.equal(canLinkProfile(catalog, 'target', 'source'), false, 'Reject an indirect cycle');
assert.equal(canLinkProfile(catalog, 'source', 'target'), true);
const independent = copyProfileStates(states, 'target', 'target', catalog, {'target': 'target'});
delete catalog.target.link;
assert.equal(resolveProfileState(independent, 'app', 'target', catalog).x, 400);
states.app.layouts.source.x = 800;
assert.equal(resolveProfileState(independent, 'app', 'target', catalog).x, 400);
catalog.target.monitors[0].index = 7;
assert.equal(resolveProfileState(independent, 'app', 'target', catalog).monitor, 7, 'Resolve stable monitor identities after reordering');
catalog.target.link = {source: 'source', mapping: {'source': 'target'}};
catalog.source.link = {source: 'target', mapping: {'target': 'source'}};
assert.equal(resolveProfileState(states, 'app', 'target', catalog), undefined, 'Malformed cycles cannot recurse forever');

const legacyKey = '[[0,0,1920,1080]]';
const legacy = legacyProfile(legacyKey);
assert.equal(legacy.monitors.length, 1);
assert.equal(legacyProfile('invalid'), null);
assert.equal(legacyProfile('[[0,0,0,1080]]'), null);
const adopted = {...legacy, name: 'Connected setup', legacy: false, legacyKey};
assert.equal(resolveProfileState({app: {layouts: {[legacyKey]: {...position, x: 87}}}},
    'app', 'connected', {[legacyKey]: legacy, connected: adopted}).x, 87);
console.log('PASS: device/layout identity, port stability, monitor mapping, proportional copies, independent edits, live links, detachment, cycle rejection and legacy profile preservation.');
