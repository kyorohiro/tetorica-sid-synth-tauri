const test = require('node:test'), assert = require('node:assert/strict');
const fs = require('node:fs'), vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../desktop/desktop-interface.js'), 'utf8');
function boot(url, subframe = false, fail = false, confirmed = false, saveResult = '/tmp/sid-voice.json') {
  const calls = [], status = {textContent: ''}, listeners = {}, button = {disabled: false, addEventListener: (type, fn) => {listeners[type] = fn;}};
  let receiveExport;
  const exportCall = new Promise(resolve => {receiveExport = resolve;});
  class Anchor {click() {calls.push('browser-click');}}
  let serial = 0;
  const URLMock = {createObjectURL: () => `blob:${++serial}`, revokeObjectURL() {}};
  const window = {addEventListener() {}, __TAURI_INTERNALS__: {invoke: async (command, args) => {
    const call = {command, args}; calls.push(call);
    if (command === 'save_export_binary') receiveExport(call);
    if (fail) throw new Error('write failed');
    return command === 'save_export_binary' ? saveResult : false;
  }}};
  window.top = subframe ? {} : window;
  vm.runInNewContext(source, {window, location: new URL(url), URL: URLMock, HTMLAnchorElement: Anchor, Map, Uint8Array, Array, DataView, TextEncoder,
    document: {readyState: 'complete', getElementById: id => id === 'audioStatus' ? status : null,
      querySelector: selector => selector === '[data-reset-offline-cache]' ? button : null,
      createElement: () => ({style: {}, children: [], listeners: {},
        addEventListener(type, fn) {this.listeners[type] = fn;}, append(...items) {this.children.push(...items);},
        close(value) {this.returnValue = value; this.listeners.close();}, remove() {}, showModal() {}, focus() {}}),
      body: {append(dialog) {setImmediate(() => dialog.children[confirmed ? 2 : 1].listeners.click());}}}});
  return {calls, status, listeners, button, Anchor, URL: URLMock, exportCall};
}
test('local Synth exports original bytes even after immediate URL revocation', async () => {
  for (const url of ['tauri://localhost/index.html', 'http://tauri.localhost/index.html', 'https://tauri.localhost/index.html']) {
    const ui = boot(url), link = new ui.Anchor();
    link.href = ui.URL.createObjectURL(new Blob([new Uint8Array([1, 2, 255])])); link.download = 'sid-voice.json';
    link.click(); ui.URL.revokeObjectURL(link.href);
    await new Promise(resolve => setImmediate(resolve));
    const packet = exportPacket(ui.calls[0]);
    assert.deepEqual(Array.from(packet.bytes), [1, 2, 255]);
    assert.equal(packet.header.filename, 'sid-voice.json'); assert.match(ui.status.textContent, /Saved/);
  }
});
function exportPacket(call) {
  assert.equal(call.command, 'save_export_binary');
  assert.ok(call.args instanceof ArrayBuffer, 'Native IPC receives raw bytes, never a numeric JSON array');
  const headerLength = new DataView(call.args).getUint32(0, true);
  assert.ok(headerLength > 0 && headerLength <= 4096);
  const header = JSON.parse(new TextDecoder().decode(new Uint8Array(call.args, 4, headerLength)));
  return {header, headerLength, bytes:new Uint8Array(call.args, 4 + headerLength)};
}
test('16 MiB generic export uses one binary packet with only a small JSON header', {timeout:2000}, async () => {
  const original = new Uint8Array(16 * 1024 * 1024);
  for (let i = 0; i < original.length; i++) original[i] = i & 0xff;
  const ui = boot('tauri://localhost/'), link = new ui.Anchor();
  link.href = ui.URL.createObjectURL(new Blob([original])); link.download = '音色🎵.cassette.zip';
  link.click(); ui.URL.revokeObjectURL(link.href);
  const call = await ui.exportCall;
  const packet = exportPacket(call);
  assert.deepEqual(packet.header, {filename:link.download});
  assert.equal(call.args.byteLength, original.byteLength + packet.headerLength + 4);
  assert.ok(packet.headerLength > JSON.stringify(packet.header).length, 'Header length counts UTF-8 bytes');
  assert.equal(Buffer.compare(Buffer.from(packet.bytes), Buffer.from(original)), 0);
  assert.equal(ui.calls.length, 1);
});
test('oversized export rejects before reading the Blob or invoking native code', async () => {
  const ui = boot('tauri://localhost/'), link = new ui.Anchor();
  let reads = 0;
  link.href = ui.URL.createObjectURL({size:128 * 1024 * 1024 + 1, arrayBuffer() {reads++; throw Error('Must not read');}});
  link.download = 'huge.cassette.zip'; link.click();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(reads, 0); assert.deepEqual(ui.calls, []);
  assert.match(ui.status.textContent, /Could not save.*Export exceeds 128 MiB/);
});
test('oversized UTF-8 filename header rejects before reading the Blob', async () => {
  const ui = boot('tauri://localhost/'), link = new ui.Anchor();
  let reads = 0;
  link.href = ui.URL.createObjectURL({size:1, arrayBuffer() {reads++; throw Error('Must not read');}});
  link.download = '界'.repeat(1500); link.click();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(reads, 0); assert.deepEqual(ui.calls, []);
  assert.match(ui.status.textContent, /Could not save.*header exceeds 4096 bytes/);
});
test('cancelled native binary save reports cancellation without browser navigation', async () => {
  const ui = boot('tauri://localhost/', false, false, false, null), link = new ui.Anchor();
  link.href = ui.URL.createObjectURL(new Blob([])); link.download = 'empty.bin'; link.click();
  await ui.exportCall;
  await new Promise(resolve => setImmediate(resolve));
  const packet = exportPacket(ui.calls[0]);
  assert.equal(packet.bytes.byteLength, 0);
  assert.equal(ui.status.textContent, 'Save cancelled.');
  assert.equal(ui.calls.includes('browser-click'), false);
});
test('remote pages and subframes retain browser behavior without native hooks', () => {
  for (const [url, frame] of [['https://example.com/', false], ['http://localhost:8890/', false], ['tauri://other/', false], ['tauri://localhost/', true]]) {
    const ui = boot(url, frame); const link = new ui.Anchor(); link.href = ui.URL.createObjectURL(new Blob(['x'])); link.download = 'x'; link.click();
    assert.deepEqual(ui.calls, ['browser-click']); assert.equal(ui.listeners.click, undefined);
  }
});
test('ordinary links use normal browser navigation and save errors are visible', async () => {
  const ui = boot('tauri://localhost/', false, true), link = new ui.Anchor(); link.href = 'https://example.com'; link.click();
  assert.equal(ui.calls[0], 'browser-click');
  link.href = ui.URL.createObjectURL(new Blob(['x'])); link.download = 'voice.vgi'; link.click();
  await new Promise(resolve => setImmediate(resolve)); assert.match(ui.status.textContent, /Could not save.*write failed/);
});
test('cache button confirms before native reload and cancellation re-enables it', async () => {
  for (const confirmed of [false, true]) {
    const ui = boot('tauri://localhost/', false, false, confirmed);
    await ui.listeners.click({preventDefault() {}, stopImmediatePropagation() {}});
    assert.equal(ui.calls.length, confirmed ? 1 : 0);
    if (confirmed) assert.equal(ui.calls[0].command, 'reload_window');
    assert.equal(ui.button.disabled, false);
  }
});

