#!/usr/bin/env bash
# Build the app-owned Windows/GDI desktop smoke test. Does not run Wine.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
: "${AVPPLAY_LLVM_MINGW_ROOT:?Set the pinned LLVM-MinGW toolchain directory}"
ARCH="${AVPPLAY_DESKTOP_DEMO_ARCH:-x64}"
case "$ARCH" in
    x64) TRIPLE=x86_64-w64-mingw32; RESOURCE_NAME=DesktopDemo ;;
    x86) TRIPLE=i686-w64-mingw32; RESOURCE_NAME=DesktopDemoX86 ;;
    *) echo "AVPPLAY_DESKTOP_DEMO_ARCH must be x64 or x86." >&2; exit 1 ;;
esac
COMPILER="$AVPPLAY_LLVM_MINGW_ROOT/bin/$TRIPLE-clang"
[[ -x "$COMPILER" ]] || { echo "Missing Windows compiler: $COMPILER" >&2; exit 1; }
SOURCE="$ROOT/visionos-windows-vr/Examples/desktop-demo"
OUTPUT="${AVPPLAY_DESKTOP_DEMO_OUTPUT:-$ROOT/visionos-windows-vr/Resources/$RESOURCE_NAME}"
mkdir -p "$OUTPUT"
"$COMPILER" -O2 -Wall -Wextra -Werror -municode -mwindows \
    "$SOURCE/main.c" -o "$OUTPUT/desktop-demo.exe" -luser32 -lgdi32
python3 - "$SOURCE" "$OUTPUT" "$ARCH" "$TRIPLE" "$AVPPLAY_LLVM_MINGW_ROOT" <<'PY'
import hashlib, json, pathlib, struct, sys
source, output = map(pathlib.Path, sys.argv[1:3])
architecture, triple = sys.argv[3:5]
toolchain = pathlib.Path(sys.argv[5])
manifest = json.loads((source / 'manifest.json').read_text())
if architecture == 'x86':
    manifest.update(id='winevision.desktop-demo-x86', title='32-bit Windows desktop test', guestArchitecture='x86')
(output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
binary = (output / 'desktop-demo.exe').read_bytes()
assert binary[:2] == b'MZ'
offset = struct.unpack_from('<I', binary, 0x3c)[0]
assert binary[offset:offset+4] == b'PE\0\0'
assert struct.unpack_from('<H', binary, offset+4)[0] == (0x14c if architecture == 'x86' else 0x8664)
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
(output / 'build.json').write_text(json.dumps({
    'target': triple, 'architecture': architecture, 'presentation': 'desktop',
    'sourceSha256': sha(source / 'main.c'),
    'compilerSha256': sha(toolchain / ('bin/' + triple + '-clang')),
    'manifestSha256': sha(output / 'manifest.json'),
    'executableSha256': sha(output / 'desktop-demo.exe'),
    'executed': False
}, indent=2) + '\n')
print(f'Built {architecture} Windows desktop test: {output / "desktop-demo.exe"}; not executed.')
PY
