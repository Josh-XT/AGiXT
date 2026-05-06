/* TTS playback queue.
 *
 * Mirrors the kids app's daily-chat audio behavior: assistant responses can
 * include audio URLs (markdown-style or returned via the prompt response);
 * we play them back-to-back automatically.
 */
(function () {
  const audio = document.getElementById('tts-audio');
  const queue = [];
  let speaking = false;
  const SAFE_AUDIO_DATA_URL = /^data:audio\/(?:mpeg|mp3|wav|ogg|mp4|m4a|flac|aac);base64,[a-z0-9+/=\s]+$/i;

  function normalizeAudioUrl(value) {
    const raw = String(value || '').trim();
    if (!raw || /[\u0000-\u001f\u007f]/.test(raw)) return '';
    if (SAFE_AUDIO_DATA_URL.test(raw)) return raw;
    try {
      const base = document.baseURI || (window.location && window.location.href) || 'http://localhost/';
      const parsed = new URL(raw, base);
      if (parsed.protocol === 'http:' || parsed.protocol === 'https:' || parsed.protocol === 'blob:') {
        return parsed.href;
      }
    } catch (_) {
      return '';
    }
    return '';
  }

  function setSpeaking(v) {
    speaking = v;
    const status = document.getElementById('composer-status');
    if (!status) return;
    if (v) {
      status.textContent = '🔊 Speaking…';
      status.classList.add('speaking');
    } else if (status.classList.contains('speaking')) {
      status.textContent = '';
      status.classList.remove('speaking');
    }
  }

  function next() {
    if (!audio) return;
    if (queue.length === 0) { setSpeaking(false); return; }
    const url = normalizeAudioUrl(queue.shift());
    if (!url) { next(); return; }
    audio.setAttribute('src', url);
    setSpeaking(true);
    const p = audio.play();
    if (p && typeof p.catch === 'function') {
      p.catch((err) => {
        // Autoplay blocked — surface in status, drop the queue.
        console.warn('TTS autoplay blocked', err);
        setSpeaking(false);
        queue.length = 0;
      });
    }
  }

  if (audio) {
    audio.addEventListener('ended', next);
    audio.addEventListener('error', () => { console.warn('TTS error'); next(); });
  }

  function enqueue(url) {
    const safe = normalizeAudioUrl(url);
    if (!safe) return;
    queue.push(safe);
    if (!speaking) next();
  }

  function stop() {
    queue.length = 0;
    if (audio) {
      audio.pause();
      try { audio.currentTime = 0; } catch (_) { /* ignore */ }
    }
    setSpeaking(false);
  }

  // Scan a freshly-rendered text fragment for audio URLs and queue them.
  function scanForAudio(text) {
    if (!text) return;
    const re = /https?:\/\/[^\s)]+\.(?:mp3|wav|ogg|m4a|flac|aac)(?:\?[^\s)]*)?/gi;
    let m;
    while ((m = re.exec(text)) !== null) enqueue(m[0]);
  }

  window.AgixtAudio = { enqueue, stop, scanForAudio };
})();
