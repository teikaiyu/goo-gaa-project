// Pure rules (no Chrome APIs), so they can be tested with plain Node: node --test lumo_extension/

// The web version of each app Lumo can watch (keys match lumo_app/lib/lumo.dart serviceNames).
export const SITES = {
  instagram: ['instagram.com'],
  x: ['x.com', 'twitter.com'],
  youtube: ['youtube.com'],
};

/** Which watched app this URL belongs to, or null. Subdomains count (www., m.); look-alikes do not. */
export function serviceFor(url, watched) {
  let host;
  try {
    host = new URL(url).hostname.toLowerCase();
  } catch {
    return null;
  }
  return (watched || []).find((s) => (SITES[s] || []).some((d) => host === d || host.endsWith('.' + d))) || null;
}

/** Is a patrol running right now? `lumo` is what the app reported: {endsAt (ms), watched, app (origin)}. */
export const isActive = (lumo, now) => !!lumo && lumo.endsAt > now && (lumo.watched || []).length > 0;
