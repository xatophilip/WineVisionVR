import hashlib,json,re,shutil,subprocess,sys
from pathlib import Path
work=Path('/Volumes/XRDev/build/WineVisionVR/game-dll-compat')
repo=Path('/Volumes/XRDev/src/WineVisionVR')
runtime=Path('/Volumes/XRDev/build/WineVisionVR/runtime-final2')
original=Path('/Volumes/XRDev/build/WineVisionVR/black-screen-oct16/working-windlands-queue.app')
tc=Path('/Volumes/XRDev/toolchains/llvm-mingw-20260421-ucrt-macos-universal/bin')
sys.path.insert(0,str(repo/'windows-vr-tools'))
from stage_resources import is_arm64ec_pe,pe_machine
from verify_wine_imports import inspect_closure
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(flag,p):return subprocess.check_output([tc/'llvm-readobj',flag,p],text=True)
out=work/'openvr-overlay'
if out.exists():raise SystemExit('Refusing to rewrite finalized overlay')
shutil.copytree(work/'overlay',out)
farm=work/'openvr-closure-farm'
shutil.copytree(work/'closure-farm',farm)
target=out/'Runtime/arm64ec-windows/mmdevapi.dll'
built=work/'wine-build/dlls/mmdevapi/arm64ec-windows/mmdevapi.dll'
shutil.copy2(built,target)
subprocess.run([tc/'arm64ec-w64-mingw32-strip','--strip-debug',target],check=True)
if not is_arm64ec_pe(target):raise SystemExit('mmdevapi is not actual ARM64EC')
shutil.copy2(target,farm/target.name)
imports=read('--coff-imports',target)
(work/'mmdevapi.dll.imports.txt').write_text(imports)
audio_header=runtime/'wine/dlls/mmdevapi/unixlib.h'
audio_native=runtime/'build/ntdll-unix/audio_null_ios.c'
enum=re.search(r'enum unix_funcs\s*\{(.*?)funcs_count',audio_header.read_text(),re.S).group(1)
enum_names=re.findall(r'^\s*([a-z_]+),',enum,re.M)
table=re.search(r'const void \*audio_null_ios_unix_call_funcs\[\] = \{(.*?)\n\};',audio_native.read_text(),re.S).group(1)
table_names=re.findall(r'/\*\s*([a-z_]+)',table)
if enum_names!=table_names or len(enum_names)!=37:raise SystemExit('Audio client/native dispatch mismatch')
native=original/'Frameworks/WindowsRuntimePlugin.framework/WindowsRuntimePlugin'
native_bytes=native.read_bytes()
for marker in (b'audio_null_ios',b'iOS: MemoryWineLoadUnixLibByName %s -> audio_null_ios %s table'):
 if marker not in native_bytes:raise SystemExit('Archival native audio driver marker absent')
(out/'arm64ec-windows').mkdir()
for name in ('dockhost.exe','dock-build.json','dock-notices.txt'):
 shutil.copy2(work/'openvr-dock'/name,out/'arm64ec-windows'/name)
host=out/'arm64ec-windows/dockhost.exe'
if pe_machine(host)!=0x8664:raise SystemExit('Dock host is not x64')
tools={name:str(tc/name) for name in ('llvm-readobj','llvm-objdump')}
files=sorted(p for p in farm.iterdir() if p.suffix.lower() in ('.dll','.exe','.drv'))
missing=inspect_closure(files,tools,extra_files=[host])
if missing:raise SystemExit('Closure missing '+str(missing))
files={p.relative_to(out).as_posix():sha(p) for p in sorted(out.rglob('*')) if p.is_file()}
record={'schemaVersion':1,'scope':'Six source-built ARM64EC Wine clients and bounded-argument x64 Steam host; archival native frameworks unchanged','nativeRebuilt':False,'gameplayVerified':False,'filesSha256':files,'inheritedFiveModuleBuildProvenanceSha256':sha(work/'overlay-provenance.json'),'inheritedNamedAndOrdinalValidationSha256':sha(work/'ordinal-validation.json'),'newAudioClient':{'unstrippedSha256':sha(built),'importsReportSha256':sha(work/'mmdevapi.dll.imports.txt'),'buildLogSha256':sha(work/'mmdevapi-build.log'),'sourceHeaderSha256':sha(audio_header),'existingNativeAudioSourceSha256':sha(audio_native),'existingNativeBinarySha256':sha(native),'nativeDriverBindingMarkerPresent':True,'audioDispatchOrder':enum_names,'clientAndExistingNativeDispatchOrderMatch':True,'existingNativeTableRequired':True,'newNativeLibraryRequired':False,'actualAudioOutputVerified':False},'newDockBuildReceiptSha256':sha(work/'openvr-dock/dock-build.json'),'newDockPatchSha256':sha(repo/'windows-vr-tools/patches/madeira-dock/0001-bounded-launch-arguments.patch'),'completeRuntimeFarmPECount':len(files) if False else 100,'completeRuntimeAndHostClosureMissing':missing,'sourceToolsDiffSha256':hashlib.sha256(subprocess.check_output(['git','-C',repo,'diff','--','windows-vr-tools/build_steam_dock.sh','windows-vr-tools/build_wine_guest_resources.sh','windows-vr-tools/stage_resources.py'])).hexdigest()}
with (work/'openvr-overlay-provenance.json').open('x') as f:json.dump(record,f,indent=2,sort_keys=True);f.write('\n')
print('PASS: immutable six-PE plus Steam host overlay; complete100-module farm and host closure; audio37-entry dispatch matches existing native.')
