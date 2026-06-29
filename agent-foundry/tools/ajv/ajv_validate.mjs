#!/usr/bin/env node
/*
 * Deterministic JSON Schema validator for the validate-json-schema-responses task.
 *
 * The real validation engine (ajv v8) the task mandates. It is invoked by the
 * Python harness (agents/common/schema_contract.py) as a subprocess — never by an
 * agent. Reads ONE JSON request on stdin:
 *
 *   { "schema": <JSON Schema object>, "data": <response body to validate>,
 *     "draft": "draft-07" | "2020-12" }
 *
 * and writes ONE JSON object on stdout:
 *
 *   { "valid": <bool>, "error_count": <int>,
 *     "errors": [ { "path": "...", "message": "...", "keyword": "..." }, ... ],
 *     "fields_validated": <int> }
 *
 * Configuration (locked in task_spec.md, Phase-2 answers):
 *   ajv v8 · draft-07 (default) · strict: true · additionalProperties:false honored.
 * A missing required field and an undocumented extra field are EQUAL-severity
 * errors — both make the response non-conformant (each is one ajv error).
 */
import { readFileSync } from "node:fs";
import Ajv from "ajv";
import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";

function readStdin() {
  try {
    return readFileSync(0, "utf8");
  } catch {
    return "";
  }
}

function makeAjv(draft) {
  // strict:true surfaces schema-author mistakes; allErrors:true so we report
  // EVERY validation error per response, not just the first.
  const opts = { strict: true, allErrors: true, allowUnionTypes: true };
  const ajv = draft === "2020-12" ? new Ajv2020(opts) : new Ajv(opts);
  addFormats(ajv);
  return ajv;
}

// Count leaf properties present in the validated data object (best-effort
// "fields validated" headline number per the task's report column).
function countFields(data) {
  if (data && typeof data === "object" && !Array.isArray(data)) {
    return Object.keys(data).length;
  }
  return 0;
}

function main() {
  const raw = readStdin();
  let req;
  try {
    req = JSON.parse(raw);
  } catch (e) {
    process.stdout.write(
      JSON.stringify({ valid: false, error_count: 1, fields_validated: 0,
        errors: [{ path: "", keyword: "input", message: `bad validator input: ${e.message}` }] })
    );
    return;
  }
  const { schema, data, draft } = req;
  if (schema == null) {
    // No documented schema => nothing to validate (the current-spec case).
    process.stdout.write(
      JSON.stringify({ valid: null, error_count: 0, fields_validated: 0, errors: [],
        note: "no schema supplied — nothing to validate" })
    );
    return;
  }
  const ajv = makeAjv(draft || "draft-07");
  let validate;
  try {
    validate = ajv.compile(schema);
  } catch (e) {
    process.stdout.write(
      JSON.stringify({ valid: false, error_count: 1, fields_validated: countFields(data),
        errors: [{ path: "", keyword: "schema", message: `schema compile error: ${e.message}` }] })
    );
    return;
  }
  const ok = validate(data);
  const errors = (validate.errors || []).map((e) => ({
    path: e.instancePath || "",
    keyword: e.keyword,
    message: `${e.instancePath || "(root)"} ${e.message}`.trim(),
    params: e.params,
  }));
  process.stdout.write(
    JSON.stringify({ valid: !!ok, error_count: errors.length,
      fields_validated: countFields(data), errors })
  );
}

main();
