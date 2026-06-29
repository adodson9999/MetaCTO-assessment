#!/usr/bin/env bash
# run-factory.sh — register every link in a manifest into the reference library.
#
# Implements the project-local add-reference contract deterministically for a
# whole collection. Reads a manifest (the output of discover-links.sh) on stdin.
#
# Usage:
#   discover-links.sh <PREFIX> <MAX> <SEED...> | run-factory.sh <COLLECTION>
#
# For each manifest row "<url>\t<content_type>\t<action>":
#   - skip            -> reported, not registered
#   - url-direct      -> docling fetches+converts the URL to references/<C>/<stem>.md
#   - json-wrap       -> fetch body, wrap to markdown, that becomes references/<C>/<stem>.md
# Then for every registered link it saves an original-copy artifact and builds
# the .lance retrieval table via the project backend. CLAUDE.md bullets are
# emitted on stdout (the caller appends them) so the file is edited once.
#
# Idempotent: a link whose <stem>.md already exists is skipped (skipped-already).
# Untrusted: fetched bodies are only ever written to files, never executed.

set -uo pipefail

COLLECTION="${1:-}"
if [[ -z "$COLLECTION" ]]; then
  echo "ERROR: usage: ... | run-factory.sh <COLLECTION>" >&2
  exit 2
fi
# Sanitize: no traversal, no absolute path.
COLLECTION="$(printf '%s' "$COLLECTION" | sed -E 's#[^A-Za-z0-9._-]+#-#g; s#^-+##; s#-+$##')"

SKILLDIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SKILLDIR/../.." && pwd)"   # ROOT/reference-link-factory/scripts -> ROOT
DESTDIR="$ROOT/references/$COLLECTION"
BACKEND="$ROOT/.venv/bin/python"
RETRIEVAL="$ROOT/scripts/contextual_retrieval.py"
UA="Mozilla/5.0 (reference-link-factory; +local)"
mkdir -p "$DESTDIR"

slug() {
  printf '%s' "$1" \
    | sed -E 's#^[a-zA-Z]+://##; s#\?.*$##' \
    | tr 'A-Z' 'a-z' \
    | sed -E 's#[^a-z0-9]+#-#g; s#^-+##; s#-+$##'
}

ext_for_ct() {
  case "$1" in
    text/html|application/xhtml+xml) echo "html" ;;
    application/pdf)                 echo "pdf" ;;
    image/png)                       echo "png" ;;
    image/jpeg|image/jpg)            echo "jpg" ;;
    image/tiff)                      echo "tiff" ;;
    application/json|text/json|application/*+json) echo "json" ;;
    text/csv)                        echo "csv" ;;
    *)                               echo "txt" ;;
  esac
}

# Results table to stderr (human), CLAUDE.md bullets to stdout (machine).
printf '%-46s %-11s %-22s %s\n' "URL" "ACTION" "STEM" "STATUS" >&2
printf '%s\n' "------------------------------------------------------------------------------------------" >&2

n_ok=0; n_skip=0; n_fail=0

while IFS=$'\t' read -r url ct action; do
  [[ -z "${url:-}" ]] && continue
  stem="$(slug "$url")"
  [[ -z "$stem" ]] && stem="index"
  md="$DESTDIR/$stem.md"
  lance="$DESTDIR/$stem.lance"

  if [[ "$action" == "skip" ]]; then
    printf '%-46s %-11s %-22s %s\n' "$url" "$action" "$stem" "skipped-unsupported($ct)" >&2
    n_skip=$((n_skip+1)); continue
  fi
  if [[ -e "$md" ]]; then
    printf '%-46s %-11s %-22s %s\n' "$url" "$action" "$stem" "skipped-already" >&2
    n_skip=$((n_skip+1)); continue
  fi

  status="failed"
  desc=""
  if [[ "$action" == "url-direct" ]]; then
    stage="$(mktemp -d)"
    if docling "$url" --to md --output "$stage" >/dev/null 2>&1; then
      produced="$(find "$stage" -maxdepth 1 -name '*.md' | head -1)"
      if [[ -n "$produced" ]]; then
        mv "$produced" "$md"
        # original copy = raw fetched bytes
        curl -sL --max-time 30 -A "$UA" "$url" -o "$DESTDIR/original_copy_$stem.$(ext_for_ct "$ct")" 2>/dev/null
        title="$(grep -m1 -E '^#+ ' "$md" 2>/dev/null | sed -E 's/^#+ +//')"
        [[ -z "$title" ]] && title="$stem"
        desc="$title — page under $COLLECTION; use when referencing this URL ($url)."
        status="registered"
      fi
    fi
    rm -rf "$stage"
  else
    # json-wrap
    if wrapped="$(bash "$SKILLDIR/json-wrap.sh" "$url" "$DESTDIR" 2>/dev/null)" && [[ -f "$wrapped" ]]; then
      # json-wrap already wrote $DESTDIR/<slug>.md == $md
      curl -sL --max-time 30 -A "$UA" "$url" -o "$DESTDIR/original_copy_$stem.json" 2>/dev/null
      desc="API response for $url — captured JSON in the $COLLECTION collection; use when referencing this endpoint's shape/data."
      status="registered"
    fi
  fi

  if [[ "$status" != "registered" ]]; then
    printf '%-46s %-11s %-22s %s\n' "$url" "$action" "$stem" "FAILED(produce md)" >&2
    n_fail=$((n_fail+1)); continue
  fi

  # Build retrieval table.
  if "$BACKEND" "$RETRIEVAL" build "$md" "$lance" >/dev/null 2>&1; then
    printf '%-46s %-11s %-22s %s\n' "$url" "$action" "$stem" "registered" >&2
    n_ok=$((n_ok+1))
    # emit CLAUDE.md bullet on stdout
    printf -- '- `references/%s/%s.md`: %s (retrieval index: `references/%s/%s.lance`)\n' \
      "$COLLECTION" "$stem" "$desc" "$COLLECTION" "$stem"
  else
    printf '%-46s %-11s %-22s %s\n' "$url" "$action" "$stem" "FAILED(build lance)" >&2
    n_fail=$((n_fail+1))
  fi
done

printf '%s\n' "------------------------------------------------------------------------------------------" >&2
printf 'DONE: %d registered, %d skipped, %d failed -> references/%s/\n' "$n_ok" "$n_skip" "$n_fail" "$COLLECTION" >&2
