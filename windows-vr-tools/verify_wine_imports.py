#!/usr/bin/env python3
"""Check packaged PE imports and export forwarders without executing Windows code."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess


def dependencies(imports, exports):
    names = {name.lower() for name in re.findall(r"^  Name: (.+)$", imports, re.M)}
    for target in re.findall(r"\(forwarded to ([^()\s]+)\)", exports):
        module, separator, _ = target.rpartition(".")
        if separator:
            module = module.lower()
            names.add(module if module.endswith((".dll", ".drv", ".exe")) else module + ".dll")
    return names


def missing_dependencies(graph, available):
    missing = {}
    for importer, names in graph.items():
        for name in names:
            if name.startswith(("api-ms-", "ext-ms-")):
                continue  # Resolved through the separately verified apisetschema.dll.
            if name not in available:
                missing.setdefault(name, []).append(importer)
    return {name: sorted(importers) for name, importers in sorted(missing.items())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("farm", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    toolchain = Path(os.environ.get("AVPPLAY_LLVM_MINGW_ROOT", "/nonexistent")) / "bin"
    tools = {}
    for name in ("llvm-readobj", "llvm-objdump"):
        candidate = toolchain / name
        tools[name] = str(candidate) if candidate.is_file() else shutil.which(name)
        if not tools[name]:
            parser.error(f"Set AVPPLAY_LLVM_MINGW_ROOT or provide {name} on PATH")
    files = sorted(p for p in args.farm.iterdir() if p.is_file() and
                   p.suffix.lower() in (".dll", ".exe", ".drv"))
    if not files:
        parser.error("The PE resource directory is empty")
    graph = {}
    for path in files:
        imports = subprocess.check_output([tools["llvm-readobj"], "--coff-imports", str(path)], text=True)
        exports = subprocess.check_output([tools["llvm-objdump"], "-p", str(path)], text=True)
        graph[path.name] = dependencies(imports, exports)
    missing = missing_dependencies(graph, {p.name.lower() for p in files})
    result = {"checkedFiles": len(files), "missingDependencies": missing,
              "scope": "Static imports, delay imports and export forwarders; dynamic LoadLibrary names and runtime behavior are not proven",
              "tools": tools}
    if args.output:
        args.output.write_text(json.dumps(result, indent=2) + "\n")
    if missing:
        for name, parents in missing.items():
            print(f"error: Missing PE dependency {name}, referenced by {', '.join(parents)}")
        return 1
    print(f"Wine PE imports/forwarders verified across {len(files)} binaries.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
