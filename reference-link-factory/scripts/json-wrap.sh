#!/usr/bin/env bash
# json-wrap.sh — fetch a JSON/text endpoint and materialize a local markdown file
# that docling (and therefore add-reference) can ingest. docling has no JSON
# parser, so a live API link cannot be registered directly; this wraps the
# response body into a fenced code block inside a .md instead.
#
# Usage:
#   json-wrap.sh <URL> <OUTDIR>
#
# Prints the path of the written .md on stdout. The fetched body is treated as
# untrusted data — it is only ever written to a file, never executed or eval'd.

set -uo pipefail

URL="${1:-}"
OUTDIR="${2:-}"
if [[ -z "$URL" || -z "$OUTDIR" ]]; then
  echo "ERROR: usage: json-wrap.sh <URL> <OUTDIR>" >&2
  exit 2
fi
mkdir -p "$OUTDIR"

UA="Mozilla/5.0 (reference-link-factory; +local)"

# Slug from host+path: drop scheme/query, non-alnum runs -> '-', empty -> index.
slug="$(printf '%s' "$URL" \
  | sed -E 's#^[a-zA-Z]+://##; s#\?.*$##' \
  | tr 'A-Z' 'a-z' \
  | sed -E 's#[^a-z0-9]+#-#g; s#^-+##; s#-+$##')"
[[ -z "$slug" ]] && slug="index"

body="$(curl -sL --max-time 30 -A "$UA" "$URL" 2>/dev/null)"
if [[ -z "$body" ]]; then
  echo "ERROR: empty/failed fetch for $URL" >&2
  exit 1
fi

# Pretty-print and pick a fence language when the body is valid JSON.
lang="text"
if command -v jq >/dev/null 2>&1; then
  if pretty="$(printf '%s' "$body" | jq . 2>/dev/null)" && [[ -n "$pretty" ]]; then
    body="$pretty"
    lang="json"
  fi
fi

out="$OUTDIR/$slug.md"
{
  echo "# $URL"
  echo
  echo "Captured API response for \`$URL\`."
  echo "Registered by reference-link-factory because docling cannot parse a live JSON endpoint directly."
  echo
  echo '```'"$lang"
  printf '%s\n' "$body"
  echo '```'
} > "$out"

printf '%s\n' "$out"
