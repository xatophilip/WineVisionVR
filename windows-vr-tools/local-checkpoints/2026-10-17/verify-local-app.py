#!/usr/bin/env python3
"""Verify this Mac's actual signed WineVision bundle before device installation."""
import json
from pathlib import Path
import plistlib
import subprocess
import sys

app = Path(sys.argv[1]).resolve()
expected_id = 'com.philipanderson.WineVisionVR'
expected_team = 'ZUFPF3R7HP'
info = plistlib.loads((app / 'Info.plist').read_bytes())
assert info.get('CFBundleIdentifier') == expected_id, 'Wrong application bundle identifier'
assert info.get('WVRDiagnostics') is True, 'Benchmark diagnostics must be a plist boolean true'
assert info.get('WVRFrameCapture') is False, 'Frame capture must be a plist boolean false'
assert {'stikdebug', 'stikjit'} <= set(info.get('LSApplicationQueriesSchemes', [])), 'Missing JIT URL query schemes'
assert (app / 'madeira-jit.js').stat().st_size > 0, 'Missing Madeira debugger protocol'

result = subprocess.run(['codesign', '-d', '--entitlements', ':-', str(app)], capture_output=True, check=True)
entitlements = plistlib.loads(result.stdout)
assert entitlements.get('get-task-allow') is True, 'Release development build must allow debugger attachment'
assert entitlements.get('com.apple.developer.kernel.increased-memory-limit') is True, 'Increased memory limit was stripped'
assert entitlements.get('application-identifier') == expected_team + '.' + expected_id, 'Signed application identifier mismatch'
assert entitlements.get('com.apple.developer.team-identifier') == expected_team, 'Signing team mismatch'

profile = plistlib.loads(subprocess.check_output(['security', 'cms', '-D', '-i', str(app / 'embedded.mobileprovision')]))
allowed = profile['Entitlements']
assert allowed.get('get-task-allow') is True, 'Provisioning profile does not permit debugging'
assert allowed.get('com.apple.developer.kernel.increased-memory-limit') is True, 'Profile does not permit increased memory'
assert expected_team in profile.get('TeamIdentifier', []), 'Provisioning team mismatch'
print(json.dumps(dict(applicationBundleIdentifier=expected_id, developmentTeam=expected_team,
                     debuggerAttachmentAllowed=True, increasedMemoryLimit=True,
                     diagnostics=True, frameCapture=False,
                     jitProtocolIncluded=True, scope='Signed bundle checks only; no headset JIT/game run'), indent=2))
