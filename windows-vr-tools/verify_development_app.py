#!/usr/bin/env python3
"""Check a signed WineVision development app before installation; never uses a device."""
import argparse
import json
from pathlib import Path
import plistlib
import subprocess
import sys

MEMORY_ENTITLEMENT = "com.apple.developer.kernel.increased-memory-limit"
TEAM_ENTITLEMENT = "com.apple.developer.team-identifier"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def command_plist(arguments):
    result = subprocess.run(arguments, capture_output=True, check=True)
    return plistlib.loads(result.stdout)


def permitted_identifier(allowed, signed):
    # Apple provisioning profiles may use an exact App ID or a trailing wildcard.
    if not isinstance(allowed, str) or not isinstance(signed, str):
        return False
    if allowed.endswith(".*") and allowed.count("*") == 1:
        return signed.startswith(allowed[:-1])
    return allowed == signed


def verify(app, bundle_id, team_id, benchmark):
    require(app.is_dir(), "App bundle does not exist")
    subprocess.run(["codesign", "--verify", "--deep", "--strict", str(app)],
                   check=True, capture_output=True)
    info = plistlib.loads((app / "Info.plist").read_bytes())
    require(info.get("CFBundleIdentifier") == bundle_id,
            "Application bundle identifier does not match --bundle-id")
    schemes = info.get("LSApplicationQueriesSchemes", [])
    require(isinstance(schemes, list) and
            {"stikdebug", "stikjit"}.issubset(schemes),
            "Missing StikDebug/JIT URL query schemes")
    jit_script = app / "madeira-jit.js"
    require(jit_script.is_file() and jit_script.stat().st_size > 0,
            "Missing or empty Madeira debugger protocol script")
    if benchmark:
        require(info.get("WVRDiagnostics") is True,
                "Benchmark diagnostics must be a plist boolean true")
        require(info.get("WVRFrameCapture") is False,
                "Benchmark frame capture must be a plist boolean false")

    signed = command_plist(["codesign", "-d", "--entitlements", ":-", str(app)])
    require(signed.get("get-task-allow") is True,
            "Signed app does not permit debugger attachment")
    require(signed.get(MEMORY_ENTITLEMENT) is True,
            "Signed app lacks the increased-memory-limit entitlement")
    require(signed.get(TEAM_ENTITLEMENT) == team_id,
            "Signed development team does not match --team-id")

    profile = command_plist(["security", "cms", "-D", "-i",
                             str(app / "embedded.mobileprovision")])
    allowed = profile.get("Entitlements", {})
    require(allowed.get("get-task-allow") is True,
            "Provisioning profile does not permit debugger attachment")
    require(allowed.get(MEMORY_ENTITLEMENT) is True,
            "Provisioning profile does not permit increased memory")
    require(team_id in profile.get("TeamIdentifier", []),
            "Provisioning profile team does not match --team-id")
    require(allowed.get(TEAM_ENTITLEMENT) == team_id,
            "Provisioning profile entitlement team does not match signed team")
    signed_app_id = signed.get("application-identifier")
    prefixes = profile.get("ApplicationIdentifierPrefix", [])
    require(any(signed_app_id == prefix + "." + bundle_id
                for prefix in prefixes if isinstance(prefix, str)),
            "Signed application identifier does not match bundle ID and profile prefix")
    require(permitted_identifier(allowed.get("application-identifier"), signed_app_id),
            "Provisioning profile does not permit the signed application identifier")

    result = dict(applicationBundleIdentifier=bundle_id, developmentTeam=team_id,
                  signatureVerified=True, provisioningIdentityMatched=True,
                  debuggerAttachmentAllowed=True, increasedMemoryLimit=True,
                  jitProtocolIncluded=True,
                  scope="Signed bundle checks only; no headset JIT/game run")
    if benchmark:
        result.update(diagnostics=True, frameCapture=False)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("app", type=Path, help="Path to the signed .app bundle")
    parser.add_argument("--bundle-id", required=True,
                        help="Expected application bundle identifier")
    parser.add_argument("--team-id", required=True,
                        help="Expected Apple development team identifier")
    parser.add_argument("--benchmark", action="store_true",
                        help="Also require diagnostics enabled and frame capture disabled")
    args = parser.parse_args()
    try:
        result = verify(args.app.resolve(), args.bundle_id, args.team_id, args.benchmark)
    except (OSError, ValueError, plistlib.InvalidFileException,
            subprocess.CalledProcessError) as error:
        if isinstance(error, subprocess.CalledProcessError):
            detail = error.stderr.decode(errors="replace").strip() if error.stderr else str(error)
        else:
            detail = str(error)
        print("FAIL: " + detail, file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
