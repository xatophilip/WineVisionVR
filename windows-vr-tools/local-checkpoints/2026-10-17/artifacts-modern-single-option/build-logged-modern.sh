#!/bin/bash
set -euo pipefail
source /Volumes/XRDev/build/WineVisionVR/env.sh
export AVPPLAY_ENABLE_X86=0
work=/Volumes/XRDev/build/WineVisionVR/artifacts-modern-single-option
python3 "$work/assembly-audit.py" preflight
xcodegen generate --spec "$work/project.yml" --project "$work"
# Generated project must contain only the app; both native frameworks are inputs.
python3 -c 'import pathlib,re; p=pathlib.Path("/Volumes/XRDev/build/WineVisionVR/artifacts-modern-single-option/LoggedModernWineVision.xcodeproj/project.pbxproj").read_text(); assert len(re.findall(r"isa = PBXNativeTarget;",p))==1; assert "WindowsRuntimePlugin.mm" not in p; assert "WindowsVRNativeBridge.framework in Embed Frameworks" in p; assert p.index("/* Embed Frameworks */,") < p.index("/* Verify compatible Metal ABI and restore exact archival native/runtime assembly */,")'
xcodebuild -project "$work/LoggedModernWineVision.xcodeproj" -scheme VisionOSWindowsVR -configuration Release -destination 'generic/platform=visionOS' -derivedDataPath "$work/xcode-derived" -clonedSourcePackagesDirPath "$work/swift-packages" -allowProvisioningUpdates DEVELOPMENT_TEAM="$AVPPLAY_DEVELOPMENT_TEAM" CODE_SIGN_STYLE=Automatic 'CODE_SIGN_IDENTITY=Apple Development' build
app="$work/xcode-derived/Build/Products/Release-xros/WineVision VR.app"
python3 "$work/assembly-audit.py" verify "$app"
codesign --verify --deep --strict "$app"
python3 /Volumes/XRDev/build/WineVisionVR/verify-local-app.py "$app"
python3 -c 'import json,pathlib,subprocess; app=pathlib.Path("/Volumes/XRDev/build/WineVisionVR/artifacts-modern-single-option/xcode-derived/Build/Products/Release-xros/WineVision VR.app"); v=json.loads((app/"WineVisionAssemblyAudit.json").read_text()); v["status"]="signed-bundle-assembly-verified-not-device-tested"; v["applicationUUID"]=subprocess.check_output(["xcrun","dwarfdump","--uuid",str(app/"WineVision VR")],text=True).strip(); pathlib.Path("/Volumes/XRDev/build/WineVisionVR/artifacts-modern-single-option/final-assembly-result.json").write_text(json.dumps(v,indent=2)+"\n")'
echo "Built and verified archival-modern Swift logger app: $app"
