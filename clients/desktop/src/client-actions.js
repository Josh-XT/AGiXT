/* Client-side action dispatcher.
 *
 * Modeled on kids/static/js/client-actions.js — when the AGiXT backend
 * streams an "action" event (or includes [SUBACTIVITY][CLIENT_TOOL] markers),
 * this module dispatches it to a local Rust IPC handler that performs the
 * actual desktop manipulation (mouse, keyboard, screenshot).
 *
 * Each handler returns a structured result the caller can post back to AGiXT
 * as the tool's response.
 */
(function () {
  const DEFAULT_SCREENSHOT_TARGET_WIDTH = 1920;
  const VISION_ACTION_SETTLE_MS = 1200;
  const invoke = () => (window.__TAURI__ && window.__TAURI__.core && window.__TAURI__.core.invoke);
  let lastScreenshot = null;

  function argsFor(action) {
    if (action.tool_args) return action.tool_args;
    if (action.arguments) return action.arguments;
    if (action.args) return action.args;
    if (action.input) return action.input;
    return action;
  }

  function intOr(value, fallback = null) {
    if (value == null || value === '') return fallback;
    if (typeof value === 'number' && Number.isFinite(value)) return Math.trunc(value);
    if (typeof value === 'string') {
      const parsed = Number(value.trim());
      return Number.isFinite(parsed) ? Math.trunc(parsed) : fallback;
    }
    return fallback;
  }

  function positiveIntOr(value, fallback = null) {
    const parsed = intOr(value, fallback);
    return parsed && parsed > 0 ? parsed : fallback;
  }

  function numberOr(value, fallback = null) {
    if (value == null || value === '') return fallback;
    if (typeof value === 'number' && Number.isFinite(value)) return value;
    if (typeof value === 'string') {
      const text = value.trim();
      if (!text) return fallback;
      if (text.endsWith('%')) {
        const pct = Number(text.slice(0, -1));
        return Number.isFinite(pct) ? pct / 100 : fallback;
      }
      const parsed = Number(text);
      return Number.isFinite(parsed) ? parsed : fallback;
    }
    return fallback;
  }

  function boolOr(value, fallback = false) {
    if (value == null || value === '') return fallback;
    if (typeof value === 'boolean') return value;
    if (typeof value === 'number') return value !== 0;
    if (typeof value === 'string') {
      const lower = value.trim().toLowerCase();
      if (['true', '1', 'yes', 'y', 'on'].includes(lower)) return true;
      if (['false', '0', 'no', 'n', 'off'].includes(lower)) return false;
    }
    return fallback;
  }

  function dispatchWorkspaceMutated(source) {
    try {
      const conversationId = window.AgixtChat && typeof window.AgixtChat.getConversationId === 'function'
        ? window.AgixtChat.getConversationId()
        : null;
      window.dispatchEvent(new CustomEvent('agixt-workspace-mutated', {
        detail: { source: source || 'client-action', conversationId },
      }));
    } catch (_) { /* best-effort UI refresh hint */ }
  }

  function keyList(keys, singleKey) {
    const raw = keys ?? singleKey ?? null;
    if (raw == null || raw === '') return null;
    if (Array.isArray(raw)) return raw.map((k) => String(k)).filter(Boolean);
    if (typeof raw === 'string') {
      const text = raw.trim();
      if (!text) return null;
      try {
        const parsed = JSON.parse(text);
        if (Array.isArray(parsed)) return parsed.map((k) => String(k)).filter(Boolean);
      } catch (_) { /* not JSON; use separators below */ }
      const parts = text.includes(',') ? text.split(',') : text.split('+');
      return parts.map((k) => k.trim()).filter(Boolean);
    }
    return [String(raw)];
  }

  function normalizeButton(value) {
    const raw = String(value || 'left').trim().toLowerCase();
    if (['primary', 'main', 'button1', 'left_click'].includes(raw)) return 'left';
    if (['secondary', 'context', 'button2', 'right_click'].includes(raw)) return 'right';
    if (['auxiliary', 'aux', 'button3', 'middle_click'].includes(raw)) return 'middle';
    if (['left', 'right', 'middle'].includes(raw)) return raw;
    return 'left';
  }

  function normalizeClickType(value, doubleValue) {
    if (boolOr(doubleValue, false)) return 'double';
    const raw = String(value || 'single').trim().toLowerCase();
    if (['double', 'dblclick', 'double_click', 'double-click'].includes(raw)) return 'double';
    if ([
      'single',
      'click',
      'single_click',
      'single-click',
      'left_click',
      'press',
      'tap',
    ].includes(raw)) return 'single';
    return 'single';
  }

  function looksUnitCoordinate(value) {
    const parsed = numberOr(value, null);
    return parsed != null && parsed > -1 && parsed < 1 && !Number.isInteger(parsed);
  }

  function normalizeCoordinateSpace(value) {
    if (value == null || value === '') return null;
    const raw = String(value).trim().toLowerCase().replace(/[\s-]+/g, '_');
    if ([
      'screenshot',
      'screenshot_pixel',
      'screenshot_pixels',
      'image',
      'image_pixel',
      'image_pixels',
      'vision',
    ].includes(raw)) {
      return 'screenshot';
    }
    if (['screen', 'screen_pixel', 'screen_pixels', 'desktop'].includes(raw)) {
      return 'screen';
    }
    if (['normalized', 'normalised', '0_1000'].includes(raw)) {
      return 'normalized';
    }
    return raw;
  }

  // Pull vision-context fields out of an action's args so we can forward
  // them on every coordinate-bearing IPC call without losing them.
  function visionFields(a) {
    const out = {};
    if (a.normalized != null) out.normalized = boolOr(a.normalized);
    const coordinateSpace = normalizeCoordinateSpace(a.coordinate_space || a.coordinateSpace);
    if (coordinateSpace) {
      out.coordinate_space = coordinateSpace;
      if (coordinateSpace === 'normalized') out.normalized = true;
    }
    if (a.image_coordinates != null || a.imageCoordinates != null) {
      out.image_coordinates = boolOr(a.image_coordinates ?? a.imageCoordinates);
      if (out.image_coordinates) out.coordinate_space = 'screenshot';
    }
    if (a.target_width != null) out.target_width = intOr(a.target_width, 0);
    if (a.target_height != null) out.target_height = intOr(a.target_height, 0);
    if (a.screen_width != null) out.screen_width = intOr(a.screen_width, 0);
    if (a.screen_height != null) out.screen_height = intOr(a.screen_height, 0);
    if (a.monitor_offset_x != null) out.monitor_offset_x = intOr(a.monitor_offset_x, 0);
    if (a.monitor_offset_y != null) out.monitor_offset_y = intOr(a.monitor_offset_y, 0);
    return out;
  }

  function usesScreenshotCoordinates(vision) {
    return vision.image_coordinates || vision.coordinate_space === 'screenshot';
  }

  function hasValue(value) {
    return value != null && value !== '';
  }

  function hasPositiveIntValue(value) {
    return positiveIntOr(value, null) != null;
  }

  function rememberScreenshot(result) {
    if (!result || result.error) return result;
    const width = positiveIntOr(result.width);
    const height = positiveIntOr(result.height);
    if (!width || !height) return result;
    lastScreenshot = {
      width,
      height,
      original_width: positiveIntOr(result.original_width, width),
      original_height: positiveIntOr(result.original_height, height),
      monitor_offset_x: intOr(result.monitor_offset_x, 0),
      monitor_offset_y: intOr(result.monitor_offset_y, 0),
      monitor_index: intOr(result.monitor_index, 0),
    };
    return result;
  }

  function frontendLog(level, message) {
    const inv = invoke();
    if (!inv) return;
    try {
      inv('frontend_log', {
        level: level || 'info',
        message: String(message || '').slice(0, 4000),
      }).catch(() => {});
    } catch (_) { /* ignore logging failures */ }
  }

  function delay(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  function screenshotDataUrl(result) {
    if (!result || !result.image_data) return '';
    let format = String(result.format || 'jpeg').toLowerCase().replace(/[^a-z0-9.+-]/g, '');
    if (!format || format === 'jpg') format = 'jpeg';
    return `data:image/${format};base64,${result.image_data}`;
  }

  function summarizeForHistory(value) {
    if (value == null) return '';
    if (typeof value === 'string') return value.slice(0, 500);
    try {
      const cleaned = { ...value };
      delete cleaned.image_url;
      delete cleaned.image_data;
      delete cleaned.data;
      return JSON.stringify(cleaned).slice(0, 500);
    } catch (_) {
      return String(value).slice(0, 500);
    }
  }

  function screenshotVisionArgs(shot) {
    return {
      coordinate_space: 'screenshot',
      target_width: positiveIntOr(shot.width, DEFAULT_SCREENSHOT_TARGET_WIDTH),
      target_height: positiveIntOr(shot.height, null),
      screen_width: positiveIntOr(shot.original_width, shot.width),
      screen_height: positiveIntOr(shot.original_height, shot.height),
      monitor_offset_x: intOr(shot.monitor_offset_x, 0),
      monitor_offset_y: intOr(shot.monitor_offset_y, 0),
    };
  }

  function normalizedVisionArgs(shot) {
    return {
      ...screenshotVisionArgs(shot),
      coordinate_space: 'normalized',
      normalized: true,
    };
  }

  function extractObservationAndThought(text) {
    const raw = String(text || '');
    const observationMatch = raw.match(/Observation:\s*([\s\S]*?)(?=Thought:|Action:|$)/i);
    const thoughtMatch = raw.match(/Thought:\s*([\s\S]*?)(?=Action:|$)/i);
    return {
      observation: observationMatch ? observationMatch[1].trim() : '',
      thought: thoughtMatch ? thoughtMatch[1].trim() : '',
    };
  }

  function unquoteActionArg(value) {
    const raw = String(value || '').trim();
    if (!raw) return '';
    if (
      (raw.startsWith('"') && raw.endsWith('"')) ||
      (raw.startsWith("'") && raw.endsWith("'"))
    ) {
      if (raw.startsWith('"')) {
        try { return JSON.parse(raw); } catch (_) { /* fall through */ }
      }
      return raw.slice(1, -1);
    }
    return raw;
  }

  function parseVisionAction(text) {
    const raw = String(text || '').replace(/<\/?answer>/gi, '').trim();
    const jsonAction = parseJsonVisionAction(raw);
    if (jsonAction) return jsonAction;
    const patterns = [
      ['double_click', /(?:Action\s*:\s*)?double_click\s*\(\s*(-?\d+)\s*,\s*(-?\d+)\s*\)/i],
      ['right_click', /(?:Action\s*:\s*)?right_click\s*\(\s*(-?\d+)\s*,\s*(-?\d+)\s*\)/i],
      ['click', /(?:Action\s*:\s*)?click\s*\(\s*(-?\d+)\s*,\s*(-?\d+)\s*\)/i],
    ];
    for (const [name, regex] of patterns) {
      const match = raw.match(regex);
      if (match) {
        return {
          name,
          x: intOr(match[1], 0),
          y: intOr(match[2], 0),
          raw: match[0].trim(),
        };
      }
    }

    let match = raw.match(/(?:Action\s*:\s*)?type\s*\(([\s\S]*?)\)/i);
    if (match) return { name: 'type', text: unquoteActionArg(match[1]), raw: match[0].trim() };

    match = raw.match(/(?:Action\s*:\s*)?hotkey\s*\(([\s\S]*?)\)/i);
    if (match) return { name: 'hotkey', keys: unquoteActionArg(match[1]), raw: match[0].trim() };

    match = raw.match(/(?:Action\s*:\s*)?scroll\s*\(\s*["']?(\w+)["']?\s*,\s*(-?\d+)\s*\)/i);
    if (match) {
      return {
        name: 'scroll',
        direction: String(match[1]).toLowerCase(),
        amount: Math.abs(intOr(match[2], 0)),
        raw: match[0].trim(),
      };
    }

    match = raw.match(/(?:Action\s*:\s*)?wait\s*\(\s*(\d+)\s*\)/i);
    if (match) return { name: 'wait', seconds: Math.min(intOr(match[1], 1), 10), raw: match[0].trim() };

    match = raw.match(/(?:Action\s*:\s*)?done\s*\(([\s\S]*?)\)/i);
    if (match) return { name: 'done', summary: unquoteActionArg(match[1]) || 'Task completed', raw: match[0].trim() };

    match = raw.match(/(?:Action\s*:\s*)?failed\s*\(([\s\S]*?)\)/i);
    if (match) return { name: 'failed', summary: unquoteActionArg(match[1]) || 'Task cannot be completed', raw: match[0].trim() };

    return { name: 'unknown', raw: raw.slice(0, 300) };
  }

  function parseJsonVisionAction(raw) {
    const start = raw.indexOf('{');
    const end = raw.lastIndexOf('}');
    if (start < 0 || end <= start) return null;
    let obj;
    try { obj = JSON.parse(raw.slice(start, end + 1)); } catch (_) { return null; }
    if (!obj || typeof obj !== 'object') return null;
    const action = String(obj.action || obj.name || obj.tool || '').toLowerCase();
    const point = Array.isArray(obj.point_2d)
      ? obj.point_2d
      : (Array.isArray(obj.point) ? obj.point : (Array.isArray(obj.coordinate) ? obj.coordinate : null));
    const bbox = Array.isArray(obj.bbox_2d) ? obj.bbox_2d : (Array.isArray(obj.box) ? obj.box : null);
    if (['click', 'double_click', 'right_click'].includes(action) || point || bbox) {
      let x = obj.x;
      let y = obj.y;
      if (point && point.length >= 2) {
        x = point[0];
        y = point[1];
      } else if (bbox && bbox.length >= 4) {
        x = (numberOr(bbox[0], 0) + numberOr(bbox[2], 0)) / 2;
        y = (numberOr(bbox[1], 0) + numberOr(bbox[3], 0)) / 2;
      }
      return {
        name: ['double_click', 'right_click'].includes(action) ? action : 'click',
        x: coordinateOr(x, true, 0),
        y: coordinateOr(y, true, 0),
        coordinate_mode: 'normalized',
        raw: JSON.stringify(obj),
      };
    }
    if (action === 'type') {
      return { name: 'type', text: String(obj.text || ''), raw: JSON.stringify(obj) };
    }
    if (action === 'hotkey') {
      const keys = Array.isArray(obj.keys) ? obj.keys.join('+') : String(obj.keys || obj.key || '');
      return { name: 'hotkey', keys, raw: JSON.stringify(obj) };
    }
    if (action === 'scroll') {
      return {
        name: 'scroll',
        direction: String(obj.direction || 'down').toLowerCase(),
        amount: Math.abs(intOr(obj.amount, 5)),
        raw: JSON.stringify(obj),
      };
    }
    if (action === 'wait') {
      return { name: 'wait', seconds: Math.min(intOr(obj.seconds, 1), 10), raw: JSON.stringify(obj) };
    }
    if (action === 'done') {
      return { name: 'done', summary: String(obj.summary || 'Task completed'), raw: JSON.stringify(obj) };
    }
    if (action === 'failed') {
      return { name: 'failed', summary: String(obj.summary || obj.reason || 'Task cannot be completed'), raw: JSON.stringify(obj) };
    }
    return null;
  }

  function buildVisionControlPrompt(task, shot, history, lastCoordinates, iteration) {
    const width = positiveIntOr(shot.width, DEFAULT_SCREENSHOT_TARGET_WIDTH);
    const height = positiveIntOr(shot.height, 0);
    const historyText = history.length
      ? history.slice(-5).map((entry) => {
        const seen = entry.observation ? ` - saw: ${entry.observation.slice(0, 100)}` : '';
        const result = entry.result ? ` - result: ${entry.result.slice(0, 100)}` : '';
        return `Step ${entry.step}: ${entry.action}${seen}${result}`;
      }).join('\n')
      : 'No previous actions in this desktop-control run.';
    const recentClicks = lastCoordinates.length
      ? `Recent click coordinates in the normalized 0..1000 grid: ${lastCoordinates.slice(-4).map((c) => `(${c.x},${c.y})`).join(', ')}. Do not repeat a click that did not work.`
      : '';
    const goalCheck = iteration > 0
      ? 'First check whether the goal is already complete in the current screenshot. If it is complete, use done("summary").'
      : '';

    return `You are a computer use agent controlling the user's local desktop from a screenshot.

Coordinate system:
- Use Qwen/Qwen-VL visual grounding coordinates: integers from 0 to 1000 normalized across the full screenshot.
- (0,0) is top-left, (1000,1000) is bottom-right, regardless of the screenshot's pixel resolution.
- The screenshot shown to you is ${width}x${height}, but your returned click point must be in the normalized 0..1000 coordinate grid.
- Click the visual center of the target element. Do not click the corner or edge of an icon.
- If the task asks for an OS app icon, use the OS dock/taskbar/launcher at the physical screen edge, not a similar logo inside a webpage, chat sidebar, browser tab, contact list, or editor.
- For a vertical dock on the far left, the x coordinate is usually around 5..20 on the 0..1000 grid, not 50+.

Available actions:
click(x, y)
double_click(x, y)
right_click(x, y)
type("text")
hotkey("key1+key2")
scroll(direction, amount)
wait(seconds)
done("summary")
failed("reason")

Rules:
1. Output exactly one action.
2. Before acting, inspect the current screenshot and decide if the goal is already done.
3. If an action did not work, try a different route instead of repeating it.
4. To type in a field or launcher, first focus it with click() or hotkey().
5. For opening apps through the desktop UI, hotkey("super"), type("app name"), then hotkey("enter") is allowed if visible icon clicking is not reliable.

Goal:
${task}

Current step: ${iteration + 1}
${goalCheck}
${recentClicks}

Previous actions:
${historyText}

Response format:
Return exactly one JSON object. Prefer this Qwen grounding shape:
{"action":"click","point_2d":[x,y],"observation":"what matters","thought":"why"}

Other valid actions:
{"action":"double_click","point_2d":[x,y],"observation":"...","thought":"..."}
{"action":"right_click","point_2d":[x,y],"observation":"...","thought":"..."}
{"action":"type","text":"literal text"}
{"action":"hotkey","keys":["super"]}
{"action":"scroll","direction":"down","amount":5}
{"action":"wait","seconds":1}
{"action":"done","summary":"goal is complete"}
{"action":"failed","summary":"reason"}`;
  }

  async function executeVisionAction(inv, task, action, shot) {
    const vision = action.coordinate_mode === 'screenshot'
      ? screenshotVisionArgs(shot)
      : normalizedVisionArgs(shot);
    switch (action.name) {
      case 'click':
      case 'double_click':
      case 'right_click': {
        const button = action.name === 'right_click' ? 'right' : 'left';
        const clickType = action.name === 'double_click' ? 'double' : 'single';
        const rejected = rejectLikelySidebarAppIconClick(
          { __original_task: task },
          { x: action.x, y: action.y },
          vision,
        );
        if (rejected) {
          return {
            error: rejected.error,
            action: `${action.name}(${action.x}, ${action.y}) rejected`,
            coordinate: { x: action.x, y: action.y },
          };
        }
        const result = await inv('desktop_click', {
          args: {
            x: action.x,
            y: action.y,
            button,
            click_type: clickType,
            ...vision,
          },
        });
        return {
          action: `${action.name}(${action.x}, ${action.y})`,
          coordinate: { x: action.x, y: action.y },
          result,
        };
      }
      case 'type': {
        const result = await inv('desktop_type', { text: action.text, keys: null });
        return { action: `type(${JSON.stringify(action.text)})`, result };
      }
      case 'hotkey': {
        const keys = keyList(action.keys, null);
        const result = await inv('desktop_type', { text: null, keys });
        return { action: `hotkey(${action.keys})`, result };
      }
      case 'scroll': {
        const amount = ['up', 'left'].includes(action.direction)
          ? action.amount
          : -action.amount;
        const axis = ['left', 'right'].includes(action.direction) ? 'horizontal' : 'vertical';
        const result = await inv('desktop_scroll', { amount, axis });
        return { action: `scroll(${action.direction}, ${action.amount})`, result };
      }
      case 'wait':
        await delay(action.seconds * 1000);
        return { action: `wait(${action.seconds})`, result: { waited_seconds: action.seconds } };
      case 'done':
        return { done: true, action: action.raw, summary: action.summary };
      case 'failed':
        return { done: true, success: false, action: action.raw, summary: action.summary };
      default:
        return { error: `No valid action found in vision response: ${action.raw}`, action: 'unknown' };
    }
  }

  async function runVisionControl(inv, a) {
    const task = String(a.task || a.prompt || a.goal || a.__original_task || '').trim();
    if (!task) return { error: 'desktop_vision_control requires a task' };
    const monitorIndex = intOr(a.monitor_index, null);
    const targetWidth = positiveIntOr(a.target_width, DEFAULT_SCREENSHOT_TARGET_WIDTH);
    const targetHeight = positiveIntOr(a.target_height, null);
    const useSmartest = boolOr(a.use_smartest ?? a.useSmartest, false);
    const history = [];
    const lastCoordinates = [];

    for (let iteration = 0; ; iteration += 1) {
      const shot = rememberScreenshot(await inv('desktop_screenshot', {
        monitorIndex,
        targetWidth,
        targetHeight,
      }));
      if (!shot || shot.error) {
        return {
          success: false,
          error: (shot && shot.error) || 'desktop_screenshot failed',
          actions_taken: history.map((h) => h.action),
          action_history: history,
        };
      }

      const imageUrl = screenshotDataUrl(shot);
      if (!imageUrl) {
        return {
          success: false,
          error: 'desktop_screenshot did not return image data',
          actions_taken: history.map((h) => h.action),
          action_history: history,
        };
      }

      const prompt = buildVisionControlPrompt(
        task,
        shot,
        history,
        lastCoordinates,
        iteration,
      );
      frontendLog(
        'info',
        `desktop_vision_control step=${iteration + 1} screenshot=${shot.width}x${shot.height} original=${shot.original_width}x${shot.original_height}`,
      );
      const vision = await inv('agent_vision', {
        args: { prompt, images: [imageUrl], use_smartest: useSmartest },
      });
      const visionText = String((vision && vision.response) || '').trim();
      frontendLog(
        'info',
        `desktop_vision_control vision step=${iteration + 1}: ${visionText.replace(/\s+/g, ' ').slice(0, 800)}`,
      );
      if (!visionText || /Unable to process request/i.test(visionText)) {
        return {
          success: false,
          error: visionText || 'vision inference returned no action',
          actions_taken: history.map((h) => h.action),
          action_history: history,
        };
      }

      const { observation, thought } = extractObservationAndThought(visionText);
      const action = parseVisionAction(visionText);
      const actionResult = await executeVisionAction(inv, task, action, shot);
      frontendLog(
        actionResult.error ? 'warn' : 'info',
        `desktop_vision_control action step=${iteration + 1}: ${actionResult.action || action.raw}${actionResult.error ? ` error=${actionResult.error}` : ''}`,
      );
      const resultSummary = summarizeForHistory(actionResult.result || actionResult.error || actionResult.summary);
      history.push({
        step: iteration + 1,
        action: actionResult.action || action.raw,
        observation,
        reasoning: thought,
        result: resultSummary,
      });
      if (actionResult.coordinate) lastCoordinates.push(actionResult.coordinate);

      if (actionResult.done) {
        return {
          success: actionResult.success !== false,
          summary: actionResult.summary || 'Task completed',
          actions_taken: history.map((h) => h.action),
          action_history: history,
        };
      }

      await delay(VISION_ACTION_SETTLE_MS);
    }
  }

  function applyLastScreenshotVisionContext(vision, provided = {}) {
    if ((!vision.normalized && !usesScreenshotCoordinates(vision)) || !lastScreenshot) return vision;

    if (!provided.target_width) vision.target_width = lastScreenshot.width;
    if (!provided.target_height) vision.target_height = lastScreenshot.height;
    if (!provided.monitor_offset_x) vision.monitor_offset_x = lastScreenshot.monitor_offset_x;
    if (!provided.monitor_offset_y) vision.monitor_offset_y = lastScreenshot.monitor_offset_y;

    const screenLooksLikeTargetWidth =
      vision.screen_width === vision.target_width || vision.screen_width === lastScreenshot.width;
    const screenLooksLikeTargetHeight =
      vision.screen_height === vision.target_height || vision.screen_height === lastScreenshot.height;

    if (
      !provided.screen_width ||
      (lastScreenshot.original_width !== lastScreenshot.width && screenLooksLikeTargetWidth)
    ) {
      vision.screen_width = lastScreenshot.original_width;
    }
    if (
      !provided.screen_height ||
      (lastScreenshot.original_height !== lastScreenshot.height && screenLooksLikeTargetHeight)
    ) {
      vision.screen_height = lastScreenshot.original_height;
    }

    return vision;
  }

  function taskLooksLikeLeftDockAppIcon(task) {
    const lower = String(task || '').toLowerCase();
    if (!lower.includes('icon')) return false;
    if (/\b(webpage|website|browser tab|sidebar|inside the app|inside agixt)\b/.test(lower)) {
      return false;
    }
    return /\b(spotify|chrome|firefox|brave|discord|slack|terminal|settings|files|file manager|app|application|dock|launcher|taskbar)\b/.test(lower);
  }

  function taskMentionsExactCoordinates(task) {
    const lower = String(task || '').toLowerCase();
    if (!/\b(click|move|drag|press|tap)\b/.test(lower)) return false;
    return (
      /\b(x|y)\s*[:=]\s*-?\d+/.test(lower) ||
      /\b-?\d+\s*,\s*-?\d+\b/.test(lower) ||
      /\b(coordinates?|pixels?|screen position|exact position)\b/.test(lower)
    );
  }

  function taskLooksLikeVisibleDesktopUi(task) {
    const lower = String(task || '').toLowerCase();
    if (!lower || taskMentionsExactCoordinates(lower)) return false;
    if (taskLooksLikeLeftDockAppIcon(lower)) return true;
    const hasUiVerb = /\b(click|press|tap|select|choose|open|launch|focus|inspect|look|see|read|find|move|drag)\b/.test(lower);
    const hasUiTarget = /\b(icon|button|menu|window|desktop|screen|dock|taskbar|launcher|app|application|visible|spotify|chrome|firefox|brave|discord|slack|terminal|settings|files)\b/.test(lower);
    return hasUiVerb && hasUiTarget;
  }

  function shouldUpgradeLowLevelUiAction(name, a) {
    if (boolOr(a.allow_direct_click ?? a.direct, false)) return false;
    const task = a.__original_task || a.task || a.goal || a.prompt || '';
    if (!taskLooksLikeVisibleDesktopUi(task)) return false;
    return [
      'desktop_click',
      'click',
      'mouse_click',
      'desktop_move',
      'mouse_move',
      'desktop_drag',
      'mouse_drag',
      'drag',
    ].includes(name);
  }

  function rejectLikelySidebarAppIconClick(a, coords, vision) {
    if (!lastScreenshot || (!vision.normalized && !usesScreenshotCoordinates(vision))) return null;
    if (!taskLooksLikeLeftDockAppIcon(a.__original_task)) return null;
    if (lastScreenshot.width < 1000 || lastScreenshot.original_width <= lastScreenshot.width) return null;
    const imageX = vision.normalized
      ? Math.round(coords.x / 1000 * lastScreenshot.width)
      : coords.x;
    if (imageX > 64 && imageX <= 384) {
      return {
        error: [
          'Refusing to click a likely in-app/sidebar coordinate for an OS application icon request.',
          `Requested image x=${imageX} on a ${lastScreenshot.width}px-wide screenshot.`,
          'For a left-edge OS dock icon, choose the visual center in the physical dock at the extreme left edge, usually image x under 40 on this screenshot.',
          'Take a fresh desktop_screenshot and retry the click on the OS dock/application launcher icon, not the AGiXT/web/sidebar icon.',
        ].join(' '),
      };
    }
    return null;
  }

  function coordinateOr(value, normalized, fallback = 0) {
    const parsed = numberOr(value, null);
    if (parsed == null) return fallback;
    if (normalized && Math.abs(parsed) <= 1) {
      return Math.round(parsed * 1000);
    }
    return Math.round(parsed);
  }

  function coordinateArgs(a, keys) {
    const vision = visionFields(a);
    const provided = {
      target_width: hasPositiveIntValue(a.target_width),
      target_height: hasPositiveIntValue(a.target_height),
      screen_width: hasPositiveIntValue(a.screen_width),
      screen_height: hasPositiveIntValue(a.screen_height),
      monitor_offset_x: hasValue(a.monitor_offset_x),
      monitor_offset_y: hasValue(a.monitor_offset_y),
    };
    const inferredNormalized = keys.some((key) => looksUnitCoordinate(a[key]));
    if (inferredNormalized && a.normalized == null) {
      vision.normalized = true;
    }
    if (
      !vision.normalized &&
      !usesScreenshotCoordinates(vision) &&
      (provided.target_width || provided.target_height) &&
      (provided.screen_width || provided.screen_height)
    ) {
      vision.coordinate_space = 'screenshot';
    }
    applyLastScreenshotVisionContext(vision, provided);
    const normalized = !!vision.normalized;
    const coords = {};
    for (const key of keys) {
      coords[key] = coordinateOr(a[key], normalized, 0);
    }
    return { coords, vision };
  }

  async function execute(action) {
    const inv = invoke();
    if (!inv) return { error: 'Tauri IPC unavailable' };
    const name = (action.tool_name || action.name || action.action_type || '').toLowerCase();
    const a = argsFor(action) || {};

    try {
      if (shouldUpgradeLowLevelUiAction(name, a)) {
        const task = a.__original_task || a.task || a.goal || a.prompt || '';
        frontendLog(
          'info',
          `Upgrading ${name} to desktop_vision_control for visible UI task: ${String(task).slice(0, 300)}`,
        );
        return await runVisionControl(inv, {
          ...a,
          task,
        });
      }

      switch (name) {
        case 'client_platform':
        case 'device_platform':
          return await inv('client_platform');

        case 'device_open_url':
        case 'open_url':
        case 'open_deep_link':
          return await inv('device_open_url', {
            args: {
              url: a.url || a.uri || a.href || '',
              with: a.with || a.app || null,
            },
          });

        case 'device_open_app':
        case 'open_app':
        case 'launch_app':
          return await inv('device_open_app', {
            args: {
              name: a.name || a.app || a.application || null,
              url: a.url || a.uri || a.href || null,
              package: a.package || a.app_package || a.package_name || null,
              package_name: a.package_name || a.packageName || null,
              bundle_id: a.bundle_id || a.bundleId || null,
            },
          });

        case 'device_open_settings':
        case 'open_settings':
        case 'open_device_settings':
          return await inv('device_open_settings', {
            args: {
              section: a.section || a.panel || null,
              app_package: a.app_package || a.package || a.package_name || null,
              bundle_id: a.bundle_id || a.bundleId || null,
            },
          });

        case 'desktop_vision_control':
        case 'vision_desktop_control':
        case 'desktop_control':
          return await runVisionControl(inv, a);

        case 'shell_run':
        case 'run_shell':
        case 'bash':
          return await inv('shell_run', {
            command: a.command || a.cmd || '',
            timeoutMs: intOr(a.timeout_ms ?? a.timeout, null),
          });

        case 'sudo_run':
        case 'sudo_shell':
        case 'privileged_shell':
          return await inv('sudo_run', {
            command: a.command || a.cmd || '',
            timeoutMs: intOr(a.timeout_ms ?? a.timeout, null),
          });

        case 'desktop_screenshot':
        case 'take_screenshot':
        case 'screenshot':
          {
            const targetWidth = positiveIntOr(a.target_width, null);
            const targetHeight = positiveIntOr(a.target_height, null);
            return rememberScreenshot(await inv('desktop_screenshot', {
              monitorIndex: intOr(a.monitor_index, null),
              targetWidth: targetWidth ?? (targetHeight == null ? DEFAULT_SCREENSHOT_TARGET_WIDTH : null),
              targetHeight,
            }));
          }

        case 'desktop_click':
        case 'click':
        case 'mouse_click':
          {
            const { coords, vision } = coordinateArgs(a, ['x', 'y']);
            const rejected = rejectLikelySidebarAppIconClick(a, coords, vision);
            if (rejected) return rejected;
            return await inv('desktop_click', {
              args: {
                x: coords.x,
                y: coords.y,
                button: normalizeButton(a.button),
                click_type: normalizeClickType(a.click_type, a.double),
                ...vision,
              },
            });
          }

        case 'desktop_move':
        case 'mouse_move':
          {
            const { coords, vision } = coordinateArgs(a, ['x', 'y']);
            return await inv('desktop_move', {
              args: { x: coords.x, y: coords.y, ...vision },
            });
          }

        case 'desktop_drag':
        case 'mouse_drag':
        case 'drag':
          {
            const { coords, vision } = coordinateArgs(a, ['from_x', 'from_y', 'to_x', 'to_y']);
            return await inv('desktop_drag', {
              args: {
                from_x: coords.from_x,
                from_y: coords.from_y,
                to_x: coords.to_x,
                to_y: coords.to_y,
                button: normalizeButton(a.button),
                ...vision,
              },
            });
          }

        case 'desktop_scroll':
        case 'scroll':
          return await inv('desktop_scroll', {
            amount: intOr(a.amount, 0),
            axis: a.axis || 'vertical',
          });

        case 'desktop_type':
        case 'type':
        case 'keyboard':
        case 'keyboard_input':
          return await inv('desktop_type', {
            text: a.text ?? null,
            keys: keyList(a.keys, a.key),
          });

        case 'terminal_open':
        case 'open_terminal':
        case 'shell_open':
          return await inv('terminal_open', {
            args: {
              shell: a.shell ?? null,
              cwd: a.cwd ?? null,
              cols: intOr(a.cols, null),
              rows: intOr(a.rows, null),
            },
          });

        case 'terminal_list':
        case 'list_terminals':
          return await inv('terminal_list');

        case 'terminal_close':
        case 'close_terminal':
          return await inv('terminal_close', { sessionId: a.session_id || a.id });

        case 'terminal_exec':
        case 'shell_exec':
        case 'execute_in_terminal':
          return await inv('terminal_exec', {
            sessionId: a.session_id || a.id,
            command: a.command || a.cmd || '',
            idleMs: intOr(a.idle_ms, null),
            timeoutMs: intOr(a.timeout_ms ?? a.timeout, null),
          });

        case 'terminal_send_input':
        case 'send_terminal_input':
          return await inv('terminal_send_input', {
            sessionId: a.session_id || a.id,
            data: a.data || a.input || '',
          });

        case 'terminal_read':
        case 'read_terminal':
          return await inv('terminal_read', {
            sessionId: a.session_id || a.id,
            offset: intOr(a.offset, null),
          });

        case 'terminal_resize':
        case 'resize_terminal':
          return await inv('terminal_resize', {
            sessionId: a.session_id || a.id,
            cols: intOr(a.cols, 0),
            rows: intOr(a.rows, 0),
          });

        case 'terminal_signal':
        case 'signal_terminal':
          return await inv('terminal_signal', {
            sessionId: a.session_id || a.id,
            signal: a.signal || 'ctrl-c',
          });

        // ---- Local filesystem on the user's machine ----------------

        case 'fs_read':
        case 'read_file':
          return await inv('fs_read', { path: a.path });

        case 'fs_write':
        case 'write_file':
          return await inv('fs_write', {
            args: {
              path: a.path,
              content: a.content ?? '',
              encoding: a.encoding || null,
              create_dirs: boolOr(a.create_dirs ?? a.parents, false),
            },
          });

        case 'fs_append':
        case 'append_file':
          return await inv('fs_append', {
            args: {
              path: a.path,
              content: a.content ?? '',
              encoding: a.encoding || null,
              create_dirs: false,
            },
          });

        case 'fs_edit':
        case 'edit_file':
          return await inv('fs_edit', {
            args: {
              path: a.path,
              edits: Array.isArray(a.edits) ? a.edits : [
                {
                  find: a.find ?? a.old_string ?? '',
                  replace: a.replace ?? a.new_string ?? '',
                  replace_all: boolOr(a.replace_all, false),
                },
              ],
            },
          });

        case 'fs_list':
        case 'list_directory':
        case 'ls':
          return await inv('fs_list', { path: a.path || '.' });

        case 'fs_stat':
        case 'stat_file':
          return await inv('fs_stat', { path: a.path });

        case 'fs_mkdir':
        case 'mkdir':
          return await inv('fs_mkdir', {
            args: { path: a.path, parents: boolOr(a.parents, true) },
          });

        case 'fs_delete':
        case 'delete_file':
        case 'rm':
          return await inv('fs_delete', {
            args: { path: a.path, recursive: boolOr(a.recursive, false) },
          });

        case 'fs_rename':
        case 'fs_move':
        case 'mv':
          return await inv('fs_rename', {
            args: {
              from: a.from || a.src || a.source,
              to: a.to || a.dest || a.destination,
              overwrite: boolOr(a.overwrite, false),
            },
          });

        // ---- Workspace bridge --------------------------------------

        case 'workspace_upload':
        case 'upload_to_workspace': {
          const result = await inv('workspace_upload_local', {
            localPath: a.local_path || a.path,
            workspacePath: a.workspace_path || null,
          });
          dispatchWorkspaceMutated('workspace-upload');
          return result;
        }

        case 'workspace_download':
        case 'download_from_workspace':
          return await inv('workspace_download_to_local', {
            workspacePath: a.workspace_path || a.path,
            localPath: a.local_path,
            overwrite: boolOr(a.overwrite, false),
          });

        case 'workspace_list':
        case 'list_workspace':
          return await inv('workspace_list', { subPath: a.sub_path || a.path || null });

        default:
          return { error: `unknown client tool: ${name}` };
      }
    } catch (err) {
      return { error: err && err.error ? err.error : String(err) };
    }
  }

  window.AgixtClientActions = { execute };
})();
