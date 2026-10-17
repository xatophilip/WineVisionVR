#!/usr/bin/env python3
"""Assemble current Swift with an unchanged, historically verified native app."""
import hashlib,json,os,plistlib,re,shutil,subprocess,sys
from pathlib import Path
REPO=Path('/Volumes/XRDev/src/WineVisionVR')
WORK=Path('/Volumes/XRDev/build/WineVisionVR/artifacts-modern-single-option')
ORIGINAL=Path('/Volumes/XRDev/build/WineVisionVR/black-screen-oct16/working-windlands-queue.app')
FRAMEWORKS=('WindowsRuntimePlugin','WindowsVRNativeBridge','WindowsVRMetal')
RESOURCES=('Runtime','WindowsVR','nls','fonts','aarch64-windows','arm64ec-windows','DesktopDemo','VRSmoke','steam-native','madeira-jit.js')
ABI_HEADERS=('WindowsVRCompositorBridge.h','WindowsVRMetalDiagnostics.h','WindowsVRThreadDump.h','WindowsVRThreadTrace.h','WindowsVRAudioSession.h')
def run(args,**kw): return subprocess.run(list(map(str,args)),check=True,**kw)
def output(args): return subprocess.check_output(list(map(str,args)),text=True).strip()
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def tree(root):
 if root.is_symlink():raise SystemExit('Refusing symlink root '+str(root))
 paths=[root] if root.is_file() else sorted(root.rglob('*'))
 result={}
 for p in paths:
  if p.is_symlink() or not(p.is_file() or p.is_dir()):raise SystemExit('Nonregular snapshot resource '+str(p))
  if p.is_file():result['.' if p==root else p.relative_to(root).as_posix()]={'sha256':sha(p),'mode':p.stat().st_mode&0o777}
 return result
def symbols(p):return sorted({r.split()[-1] for r in output(['xcrun','nm','-gU',p]).splitlines() if r.split()})
def source_hashes():
 roots=[REPO/'visionos-windows-vr/Sources',REPO/'windows-vr/Sources',REPO/'windows-vr-metal/Sources']
 result={}
 for root in roots:
  for p in sorted(root.rglob('*')):
   if p.is_file() and not p.is_symlink():result[p.relative_to(REPO).as_posix()]=sha(p)
 for rel in ['windows-vr/Package.swift','windows-vr-metal/Package.swift',*['windows-vr-native/include/'+n for n in ABI_HEADERS],'windows-vr/include/WindowsVRRuntimePlugin.h']:
  result[rel]=sha(REPO/rel)
 return result
def preflight():
 WORK.mkdir(exist_ok=True)
 if (WORK/'preflight.json').exists():raise SystemExit('Preflight already exists; explicit new assembly required')
 run(['git','-C',REPO,'diff','--exit-code','ce26c6d','--','windows-vr-metal','windows-vr-native/include','windows-vr/include/WindowsVRRuntimePlugin.h'])
 run(['codesign','--verify','--deep','--strict',ORIGINAL])
 env=dict(os.environ,AVPPLAY_ENABLE_X86='0')
 run(['bash',REPO/'windows-vr-tools/verify_wine_bundle.sh',ORIGINAL],env=env)
 current_xcode=output(['xcodebuild','-version'])
 version=plistlib.loads((ORIGINAL/'Frameworks/WindowsVRMetal.framework/Info.plist').read_bytes())
 if version['DTSDKName']!='xros27.0' or version['DTXcodeBuild'] not in current_xcode:raise SystemExit('Snapshot and selected SDK/toolchain mismatch')
 framework_trees={n:tree(ORIGINAL/'Frameworks'/(n+'.framework')) for n in FRAMEWORKS}
 exports={n:symbols(ORIGINAL/'Frameworks'/(n+'.framework')/n) for n in FRAMEWORKS}
 required=set()
 for p in (REPO/'visionos-windows-vr/Sources').rglob('*.swift'):
  text=p.read_text()
  shader_entrypoints=set(re.findall(r'\b(?:vertex|fragment|kernel)\s+\w+\s+((?:wvr_)[A-Za-z0-9_]*)\s*\(',text))
  required.update('_'+n for n in re.findall(r'\b((?:wvr_|winios_|wine_process_|wineserver_|madeira_)[A-Za-z0-9_]*)\s*\(',text) if n not in shader_entrypoints)
 missing=required-set().union(*(set(v) for v in exports.values()))
 if missing:raise SystemExit('Current Swift requires absent prebuilt C APIs: '+str(sorted(missing)))
 expected_metal=['_WVRMetalFXABIVersion','_WVRMetalFXSRCreateV1','_WVRMetalFXSRDestroyV1','_WVRMetalFXSREncodeV1']
 if exports['WindowsVRMetal']!=expected_metal:raise SystemExit('Unexpected archival Metal exported ABI')
 resource_trees={n:tree(ORIGINAL/n) for n in RESOURCES}
 v={'schemaVersion':1,'originalApp':str(ORIGINAL),'originalAppMainSha256':sha(ORIGINAL/'WineVision VR'),'sourceBaseline':'ce26c6d','currentHead':output(['git','-C',REPO,'rev-parse','HEAD']),'xcode':current_xcode,'sdk':output(['xcrun','--sdk','xros','--show-sdk-version']),'frameworkTrees':framework_trees,'frameworkExportedABI':exports,'resources':resource_trees,'currentSwiftSourcesSha256':source_hashes(),'requiredCurrentSwiftCExports':sorted(required),'nativeRebuilt':False}
 (WORK/'preflight.json').write_text(json.dumps(v,indent=2)+'\n')
 print('Preflight passed: verified original signed runtime, unchanged C ABI/Metal source and current Swift C API compatibility.')
