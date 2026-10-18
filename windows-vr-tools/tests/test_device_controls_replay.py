#!/usr/bin/env python3
"""Replay private r6 direct/mixed evidence through production Controls.run.

Supply preserved external evidence; no device, debugger, package validation or
real subprocess is invoked. Raw logs/PEs remain external and are not in Git.
"""
import argparse
import copy
import importlib.util
import json
from pathlib import Path
import re
import sys
import tempfile
from types import SimpleNamespace

spec=importlib.util.spec_from_file_location('runner',Path(__file__).resolve().parents[1]/'test_device_controls.py')
m=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=m
spec.loader.exec_module(m)


class Clock:
    def __init__(self,wall):self.tick,self.offset=0,wall
    def monotonic(self):return self.tick
    def time(self):return self.offset+self.tick
    def sleep(self,seconds):self.tick+=seconds
    def wall(self,value):self.offset=value-self.tick


class Evidence:
    def __init__(self,root,output):
        self.root,self.output,self.sources=root,output,{}
        self.phases={}
        mixed_launcher=self.read('mixed-recovery/launcher.txt')
        for phase,run in [('direct','device-controls-run-3'),('mixed','mixed-only-run-1')]:
            recovery=phase+'-recovery/'
            verified=self.load(recovery+'verified-'+phase+'-result.json')
            for record in verified['evidence']:
                path=Path(record['path'])
                assert path.is_relative_to(root) and m.sha(path)==record['sha256'], 'Recovered evidence changed: '+path.name
            launch=self.raw(run,phase+'-launch')
            marker=phase+'-child-result.json'
            documents=self.load(recovery+'logs-metadata-after.json')
            if phase=='direct':
                # Later ACTUAL remote runtime row, before mixed launch. Keep its
                # size even though the earlier proof snapshot has fewer bytes.
                later=self.raw('mixed-only-run-1','mixed-prior-logs')
                runtime_row=next(r for r in later['result']['files'] if r['name']=='madeira-log.txt')
                documents['result']['files'].append(copy.deepcopy(runtime_row))
                direct=self.read('device-controls-run-3/direct/capture-008/launcher.txt')
                size=next(r for r in documents['result']['files'] if r['name']=='launcher-log.txt')['metadata']['size']
                # LaunchLog is append-only between rotations. Exact preserved
                # prefix reconstructs the later actual remote5887-byte snapshot.
                assert mixed_launcher.startswith(direct)
                launcher=mixed_launcher[:size]
                assert launcher.endswith(b'\n')
                runtime=self.read('device-controls-run-3/direct/capture-008/runtime.txt')
                archive=self.read(recovery+'launcher.previous-1.txt')
                failure='device-controls-run-3/raw/0034-runtime-copy'
                fail_source='Documents/madeira-log.txt'
                ready=84
            else:
                launcher=mixed_launcher
                runtime=self.read(recovery+'runtime.txt')
                archive=None
                failure='mixed-only-run-1/raw/0021-launcher-copy'
                fail_source='Documents/launcher-log.txt'
                ready=50
            pattern=rb'(ml989: running image|\[WineProc\] Wine exited|CHILD_EXIT|PASS: x64 parent|\[redeliv\] terminating|\[thread-trace\] (exit|abort))'
            # Runtime proof is trimmed without changing remote metadata size.
            runtime=b''.join(line for line in runtime.splitlines(keepends=True) if re.search(pattern,line))
            payloads={'Documents/launcher-log.txt':launcher,'Documents/madeira-log.txt':runtime}
            if archive:payloads['Documents/launcher.previous-1.txt']=archive
            for name in (marker,marker+'.before-seh.json','child32.exe',*(['parent64.exe'] if phase=='mixed' else [])):
                payloads['Documents/WindowsVR/Apps/'+('DirectChildControl' if phase=='direct' else 'MixedArchitectureChild')+'/'+name]=self.read(recovery+name)
            private=output/'private-replay-inputs'/phase
            private.mkdir(parents=True)
            for name,data in payloads.items():(private/Path(name).name).write_bytes(data)
            self.phases[phase]=dict(verified=verified,prior=self.raw(run,phase+'-prior'),
                prior_logs=self.raw(run,phase+'-prior-logs'),processes=self.raw(run,phase+'-prior-processes'),
                launch=launch,files=self.load(recovery+'files-after.json'),documents=documents,payloads=payloads,
                failed=self.load(failure+'.json'),failed_code=self.load(failure+'.command.json')['returnCode'],
                fail_source=fail_source,ready=ready,started=m.timestamp(verified['startedUTC']),
                pid=launch['result']['process']['processIdentifier'])
            assert verified['passed']
        process=self.phases['direct']['launch']['result']['process']
        remote=process['executable'].removeprefix('file://').removesuffix('/WineVisionVR')
        self.device=self.phases['direct']['launch']['result']['deviceIdentifier']
        hashes={phase+'/'+Path(name).name:m.sha(output/'private-replay-inputs'/phase/Path(name).name)
                for phase,values in self.phases.items() for name in values['payloads'] if name.endswith('.exe')}
        assert hashes['direct/child32.exe']==hashes['mixed/child32.exe']
        self.identity=dict(installedBundle=remote,remoteExecutable=remote+'/WineVisionVR',
            pluginUUID=self.phases['direct']['verified']['proof']['runtimePluginUUID'],fixtureSha256=hashes,
            scope='Previously verified actual r6 identity; package preflight not repeated')
        self.lock=self.raw('device-controls-run-3','initial-lock')
        self.apps=self.raw('device-controls-run-3','installed-app')
        m.save(output/'replay-inputs.json',dict(sourceFiles=self.sources,scope=__doc__,
            transformations=['Runtime snapshots retain only actual proof/failure lines; remote sizes unchanged.',
                'Exact archive bytes, marker bytes, PE bytes, launch results and remote metadata retained.',
                'Direct launcher is exact5887-byte prefix of append-only mixed launcher, extending verified capture008 prefix.',
                'Direct runtime metadata is actual later pre-mixed row, size172296 unchanged.',
                'Virtual phase gaps compressed; completed evidence available at84/50 seconds after launch.'],
            phasePIDs={k:v['pid'] for k,v in self.phases.items()},fixtureSha256=hashes))

    def read(self,name):
        path=self.root/name
        data=path.read_bytes()
        self.sources[name]=m.sha(path)
        return data

    def load(self,name):return json.loads(self.read(name))

    def raw(self,run,tag):
        paths=list((self.root/run/'raw').glob('*-'+tag+'.json'))
        assert len(paths)==1,(run,tag)
        return self.load(paths[0].relative_to(self.root).as_posix())


