#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 WineVision VR contributors
"""Opt-in actual owned i386 InterlockedExchange controls under isolated Mac Wine.

Each case/mode gets a fresh stock-template prefix, same-build PE providers,
unique create-new marker token and bounded process wait. No game assets, user
prefixes or device actions. Local success validates the x86 protocol/semantics,
not the iOS/FEX RWX alias/SMC bug or an ARM64 handler fix.
"""
import argparse,datetime,hashlib,json,os,shutil,struct,subprocess,tarfile,tempfile,uuid
from pathlib import Path
CASES={
 'rw-aligned':(4,0x208,0),'rw-unaligned':(4,0x207,0),
 'rwx-aligned':(64,0x208,0),'rwx-unaligned':(64,0x207,0),
 'rwx-unaligned-execute':(64,0x207,1)}
p=argparse.ArgumentParser(description=__doc__)
for name in ['build','wine-build','wine-source','freetype-lib','prefix-template','toolchain']:
 p.add_argument('--'+name,type=Path,required=True)
p.add_argument('--template-sha256',required=True)
p.add_argument('--cases',nargs='+',choices=list(CASES),default=list(CASES))
p.add_argument('--modes',nargs='+',choices=['direct','mixed'],default=['direct','mixed'])
a=p.parse_args();sources=Path(__file__).with_name('atomic-controls').resolve()
a.build=a.build.resolve()
assert a.build!=sources and sources not in a.build.parents,'Output must be outside owned probe sources'
def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
 return h.hexdigest()
def machine(path):
 with path.open('rb') as f:
  head=f.read(64);f.seek(struct.unpack_from('<I',head,0x3c)[0]);pe=f.read(6)
 assert pe[:4]==b'PE\0\0'
 return struct.unpack_from('<H',pe,4)[0]
assert sha(a.prefix_template)==a.template_sha256
a.build.mkdir(parents=True,exist_ok=True)
run=Path(tempfile.mkdtemp(prefix='execution-',dir=a.build));(run/'tmp').mkdir()
shutil.copy2(Path(__file__),run/'test_atomic_wine.executed.py')
env=dict(os.environ,TMPDIR=str(run/'tmp'),CLANG_MODULE_CACHE_PATH=str(run/'tmp/cache'),
 WINELOADER=str(a.wine_build/'loader/wine'),WINESERVER=str(a.wine_build/'server/wineserver'),
 WINEDLLPATH=str(a.wine_build/'dlls'),DYLD_FALLBACK_LIBRARY_PATH=str(a.freetype_lib.parent),
 WINEDEBUG='+seh,+loaddll',WINEDLLOVERRIDES='mscoree,mshtml=d')
report={'startedUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'passed':False,
 'scope':__doc__,'deviceActions':False,'freshPrefixInitializationTested':False,'tests':{},
 'helperSha256':sha(run/'test_atomic_wine.executed.py'),
 'wineLoaderSha256':sha(Path(env['WINELOADER'])),'wineServerSha256':sha(Path(env['WINESERVER'])),
 'freetypeSha256':sha(a.freetype_lib),'prefixTemplateSha256':a.template_sha256,'fixtures':{}}
def seed(work):
 prefix=work/'prefix'
 with tarfile.open(a.prefix_template) as archive:
  for member in archive.getmembers():
   n=Path(member.name)
   assert not n.is_absolute() and '..' not in n.parts and n.parts and n.parts[0]=='prefix'
   assert not member.issym() and not member.islnk() and (member.isdir() or member.isfile())
   assert n.suffix.lower() not in ['.dll','.exe','.drv','.sys']
  archive.extractall(work)
 (prefix/'.update-timestamp').write_text(str(int((a.wine_build/'loader/wine.inf').stat().st_mtime))+'\n')
 fonts=prefix/'drive_c/windows/Fonts';fonts.mkdir(parents=True,exist_ok=True)
 for font in (a.wine_source/'fonts').glob('*.ttf'):shutil.copy2(font,fonts/font.name)
 modules=[];destinations=set()
 for arch,system in [('x86_64','system32'),('i386','syswow64')]:
  for origin in a.wine_build.glob('**/'+arch+'-windows/*'):
   if not origin.is_file() or origin.suffix.lower() not in ['.dll','.exe','.drv','.sys','.cpl','.ax','.ocx','.acm']:continue
   dest=prefix/'drive_c/windows'/system
   if origin.suffix.lower()=='.sys':dest=dest/'drivers'
   dest.mkdir(parents=True,exist_ok=True);dest=dest/origin.name
   assert dest not in destinations;destinations.add(dest)
   shutil.copy2(origin,dest)
   modules.append({'source':str(origin),'destination':str(dest),'sha256':sha(dest),'architecture':arch})
 return prefix,modules
