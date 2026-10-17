import hashlib,json,os,re,shutil,subprocess,sys
from pathlib import Path
REPO=Path('/Volumes/XRDev/src/WineVisionVR')
WORK=Path('/Volumes/XRDev/build/WineVisionVR/game-dll-compat')
SOURCE=Path('/Volumes/XRDev/build/WineVisionVR/runtime-final2/wine')
ORIGINAL=Path('/Volumes/XRDev/build/WineVisionVR/black-screen-oct16/working-windlands-queue.app')
TC=Path('/Volumes/XRDev/toolchains/llvm-mingw-20260421-ucrt-macos-universal/bin')
sys.path.insert(0,str(REPO/'windows-vr-tools'))
from stage_resources import is_arm64ec_pe
from verify_wine_imports import inspect_closure,dependencies
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def output(*args):return subprocess.check_output(list(map(str,args)),text=True)
def write(p,d):p.write_text(json.dumps(d,indent=2,sort_keys=True)+'\n')
modules=('dwmapi','wsock32','avrt','vcruntime140','msvcp140')
overlay=WORK/'overlay/Runtime/arm64ec-windows'
farm=WORK/'closure-farm'
if overlay.exists() or farm.exists():raise SystemExit('Refusing existing immutable overlay; create a new build directory.')
overlay.mkdir(parents=True)
shutil.copytree(ORIGINAL/'Runtime/arm64ec-windows',farm)
records={}
for module in modules:
 name=module+'.dll';target=overlay/name
 built=WORK/'wine-build/dlls'/module/'arm64ec-windows'/name
 shutil.copy2(built,target)
 subprocess.run([TC/'arm64ec-w64-mingw32-strip','--strip-debug',target],check=True)
 if not is_arm64ec_pe(target):raise SystemExit('Invalid actual ARM64EC PE: '+name)
 imports=output(TC/'llvm-readobj','--coff-imports',target)
 if re.search(r'Symbol: .*(__wine_unix_call|unixlib)',imports):raise SystemExit('Unexpected native Unix bridge: '+name)
 exported=output(TC/'llvm-readobj','--coff-exports',target)
 (WORK/(name+'.imports.txt')).write_text(imports)
 (WORK/(name+'.exports.txt')).write_text(exported)
 shutil.copy2(target,farm/name)
 records['Runtime/arm64ec-windows/'+name]={'sha256':sha(target),'bytes':target.stat().st_size,'unstrippedSha256':sha(built),'isActualARM64EC':True,'directImports':sorted(set(re.findall(r'^  Name: (.+)$',imports,re.M))),'nativeUnixLibraryRequired':False}
tools={name:str(TC/name) for name in ('llvm-readobj','llvm-objdump')}
files=sorted(p for p in farm.iterdir() if p.suffix.lower() in ('.dll','.exe','.drv'))
missing=inspect_closure(files,tools)
if missing:raise SystemExit('Missing recursive farm dependencies: '+str(missing))
games={}
for filename in ('fantastic-UnityPlayer.dll','Earth.exe'):
 path=WORK.parent/'black-screen-oct17'/filename
 if not path.is_file():continue
 imports=output(TC/'llvm-readobj','--coff-imports',path)
 checks={}
 for block in re.findall(r'Import \{(.*?)\n\}',imports,re.S):
  name=re.search(r'^  Name: (.+)$',block,re.M).group(1).lower()
  if name not in {m+'.dll' for m in modules}:continue
  required=set(re.findall(r'^  Symbol: (.+) \(\d+\)$',block,re.M))
  exports=set(re.findall(r'^  Name: (.+)$',(WORK/(name+'.exports.txt')).read_text(),re.M))
  unresolved=sorted(required-exports)
  if unresolved:raise SystemExit(filename+': unresolved '+name+' '+str(unresolved))
  checks[name]={'requiredSymbols':sorted(required),'unresolved':unresolved}
 games[filename]={'sha256':sha(path),'correctedImportSymbols':checks}
source_hashes={}
for directory,dirs,names in os.walk(SOURCE):
 dirs[:]=[d for d in dirs if not d.startswith('build') and d not in ('.git','obj')]
 for name in names:
  p=Path(directory)/name
  if p.is_file() and not p.is_symlink() and p.suffix not in ('.o','.a'):
   source_hashes[p.relative_to(SOURCE).as_posix()]=sha(p)
write(WORK/'wine-source-files.json',source_hashes)
write(WORK/'overlay-provenance.json',{'schemaVersion':1,'kind':'Five newly source-built ARM64EC Wine PE DLLs added to archival stable native runtime','nativeRebuilt':False,'wineExecuted':False,'hardwareGameplayVerified':False,'sourceRoot':str(SOURCE),'preparedMadeiraProvenanceSha256':sha(SOURCE.parent/'AVPPLAY_SOURCE_PROVENANCE.json'),'wineSourceFileHashesSha256':sha(WORK/'wine-source-files.json'),'wineSourceFileCount':len(source_hashes),'buildDirectory':str(WORK/'wine-build'),'configureArguments':['--enable-archs=arm64ec','--without-x','--without-freetype','--disable-tests','--enable-winegstreamer'],'buildTargets':['dlls/'+m+'/arm64ec-windows/'+m+'.dll' for m in modules],'buildLogSha256':sha(WORK/'build.log'),'configureLogSha256':sha(WORK/'configure.log'),'generatedMakefileSha256':sha(WORK/'wine-build/Makefile'),'configStatusSha256':sha(WORK/'wine-build/config.status'),'compilerSha256':sha((TC/'arm64ec-w64-mingw32-clang').resolve()),'compilerVersion':output(TC/'arm64ec-w64-mingw32-clang','--version'),'originalGuestReceiptSha256':sha(ORIGINAL/'Runtime/AVPPLAY_GUEST_BUILD_RECEIPT.json'),'originalNativeReceiptSha256':sha(ORIGINAL/'Runtime/AVPPLAY_NATIVE_BUILD_RECEIPT.json'),'files':records,'completeFarmPECount':len(files),'recursiveClosureMissing':missing,'actualGameImportSymbolChecks':games,'prefixRefresh':'Existing native WineProcessBridge recreates session system32 and sysx64 links on each launch; no active prefix mutation performed.'})
print('PASS: five source-built ARM64EC DLLs, '+str(len(files))+'-module recursive closure, actual game import symbol checks; no native runtime mutation.')
