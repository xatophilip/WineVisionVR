#!/usr/bin/env python3
"""Opt-in actual Wine QPC/SDL boundary controls. No game assets are included.

Each direct/mixed case gets a fresh verified-template prefix and same-build PEs.
The SDL matrix uses a supplied owned SDL 1 DLL, actual timer callbacks and an
owned window. It proves API execution, not gameplay, audio playback, physical
joystick input, fresh-prefix initialization or visionOS behavior.
"""
import argparse,datetime,hashlib,json,os,re,shutil,struct,subprocess,tarfile,tempfile
from pathlib import Path
def sha(path):
    digest=hashlib.sha256()
    with path.open('rb') as file:
        for chunk in iter(lambda:file.read(1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()
def machine(path):
    with path.open('rb') as file:
        header=file.read(64);file.seek(struct.unpack_from('<I',header,0x3c)[0]);pe=file.read(6)
    assert pe[:4]==b'PE\0\0'
    return struct.unpack_from('<H',pe,4)[0]
def validate_row(kind,row):
    if kind=='qpc':
        markers=row.get('markers',{})
        return row.get('exitCode')==0 and all(f'PASS QPC calls=100000 pointerBits=32' in markers.get('qpc-'+name+'-after.txt','') and 'before QPC pointerBits=32' in markers.get('qpc-'+name+'-before.txt','') for name in ['main','worker'])
    text=row.get('milestones','')
    count=re.search(r'^timer-after value=(\d+) pointerBits=32 ',text,re.M)
    return row.get('exitCode')==0 and count is not None and int(count[1])>=100 and all(re.search('^'+stage+r' pointerBits=32 ',text,re.M) for stage in ['init-after value=0','main-after value=10000','worker-after value=10000','timer-remove value=1','final value=1'])
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--output-root',type=Path)
p.add_argument('--wine-build',type=Path);p.add_argument('--wine-source',type=Path)
p.add_argument('--freetype-lib',type=Path);p.add_argument('--toolchain',type=Path)
p.add_argument('--prefix-template',type=Path);p.add_argument('--template-sha256')
p.add_argument('--sdl-dll',type=Path)
p.add_argument('--kind',choices=['qpc','sdl','all'],default='all')
p.add_argument('--verify-receipts',nargs='+',type=Path,help='Read-only verification of preserved actual QPC/SDL execution receipts')
a=p.parse_args()
sources=Path(__file__).with_name('dosbox-controls')
if a.verify_receipts:
    for receipt in a.verify_receipts:
        document=json.loads(receipt.read_text());kind='sdl' if document.get('sdlOriginalSha256') else 'qpc'
        assert document['tests']
        for name,row in document['tests'].items():
            assert row['passed'] and validate_row(row.get('kind',kind),row),(receipt,name)
            if row.get('kind',kind)=='sdl':assert sha(Path(row['command'][-1]))==document['sdlOriginalSha256']
            dll=row['actualNTDLL']
            assert sha(Path(dll['source']))==sha(Path(dll.get('destination',dll.get('installed'))))==dll['sha256']
        for name,expected in document.get('fixtureHashes',{}).items():
            assert sha(receipt.parent/name)==expected
            if name.endswith('.c'):assert sha(sources/name)==expected
        for name,fixture in document.get('fixtures',{}).items():
            assert sha(Path(fixture['path']))==fixture['sha256']
            assert sha(Path(fixture['source']))==sha(sources/(name+'.c'))==fixture['sourceSha256']
        print('PASS: preserved',kind,'actual execution receipt:',receipt)
    raise SystemExit(0)
for name in ['output_root','wine_build','wine_source','freetype_lib','toolchain','prefix_template','template_sha256']:
    if getattr(a,name) is None:p.error('--'+name.replace('_','-')+' is required for execution')
if a.kind!='qpc' and a.sdl_dll is None:p.error('--sdl-dll is required for SDL execution')
a.output_root=a.output_root.resolve()
assert a.output_root!=sources.resolve() and sources.resolve() not in a.output_root.parents, 'Output must be outside probe sources'
if a.sdl_dll:
    source_folder=a.sdl_dll.resolve().parent
    assert a.output_root!=source_folder and source_folder not in a.output_root.parents, 'Output must be outside original SDL source folder'
assert sha(a.prefix_template)==a.template_sha256
if a.sdl_dll:
    assert a.sdl_dll.is_file() and not a.sdl_dll.is_symlink() and machine(a.sdl_dll)==0x14c
a.output_root.mkdir(parents=True,exist_ok=True)
run=Path(tempfile.mkdtemp(prefix='execution-',dir=a.output_root.resolve()));(run/'tmp').mkdir()
if a.sdl_dll:assert a.sdl_dll.resolve().parent not in run.parents
env=dict(os.environ,TMPDIR=str(run/'tmp'),WINELOADER=str(a.wine_build/'loader/wine'),WINESERVER=str(a.wine_build/'server/wineserver'),WINEDLLPATH=str(a.wine_build/'dlls'),DYLD_FALLBACK_LIBRARY_PATH=str(a.freetype_lib.parent),WINEDEBUG='+seh,+loaddll',WINEDLLOVERRIDES='mscoree,mshtml=d',SDL_VIDEODRIVER='windib')
report={'startedAtUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'passed':False,'scope':__doc__,'tests':{},'freshPrefixInitializationTested':False,'prefixTemplateSha256':a.template_sha256,'wineLoaderSha256':sha(a.wine_build/'loader/wine'),'wineServerSha256':sha(a.wine_build/'server/wineserver'),'freetypeSha256':sha(a.freetype_lib),'fixtures':{},'sdlOriginalSha256':sha(a.sdl_dll) if a.sdl_dll else None}
def seed(prefix):
    assert not prefix.exists()
    with tarfile.open(a.prefix_template) as archive:
        for member in archive.getmembers():
            parts=Path(member.name)
            assert not parts.is_absolute() and '..' not in parts.parts and parts.parts[0]=='prefix'
            assert not member.issym() and not member.islnk() and (member.isdir() or member.isfile())
            assert parts.suffix.lower() not in ['.dll','.exe','.drv','.sys']
        archive.extractall(prefix.parent)
    (prefix/'.update-timestamp').write_text(str(int((a.wine_build/'loader/wine.inf').stat().st_mtime))+'\n')
    fonts=prefix/'drive_c/windows/Fonts';fonts.mkdir(parents=True,exist_ok=True)
    for font in (a.wine_source/'fonts').glob('*.ttf'):shutil.copy2(font,fonts/font.name)
    modules=[];destinations=set()
    for arch,system in [('x86_64','system32'),('i386','syswow64')]:
        for origin in a.wine_build.glob('**/'+arch+'-windows/*'):
            if not origin.is_file() or origin.suffix.lower() not in ['.dll','.exe','.drv','.sys','.cpl','.ax','.ocx','.acm']:continue
            target=prefix/'drive_c/windows'/system
            if origin.suffix.lower()=='.sys':target=target/'drivers'
            target.mkdir(parents=True,exist_ok=True);target=target/origin.name
            assert target not in destinations;destinations.add(target)
            shutil.copy2(origin,target);modules.append({'source':str(origin),'destination':str(target),'sha256':sha(target),'architecture':arch})
    return modules
try:
    required=['qpc-worker32','qpc-parent64'] if a.kind=='qpc' else ['sdl-probe32','probe-parent64'] if a.kind=='sdl' else ['qpc-worker32','qpc-parent64','sdl-probe32','probe-parent64']
    for name in required:
        c=sources/(name+'.c');exe=run/(name+'.exe');arch='x86_64' if name.endswith('64') else 'i686'
        command=[str(a.toolchain/'bin'/(arch+'-w64-mingw32-gcc')),'-O2','-Wall','-Wextra']
        if name!='qpc-worker32':command.append('-municode')
        command.extend([str(c),'-o',str(exe)]);subprocess.run(command,env=env,check=True)
        assert machine(exe)==(0x8664 if arch=='x86_64' else 0x14c)
        report['fixtures'][name]={'source':str(c),'sourceSha256':sha(c),'path':str(exe),'sha256':sha(exe),'command':command}
    kinds=['qpc','sdl'] if a.kind=='all' else [a.kind]
    for kind in kinds:
        cases=[('qpc',None)] if kind=='qpc' else [('timer',1),('video-timer',0x21),('joystick-video-timer',0x221),('audio-timer',0x11)]
        for label,flags in cases:
            for mode in ['direct','mixed']:
                key=label+'-'+mode;work=run/key;work.mkdir();prefix=work/'prefix'
                modules=seed(prefix);env['WINEPREFIX']=str(prefix)
                child=run/('qpc-worker32.exe' if kind=='qpc' else 'sdl-probe32.exe')
                args=[str(child)]
                if kind=='sdl':
                    shutil.copy2(a.sdl_dll,work/'SDL.dll');assert sha(work/'SDL.dll')==report['sdlOriginalSha256']
                    args.extend([str(flags),str(work/'SDL.dll')])
                parent=run/('qpc-parent64.exe' if kind=='qpc' else 'probe-parent64.exe')
                command=[env['WINELOADER']]+([str(parent)]+args if mode=='mixed' else args)
                row={'kind':kind,'command':command,'flags':flags,'passed':False,'installedPEModules':modules}
                report['tests'][key]=row
                try:
                    with (work/'wine.log').open('wb') as log:
                        status=subprocess.run(command,cwd=work,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=60)
                    row['exitCode']=status.returncode
                    if kind=='qpc':row['markers']={x.name:x.read_text() for x in work.glob('qpc-*.txt')}
                    else:row['milestones']=(work/'sdl-milestones.txt').read_text() if (work/'sdl-milestones.txt').exists() else ''
                    row['passed']=validate_row(kind,row)
                except subprocess.TimeoutExpired:row['timedOut']=True
                finally:subprocess.run([env['WINESERVER'],'-k'],env=env,timeout=15,check=False,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                for module in modules:assert sha(Path(module['source']))==sha(Path(module['destination']))==module['sha256']
                row['actualNTDLL']=next(x for x in modules if x['architecture']=='i386' and Path(x['source']).name.lower()=='ntdll.dll')
                row['rawWineLogSha256']=sha(work/'wine.log');row['rawWineLogBytes']=(work/'wine.log').stat().st_size
                print(key,'PASS' if row['passed'] else 'FAIL',flush=True)
    report['passed']=all(x['passed'] for x in report['tests'].values())
finally:
    if a.sdl_dll:
        report['originalDLLUnchanged']=sha(a.sdl_dll)==report['sdlOriginalSha256']
        if not report['originalDLLUnchanged']:report['passed']=False
    report['completedAtUTC']=datetime.datetime.now(datetime.timezone.utc).isoformat()
    (run/'provider-receipt.json').write_text(json.dumps(report,indent=2)+'\n');print(run/'provider-receipt.json',flush=True)
raise SystemExit(0 if report['passed'] else 1)
