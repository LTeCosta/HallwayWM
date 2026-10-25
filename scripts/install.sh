#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ "${1:-}" == --zip && $# == 1 ]]; then
    exec bash "$project_root/scripts/pack.sh"
fi
if (( $# )); then
    printf 'Usage: %s [--zip]\n' "$0" >&2
    exit 2
fi
uuid="$(python -c 'import json,sys; print(json.load(open(sys.argv[1]))["uuid"])' "$project_root/src/metadata.json")"
destination="${XDG_DATA_HOME:-$HOME/.local/share}/gnome-shell/extensions/$uuid"
for file in extension.js prefs.js windowMenu.js metadata.json icons/deja-window-symbolic.png icons/globe-symbolic.svg schemas/org.gnome.shell.extensions.deja-window.gschema.xml; do
    install -Dm644 "$project_root/src/$file" "$destination/$file"
done
install -m644 "$project_root/LICENSE" "$destination/LICENSE"
glib-compile-schemas --strict "$destination/schemas"
printf 'Installed %s. Sign in again to load changed JavaScript.\n' "$uuid"
