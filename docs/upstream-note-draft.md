# Draft note to the original developer

Suggested GitHub issue title: **Experimental fork: compatibility fixes, download improvements and fresh-build notes**

This is a draft for review, not a posted issue or pull request.

---

Hi Hudson — we have an experimental fork that may contain useful fixes:

https://github.com/xatophilip/WineVisionVR/tree/codex/local-build-and-benchmarks

We merged upstream through `76bf424` and kept our desktop window/input work,
Steam download queue and size display, Windows filename handling, session logs,
launch-option selection, extra Wine providers and runtime build documentation.
Background URLSession transfers and suspension recovery are included, but whole
queues completing with the headset off have not been validated.

This was developed with substantial **OpenAI Codex assistance**. It is research
work with limited hardware testing, provided **as-is, without warranty**, under
the existing project licences. We are not claiming the changes are production
ready or expecting you to support our fork.

Current evidence on an M2 Vision Pro with visionOS 27.2:

- Windlands and Job Simulator worked in our earlier preserved runtime build.
- After the upstream source rebuild, Windlands reached a menu/game scene with
  the experimental FEX cache launcher disabled; that is now our app default.
- Space Pirate Trainer is provisional: initially appeared to work, but the latest
  user report is slow loading and only almost working.
- Fantastic Contraption remains slow/unstable. Google Earth VR and Audioshield
  are unresolved. Full 32-bit support remains in development; it is not claimed.

A fresh checkout produced unsigned Debug and signed Release apps using documented
external compiler/prefix inputs. Component, packaging and targeted simulator
checks passed; those checks do not establish game compatibility or sustained FPS.
The reports also describe a GDI child-initialization issue observed with the
experimental cache wrapper; the wrapper is disabled as a workaround, not claimed
fixed in Wine.

Build/recovery details and exact limitations:

- https://github.com/xatophilip/WineVisionVR/blob/codex/local-build-and-benchmarks/docs/windows-vr-reproducibility.md
- https://github.com/xatophilip/WineVisionVR/blob/codex/local-build-and-benchmarks/docs/windows-vr-upstream-integration.md
- https://github.com/xatophilip/WineVisionVR/blob/codex/local-build-and-benchmarks/docs/windows-vr-local-testing.md

Would any of these areas be useful to upstream? We can isolate smaller changes
for review rather than propose a large merge. No pull request has been opened.
