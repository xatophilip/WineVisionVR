#!/usr/bin/env bash
# Build owned x64->i386 startup probes; never run Wine or modify a runtime.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
: "${AVPPLAY_LLVM_MINGW_ROOT:?Set the pinned LLVM-MinGW toolchain directory}"
: "${AVPPLAY_MIXED_CHILD_OUTPUT:?Set a separate external fixture output directory}"
case "$AVPPLAY_MIXED_CHILD_OUTPUT" in /*) ;; *) echo 'Fixture output must be absolute.' >&2; exit 1 ;; esac
SOURCE="$ROOT/visionos-windows-vr/Examples/mixed-architecture-child"
OUTPUT="$AVPPLAY_MIXED_CHILD_OUTPUT"
for target in x86_64 i686; do
    [[ -x "$AVPPLAY_LLVM_MINGW_ROOT/bin/$target-w64-mingw32-clang" ]] || { echo "Missing compiler: $target" >&2; exit 1; }
done
mkdir -p "$OUTPUT/mixed" "$OUTPUT/direct"
"$AVPPLAY_LLVM_MINGW_ROOT/bin/x86_64-w64-mingw32-clang" -O2 -Wall -Wextra -Werror -municode \
    "$SOURCE/parent.c" -o "$OUTPUT/mixed/parent64.exe"
"$AVPPLAY_LLVM_MINGW_ROOT/bin/i686-w64-mingw32-clang" -O2 -Wall -Wextra -Werror -municode \
    "$SOURCE/child.c" -o "$OUTPUT/mixed/child32.exe" -lntdll
cp "$OUTPUT/mixed/child32.exe" "$OUTPUT/direct/child32.exe"
python3 - "$SOURCE" "$OUTPUT" "$AVPPLAY_LLVM_MINGW_ROOT" <<'PY'
import hashlib,json,pathlib,struct,sys
source,output,tools=map(pathlib.Path,sys.argv[1:])
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
manifest=json.loads((source/'manifest.json').read_text())
(output/'mixed/manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
manifest.update(id='winevision.direct-i386-child',title='Direct 32-bit child startup control',
                executableRelativePath='child32.exe',guestArchitecture='x86')
(output/'direct/manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
for relative,machine in [('mixed/parent64.exe',0x8664),('mixed/child32.exe',0x14c),('direct/child32.exe',0x14c)]:
    binary=(output/relative).read_bytes();offset=struct.unpack_from('<I',binary,0x3c)[0]
    assert binary[:2]==b'MZ' and binary[offset:offset+4]==b'PE\0\0'
    assert struct.unpack_from('<H',binary,offset+4)[0]==machine
(output/'build.json').write_text(json.dumps({
    'schemaVersion':1,'fixture':'mixed-architecture-child-v1','executed':False,
    'sourcesSha256':{name:sha(source/name) for name in ('parent.c','child.c','manifest.json')},
    'compilersSha256':{name:sha(tools/'bin'/name) for name in ('x86_64-w64-mingw32-clang','i686-w64-mingw32-clang')},
    'outputsSha256':{str(p.relative_to(output)):sha(p) for d in ('mixed','direct') for p in sorted((output/d).iterdir()) if p.is_file()}
},indent=2)+'\n')
print('Built x64 parent and identical mixed/direct i386 child probes; not executed.')
PY
