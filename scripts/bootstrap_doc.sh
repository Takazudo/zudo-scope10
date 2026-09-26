#!/usr/bin/env bash
# Use official scaffolding in a NEW directory; never overwrite an existing project.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ $# -ne 1 ]]; then echo 'Usage: bash scripts/bootstrap_doc.sh /path/to/new/scope-doc' >&2; exit 2; fi
DEST="$1"
if [[ -e "$DEST" ]]; then echo "Refusing existing destination: $DEST" >&2; exit 2; fi
command -v npm >/dev/null || { echo 'Node/npm required for official scaffold.' >&2; exit 2; }
npm exec --yes --package=create-zudo-doc@5.27.0 -- create-zudo-doc "$DEST" --yes --lang en --no-install --no-doc-history
cp -R "$ROOT/doc/src/content/docs/." "$DEST/src/content/docs/"
cp -R "$ROOT/doc/public/." "$DEST/public/"
cp "$ROOT/doc/zfb.config.ts" "$DEST/zfb.config.ts"
printf '\nScaffolded %s. Install its dependencies and run its native build locally.\n' "$DEST"
echo 'This copy has generated content. Regenerate in the original handoff repository and copy again when evidence changes.'