class Replay:
    def __init__(self,evidence,clock,output,mutation):
        self.e,self.clock,self.output,self.mutation=evidence,clock,output,mutation
        self.phase,self.launch_time=None,None
        self.calls,self.launches,self.failures=[],[],set()

    def call(self,args,tag,timeout,trailing=()):
        self.calls.append(dict(args=args,tag=tag,timeout=timeout,trailing=trailing))
        self.clock.tick+=.01
        operation=args[1:3]
        if operation==['info','lockState']:
            if tag in ('direct-lock','mixed-lock'):
                self.phase=tag.removesuffix('-lock')
                self.clock.wall(self.e.phases[self.phase]['started'])
            document=self.e.lock
        elif operation==['info','apps']:document=self.e.apps
        elif operation==['info','processes']:document=self.e.phases[self.phase]['processes']
        elif operation==['process','launch']:
            assert args[3:5]==['--terminate-existing','--activate']
            assert list(trailing)==[m.BUNDLE,'--mixed-architecture-child-test',*(['--direct-child-control'] if self.phase=='direct' else [])]
            self.launches.append(self.phase)
            document=self.e.phases[self.phase]['launch']
            self.launch_time=self.clock.monotonic()
        elif operation==['info','files']:
            values=self.e.phases[self.phase]
            subdir=args[args.index('--subdirectory')+1]
            prior='-prior' in tag
            ready=self.launch_time is not None and self.clock.monotonic()-self.launch_time>=values['ready']
            if subdir=='Documents':
                document=values['prior_logs'] if prior or not ready else copy.deepcopy(values['documents'])
                if self.phase=='direct' and self.mutation=='stale-archive' and not prior and ready:
                    for row in document['result']['files']:
                        if row['name']=='launcher.previous-1.txt':row['metadata']['lastModDate']='2026-10-18T11:00:00Z'
            else:document=values['prior'] if prior or not ready else values['files']
        elif operation==['copy','from']:
            values=self.e.phases[self.phase]
            remote=args[args.index('--source')+1]
            destination=Path(args[args.index('--destination')+1])
            ready=self.clock.monotonic()-self.launch_time>=values['ready']
            data=values['payloads'].get(remote,b'') if ready else b'prior log without current proof\n'
            if ready and remote==values['fail_source'] and self.phase not in self.failures:
                self.failures.add(self.phase)
                destination.write_bytes(data[:max(1,len(data)//2)])
                document=values['failed']
                m.save(self.output/'raw'/f'{len(self.calls):04d}-{tag}.json',document)
                return m.Result(copy.deepcopy(document),values['failed_code'])
            if self.phase=='direct' and self.mutation=='missing-attach' and remote.endswith('launcher.previous-1.txt'):
                data=re.sub(rb'JIT: debugger attached after [^\r\n]*',lambda match:b' '*len(match.group(0)),data)
            if self.phase=='mixed':
                if self.mutation=='missing-parent-exit':data=data.replace(b'CHILD_EXIT code=0 beforeStage=1',b'parent exit proof removed')
                elif self.mutation=='missing-parent-pass':data=data.replace(m.PARENT_PASS.encode(),b'parent proof removed')
                elif self.mutation=='bad-final' and remote.endswith('mixed-child-result.json'):
                    data,count=re.subn(rb'("continuedAfterRaise"\s*:\s*)1',rb'\g<1>0',data);assert count==1
                elif self.mutation=='wrong-pe' and remote.endswith('parent64.exe'):data+=b'corrupted'
            destination.write_bytes(data)
            document=dict(info=dict(outcome='success',commandType='devicectl.device.copy.from'),result={})
        else:raise AssertionError('Unexpected action in replay: '+str(operation))
        m.save(self.output/'raw'/f'{len(self.calls):04d}-{tag}.json',document)
        return m.Result(copy.deepcopy(document))


def run_case(evidence,output,mutation):
    directory=output/mutation
    (directory/'raw').mkdir(parents=True)
    (directory/'tmp').mkdir()
    clock=Clock(evidence.phases['direct']['started'])
    config=SimpleNamespace(output=directory,verified_app=None,install_receipt=None,device=evidence.device,
        unlock_timeout=180,phase_timeout=120,command_timeout=10,poll_interval=2,clock_skew=2,keep_app_open=True)
    replay=Replay(evidence,clock,directory,mutation)
    original=m.package_identity
    try:
        m.package_identity=lambda *args:copy.deepcopy(evidence.identity)
        controls=m.Controls(config,replay,clock)
    finally:m.package_identity=original
    expected=mutation=='combined'
    assert controls.run() is expected,(mutation,controls.report)
    phases=controls.report['phases']
    if expected:
        assert replay.launches==['direct','mixed'] and replay.failures=={'direct','mixed'}
        assert controls.copy_retries==2 and all(p['passed'] for p in phases)
        assert phases[0]['proof']['launcherProofFiles']==['launcher.previous-1.txt','launcher-log.txt']
        assert phases[1]['proof']['parentWaitAndExitVerified'] is True
    elif mutation in ('stale-archive','missing-attach'):assert replay.launches==['direct'] and not phases[0]['passed']
    else:assert replay.launches==['direct','mixed'] and phases[0]['passed'] and not phases[1]['passed']
    assert not list(directory.rglob('*.partial'))
    m.save(directory/'replay-calls.json',replay.calls)
    print('PASS actual-evidence replay:',mutation,'expected pass='+str(expected))
    return dict(case=mutation,passed=True,runnerPassed=controls.report['passed'],launches=replay.launches,
                retries=controls.copy_retries,result=str(directory/'result.json'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--r6',required=True,type=Path)
    parser.add_argument('--build',required=True,type=Path)
    args=parser.parse_args()
    args.build.mkdir(parents=True,exist_ok=True)
    output=Path(tempfile.mkdtemp(prefix='recorded-replay-',dir=args.build.resolve()))
    evidence=Evidence(args.r6.resolve(),output)
    results=[run_case(evidence,output,case) for case in
             ('combined','stale-archive','missing-attach','missing-parent-pass','missing-parent-exit','bad-final','wrong-pe')]
    m.save(output/'summary.json',dict(passed=True,scope='Offline replay only; no new hardware evidence',
                                    cases=results,inputs=str(output/'replay-inputs.json')))
    print('PASS: recorded direct/mixed default-sequence replay; artifacts:',output)


if __name__=='__main__':main()
