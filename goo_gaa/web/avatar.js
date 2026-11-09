/*
 * AVATAR SLOT - the single swap point for the avatar. Replace this file to change how it looks.
 *
 * Contract (keep these two functions; nothing else needs to change):
 *   Avatar.mount(el)     called once with the #avatar element. Build your DOM / canvas /
 *                        <img> / Lottie player inside `el`.
 *   Avatar.update(state) called every second with the state from Python:
 *                        {
 *                          social_seconds: number,
 *                          total_seconds:  number,
 *                          avatar: null | {            // null until the cloud has answered, or when not configured
 *                            mood:    "happy" | "uneasy" | "grumpy" | "angry" | "watching",
 *                                     // ("watching" = browsing SNS for the user; set by the page)
 *                            message: string,          // what the avatar says (Gemini, or a fixed
 *                            action:  string,          //   fallback line); action = one small step
 *                            source:  "gemini" | "fallback"
 *                          }
 *                        }
 *                        New fields are only ever ADDED, never renamed.
 *
 * The picture is NOT in the state (it would cross the bridge every second). Ask for it once per mood:
 *   const dataUrl = await window.pywebview.api.get_avatar_image(mood);   // "data:image/png;base64,..." | null
 * and use it as an <img src>. null means the server has no picture for that mood: keep a fallback.
 *
 * STARTUP: the cloud's first answer takes seconds (and never comes when offline), so the avatar must not
 * be empty meanwhile. As soon as the bridge is ready this shows the picture for START_MOOD, taken from
 * the SAME call (get_avatar_image) - Python falls back to the picture that ships with the app. When the
 * cloud answers, the normal update() path takes over. A custom avatar should do the same: draw something
 * immediately, never wait for state.avatar.
 *
 * This default shows the server's picture + words. A custom avatar may ignore either (for example
 * draw its own art from `mood` and use only `message`). The speech line is `#speech` in index.html.
 */
const START_MOOD = 'happy';  // what a fresh start looks like: nothing has gone wrong yet

window.Avatar = {
  _img: null,
  _placeholder: null,
  _speech: null,
  _mood: null,    // the mood the CLOUD last reported (null until it has answered)
  _wanted: null,  // the mood whose picture we most recently asked for (to drop stale answers)

  mount(el) {
    el.innerHTML =
      '<img class="avatar-img" alt="" hidden>' +
      '<div class="avatar-placeholder" aria-hidden="true"></div>';
    this._img = el.querySelector('.avatar-img');
    this._placeholder = el.querySelector('.avatar-placeholder');
    this._speech = document.getElementById('speech');

    // The bridge to Python is not usable at load; this event says when it is.
    window.addEventListener('pywebviewready', () => {
      // If the cloud somehow answered first, its mood wins: never overwrite it with the start picture.
      if (this._mood === null) this._showPicture(START_MOOD);
    });
  },

  update(state) {
    const a = state.avatar;
    if (!a) return;  // not answered yet / offline: keep the start picture, nothing to say yet

    if (a.mood !== this._mood) {
      this._mood = a.mood;
      this._showPicture(a.mood);
    }
    this._say(a);
  },

  async _showPicture(mood) {
    this._wanted = mood;
    let url = null;
    try {
      url = await window.pywebview.api.get_avatar_image(mood);
    } catch (e) {
      // keep whatever is on screen; the next mood change tries again
    }
    if (this._wanted !== mood) return;  // a newer request was made while we waited: stale answer
    if (url) {
      this._img.src = url;
      this._img.hidden = false;
      this._placeholder.hidden = true;
    } else {
      this._img.hidden = true;        // the server has no picture for this mood
      this._placeholder.hidden = false;
    }
  },

  _say(a) {
    // textContent (never innerHTML): the words come from an AI model, so treat them as untrusted text.
    // Only the main line is shown. `a.action` (the small second line) is still in the state, but the
    // widget does not display it.
    this._speech.textContent = a.message || '';
    this._speech.hidden = !a.message;
  },
};
