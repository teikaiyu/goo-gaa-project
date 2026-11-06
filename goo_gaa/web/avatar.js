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
 *                          avatar: null | {            // null until the cloud has answered, or when
 *                            mood:    "happy" | "uneasy" | "grumpy" | "angry",   // not configured
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
 * This default shows the server's picture + words. A custom avatar may ignore either (for example
 * draw its own art from `mood` and use only `message`). The speech line is `#speech` in index.html.
 */
window.Avatar = {
  _img: null,
  _placeholder: null,
  _speech: null,
  _mood: null,

  mount(el) {
    el.innerHTML =
      '<img class="avatar-img" alt="" hidden>' +
      '<div class="avatar-placeholder" aria-hidden="true"></div>';
    this._img = el.querySelector('.avatar-img');
    this._placeholder = el.querySelector('.avatar-placeholder');
    this._speech = document.getElementById('speech');
  },

  update(state) {
    const a = state.avatar;
    if (!a) return;  // offline or not configured: keep the placeholder, nothing to say yet

    if (a.mood !== this._mood) {
      this._mood = a.mood;
      this._showPicture(a.mood);
    }
    this._say(a);
  },

  async _showPicture(mood) {
    let url = null;
    try {
      url = await window.pywebview.api.get_avatar_image(mood);
    } catch (e) {
      // keep whatever is on screen; the next mood change tries again
    }
    if (this._mood !== mood) return;  // the mood changed again while we were waiting: stale answer
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
    this._speech.textContent = a.message || '';
    if (a.action) {
      const span = document.createElement('span');
      span.className = 'action';
      span.textContent = a.action;
      this._speech.appendChild(span);
    }
    this._speech.hidden = !a.message;
  },
};
