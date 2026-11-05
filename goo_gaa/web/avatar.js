/*
 * AVATAR SLOT - the single swap point for the future avatar.
 *
 * Contract (keep these two functions and nothing else changes):
 *   Avatar.mount(el)     called once with the #avatar element. Build your DOM / canvas /
 *                        <img> / Lottie player inside `el`.
 *   Avatar.update(state) called every second with the state from Python:
 *                        { social_seconds: number, total_seconds: number }
 *                        (new fields such as `mood` will be ADDED later, never renamed).
 *
 * To replace the placeholder: edit this file and put assets next to it (e.g. web/avatar/).
 * Do not touch app.js, index.html's readout, or any Python code.
 */
window.Avatar = {
  mount(el) {
    // Placeholder only: a plain circle so the layout reserves the avatar's space.
    el.innerHTML = '<div class="avatar-placeholder" aria-hidden="true"></div>';
  },
  update(state) {
    // Placeholder does nothing. The real avatar will react to `state` here.
  },
};
