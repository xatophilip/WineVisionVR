import hashlib,json,os,plistlib,shutil,subprocess,sys
from pathlib import Path
WORK=Path('/Volumes/XRDev/build/WineVisionVR/artifacts-modern-single-option-game-compat')
BASE=Path('/Volumes/XRDev/build/WineVisionVR/artifacts-modern-single-option/xcode-derived/Build/Products/Release-xros/WineVision VR.app')
APP=WORK/'WineVision VR.app'
OVERLAY=Path('/Volumes/XRDev/build/WineVisionVR/game-dll-compat')
REPO=Path('/Volumes/XRDev/src/WineVisionVR')
ALLOW={f'Runtime/arm64ec-windows/{name}.dll' for name in ('avrt','dwmapi','mmdevapi','msvcp140','vcruntime140','wsock32')}|{f'arm64ec-windows/{name}' for name in ('dockhost.exe','dock-build.json','dock-notices.txt')}
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def write(p,v):p.write_text(json.dumps(v,indent=2,sort_keys=True)+'\n')
def read(p):return json.loads(p.read_text())
def tree(root):
 result={}
 for p in sorted(root.rglob('*')):
  if p.is_symlink():raise SystemExit('Symlink rejected '+str(p))
  if p.is_file():result[p.relative_to(root).as_posix()]={'sha256':sha(p),'mode':p.stat().st_mode&0o777}
 return result
def resource_hashes():return {k:v['sha256'] for k,v in tree(APP).items() if k.startswith(('Runtime/','WindowsVR/')) and k!='Runtime/AVPPLAY_RESOURCE_STAGE.json'}
def run(args,**kw):return subprocess.run(list(map(str,args)),check=True,**kw)
if (WORK/'verification-result.json').exists():raise SystemExit('Finalized candidate is immutable')
provenance=read(OVERLAY/'openvr-overlay-provenance.json')
assert set(provenance['filesSha256'])==ALLOW
assert provenance['completeRuntimeAndHostClosureMissing']=={} and provenance['gameplayVerified'] is False
assert provenance['inheritedFiveModuleBuildProvenanceSha256']==sha(OVERLAY/'overlay-provenance.json')
assert provenance['inheritedNamedAndOrdinalValidationSha256']==sha(OVERLAY/'ordinal-validation.json')
before=tree(BASE)
assert tree(APP)==before
assert read(OVERLAY/'overlay-provenance.json')['originalGuestReceiptSha256']==sha(APP/'Runtime/AVPPLAY_GUEST_BUILD_RECEIPT.json')
assert read(OVERLAY/'overlay-provenance.json')['originalNativeReceiptSha256']==sha(APP/'Runtime/AVPPLAY_NATIVE_BUILD_RECEIPT.json')
for rel in sorted(ALLOW):
 src=OVERLAY/'openvr-overlay'/rel
 assert src.is_file() and not src.is_symlink() and sha(src)==provenance['filesSha256'][rel]
 if rel.startswith('Runtime/'):assert not (APP/rel).exists(), 'Expected missing provider '+rel
 shutil.copy2(src,APP/rel)
# Preserve all original receipts explicitly as historical provenance. The current
# resource checksum manifest and composite guest receipt describe this assembly.
history=APP/'Runtime/HistoricalProvenance';history.mkdir()
for name in ('AVPPLAY_GUEST_BUILD_RECEIPT.json','AVPPLAY_RESOURCE_STAGE.json'):
 shutil.copy2(BASE/'Runtime'/name,history/name)
shutil.copy2(OVERLAY/'openvr-overlay-provenance.json',APP/'Runtime/AVPPLAY_PE_OVERLAY_PROVENANCE.json')
guest=read(BASE/'Runtime/AVPPLAY_GUEST_BUILD_RECEIPT.json')
assert guest['nativeReceiptSha256']==sha(APP/'Runtime/AVPPLAY_NATIVE_BUILD_RECEIPT.json')
guest['assembly']={'mode':'Historical full guest build plus six newly source-built ARM64EC PE providers and rebuilt Steam host','fullGuestRebuilt':False,'nativeRebuilt':False,'sourceScope':'Top-level source describes historical inherited runtime only; current six-PE/Steam-host build source/configuration/toolchain/snapshots are in overlay provenance.','historicalGuestReceiptSha256':sha(history/'AVPPLAY_GUEST_BUILD_RECEIPT.json'),'peOverlayProvenanceSha256':sha(APP/'Runtime/AVPPLAY_PE_OVERLAY_PROVENANCE.json'),'hardwareGameplayVerified':False}
for rel in ALLOW:
 if rel.startswith('Runtime/'):guest['guest']['resourcesSha256'][rel.removeprefix('Runtime/')]=sha(APP/rel)