function bootPin({url = 'tauri://localhost/index.html', subframe = false, loading = false, available = true, initial = false, invoke} = {}) {
  const calls = [], events = {}, domEvents = {}, status = {textContent: ''};
  const button = {
    hidden: true, disabled: false, attributes: {}, listeners: {}, selected: false,
    setAttribute(name, value) {this.attributes[name] = value;},
    addEventListener(type, listener) {(this.listeners[type] ||= []).push(listener);},
    classList: {toggle(name, value) {if (name === 'is-selected') button.selected = value;}},
  };
  class Anchor {click() {}}
  const window = {
    addEventListener(type, listener) {events[type] = listener;},
    __TAURI_INTERNALS__: {invoke: async (command, args) => {
      calls.push({command, args});
      return invoke ? invoke(command, args) : command === 'window_pin_state' ? initial : args.pinned;
    }},
  };
  window.top = subframe ? {} : window;
  let mounted = available;
  vm.runInNewContext(source, {
    window, location: new URL(url), URL: {createObjectURL() {}, revokeObjectURL() {}},
    HTMLAnchorElement: Anchor, Map, Uint8Array, Array,
    document: {
      readyState: loading ? 'loading' : 'complete',
      getElementById: id => id === 'audioStatus' ? status : id === 'synthPinButton' && mounted ? button : null,
      querySelector() {return null;},
      addEventListener(type, listener) {domEvents[type] = listener;},
    },
  });
  return {calls, events, domEvents, status, button, mount() {mounted = true; events['tetorica-synth-ready']?.();}};
}
const settle = () => new Promise(resolve => setImmediate(resolve));