def check(app,restore=False):
 app=app.resolve()
 if WORK.resolve() not in app.parents or app.name!='WineVision VR.app':raise SystemExit('Refusing app outside isolated assembly directory')
 v=json.loads((WORK/'preflight.json').read_text())
 if source_hashes()!=v['currentSwiftSourcesSha256']:raise SystemExit('Swift/ABI source changed after frozen preflight')
 for n in FRAMEWORKS:
  if tree(ORIGINAL/'Frameworks'/(n+'.framework'))!=v['frameworkTrees'][n]:raise SystemExit('Original framework changed '+n)
 for n in RESOURCES:
  if tree(ORIGINAL/n)!=v['resources'][n]:raise SystemExit('Original resources changed '+n)
  if tree(app/n)!=v['resources'][n]:raise SystemExit('Embedded original resource mismatch '+n)
 for rel in ('Runtime/i386-windows','WindowsVR/Guest/x86','VRSmokeX86'):
  if (app/rel).exists():raise SystemExit('32-bit resources must not be advertised by archival modern assembly: '+rel)
 if restore:
  fresh=symbols(app/'Frameworks/WindowsVRMetal.framework/WindowsVRMetal')
  if fresh!=v['frameworkExportedABI']['WindowsVRMetal']:raise SystemExit('Fresh Metal package exported ABI mismatch')
  (WORK/'fresh-metal-abi.json').write_text(json.dumps({'freshExportedABI':fresh,'originalExportedABI':v['frameworkExportedABI']['WindowsVRMetal'],'compatible':True},indent=2)+'\n')
  # All three inputs already carry valid same-team signatures. Restore exact
  # signed framework bytes AFTER Xcode's embed/sign phases, BEFORE app signing.
  for n in FRAMEWORKS:
   target=app/'Frameworks'/(n+'.framework')
   if target.is_symlink():raise SystemExit('Unexpected generated framework symlink')
   shutil.rmtree(target)
   shutil.copytree(ORIGINAL/'Frameworks'/(n+'.framework'),target,copy_function=shutil.copy2)
 for n in FRAMEWORKS:
  if tree(app/'Frameworks'/(n+'.framework'))!=v['frameworkTrees'][n]:raise SystemExit('Archival framework byte/mode mismatch '+n)
 archive_receipts={p.relative_to(app).as_posix():sha(p) for p in (app/'Runtime').rglob('*RECEIPT*.json')}
 archive_receipts['Runtime/AVPPLAY_RESOURCE_STAGE.json']=sha(app/'Runtime/AVPPLAY_RESOURCE_STAGE.json')
 assembly={'schemaVersion':1,'assemblyMode':'Current Swift frontend with exact archival native frameworks and runtime resources','nativeRebuilt':False,'nativeSourceValidationPerformed':False,'archivalNativeProvenance':'Original native/guest/resource receipts retained byte-for-byte as historical provenance; they are not assertions of a current native source build.','originalWorkingApp':str(ORIGINAL),'sourceBaselineForUnchangedMetalAndCABI':'ce26c6d','frameworkBytesAndSignaturesPreserved':True,'runtimeResourcesUnchanged':True,'currentSwiftSourcesSha256':v['currentSwiftSourcesSha256'],'archivalReceiptFilesSha256':archive_receipts,'freshMetalExportedABIChecked':True,'finalMetalBinary':'Exact original signed WindowsVRMetal.framework restored after compatible current-source package compilation.'}
 if restore:
  (app/'WineVisionAssemblyAudit.json').write_text(json.dumps(assembly,indent=2)+'\n')
 else:
  embedded=json.loads((app/'WineVisionAssemblyAudit.json').read_text())
  if embedded!=assembly:raise SystemExit('Embedded assembly audit mismatch')
 run(['bash',REPO/'windows-vr-tools/verify_wine_bundle.sh',app],env=dict(os.environ,AVPPLAY_ENABLE_X86='0'))
 print('Assembly audit passed; exact original native frameworks/resources/receipts preserved.')
if sys.argv[1]=='preflight':preflight()
elif sys.argv[1]=='finalize':check(Path(sys.argv[2]),True)
elif sys.argv[1]=='verify':check(Path(sys.argv[2]))
else:raise SystemExit('Use preflight/finalize/verify')
