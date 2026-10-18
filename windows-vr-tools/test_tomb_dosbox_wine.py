#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 WineVision VR contributors

"""Opt-in actual owned Tomb Raider/DOSBox integration. No game assets in Git.

Compiles the current production Swift compatibility helper, resolver, scoped
environment, Sense VK mapper and surface key-source transition method. Its
outputs launch bundled x86 DOSBox through an owned Win64 CreateProcessW driver.
GC hardware sampling and the visionOS native input sink are boundary substitutes.
Native DOSBox screenshots require visual checkpoint review; exit 0 alone is not
a gameplay assertion. Requires macOS, Pillow, pinned MinGW and local Wine.
"""
import argparse,datetime,hashlib,json,os,re,shutil,struct,subprocess,tarfile,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--source-root',type=Path,default=ROOT)
p.add_argument('--game',type=Path,required=True)
p.add_argument('--build',type=Path,required=True)
p.add_argument('--wine-build',type=Path,required=True)
p.add_argument('--wine-source',type=Path,required=True)
p.add_argument('--freetype-lib',type=Path,required=True)
p.add_argument('--prefix-template',type=Path,required=True)
p.add_argument('--template-sha256',required=True)
p.add_argument('--toolchain',type=Path,required=True)
p.add_argument('--capture-method',choices=['gdi','native'],required=True,help='Owned HWND GDI readback; native diagnostic Ctrl+F5 can affect game menus')
p.add_argument('--startup-control',action='store_true',help='No mapped inputs: isolate the proven CreateProcess startup path')
p.add_argument('--wine-debug',default='-all')
p.add_argument('--diagnostic-bare-prompt',action='store_true',help='Diagnostic only: omit game commands and stop at the real DOSBox prompt')
p.add_argument('--diagnostic-core-normal',action='store_true',help='Diagnostic only: private extra [cpu] core=normal config; production settings preserved')
p.add_argument('--windows-path-style',choices=['c','z'],default='c',help='Controlled host path comparison; production extra config remains C:')
a=p.parse_args()
# Reject unsafe destinations before creating even the output parent.
assert a.game.is_dir() and not a.game.is_symlink()
assert not any(x.is_symlink() for x in a.game.rglob('*')), 'Original game must contain no symbolic links'
a.game=a.game.resolve();a.build=a.build.resolve()
assert a.build!=a.game and a.game not in a.build.parents, 'Output must be outside original game'
def sha(path):
    digest=hashlib.sha256()
    with path.open('rb') as file:
        for block in iter(lambda:file.read(1024*1024),b''):digest.update(block)
    return digest.hexdigest()
a.build.mkdir(parents=True,exist_ok=True)
run=Path(tempfile.mkdtemp(prefix='run-',dir=a.build.resolve()))
(run/'tmp').mkdir()
env=dict(os.environ,TMPDIR=str(run/'tmp'),CLANG_MODULE_CACHE_PATH=str(run/'tmp/module-cache'),SWIFT_MODULECACHE_PATH=str(run/'tmp/swift-cache'))
report={'startedAtUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'passed':False,'scope':'Actual user-owned DOSBox/game under local Mac Wine/Rosetta WoW64; production Swift settings/argv/VK mapping and key-source transitions. No Steam authentication, visionOS/FEX/ARM64EC execution or physical controller sampling.',
        'noDeviceActions':True,'freshPrefixInitializationTested':False,
        'runDirectory':str(run),'visualReviewRequired':True,'captureLabelsAreRequestedCheckpoints':True,'captureHotkeyMayAffectGameMenus':a.capture_method=='native','captureMethod':a.capture_method}
def ledger(folder):return {str(x.relative_to(folder)):sha(x) for x in sorted(folder.rglob('*')) if x.is_file()}
def body(text,signature):
    start=text.index(signature);opening=text.index('{',start);end=opening+1;depth=1
    while depth:
        depth+=(text[end]=='{')-(text[end]=='}');end+=1
    return text[start:end]
def pe_machine(file):
    data=file.read_bytes();off=struct.unpack_from('<I',data,0x3c)[0]
    assert data[off:off+4]==b'PE\0\0'
    return struct.unpack_from('<H',data,off+4)[0]
