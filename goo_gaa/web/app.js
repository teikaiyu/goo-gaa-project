// Page logic: memo box, "watch SNS for me" switch, small time line.
// Knows nothing about the avatar's internals - it only calls Avatar.update().

const card = document.getElementById('card');
const timeEl = document.getElementById('time');
const noteForm = document.getElementById('note-form');
const noteInput = document.getElementById('note-input');
const noteList = document.getElementById('note-list');
const briefList = document.getElementById('brief-list');
const watchStatus = document.getElementById('watch-status');

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

// What the avatar tells when it takes over SNS: the prepared research, memo by memo.
function renderBriefing(notes) {
  briefList.replaceChildren();
  const done = notes.filter((n) => n.research);
  if (done.length === 0) {
    briefList.appendChild(li('note', ['note-text', '下調べしたものはまだないよ']));
    return;
  }
  for (const n of done) {
    briefList.appendChild(li('note', ['note-text', n.text],
      ['note-research', n.research.summary], ['note-next', '→ ' + n.research.next_step]));
  }
}

let notes = [];
async function refreshNotes() {
  try {
    notes = await api().list_notes();
    renderNotes(notes);
    if (card.dataset.view === 'watch') renderBriefing(notes);
  } catch (e) { /* keep what is shown; the next refresh retries */ }
}

// ---------- views ----------
function setView(view) {
  card.dataset.view = view;
  document.body.classList.toggle('watching', view === 'watch');
  if (view === 'watch') {
    renderBriefing(notes);
    const n = notes.filter((x) => x.research).length;
    watchStatus.textContent = n > 0 ? `下調べ${n}件、まとめたよ。SNSを見てくるね` : 'SNSを見てくるね';
  }
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
  // While watching, the avatar is busy with its report: keep the picture, do not replace the speech line.
  window.Avatar.update(state.watching ? { ...state, avatar: null } : state);
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
