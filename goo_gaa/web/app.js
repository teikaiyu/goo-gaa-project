// Readout logic. Knows nothing about the avatar's internals - it only calls Avatar.update().

const timeEl = document.getElementById('time');

function formatHMS(totalSeconds) {
  const s = Math.max(0, Math.floor(totalSeconds));
  const hh = String(Math.floor(s / 3600)).padStart(2, '0');
  const mm = String(Math.floor((s % 3600) / 60)).padStart(2, '0');
  const ss = String(s % 60).padStart(2, '0');
  return `${hh}:${mm}:${ss}`;
}

function render(state) {
  timeEl.textContent = formatHMS(state.social_seconds);
  window.Avatar.update(state);
}

async function tick() {
  try {
    render(await window.pywebview.api.get_state());
  } catch (e) {
    // Keep the last value on screen if one poll fails; the next tick retries.
  }
}

window.Avatar.mount(document.getElementById('avatar'));
document.getElementById('close').addEventListener('click', () => window.pywebview.api.quit());

// The bridge to Python is not ready at page load; this event says when it is.
window.addEventListener('pywebviewready', () => {
  tick();
  setInterval(tick, 1000);
});