// A small DOM fixture for the toolbar's tree operations. Load the shipped HTML
// so additions to the Web menu are exercised without a browser dependency in
// the native build matrix.
function bootToolbar({legacy = false} = {}) {
  class Element {
    constructor(tag) {
      this.tagName = tag.toLowerCase(); this.children = []; this.parentElement = null;
      this.id = ''; this.className = ''; this.dataset = {}; this.attributes = {};
      this.style = {}; this.listeners = {}; this.open = false;
      this.classList = {
        add: name => {if (!this.className.split(/\s+/).includes(name)) this.className += ' ' + name;},
        toggle: (name, enabled) => {
          this.className = this.className.split(/\s+/).filter(value => value && value !== name).concat(enabled ? [name] : []).join(' ');
        },
      };
    }
    setAttribute(name, value) {
      this.attributes[name] = value;
      if (name === 'id') this.id = value;
      if (name === 'class') this.className = value;
      if (name.startsWith('data-')) this.dataset[name.slice(5).replace(/-([a-z])/g, (_, char) => char.toUpperCase())] = value;
    }
    matches(selector) {
      if (selector.startsWith('#')) return this.id === selector.slice(1);
      if (selector.startsWith('.')) return this.className.split(/\s+/).includes(selector.slice(1));
      if (selector.startsWith('[')) return Object.hasOwn(this.attributes, selector.slice(1, -1)) ||
        Object.hasOwn(this.dataset, selector.slice(6, -1).replace(/-([a-z])/g, (_, char) => char.toUpperCase()));
      return this.tagName === selector;
    }
    querySelectorAll(selector) {
      return this.children.filter(child => child instanceof Element).flatMap(child => [
        ...(child.matches(selector) ? [child] : []), ...child.querySelectorAll(selector),
      ]);
    }
    querySelector(selector) {return this.querySelectorAll(selector)[0] ?? null;}
    closest(selector) {return this.matches(selector) ? this : this.parentElement?.closest(selector) ?? null;}
    contains(node) {return node === this || this.children.some(child => child instanceof Element && child.contains(node));}
    remove() {
      if (this.parentElement) this.parentElement.children.splice(this.parentElement.children.indexOf(this), 1);
      this.parentElement = null;
    }
    append(...nodes) {
      for (const node of nodes) {
        if (node instanceof Element) {node.remove(); node.parentElement = this;}
        this.children.push(node);
      }
    }
    before(node) {this.insertSibling(node, 0);}
    after(node) {this.insertSibling(node, 1);}
    insertSibling(node, offset) {
      node.remove(); node.parentElement = this.parentElement;
      this.parentElement.children.splice(this.parentElement.children.indexOf(this) + offset, 0, node);
    }
    replaceChildren(...nodes) {for (const child of this.children) if (child instanceof Element) child.parentElement = null; this.children = []; this.append(...nodes);}
    set textContent(text) {this.replaceChildren(String(text));}
    get textContent() {return this.children.map(child => typeof child === 'string' ? child : child.textContent).join('');}
    set innerHTML(text) {this.replaceChildren();}
    addEventListener(type, callback) {(this.listeners[type] ||= []).push(callback);}
    click() {for (const callback of this.listeners.click ?? []) callback({target:this});}
    blur() {}
    focus() {document.activeElement = this;}
  }
  const tree = new Element('document'), stack = [tree];
  const html = legacy ? `<html><head></head><body><div class="title-row"><div class="product-identity">SID Synth</div></div>
    <details id="sidImportTools"><button id="loadSidSound">Load SID</button></details>
    <div><button id="loadPreset">Load preset</button><input id="presetFileInput"><button id="savePreset">Save voice</button><button id="saveChannelSettings">Save setup</button></div>
    <p id="audioStatus"></p></body></html>` : fs.readFileSync(require('node:path').join(__dirname, '../dist/index.html'), 'utf8');
  const voidTags = new Set(['area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr']);
  for (const token of html.matchAll(/<\/?([a-z][\w-]*)([^>]*)>|([^<]+)/gi)) {
    if (!token[1]) {stack.at(-1).append(token[3]); continue;}
    const tag = token[1].toLowerCase();
    if (token[0].startsWith('</')) {
      const index = stack.findLastIndex(node => node.tagName === tag);
      if (index > 0) stack.length = index;
      continue;
    }
    const node = new Element(tag);
    for (const attr of token[2].matchAll(/([:\w-]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+)))?/g)) node.setAttribute(attr[1], attr[2] ?? attr[3] ?? attr[4] ?? '');
    stack.at(-1).append(node); if (!voidTags.has(tag)) stack.push(node);
  }
  const document = {
    readyState:'complete', head:tree.querySelector('head'), body:tree.querySelector('body'), listeners:{},
    getElementById:id => tree.querySelector('#' + id), querySelector:selector => tree.querySelector(selector),
    querySelectorAll:selector => tree.querySelectorAll(selector), createElement:tag => new Element(tag),
    addEventListener(type, callback) {(this.listeners[type] ||= []).push(callback);},
  };
  const window = {listeners:{}, addEventListener(type, callback) {(this.listeners[type] ||= []).push(callback);},
    __TAURI_INTERNALS__:{invoke:async command => {calls.push(command); return false;}}};
  window.top = window;
  const calls = [], originalMenu = document.getElementById('synthMenu');
  if (originalMenu) {
    // The imported module installs its own menu handlers before announcing the
    // desktop bridge. Preserve both the elements and those handler counts.
    originalMenu.addEventListener('toggle', () => {});
    document.getElementById('synthMenuButton').addEventListener('pointerdown', () => {});
    originalMenu.querySelector('.synth-menu-panel').addEventListener('click', () => {});
    document.addEventListener('pointerdown', () => {}); window.addEventListener('keydown', () => {});
  }
  class Anchor {click() {}}
  vm.runInNewContext(source, {window, document, location:new URL('tauri://localhost/index.html'),
    URL:{createObjectURL() {}, revokeObjectURL() {}}, HTMLAnchorElement:Anchor, Map, Uint8Array, Array});
  return {document, window, originalMenu, calls, ready() {for (const callback of window.listeners['tetorica-synth-ready']) callback();}};
}

