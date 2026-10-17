"""Execute the patched host's bounded environment reader under sanitizers."""
from pathlib import Path
import os
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class DockLaunchArgumentsTests(unittest.TestCase):
    def test_production_reader_and_both_launch_calls(self):
        source_root = Path(os.environ.get("AVPPLAY_MADEIRA_STEAM_SOURCE", ROOT / "third-party/madeira"))
        original = source_root / "madeira-dock/src/launch.c"
        if not original.is_file():
            self.skipTest("Pinned Madeira Dock source is not fetched")
        patch = ROOT / "windows-vr-tools/patches/madeira-dock/0001-bounded-launch-arguments.patch"
        with tempfile.TemporaryDirectory() as scratch:
            work = Path(scratch)
            (work / "src").mkdir()
            shutil.copy2(original, work / "src/launch.c")
            subprocess.run(["git", "-C", str(work), "apply", "--include=src/launch.c", str(patch)], check=True)
            source = (work / "src/launch.c").read_text()
            calls = re.findall(r"\(\(launch_fn\).*?;", source)
            self.assertEqual(len(calls), 2)
            self.assertTrue(all("launch_option, 0, launch_args)" in call for call in calls))
            reader = "static bool read_launch_args(" + source.split("static bool read_launch_args(", 1)[1].split("\nstruct saved_value", 1)[0]
            harness = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
typedef uint32_t DWORD;
#define ERROR_SUCCESS 0
#define ERROR_ENVVAR_NOT_FOUND 203
static DWORD last_error, injected_error;
static const char *value;
static void SetLastError(DWORD error) { last_error = error; }
static DWORD GetLastError(void) { return last_error; }
static DWORD GetEnvironmentVariableA(const char *key, char *out, DWORD capacity) {
    assert(!strcmp(key, "MADEIRA_STEAM_HOST_EXTRA_ARGS"));
    if (injected_error) { last_error = injected_error; return 0; }
    if (!value) { last_error = ERROR_ENVVAR_NOT_FOUND; return 0; }
    size_t size = strlen(value);
    if (size >= capacity) return size + 1;
    memcpy(out, value, size + 1);
    return size;
}
'''
            probe = r'''
int main(void) {
    char out[2048], limit[2049];
    assert(read_launch_args(out, sizeof(out)) && out[0] == 0);
    value = "";
    assert(read_launch_args(out, sizeof(out)) && out[0] == 0);
    value = "-vrmode openvr -label \"two words\"";
    assert(read_launch_args(out, sizeof(out)) && !strcmp(out, value));
    memset(limit, 'x', sizeof(limit)); limit[2047] = 0; value = limit;
    assert(read_launch_args(out, sizeof(out)) && strlen(out) == 2047);
    limit[2047] = 'x'; limit[2048] = 0;
    assert(!read_launch_args(out, sizeof(out)));
    injected_error = 5;
    assert(!read_launch_args(out, sizeof(out)));
    assert(!read_launch_args(NULL, sizeof(out)));
    assert(!read_launch_args(out, 0));
    return 0;
}
'''
            unit = work / "probe.c"
            unit.write_text(harness + reader + probe)
            subprocess.run(["xcrun", "clang", "-std=c11", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined", str(unit), "-o", str(work / "probe")], check=True)
            subprocess.run([str(work / "probe")], check=True)