assert a.game.is_dir() and a.wine_build.is_dir() and a.wine_source.is_dir()
assert a.game.resolve() not in run.parents, 'Output must be outside original game'
assert not a.game.is_symlink() and not any(x.is_symlink() for x in a.game.rglob('*')), 'Original game must contain no symbolic links'
originals=ledger(a.game)
shutil.copy2(Path(__file__),run/'test_tomb_dosbox_wine.executed.py')
report['helperSha256']=sha(run/'test_tomb_dosbox_wine.executed.py')
report.update(originalGame=str(a.game.resolve()),originalFiles=originals,originalFileCount=len(originals))
try:
    assert originals and sha(a.prefix_template)==a.template_sha256
    source=a.source_root.resolve()
    names=['visionos-windows-vr/Sources/Steam/SteamDOSBoxCompatibility.swift',
           'visionos-windows-vr/Sources/Steam/SteamInstalledExecutable.swift',
           'visionos-windows-vr/Sources/Desktop/WindowsDesktopGamepad.swift',
           'visionos-windows-vr/Sources/Desktop/WindowsDesktopView.swift',
           'visionos-windows-vr/Sources/LauncherModel.swift']
    texts=[(source/x).read_text() for x in names]
    compat,resolver,gamepad,view,launcher=texts
    report['productionSources']={x:hashlib.sha256(t.encode()).hexdigest() for x,t in zip(names,texts)}
    report['sourceCommit']=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
    prefix=run/'prefix'
    with tarfile.open(a.prefix_template) as tar:
        for member in tar.getmembers():
            name=Path(member.name)
            assert not name.is_absolute() and '..' not in name.parts and name.parts[0]=='prefix'
            assert not member.issym() and not member.islnk() and (member.isdir() or member.isfile())
            assert name.suffix.lower() not in ['.dll','.exe','.drv','.sys']
        tar.extractall(run)
    (prefix/'.update-timestamp').write_text(str(int((a.wine_build/'loader/wine.inf').stat().st_mtime))+'\n')
    # This pinned macOS Wine hard-codes /tmp for its small per-prefix server
    # socket/lock directory, ignoring TMPDIR. Preflight only this fresh prefix's
    # directory before any compilation; all bulk files stay in the external run.
    st=prefix.stat()
    socket_parent=Path('/tmp')/('.wine-'+str(os.getuid()))
    if not socket_parent.exists():socket_parent.mkdir(mode=0o700)
    parent_st=socket_parent.lstat()
    assert not socket_parent.is_symlink() and parent_st.st_uid==os.getuid() and parent_st.st_mode&0o077==0
    socket_dir=socket_parent/('server-%x-%x'%(st.st_dev,st.st_ino))
    report['wineSocketDirectory']=str(socket_dir)
    socket_dir.mkdir(mode=0o700)
    check=socket_dir/'owned-integration-preflight'
    with check.open('xb') as f:f.write(b'preflight\n')
    check.unlink()
    report['wineSocketPreflightPassed']=True
    fonts=prefix/'drive_c/windows/Fonts';fonts.mkdir(parents=True,exist_ok=True)
    for f in (a.wine_source/'fonts').glob('*.ttf'):shutil.copy2(f,fonts/f.name)
    modules=[]
    for arch,system in [('x86_64','system32'),('i386','syswow64')]:
        for origin in a.wine_build.glob('**/'+arch+'-windows/*'):
            if not origin.is_file() or origin.suffix.lower() not in ['.dll','.exe','.drv','.sys','.cpl','.ax','.ocx','.acm']:continue
            target=prefix/'drive_c/windows'/system
            if origin.suffix.lower()=='.sys':target=target/'drivers'
            target.mkdir(parents=True,exist_ok=True);target=target/origin.name
            shutil.copy2(origin,target)
            modules.append({'source':str(origin),'destination':str(target),'sha256':sha(target)})
    drive=prefix/'drive_c'
    game=drive/'Steam/steamapps/common/Tomb Raider (I)'
    game.mkdir(parents=True)
    # APFS copy-on-write clone of owned files, never modify receiving/original tree.
    subprocess.run(['cp','-cR',str(a.game.resolve())+'/.',str(game)],check=True,env=env)
    assert ledger(game)==originals
    (game/'capture').mkdir(exist_ok=True)
    assert not list((game/'capture').glob('*.png')),'Use a pristine owned game snapshot without prior screenshots'
    shell=r'''
import Foundation
import GameController
struct DockGame { var id:Int;var library:String;var installDir:String }
struct SteamLaunchOption { var executable:String;var index:UInt32=0 }
enum DockError:Error { case message(String) }
var lines:[String]=[]
var events:[[String:Int32]]=[]
@MainActor func winios_post_key(_ vk:Int32,_ down:Int32) {
    lines.append("KEY \(vk) \(down)");events.append(["vk":vk,"down":down])
}
@MainActor final class Surface {
    var inputEnabled=true
    var keysHeld:Set<Int32>=[]
    var gamepadKeysHeld:Set<Int32>=[]
'''
    surface=body(view,'func updateGamepadKeys(_ keys: Set<Int32>)')
    mapping=body(gamepad,'enum WindowsDesktopGamepadMapping {')
    environment=body(launcher,'nonisolated static func steamCompatibilityEnvironment(')
    driver=r'''
let drive=URL(fileURLWithPath:CommandLine.arguments[1])
let out=URL(fileURLWithPath:CommandLine.arguments[2])
let game=DockGame(id:224960,library:"Steam/steamapps",installDir:"Tomb Raider (I)")
let option=SteamLaunchOption(executable:"dosbox.exe",index:1)
guard let extra=try SteamDOSBoxCompatibility.prepare(game:game,option:option,drive:drive) else { fatalError("Missing compatibility route") }
let environment=Env.steamCompatibilityEnvironment(appID:224960,base:[:],optionExecutable:option.executable)
let surface=Surface()
var samples:[[String:Any]]=[]
@MainActor func state(_ label:String,_ buttons:Set<String>=[],_ x:Float=0,_ y:Float=0) {
    let before=events.count
    let mapped=WindowsDesktopGamepadMapping.keys(pressed:{buttons.contains($0)},axis:{_ in nil},
        stick:{$0=="Left Thumbstick" ? (x,y):nil})
    surface.updateGamepadKeys(mapped)
    samples.append(["label":label,"buttons":buttons.sorted(),"x":x,"y":y,"mapped":mapped.sorted(),"eventCount":events.count-before])
}
@MainActor func wait(_ ms:Int) { lines.append("WAIT \(ms)") }
@MainActor func capture(_ label:String) { lines.append("CAPTURE \(label)") }
@MainActor func pulse(_ label:String,_ button:String) {
    state(label,[button]);wait(180);state(label+"-release");wait(5000)
}
wait(30000)
pulse("skip-logo",GCInputButtonOptions)
capture("title")
pulse("open-passport","Thumbstick Button")
capture("passport")
pulse("new-game","Thumbstick Button")
capture("intro")
// Allow the complete opening movie to finish without an ambiguous Escape.
for _ in 0..<4 { wait(30000) }
capture("caves-before")
state("forward-held",[],0,0.9);wait(1200)
state("forward-held-repeat",[],0,0.9);capture("forward-held")
state("forward-release");wait(900);capture("forward-released")
wait(1800);capture("forward-idle")
state("turn-held",[],0.9,0);wait(450)
state("turn-held-repeat",[],0.9,0);capture("turn-held")
wait(450)
state("turn-release");wait(900);capture("turn-released")
wait(1800);capture("turn-idle")
pulse("inventory-open",GCInputButtonOptions);capture("inventory")
pulse("inventory-close",GCInputButtonOptions);capture("inventory-closed")
precondition(surface.gamepadKeysHeld.isEmpty && surface.keysHeld.isEmpty)
precondition(samples.filter{($0["label"] as? String)?.hasSuffix("-repeat")==true}.allSatisfy{($0["eventCount"] as? Int)==0})
let evidence:[String:Any]=["arguments":extra,"environment":environment,"samples":samples,"events":events,"heldAtEnd":surface.gamepadKeysHeld.sorted()]
try JSONSerialization.data(withJSONObject:evidence,options:[.prettyPrinted,.sortedKeys]).write(to:out.appendingPathComponent("production-output.json"))
try Data((lines.joined(separator:"\n")+"\n").utf8).write(to:out.appendingPathComponent("plan.txt"))
'''
    swift=run/'production-probe.swift'
    swift.write_text(shell+surface+'\n}\n'+resolver+compat+mapping+'\nenum Env {\n'+environment+'\n}\n'+driver)
    probe=run/'production-probe'
    subprocess.run(['xcrun','swiftc','-swift-version','6','-module-cache-path',str(run/'tmp/swift-cache'),str(swift),'-o',str(probe)],check=True,env=env)
    subprocess.run([str(probe),str(drive),str(run)],check=True,env=env)
    produced=json.loads((run/'production-output.json').read_text())
    if a.startup_control:(run/'plan.txt').write_text('WAIT 30000\nCAPTURE startup\nWAIT 5000\nCAPTURE stable\nWAIT 5000\n')
    if a.diagnostic_bare_prompt:
        a.startup_control=True
        (run/'plan.txt').write_text('WAIT 5000\nCAPTURE startup\nWAIT 10000\nCAPTURE stable\nWAIT 1000\n')
    report['startupControlOnly']=a.startup_control
    report['diagnosticBarePrompt']=a.diagnostic_bare_prompt
    report['diagnosticCoreNormal']=a.diagnostic_core_normal
    report['executedPlan']=(run/'plan.txt').read_text()
    assert produced['environment']=={'SDL_VIDEODRIVER':'windib'} and produced['heldAtEnd']==[]
    settings=drive/'AVPPlaySteam/Compatibility/224960/software.conf'
    report['vendorCPUSettings']={}
    for vendor in ['dosbox.conf','dosboxTRWindowed.conf']:
        cpu=re.search(r'(?ms)^\[cpu\]\s*\n(.*?)(?=^\[|\Z)',(game/vendor).read_text()).group(1)
        report['vendorCPUSettings'][vendor]={line.split('=',1)[0].strip():line.split('=',1)[1].strip() for line in cpu.splitlines() if '=' in line and not line.lstrip().startswith(('#',';'))}
    dosbox=game/'dosbox.exe'
    assert pe_machine(dosbox)==0x14c
    cwd=r"C:\Steam\steamapps\common\Tomb Raider (I)" if a.windows_path_style=="c" else "Z:"+str(game).replace("/",chr(92))
    extra=produced['arguments'].split(' -c ',1)[0] if a.diagnostic_bare_prompt else produced['arguments']
    if a.diagnostic_core_normal:
        private=settings.with_name('cpu-normal-diagnostic.conf')
        private.write_text('[cpu]\ncore=normal\n')
        report['diagnosticConfiguration']={'path':str(private),'sha256':sha(private),'settings':'[cpu]\ncore=normal\n','productionSoftwareConfigurationUnchanged':True}
        extra+=' -conf "C:\\AVPPlaySteam\\Compatibility\\224960\\cpu-normal-diagnostic.conf"'
    command='"'+cwd+'\\dosbox.exe" -conf dosbox.conf -conf dosboxTRWindowed.conf -noconsole '+extra
    (run/'command.utf16').write_bytes(command.encode('utf-16le'))
    driver_source=Path(__file__).with_name('tomb_dosbox_driver.c')
    shutil.copy2(driver_source,run/driver_source.name)
    exe=run/'tomb_dosbox_driver.exe'
    subprocess.run([str(a.toolchain/'bin/x86_64-w64-mingw32-gcc'),'-O2','-municode','-Wall','-Wextra',str(driver_source),'-o',str(exe),'-luser32','-lgdi32'],check=True,env=env)
    assert pe_machine(exe)==0x8664
    wine=a.wine_build/'loader/wine';server=a.wine_build/'server/wineserver'
    env.update(WINEPREFIX=str(prefix),WINELOADER=str(wine),WINESERVER=str(server),WINEDLLPATH=str(a.wine_build/'dlls'),DYLD_FALLBACK_LIBRARY_PATH=str(a.freetype_lib.parent),WINEDEBUG=a.wine_debug,WINEDLLOVERRIDES='mscoree,mshtml=d',**produced['environment'])
    report.update(originalGame=str(a.game.resolve()),originalFiles=originals,originalFileCount=len(originals),wineBuild=str(a.wine_build.resolve()),wineLoaderSha256=sha(wine),wineServerSha256=sha(server),freetypeSha256=sha(a.freetype_lib),prefixTemplateSha256=sha(a.prefix_template),modules=modules,commandLine=command,workingDirectory=cwd,windowsPathStyle=a.windows_path_style,productionOutput=produced,settingsSha256=sha(settings),dosboxSha256=sha(dosbox),driverSha256=sha(exe),driverSourceSha256=sha(driver_source),cleanup='Own interactive child terminated after plan; cleanup exit is not a gameplay assertion.')
    with (run/'wine.log').open('wb') as log:
        process=subprocess.run([str(wine),str(exe),str(run/'command.utf16'),report['workingDirectory'],str(run/'plan.txt'),a.capture_method],cwd=run,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=240)
    report['harnessExitCode']=process.returncode
    milestones=run/'owned-driver-events.txt'
    text=milestones.read_text() if milestones.exists() else ''
    report['milestones']=text
    report['rawWineLogSha256']=sha(run/'wine.log')
    report['rawWineLogBytes']=(run/'wine.log').stat().st_size
    assert process.returncode==0 and 'PARENT_POINTER_BITS 64' in text and 'CHILD_WOW64 1' in text and 'HELD_AT_PLAN_END 0' in text and 'HARNESS_STATUS 0' in text,'Harness/loader/owned-child failure; inspect sidecar and first exception, not a gameplay verdict'
    labels=[line.split(' ',1)[1] for line in (run/'plan.txt').read_text().splitlines() if line.startswith('CAPTURE ')]
    captures=[run/'gdi-captures'/(label+'.bmp') for label in labels] if a.capture_method=='gdi' else sorted((game/'capture').glob('*.png'))
    assert all(path.is_file() for path in captures),'Missing capture artifacts'
    assert len(captures)==len(labels),'Incomplete native screenshots'
    if a.capture_method=='native':
        matches=[re.fullmatch(r'(dosbox)_(\d{3})\.png' if a.diagnostic_bare_prompt else r'(tombno~1)_(\d{3})\.png',x.name,re.IGNORECASE) for x in captures]
        assert all(matches) and len({m.group(1).lower() for m in matches})==1
        assert [int(m.group(2)) for m in matches]==list(range(len(labels))),'Native screenshot sequence gap or unrelated capture'
    report['captures']={label:{'path':str(path),'sha256':sha(path)} for label,path in zip(labels,captures)}
    assert process.returncode==0 and 'PARENT_POINTER_BITS 64' in text and 'CHILD_WOW64 1' in text and 'HELD_AT_PLAN_END 0' in text and 'HARNESS_STATUS 0' in text,'Harness/loader/owned window failure; not a game compatibility verdict'
    assert len(captures)==len(labels),'Incomplete DOSBox native screenshots; not a gameplay PASS'
    from PIL import Image,ImageChops
    def difference(first,second):
        l=Image.open(first).convert('RGB');r=Image.open(second).convert('RGB')
        assert l.size==r.size
        values=list(ImageChops.difference(l,r).getdata())
        return {'changedPixelFraction':sum(max(v)>20 for v in values)/len(values),'meanAbsoluteRGBDifference':sum(sum(v) for v in values)/(len(values)*3)}
    pairs=[] if a.startup_control else [('caves-before','forward-held'),('forward-held','forward-released'),('forward-released','forward-idle'),('forward-idle','turn-held'),('turn-held','turn-released'),('turn-released','turn-idle')]
    report['frameComparisons']={x+' -> '+y:difference(Path(report['captures'][x]['path']),Path(report['captures'][y]['path'])) for x,y in pairs}
    for module in modules:assert sha(Path(module['source']))==sha(Path(module['destination']))==module['sha256']
    assert ledger(a.game)==originals, 'Original game bytes changed'
    report['harnessPassed']=True
    report['passed']=False # Explicitly pending visual checkpoints and movement/release review.
except BaseException as error:
    report['error']=repr(error)
    raise
finally:
    if 'server' in locals():
        try:
            cleanup=subprocess.run([str(server),'-k'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15,check=False)
            report['prefixScopedServerCleanupExit']=cleanup.returncode
        except Exception as cleanup_error:report['cleanupError']=repr(cleanup_error)
    report['originalFilesUnchanged']=ledger(a.game)==originals
    if not report['originalFilesUnchanged']:
        report['harnessPassed']=False;report['passed']=False;report['preservationError']='Original game bytes changed'
    report['gdiCaptureArtifacts']=[{'path':str(path),'sha256':sha(path)} for path in (run/'gdi-captures').glob('*.bmp')]
    report['completedAtUTC']=datetime.datetime.now(datetime.timezone.utc).isoformat()
    (run/'integration-receipt.json').write_text(json.dumps(report,indent=2)+'\n')
    print(run/'integration-receipt.json',flush=True)
    if not report['originalFilesUnchanged']:raise AssertionError('Original game bytes changed')