test('desktop extends the shipped Web menu once and preserves project and SID import actions', async () => {
  const ui = bootToolbar(), {document, window, originalMenu} = ui;
  const get = id => document.getElementById(id);
  ui.ready(); ui.ready(); await settle();
  for (const id of ['synthMenu','synthMenuButton','synthMenuPanel','synthPinButton','synthDesktopTools','synthMenuAudio','loadPreset','savePreset','saveChannelSettings','presetFileInput']) {
    assert.equal(document.querySelectorAll('#' + id).length, 1, id + ' remains unique');
  }
  assert.equal(get('synthMenu'), originalMenu);
  for (const id of ['sidMenuProjectNew','sidMenuProjectImport','sidMenuFilesImport','sidMenuProjectExport','sidMenuFileExport','loadSidSound']) assert.ok(originalMenu.contains(get(id)), id + ' remains in the Web menu');
  assert.equal(get('synthMenuSid'), null, 'The existing SID import action needs no duplicate shortcut');
  const importSection = get('sidMenuProjectImport').closest('.synth-menu-section');
  assert.ok(importSection.contains(get('loadPreset'))); assert.ok(importSection.contains(get('presetFileInput')));
  const exportSection = get('sidMenuProjectExport').closest('.synth-menu-section');
  assert.ok(exportSection.contains(get('savePreset'))); assert.ok(exportSection.contains(get('saveChannelSettings')));
  assert.ok(originalMenu.contains(get('synthMenuAudio')));
  assert.ok(originalMenu.contains(document.querySelector('[data-reset-offline-cache]')));
  assert.equal(originalMenu.parentElement, get('synthDesktopTools').parentElement, 'Pin stays beside the existing toolbar menu');
  assert.equal(originalMenu.listeners.toggle.length, 1);
  assert.equal(get('synthMenuButton').listeners.pointerdown.length, 1);
  assert.equal(get('synthMenuPanel').listeners.click.length, 1);
  assert.equal(document.listeners.pointerdown.length, 1); assert.equal(window.listeners.keydown.length, 1);
  assert.deepEqual(ui.calls, ['window_pin_state']);
});

test('older Web releases receive one working desktop menu and a SID import shortcut', async () => {
  const ui = bootToolbar({legacy:true}), {document, window} = ui;
  const get = id => document.getElementById(id);
  ui.ready(); ui.ready(); await settle();
  const menu = get('synthMenu'), button = get('synthMenuButton');
  assert.equal(document.querySelectorAll('#synthMenu').length, 1);
  for (const id of ['loadPreset','savePreset','saveChannelSettings','presetFileInput','synthMenuAudio','synthMenuSid']) assert.ok(menu.contains(get(id)), id + ' is available in the fallback menu');
  let selections = 0; get('loadSidSound').addEventListener('click', () => selections++);
  get('synthMenuSid').click(); assert.equal(selections, 1); assert.equal(get('sidImportTools').open, true);
  assert.equal(menu.listeners.toggle.length, 1); assert.equal(button.listeners.pointerdown.length, 1);
  menu.open = true; menu.listeners.toggle[0](); assert.equal(button.attributes['aria-expanded'], 'true');
  window.listeners.keydown[0]({key:'Escape', preventDefault() {}, stopPropagation() {}});
  assert.equal(menu.open, false); assert.equal(button.attributes['aria-expanded'], 'false'); assert.equal(document.activeElement, button);
  let saves = 0; get('savePreset').addEventListener('click', () => saves++); get('savePreset').click(); assert.equal(saves, 1);
  assert.deepEqual(ui.calls, ['window_pin_state']);
});

