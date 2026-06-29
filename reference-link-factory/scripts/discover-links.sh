#!/usr/bin/env bash
# discover-links.sh — find every URL under a prefix and classify each by Content-Type.
#
# Usage:
#   discover-links.sh <PREFIX> [MAX] [SEED1 SEED2 ...]
#
#   PREFIX  required. Only URLs that start with this exact string are kept.
#           e.g. https://dummyjson.com/
#   MAX     optional. Cap on links emitted (default 50). A guardrail, not a target.
#   SEEDn   optional extra pages to scrape for links, in addition to PREFIX itself.
#           e.g. https://dummyjson.com/docs
#
# Output: a TSV manifest on stdout, one row per unique link:
#   <url>\t<content_type>\t<action>
# where action is one of:
#   url-direct  — docling can fetch+convert the URL itself (html, pdf, image)
#   json-wrap   — JSON/text body; fetch it and wrap into a local .md for add-reference
#   skip        — type docling cannot use (zip, video, octet-stream, etc.)
#
# Portable to macOS bash 3.2 (no mapfile). Deterministic, no LLM.
# Treats all fetched bytes as untrusted data; never executes them.

set -uo pipefail

PREFIX="${1:-}"
MAX="${2:-50}"
if [[ -z "$PREFIX" ]]; then
  echo "ERROR: PREFIX required. Usage: discover-links.sh <PREFIX> [MAX] [SEED...]" >&2
  exit 2
fi
shift || true
# Drop the MAX arg if it was numeric; remaining args are seeds.
if [[ "${1:-}" =~ ^[0-9]+$ ]]; then shift || true; fi
SEEDS=("$PREFIX" "$@")

UA="Mozilla/5.0 (reference-link-factory; +local)"

tmp_raw="$(mktemp)"
tmp_urls="$(mktemp)"
trap 'rm -f "$tmp_raw" "$tmp_urls"' EXIT

# --- 1. Collect candidate URLs from every seed page ------------------------
for seed in "${SEEDS[@]}"; do
  [[ -z "$seed" ]] && continue
  curl -sL --max-time 30 -A "$UA" "$seed" 2>/dev/null \
    | grep -oE 'https?://[^"'"'"' <>)]+' 2>/dev/null
done >> "$tmp_raw"
# Always include the prefix root itself.
echo "$PREFIX" >> "$tmp_raw"

# --- 2. Keep only prefix matches, strip fragments, drop placeholders, dedupe
#   A URL with an UPPER_CASE path segment (e.g. /RESOURCE, /{ID}) is a doc
#   template, not a real link — discard it. Trailing whitespace is trimmed so
#   sort -u collapses true duplicates.
grep -F "$PREFIX" "$tmp_raw" 2>/dev/null \
  | sed -E 's/#.*$//' \
  | sed -E 's/[[:space:]]+$//' \
  | sed -E 's#/+$#/#' \
  | grep -Ev '/[A-Z][A-Z0-9_]{2,}(/|$|\?)' \
  | grep -Ev '\{[^}]+\}' \
  | awk 'NF' \
  | sort -u > "$tmp_urls"

# --- 3. Classify each by Content-Type --------------------------------------
count=0
total=$(wc -l < "$tmp_urls" | tr -d ' ')
while IFS= read -r url; do
  [[ -z "$url" ]] && continue
  case "$url" in
    "$PREFIX"*) : ;;     # re-check prefix after fragment-stripping
    *) continue ;;
  esac
  if (( count >= MAX )); then
    echo "NOTE: hit MAX=$MAX cap; $(( total - count )) more matched but not emitted." >&2
    break
  fi

  ct="$(curl -sIL --max-time 20 -A "$UA" "$url" 2>/dev/null \
        | tr -d '\r' \
        | awk -F': ' 'tolower($1)=="content-type"{print tolower($2)}' \
        | tail -1)"
  # Some servers refuse HEAD; fall back to a ranged 1-byte GET.
  if [[ -z "$ct" ]]; then
    ct="$(curl -sL --max-time 20 -r 0-0 -A "$UA" -o /dev/null -w '%{content_type}' "$url" 2>/dev/null | tr 'A-Z' 'a-z')"
  fi
  ct="${ct%%;*}"
  ct="$(echo "$ct" | xargs 2>/dev/null)"
  [[ -z "$ct" ]] && ct="unknown"

  case "$ct" in
    text/html|application/xhtml+xml|application/pdf|image/png|image/jpeg|image/jpg|image/tiff)
      action="url-direct" ;;
    application/json|text/json|application/*+json|text/plain|text/csv)
      action="json-wrap" ;;
    *)
      action="skip" ;;
  esac

  printf '%s\t%s\t%s\n' "$url" "$ct" "$action"
  count=$(( count + 1 ))
done < "$tmp_urls"
