# Desktop CI menu compatibility — 2026-11-21

- [x] Inspect the latest failed Actions job and identify its first real error.
      Run 44787516348 fails in the browser gate: desktop and imported Web code
      create duplicate synthMenu/menu-button/panel IDs. Build jobs are skipped.
- [x] Reuse the imported Web menu for desktop preset/audio/reload actions,
      preserving New, Import/Export, Files and existing event ownership. Keep
      the older Web-without-menu fallback. Do not modify pinned dist bytes.
- [x] Align desktop browser checks with the imported UI and assert one menu;
      retain actual WASM/AudioWorklet, native IPC routing, save/load and failure
      checks with physical audio muted before startup.
- [x] Run local tests, release-lock verification and the browser gate. Record
      results and the remaining push/Actions step. No release/tag publication.

## Cause and fix

Latest failed job: [run 44787516348](https://github.com/kyorohiro/tetorica-sid-synth-tauri/actions/runs/44787516348/job/136466172599),
commit `c0033c9d35faae4fcf093de254147871feefd53b` (0.99.993).
The browser gate failed because `#synthMenu` matched both the desktop-created
menu and the newly imported Web menu. No OS build had started: all build matrix
jobs depend on that browser gate and were skipped.

The desktop adapter now reuses the supplied menu, preserves New/Cassette,
Import/Export and the original Load SID action, and adds native preset saves,
audio output and Reload to it. The Web helper retains menu event ownership;
repeated mounts do not add duplicate listeners. Older imports without a Web
menu retain the former desktop menu and SID shortcut. Imported dist assets and
their release lock remain unchanged.

The browser checker now asserts one menu/button/panel, retains the Web project
actions, opens the real supplied SID import action, and checks channel-export
meaning without depending on one exact label. Actual native-save bytes and
round trips remain asserted.

## Local verification

- `npm test`: Python **42/42**, Node **49/49** passed. New DOM regressions read
  the actual imported HTML and cover current-menu preservation/unique IDs,
  repeated mounting, handler ownership and legacy menu/keyboard behavior.
- `npm run test:browser -- --out artifacts/ci-menu-20261121/desktop-browser.json --screenshots artifacts/ci-menu-20261121/screenshots`:
  Chromium and WebKit passed **10 stages each**. This is the failed CI command
  with local evidence paths. It covers both actual SID models and song preview,
  independent channels, native binary save/load, Pin, Legato, final PCM routing,
  output switching, cancellation/failure recovery and narrow layout.
- Every browser speaker destination was muted before startup. Native IPC is
  mocked for this test; it does not open a CPAL device or replace listening.
- `python3 scripts/import_release.py --check`: **359 files verified**.
  `git diff --check` passed. Evidence:
  [verification_ci_menu_20261121.json](verification_ci_menu_20261121.json).

The fix is local and uncommitted. Next commit/push this repository so Actions
can execute the browser gate and then the existing OS build matrix. No workflow
dispatch, remote rerun, tag or release publication was performed in this task.