test('native pin reads actual state and toggles without taking keyboard focus', async () => {
  for (const url of ['tauri://localhost/index.html', 'http://tauri.localhost/index.html', 'https://tauri.localhost/index.html']) {
    const ui = bootPin({url, initial: true});
    assert.equal(ui.button.disabled, true); assert.equal(ui.button.hidden, true);
    await settle();
    assert.equal(ui.button.hidden, false); assert.equal(ui.button.disabled, false);
    assert.equal(ui.button.attributes['aria-pressed'], 'true'); assert.equal(ui.button.selected, true);
    assert.equal(ui.button.title, 'Unpin window');
    let prevented = false;
    ui.button.listeners.pointerdown[0]({preventDefault() {prevented = true;}});
    assert.equal(prevented, true);
    await ui.button.listeners.click[0]();
    assert.equal(ui.calls[1].command, 'set_window_pin'); assert.equal(ui.calls[1].args.pinned, false);
    assert.equal(ui.button.attributes['aria-pressed'], 'false'); assert.equal(ui.button.selected, false);
    assert.equal(ui.button.title, 'Pin window on top');
  }
});

test('pin command errors retain the last confirmed state and allow retry', async () => {
  const ui = bootPin({initial: true, invoke: async command => {
    if (command === 'window_pin_state') return true;
    throw new Error('not supported');
  }});
  await settle();
  await ui.button.listeners.click[0]();
  assert.equal(ui.button.attributes['aria-pressed'], 'true'); assert.equal(ui.button.selected, true);
  assert.equal(ui.button.disabled, false); assert.match(ui.status.textContent, /Could not pin window.*not supported/);
  await ui.button.listeners.click[0]();
  assert.equal(ui.calls.filter(call => call.command === 'set_window_pin').length, 2);
});

test('pin uses the native returned state and rejects duplicate in-flight toggles', async () => {
  let complete;
  const ui = bootPin({invoke: (command) => command === 'window_pin_state' ? false : new Promise(resolve => {complete = resolve;})});
  await settle();
  const toggle = ui.button.listeners.click[0]();
  assert.equal(ui.button.disabled, true); assert.equal(ui.button.attributes['aria-pressed'], 'false');
  await ui.button.listeners.click[0]();
  assert.equal(ui.calls.length, 2);
  complete(false); // The actual native state can differ from the requested target.
  await toggle;
  assert.equal(ui.button.disabled, false); assert.equal(ui.button.attributes['aria-pressed'], 'false');
});

test('pin mounts once when DOM is ready or when Synth supplies the controls later', async () => {
  const pending = bootPin({loading: true});
  assert.equal(pending.calls.length, 0);
  pending.domEvents.DOMContentLoaded(); pending.events['tetorica-synth-ready']();
  await settle();
  assert.equal(pending.calls.length, 1); assert.equal(pending.button.listeners.click.length, 1);
  const dynamic = bootPin({available: false});
  assert.equal(dynamic.calls.length, 0);
  dynamic.mount(); dynamic.mount();
  await settle();
  assert.equal(dynamic.calls.length, 1); assert.equal(dynamic.button.listeners.click.length, 1);
});

test('remote pages and subframes cannot mount or call native pin controls', async () => {
  for (const [url, subframe] of [['https://example.com/', false], ['http://localhost:8890/', false], ['tauri://other/', false], ['tauri://localhost/', true]]) {
    const ui = bootPin({url, subframe});
    ui.mount(); await settle();
    assert.equal(ui.button.hidden, true); assert.equal(ui.button.listeners.click, undefined); assert.equal(ui.calls.length, 0);
  }
});

test('failed or malformed initial native pin state leaves the control hidden', async () => {
  for (const invoke of [() => {throw new Error('unavailable');}, () => 'false']) {
    const ui = bootPin({invoke}); await settle();
    assert.equal(ui.button.hidden, true); assert.match(ui.status.textContent, /Could not read window pin state/);
    assert.equal(ui.button.attributes['aria-pressed'], 'false');
  }
});