write(APP/'Runtime/AVPPLAY_GUEST_BUILD_RECEIPT.json',guest)
assert all(sha(APP/'Runtime'/rel)==h for rel,h in guest['guest']['resourcesSha256'].items())
stage=read(BASE/'Runtime/AVPPLAY_RESOURCE_STAGE.json')
stage['inputs']['guestReceiptSha256']=sha(APP/'Runtime/AVPPLAY_GUEST_BUILD_RECEIPT.json')
stage['inputs']['peOverlayProvenanceSha256']=sha(APP/'Runtime/AVPPLAY_PE_OVERLAY_PROVENANCE.json')
stage['inputs']['historicalStageReceiptSha256']=sha(history/'AVPPLAY_RESOURCE_STAGE.json')
stage['assemblyScope']='Composite checksum stage: exact historical resources plus declared six-PE/Steam-host source build; no full runtime/native rebuild asserted.'
stage['filesSha256']=resource_hashes();write(APP/'Runtime/AVPPLAY_RESOURCE_STAGE.json',stage)
assert stage['filesSha256']==resource_hashes()
audit=read(BASE/'WineVisionAssemblyAudit.json')
audit['assemblyMode']='Current Swift size/Repair/session-log frontend with archival native frameworks and six source-built ARM64EC PE providers plus rebuilt Steam host'
audit['runtimeResourcesUnchanged']=False
audit['archivalNativeProvenance']='Original native receipt and all native framework bytes/signatures are retained unchanged. Original guest/stage receipts are retained under Runtime/HistoricalProvenance as historical provenance only. Current composite guest/stage receipts and PE/Steam-host overlay provenance describe actual packaged resources; no full native/guest source rebuild is claimed.'
audit['archivalReceiptFilesSha256']={f'Runtime/HistoricalProvenance/{name}':sha(history/name) for name in ('AVPPLAY_GUEST_BUILD_RECEIPT.json','AVPPLAY_RESOURCE_STAGE.json')}
audit['archivalReceiptFilesSha256']['Runtime/AVPPLAY_NATIVE_BUILD_RECEIPT.json']=sha(APP/'Runtime/AVPPLAY_NATIVE_BUILD_RECEIPT.json')
audit['peOverlay']={'filesSha256':{rel:sha(APP/rel) for rel in sorted(ALLOW)},'provenanceSha256':sha(APP/'Runtime/AVPPLAY_PE_OVERLAY_PROVENANCE.json'),'guestReceiptSha256':sha(APP/'Runtime/AVPPLAY_GUEST_BUILD_RECEIPT.json'),'resourceStageSha256':sha(APP/'Runtime/AVPPLAY_RESOURCE_STAGE.json'),'fullGuestRebuilt':False,'nativeRebuilt':False,'hardwareGameplayVerified':False}
write(APP/'WineVisionAssemblyAudit.json',audit)
snapshot=tree(APP)
changed={k for k in set(before)|set(snapshot) if before.get(k)!=snapshot.get(k)}
expected={rel for rel in ALLOW if before.get(rel)!=snapshot.get(rel)}|{'WineVisionAssemblyAudit.json','Runtime/AVPPLAY_GUEST_BUILD_RECEIPT.json','Runtime/AVPPLAY_RESOURCE_STAGE.json','Runtime/AVPPLAY_PE_OVERLAY_PROVENANCE.json','Runtime/HistoricalProvenance/AVPPLAY_GUEST_BUILD_RECEIPT.json','Runtime/HistoricalProvenance/AVPPLAY_RESOURCE_STAGE.json'}
assert changed==expected,(changed,expected)
for name in ('WindowsRuntimePlugin','WindowsVRNativeBridge','WindowsVRMetal'):
 assert tree(BASE/'Frameworks'/(name+'.framework'))==tree(APP/'Frameworks'/(name+'.framework'))
write(WORK/'pre-sign-diff.json',{'changedFiles':sorted(changed),'expectedFiles':sorted(expected),'exactAllowlist':True,'nativeFrameworkBytesUnchanged':True})
ent=subprocess.check_output(['codesign','-d','--entitlements',':-',str(BASE)],stderr=subprocess.DEVNULL)
plistlib.loads(ent);(WORK/'entitlements.plist').write_bytes(ent)
run(['codesign','--force','--sign','1D6311197934469C06035179ECDE965FAF23875A','--entitlements',WORK/'entitlements.plist',APP])
run(['codesign','--verify','--deep','--strict',APP])
# App-level signing may change only the resource envelope and executable seal.
after=tree(APP)
assert {k for k in set(before)|set(after) if before.get(k)!=after.get(k)}<=expected|{'_CodeSignature/CodeResources','WineVision VR'}
for name in ('WindowsRuntimePlugin','WindowsVRNativeBridge','WindowsVRMetal'):
 assert tree(BASE/'Frameworks'/(name+'.framework'))==tree(APP/'Frameworks'/(name+'.framework'))
assert read(APP/'Runtime/AVPPLAY_RESOURCE_STAGE.json')['filesSha256']==resource_hashes()
run(['bash',REPO/'windows-vr-tools/verify_wine_bundle.sh',APP],env=dict(os.environ,AVPPLAY_ENABLE_X86='0'))
run(['python3','/Volumes/XRDev/build/WineVisionVR/verify-local-app.py',APP])
result={'ordinalValidationSidecarSha256':sha(OVERLAY/'ordinal-validation.json'),'status':'signed-composite-assembly-verified-not-device-tested','app':str(APP),'nativeFrameworkBytesAndSignaturesPreserved':True,'frontendUUID':subprocess.check_output(['xcrun','dwarfdump','--uuid',str(APP/'WineVision VR')],text=True).strip(),'exactResourceOverlay':sorted(ALLOW),'nativeRebuilt':False,'fullGuestRebuilt':False,'hardwareGameplayVerified':False,'guestResourceFilesVerified':len(guest['guest']['resourcesSha256']),'resourceStageFilesVerified':len(stage['filesSha256']),'overlayProvenanceSha256':sha(APP/'Runtime/AVPPLAY_PE_OVERLAY_PROVENANCE.json'),'allAppFilesSha256':{k:v['sha256'] for k,v in after.items()}}
write(WORK/'verification-result.json',result)
print('PASS: signed composite candidate, exact six-PE/Steam-host allowlist, unchanged native frameworks/signatures, full guest/stage checksum closure; device gameplay unverified.')
