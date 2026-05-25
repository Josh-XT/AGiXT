/* Helpers shared across the team chat surface.
 *
 *   - md5      — tiny MD5 used only for gravatar URL construction. The
 *                webview ships with crypto.subtle, but that only exposes
 *                async algorithms (SHA-1, SHA-256, ...). MD5 is purely
 *                client-side and the cost is negligible (~3 ms per page
 *                load), so we keep it here rather than adding a deps
 *                pipeline. Source: public-domain Joseph Myers, trimmed
 *                to the strict ES5 happy path we need.
 *   - gravatarUrl(email, size)
 *   - mentionRe / replyRe / emojiCodeRe — regex constants reused by the
 *                renderer.
 *   - parseReply  — vanilla-JS port of web/components/conversation/Message/
 *                Message.tsx:parseReplyReference. Produces a structured
 *                {replyAuthor, replyPreview, actualMessage, replyMessageId,
 *                 replyAuthorUserId} object so the renderer can draw a
 *                reply card above the rest of the message body.
 *   - applyMentions(text, lookupFn)
 *                Replaces `<@uuid>` tokens with `@DisplayName` using the
 *                caller-supplied resolver (the web stores user mentions
 *                as `<@uid>` so they keep working across renames). Both
 *                the reply preview and the actual body get this pass.
 *   - applyEmojiShortcodes(text)
 *                Replaces `:shortcode:` tokens with Unicode emoji using
 *                the EMOJI_SHORTCODES map.
 *   - extractFirstFewUrls(text)
 *                Pulls up to 3 distinct http(s) URLs out of a string so
 *                the OG preview renderer knows what to fetch.
 *   - EMOJI_SHORTCODES
 *                The ~600-entry shortcode → emoji dictionary. Ported
 *                verbatim from web/components/conversation/Message/
 *                EmojiReactions.tsx so `:joy:`, `:fire:`, etc., resolve
 *                the same way on desktop as they do on the web.
 */
