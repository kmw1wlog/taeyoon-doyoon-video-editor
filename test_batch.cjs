const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const elements = new Map();
function element(id) {
  if (!elements.has(id)) elements.set(id, { value: '', files: [], innerHTML: '', textContent: '', disabled: false, classList: { add() {}, toggle() {} } });
  return elements.get(id);
}
const storage = new Map();
const submitted = [];
let id = 0;
const context = vm.createContext({
  document: { getElementById: element },
  sessionStorage: { getItem: key => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value) },
  crypto: { randomUUID: () => String(++id) },
  URL: { createObjectURL: file => `blob:${file.name}`, revokeObjectURL() {} },
  FileReader: class { readAsDataURL(file) { this.result = `data:${file.type};base64,${file.name}`; this.onload(); } },
  fetch: async (path, request) => { submitted.push({ path, body: JSON.parse(request.body) }); return { ok: true, json: async () => ({ taskId: String(submitted.length) }) }; },
  setTimeout: () => {},
  Promise,
  console,
});
vm.runInContext(fs.readFileSync(require('node:path').join(__dirname, 'simple.js'), 'utf8'), context);

(async () => {
  element('minimaxKey').value = 'test-key';
  element('batchImages').files = [
    { name: 'scene-10.png', type: 'image/png', size: 100 },
    { name: 'scene-2.png', type: 'image/png', size: 100 },
  ];
  element('batchPrompts').value = 'second scene\n---\ntenth scene';
  element('batchDuration').value = '5';
  await element('batchGenerate').onclick();
  assert.equal(submitted.length, 2);
  assert.equal(submitted[0].body.prompt, 'second scene');
  assert.equal(submitted[0].body.image, 'data:image/png;base64,scene-2.png');
  assert.equal(submitted[1].body.prompt, 'tenth scene');
  assert.equal(submitted[1].body.image, 'data:image/png;base64,scene-10.png');
  assert.equal([...storage.values()].some(value => value.includes('test-key')), false, 'API key must not be saved');
  element('batchImages').files = [{ name: 'a.png', type: 'image/png', size: 100 }, { name: 'b.png', type: 'image/png', size: 100 }];
  element('batchPrompts').value = 'one prompt';
  await element('batchGenerate').onclick();
  assert.equal(submitted.length, 2, 'mismatched counts must not submit paid requests');
  console.log('batch mapping and mismatch checks passed');
})().catch(error => { console.error(error); process.exitCode = 1; });
