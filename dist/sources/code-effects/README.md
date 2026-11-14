# Code software effects

This original Tetorica C effect rack is BSD-3-Clause; see LICENSE. It is host software after the SID, not a SID hardware effect. The readable browser host is js/native_fx_rack.js and the served WASM is js/native_audio_effect.wasm at the package root.

With Emscripten installed, run from this directory:

```sh
sh scripts/build_native_audio_effect.sh /tmp/tetorica-sid-code-effects
cp /tmp/tetorica-sid-code-effects/gain.wasm ../../js/native_audio_effect.wasm
```

An explicit output directory keeps this standalone rebuild independent of repository artifact-sync tools.
