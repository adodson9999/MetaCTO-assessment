---
name: add-reference
description: >
  Add a file to the Jarvis references folder and register it in CLAUDE.md.
  Use when the user provides a PDF, guide, doc, or any file they want
  remembered for future sessions. Trigger with "add this to references",
  "save this as a reference", "add to my reference library", or any time
  a file is shared and the user wants it permanently available to the AIOS.
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

- ROOT: the directory that contains CLAUDE.md. All `references/` paths and the retrieval backend are relative to ROOT.
- STEM: the original filename without its extension.
- EXT: the original file extension.
- ORIGINAL: the exact original filename, including case and all characters.
- BACKEND: the local contextual-retrieval backend at `ROOT/scripts/contextual_retrieval.py`, configured by `ROOT/scripts/retrieval_config.json` (LanceDB store, BGE-M3 embeddings, LanceDB full-text BM25 index).
- The three artifacts this skill writes:
  1. `references/[STEM].md` (the docling output, this is the registered reference)
  2. `references/original_copy_[ORIGINAL]` (the renamed copy of the source file)
  3. `references/[STEM].lance` (the LanceDB table of contextualized, embedded, BM25-indexed chunks)

## Hard rules (apply at every step)

1. Never guess. If anything required is missing or ambiguous, stop and ask the user in plain language.
2. Never overwrite anything. A collision of any kind is resolved by renaming, never by replacing.
3. No half-done state. If any copy, conversion, docling run, chunking, embedding, table write, or CLAUDE.md edit fails, notify the user, explain exactly why it failed, give step-by-step instructions to fix it, then continue the skill from the failed step. Repeat until it succeeds. Do not stop in a partial state and do not silently move on.
4. When bash is unavailable, hand the user the exact terminal command to run, then continue once they confirm it ran.

---

## Step 1: Identify the file

Input is either a path the user provides or a file the user uploaded.

- If neither a path nor an upload is provided: stop. Ask which file to register. Do not pick one.
- If both a path and an upload are provided: stop. Ask which of the two to use. Do not pick one.
- Confirm the file exists at its stated location (the given path, or the upload location for an uploaded file).
- If the file does not exist: stop. State it plainly, for example: "The file [name] does not exist at [location]." Do not guess an alternative, do not search for similar names, do not proceed. Ask the user for a correct path or a new upload, then re-check existence.

Only continue once exactly one file is identified and confirmed to exist.

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

1. Run the source file through docling to produce `references/[STEM].md`. This is the reference.
  - If bash is unavailable, hand the user the exact command (for example: `docling [source] --to md --output references/`), then continue once they confirm.
2. Rename the source copy to `references/original_copy_[ORIGINAL]`.
3. If either action fails, apply Hard Rule 3: notify, explain why, give fix steps, continue from the failed action until it succeeds.

## Step 6: Get the one-line description

The user provides this. Required format: what it is plus when to use it. Example: "Q3 vendor contract, use when checking renewal terms or payment schedules."

- If the description is missing, vague, or only covers one half (says what it is but not when to use it, or the reverse): notify the user that it is unclear and re-ask. Repeat until the description clearly states both what it is and when to use it.

## Step 7: Contextual retrieval preprocessing

This step runs after the description is set and before CLAUDE.md is updated. Its inputs are `references/[STEM].md` from Step 5 and the description from Step 6. Its output is the LanceDB table `references/[STEM].lance`, whose name was already resolved and collision-checked in Step 3. All work goes through BACKEND.

1. Chunk `references/[STEM].md` using BACKEND's `chunk()`, which splits by document heading or section, caps each chunk at the configured token limit, and carries the configured overlap on any split section.
2. For each chunk, generate a 1 to 2 sentence context using BACKEND's `make_context()`, passing the chunk text, the full reference document, and the Step 6 description as document-level context. The model that writes this context is set in the backend config, not in this skill.
3. Embed and store using BACKEND's `embed_and_store()`: embed each chunk's contextualized text with BGE-M3, write the rows into `references/[STEM].lance`, and build the full-text (BM25) index so hybrid search works. Each row includes at least: chunk_id, section, context, text, contextualized_text, and the dense vector.
  - If bash is unavailable, hand the user the exact command to run the backend module on `references/[STEM].md` writing to `references/[STEM].lance`, then continue once they confirm.
4. If chunking, context generation, embedding, or the table write fails, apply Hard Rule 3: notify, explain why, give fix steps, continue from the failed action until it succeeds. Never leave a partial table. If a partial `.lance` table was written before failure, state that it is incomplete and must not be used until the step completes, and finish building it before moving on.

## Step 8: Update CLAUDE.md

- If CLAUDE.md does not exist (unlikely): the skill is permitted to create it. Ask the user where ROOT is before creating it. Do not guess the location.
- Add a single bullet under the "Reference Library" section that covers the reference and names its retrieval index:
  - `references/[STEM].md`: [description] (retrieval index: `references/[STEM].lance`)
- If the "Reference Library" section does not exist, create it immediately before the "## How you work with me" heading.
- If the "## How you work with me" heading is also missing: stop and ask the user where the "Reference Library" section should be placed. Do not guess placement.
- If the edit fails after the files were already written: apply Hard Rule 3. The files stay in place, the user is told the registration failed and why, given fix steps, and the edit is retried until it succeeds. Never leave the files on disk unregistered.

## Step 9: Confirm

One line, reflecting the three actual stored artifacts: "Added `references/[STEM].md` (reference), `references/original_copy_[ORIGINAL]` (source copy), and `references/[STEM].lance` (retrieval index), and registered the reference in CLAUDE.md."