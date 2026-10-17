#!/usr/bin/env bash
# Build the pinned Madeira Dock host; never launches Steam or runs tests.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SOURCE="${AVPPLAY_MADEIRA_STEAM_SOURCE:-${AVPPLAY_SOURCE_CACHE_ROOT:-$ROOT/third-party}/madeira}"
: "${AVPPLAY_LLVM_MINGW_ROOT:?Set AVPPLAY_LLVM_MINGW_ROOT to the extracted pinned LLVM-MinGW bundle}"
DOCK="$SOURCE/madeira-dock"
EXPECTED=72558e416a390f3669457930f09a389e54f49556
[[ -f "$DOCK/src/main.c" ]] || { echo "Fetch Madeira's pinned madeira-dock submodule first." >&2; exit 1; }
[[ "$(git -C "$DOCK" rev-parse HEAD)" == "$EXPECTED" ]] || { echo "Madeira Dock source revision mismatch." >&2; exit 1; }
git -C "$DOCK" diff --quiet HEAD -- || { echo "Madeira Dock has modified tracked sources." >&2; exit 1; }
WORK="$(mktemp -d "${TMPDIR:-/tmp}/winevision-dock.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
cp -R "$DOCK/src" "$WORK/src"
mkdir -p "$WORK/docs"
cp "$DOCK/README.md" "$WORK/README.md"
cp "$DOCK/docs/HANDOFF.md" "$WORK/docs/HANDOFF.md"
PATCH="$ROOT/windows-vr-tools/patches/madeira-dock/0001-bounded-launch-arguments.patch"
git -C "$WORK" apply --check "$PATCH"
git -C "$WORK" apply "$PATCH"
"$AVPPLAY_LLVM_MINGW_ROOT/bin/x86_64-w64-mingw32-clang" \
    -std=c11 -O2 -Wall -Wextra -Werror -Wno-cast-function-type \
    -static -Wl,--strip-all -Wl,--no-insert-timestamp \
    -o "$WORK/dockhost.exe" "$WORK"/src/*.c -ladvapi32
python3 - "$SOURCE" "$ROOT" "$EXPECTED" "$WORK" "$PATCH" "${AVPPLAY_STEAM_DOCK_OUTPUT:-$ROOT/visionos-windows-vr/Resources/arm64ec-windows}" <<'PY'
import hashlib, json, pathlib, shutil, sys
source, root, revision = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), sys.argv[3]
work, patch, out = map(pathlib.Path, sys.argv[4:7])
out.mkdir(parents=True, exist_ok=True)
shutil.copy2(work / 'dockhost.exe', out / 'dockhost.exe')
shutil.copy2(source / 'app/Madeira/arm64ec-windows/dock-notices.txt', out / 'dock-notices.txt')
(out / 'dock-build.json').write_text(json.dumps({
    'schemaVersion': 1, 'sourceURL': 'https://github.com/willfaust/madeira-dock',
    'revision': revision, 'target': 'x86_64-w64-mingw32', 'testsRun': False,
    'patchesSha256': {patch.name: hashlib.sha256(patch.read_bytes()).hexdigest()},
    'patchedSourcesSha256': {p.relative_to(work).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in sorted((work / 'src').glob('*')) if p.is_file()},
    'patchScope': 'Bounded optional application arguments on initial and retried Valve LaunchApp calls',
    'sha256': hashlib.sha256((out / 'dockhost.exe').read_bytes()).hexdigest()
}, indent=2) + '\n')
PY
