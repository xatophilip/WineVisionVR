#!/usr/bin/env python3
"""Compile and execute the actual inactive-prefix CSP migration, with no user hive or Wine execution."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--runtime-source', type=Path, required=True)
p.add_argument('--provider', type=Path, required=True)
p.add_argument('--registered-hive', type=Path, help='Optional owned genuine guest32 registration output, never a user hive')
p.add_argument('--build', type=Path, required=True)
a = p.parse_args()
source = a.runtime_source.resolve()
provider = a.provider.resolve()
output = a.build.resolve()
assert not output.is_relative_to(ROOT) and not output.is_relative_to(source)
assert provider.name == 'rsaenh.dll' and provider.is_file()
rgs = source/'wine/dlls/rsaenh/rsaenh.rgs'
assert rgs.is_file()
output.mkdir(parents=True, exist_ok=True)
work = Path(tempfile.mkdtemp(prefix='prefix-crypto-', dir=output))
header = ROOT/'windows-runtime-plugin/WindowsVRPrefixCrypto.h'
adapter = ROOT/'windows-runtime-plugin/WindowsVRRuntimePlugin.mm'
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
original = {str(path): sha(path) for path in [header, adapter, provider, rgs]}
driver = work/'driver.cpp'
driver.write_text(r'''
#include <string>
#include <cstdio>
#include <cstring>
#include <cstdarg>
#include <fcntl.h>
#include <unistd.h>
static std::string mode, hivePath, documentsRoot, resourceRoot;
static bool injected;
static int ControlledOpen(const char*,int,...);
static int ControlledFsync(int);
static int ControlledRename(int,const char*,int,const char*);
#define open ControlledOpen
#define fsync ControlledFsync
#define renameat ControlledRename
#include "''' + str(header) + r'''"
#undef open
#undef fsync
#undef renameat
static int ControlledOpen(const char* path,int flags,...) {
 if(mode=="deny-parent-opens" && path[0]=='/' && path!=documentsRoot && path!=resourceRoot) {
  errno=EACCES;return -1;
 }
 mode_t permissions=0;
 if(flags&O_CREAT) {va_list args;va_start(args,flags);permissions=va_arg(args,int);va_end(args);}
 return ::open(path,flags,permissions);
}
static int ControlledFsync(int fd) {
 if (!injected && mode=="change-before-commit") {
  injected=true;
  int file=open(hivePath.c_str(),O_WRONLY|O_APPEND);
  if(file<0)return -1;
  const char extra[]=";; external writer\n";
  (void)write(file,extra,sizeof(extra)-1);close(file);
 }
 if(mode=="fail-fsync") {errno=EIO;return -1;}
 return ::fsync(fd);
}
static int ControlledRename(int a,const char*b,int c,const char*d) {
 if(mode=="fail-rename") {errno=EIO;return -1;}
 return ::renameat(a,b,c,d);
}
int main(int argc,char**argv) {
 if(argc==2 && !strcmp(argv[1],"--fragment")) {
  const auto fragment=WVRPrefixCrypto::StockAppend();
  fwrite(fragment.data(),1,fragment.size(),stdout);return 0;
 }
 if(argc!=5)return 64;
 mode=argv[4];documentsRoot=argv[1];resourceRoot=argv[3];hivePath=std::string(argv[1])+"/"+argv[2]+"/system.reg";
 std::string error;
 auto result=WVRPrefixCrypto::Ensure(argv[1],argv[2],argv[3],error);
 printf("RESULT=%d\n%s\n",static_cast<int>(result),error.c_str());
 return 0;
}
''')
binary = work/'driver'
command = ['xcrun','--sdk','macosx','clang++','-std=c++17','-O1','-g',
           '-fsanitize=address,undefined','-fno-omit-frame-pointer',str(driver),'-o',str(binary)]
subprocess.run(command, check=True, timeout=120)
cases = []
bundle = work/'bundle'
bundleProvider = bundle/'Runtime/i386-windows/rsaenh.dll'
bundleProvider.parent.mkdir(parents=True)
shutil.copy2(provider,bundleProvider)
def invoke(name, hive, expected, module=bundle, mode='normal', prepare=None):
    prefix = work/name
    prefix.mkdir()
    (prefix/'system.reg').write_bytes(hive)
    os.chmod(prefix/'system.reg', 0o640)
    if prepare:
        prefix = prepare(prefix) or prefix
    before = (prefix/'system.reg').read_bytes()
    result = subprocess.run([str(binary),str(work),str(prefix.relative_to(work)),str(module),mode],
                            capture_output=True,text=True,timeout=15)
    assert result.returncode == 0, result.stdout+result.stderr
    assert f'RESULT={expected}\n' in result.stdout, name+result.stdout+result.stderr
    after = (prefix/'system.reg').read_bytes()
    if expected == 0:
        assert after.startswith(before) and after[len(before):] == fragment
        assert (prefix/'system.reg').stat().st_mode & 0o777 == 0o640
    elif mode == 'change-before-commit':
        assert after == before+b';; external writer\n'
    else:
        assert after == before, name+' changed registry on refusal/no-op'
    assert not list(prefix.glob('.system.reg.wvr-crypto-*')), name+' leaked temporary file'
    cases.append(dict(name=name,result=expected,bytesBefore=len(before),bytesAfter=len(after),
                      originalPrefixPreserved=after.startswith(before),stdout=result.stdout))
    return prefix
fragment = subprocess.run([str(binary),'--fragment'],check=True,capture_output=True).stdout
base = b'WINE REGISTRY Version 2\n\n#arch=win64\n\n[Software\\\\PrivateSentinel] 17\n"UserSetting"="unchanged"\n'
target = r'Software\\Wow6432Node\\Microsoft\\Cryptography\\Defaults'
added = invoke('absent',base,0)
invoke('sandbox-parent-opens-denied',base,0,mode='deny-parent-opens')
invoke('idempotent',base+fragment,1)
invoke('existing-root',base+('['+target+']\n').encode(),1)
invoke('custom-descendant',base+('['+target+r'\\Provider\\Private Custom CSP]\n"Type"=dword:00000001'+'\n').encode(),1)
invoke('case-insensitive',base+('['+target.upper()+r'\\pRoViDeR tYpEs\\tYpE 001]'+'\n').encode(),1)
invoke('escaped-target',base+('['+target.replace('Software',r'\x0053oftware')+']\n').encode(),1)
invoke('lookalike-is-not-defaults',base+('['+target+'Backup]\n').encode(),0)
invoke('bad-utf8',base+b'\xff',2)
invoke('embedded-nul',base+b'\0',2)
invoke('missing-arch',base.replace(b'#arch=win64',b'; no architecture'),2)
invoke('wrong-arch',base.replace(b'#arch=win64',b'#arch=win32'),2)
invoke('malformed-section',base+b'[unfinished\n',2)
invoke('escaped-nul-key',base+b'[Software\\\\Other\\x0000]\n',2)
invoke('oversize',base+b';'+b'x'*(16*1024*1024),2)
limit=16*1024*1024
near=base+b';'+b'x'*(limit-len(base)-1)
invoke('exact-limit-absent-refused',near,2)
already=base+fragment
invoke('exact-limit-existing-preserved',already+b';'+b'x'*(limit-len(already)-1),1)
fits=base+b';'+b'x'*(limit-len(base)-len(fragment)-1)
invoke('exact-output-limit-migrated',fits,0)

bad = work/'bad-provider'
badFile = bad/'Runtime/i386-windows/rsaenh.dll';badFile.parent.mkdir(parents=True)
badFile.write_bytes(b'')
invoke('empty-module',base,2,module=bad)
badFile.write_bytes(b'MZ'+b'x'*256)
invoke('invalid-module',base,2,module=bad)
wrong = bytearray(provider.read_bytes())
pe = int.from_bytes(wrong[60:64],'little')
wrong[pe+4:pe+6] = b'\x64\x86'
badFile.write_bytes(wrong)
invoke('wrong-machine-module',base,2,module=bad)
invoke('existing-custom-invalid-module-preserved',base+('['+target+r'\\Provider\\Custom]'+'\n').encode(),1,module=bad)
linkdir=work/'linked-provider';linkdir.symlink_to(bundle,target_is_directory=True)
invoke('provider-ancestor-symlink',base,2,module=linkdir)
nested=work/'nested-bundle';nested.mkdir()
(nested/'Runtime').symlink_to(bundle/'Runtime',target_is_directory=True)
invoke('provider-runtime-symlink',base,2,module=nested)
nested2=work/'nested-bundle2';(nested2/'Runtime').mkdir(parents=True)
(nested2/'Runtime/i386-windows').symlink_to(bundle/'Runtime/i386-windows',target_is_directory=True)
invoke('provider-machine-symlink',base,2,module=nested2)
fifoBundle=work/'fifo-bundle';fifoProvider=fifoBundle/'Runtime/i386-windows/rsaenh.dll'
fifoProvider.parent.mkdir(parents=True);os.mkfifo(fifoProvider)
invoke('provider-fifo',base,2,module=fifoBundle)
fifoPrefix=work/'hive-fifo';fifoPrefix.mkdir();os.mkfifo(fifoPrefix/'system.reg')
fifoResult=subprocess.run([str(binary),str(work),fifoPrefix.name,str(bundle),'normal'],
                          capture_output=True,text=True,timeout=5)
assert fifoResult.returncode==0 and 'RESULT=2' in fifoResult.stdout
assert (fifoPrefix/'system.reg').is_fifo() and not list(fifoPrefix.glob('.system.reg.wvr-crypto-*'))
cases.append(dict(name='hive-fifo',result=2,stdout=fifoResult.stdout))

def hive_link(prefix):
    value=prefix/'original';(prefix/'system.reg').rename(value);(prefix/'system.reg').symlink_to(value)
invoke('hive-symlink',base,2,prepare=hive_link)
def prefix_link(prefix):
    alias=prefix.with_name(prefix.name+'-alias');alias.symlink_to(prefix,target_is_directory=True);return alias
invoke('prefix-symlink',base,2,prepare=prefix_link)
def ancestor_link(prefix):
    parent=work/'ancestor-link';parent.symlink_to(work,target_is_directory=True);return parent/prefix.name
invoke('prefix-ancestor-symlink',base,2,prepare=ancestor_link)
def hardlink(prefix):
    os.link(prefix/'system.reg',prefix/'second-link')
invoke('hive-hardlink',base,2,prepare=hardlink)
invoke('write-flush-error',base,2,mode='fail-fsync')
invoke('rename-error',base,2,mode='fail-rename')
invoke('concurrent-content-change',base,2,mode='change-before-commit')

# Parse stock records from actual pinned resource grammar; do not duplicate the
# provider/default-name tables in the test.
expected = {}
# Keep parsing simple numeric/quoted resource values while preserving their types.
for name,body in re.findall(r"ForceRemove '([^']+)'\s*\{([^{}]*)\}",rgs.read_text()):
    values={}
    for match in re.finditer(r"val '([^']+)' = ([sdb])\s+('([^']*)'|[^\s]+)",body):
        value,kind,raw=match.group(1),match.group(2),match.group(4) if match.group(4) is not None else match.group(3)
        values[value] = (kind, int(raw) if kind=='d' else raw.replace('%MODULE%',r'C:\windows\system32\rsaenh.dll').lower() if kind=='b' else raw.replace('%MODULE%',r'C:\windows\system32\rsaenh.dll'))
    branch='Provider Types' if name.startswith('Type ') else 'Provider'
    expected[branch+'\\'+name]=values
def records(text):
    found={}
    for section in re.split(r'\n(?=\[)',text):
        if not section.startswith('['):continue
        key=section.split(']',1)[0][1:].replace('\\\\','\\')
        prefix='Software\\Wow6432Node\\Microsoft\\Cryptography\\Defaults\\'
        if not key.startswith(prefix):continue
        values={}
        for line in section.splitlines()[1:]:
            match=re.match(r'(".*?")=(.*)$',line)
            if not match:continue
            name=json.loads(match.group(1));raw=match.group(2)
            if raw.startswith('"'):values[name]=('s',json.loads(raw))
            elif raw.startswith('dword:'):values[name]=('d',int(raw[6:],16))
            elif raw.startswith('hex:'):values[name]=('b',raw[4:].replace(',','').lower())
        found[key[len(prefix):]]=values
    return found
actual=records(fragment.decode())
assert len(expected)==len(actual)==9 and actual==expected
registeredCompared=False
if a.registered_hive:
    assert records(a.registered_hive.read_text())==expected
    registeredCompared=True
# Verify actual integration ordering and parent/child coverage.
integration=adapter.read_text()
start=integration.index('int32_t RunRequest(')
body=integration[start:integration.index('wineserver_start(prefix.fileSystemRepresentation)',start)]
assert body.index('madeira_seed_prefix_if_needed(') < body.index('if (!prefixReady)') < body.index('WVRPrefixCrypto::Ensure(')
assert 'if (wine_process_is_running() || wineserver_is_running())' in body
assert 'cryptoDocuments.fileSystemRepresentation' in body
assert 'cryptoRelativePrefix.UTF8String' in body
assert 'cryptoResources.path.fileSystemRepresentation' in body
assert 'OpenRoot(documents)' in header.read_text() and 'Walk(root.value, relativePrefix)' in header.read_text()
assert 'Runtime/i386-windows/rsaenh.dll' in body
assert all(sha(Path(path))==value for path,value in original.items())
report=dict(passed=True,scope=__doc__,command=command,cases=cases,
            sourceHashes=original,generatedDriverSha256=sha(driver),
            actualRgsRecordsCompared=9,genuineRegistrationCompared=registeredCompared,
            productionIntegrationBeforeWineStart=True,sourceUnchanged=True,
            limitations=['Source helper and filesystem contract; real Wine/API evidence is a separate owned execution.'])
(work/'result.json').write_text(json.dumps(report,indent=2)+'\n')
print('PASS',len(cases),'actual migration cases; pinned9records; genuineRegistrationCompared=',registeredCompared)
print('Receipt:',work/'result.json')
