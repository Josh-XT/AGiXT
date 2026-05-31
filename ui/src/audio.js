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

  // ---- Streamed PCM playback (interleaved TTS) ---------------------------
  //
  // AGiXT's chat/completions streams the spoken reply as raw little-endian
  // 16-bit PCM, split into `audio.header` / `audio.chunk` / `audio.end`
  // SSE events. We decode each chunk into a Web Audio buffer and schedule
  // it back-to-back so the kid hears the answer read aloud automatically,
  // with a pause/play control. This mirrors the kids app's auto-playback.
  let audioCtx = null;
  let pcmFormat = { sampleRate: 22050, bitsPerSample: 16, channels: 1 };
  let nextStartTime = 0;
  let pcmPlaying = false;
  let pcmPaused = false;
  const scheduledSources = new Set();
  // Decoded buffers for the current reply, kept so the child can replay the
  // spoken answer after it finishes (mirrors the kids app's per-reply control).
  let pcmBuffers = [];
  let segmentEnded = false;
  let toggleBtn = null;
  // The voice control can live either on the composer (`#btn-voice-toggle`,
  // the global fallback) or anchored to the current assistant message bubble
  // (`activeBtn`). chat.js points `activeBtn` at the live reply's per-message
  // button so the pause/replay control sits in the bottom corner of the
  // message it belongs to, mirroring the old kids app's per-reply control.
  let activeBtn = null;

  function globalToggleBtn() {
    if (!toggleBtn) toggleBtn = document.getElementById('btn-voice-toggle');
    return toggleBtn;
  }

  function getToggleBtn() {
    return activeBtn || globalToggleBtn();
  }

  function setToggleVisible(visible) {
    const btn = getToggleBtn();
    if (!btn) return;
    btn.hidden = !visible;
  }

  function setToggleIcon(paused) {
    const btn = getToggleBtn();
    if (!btn) return;
    const pause = btn.querySelector('.voice-icon-pause');
    const play = btn.querySelector('.voice-icon-play');
    if (pause) pause.hidden = paused;
    if (play) play.hidden = !paused;
    btn.setAttribute('aria-label', paused ? 'Resume voice' : 'Pause voice');
    btn.setAttribute('title', paused ? 'Resume voice' : 'Pause voice');
  }

  function ensureAudioCtx() {
    if (audioCtx) return audioCtx;
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return null;
    audioCtx = new Ctx();
    return audioCtx;
  }

  function base64ToBytes(b64) {
    const clean = String(b64 || '').replace(/\s+/g, '');
    if (!clean) return new Uint8Array(0);
    try {
      const binary = atob(clean);
      const len = binary.length;
      const bytes = new Uint8Array(len);
      for (let i = 0; i < len; i += 1) bytes[i] = binary.charCodeAt(i);
      return bytes;
    } catch (_) {
      return new Uint8Array(0);
    }
  }

  function startPcmSegment(meta) {
    const ctx = ensureAudioCtx();
    if (!ctx) return;
    pcmFormat = {
      sampleRate: (meta && meta.sampleRate) || 22050,
      bitsPerSample: (meta && meta.bitsPerSample) || 16,
      channels: (meta && meta.channels) || 1,
    };
    // A new spoken reply: stop any URL-based playback so they don't overlap,
    // and drop the previous reply's buffered audio.
    stop();
    stopPcm();
    pcmBuffers = [];
    segmentEnded = false;
    if (ctx.state === 'suspended') ctx.resume().catch(() => {});
    pcmPaused = false;
    if (nextStartTime < ctx.currentTime) nextStartTime = ctx.currentTime;
    setPcmPlaying(true);
    setToggleIcon(false);
    // The header carries a short WAV-style preamble we can ignore — the
    // chunk events already contain decodable PCM frames.
  }

  // Schedule one decoded AudioBuffer to play gaplessly after whatever is
  // already queued, tracking it so we can pause/stop and detect drain.
  function scheduleBuffer(ctx, buffer, isReplay) {
    const src = ctx.createBufferSource();
    src.buffer = buffer;
    src.connect(ctx.destination);
    if (nextStartTime < ctx.currentTime) nextStartTime = ctx.currentTime;
    try {
      src.start(nextStartTime);
    } catch (_) {
      return;
    }
    nextStartTime += buffer.duration;
    scheduledSources.add(src);
    src.onended = () => {
      scheduledSources.delete(src);
      // When the queue drains, keep the control visible as a replay button
      // if we have the spoken reply buffered; otherwise hide it.
      if (scheduledSources.size === 0 && !pcmPaused) {
        if (pcmBuffers.length && (segmentEnded || isReplay)) {
          pcmPlaying = false;
          setToggleVisible(true);
          setToggleIcon(true); // show the play (replay) icon
          clearSpeakingStatus();
        } else {
          setPcmPlaying(false);
        }
      }
    };
  }

  function pushPcmChunk(b64) {
    const ctx = ensureAudioCtx();
    if (!ctx) return;
    const bytes = base64ToBytes(b64);
    if (!bytes.length) return;
    const bytesPerSample = Math.max(1, pcmFormat.bitsPerSample / 8);
    const channels = Math.max(1, pcmFormat.channels);
    const frameCount = Math.floor(bytes.length / (bytesPerSample * channels));
    if (frameCount <= 0) return;

    const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    const buffer = ctx.createBuffer(channels, frameCount, pcmFormat.sampleRate);
    for (let ch = 0; ch < channels; ch += 1) {
      const channelData = buffer.getChannelData(ch);
      for (let i = 0; i < frameCount; i += 1) {
        const offset = (i * channels + ch) * bytesPerSample;
        // 16-bit signed LE is what AGiXT emits; normalize to [-1, 1].
        const sample = view.getInt16(offset, true);
        channelData[i] = sample / 32768;
      }
    }

    pcmBuffers.push(buffer);
    scheduleBuffer(ctx, buffer, false);
    setPcmPlaying(true);
    setToggleIcon(pcmPaused);
  }

  function endPcmSegment() {
    // All chunks have arrived; mark the segment complete so that once the
    // scheduled sources drain, the toggle becomes a replay button.
    segmentEnded = true;
    if (scheduledSources.size === 0 && pcmBuffers.length) {
      pcmPlaying = false;
      setToggleVisible(true);
      setToggleIcon(true);
      clearSpeakingStatus();
    }
  }

  // Replay the full buffered reply from the start.
  function replayPcm() {
    const ctx = ensureAudioCtx();
    if (!ctx || !pcmBuffers.length) return;
    // Clear any stragglers and reschedule from now.
    scheduledSources.forEach((src) => {
      try { src.stop(); } catch (_) { /* already stopped */ }
    });
    scheduledSources.clear();
    pcmPaused = false;
    if (ctx.state === 'suspended') ctx.resume().catch(() => {});
    nextStartTime = ctx.currentTime;
    pcmBuffers.forEach((buf) => scheduleBuffer(ctx, buf, true));
    setPcmPlaying(true);
    setToggleIcon(false);
  }

  function clearSpeakingStatus() {
    const status = document.getElementById('composer-status');
    if (status && status.classList.contains('speaking')) {
      status.textContent = '';
      status.classList.remove('speaking');
    }
  }

  function setPcmPlaying(v) {
    pcmPlaying = v;
    // Keep the control visible while we have a buffered reply to replay, even
    // after playback finishes — only hide when there's nothing to play.
    setToggleVisible(v || pcmBuffers.length > 0);
    const status = document.getElementById('composer-status');
    if (!status) return;
    if (v && !pcmPaused) {
      status.textContent = '🔊 Speaking…';
      status.classList.add('speaking');
    } else if (status.classList.contains('speaking')) {
      status.textContent = '';
      status.classList.remove('speaking');
    }
  }

  function pausePcm() {
    if (!audioCtx || !pcmPlaying) return;
    pcmPaused = true;
    audioCtx.suspend().catch(() => {});
    setToggleIcon(true);
    const status = document.getElementById('composer-status');
    if (status && status.classList.contains('speaking')) {
      status.textContent = '⏸ Paused';
    }
  }

  function resumePcm() {
    if (!audioCtx) return;
    pcmPaused = false;
    audioCtx.resume().catch(() => {});
    setToggleIcon(false);
    setPcmPlaying(scheduledSources.size > 0);
  }

  function togglePcm() {
    if (pcmPaused) {
      resumePcm();
    } else if (scheduledSources.size > 0) {
      pausePcm();
    } else if (pcmBuffers.length) {
      // Playback finished — act as a replay button.
      replayPcm();
    }
  }

  function stopPcm() {
    scheduledSources.forEach((src) => {
      try { src.stop(); } catch (_) { /* already stopped */ }
    });
    scheduledSources.clear();
    pcmPaused = false;
    if (audioCtx) {
      nextStartTime = audioCtx.currentTime;
      if (audioCtx.state === 'suspended') audioCtx.resume().catch(() => {});
    }
    pcmPlaying = false;
    setToggleVisible(pcmBuffers.length > 0);
    if (pcmBuffers.length) setToggleIcon(true);
    clearSpeakingStatus();
  }

  const btn = getToggleBtn();
  if (btn) {
    btn.addEventListener('click', togglePcm);
  } else {
    // The composer may render after this script; wire on DOM ready.
    document.addEventListener('DOMContentLoaded', () => {
      const b = getToggleBtn();
      if (b) b.addEventListener('click', togglePcm);
    });
  }

  // Reflect the current playback state onto whatever control is active
  // (per-message button or the global composer fallback).
  function syncControlState() {
    const playing = pcmPlaying || pcmBuffers.length > 0;
    setToggleVisible(playing);
    const drained = segmentEnded && scheduledSources.size === 0 && pcmBuffers.length > 0;
    setToggleIcon(pcmPaused || drained);
  }

  // Anchor the voice control to a specific assistant message bubble's button.
  // Hides whatever control was previously active and migrates the live state
  // onto the new one so the pause/replay icon stays correct mid-playback.
  function setActiveVoiceTarget(target) {
    if (target === activeBtn) return;
    const prev = getToggleBtn();
    if (prev && prev !== target) prev.hidden = true;
    activeBtn = target || null;
    if (activeBtn && !activeBtn.dataset.voiceWired) {
      activeBtn.dataset.voiceWired = '1';
      activeBtn.addEventListener('click', togglePcm);
    }
    syncControlState();
  }

  // Drop the per-message anchor (e.g. when a new turn begins) so a stale
  // reply's control doesn't keep showing. Hides every known control.
  function resetVoiceControl() {
    if (activeBtn) activeBtn.hidden = true;
    activeBtn = null;
    const g = globalToggleBtn();
    if (g) g.hidden = true;
  }

  window.AgixtAudio = {
    enqueue,
    stop,
    scanForAudio,
    startPcmSegment,
    pushPcmChunk,
    endPcmSegment,
    pausePcm,
    resumePcm,
    togglePcm,
    stopPcm,
    setActiveVoiceTarget,
    resetVoiceControl,
  };
})();
