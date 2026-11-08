# SID file preview and voice capture

The synthesizer's instrument voices use the CPU-free SID core. Its separate
SID-file preview runs the existing bounded C64 player to execute a tune and
capture current voice registers. It does not recover the complete original
instrument, elapsed envelope, oscillator phase or later song automation.

The Synth import screen uses the ROM-free C64 path for supported PAL single-SID
PSID / RSID files. No game music, user firmware or recorded PCM is included.

- [6581 C64 player sources and rebuild recipe](sid-rsid/README.md): 29 compiled inputs.
- [Direct VBI player sources and rebuild recipe](sid-player/README.md): 14 compiled inputs;
  retained with the shared player factory and its checked asset URL.
- [8580 source kit](sid8580-machine/README.md): 99 compiled inputs for the endpoint
  and C64 machine WASMs, with matching licenses and toolchain notices.

The generated/ directories contain each exact WASM and its source-hash receipt.
The standalone SID instrument's 13-input kit remains at [sid/](sid/README.md).
All browser modules remain readable and independently editable.
