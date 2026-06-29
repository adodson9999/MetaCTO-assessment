---
name: add-reference
description: >
  Add a file to the MetaCTO-Assessment project's references folder and register
  it in this project's CLAUDE.md. Use when the user provides a PDF, guide, doc,
  or any file they want remembered for future sessions in this project. Trigger
  with "add this to references", "save this as a reference", "add to my reference
  library", or any time a file is shared and the user wants it permanently
  available within the MetaCTO-Assessment project. Also accepts an http(s) URL
  as the source, and an optional collection subfolder so callers (such as the
  cli-factory skill) can file many links under `references/<collection>/`.
---

# Skill: Add Reference to Library

## When this fires

Activate this skill when the user says any of:

- "add this to my reference library"
- "register this file in CLAUDE.md"
- "save this as a reference"
- any phrasing that names a file and asks to store it as a reference

If the intent is close but not certain, ask before starting. Do not assume.

## Definitions used below

- ROOT: the MetaCTO-Assessment project root at `/Users/alexdodson/Downloads/Jarvis/assessment/MetaCTO-Assessment` (the directory that contains this project's CLAUDE.md). All `references/` paths and the retrieval backend are relative to ROOT — never the parent Jarvis vault.
- STEM: the original filename without its extension. For a URL source, a filesystem-safe slug derived from the URL (see Step 0).
- EXT: the original file extension. For a URL source, the fetched content type's extension (`html` for a web page, `pdf` for a PDF, etc.).
- ORIGINAL: the exact original filename, including case and all characters. For a URL source, `[STEM].[EXT]`.
- SOURCE: the thing being registered — a local file path, an uploaded file, or an http(s) URL.
- COLLECTION: an optional named subfolder under `references/`, supplied by the caller (the user, or another skill such as cli-factory). Absent for a plain single-file add.
- DESTDIR: the destination directory for all three artifacts. `references/` when no COLLECTION is given, or `references/[COLLECTION]/` when one is. **Everywhere a step below names the `references/` directory, read it as DESTDIR.**
- BACKEND: the local contextual-retrieval backend at `ROOT/scripts/contextual_retrieval.py`, configured by `ROOT/scripts/retrieval_config.json` (LanceDB store, BGE-M3 embeddings, LanceDB full-text BM25 index). It runs in this project's own virtualenv at `ROOT/.venv` against the project-local model cache at `ROOT/.models` — no dependency on the parent Jarvis vault. Always invoke it as `ROOT/.venv/bin/python ROOT/scripts/contextual_retrieval.py ...`. If `ROOT/.venv` is missing, recreate it with `python3 -m venv ROOT/.venv && ROOT/.venv/bin/pip install -r ROOT/scripts/requirements.txt`.
- The three artifacts this skill writes (all inside DESTDIR):
  1. `DESTDIR/[STEM].md` (the docling output, this is the registered reference)
  2. `DESTDIR/original_copy_[ORIGINAL]` (the renamed or saved copy of the source)
  3. `DESTDIR/[STEM].lance` (the LanceDB table of contextualized, embedded, BM25-indexed chunks)

## Hard rules (apply at every step)

1. Never guess. If anything required is missing or ambiguous, stop and ask the user in plain language.
2. Never overwrite anything. A collision of any kind is resolved by renaming, never by replacing.
3. No half-done state. If any copy, conversion, docling run, chunking, embedding, table write, or CLAUDE.md edit fails, notify the user, explain exactly why it failed, give step-by-step instructions to fix it, then continue the skill from the failed step. Repeat until it succeeds. Do not stop in a partial state and do not silently move on.
4. When bash is unavailable, hand the user the exact terminal command to run, then continue once they confirm it ran.

---

## Step 0: Resolve collection and destination (run first)

1. COLLECTION: if the caller named a collection/subfolder (a user, or the cli-factory skill passing one per discovered link), set COLLECTION to it and DESTDIR = `references/[COLLECTION]/`. Otherwise leave COLLECTION unset and DESTDIR = `references/`. Sanitize COLLECTION to a filesystem-safe folder name; never let it contain `..` or an absolute path, so DESTDIR can never escape `references/`.
2. Create DESTDIR if it does not exist (`mkdir -p DESTDIR`). Write nothing outside DESTDIR.
3. From here on, every reference to the `references/` directory means DESTDIR.

## Step 1: Identify the source

SOURCE is a local path the user provides, a file the user uploaded, or an http(s) URL.

- If no path, upload, or URL is provided: stop. Ask what to register. Do not pick one.
- If more than one of {path, upload, URL} is provided: stop. Ask which to use. Do not pick one.
- **Local file or upload:** confirm the file exists at its stated location. If it does not: stop. State it plainly, for example: "The file [name] does not exist at [location]." Do not guess an alternative, do not search for similar names, do not proceed. Ask for a correct path or a new upload, then re-check existence.
- **URL:** confirm it is a single, well-formed http(s) URL. Do not invent or "correct" URLs — register only the exact URL given (or, in a cli-factory run, the exact URL discovered). Derive STEM as a filesystem-safe slug from the URL: lowercase the host plus path, drop the scheme and query string, replace non-alphanumeric runs with `-`, and use `index` if the path is empty (e.g. `https://api.example.com/docs/auth?v=2` → `api-example-com-docs-auth`). The actual fetch happens in Step 5; reachability is verified there.

Only continue once exactly one source is identified (a file confirmed to exist, or a well-formed URL).

## Step 2: Determine the destination name

- Keep the exact ORIGINAL filename. Do not lowercase it, do not convert spaces to hyphens, do not change any character.
- The only thing that changes is the location. The three target names are `references/[STEM].md`, `references/original_copy_[ORIGINAL]`, and `references/[STEM].lance`.

## Step 3: Classify the type and check for collisions

This step runs before any copy, conversion, docling run, or embedding.

1. Classify the file type (this is where picture detection happens, not later).
2. Resolve all three artifact names: `references/[STEM].md`, `references/original_copy_[ORIGINAL]`, and `references/[STEM].lance`.
3. Check for a collision of any kind:
  - Does `references/[STEM].md` already exist on disk?
  - Does `references/original_copy_[ORIGINAL]` already exist on disk?
  - Does `references/[STEM].lance` already exist on disk?
  - Does CLAUDE.md already contain any entry pointing at `references/[STEM].md`, the original name, or `references/[STEM].lance`?
4. If there is any collision at all (any of the three files on disk, or any matching entry in CLAUDE.md): do not overwrite. Ask the user for a new base name. Replace STEM with the new name, re-resolve all three artifact names, and run this entire collision check again. The new base name flows to all three artifacts. Repeat until no collision of any kind remains.

## Step 4: Confirm the type is supported by docling

Everything is processed through docling, so the file type must be one docling can parse.

Supported input types:

- Documents: PDF, DOCX, PPTX, XLSX, HTML
- E-books: EPUB
- Email: EML, MSG
- Images: PNG, TIFF, JPEG, JPG
- Audio: WAV, MP3, WebVTT
- Text family: TXT, TEXT, MD, MARKDOWN, QMD, RMD, LaTeX
- XML schemas: USPTO patents, JATS articles, XBRL financial reports

If the file type is not on this list (for example: ZIP, MP4, MOV, EXE, or any other unsupported type): stop. Notify the user, state that docling cannot parse this type, register nothing, and leave every file untouched. Do not invent a workaround.

## Step 5: Run docling and rename the original

In this order:

1. Produce `DESTDIR/[STEM].md` (the reference) with docling:
  - **Local file or upload:** run docling on the source file: `docling [source] --to md --output DESTDIR/`.
  - **URL:** docling fetches and converts the page directly — `docling [URL] --to md --output DESTDIR/`. If the page is auth-walled, pass `--headers` per docling's docs; never put a secret value in any artifact (see the secret rule). If docling cannot fetch or parse the URL, fall back to the `defuddle` skill to produce clean markdown for the public URL, writing the same `DESTDIR/[STEM].md`. If both fail, apply Hard Rule 3.
  - If bash is unavailable, hand the user the exact command, then continue once they confirm.
2. Save the source copy as `DESTDIR/original_copy_[ORIGINAL]`:
  - **Local file or upload:** rename/copy the source to that path.
  - **URL:** save the fetched raw page (the bytes docling downloaded, or a one-time fetch of the URL) as `DESTDIR/original_copy_[STEM].[EXT]`.
3. If either action fails, apply Hard Rule 3: notify, explain why, give fix steps, continue from the failed action until it succeeds.

## Step 6: Get the one-line description

The user provides this. Required format: what it is plus when to use it. Example: "Q3 vendor contract, use when checking renewal terms or payment schedules."

- If the description is missing, vague, or only covers one half (says what it is but not when to use it, or the reverse): notify the user that it is unclear and re-ask. Repeat until the description clearly states both what it is and when to use it.
- **Bulk / collection mode (e.g. a cli-factory run over many URLs):** do not stop to ask per link. Auto-derive the description from the page's title/`<h1>` plus the collection's purpose, keeping both halves — for example: "[Page title] — documentation page for the [COLLECTION] CLI; use when looking up [the page's topic]." If a title cannot be determined, fall back to the slug. Both halves (what it is + when to use it) must still be present.

## Step 7: Contextual retrieval preprocessing

This step runs after the description is set and before CLAUDE.md is updated. Its inputs are `references/[STEM].md` from Step 5 and the description from Step 6. Its output is the LanceDB table `references/[STEM].lance`, whose name was already resolved and collision-checked in Step 3. All work goes through BACKEND.

1. Chunk `references/[STEM].md` using BACKEND's `chunk()`, which splits by document heading or section, caps each chunk at the configured token limit, and carries the configured overlap on any split section.
2. For each chunk, generate a 1 to 2 sentence context using BACKEND's `make_context()`, passing the chunk text, the full reference document, and the Step 6 description as document-level context. The model that writes this context is set in the backend config, not in this skill.
3. Embed and store using BACKEND's `embed_and_store()`: embed each chunk's contextualized text with BGE-M3, write the rows into `references/[STEM].lance`, and build the full-text (BM25) index so hybrid search works. Each row includes at least: chunk_id, section, context, text, contextualized_text, and the dense vector.
  - Build the table by running BACKEND's `build` command from ROOT: `.venv/bin/python scripts/contextual_retrieval.py build DESTDIR/[STEM].md DESTDIR/[STEM].lance`. If bash is unavailable, hand the user that exact command, then continue once they confirm.
4. If chunking, context generation, embedding, or the table write fails, apply Hard Rule 3: notify, explain why, give fix steps, continue from the failed action until it succeeds. Never leave a partial table. If a partial `.lance` table was written before failure, state that it is incomplete and must not be used until the step completes, and finish building it before moving on.

## Step 8: Update CLAUDE.md

- The target is this project's CLAUDE.md at `ROOT/CLAUDE.md` (the MetaCTO-Assessment project root), never the parent Jarvis vault's CLAUDE.md.
- If `ROOT/CLAUDE.md` does not exist (unlikely): the skill is permitted to create it at ROOT. Do not create it anywhere else and do not guess an alternate location.
- Add a single bullet that covers the reference and names its retrieval index (one bullet per reference — in a collection run, one per link):
  - `DESTDIR/[STEM].md`: [description] (retrieval index: `DESTDIR/[STEM].lance`)
- If a "## Reference Library" section does not exist in `ROOT/CLAUDE.md`, create it by appending the `## Reference Library` heading at the end of the file, then add the bullet under it.
- **Collection mode:** group the bullet under a `### [COLLECTION]` subheading inside the Reference Library (create the subheading once, then add each link's bullet beneath it) so all references for one CLI/collection stay together and mirror the `references/[COLLECTION]/` folder.
- If the edit fails after the files were already written: apply Hard Rule 3. The files stay in place, the user is told the registration failed and why, given fix steps, and the edit is retried until it succeeds. Never leave the files on disk unregistered.

## Step 9: Confirm

One line, reflecting the three actual stored artifacts: "Added `DESTDIR/[STEM].md` (reference), `DESTDIR/original_copy_[ORIGINAL]` (source copy), and `DESTDIR/[STEM].lance` (retrieval index), and registered the reference in CLAUDE.md." In a collection run, confirm once at the end with a count: "Added N references under `references/[COLLECTION]/` and registered each in CLAUDE.md."