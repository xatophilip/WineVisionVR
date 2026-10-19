#!/usr/bin/env python3
"""Exercise the actual production bridge with real Mac Metal events.

Not Wine/FEX, simulator or headset execution. Optionally require an immutable
baseline bridge to fail at the demonstrated delayed-frame starvation assertion.
Use a fresh --build directory and allow local Metal access.
"""
import argparse, hashlib, json, subprocess
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--build',required=True,type=Path)
p.add_argument('--baseline-source',type=Path)
p.add_argument('--source-root',type=Path,default=Path(__file__).resolve().parents[1])
a=p.parse_args();root=a.source_root.resolve();build=a.build.resolve();build.mkdir(parents=True,exist_ok=True)
bridge=root/'windows-vr-native/Sources/WindowsVRCompositorBridge.mm'
foveation=root/'windows-vr-native/Sources/WindowsVRGuestFoveation.mm'
probe=root/'windows-vr-native/Tests/CompositorBackpressureProbe.mm'
original=root/'windows-vr-native/Tests/SimulatorCompositorProbe.mm'
completion=root/'windows-vr-native/Tests/CompletionWindowTests.cpp'
include=root/'windows-vr-native/include'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
inputs=[Path(__file__).resolve(),bridge,foveation,probe,original,completion,*sorted(include.glob('*'))]
inputs=[path for path in inputs if path.is_file()]
if a.baseline_source:inputs.append(a.baseline_source.resolve())
def hashes():return {str(path):sha(path) for path in inputs}
before=hashes();results=[]
def run(name,source,test,expected_failure=None,metal=True):
 binary=build/name
 command=['xcrun','--sdk','macosx','clang++','-std=c++20','-I',str(include)]
 if metal:command+=['-fobjc-arc',str(source),str(foveation),str(test),'-framework','QuartzCore','-framework','Foundation','-framework','Metal','-framework','CoreFoundation']
 else:command+=[str(test)]
 command+=['-o',str(binary)]
 compiled=subprocess.run(command,capture_output=True,text=True)
 (build/(name+'-compile.log')).write_text(compiled.stdout+compiled.stderr)
 assert compiled.returncode==0,compiled.stderr
 result=subprocess.run([str(binary)],capture_output=True,text=True,timeout=30)
 output=result.stdout+result.stderr;(build/(name+'.log')).write_text(output)
 if expected_failure:
  assert result.returncode==1 and 'FAIL: '+expected_failure in output,output
 else:assert result.returncode==0,output
 results.append(dict(name=name,passed=True,exitCode=result.returncode,expectedFailure=expected_failure,command=command,binarySha256=sha(binary),logSha256=sha(build/(name+'.log'))))
 print(name+': PASS'+(' (expected baseline failure)' if expected_failure else ''),flush=True)
if a.baseline_source:
 run('baseline-starvation',a.baseline_source.resolve(),probe,'delayed frame survives fourth submission and becomes acquirable')
run('fixed-backpressure',bridge,probe)
run('existing-compositor',bridge,original)
run('completion-window',None,completion,metal=False)
assert hashes()==before,'Inputs changed during test'
xr=root/'windows-vr-openxr/src/WindowsVROpenXR.cpp';text=xr.read_text()
assert text.count('if(hr==S_FALSE)TraceCompositorDrop(activeFrameIndex);')==4
assert text.count('FAILED(hr)?XR_ERROR_RUNTIME_FAILURE:XR_SUCCESS')>=4
result=dict(passed=True,scope='Actual production bridge with real Mac Metal events; no Wine/FEX/headset execution.',sourceHashes=before,sourcesUnchanged=True,tests=results,producerSFalseNonfatalSourceSha256=sha(xr),completionWindowUnchanged=6,deviceActionsPerformed=False)
(build/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(build/'result.json')
