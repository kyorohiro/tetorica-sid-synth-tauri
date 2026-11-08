// The pinned Web app exposes the guarded audio bridge. Keep this desktop
// adapter separate so imported sources remain byte-for-byte reusable.
(() => {
  'use strict';
  const local = (location.protocol === 'tauri:' && location.hostname === 'localhost') ||
    (['http:', 'https:'].includes(location.protocol) && location.hostname === 'tauri.localhost');
  if (window.top !== window || !local || !window.__TAURI_INTERNALS__) return;
  if (!window.tetoricaSynthAudio?.setOutputHandler) {
    console.error('The imported SID Synth does not provide the desktop audio bridge.');
    return;
  }
  window.dispatchEvent(new Event('tetorica-synth-ready'));
})();