try:
 for name,arch in [('atomic32','i686'),('parent64','x86_64')]:
  source=sources/(name+'.c');shutil.copy2(source,run/source.name)
  shutil.copy2(sources/'atomic_protocol.h',run/'atomic_protocol.h')
  exe=run/(name+'.exe')
  command=[str(a.toolchain/'bin'/(arch+'-w64-mingw32-gcc')),'-std=c11','-O2','-municode',
           '-Wall','-Wextra','-Werror',str(source),'-o',str(exe)]
  subprocess.run(command,env=env,check=True,timeout=60)
  assert machine(exe)==(0x14c if arch=='i686' else 0x8664)
  report['fixtures'][name]={'path':str(exe),'sha256':sha(exe),'sourceSha256':sha(source),
                            'headerSha256':sha(sources/'atomic_protocol.h'),'command':command}
 for case in a.cases:
  for mode in a.modes:
   key=case+'-'+mode;work=run/key;work.mkdir()
   prefix,modules=seed(work);env['WINEPREFIX']=str(prefix)
   token=uuid.uuid4().hex;child=run/'atomic32.exe';parent=run/'parent64.exe'
   args=[str(child),case,token]
   command=[env['WINELOADER']]+([str(parent)]+args if mode=='mixed' else args)
   row={'case':case,'mode':mode,'token':token,'command':command,'passed':False,'installedPEModules':modules}
   report['tests'][key]=row
   try:
    with (work/'wine.log').open('wb') as log:
     status=subprocess.run(command,cwd=work,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=45)
    row['exitCode']=status.returncode;assert status.returncode==0,'Owned process failed'
    markers={}
    for stage in ['prepared','before','after']:
     path=work/('atomic-'+token+'-'+case+'.'+stage+'.json')
     data=json.loads(path.read_text());markers[stage]=data
     row.setdefault('markerFiles',{})[stage]={'path':str(path),'sha256':sha(path)}
     protect,offset,execute=CASES[case]
     assert data['fixture']=='owned-atomic-v1' and data['case']==case and data['token']==token
     assert data['pointerBits']==32 and data['protect']==protect and data['offset']==offset and data['executeStub']==execute
    assert len({m['childPID'] for m in markers.values()})==1
    assert markers['prepared']['stage']=='prepared' and markers['prepared']['apiResolved']==1
    before,after=markers['before'],markers['after']
    assert before['stage']=='beforeExchange' and before['apiResolved']==1 and before['initial']==0x11223344 and before['desired']==0x55667788
    assert after['stage']=='afterExchange' and after['returnedOld']==0x11223344 and after['observedNew']==0x55667788
    assert after['canary']==1 and after['exitCode']==0
    assert before['stubResult']==after['stubResult']==(0x12345678 if execute else 0)
    if mode=='mixed':
     text=(work/'wine.log').read_text(errors='replace')
     assert 'PARENT pointerBits=64' in text and 'CHILD_WOW64=1' in text and 'CHILD_WAIT=0 CHILD_EXIT=0' in text
     assert 'PASS mixed atomic case='+case+' token='+token+' freshMarkers=3 childExit=0' in text
    row.update(markers=markers,passed=True)
   except (AssertionError,subprocess.TimeoutExpired,OSError,ValueError) as error:
    row['error']=repr(error)
   finally:
    cleanup=subprocess.run([env['WINESERVER'],'-k'],env=env,timeout=15,check=False,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    row['prefixScopedCleanupExit']=cleanup.returncode
   for module in modules:assert sha(Path(module['source']))==sha(Path(module['destination']))==module['sha256']
   row['actualI386NTDLL']=next(m for m in modules if m['architecture']=='i386' and Path(m['source']).name.lower()=='ntdll.dll')
   row['rawWineLogSha256']=sha(work/'wine.log');row['rawWineLogBytes']=(work/'wine.log').stat().st_size
   print(key,'PASS' if row['passed'] else 'FAIL',flush=True)
 report['passed']=bool(report['tests']) and all(row['passed'] for row in report['tests'].values())
finally:
 report['completedUTC']=datetime.datetime.now(datetime.timezone.utc).isoformat()
 (run/'atomic-receipt.json').write_text(json.dumps(report,indent=2)+'\n')
 print(run/'atomic-receipt.json',flush=True)
raise SystemExit(0 if report['passed'] else 1)
