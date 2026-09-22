/**
 * What the bot puts a reaction on, run against real messages from the group.
 *
 *   node --test marks.test.js
 *
 * This is the part of the feature that can embarrass us. The bot is about
 * to mark messages in a group of 390 people who are also judging it, and a
 * grin on the wrong message is remembered longer than a useful one on the
 * right message.
 */

import assert from 'node:assert/strict';
import { test } from 'node:test';

import { worthMarking, writtenByABot } from './marks.js';

test('a session recording is worth keeping', () => {
  const message =
    'Today the Wadhwani Module 2 class covered identifying customers and ' +
    'validating their needs. The session recording is here: ' +
    'https://youtu.be/C9gaW26GfWw';

  assert.equal(worthMarking(message), '📌');
});

test('a date somebody has to act on beats the link next to it', () => {
  const message =
    'Participants were asked to complete their tests by Friday 25 September. ' +
    'Details here: https://example.org/tests';

  assert.equal(worthMarking(message), '⏰');
});

test('the deadline words this group actually uses, in both languages', () => {
  for (const message of [
    'Reminder, the submission deadline for the hackathon is Thursday 24 September 2026.',
    'Merci de rendre vos vidéos avant le jeudi 24 septembre, date limite ferme.',
    'All team declarations are due by Thursday, no later than close of business.',
  ]) {
    assert.equal(worthMarking(message), '⏰', message);
  }
});

test('a joke somebody has already flagged as one', () => {
  // Posted in the group. Sixteen characters, and every human in the group
  // smiled at it.
  assert.equal(worthMarking('Make me admin🌝'), '😄');
  assert.equal(worthMarking('I have been refreshing since 6am 😂'), '😄');
  assert.equal(worthMarking('haha the bot beat me to it'), null); // mentions the bot
});

test('a complaint with a laughing face is never laughed at', () => {
  // This complaint was made in this group, by name. A grin on it is the
  // single worst thing this feature could do.
  for (const message of [
    'the bot is flooding the group 😅',
    'this is spam at this point 😂',
    'it is getting annoying 🤣',
  ]) {
    assert.equal(worthMarking(message), null, message);
  }
});

test('an announcement with a smiley in it is not a joke', () => {
  const message =
    'Welcome everyone to cohort 1 🙂 We are glad you are here and we will ' +
    'be sharing the full programme schedule with all of you later today.';

  assert.notEqual(worthMarking(message), '😄');
});

test('ordinary conversation is left alone', () => {
  for (const message of [
    'ok',
    'Thanks',
    '2PM',
    'Yes, not so much new, business as usual',
    'I could not join the call today, was it recorded',
  ]) {
    assert.equal(worthMarking(message), null, message);
  }
});

test('a one line reply carrying a link is not an announcement', () => {
  assert.equal(worthMarking('here https://x.co/a'), null);
});

test('another team bot is never marked', () => {
  // Marking its announcement would read as ours endorsing it, in front of
  // the group that is judging both.
  assert.equal(writtenByABot('meti_bot'), true);
  assert.equal(writtenByABot('Nexus Bot'), true);
  assert.equal(writtenByABot('UniConnect-BOT'), true);
  assert.equal(writtenByABot('Akpan, Victor D.'), false);
});
