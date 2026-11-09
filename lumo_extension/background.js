// While a patrol runs, a tab that opens a watched SNS is sent to the Lumo app's Shield page.
// The Shield's buttons come back here: "やっぱやめとく" closes the tab, "開く" lets it through.
// State is kept in chrome.storage.session because Chrome may stop this service worker at any time.
import { isActive, serviceFor } from './rules.js';

const get = (keys) => chrome.storage.session.get(keys);
const set = (items) => chrome.storage.session.set(items);

async function shield(tabId, url) {
  const { lumo, allowed = [], blocked = {} } = await get(['lumo', 'allowed', 'blocked']);
  if (!isActive(lumo, Date.now()) || allowed.includes(tabId)) return;
  const service = serviceFor(url, lumo.watched);
  if (!service) return;
  blocked[tabId] = url; // where to go if the user taps "開く"
  await set({ blocked });
  await chrome.tabs.update(tabId, { url: `${lumo.app}/?shield=${service}` });
}

// A new page load, and in-app navigation of sites like Instagram (they change the URL without reloading).
chrome.webNavigation.onBeforeNavigate.addListener(({ tabId, frameId, url }) => frameId === 0 && shield(tabId, url));
chrome.webNavigation.onHistoryStateUpdated.addListener(({ tabId, frameId, url }) => frameId === 0 && shield(tabId, url));

chrome.runtime.onMessage.addListener((msg, sender) => {
  handle(msg, sender);
});

async function handle(msg, sender) {
  const tabId = sender.tab?.id;
  if (msg.type === 'state') {
    // From bridge.js on the Lumo app: what is watched, and until when.
    const { lumo } = await get('lumo');
    const next = { endsAt: msg.endsAt, watched: msg.watched, app: sender.origin };
    await set({ lumo: next });
    if (lumo?.endsAt !== next.endsAt) {
      await set({ allowed: [], blocked: {} }); // a new patrol: forget earlier "開く" choices
      // SNS tabs that were already open when the patrol started are covered too.
      for (const tab of await chrome.tabs.query({})) if (tab.url) await shield(tab.id, tab.url);
    }
  } else if (msg.type === 'close' && tabId != null) {
    await chrome.tabs.remove(tabId);
  } else if (msg.type === 'allow' && tabId != null) {
    const { blocked = {}, allowed = [] } = await get(['blocked', 'allowed']);
    if (!blocked[tabId]) return;
    await set({ allowed: [...allowed, tabId] }); // only this tab, only for this patrol
    await chrome.tabs.update(tabId, { url: blocked[tabId] });
  }
}

chrome.tabs.onRemoved.addListener(async (tabId) => {
  const { blocked = {}, allowed = [] } = await get(['blocked', 'allowed']);
  delete blocked[tabId];
  await set({ blocked, allowed: allowed.filter((t) => t !== tabId) });
});
