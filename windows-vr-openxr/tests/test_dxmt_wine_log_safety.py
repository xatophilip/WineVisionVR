#!/usr/bin/env python3
"""Run production DXMT formatting/logger code against a Wine C-string sink.

Requires a DXMT checkout with patch 0026. No Windows runtime or device required.
The fixture substitutes only platform plumbing; emitMsg, str::format and the
foveation WARN expression are extracted unchanged from the prepared source.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import tempfile


def function(text, signature):
    start = text.index(signature)
    opening = text.index('{', start)
    depth, end = 1, opening + 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dxmt-source', required=True, type=Path)
    parser.add_argument('--output-dir', type=Path)
    args = parser.parse_args()
    logger_path = args.dxmt_source / 'src/util/log/log.cpp'
    context_path = args.dxmt_source / 'src/dxmt/dxmt_context.cpp'
    string_path = args.dxmt_source / 'src/util/util_string.hpp'
    logger, context, strings = (p.read_text() for p in (logger_path, context_path, string_path))
    emit = function(logger, 'void Logger::emitMsg(')
    formats = strings[strings.index('inline void format1('):strings.index('inline void strlcpy(')]
    diagnostic = re.search(r'WARN\("wvr-foveation passes=".*?;', context, re.S).group()
    code = r'''
#include <array>
#include <cassert>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iostream>
#include <mutex>
#include <sstream>
#include <string>
#include <utility>
#include <vector>
using WCHAR = wchar_t;
namespace dxmt {
using mutex = std::mutex;
namespace str {
std::string fromws(const WCHAR *) { return "wide"; }
std::string topath(const char *value) { return value; }
'''+formats+r'''
}
enum class LogLevel : uint32_t { Trace, Debug, Info, Warn, Error, None };
class Logger {
 public:
  LogLevel m_minLevel = LogLevel::Info;
  std::string m_fileName;
  mutex m_mutex;
  bool m_initialized = true;
  std::ofstream m_fileStream;
  int (*m_wineLogOutput)(const char *) = nullptr;
  std::string getFileName(const std::string &) { return {}; }
  void emitMsg(LogLevel level, const std::string &message);
};
'''+emit+r'''
}
// C-string truncation and newline accumulation match Wine's __wine_dbg_output.
static std::string pending;
static std::vector<std::string> calls;
static int wineOutput(const char *value) {
  std::string visible(value);
  calls.push_back(visible);
  auto newline = visible.find_last_of('\n');
  if (newline == std::string::npos) pending += visible;
  else pending = visible.substr(newline + 1);
  // A truncated record must not accumulate into Wine's bounded output buffer.
  assert(pending.size() < 1024);
  return static_cast<int>(visible.size());
}
int main(int argc, char **argv) {
  assert(argc == 2);
  dxmt::Logger logger;
  logger.m_wineLogOutput = wineOutput;
  logger.m_fileStream.open(argv[1], std::ios::binary);
  auto warn = [&](const std::string &text) { logger.emitMsg(dxmt::LogLevel::Warn, text); };
#define WARN(...) warn(dxmt::str::format(__VA_ARGS__))
  struct { uint8_t default_raster_sample_count = 0, render_target_array_length = 1; } render_pass_info;
  struct { uint32_t foveation_draw_calls = 3; bool use_visibility_result = false; void *last_pso = nullptr; uint8_t render_target_count = 2; } object;
  auto data = &object;
  uint64_t passes = 1024, safePasses = 1000, eligiblePasses = 990;
  bool foveationPeer = true;
'''+diagnostic+r'''
  assert(calls.back().find("samples=0 array=1 colors=2\n") != std::string::npos);
  assert(calls.back().find('\0') == std::string::npos);
  for (uint8_t count : { uint8_t(0), uint8_t(1), uint8_t(255) }) {
    render_pass_info.default_raster_sample_count = count;
    render_pass_info.render_target_array_length = count;
'''+diagnostic+r'''
    assert(calls.back().find("samples=" + std::to_string(count)) != std::string::npos);
    assert(calls.back().back() == '\n');
  }
  // The old logger truncates at the first zero, drops the newline and fills
  // Wine's thread-local debug buffer after repeated ordinary diagnostics.
  const std::string binary("first\0middle\0last\nsecond\0tail", 29);
  for (unsigned i = 0; i < 5000; ++i) warn(binary);
  assert(pending.empty());
  assert(calls[calls.size()-2] == "warn:  first\\0middle\\0last\n");
  assert(calls.back() == "warn:  second\\0tail\n");
  warn("ordinary text\nsecond line");
  assert(calls[calls.size()-2] == "warn:  ordinary text\n");
  assert(calls.back() == "warn:  second line\n");
  auto count = calls.size();
  logger.emitMsg(dxmt::LogLevel::Debug, binary);
  assert(calls.size() == count);
  logger.m_fileStream.flush();
  std::ifstream file(argv[1], std::ios::binary);
  std::string saved((std::istreambuf_iterator<char>(file)), {}), expected;
  for (const auto &call : calls) expected += call;
  assert(saved == expected && saved.find('\0') == std::string::npos);
  std::cout << "PASS: production foveation numeric fields, 5000 binary records, Wine newline safety, file parity, multiline and filtering\n";
}
'''
    output = args.output_dir or Path(tempfile.mkdtemp(prefix='wvr-log-nul-'))
    output.mkdir(parents=True, exist_ok=True)
    source = output / 'logger-nul-safety.cpp'
    source.write_text(code)
    command = ['xcrun', 'clang++', '-std=c++17', '-O1', '-g', '-fsanitize=address,undefined',
               '-fno-omit-frame-pointer', str(source), '-o', str(output / 'logger-nul-safety')]
    print(shlex.join(command), flush=True)
    subprocess.run(command, check=True)
    result = subprocess.run([str(output / 'logger-nul-safety'), str(output / 'logger-output.txt')],
                            check=True, capture_output=True, text=True)
    print(result.stdout, end='')
    (output / 'result.json').write_text(json.dumps({
        'passed': True, 'command': command, 'result': result.stdout.strip(),
        'sourceSHA256': {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in (logger_path, context_path, string_path)},
    }, indent=2) + '\n')


if __name__ == '__main__':
    main()
