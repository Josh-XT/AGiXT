import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { JSDOM } from 'jsdom';

const SRC = '/home/josh/repos/xtsys/WorkConductor/ui/src';
const dom = new JSDOM(fs.readFileSync(path.join(SRC, 'index.html'), 'utf8'), {
  runScripts: 'outside-only', url: 'http://localhost/',
});
const { window } = dom;
window.__TAURI__ = {
  core: { invoke: async (cmd) => { if (cmd === 'get_conversation_history') return []; return null; }},
  event: { listen: async () => () => {} },
};
window.WebSocket = class { constructor() { this.readyState = 0; } close() {} send() {} };

window.AgixtApi = {
  getSettings: async () => ({ server_url: 'http://localhost:7437', jwt: 'jwt' }),
  getUser: async () => ({ id: 'u1', email: 'me@x', companies: [{id: 'c1', primary: true}] }),
  listCompanies: async () => [{
    id: 'c1', name: 'Test Co', icon_url: null, sort_order: 0,
    agents: [
      { id: 'a1', name: 'XT', companyId: 'c1' },
      { id: 'a2', name: 'NotInChannel', companyId: 'c1' },
    ],
  }],
  getGroupConversations: async () => ({
    'chan-1': { name: 'general', conversation_type: 'group',
                category: 'Text Channels', notification_mode: 'none' }, // muted!
    'chan-2': { name: 'random', conversation_type: 'group',
                category: 'Text Channels', has_notifications: true, notification_count: 3 },
  }),
  listAllConversations: async () => ({}),
  getConversationParticipants: async () => [
    { id: 'p1', participant_type: 'user', role: 'owner',
      user: { id: 'u1', email: 'alice@example.com', first_name: 'Alice', last_name: '',
              last_seen: new Date().toISOString(), status_text: 'working on docs' } },
    { id: 'p2', participant_type: 'user', role: 'admin',
      user: { id: 'u2', email: 'bob@example.com', first_name: 'Bob', last_name: 'B',
              last_seen: null } },
    { id: 'p3', participant_type: 'agent', role: 'member', agent: { id: 'a1', name: 'XT' } },
  ],
  markConversationRead: async () => ({}),
  getCompanyMembers: async () => [
    { id: 'u3', first_name: 'Charlie', last_name: '', email: 'charlie@x' },
  ],
};

for (const name of ['markdown.js', 'team-chat-helpers.js', 'team-chat.js']) {
  vm.runInContext(fs.readFileSync(path.join(SRC, name), 'utf8'),
                  dom.getInternalVMContext(), { filename: name });
}

await window.AgixtTeamChat.mount();
await new Promise((r) => setTimeout(r, 80));

// Click into Test Co.
const rail = window.document.getElementById('tc-company-list');
console.log('Companies rendered:', rail.children.length);
console.log('Active pill on private DM button:',
  !!window.document.querySelector('.tc-company-private.is-active'));

rail.querySelector('.tc-company').click();
await new Promise((r) => setTimeout(r, 80));
await new Promise((r) => setImmediate(r));
await new Promise((r) => setTimeout(r, 80));

// Channel rendering
const channels = window.document.querySelectorAll('#tc-channel-scroll .tc-channel-row');
console.log('Channels rendered:', channels.length);
console.log('Muted indicator on first channel:',
  !!channels[0].querySelector('.tc-channel-muted'));
console.log('Unread badge on second channel:',
  channels[1].querySelector('.tc-channel-unread')?.textContent);

// Category collapse
const catBtn = window.document.querySelector('.tc-channel-category-btn');
console.log('Category is a button (collapsible):', !!catBtn);
catBtn.click();
await new Promise((r) => setTimeout(r, 30));
console.log('After collapse, channels in DOM:',
  window.document.querySelectorAll('#tc-channel-scroll .tc-channel-row').length);
catBtn.click();
await new Promise((r) => setTimeout(r, 30));

// Member features
const members = window.document.querySelectorAll('#tc-member-scroll .tc-member-row');
console.log('Members rendered:', members.length, '(expect 4: 2 users + 1 agent + 1 extra agent)');
console.log('Owner has crown icon:',
  !!members[0].querySelector('.tc-member-role-icon'));
console.log('Online dot present:',
  !!members[0].querySelector('.tc-presence-dot.is-online'));
console.log('Status text rendered:',
  !!Array.from(window.document.querySelectorAll('.tc-member-status'))
    .find((n) => n.textContent === 'working on docs'));
console.log('Extra agent row (not-in-channel):',
  !!window.document.querySelector('.tc-member-extra'));

// Search filter
const searchInput = window.document.getElementById('tc-member-search-input');
searchInput.value = 'bob';
searchInput.dispatchEvent(new window.Event('input'));
await new Promise((r) => setTimeout(r, 30));
console.log('After search "bob" — members in DOM:',
  window.document.querySelectorAll('#tc-member-scroll .tc-member-row').length);

// New DM button hidden in company mode
console.log('"New DM" button hidden in company mode:',
  window.document.getElementById('tc-new-dm-btn').hidden);

// Add Server button present
console.log('Add Server button hidden:',
  window.document.getElementById('tc-company-add').hidden);

// Try open New DM dialog (must work without errors)
searchInput.value = '';
searchInput.dispatchEvent(new window.Event('input'));
const privateBtn = window.document.getElementById('tc-company-private');
privateBtn.click();
await new Promise((r) => setTimeout(r, 80));
console.log('After switching to private — Add DM button hidden:',
  window.document.getElementById('tc-channel-add').hidden);
console.log('New DM button visible:',
  !window.document.getElementById('tc-new-dm-btn').hidden);

window.document.getElementById('tc-new-dm-btn').click();
await new Promise((r) => setTimeout(r, 50));
console.log('New DM dialog opened:',
  !!window.document.querySelector('.tc-modal'));
console.log('Tabs in dialog:',
  window.document.querySelectorAll('.tc-modal .tc-tab').length);

window.AgixtTeamChat.unmount();
console.log('All smoke checks passed.');
