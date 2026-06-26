#!/usr/bin/env node
/*
 * n601 Postman v2.1 schema validation via Newman's OWN bundled loader.
 *
 * The n601 spec calls for `newman run <file> --dry-run`, but Newman has no `--dry-run`
 * flag (and `newman run` without it would actually fire every request at base_url, which
 * is not what "validate the collection schema" means). The faithful, request-free
 * equivalent is to load the collection through `postman-collection` — the exact SDK
 * Newman uses to parse a collection before running it. If the Collection constructs and
 * round-trips, the file is structurally valid Postman v2.1.
 *
 * Exit 0 = valid; non-zero = invalid (with a message on stderr). Prints the recursive
 * request-item count on stdout.
 */
const fs = require('fs');
const { Collection } = require('postman-collection');

const file = process.argv[2];
if (!file) { console.error('usage: validate_collection.js <collection.json>'); process.exit(2); }

let raw;
try { raw = JSON.parse(fs.readFileSync(file, 'utf8')); }
catch (e) { console.error('invalid JSON: ' + e.message); process.exit(1); }

const info = raw.info || {};
if (!info.schema || !/v2\.1\.0/.test(info.schema)) {
  console.error('info.schema is not a Postman v2.1.0 schema URL');
  process.exit(1);
}

let collection;
try { collection = new Collection(raw); }
catch (e) { console.error('Collection failed to load: ' + e.message); process.exit(1); }

let count = 0;
let bad = null;
collection.forEachItem(function (item) {
  count += 1;
  const req = item.request;
  if (!req || !req.method || !req.url) { bad = item.name; }
});
if (bad !== null) { console.error('item ' + bad + ' has a malformed request'); process.exit(1); }

console.log(String(count));
process.exit(0);
