import assert from 'node:assert/strict';
import { test } from 'node:test';

import { isActive, serviceFor } from './rules.js';

test('watched SNS sites are recognised, subdomains included', () => {
  assert.equal(serviceFor('https://www.instagram.com/stories/a/', ['instagram']), 'instagram');
  assert.equal(serviceFor('https://instagram.com/', ['instagram']), 'instagram');
  assert.equal(serviceFor('https://twitter.com/home', ['x']), 'x');
  assert.equal(serviceFor('https://m.youtube.com/', ['youtube']), 'youtube');
});

test('unwatched apps, look-alikes and junk are left alone', () => {
  assert.equal(serviceFor('https://www.instagram.com/', ['x']), null);
  assert.equal(serviceFor('https://instagram.com.evil.io/', ['instagram']), null);
  assert.equal(serviceFor('https://notinstagram.com/', ['instagram']), null);
  assert.equal(serviceFor('not a url', ['instagram']), null);
  assert.equal(serviceFor('https://www.instagram.com/', undefined), null);
});

test('a patrol is active only before it ends and with something watched', () => {
  assert.equal(isActive({ endsAt: 2000, watched: ['x'] }, 1000), true);
  assert.equal(isActive({ endsAt: 1000, watched: ['x'] }, 1000), false);
  assert.equal(isActive({ endsAt: 2000, watched: [] }, 1000), false);
  assert.equal(isActive(undefined, 1000), false);
});

test('apps the user added (site:<host>) are recognised like the built-in ones', () => {
  const watched = ['site:mail.google.com', 'site:discord.com'];
  assert.equal(serviceFor('https://mail.google.com/mail/u/0/', watched), 'site:mail.google.com');
  assert.equal(serviceFor('https://discord.com/channels/@me', watched), 'site:discord.com');
  assert.equal(serviceFor('https://canary.discord.com/app', watched), 'site:discord.com'); // subdomain
  assert.equal(serviceFor('https://www.google.com/', watched), null); // only the chosen host, not its parent
  assert.equal(serviceFor('https://discord.com.evil.io/', watched), null);
  assert.equal(serviceFor('https://mail.google.com/', ['instagram']), null); // not switched on
});

test('a malformed custom key never matches (it must not shield a whole domain ending by accident)', () => {
  for (const key of ['site:', 'site:com', 'site:localhost', 'site:.com', 'site:a b.com', 'discord.com']) {
    assert.equal(serviceFor('https://discord.com/', [key]), null, key);
    assert.equal(serviceFor('https://example.com/', [key]), null, key);
  }
});
