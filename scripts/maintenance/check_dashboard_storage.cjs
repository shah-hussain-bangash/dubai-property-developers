'use strict';

// Run only inside the dashboard image with a fresh disposable volume.
// These are synthetic storage probes, not portal records or customer data.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

assert.equal(typeof process.getuid, 'function', 'This check requires a Linux container');
assert.notEqual(process.getuid(), 0, 'Dashboard must run as non-root');
const directory = process.env.DUBAI_PORTAL_DATA_DIR;
assert.equal(directory, '/app/portal-data');
const mode = process.argv[2];
assert.ok(mode === 'write' || mode === 'read', 'Choose write or read');
const file = path.join(directory, 'ci-fictional-storage.json');
const fixture = { fictional: true, source: 'website', owner: 'synthetic-operator' };

if (mode === 'write') {
  fs.mkdirSync(directory, { recursive: true, mode: 0o700 });
  const lock = path.join(directory, 'ci-fictional-storage.lock');
  const descriptor = fs.openSync(lock, 'wx', 0o600);
  try {
    const temporary = file + '.tmp';
    const writer = fs.openSync(temporary, 'wx', 0o600);
    try {
      fs.writeFileSync(writer, JSON.stringify(fixture));
      fs.fsyncSync(writer);
    } finally {
      fs.closeSync(writer);
    }
    fs.renameSync(temporary, file);
  } finally {
    fs.closeSync(descriptor);
    fs.unlinkSync(lock);
  }
}

assert.deepEqual(JSON.parse(fs.readFileSync(file, 'utf8')), fixture);
assert.equal(fs.statSync(file).uid, process.getuid());
assert.equal(fs.statSync(file).mode & 0o777, 0o600);
assert.equal(fs.statSync(directory).mode & 0o777, 0o700);
console.log(`Dashboard storage ${mode} check passed as non-root`);
