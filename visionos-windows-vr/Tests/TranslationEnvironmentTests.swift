import Foundation
@main struct Probe {
 static func main() {
  for name in WindowsVRTranslationEnvironment.defaults.keys { unsetenv(name) }
  setenv("FEX_MAXINST", "1024", 1)
  WindowsVRTranslationEnvironment.applyDefaults()
  precondition(String(cString: getenv("FEX_MAXINST")) == "1024")
  precondition(String(cString: getenv("FEX_MULTIBLOCK")) == "1")
  precondition(String(cString: getenv("FEX_ENABLECODECACHINGWIP")) == "0")
  precondition(String(cString: getenv("FEX_ENABLECODECACHEVALIDATION")) == "0")
  precondition(getenv("MADEIRA_JIT_DUMP") != nil)
  precondition(String(cString: getenv("MADEIRA_JIT_DUMP")) == "0")
  setenv("MADEIRA_JIT_DUMP", "1", 1)
  setenv("FEX_ENABLECODECACHINGWIP", "1", 1)
  WindowsVRTranslationEnvironment.applyDefaults()
  precondition(String(cString: getenv("FEX_ENABLECODECACHINGWIP")) == "1")
  precondition(String(cString: getenv("MADEIRA_JIT_DUMP")) == "1")
  print("PASS: translation defaults apply before Wine, preserve explicit overrides and leave the experimental cache launcher and large fault dump opt-in")
 }
}
