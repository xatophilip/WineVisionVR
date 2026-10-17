#!/usr/bin/env bash
# Build pinned visionOS DXMT and matching ARM64EC/optional i386 graphics DLLs.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
PROFILE="${AVPPLAY_D3D12_PROFILE_SOURCE:-$ROOT/runtime-source-d3d12-experimental}"
MADEIRA="${AVPPLAY_RUNTIME_SOURCE:-$ROOT/runtime-source}"
BUILD_ROOT="${AVPPLAY_D3D12_BUILD_ROOT:-${AVPPLAY_BUILD_ROOT:-}}"
x86_enabled="${AVPPLAY_ENABLE_X86:-0}"
case "$x86_enabled" in 0|1) ;; *) echo "AVPPLAY_ENABLE_X86 must be 0 or 1." >&2; exit 1 ;; esac
export AVPPLAY_ENABLE_X86="$x86_enabled"

[[ "${AVPPLAY_ALLOW_RUNTIME_BUILD:-0}" == "1" && "${AVPPLAY_ENABLE_D3D12:-0}" == "1" ]] || {
    echo "Set AVPPLAY_ALLOW_RUNTIME_BUILD=1 and AVPPLAY_ENABLE_D3D12=1 to build D3D12." >&2; exit 1;
}
[[ -d "$PROFILE/dxmt" && -f "$PROFILE/AVPPLAY_D3D12_SOURCE_PROVENANCE.json" ]] || {
    echo "Prepare the pinned D3D12 profile first: $PROFILE" >&2; exit 1;
}
[[ -f "$PROFILE/AVPPLAY_D3D12_NATIVE_ADAPTATION_RECEIPT.json" ]] || {
    echo "Missing applied-source adaptation receipt; prepare a fresh D3D12 profile." >&2; exit 1;
}
[[ "$BUILD_ROOT" == /* && -d "$BUILD_ROOT" ]] || {
    echo "Set AVPPLAY_D3D12_BUILD_ROOT (or AVPPLAY_BUILD_ROOT) to an existing absolute build directory." >&2; exit 1;
}
for tool in xcrun meson ninja python3 git; do command -v "$tool" >/dev/null 2>&1 || { echo "Missing D3D12 build tool: $tool" >&2; exit 1; }; done
xcrun --sdk xros --show-sdk-path >/dev/null

# Xcode distributes Metal as a separately mounted component. Prefer an
# explicit toolchain root (useful in restricted runners), otherwise resolve
# the installed component's search path from Xcode's component metadata.
if [[ -z "${AVPPLAY_METAL_TOOLCHAIN_ROOT:-}" ]]; then
    COMPONENT_JSON="$(xcodebuild -showComponent MetalToolchain -json 2>/dev/null || true)"
    if [[ -n "$COMPONENT_JSON" ]]; then
        COMPONENT_SEARCH_PATH="$(python3 -c 'import json,sys
def walk(value):
    if isinstance(value, dict):
        path=value.get("toolchainSearchPath")
        if isinstance(path, str): return path
        for child in value.values():
            found=walk(child)
            if found: return found
    elif isinstance(value, list):
        for child in value:
            found=walk(child)
            if found: return found
    return ""
try: print(walk(json.loads(sys.stdin.read())))
except Exception: print("")' <<< "$COMPONENT_JSON")"
        if [[ -n "$COMPONENT_SEARCH_PATH" ]]; then
            AVPPLAY_METAL_TOOLCHAIN_ROOT="$COMPONENT_SEARCH_PATH/Metal.xctoolchain"
        fi
    fi
fi
if [[ -n "${AVPPLAY_METAL_TOOLCHAIN_ROOT:-}" && ! -x "$AVPPLAY_METAL_TOOLCHAIN_ROOT/usr/bin/metal" && -x "$AVPPLAY_METAL_TOOLCHAIN_ROOT/Metal.xctoolchain/usr/bin/metal" ]]; then
    AVPPLAY_METAL_TOOLCHAIN_ROOT="$AVPPLAY_METAL_TOOLCHAIN_ROOT/Metal.xctoolchain"
fi
if [[ -n "${AVPPLAY_METAL_TOOLCHAIN_ROOT:-}" ]]; then
    [[ -x "$AVPPLAY_METAL_TOOLCHAIN_ROOT/usr/bin/metal" && -x "$AVPPLAY_METAL_TOOLCHAIN_ROOT/usr/bin/metallib" ]] || {
        echo "Metal Toolchain root lacks usr/bin/metal and usr/bin/metallib: $AVPPLAY_METAL_TOOLCHAIN_ROOT" >&2; exit 1;
    }
    export PATH="$AVPPLAY_METAL_TOOLCHAIN_ROOT/usr/bin:$PATH"
else
    echo "Set AVPPLAY_METAL_TOOLCHAIN_ROOT or allow xcodebuild -showComponent MetalToolchain to resolve the installed component." >&2
    exit 1
fi

NATIVE_SOURCE="$PROFILE/dxmt"
NATIVE_BUILD="$BUILD_ROOT/dxmt-d3d12-meson"
NATIVE_FILE="$BUILD_ROOT/dxmt-d3d12-xros-native.ini"
LLVM_SOURCE="$MADEIRA/toolchains/llvm-project"
LLVM_BUILD="$MADEIRA/toolchains/llvm-ios-build"
WINE_BUILD="$MADEIRA/wine/build-arm64ec"
GUEST_FARM="$PROFILE/app/Madeira/arm64ec-windows"
NATIVE_ARCHIVE="$PROFILE/app/Madeira/libdxmt_d3d12_combined.a"
BUILD_RECEIPT="$PROFILE/AVPPLAY_D3D12_BUILD_RECEIPT.json"

[[ -d "$LLVM_SOURCE/llvm" && -d "$LLVM_BUILD/include" && -d "$LLVM_BUILD/lib" ]] || {
    echo "Build the locked visionOS LLVM dependency with prepare_llvm.sh build first." >&2; exit 1;
}
[[ -d "$WINE_BUILD" ]] || { echo "Missing pinned Wine ARM64EC build tree: $WINE_BUILD" >&2; exit 1; }
[[ -f "$NATIVE_SOURCE/build-arm64ec.txt" ]] || {
    echo "Pinned DXMT source lacks its ARM64EC Meson cross file: $NATIVE_SOURCE/build-arm64ec.txt" >&2; exit 1;
}
[[ -n "${AVPPLAY_LLVM_MINGW_ROOT:-}" && "$AVPPLAY_LLVM_MINGW_ROOT" == /* ]] || {
    echo "Set AVPPLAY_LLVM_MINGW_ROOT to the pinned LLVM-MinGW bundle root." >&2; exit 1;
}
for tool in arm64ec-w64-mingw32-gcc arm64ec-w64-mingw32-g++ arm64ec-w64-mingw32-ar arm64ec-w64-mingw32-strip arm64ec-w64-mingw32-windres; do
    [[ -x "$AVPPLAY_LLVM_MINGW_ROOT/bin/$tool" ]] || { echo "LLVM-MinGW lacks $tool." >&2; exit 1; }
done
[[ ! -e "$NATIVE_BUILD" && ! -e "$NATIVE_FILE" && ! -e "$NATIVE_ARCHIVE" && ! -e "$BUILD_RECEIPT" ]] || {
    echo "D3D12 build output exists; choose a fresh AVPPLAY_D3D12_BUILD_ROOT and profile. No existing archive is reused." >&2; exit 1;
}
for dll in d3d11.dll d3d12.dll dxgi.dll winemetal.dll; do
    [[ ! -e "$GUEST_FARM/$dll" ]] || { echo "Refusing to replace existing profile DLL: $GUEST_FARM/$dll" >&2; exit 1; }
done
if [[ "$x86_enabled" == 1 ]]; then
    [[ -f "$MADEIRA/wine/build-i386/Makefile" ]] || {
        echo "Build the matching Wine i386 base before modern DXMT (AVPPLAY_I386_BUILD_PHASE=base)." >&2; exit 1;
    }
    [[ ! -e "$BUILD_ROOT/dxmt-d3d12-i386" && ! -e "$BUILD_ROOT/dxmt-d3d12-i386.ini" ]] || {
        echo "Modern i386 DXMT outputs exist; choose a fresh build root/profile." >&2; exit 1;
    }
    for tool in i686-w64-mingw32-clang i686-w64-mingw32-clang++ i686-w64-mingw32-ar i686-w64-mingw32-strip i686-w64-mingw32-windres i686-w64-mingw32-dlltool; do
        [[ -x "$AVPPLAY_LLVM_MINGW_ROOT/bin/$tool" ]] || { echo "LLVM-MinGW lacks $tool." >&2; exit 1; }
    done
fi
python3 - "$ROOT" "$PROFILE" <<'PY'
import hashlib, json, pathlib, sys
root, profile = map(pathlib.Path, sys.argv[1:])
source_path=profile/"AVPPLAY_D3D12_SOURCE_PROVENANCE.json"
adaptation_path=profile/"AVPPLAY_D3D12_NATIVE_ADAPTATION_RECEIPT.json"
source=json.loads(source_path.read_text(encoding="utf-8")); adaptation=json.loads(adaptation_path.read_text(encoding="utf-8"))
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
if source.get("profileId") != "dxmt-d3d12-experimental-e94c312f5c054263acf261cfa109edf13e757587": raise SystemExit("Unexpected D3D12 source profile pin.")
if adaptation.get("sourceProvenanceSha256") != sha(source_path) or adaptation.get("nativeSourceTreeSha256") != source.get("nativeSourceTreeSha256"): raise SystemExit("D3D12 native adaptation receipt is stale.")
for name, expected in source.get("integrationInputsSha256", {}).items():
    if sha(root/name) != expected: raise SystemExit(f"D3D12 profile input changed after preparation: {name}")
h=hashlib.sha256()
for path in sorted((profile/"dxmt").rglob("*")):
    if not path.is_file() or ".git" in path.parts: continue
    rel=path.relative_to(profile/"dxmt").as_posix().encode(); h.update(len(rel).to_bytes(8,"big")); h.update(rel); h.update(path.stat().st_size.to_bytes(8,"big"))
    with path.open("rb") as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b""): h.update(chunk)
if h.hexdigest() != source.get("nativeSourceTreeSha256"): raise SystemExit("D3D12 source tree changed after preparation.")
PY
mkdir -p "$BUILD_ROOT" "$GUEST_FARM" "$PROFILE/app/Madeira" "$BUILD_ROOT/d3d12-generated"
export PATH="$AVPPLAY_LLVM_MINGW_ROOT/bin:$PATH"

cat > "$NATIVE_FILE" <<MESON
[binaries]
c = ['xcrun', 'clang']
cpp = ['xcrun', 'clang++']
ar = ['xcrun', '--sdk', 'xros', 'ar']
strip = ['xcrun', '--sdk', 'xros', 'strip']

[built-in options]
c_args = []
cpp_args = ['-I$BUILD_ROOT/d3d12-generated']
MESON

# One Meson graph gives the guest PE targets the pinned LLVM-MinGW cross-file
# and gives native targets the xros compiler. Source lists and object commands
# are discovered from this revision's own Meson introspection/compile database.
meson setup "$NATIVE_BUILD" "$NATIVE_SOURCE" \
    --cross-file="$NATIVE_SOURCE/build-arm64ec.txt" \
    --native-file="$NATIVE_FILE" \
    -Dbuildtype=release \
    -Dwine_build_path="$WINE_BUILD" \
    -Dnative_llvm_path="$LLVM_BUILD" \
    -Dnative_llvm_source_path="$LLVM_SOURCE/llvm" \
    -Denable_d3d12=true \
    -Dvisionos_native=true \
    -Dbuild_airconv_for_windows=false \
    -Denable_tests=false

python3 - "$NATIVE_BUILD" "$NATIVE_SOURCE" "$NATIVE_ARCHIVE" "$GUEST_FARM" "$LLVM_BUILD" "$BUILD_RECEIPT" "$PROFILE" "$MADEIRA" "$ROOT" <<'PY'
import hashlib, json, os, pathlib, shlex, shutil, subprocess, sys
build, source, archive, guest, llvm_build, receipt_path, profile, madeira, root = map(pathlib.Path, sys.argv[1:])

build_jobs = os.environ.get("AVPPLAY_BUILD_JOBS", "4")
if not build_jobs.isdigit() or int(build_jobs) < 1:
    raise SystemExit("AVPPLAY_BUILD_JOBS must be a positive integer.")
def run(args, **kwargs):
    if args and args[0] == "ninja": args = [args[0], "-j" + build_jobs, *args[1:]]
    subprocess.run(args, check=True, **kwargs)
def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""): h.update(chunk)
    return h.hexdigest()
def regular(path, label):
    if path.is_symlink() or not path.is_file() or not path.stat().st_size: raise SystemExit(f"Missing/nonempty {label}: {path}")
def target_outputs(target):
    values = []
    for key in ("filename", "outputs"):
        value = target.get(key, [])
        values.extend(value if isinstance(value, list) else [value])
    return [str(v) for v in values if v]
def target_sources(target):
    values = []
    for group in target.get("target_sources", []):
        values.extend(group.get("sources", []))
    paths = []
    for item in values:
        path = pathlib.Path(item)
        if not path.is_absolute(): path = source / path
        paths.append(path.resolve())
    return paths
def discover_targets():
    raw = subprocess.check_output(["meson", "introspect", "--targets", str(build)], text=True)
    targets = json.loads(raw)
    def has_output(target, basename):
        return any(pathlib.PurePath(value).name == basename for value in target_outputs(target))
    airconv = [t for t in targets if t.get("type") == "static library" and has_output(t, "libairconv.a")]
    parser = [t for t in targets if t.get("type") == "static library" and has_output(t, "libDXBCParserNative.a")]
    if len(airconv) != 1 or len(parser) != 1:
        raise SystemExit("Meson did not expose exactly one native libairconv.a and libDXBCParserNative.a for this profile.")
    unix_targets = [t for t in targets if any("/src/winemetal/unix/" in p.as_posix() for p in target_sources(t))]
    unix_sources = sorted({p for t in unix_targets for p in target_sources(t) if p.is_file()})
    if not unix_sources:
        raise SystemExit("Meson introspection found no winemetal Unix source list in the configured profile.")
    guest_targets = {}
    for dll, source_dir in (("d3d11.dll", "/src/d3d11/"), ("d3d12.dll", "/src/d3d12/"),
                            ("dxgi.dll", "/src/dxgi/"), ("winemetal.dll", "/src/winemetal/")):
        found = [t for t in targets if has_output(t, dll) and any(source_dir in p.as_posix() for p in target_sources(t))]
        if len(found) != 1:
            raise SystemExit(f"Meson did not expose exactly one matching guest target for {dll}.")
        guest_targets[dll] = found[0]
    return targets, airconv[0], parser[0], unix_sources, guest_targets

targets, airconv_target, parser_target, unix_sources, guest_targets = discover_targets()
# Generator outputs are not standalone Meson introspection targets. Read the
# actual Ninja graph and build its exact production-metallib output rule.
ninja_targets=subprocess.check_output(["ninja","-C",str(build),"-t","targets","all"],text=True)
references=[]
for row in ninja_targets.splitlines():
    name=row.rsplit(": ",1)[0]
    if pathlib.PurePath(name).name == "dxmt_command.metallib": references.append(name)
if len(references) != 1: raise SystemExit("Expected one xros production command metallib rule in the pinned graph.")
run(["ninja","-C",str(build),references[0]])
metallib_reference=pathlib.Path(references[0])
if not metallib_reference.is_absolute(): metallib_reference=build/metallib_reference
regular(metallib_reference, "xros-compiled metallib reference")
platform_header = build.parent / "d3d12-generated/wvr_metallib_platform.h"
sdk_version = subprocess.check_output(["xcrun", "--sdk", "xros", "--show-sdk-version"], text=True).strip()
run([sys.executable, str(root/"windows-vr-openxr/native-d3d12/generate_metallib_platform.py"),
     "--reference", str(metallib_reference), "--sdk-version", sdk_version,
     "--output", str(platform_header)])
regular(platform_header, "generated xros metallib metadata header")
# Build the two actual Meson static targets; generators run from this graph.
for target in (airconv_target, parser_target):
    outputs=target_outputs(target)
    if not outputs: raise SystemExit("Native Meson target has no output.")
    output=pathlib.Path(outputs[0]); output=output if output.is_absolute() else build/output
    run(["ninja", "-C", str(build), output.resolve().relative_to(build.resolve()).as_posix()])

compile_db = json.loads((build / "compile_commands.json").read_text(encoding="utf-8"))
needed = {p.resolve() for p in unix_sources}
object_paths = []
compiled_sources = set()
for entry in compile_db:
    source_file = pathlib.Path(entry["file"])
    if not source_file.is_absolute(): source_file = pathlib.Path(entry["directory"]) / source_file
    source_file = source_file.resolve()
    if source_file not in needed: continue
    argv = entry.get("arguments") or shlex.split(entry["command"])
    if "arm64-apple-xros27.0" not in " ".join(argv): continue
    run(argv, cwd=entry["directory"])
    try: out = pathlib.Path(argv[argv.index("-o") + 1])
    except (ValueError, IndexError): raise SystemExit(f"Meson compiler command has no output object for {source_file}.")
    if not out.is_absolute(): out = pathlib.Path(entry["directory"]) / out
    regular(out, "native winemetal object")
    object_paths.append(out); compiled_sources.add(source_file)
if compiled_sources != needed:
    missing = sorted(str(p) for p in needed - compiled_sources)
    raise SystemExit("Missing xros Meson compile commands for native winemetal sources: " + ", ".join(missing))

def output_path(target, basename, graph_build=build):
    candidates = [pathlib.Path(value) for value in target_outputs(target) if pathlib.PurePath(value).name == basename]
    if len(candidates) != 1: raise SystemExit(f"Meson target {target.get('name')} has no unique {basename} output.")
    path = candidates[0]
    return path if path.is_absolute() else graph_build / path
archives = [output_path(airconv_target, "libairconv.a"), output_path(parser_target, "libDXBCParserNative.a")]
for path in archives: regular(path, "native Meson compiler archive")
llvm_archives = sorted((llvm_build / "lib").glob("*.a"))
if not llvm_archives: raise SystemExit(f"No archives in the locked visionOS LLVM build: {llvm_build / 'lib'}")
archive.parent.mkdir(parents=True, exist_ok=True)
subprocess.run(["xcrun", "--sdk", "xros", "libtool", "-static", "-o", str(archive),
                *map(str, object_paths), *map(str, archives), *map(str, llvm_archives)], check=True)
regular(archive, "combined native DXMT archive")

# Build all four PE modules from this exact modern DXMT Meson graph.
for dll in ("d3d11.dll", "d3d12.dll", "dxgi.dll", "winemetal.dll"):
    output=output_path(guest_targets[dll],dll)
    run(["ninja", "-C", str(build), output.resolve().relative_to(build.resolve()).as_posix()])
    post=[t for t in targets if any(pathlib.PurePath(v).name == dll+".postproc" for v in target_outputs(t))]
    if len(post) != 1: raise SystemExit(f"Missing unique Wine builtin postprocessor for {dll}.")
    output=output_path(post[0],dll+".postproc")
    run(["ninja", "-C", str(build), output.resolve().relative_to(build.resolve()).as_posix()])
for dll, target in guest_targets.items():
    source_file = output_path(target, dll)
    regular(source_file, f"ARM64EC {dll}")
    shutil.copy2(source_file, guest / dll)
    regular(guest / dll, f"copied ARM64EC {dll}")

# i386 graphics use a second PE graph over the exact same patched modern
# source. Its Wine import libraries come only from this profile's i386 base.
# Native shaders/Unix code are built once by the ARM64EC graph above.
x86_enabled = os.environ.get("AVPPLAY_ENABLE_X86", "0") == "1"
x86_guest = profile / "app/Madeira/i386-windows"
x86_graph = None
source_receipt_path = profile / "AVPPLAY_D3D12_SOURCE_PROVENANCE.json"
source_receipt = json.loads(source_receipt_path.read_text(encoding="utf-8"))
if x86_enabled:
    if source_receipt.get("wow64TransportABI") != 1 or source_receipt.get("wow64DispatchTableExpectedEntryCount") != 148:
        raise SystemExit("Modern i386 graphics require source-bound WOW64 ABI 1 and all 148 dispatch slots.")
    graph = build.parent / "dxmt-d3d12-i386"
    cross_file = build.parent / "dxmt-d3d12-i386.ini"
    wine_i386 = madeira / "wine/build-i386"
    if graph.exists() or cross_file.exists():
        raise SystemExit("Refusing to reuse an existing modern i386 graphics graph.")
    regular(wine_i386 / "Makefile", "same-profile Wine i386 graph")
    mingw = pathlib.Path(os.environ["AVPPLAY_LLVM_MINGW_ROOT"])
    binaries = {"c": "clang", "cpp": "clang++", "ar": "ar", "strip": "strip",
                "windres": "windres", "dlltool": "dlltool"}
    cross_file.write_text("[binaries]\n" + "".join(
        f"{key} = {str(mingw / 'bin' / ('i686-w64-mingw32-' + value))!r}\n"
        for key, value in binaries.items()) +
        "\n[properties]\nneeds_exe_wrapper = true\n\n[host_machine]\n"
        "system = 'windows'\ncpu_family = 'x86'\ncpu = 'i686'\nendian = 'little'\n")
    run(["meson", "setup", str(graph), str(source), "--cross-file=" + str(cross_file),
         "--native-file=" + str(build.parent / "dxmt-d3d12-xros-native.ini"),
         "-Dbuildtype=release", "-Dwine_builtin_dll=true", "-Dwine_build_path=" + str(wine_i386),
         "-Dnative_llvm_path=" + str(llvm_build),
         "-Dnative_llvm_source_path=" + str(madeira / "toolchains/llvm-project/llvm"),
         "-Denable_d3d12=true", "-Dvisionos_native=true", "-Dbuild_airconv_for_windows=false",
         "-Denable_tests=false"])
    graph_targets = json.loads(subprocess.check_output(
        ["meson", "introspect", "--targets", str(graph)], text=True))
    x86_outputs = {}
    for name, directory in (("d3d11.dll", "/src/d3d11/"), ("d3d12.dll", "/src/d3d12/"),
                            ("dxgi.dll", "/src/dxgi/"), ("winemetal.dll", "/src/winemetal/")):
        selected = [target for target in graph_targets
                    if any(pathlib.PurePath(value).name == name for value in target_outputs(target))
                    and any(directory in path.as_posix() for path in target_sources(target))]
        post = [target for target in graph_targets
                if any(pathlib.PurePath(value).name == name + ".postproc" for value in target_outputs(target))]
        if len(selected) != 1 or len(post) != 1:
            raise SystemExit(f"Modern i386 graph lacks unique DLL/postprocessing targets for {name}.")
        for target, basename in ((selected[0], name), (post[0], name + ".postproc")):
            output = output_path(target, basename, graph)
            run(["ninja", "-C", str(graph), output.resolve().relative_to(graph.resolve()).as_posix()])
        x86_outputs[name] = output_path(selected[0], name, graph)
    sys.path.insert(0, str(root / "windows-vr-tools"))
    from stage_resources import pe_machine
    for name, output in x86_outputs.items():
        regular(output, "fresh modern i386 " + name)
        if pe_machine(output) != 0x14c:
            raise SystemExit(f"Modern i386 graphics target has the wrong architecture: {output}")
        import_dump = subprocess.check_output([str(mingw / "bin/llvm-readobj"), "--coff-imports", str(output)], text=True)
        dependencies = {row.strip().split(": ", 1)[1].casefold() for row in import_dump.splitlines()
                        if row.strip().startswith("Name: ")}
        forbidden = dependencies & {"libc++.dll", "libc++abi.dll", "libunwind.dll", "libstdc++-6.dll"}
        if forbidden:
            raise SystemExit(f"Modern i386 {name} must embed its C++ runtime: {sorted(forbidden)}")
    x86_guest.mkdir(parents=True, exist_ok=True)
    for name, output in x86_outputs.items():
        # Wine's base phase may provide fallback d3d12.dll. Replace it only
        # with this freshly compiled same-profile modern graphics closure.
        shutil.copy2(output, x86_guest / name)
    x86_graph = {"buildDirectory": str(graph), "wineBuildDirectory": str(wine_i386),
                 "wineMakefileSha256": sha(wine_i386 / "Makefile"),
                 "crossFileSha256": sha(cross_file), "sharedCXXImportsRejected": True}

# The profile's exported table names/count are checked from the artifact, not
# copied from a declarative readiness flag. These are symbol reads, not execution.
nm = subprocess.check_output(["xcrun", "--sdk", "xros", "nm", "-gU", str(archive)], text=True)
required_symbols = ("_dxmt_winemetal_unix_call_funcs", "_dxmt_winemetal_unix_call_wow64_funcs",
                    "_wvr_dxmt_d3d12_unix_call_count_v1", "_wvr_dxmt_d3d12_transport_abi_v1")
if source_receipt.get("wow64TransportABI") == 1:
    if source_receipt.get("wow64DispatchTableExpectedEntryCount") != 148:
        raise SystemExit("Modern WOW64 source dispatch count must be 148.")
    required_symbols += ("_wvr_dxmt_wow64_transport_abi_v1", "_wvr_dxmt_wow64_unix_call_count_v1")
elif source_receipt.get("wow64TransportABI") is not None:
    raise SystemExit("Unsupported modern WOW64 transport ABI.")
missing_symbols = [symbol for symbol in required_symbols if symbol not in nm]
if missing_symbols: raise SystemExit("Native archive is missing dispatch exports: " + ", ".join(missing_symbols))
sys.path.insert(0, str(root / "windows-vr-tools"))
from stage_resources import is_arm64ec_pe
 # This receipt covers DXMT's four executable graphics modules. Wine's
 # broader farm also contains data-only API-set DLLs without CHPE code.
for name in ("d3d11.dll", "d3d12.dll", "dxgi.dll", "winemetal.dll"):
    dll = guest / name
    if not is_arm64ec_pe(dll): raise SystemExit(f"Expected ARM64EC PE or valid AMD64+CHPE builtin: {dll}")

source_receipt_path = profile / "AVPPLAY_D3D12_SOURCE_PROVENANCE.json"
adaptation_path = profile / "AVPPLAY_D3D12_NATIVE_ADAPTATION_RECEIPT.json"
source_receipt = json.loads(source_receipt_path.read_text(encoding="utf-8"))
adaptation = json.loads(adaptation_path.read_text(encoding="utf-8"))
if source_receipt.get("unixCallTable", {}).get("expectedEntryCount") != 148:
    raise SystemExit("D3D12 profile dispatch table count does not match the native loader's 148-entry contract.")
def profile_source_hash(directory):
    h = hashlib.sha256()
    for path in sorted(directory.rglob("*")):
        if not path.is_file() or ".git" in path.parts: continue
        rel = path.relative_to(directory).as_posix().encode(); h.update(len(rel).to_bytes(8, "big")); h.update(rel)
        h.update(path.stat().st_size.to_bytes(8, "big"))
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""): h.update(chunk)
    return h.hexdigest()
actual_tree_hash = profile_source_hash(profile / "dxmt")
if actual_tree_hash != source_receipt.get("nativeSourceTreeSha256") or actual_tree_hash != adaptation.get("nativeSourceTreeSha256"):
    raise SystemExit("D3D12 source tree changed after the source/adaptation receipts were prepared.")
llvm_lock = json.loads((root / "windows-vr-tools/llvm.lock.json").read_text(encoding="utf-8"))
llvm_source = madeira / "toolchains/llvm-project"
actual_llvm_revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=llvm_source, text=True).strip()
if actual_llvm_revision != llvm_lock["revision"]:
    raise SystemExit("LLVM source revision does not match windows-vr-tools/llvm.lock.json.")
llvm_mingw_root = pathlib.Path(os.environ["AVPPLAY_LLVM_MINGW_ROOT"])
llvm_mingw_tools = ("arm64ec-w64-mingw32-gcc", "arm64ec-w64-mingw32-g++", "arm64ec-w64-mingw32-ar", "arm64ec-w64-mingw32-strip", "arm64ec-w64-mingw32-windres")
if x86_enabled:
    llvm_mingw_tools += tuple("i686-w64-mingw32-" + name for name in ("clang", "clang++", "ar", "strip", "windres", "dlltool"))
llvm_mingw_hashes = {name: sha(llvm_mingw_root / "bin" / name) for name in llvm_mingw_tools}
madeira_lock = json.loads((root / "windows-vr-tools/sources.lock.json").read_text(encoding="utf-8"))
madeira_revision = next(s["revision"] for s in madeira_lock["sources"] if s["name"] == "madeira")
artifacts = {"native/libdxmt_d3d12_combined.a": sha(archive)}
for dll in ("d3d11.dll", "d3d12.dll", "dxgi.dll", "winemetal.dll"):
    artifacts[f"guest/arm64ec-windows/{dll}"] = sha(guest / dll)
if x86_enabled:
    for dll in ("d3d11.dll", "d3d12.dll", "dxgi.dll", "winemetal.dll"):
        artifacts[f"guest/i386-windows/{dll}"] = sha(x86_guest / dll)
receipt = {
 "schemaVersion": 1, "profileId": source_receipt["profileId"],
 "sourceProvenanceSha256": sha(source_receipt_path), "nativeAdaptationReceiptSha256": sha(adaptation_path),
 "nativeSourceTreeSha256": actual_tree_hash, "sourceRevision": source_receipt["sourceRevision"],
 "madeiraRevision": madeira_revision, "llvmSourceRevision": actual_llvm_revision,
 "llvmTarget": llvm_lock["target"], "llvmMingwRelease": "20260421", "llvmMingwExpectedReleaseArchiveSha256": "bd85a3975723815cef28dbbd2ca2cb0c926f6b348a12a0453f39f7af273cb3f7", "llvmMingwToolArtifactsSha256": llvm_mingw_hashes,
 "xrosMetallibReferenceSha256": sha(metallib_reference), "xrosMetallibPlatformHeaderSha256": sha(platform_header),
 "nativeArchive": "libdxmt_d3d12_combined.a",
 "unixCallTable": source_receipt["unixCallTable"], "dispatchTableExpectedEntryCount": source_receipt["unixCallTable"]["expectedEntryCount"], "exportedDispatchSymbols": list(required_symbols),
 "transportABI": source_receipt["transportABI"], "artifactsSha256": artifacts,
 "shaderPlatformHeaderSha256": sha(platform_header),
 "buildCommandsCompleted": ["Meson native DXMT targets", "xros archive link", "Meson ARM64EC d3d11/d3d12/dxgi/winemetal targets"],
}
if source_receipt.get("wow64TransportABI") == 1:
    receipt.update(wow64TransportABI=1, wow64DispatchTableExpectedEntryCount=148)
if x86_enabled:
    receipt["i386GraphicsBuild"] = x86_graph
    receipt["buildCommandsCompleted"].append("Meson i386 d3d11/d3d12/dxgi/winemetal targets and Wine builtin postprocessors")
receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

echo "Built receipt-backed modern DXMT native archive and guest graphics closure (x86=$x86_enabled). No Wine guest was run."
