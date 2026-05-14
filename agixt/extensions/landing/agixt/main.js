/* AGiXT Landing - vanilla JS bundle for iframe-embedded landing page */
(function () {
  'use strict';

  // ----- Sign-in postMessage protocol -----
  function signin() {
    try {
      window.parent.postMessage({ type: 'landing-action', action: 'signin' }, '*');
    } catch (e) {
      // best-effort
    }
  }

  document.addEventListener('click', function (e) {
    var t = e.target;
    while (t && t !== document.body) {
      if (t.dataset && t.dataset.action === 'signin') {
        e.preventDefault();
        signin();
        return;
      }
      t = t.parentElement;
    }
  });

  // ----- Inline SVG icons (lucide-style) -----
  function svg(path, opts) {
    opts = opts || {};
    var size = opts.size || 24;
    var stroke = opts.stroke || 2;
    return (
      '<svg xmlns="http://www.w3.org/2000/svg" width="' + size + '" height="' + size +
      '" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="' + stroke +
      '" stroke-linecap="round" stroke-linejoin="round">' + path + '</svg>'
    );
  }

  var icons = {
    globe: svg('<circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>'),
    message: svg('<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>'),
    brain: svg('<path d="M12 2a4 4 0 0 0-4 4v2a4 4 0 0 0-4 4v2a4 4 0 0 0 4 4v2a4 4 0 0 0 8 0v-2a4 4 0 0 0 4-4v-2a4 4 0 0 0-4-4V6a4 4 0 0 0-4-4z"/><circle cx="12" cy="12" r="2"/>'),
    shield: svg('<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><polyline points="9 12 11 14 15 10"/>'),
    clock: svg('<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>'),
    users: svg('<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>'),
    settings: svg('<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>'),
    workflow: svg('<rect x="3" y="3" width="6" height="6" rx="1"/><rect x="15" y="15" width="6" height="6" rx="1"/><path d="M21 11V8a2 2 0 0 0-2-2h-7"/><path d="M3 13v3a2 2 0 0 0 2 2h7"/>'),
    zap: svg('<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>'),
    check: svg('<polyline points="20 6 9 17 4 12"/>', { size: 16 }),
    sparkles: svg('<path d="M12 3l1.9 5.6L19.5 10.5l-5.6 1.9L12 18l-1.9-5.6L4.5 10.5l5.6-1.9L12 3z"/>'),
    chevronRight: svg('<polyline points="9 18 15 12 9 6"/>', { size: 16 }),
    phone: svg('<path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/>', { size: 16 }),
    // small chain-demo icons (size 14)
    mic: svg('<path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="23"/><line x1="8" y1="23" x2="16" y2="23"/>', { size: 18 }),
    lock: svg('<rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>', { size: 14 }),
    bulb: svg('<path d="M9 18h6"/><path d="M10 22h4"/><path d="M12 2a7 7 0 0 0-4 12.74V17h8v-2.26A7 7 0 0 0 12 2z"/>', { size: 14 }),
    shieldCheck: svg('<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><polyline points="9 12 11 14 15 10"/>', { size: 14 }),
    thermo: svg('<path d="M14 14.76V3.5a2.5 2.5 0 0 0-5 0v11.26a4.5 4.5 0 1 0 5 0z"/>', { size: 14 }),
    calendar: svg('<rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>', { size: 14 }),
    car: svg('<path d="M14 16H9m10 0h3v-3.15a1 1 0 0 0-.84-.99L16 11l-2.7-3.6a1 1 0 0 0-.8-.4H5.24a2 2 0 0 0-1.79 1.11L1 14l3 2v0a3 3 0 0 0 6 0v0a3 3 0 0 0 6 0v0z"/>', { size: 14 }),
    sparkSm: svg('<path d="M12 3l1.9 5.6L19.5 10.5l-5.6 1.9L12 18l-1.9-5.6L4.5 10.5l5.6-1.9L12 3z"/>', { size: 14 }),
    mail: svg('<path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/>', { size: 14 }),
    checkSm: svg('<polyline points="20 6 9 17 4 12"/>', { size: 12 }),
  };

  // ----- Section data -----
  var coreFeatures = [
    { icon: 'globe', title: 'Connect Everything You Own',
      description: 'Ring doorbells. Tesla. Smart lights. Calendar. Email. 50+ integrations that actually work together.' },
    { icon: 'message', title: 'Just Say What You Want',
      description: "No code. No complex rules. Describe what you want like you're talking to a person." },
    { icon: 'brain', title: 'AI That Actually Acts',
      description: 'Other assistants explain how. AGiXT actually does it. Real actions across real services.' },
    { icon: 'shield', title: 'Own Your Data',
      description: 'Open-source and self-hostable. Your smart home data stays in your home. No cloud required.' },
    { icon: 'clock', title: 'Runs 24/7',
      description: 'Set it once, it works forever. Morning routines, security checks, notifications—always running.' },
    { icon: 'users', title: 'It Learns You',
      description: 'Remembers your preferences. The more you use it, the less you have to explain.' },
  ];

  var useCases = [
    { emoji: '🌅', title: 'The Morning Person',
      examples: ['Coffee maker starts', "Today's calendar read aloud", 'Weather sent to your phone'],
      description: '"Good morning" and your day is organized.' },
    { emoji: '🔒', title: 'The Security-Conscious',
      examples: ['Motion at 3am? Lights flood on.', 'Door left unlocked? Auto-lock + alert.', "Someone at door? See them anywhere."],
      description: 'Your house watches itself.' },
    { emoji: '🚗', title: 'The Road Warrior',
      examples: ['Leave work → Tesla starts', '10 min out → Garage ready, lights on', 'Arrive → Door unlocks, music starts'],
      description: 'Your home anticipates you.' },
    { emoji: '💼', title: 'The Work-From-Home Pro',
      examples: ['"Start work" → Office mode activates', '"Done for day" → Home mode, partner texted', 'Calendar conflicts caught automatically'],
      description: 'Boundaries that enforce themselves.' },
  ];

  var steps = [
    { icon: 'settings', title: 'Connect Your Stuff',
      description: 'Pick from 50+ integrations—Ring, Tesla, Calendar, Email, Lights. Link accounts once.' },
    { icon: 'message', title: 'Describe What You Want',
      description: '"When I leave work, start my car and turn on the lights at home."' },
    { icon: 'workflow', title: 'It Just Works',
      description: 'AGiXT creates the automation and runs it. Forever. Check back anytime.' },
    { icon: 'zap', title: 'Add More Anytime',
      description: 'Stack automations. Make them smarter. Your AI assistant grows with you.' },
  ];

  var extensionCategories = [
    { name: 'Smart Home', items: ['Ring', 'Tesla', 'Roomba', 'Philips Hue', 'Thermostats'] },
    { name: 'Communication', items: ['Discord', 'Slack', 'Email', 'SMS', 'Teams'] },
    { name: 'Productivity', items: ['Google Calendar', 'Outlook', 'Notion', 'Todoist'] },
    { name: 'Security', items: ['Cameras', 'Locks', 'Alarms', 'Motion Sensors'] },
  ];

  // ----- Static section renderers -----
  function renderCoreFeatures() {
    var grid = document.getElementById('core-features');
    if (!grid) return;
    grid.innerHTML = coreFeatures.map(function (f) {
      return (
        '<div class="card feature-card">' +
          '<div class="feature-icon">' + icons[f.icon] + '</div>' +
          '<h3 class="feature-title">' + escapeHtml(f.title) + '</h3>' +
          '<p class="feature-desc">' + escapeHtml(f.description) + '</p>' +
        '</div>'
      );
    }).join('');
  }

  function renderUseCases() {
    var grid = document.getElementById('use-cases');
    if (!grid) return;
    grid.innerHTML = useCases.map(function (u) {
      var lis = u.examples.map(function (e) {
        return '<li>' + icons.check.replace('<svg ', '<svg class="check-icon" ') + '<span>' + escapeHtml(e) + '</span></li>';
      }).join('');
      return (
        '<div class="card">' +
          '<div class="usecase">' +
            '<span class="usecase-emoji">' + u.emoji + '</span>' +
            '<div class="usecase-body">' +
              '<h3>' + escapeHtml(u.title) + '</h3>' +
              '<ul class="usecase-list">' + lis + '</ul>' +
              '<p class="usecase-tag">' + escapeHtml(u.description) + '</p>' +
            '</div>' +
          '</div>' +
        '</div>'
      );
    }).join('');
  }

  function renderSteps() {
    var grid = document.getElementById('steps');
    if (!grid) return;
    grid.innerHTML = steps.map(function (s) {
      return (
        '<div class="step">' +
          '<div class="step-icon">' + icons[s.icon].replace('width="24" height="24"', 'width="28" height="28"') + '</div>' +
          '<h3>' + escapeHtml(s.title) + '</h3>' +
          '<p>' + escapeHtml(s.description) + '</p>' +
        '</div>'
      );
    }).join('');
  }

  function renderExtensionCategories() {
    var grid = document.getElementById('extension-categories');
    if (!grid) return;
    grid.innerHTML = extensionCategories.map(function (c) {
      var lis = c.items.map(function (i) { return '<li>' + escapeHtml(i) + '</li>'; }).join('');
      return (
        '<div class="card ext-card">' +
          '<h3>' + escapeHtml(c.name) + '</h3>' +
          '<ul>' + lis + '</ul>' +
        '</div>'
      );
    }).join('');
  }

  function escapeHtml(s) {
    if (s === null || s === undefined) return '';
    return String(s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  // ----- Token copy -----
  function setupTokenCopy() {
    var btn = document.getElementById('copy-token');
    var input = document.getElementById('token-address');
    if (!btn || !input) return;
    var defIcon = btn.querySelector('.copy-default');
    var doneIcon = btn.querySelector('.copy-done');
    btn.addEventListener('click', function () {
      var v = input.value;
      var ok = false;
      try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(v);
          ok = true;
        } else {
          input.removeAttribute('readonly');
          input.select();
          ok = document.execCommand('copy');
          input.setAttribute('readonly', 'readonly');
          input.blur();
        }
      } catch (e) { ok = false; }
      if (ok) {
        if (defIcon) defIcon.hidden = true;
        if (doneIcon) doneIcon.hidden = false;
        setTimeout(function () {
          if (defIcon) defIcon.hidden = false;
          if (doneIcon) doneIcon.hidden = true;
        }, 2000);
      }
    });
  }

  // ----- Contact form (display-only) -----
  function setupContactForm() {
    var form = document.getElementById('contact-form');
    if (!form) return;
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      try { window.alert('Demo only'); } catch (_) {}
    });
  }

  // ----- Footer copyright -----
  function setupFooter() {
    var el = document.getElementById('footer-copyright');
    if (!el) return;
    var year = new Date().getFullYear();
    el.textContent = '© ' + year + ' AGiXT. Open-source AI automation for everyone.';
  }

  // ----- Chain demo -----
  var scenarios = [
    { command: 'Lock up for the night', actions: [
      { tool: 'smart-lock.lock_all',  label: 'Locked 3 doors',       icon: 'lock',        color: 'emerald' },
      { tool: 'lights.off',           label: 'Lights off (12)',      icon: 'bulb',        color: 'amber' },
      { tool: 'alarm.arm_stay',       label: 'Alarm armed · stay', icon: 'shieldCheck', color: 'red' },
      { tool: 'thermostat.set',       label: 'Thermostat → 68°F', icon: 'thermo',  color: 'blue' },
    ]},
    { command: 'Plan my morning', actions: [
      { tool: 'calendar.read',        label: '4 meetings found',     icon: 'calendar', color: 'blue' },
      { tool: 'tesla.precondition',   label: 'Tesla preheating 7:45', icon: 'car',     color: 'slate' },
      { tool: 'coffee.brew',          label: 'Coffee queued 7:30',   icon: 'sparkSm',  color: 'amber' },
      { tool: 'mail.send',            label: 'Daily brief emailed',  icon: 'mail',     color: 'purple' },
    ]},
    { command: 'Someone’s at the door', actions: [
      { tool: 'ring.snapshot',        label: 'Snapshot captured',    icon: 'shieldCheck', color: 'red' },
      { tool: 'lights.porch_on',      label: 'Porch light on',       icon: 'bulb',        color: 'amber' },
      { tool: 'sms.send',             label: 'Text sent to you',     icon: 'mail',        color: 'purple' },
      { tool: 'lock.status',          label: 'Doors verified locked',icon: 'lock',        color: 'emerald' },
    ]},
  ];

  function buildChainDemo() {
    var root = document.getElementById('chain-demo');
    if (!root) return;
    root.innerHTML =
      '<div class="demo-glow"></div>' +
      '<div class="demo-window">' +
        '<div class="demo-titlebar">' +
          '<div class="demo-titlebar-left">' +
            '<span class="demo-spark">' + icons.sparkSm + '</span>' +
            '<span>AGiXT · Home Agent</span>' +
          '</div>' +
          '<div class="demo-titlebar-right">' +
            '<span><span class="demo-pulse-dot"></span>52 devices</span>' +
            '<span>•</span>' +
            '<span>12 chains</span>' +
          '</div>' +
        '</div>' +
        '<div class="demo-body">' +
          '<div class="demo-block">' +
            '<div class="demo-mic-row">' +
              '<div class="demo-mic" id="demo-mic">' + icons.mic + '</div>' +
              '<div style="flex:1; min-width: 0;">' +
                '<div class="demo-cmd-meta" id="demo-meta">Say something</div>' +
                '<div class="demo-cmd-text" id="demo-cmd">&nbsp;</div>' +
              '</div>' +
            '</div>' +
          '</div>' +
          '<div class="demo-block dim" id="demo-thinking">' +
            '<div class="demo-think-row">' +
              '<div class="demo-think-icon">' + icons.sparkSm + '</div>' +
              '<span class="demo-think-title">Agent reasoning</span>' +
              '<span class="demo-think-extra" id="demo-think-extra"></span>' +
            '</div>' +
            '<p class="demo-think-text" id="demo-think-text" hidden></p>' +
          '</div>' +
          '<div class="demo-block demo-chain" id="demo-chain">' +
            '<div class="demo-chain-head">' +
              '<span class="demo-chain-title">Tool chain</span>' +
              '<span class="demo-chain-status" id="demo-chain-status" hidden>' + icons.checkSm + '<span>All steps complete</span></span>' +
            '</div>' +
            '<div class="demo-actions" id="demo-actions"></div>' +
          '</div>' +
        '</div>' +
        '<div class="demo-footer">' +
          '<span>One sentence · 4 apps · 0 taps</span>' +
          '<span class="accent">AGiXT orchestrated</span>' +
        '</div>' +
      '</div>';

    runDemo(root);
  }

  function runDemo(root) {
    var paused = false;
    root.addEventListener('mouseenter', function () { paused = true; });
    root.addEventListener('mouseleave', function () { paused = false; });

    var idx = 0;
    var cancelled = false;

    function sleepWhile(ms) {
      return new Promise(function (resolve) {
        var start = Date.now();
        function tick() {
          if (cancelled) return;
          if (Date.now() - start >= ms && !paused) return resolve();
          setTimeout(tick, 50);
        }
        tick();
      });
    }

    function setMic(active) {
      var mic = document.getElementById('demo-mic');
      if (!mic) return;
      if (active) {
        mic.classList.add('active');
        if (!mic.querySelector('.ping')) {
          var p = document.createElement('span');
          p.className = 'ping';
          mic.appendChild(p);
        }
      } else {
        mic.classList.remove('active');
        var p2 = mic.querySelector('.ping');
        if (p2) p2.remove();
      }
    }

    function setMeta(text) {
      var el = document.getElementById('demo-meta');
      if (el) el.textContent = text;
    }

    function setCmd(text, listening) {
      var el = document.getElementById('demo-cmd');
      if (!el) return;
      if (text === '' || text === null) {
        el.innerHTML = '&nbsp;';
        return;
      }
      var html = '“' + escapeHtml(text);
      if (listening) html += '<span class="cursor"></span>';
      html += '”';
      el.innerHTML = html;
    }

    function setThinking(state, scene) {
      var block = document.getElementById('demo-thinking');
      var extra = document.getElementById('demo-think-extra');
      var text = document.getElementById('demo-think-text');
      if (!block) return;
      if (state === 'idle' || state === 'listening') {
        block.classList.remove('thinking-active');
        block.classList.add('dim');
        if (extra) extra.innerHTML = '';
        if (text) text.hidden = true;
        return;
      }
      block.classList.add('thinking-active');
      block.classList.remove('dim');
      if (state === 'thinking') {
        if (extra) extra.innerHTML = '<span class="demo-think-dots"><span></span><span></span><span></span></span>';
      } else {
        if (extra) extra.innerHTML = '<span class="demo-think-meta">chain resolved · ' + scene.actions.length + ' steps</span>';
      }
      if (text) {
        text.hidden = false;
        text.textContent = 'Parsed intent → selected ' + scene.actions.length + ' tools → planned execution order with rollback on failure.';
      }
    }

    function buildActions(scene) {
      var wrap = document.getElementById('demo-actions');
      if (!wrap) return;
      wrap.innerHTML = scene.actions.map(function (a, i) {
        return (
          '<div class="demo-action dim" data-i="' + i + '">' +
            '<span class="demo-action-icon">' + icons[a.icon] + '</span>' +
            '<span class="demo-action-tool">' + escapeHtml(a.tool) + '</span>' +
            '<span class="demo-action-label">' + escapeHtml(a.label) + '</span>' +
          '</div>'
        );
      }).join('');
    }

    function setActionState(scene, execStep, allDone) {
      var nodes = document.querySelectorAll('#demo-actions .demo-action');
      nodes.forEach(function (node, i) {
        var a = scene.actions[i];
        var active = !allDone && execStep === i + 1;
        var done = (!allDone && execStep > i + 1) || allDone;
        node.classList.remove('dim', 'active', 'done', 'color-emerald', 'color-amber', 'color-red', 'color-blue', 'color-slate', 'color-purple');
        if (active || done) {
          node.classList.add('color-' + a.color);
          if (active) node.classList.add('active');
          if (done) node.classList.add('done');
          var iconWrap = node.querySelector('.demo-action-icon');
          if (iconWrap) {
            iconWrap.innerHTML = done ? icons.checkSm : icons[a.icon];
          }
        } else {
          node.classList.add('dim');
        }
      });
      var status = document.getElementById('demo-chain-status');
      if (status) status.hidden = !allDone;
    }

    function showChain(visible) {
      var c = document.getElementById('demo-chain');
      if (!c) return;
      c.classList.toggle('visible', !!visible);
    }

    function runOnce() {
      var scene = scenarios[idx];

      // idle
      setMic(false);
      setMeta('Say something');
      setCmd('', false);
      setThinking('idle', scene);
      showChain(false);
      buildActions(scene);

      return sleepWhile(700).then(function () {
        if (cancelled) return;
        // listening
        setMic(true);
        setMeta('Listening…');
        var p = Promise.resolve();
        for (var i = 0; i <= scene.command.length; i++) {
          (function (k) {
            p = p.then(function () {
              if (cancelled) return;
              return sleepWhile(45).then(function () {
                if (cancelled) return;
                setCmd(scene.command.slice(0, k), true);
              });
            });
          })(i);
        }
        return p;
      }).then(function () {
        if (cancelled) return;
        return sleepWhile(500);
      }).then(function () {
        if (cancelled) return;
        // thinking
        setMic(false);
        setMeta('You said');
        setCmd(scene.command, false);
        setThinking('thinking', scene);
        return sleepWhile(1100);
      }).then(function () {
        if (cancelled) return;
        // executing
        setThinking('executing', scene);
        showChain(true);
        var p = Promise.resolve();
        for (var s = 1; s <= scene.actions.length; s++) {
          (function (step) {
            p = p.then(function () {
              if (cancelled) return;
              return sleepWhile(600).then(function () {
                if (cancelled) return;
                setActionState(scene, step, false);
              });
            });
          })(s);
        }
        return p;
      }).then(function () {
        if (cancelled) return;
        return sleepWhile(400);
      }).then(function () {
        if (cancelled) return;
        // done
        setThinking('done', scene);
        setActionState(scene, scene.actions.length + 1, true);
        return sleepWhile(2200);
      }).then(function () {
        if (cancelled) return;
        idx = (idx + 1) % scenarios.length;
        runOnce();
      });
    }

    runOnce();
  }

  // ----- Pricing -----
  function fetchPricing() {
    return fetch('/v1/billing/pricing', { credentials: 'omit' })
      .then(function (r) {
        if (!r.ok) throw new Error('http ' + r.status);
        return r.json();
      });
  }

  function formatPrice(tier, billingInterval, annualDiscountPercent) {
    if (tier.custom_pricing || (tier.price === null && tier.price_per_unit === null) ||
        (tier.price === undefined && tier.price_per_unit === undefined)) {
      return 'Custom';
    }
    var price = (tier.price !== null && tier.price !== undefined) ? tier.price : tier.price_per_unit;
    if (price === null || price === undefined) return 'Custom';
    if (billingInterval === 'year') {
      var annualPrice = annualDiscountPercent > 0
        ? price * 12 * (1 - annualDiscountPercent / 100)
        : price * 12;
      return '$' + Math.round(annualPrice).toLocaleString();
    }
    return '$' + price;
  }

  function getPriceSubtext(tier, billingInterval, pricingModel, unitName) {
    if (tier.custom_pricing || (tier.price === null && tier.price_per_unit === null)) {
      return 'Contact us for pricing';
    }
    if (tier.unit_display) return tier.unit_display;
    if (pricingModel === 'per_token') {
      return 'per ' + (tier.unit_multiplier ? (tier.unit_multiplier / 1000000) + 'M' : '1M') + ' tokens';
    }
    if (pricingModel === 'tiered_plan') {
      return billingInterval === 'year' ? '/year' : '/month';
    }
    if (pricingModel === 'per_bed') {
      return billingInterval === 'year' ? 'per ' + unitName + '/year' : 'per ' + unitName + '/month';
    }
    return 'per ' + (unitName || 'unit') + '/' + (billingInterval === 'year' ? 'yr' : 'mo');
  }

  function getCtaText(tier, trial) {
    if (tier.contact_sales) return 'Contact Sales';
    if (trial && trial.enabled) {
      if (trial.type === 'pilot') return 'Start Pilot Program';
      if (trial.type === 'free_trial') return 'Start Free Trial';
      if (trial.type === 'money_back_guarantee') return 'Get Started';
      if (trial.type === 'credits' && trial.credits_usd) return 'Get $' + trial.credits_usd + ' Free';
    }
    return 'Get Started';
  }

  var pricingState = { config: null, billingInterval: 'month' };

  function renderPricing() {
    var section = document.getElementById('pricing-section');
    var grid = document.getElementById('pricing-grid');
    var subhead = document.getElementById('pricing-subhead');
    var toggleWrap = document.getElementById('pricing-toggle');
    var annualBadge = document.getElementById('annual-badge');
    var extras = document.getElementById('pricing-extras');
    var config = pricingState.config;
    if (!section || !grid || !config) return;

    var tiers = config.tiers || [];
    if (!tiers.length) {
      section.hidden = true;
      return;
    }
    section.hidden = false;

    var pricingModel = config.pricing_model;
    var unitName = config.unit_name;
    var trial = config.trial;
    var contracts = config.contracts;
    var supportsAnnual = !!(contracts && contracts.annual === true);
    var annualDiscountPercent = (contracts && contracts.annual_discount_percent) || 0;

    if (subhead) {
      subhead.textContent = pricingModel === 'per_token'
        ? 'Pay only for what you use. No subscriptions. No hidden fees.'
        : pricingModel === 'tiered_plan'
          ? 'Choose the plan that fits your team. Scale up anytime.'
          : pricingModel === 'per_bed'
            ? 'Simple per-bed pricing that scales with your facility.'
            : 'Flexible plans for teams of all sizes.';
    }

    if (supportsAnnual) {
      toggleWrap.hidden = false;
      var btns = toggleWrap.querySelectorAll('.toggle-btn');
      btns.forEach(function (b) {
        b.classList.toggle('active', b.dataset.interval === pricingState.billingInterval);
      });
      if (annualBadge) {
        if (annualDiscountPercent > 0) {
          annualBadge.hidden = false;
          annualBadge.textContent = 'Save ' + annualDiscountPercent + '%';
        } else annualBadge.hidden = true;
      }
    } else {
      toggleWrap.hidden = true;
    }

    // recommended tier
    var recIdx = -1;
    for (var i = 0; i < tiers.length; i++) {
      var t = tiers[i];
      var n = (t.name || '').toLowerCase();
      if (t.id === 'professional' || t.id === 'standard' || t.id === 'team_10' ||
          n.indexOf('professional') >= 0 || n.indexOf('standard') >= 0) {
        recIdx = i; break;
      }
    }
    var highlightIndex = recIdx >= 0 ? recIdx : (tiers.length > 1 ? 0 : -1);

    grid.className = 'pricing-grid cols-' + Math.min(tiers.length, 4);
    grid.innerHTML = tiers.map(function (tier, idx) {
      var isHighlighted = idx === highlightIndex && tiers.length > 1;
      var price = formatPrice(tier, pricingState.billingInterval, annualDiscountPercent);
      var sub = getPriceSubtext(tier, pricingState.billingInterval, pricingModel, unitName);
      var cta = getCtaText(tier, trial);
      var origPrice = (tier.original_price_per_unit && tier.original_price_per_unit > (tier.price_per_unit || 0))
        ? '<span class="tier-price-original">$' + tier.original_price_per_unit + '</span>' : '';
      var discountBadge = tier.discount_label
        ? '<span class="badge badge-success tier-discount-badge">' + escapeHtml(tier.discount_label) + '</span>'
        : '';
      var description = tier.description ? '<p class="tier-description">' + escapeHtml(tier.description) + '</p>' : '';

      var limitsHtml = '';
      if (pricingModel === 'tiered_plan' && tier.limits) {
        var L = tier.limits;
        var parts = [];
        if (L.users) parts.push(L.users + ' users');
        if (L.devices) parts.push(L.devices.toLocaleString() + ' devices');
        if (L.tokens) {
          var tk = L.tokens >= 1000000 ? Math.round(L.tokens / 1000000) + 'M' : L.tokens.toLocaleString();
          parts.push(tk + ' tokens/mo');
        }
        if (L.storage_gb) {
          var st = L.storage_gb >= 1000 ? (L.storage_gb / 1000).toFixed(1) + ' TB' : L.storage_gb + ' GB';
          parts.push(st + ' storage');
        }
        if (parts.length) {
          limitsHtml = '<div class="tier-limits">' + parts.map(function (p) { return '<div>' + escapeHtml(p) + '</div>'; }).join('') + '</div>';
        }
      }

      var features = (tier.features || []).map(function (f) {
        return '<li>' + icons.check + '<span>' + escapeHtml(f) + '</span></li>';
      }).join('');

      var popularBadge = isHighlighted
        ? '<span class="tier-popular-badge">' + icons.sparkles.replace('width="24" height="24"', 'width="12" height="12"') +
          ' ' + (tier.id === 'standard' ? 'Best Value' : 'Most Popular') + '</span>'
        : '';

      var ctaIcon = tier.contact_sales ? icons.phone : icons.chevronRight;
      var ctaPos = tier.contact_sales ? 'before' : 'after';
      var ctaInner = ctaPos === 'before'
        ? ctaIcon + ' ' + escapeHtml(cta)
        : escapeHtml(cta) + ' ' + ctaIcon;

      var btnClass = 'btn ' + (isHighlighted ? 'btn-primary' : 'btn-outline') + ' btn-block';
      var ctaButton = tier.contact_sales
        ? '<a class="' + btnClass + '" href="mailto:hello@agixt.com">' + ctaInner + '</a>'
        : '<button type="button" class="' + btnClass + '" data-action="signin">' + ctaInner + '</button>';

      return (
        '<div class="card tier-card' + (isHighlighted ? ' highlighted' : '') + '">' +
          popularBadge +
          '<h3 class="tier-name">' + escapeHtml(tier.name || '') + '</h3>' +
          discountBadge +
          '<div class="tier-price-row">' +
            origPrice +
            '<span class="tier-price">' + price + '</span>' +
            '<span class="tier-price-sub">' + escapeHtml(sub) + '</span>' +
          '</div>' +
          description +
          limitsHtml +
          '<ul class="tier-features">' + features + '</ul>' +
          '<div class="tier-cta">' + ctaButton + '</div>' +
        '</div>'
      );
    }).join('');

    // extras
    if (extras) {
      var bits = [];
      if (trial && trial.enabled && trial.description) {
        var tag = (trial.type === 'credits' && trial.credits_usd) ? '$' + trial.credits_usd + ' Free Credits'
          : trial.type === 'pilot' ? 'Pilot Program'
          : trial.type === 'money_back_guarantee' ? 'Guarantee'
          : 'Trial';
        bits.push('<div><span class="badge">' + escapeHtml(tag) + '</span> ' +
          escapeHtml(trial.description) + (!trial.requires_card ? ' — No credit card required' : '') + '</div>');
      }
      if (config.volume_discounts && config.volume_discounts.enabled && config.volume_discounts.description) {
        bits.push('<p>' + escapeHtml(config.volume_discounts.description) + '</p>');
      }
      if (contracts) {
        var msg = '';
        if (contracts.monthly && contracts.annual) {
          msg = 'Month-to-month or annual billing available' + (contracts.annual_discount_percent ? ' — save ' + contracts.annual_discount_percent + '% with annual billing' : '');
        } else if (contracts.monthly) {
          msg = 'Month-to-month billing — cancel anytime';
        } else {
          msg = 'Annual billing';
        }
        if (!contracts.multi_year_required) msg += ' — No multi-year contracts required';
        bits.push('<p>' + escapeHtml(msg) + '</p>');
      }
      extras.innerHTML = bits.join('');
    }
  }

  function setupPricing() {
    var toggleWrap = document.getElementById('pricing-toggle');
    if (toggleWrap) {
      toggleWrap.addEventListener('click', function (e) {
        var btn = e.target.closest('.toggle-btn');
        if (!btn) return;
        pricingState.billingInterval = btn.dataset.interval;
        renderPricing();
      });
    }
    fetchPricing().then(function (cfg) {
      if (!cfg || !cfg.tiers || !cfg.tiers.length) {
        var section = document.getElementById('pricing-section');
        if (section) section.hidden = true;
        return;
      }
      pricingState.config = cfg;
      renderPricing();
    }).catch(function () {
      var section = document.getElementById('pricing-section');
      if (section) section.hidden = true;
    });
  }

  // ----- Init -----
  function init() {
    renderCoreFeatures();
    renderUseCases();
    renderSteps();
    renderExtensionCategories();
    setupTokenCopy();
    setupContactForm();
    setupFooter();
    buildChainDemo();
    setupPricing();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
