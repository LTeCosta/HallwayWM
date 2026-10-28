#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
shell_libdir="${GNOME_SHELL_LIBDIR:-}"
if [[ -z "$shell_libdir" ]]; then
    shell_prefix="$(dirname -- "$(dirname -- "$(command -v gnome-shell)")")"
    package_libdir="$(pkg-config --variable=libdir gobject-introspection-1.0 2>/dev/null || true)"
    shopt -s nullglob
    for candidate in "${package_libdir:-$shell_prefix/lib}/gnome-shell" \
        "$shell_prefix/lib/gnome-shell" "$shell_prefix/lib64/gnome-shell" \
        "$shell_prefix"/lib/*/gnome-shell; do
        if [[ -d "$candidate" ]]; then
            shell_libdir="$candidate"
            break
        fi
    done
fi
if [[ ! -d "$shell_libdir" ]]; then
    printf 'GNOME Shell libraries were not found. Set GNOME_SHELL_LIBDIR to their directory.\n' >&2
    exit 1
fi
export GI_TYPELIB_PATH="$shell_libdir:$shell_libdir/girepository-1.0${GI_TYPELIB_PATH:+:$GI_TYPELIB_PATH}"
export LD_LIBRARY_PATH="$shell_libdir${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

temporary="$(mktemp -d "${TMPDIR:-/tmp}/hallwaywm-preferences.XXXXXXXX")"
trap 'rm -rf -- "$temporary"' EXIT
mkdir -p "$temporary/config" "$temporary/data" "$temporary/cache"
export XDG_CONFIG_HOME="$temporary/config" XDG_DATA_HOME="$temporary/data" XDG_CACHE_HOME="$temporary/cache"
export GSETTINGS_BACKEND=memory GTK_A11Y=none
# Keep GIO, GTK and libadwaita from activating desktop services on the private bus.
export GIO_USE_VFS=local ADW_DISABLE_PORTAL=1
export GDK_DEBUG="${GDK_DEBUG:+$GDK_DEBUG,}no-portals"
dbus-run-session -- gjs -m "$project_root/tests/preferences.mjs" "$@"
