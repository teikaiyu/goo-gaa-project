// Page logic: memo box, "watch SNS for me" switch, small time line.
// Knows nothing about the avatar's internals - it only calls Avatar.update().

const card = document.getElementById('card');
const timeEl = document.getElementById('time');
const noteForm = document.getElementById('note-form');
const noteInput = document.getElementById('note-input');
const noteList = document.getElementById('note-list');
const briefList = document.getElementById('brief-list');

const api = () => window.pywebview.api;

function formatHMS(totalSeconds) {
  const s = Math.max(0, Math.floor(totalSeconds));
  const hh = String(Math.floor(s / 3600)).padStart(2, '0');
  const mm = String(Math.floor((s % 3600) / 60)).padStart(2, '0');
  const ss = String(s % 60).padStart(2, '0');
  return `${hh}:${mm}:${ss}`;
}

// ---------- rendering notes ----------
// Memo text and research text are user/AI-provided: only ever textContent, never innerHTML.
function li(className, ...parts) {
  const el = document.createElement('li');
  el.className = className;
  for (const [cls, text] of parts) {
    const span = document.createElement('span');
    span.className = cls;
    span.textContent = text;
    el.appendChild(span);
  }
  return el;
}

function renderNotes(notes) {
  noteList.replaceChildren();
  for (const n of notes) {
    const item = li('note', ['note-text', n.text],
      ['note-state', n.research ? '✓ 調べ済み' : '… 下調べ中']);
    const del = document.createElement('button');
    del.type = 'button';
    del.className = 'note-del';
    del.title = '削除';
    del.textContent = '×';
    del.addEventListener('click', async () => { await api().delete_note(n.id); refreshNotes(); });
    item.appendChild(del);
    noteList.appendChild(item);
  }
}

// The watch view lists what the avatar SAW (watch.items), then what it had prepared (memo research).
let lastBriefKey = '';
function renderBriefing(watch) {
  const prepared = notes.filter((n) => n.research);
  const key = JSON.stringify([watch.items, prepared.map((n) => n.id)]);
  if (key === lastBriefKey) return;  // unchanged: do not rebuild (it would reset the list's scroll position)
  lastBriefKey = key;
  briefList.replaceChildren();
  if (watch.items.length > 0) briefList.appendChild(li('brief-head', ['note-state', 'いま見ているもの']));
  for (const it of watch.items) {
    briefList.appendChild(li('note', ['note-text', it.title], ['note-research', it.gist]));
  }
  if (prepared.length > 0) {
    briefList.appendChild(li('brief-head', ['note-state', '調べておいたこと']));
    for (const n of prepared) {
      briefList.appendChild(li('note', ['note-text', n.text],
        ['note-research', n.research.summary], ['note-next', '→ ' + n.research.next_step]));
    }
  }
}

let notes = [];
async function refreshNotes() {
  try {
    notes = await api().list_notes();
    renderNotes(notes);
  } catch (e) { /* keep what is shown; the next refresh retries */ }
}

// ---------- views ----------
function setView(view) {
  card.dataset.view = view;
  document.body.classList.toggle('watching', view === 'watch');
}

// The avatar's own line about the watch, or null when it has nothing to say about it.
//   watching  -> what it is looking at now (the cloud's spoken line)
//   recapping -> "summing up..." (after the user pressed back)
//   recap     -> how it went (shown for a minute, in the memo view too)
function watchLine(watch) {
  if (watch.status === 'watching' || watch.status === 'recapping') return watch.report;
  if (watch.status === 'recap') return watch.recap;
  return null;
}

noteForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  const text = noteInput.value;
  noteInput.value = '';
  await api().add_note(text);
  refreshNotes();
});
// Enter saves, Shift+Enter makes a new line.
noteInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {  // isComposing: Enter that confirms Japanese IME text
    e.preventDefault();
    noteForm.requestSubmit();
  }
});

document.getElementById('watch-start').addEventListener('click', async () => {
  await refreshNotes();
  await api().set_watching(true);
  setView('watch');
});
document.getElementById('watch-stop').addEventListener('click', async () => {
  await api().set_watching(false);
  setView('memo');
});

// ---------- polling ----------
function render(state) {
  timeEl.textContent = formatHMS(state.social_seconds);
  const watch = state.watch;
  if (state.watching) renderBriefing(watch);
  const line = watchLine(watch);
  // The avatar talks about the watch through the same speech line it always uses (Avatar contract unchanged).
  // While it browses SNS it wears the "watching" look (one of two phone pictures, random per session);
  // for the recap it is happy again.
  const mood = state.watching ? 'watching' : 'happy';
  window.Avatar.update(line
    ? { ...state, avatar: { mood, message: line, action: null, source: 'gemini' } }
    : state);
}

async function tick() {
  try {
    render(await api().get_state());
  } catch (e) {
    // Keep the last value on screen if one poll fails; the next tick retries.
  }
}

window.Avatar.mount(document.getElementById('avatar'));
document.getElementById('close').addEventListener('click', () => api().quit());

// The bridge to Python is not ready at page load; this event says when it is.
window.addEventListener('pywebviewready', () => {
  tick();
  setInterval(tick, 1000);
  refreshNotes();
  setInterval(refreshNotes, 5000);  // picks up research results that finished in the background
});
