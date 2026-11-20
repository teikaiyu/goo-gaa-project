// Pure rules (no Chrome APIs), so they can be tested with plain Node: node --test lumo_extension/

// The web version of each built-in app Lumo can watch (keys match lumo_app/lib/lumo.dart serviceNames).
export const SITES = {
  instagram: ['instagram.com'],
  x: ['x.com', 'twitter.com'],
  youtube: ['youtube.com'],
};

/** Apps the user added by hand are watched as `site:<host>` (lumo_app/lib/lumo.dart customPrefix). */
const CUSTOM = 'site:';

/** The domains a watched key stands for. A custom host needs a dot ("com" or "localhost" would shield far too much). */
function domainsOf(key) {
  if (SITES[key]) return SITES[key];
  const host = typeof key === 'string' && key.startsWith(CUSTOM) ? key.slice(CUSTOM.length).toLowerCase() : '';
  return /^([a-z0-9-]+\.)+[a-z]{2,}$/.test(host) ? [host] : [];
}

/** Which watched app this URL belongs to, or null. Subdomains count (www., m.); look-alikes do not. */
export function serviceFor(url, watched) {
  let host;
  try {
    host = new URL(url).hostname.toLowerCase();
  } catch {
    return null;
  }
  return (watched || []).find((s) => domainsOf(s).some((d) => host === d || host.endsWith('.' + d))) || null;
}

/** Is a patrol running right now? `lumo` is what the app reported: {endsAt (ms), watched, app (origin)}. */
export const isActive = (lumo, now) => !!lumo && lumo.endsAt > now && (lumo.watched || []).length > 0;
