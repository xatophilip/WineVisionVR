#!/usr/bin/env bash
# Build only the app-owned, Steam-free x64 OpenVR/D3D11 scene. Never executes it.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
: "${AVPPLAY_LLVM_MINGW_ROOT:?Set the pinned LLVM-MinGW toolchain directory}"
COMPILER="$AVPPLAY_LLVM_MINGW_ROOT/bin/x86_64-w64-mingw32-clang"
SOURCE="$ROOT/visionos-windows-vr/Examples/vr-smoke"
OUTPUT="${AVPPLAY_VR_SMOKE_OUTPUT:-$ROOT/visionos-windows-vr/Resources/VRSmoke}"
[[ -x "$COMPILER" ]] || { echo "Missing pinned compiler: $COMPILER" >&2; exit 1; }
mkdir -p "$OUTPUT"
"$COMPILER" -O2 -Wall -Wextra -Werror -municode -mwindows \
    -isystem "$ROOT/third-party/openvr/headers" "$SOURCE/main.c" \
    -o "$OUTPUT/vr-smoke.exe" -ld3d11 -ld3dcompiler -luser32 -ladvapi32
cp "$SOURCE/manifest.json" "$OUTPUT/manifest.json"
python3 - "$SOURCE" "$OUTPUT" "$ROOT" "$AVPPLAY_LLVM_MINGW_ROOT" <<'PY'
import hashlib,json,pathlib,struct,subprocess,sys
source,output,root,toolchain=map(pathlib.Path,sys.argv[1:])
binary=(output/'vr-smoke.exe').read_bytes()
assert binary[:2]==b'MZ'
offset=struct.unpack_from('<I',binary,0x3c)[0]
assert binary[offset:offset+4]==b'PE\0\0' and struct.unpack_from('<H',binary,offset+4)[0]==0x8664
inspection=subprocess.check_output([str(toolchain/'bin/llvm-readobj'),'--coff-imports',str(output/'vr-smoke.exe')],text=True)
(output/'imports.txt').write_text(inspection)
imports=[line.strip().split(': ',1)[1] for line in inspection.splitlines() if line.strip().startswith('Name: ')]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
(output/'build.json').write_text(json.dumps({'target':'x86_64-w64-mingw32','presentation':'immersiveVR','sourceSha256':sha(source/'main.c'),'manifestSha256':sha(output/'manifest.json'),'executableSha256':sha(output/'vr-smoke.exe'),'openvrHeaderSha256':sha(root/'third-party/openvr/headers/openvr_capi.h'),'compilerSha256':sha(toolchain/'bin/x86_64-w64-mingw32-clang'),'imports':imports,'executed':False},indent=2)+'\n')
print(f'Built app-owned x64 VR test scene: {output / "vr-smoke.exe"}; not executed.')
PY