(function () {
  if (window.AgixtTeamChatHelpers) return;

  // ----- MD5 -------------------------------------------------------------
  // Compact, pure-ES5 MD5 implementation. We only call this on email
  // strings <100 chars so the I/O performance is irrelevant.

  function md5cycle(x, k) {
    let a = x[0], b = x[1], c = x[2], d = x[3];

    a = ff(a, b, c, d, k[0], 7, -680876936);
    d = ff(d, a, b, c, k[1], 12, -389564586);
    c = ff(c, d, a, b, k[2], 17, 606105819);
    b = ff(b, c, d, a, k[3], 22, -1044525330);
    a = ff(a, b, c, d, k[4], 7, -176418897);
    d = ff(d, a, b, c, k[5], 12, 1200080426);
    c = ff(c, d, a, b, k[6], 17, -1473231341);
    b = ff(b, c, d, a, k[7], 22, -45705983);
    a = ff(a, b, c, d, k[8], 7, 1770035416);
    d = ff(d, a, b, c, k[9], 12, -1958414417);
    c = ff(c, d, a, b, k[10], 17, -42063);
    b = ff(b, c, d, a, k[11], 22, -1990404162);
    a = ff(a, b, c, d, k[12], 7, 1804603682);
    d = ff(d, a, b, c, k[13], 12, -40341101);
    c = ff(c, d, a, b, k[14], 17, -1502002290);
    b = ff(b, c, d, a, k[15], 22, 1236535329);

    a = gg(a, b, c, d, k[1], 5, -165796510);
    d = gg(d, a, b, c, k[6], 9, -1069501632);
    c = gg(c, d, a, b, k[11], 14, 643717713);
    b = gg(b, c, d, a, k[0], 20, -373897302);
    a = gg(a, b, c, d, k[5], 5, -701558691);
    d = gg(d, a, b, c, k[10], 9, 38016083);
    c = gg(c, d, a, b, k[15], 14, -660478335);
    b = gg(b, c, d, a, k[4], 20, -405537848);
    a = gg(a, b, c, d, k[9], 5, 568446438);
    d = gg(d, a, b, c, k[14], 9, -1019803690);
    c = gg(c, d, a, b, k[3], 14, -187363961);
    b = gg(b, c, d, a, k[8], 20, 1163531501);
    a = gg(a, b, c, d, k[13], 5, -1444681467);
    d = gg(d, a, b, c, k[2], 9, -51403784);
    c = gg(c, d, a, b, k[7], 14, 1735328473);
    b = gg(b, c, d, a, k[12], 20, -1926607734);

    a = hh(a, b, c, d, k[5], 4, -378558);
    d = hh(d, a, b, c, k[8], 11, -2022574463);
    c = hh(c, d, a, b, k[11], 16, 1839030562);
    b = hh(b, c, d, a, k[14], 23, -35309556);
    a = hh(a, b, c, d, k[1], 4, -1530992060);
    d = hh(d, a, b, c, k[4], 11, 1272893353);
    c = hh(c, d, a, b, k[7], 16, -155497632);
    b = hh(b, c, d, a, k[10], 23, -1094730640);
    a = hh(a, b, c, d, k[13], 4, 681279174);
    d = hh(d, a, b, c, k[0], 11, -358537222);
    c = hh(c, d, a, b, k[3], 16, -722521979);
    b = hh(b, c, d, a, k[6], 23, 76029189);
    a = hh(a, b, c, d, k[9], 4, -640364487);
    d = hh(d, a, b, c, k[12], 11, -421815835);
    c = hh(c, d, a, b, k[15], 16, 530742520);
    b = hh(b, c, d, a, k[2], 23, -995338651);

    a = ii(a, b, c, d, k[0], 6, -198630844);
    d = ii(d, a, b, c, k[7], 10, 1126891415);
    c = ii(c, d, a, b, k[14], 15, -1416354905);
    b = ii(b, c, d, a, k[5], 21, -57434055);
    a = ii(a, b, c, d, k[12], 6, 1700485571);
    d = ii(d, a, b, c, k[3], 10, -1894986606);
    c = ii(c, d, a, b, k[10], 15, -1051523);
    b = ii(b, c, d, a, k[1], 21, -2054922799);
    a = ii(a, b, c, d, k[8], 6, 1873313359);
    d = ii(d, a, b, c, k[15], 10, -30611744);
    c = ii(c, d, a, b, k[6], 15, -1560198380);
    b = ii(b, c, d, a, k[13], 21, 1309151649);
    a = ii(a, b, c, d, k[4], 6, -145523070);
    d = ii(d, a, b, c, k[11], 10, -1120210379);
    c = ii(c, d, a, b, k[2], 15, 718787259);
    b = ii(b, c, d, a, k[9], 21, -343485551);

    x[0] = add32(a, x[0]);
    x[1] = add32(b, x[1]);
    x[2] = add32(c, x[2]);
    x[3] = add32(d, x[3]);
  }
  function cmn(q, a, b, x, s, t) {
    a = add32(add32(a, q), add32(x, t));
    return add32((a << s) | (a >>> (32 - s)), b);
  }
  function ff(a, b, c, d, x, s, t) { return cmn((b & c) | ((~b) & d), a, b, x, s, t); }
  function gg(a, b, c, d, x, s, t) { return cmn((b & d) | (c & (~d)), a, b, x, s, t); }
  function hh(a, b, c, d, x, s, t) { return cmn(b ^ c ^ d, a, b, x, s, t); }
  function ii(a, b, c, d, x, s, t) { return cmn(c ^ (b | (~d)), a, b, x, s, t); }
  function md51(s) {
    const n = s.length;
    const state = [1732584193, -271733879, -1732584194, 271733878];
    let i;
    for (i = 64; i <= s.length; i += 64) md5cycle(state, md5blk(s.substring(i - 64, i)));
    s = s.substring(i - 64);
    const tail = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0];
    for (i = 0; i < s.length; i++) tail[i >> 2] |= s.charCodeAt(i) << ((i % 4) << 3);
    tail[i >> 2] |= 0x80 << ((i % 4) << 3);
    if (i > 55) { md5cycle(state, tail); for (i = 0; i < 16; i++) tail[i] = 0; }
    tail[14] = n * 8;
    md5cycle(state, tail);
    return state;
  }
  function md5blk(s) {
    const md5blks = [];
    for (let i = 0; i < 64; i += 4) {
      md5blks[i >> 2] = s.charCodeAt(i) + (s.charCodeAt(i + 1) << 8) + (s.charCodeAt(i + 2) << 16) + (s.charCodeAt(i + 3) << 24);
    }
    return md5blks;
  }
  const hex_chr = '0123456789abcdef'.split('');
  function rhex(n) {
    let s = '';
    for (let j = 0; j < 4; j++) {
      s += hex_chr[(n >> (j * 8 + 4)) & 0x0F] + hex_chr[(n >> (j * 8)) & 0x0F];
    }
    return s;
  }
  function hex(x) { return x.map(rhex).join(''); }
  function add32(a, b) { return (a + b) & 0xFFFFFFFF; }
  function md5(s) { return hex(md51(unescape(encodeURIComponent(s)))); }

  // ----- Gravatar / avatar -----------------------------------------------

  function gravatarUrl(email, size) {
    if (!email) return null;
    const hash = md5(String(email).trim().toLowerCase());
    return 'https://www.gravatar.com/avatar/' + hash + '?s=' + (size || 64) + '&d=404';
  }

  // ----- Reply parsing ---------------------------------------------------
  // Matches the web's parseReplyReference exactly (we have to round-trip
  // the same `> **Author** said: [ref:msg-id] [uid:user-id]\n> quote\n\n`
  // format on the wire).
  const REPLY_HEADER = /^> \*\*(.+?)\*\* said:(?:\s*\[ref:([^\]]+)\])?(?:\s*\[uid:([^\]]+)\])?$/;

  function parseReply(message) {
    if (typeof message !== 'string' || !message.startsWith('> **')) return null;
    const firstNL = message.indexOf('\n');
    if (firstNL === -1) return null;
    const headerLine = message.substring(0, firstNL);
    const m = headerLine.match(REPLY_HEADER);
    if (!m) return null;
    const replyAuthor = m[1];
    const replyMessageId = m[2] || undefined;
    const replyAuthorUserId = m[3] || undefined;
    const rest = message.substring(firstNL + 1);
    const lines = rest.split('\n');
    const quoted = [];
    let i = 0;
    for (; i < lines.length; i++) {
      if (lines[i].startsWith('> ') || lines[i] === '>') {
        quoted.push(lines[i].replace(/^> ?/, ''));
      } else break;
    }
    if (!quoted.length) return null;
    if (i < lines.length && lines[i].trim() === '') i++;
    return {
      replyAuthor,
      replyPreview: quoted.join(' ').trim(),
      actualMessage: lines.slice(i).join('\n').trim(),
      replyMessageId,
      replyAuthorUserId,
    };
  }

  // ----- Mention + emoji rewriters --------------------------------------

  const MENTION_RE = /<@([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})>/gi;
  const EMOJI_CODE_RE = /:([a-zA-Z0-9_+-]+):/g;

  function applyMentions(text, resolver) {
    if (!text) return text;
    return text.replace(MENTION_RE, (_m, uid) => {
      const name = resolver ? resolver(uid) : null;
      return '@' + (name || 'User');
    });
  }

  // ----- URL extraction (for OG previews) -------------------------------
  // Standalone URL extractor that ignores URLs embedded inside markdown
  // link syntax (`[text](url)`) and image syntax (`![alt](url)`) — those
  // are already represented in the rendered HTML and we don't want a
  // separate preview card duplicating them.
  const URL_RE = /\bhttps?:\/\/[^\s<>"]+/g;
  function extractFirstFewUrls(text, max) {
    if (!text) return [];
    const out = [];
    const seen = new Set();
    // Strip markdown link/image content first.
    const stripped = String(text)
      .replace(/!\[[^\]]*\]\([^)]+\)/g, ' ')
      .replace(/\[[^\]]*\]\([^)]+\)/g, ' ');
    const limit = max || 3;
    let m;
    while ((m = URL_RE.exec(stripped)) !== null) {
      // Trim trailing punctuation that's almost never part of a URL.
      let url = m[0].replace(/[.,;:!?)\]]+$/, '');
      if (seen.has(url)) continue;
      seen.add(url);
      out.push(url);
      if (out.length >= limit) break;
    }
    return out;
  }

  // ----- Emoji shortcodes -----------------------------------------------
  // Ported from web/components/conversation/Message/EmojiReactions.tsx.
  // Trimmed to the categories the web ships; if you add a shortcode on
  // either side, mirror it here so chat content stays consistent.
  const EMOJI_SHORTCODES = {
    // Smileys & Emotion
    grinning: '\u{1F600}', smiley: '\u{1F603}', smile: '\u{1F604}', grin: '\u{1F601}',
    laughing: '\u{1F606}', satisfied: '\u{1F606}', sweat_smile: '\u{1F605}',
    rofl: '\u{1F923}', joy: '\u{1F602}', slightly_smiling_face: '\u{1F642}',
    upside_down_face: '\u{1F643}', wink: '\u{1F609}', blush: '\u{1F60A}',
    innocent: '\u{1F607}', heart_eyes: '\u{1F60D}', star_struck: '\u{1F929}',
    kissing_heart: '\u{1F618}', kissing: '\u{1F617}', yum: '\u{1F60B}',
    stuck_out_tongue: '\u{1F61B}', stuck_out_tongue_winking_eye: '\u{1F61C}',
    zany_face: '\u{1F92A}', money_mouth_face: '\u{1F911}', hugs: '\u{1F917}',
    hugging: '\u{1F917}', hand_over_mouth: '\u{1F92D}', shushing_face: '\u{1F92B}',
    thinking: '\u{1F914}', thinking_face: '\u{1F914}', saluting_face: '\u{1FAE1}',
    salute: '\u{1FAE1}', zipper_mouth_face: '\u{1F910}', neutral_face: '\u{1F610}',
    expressionless: '\u{1F611}', no_mouth: '\u{1F636}', smirk: '\u{1F60F}',
    unamused: '\u{1F612}', roll_eyes: '\u{1F644}', eye_roll: '\u{1F644}',
    grimacing: '\u{1F62C}', grimace: '\u{1F62C}', liar: '\u{1F925}',
    lying_face: '\u{1F925}', relieved: '\u{1F60C}', pensive: '\u{1F614}',
    sleepy: '\u{1F62A}', drooling_face: '\u{1F924}', drool: '\u{1F924}',
    sleeping: '\u{1F634}', zzz: '\u{1F4A4}', mask: '\u{1F637}',
    face_with_thermometer: '\u{1F912}', sick: '\u{1F912}',
    face_with_head_bandage: '\u{1F915}', hurt: '\u{1F915}',
    nauseated_face: '\u{1F922}', vomiting: '\u{1F92E}', puke: '\u{1F92E}',
    hot_face: '\u{1F975}', cold_face: '\u{1F976}', woozy_face: '\u{1F974}',
    drunk: '\u{1F974}', dizzy_face: '\u{1F635}', exploding_head: '\u{1F92F}',
    mind_blown: '\u{1F92F}', cowboy: '\u{1F920}', cowboy_hat_face: '\u{1F920}',
    partying_face: '\u{1F973}', party: '\u{1F973}', disguised_face: '\u{1F978}',
    sunglasses: '\u{1F60E}', cool: '\u{1F60E}', nerd_face: '\u{1F913}',
    nerd: '\u{1F913}', monocle_face: '\u{1F9D0}', confused: '\u{1F615}',
    worried: '\u{1F61F}', slightly_frowning_face: '\u{1F641}',
    frowning_face: '\u{1F62E}', open_mouth: '\u{1F62E}', hushed: '\u{1F62F}',
    astonished: '\u{1F632}', flushed: '\u{1F633}', pleading_face: '\u{1F97A}',
    pleading: '\u{1F97A}', anguished: '\u{1F627}', fearful: '\u{1F628}',
    cold_sweat: '\u{1F630}', disappointed_relieved: '\u{1F625}',
    cry: '\u{1F622}', sob: '\u{1F62D}', scream: '\u{1F631}',
    confounded: '\u{1F616}', persevere: '\u{1F623}', disappointed: '\u{1F61E}',
    sweat: '\u{1F613}', weary: '\u{1F629}', tired_face: '\u{1F62B}',
    yawning_face: '\u{1F971}', yawn: '\u{1F971}', triumph: '\u{1F624}',
    rage: '\u{1F621}', angry: '\u{1F620}', pout: '\u{1F621}',
    cursing: '\u{1F92C}', swearing: '\u{1F92C}', smiling_imp: '\u{1F608}',
    devil: '\u{1F608}', imp: '\u{1F47F}', skull: '\u{1F480}', dead: '\u{1F480}',
    skull_and_crossbones: '☠️', poop: '\u{1F4A9}', hankey: '\u{1F4A9}',
    clown_face: '\u{1F921}', clown: '\u{1F921}', ogre: '\u{1F479}',
    goblin: '\u{1F47A}', ghost: '\u{1F47B}', boo: '\u{1F47B}',
    alien: '\u{1F47D}', space_invader: '\u{1F47E}', robot: '\u{1F916}',
    bot: '\u{1F916}',

    // Gestures
    wave: '\u{1F44B}', hand: '✋', raised_hand: '✋', vulcan: '\u{1F596}',
    ok_hand: '\u{1F44C}', ok: '\u{1F44C}', pinched_fingers: '\u{1F90C}',
    pinching_hand: '\u{1F90F}', v: '✌️', peace: '✌️',
    crossed_fingers: '\u{1F91E}', fingers_crossed: '\u{1F91E}',
    love_you_gesture: '\u{1F91F}', metal: '\u{1F918}', rock: '\u{1F918}',
    call_me_hand: '\u{1F919}', shaka: '\u{1F919}', point_left: '\u{1F448}',
    point_right: '\u{1F449}', point_up_2: '\u{1F446}', point_down: '\u{1F447}',
    point_up: '☝️', middle_finger: '\u{1F595}', fu: '\u{1F595}',
    thumbsup: '\u{1F44D}', thumbs_up: '\u{1F44D}', '+1': '\u{1F44D}',
    like: '\u{1F44D}', yes: '\u{1F44D}', thumbsdown: '\u{1F44E}',
    thumbs_down: '\u{1F44E}', '-1': '\u{1F44E}', dislike: '\u{1F44E}',
    fist: '✊', fist_raised: '✊', facepunch: '\u{1F44A}',
    punch: '\u{1F44A}', clap: '\u{1F44F}', applause: '\u{1F44F}',
    raised_hands: '\u{1F64C}', celebrate: '\u{1F64C}', heart_hands: '\u{1FAF6}',
    open_hands: '\u{1F450}', palms_up: '\u{1F932}', handshake: '\u{1F91D}',
    deal: '\u{1F91D}', pray: '\u{1F64F}', please: '\u{1F64F}',
    thanks: '\u{1F64F}', muscle: '\u{1F4AA}', strong: '\u{1F4AA}',
    flex: '\u{1F4AA}', eyes: '\u{1F440}', look: '\u{1F440}', see: '\u{1F440}',

    // Nature
    dog: '\u{1F436}', puppy: '\u{1F436}', cat: '\u{1F431}', kitten: '\u{1F431}',
    mouse: '\u{1F42D}', hamster: '\u{1F439}', rabbit: '\u{1F430}',
    bunny: '\u{1F430}', fox: '\u{1F98A}', bear: '\u{1F43B}', panda: '\u{1F43C}',
    koala: '\u{1F428}', tiger: '\u{1F42F}', lion: '\u{1F981}', cow: '\u{1F42E}',
    pig: '\u{1F437}', frog: '\u{1F438}', monkey: '\u{1F435}',
    see_no_evil: '\u{1F648}', hear_no_evil: '\u{1F649}', speak_no_evil: '\u{1F64A}',
    chicken: '\u{1F414}', penguin: '\u{1F427}', bird: '\u{1F426}',
    unicorn: '\u{1F984}', bee: '\u{1F41D}', butterfly: '\u{1F98B}',
    snail: '\u{1F40C}', bug: '\u{1F41B}', ladybug: '\u{1F41E}',
    cherry_blossom: '\u{1F338}', rose: '\u{1F339}', sunflower: '\u{1F33B}',
    tulip: '\u{1F337}', seedling: '\u{1F331}', evergreen_tree: '\u{1F332}',
    palm_tree: '\u{1F334}', cactus: '\u{1F335}', four_leaf_clover: '\u{1F340}',
    lucky: '\u{1F340}', maple_leaf: '\u{1F341}', mushroom: '\u{1F344}',

    // Food
    grapes: '\u{1F347}', watermelon: '\u{1F349}', banana: '\u{1F34C}',
    apple: '\u{1F34E}', cherries: '\u{1F352}', strawberry: '\u{1F353}',
    pineapple: '\u{1F34D}', avocado: '\u{1F951}', eggplant: '\u{1F346}',
    tomato: '\u{1F345}', corn: '\u{1F33D}', bread: '\u{1F35E}', cheese: '\u{1F9C0}',
    bacon: '\u{1F953}', hamburger: '\u{1F354}', burger: '\u{1F354}',
    fries: '\u{1F35F}', pizza: '\u{1F355}', hotdog: '\u{1F32D}', hot_dog: '\u{1F32D}',
    taco: '\u{1F32E}', burrito: '\u{1F32F}', sushi: '\u{1F363}', ramen: '\u{1F35C}',
    noodles: '\u{1F35C}', rice: '\u{1F35A}', curry: '\u{1F35B}',
    ice_cream: '\u{1F366}', donut: '\u{1F369}', cookie: '\u{1F36A}',
    cake: '\u{1F382}', birthday_cake: '\u{1F382}', chocolate: '\u{1F36B}',
    candy: '\u{1F36C}', honey: '\u{1F36F}', coffee: '☕', tea: '\u{1F375}',
    beer: '\u{1F37A}', beers: '\u{1F37B}', wine: '\u{1F377}', cocktail: '\u{1F378}',

    // Activities
    soccer: '⚽', football: '\u{1F3C8}', basketball: '\u{1F3C0}',
    baseball: '⚾', tennis: '\u{1F3BE}', volleyball: '\u{1F3D0}',
    trophy: '\u{1F3C6}', winner: '\u{1F3C6}', first_place: '\u{1F947}',
    gold_medal: '\u{1F947}', dart: '\u{1F3AF}', target: '\u{1F3AF}',
    bullseye: '\u{1F3AF}', video_game: '\u{1F3AE}', gaming: '\u{1F3AE}',
    controller: '\u{1F3AE}', dice: '\u{1F3B2}', headphones: '\u{1F3A7}',
    music: '\u{1F3B5}', notes: '\u{1F3B6}', guitar: '\u{1F3B8}',
    drum: '\u{1F941}', mic: '\u{1F3A4}', microphone: '\u{1F3A4}',

    // Travel
    car: '\u{1F697}', taxi: '\u{1F695}', bus: '\u{1F68C}', truck: '\u{1F69A}',
    motorcycle: '\u{1F3CD}️', bike: '\u{1F6B2}', train: '\u{1F686}',
    airplane: '✈️', plane: '✈️', rocket: '\u{1F680}',
    launch: '\u{1F680}', helicopter: '\u{1F681}', ship: '\u{1F6A2}',
    sailboat: '⛵', house: '\u{1F3E0}', home: '\u{1F3E0}',
    office: '\u{1F3E2}', school: '\u{1F3EB}', sunset: '\u{1F305}',
    rainbow: '\u{1F308}', mountain: '⛰️', beach: '\u{1F3D6}️',

    // Objects
    watch: '⌚', phone: '\u{1F4F1}', mobile: '\u{1F4F1}',
    computer: '\u{1F4BB}', laptop: '\u{1F4BB}', desktop: '\u{1F5A5}️',
    keyboard: '⌨️', camera: '\u{1F4F7}', tv: '\u{1F4FA}',
    radio: '\u{1F4FB}', clock: '\u{1F570}️', alarm_clock: '⏰',
    bulb: '\u{1F4A1}', lightbulb: '\u{1F4A1}', idea: '\u{1F4A1}',
    flashlight: '\u{1F526}', candle: '\u{1F56F}️',
    money: '\u{1F4B0}', moneybag: '\u{1F4B0}', dollar: '\u{1F4B5}',
    credit_card: '\u{1F4B3}', key: '\u{1F511}', lock: '\u{1F512}',
    unlock: '\u{1F513}', door: '\u{1F6AA}', gift: '\u{1F381}',
    present: '\u{1F381}', balloon: '\u{1F388}', tada: '\u{1F389}',
    confetti: '\u{1F389}', party_popper: '\u{1F389}',
    ribbon: '\u{1F380}', sparkles: '✨', sparkle: '✨',
    glitter: '✨', envelope: '✉️', email: '\u{1F4E7}',
    mail: '\u{1F4E7}', package: '\u{1F4E6}', book: '\u{1F4D5}',
    books: '\u{1F4DA}', pen: '\u{1F58A}️', pencil: '✏️',
    search: '\u{1F50D}', magnifying_glass: '\u{1F50D}',
    bell: '\u{1F514}', notification: '\u{1F514}',
    hammer: '\u{1F528}', wrench: '\u{1F527}', gear: '⚙️',
    settings: '⚙️', link: '\u{1F517}', chain: '\u{1F517}',

    // Symbols
    fire: '\u{1F525}', flame: '\u{1F525}', hot: '\u{1F525}', lit: '\u{1F525}',
    heart: '❤️', love: '❤️', red_heart: '❤️',
    orange_heart: '\u{1F9E1}', yellow_heart: '\u{1F49B}',
    green_heart: '\u{1F49A}', blue_heart: '\u{1F499}',
    purple_heart: '\u{1F49C}', black_heart: '\u{1F5A4}',
    white_heart: '\u{1F90D}', broken_heart: '\u{1F494}',
    heartbreak: '\u{1F494}', two_hearts: '\u{1F495}',
    sparkling_heart: '\u{1F496}',
    '100': '\u{1F4AF}', hundred: '\u{1F4AF}', perfect: '\u{1F4AF}',
    boom: '\u{1F4A5}', explosion: '\u{1F4A5}', dash: '\u{1F4A8}',
    speech_balloon: '\u{1F4AC}', chat: '\u{1F4AC}', thought_balloon: '\u{1F4AD}',
    star: '⭐', dizzy: '\u{1F4AB}', sun: '☀️',
    moon: '\u{1F319}', cloud: '☁️', rain: '\u{1F327}️',
    snow: '❄️', snowflake: '❄️',
    zap: '⚡', lightning: '⚡', high_voltage: '⚡',
    earth: '\u{1F30D}', globe: '\u{1F30D}', world: '\u{1F30D}',
    check: '✅', checkmark: '✅', white_check_mark: '✅',
    done: '✅', complete: '✅',
    x: '❌', cross: '❌', wrong: '❌', no: '❌',
    warning: '⚠️', caution: '⚠️', alert: '⚠️',
    exclamation: '❗', question: '❔',
    arrow_right: '➡️', arrow_left: '⬅️',
    arrow_up: '⬆️', arrow_down: '⬇️',
    new: '\u{1F195}', tm: '™️', trademark: '™️',
    copyright: '©️', registered: '®️',
    heavy_check_mark: '✔️',

    // Flags
    checkered_flag: '\u{1F3C1}', triangular_flag: '\u{1F6A9}',
    red_flag: '\u{1F6A9}', rainbow_flag: '\u{1F3F3}️‍\u{1F308}',
    pride: '\u{1F3F3}️‍\u{1F308}',
    pirate_flag: '\u{1F3F4}‍☠️',
    us: '\u{1F1FA}\u{1F1F8}', usa: '\u{1F1FA}\u{1F1F8}',
  };

  function applyEmojiShortcodes(text) {
    if (!text) return text;
    return String(text).replace(EMOJI_CODE_RE, (m, code) => {
      const lower = code.toLowerCase();
      return EMOJI_SHORTCODES[lower] || m;
    });
  }

  window.AgixtTeamChatHelpers = {
    md5,
    gravatarUrl,
    parseReply,
    applyMentions,
    applyEmojiShortcodes,
    extractFirstFewUrls,
    EMOJI_SHORTCODES,
  };
})();
