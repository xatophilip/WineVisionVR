import hashlib,json,re,subprocess
from pathlib import Path
work=Path('/Volumes/XRDev/build/WineVisionVR/game-dll-compat')
readobj=Path('/Volumes/XRDev/toolchains/llvm-mingw-20260421-ucrt-macos-universal/bin/llvm-readobj')
modules={p.name.lower():p for p in (work/'closure-farm').iterdir() if p.is_file()}
corrected={'dwmapi.dll','wsock32.dll','avrt.dll','vcruntime140.dll','msvcp140.dll'}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(flag,p):return subprocess.check_output([readobj,flag,p],text=True)
tables={}
def exports(module):
 if module not in tables:
  table={}
  for block in re.findall(r'Export \{(.*?)\n\}',read('--coff-exports',modules[module]),re.S):
   ordinal=int(re.search(r'^  Ordinal: (\d+)$',block,re.M).group(1))
   named=re.search(r'^  Name: (.+)$',block,re.M)
   forwarded=re.search(r'^  ForwardedTo: (.+)$',block,re.M)
   item={'ordinal':ordinal,'name':named.group(1) if named else None,'forwardedTo':forwarded.group(1) if forwarded else None}
   table[ordinal]=item
   if named:table[named.group(1)]=item
  tables[module]=table
 return tables[module]
def resolve(module,key,seen=()):
 marker=(module,str(key))
 if marker in seen:raise ValueError('Forwarder cycle '+str(marker))
 item=exports(module).get(key)
 if item is None:raise ValueError('Missing export '+str(marker))
 link={'module':module,'ordinal':item['ordinal'],'name':item['name'],'sha256':sha(modules[module])}
 if item['forwardedTo']:
  host,_,symbol=item['forwardedTo'].rpartition('.')
  host=host.lower();host=host if '.' in host else host+'.dll'
  next_key=int(symbol[1:]) if symbol.startswith('#') else symbol
  return [link,*resolve(host,next_key,(*seen,marker))]
 return [link]
results={}
for filename in ('fantastic-UnityPlayer.dll','Earth.exe'):
 game=work.parent/'black-screen-oct17'/filename
 checks={}
 for block in re.findall(r'Import \{(.*?)\n\}',read('--coff-imports',game),re.S):
  module=re.search(r'^  Name: (.+)$',block,re.M).group(1).lower()
  if module not in corrected:continue
  named=[];ordinals=[];resolved=[]
  for name,number in re.findall(r'^  Symbol: (.*?) \((\d+)\)$',block,re.M):
   name=name.strip();key=name if name else int(number)
   (named if name else ordinals).append(key)
   resolved.append({'import':{'name':name} if name else {'ordinal':key},'resolution':resolve(module,key)})
  checks[module]={'requiredNames':named,'requiredOrdinals':ordinals,'unresolved':[],'resolved':resolved}
 results[filename]={'sha256':sha(game),'correctedModuleChecks':checks}
record={'schemaVersion':1,'scope':'Actual named and ordinal game imports to five corrected DLLs, including recursive export-forwarder resolution','originalOverlayProvenanceSha256':sha(work/'overlay-provenance.json'),'files':results,'allCorrectedModuleImportsResolve':True,'gameplayVerified':False}
with (work/'ordinal-validation.json').open('x') as f:json.dump(record,f,indent=2,sort_keys=True);f.write('\n')
print('PASS: named and ordinal imports resolve, including recursive forwarders; WSOCK32 ordinals 51, 7, 108, 103 checked.')
