/**
 * What is worth marking with a reaction, and what is not.
 *
 * Kept apart from index.js so it can be run against real messages without
 * starting a WhatsApp session. The decision is the whole feature: the
 * mechanics of sending a reaction are four lines, and choosing what to put
 * one on is the part that can embarrass us in front of 390 people.
 *
 * Nothing here talks to WhatsApp, to the API or to a model. It is text in,
 * emoji or null out, and it costs nothing to run on every message.
 */

// Below this a message is not an announcement, whatever it contains. It
// keeps the bot off one line replies that happen to carry a link.
export const MIN_CHARS = 60;

const A_LINK = /https?:\/\/\S+/i;

// A date somebody has to act on, in the words this group actually uses.
const A_DEADLINE = [
  'deadline', 'due by', 'due on', 'due:', 'submit by', 'closes', 'closing',
  'no later than', 'last day', 'by friday', 'by thursday', 'by monday',
  'by tuesday', 'by wednesday', 'by sunday', 'by saturday',
  'date limite', 'échéance', 'echeance', 'avant le', 'au plus tard',
  'dernier délai', 'dernier delai', 'à rendre', 'a rendre',
];

// Phone keyboards produce a curly apostrophe and the phrases above are
// written with a straight one. The same rule the rest of the worker uses.
const flatten = (text) => text.toLowerCase().replace(/[‘’ʼ]/g, "'");

// Somebody joking. "Make me admin🌝" was posted in the group and is exactly
// the kind of message a bot that only ever marks deadlines will scroll past
// while every human in the group smiles at it.
//
// Matched only when the sender has already signalled it themselves, with a
// laughing emoji or with "haha". That is the whole safeguard, and it is a
// strong one: the bot is joining in on something already labelled a joke
// rather than deciding what is funny, which it cannot do and would get
// wrong in front of 390 people.
const LAUGHING = /[\u{1F600}-\u{1F606}\u{1F609}-\u{1F60D}\u{1F639}\u{1F642}\u{1F643}\u{1F923}\u{1F92A}\u{1F31D}\u{1F31C}]/u;

const LAUGHING_WORDS = ['haha', 'hehe', 'lool', 'lol ', 'mdr', 'ptdr', '😹'];

// Except about the bots. "The bot is flooding the group 😅" carries a
// laughing face and is a complaint, and a bot putting a grin on it is the
// single worst thing this feature could do. That complaint has already been
// made in this group, by name.
const NOT_OURS_TO_LAUGH_AT = ['bot', 'spam', 'flood', 'annoying', 'agaçant', 'agacant'];

/** What this message is worth marking as, or null for most of them.
 *
 * Three things, on purpose. Two of them are what the group loses by
 * scrolling: a link somebody will want again, a date somebody has to act
 * on, both findable afterwards by looking for the bot's own mark. The third
 * is a joke somebody has already flagged as one, which is what makes the
 * bot feel present in the group rather than filed in it.
 */
export function worthMarking(text) {
  const clean = (text || '').trim();
  if (!clean) return null;

  const lowered = flatten(clean);

  // Checked before the length rule, because a joke is short by nature and
  // "Make me admin🌝" is sixteen characters.
  if (isAJoke(clean, lowered)) return '😄';

  if (clean.length < MIN_CHARS) return null;
  // A date to act on beats a link: whoever misses it misses more.
  if (A_DEADLINE.some((phrase) => lowered.includes(flatten(phrase)))) return '⏰';
  if (A_LINK.test(clean)) return '📌';
  return null;
}

function isAJoke(clean, lowered) {
  if (NOT_OURS_TO_LAUGH_AT.some((word) => lowered.includes(word))) return false;
  // A long message with a smiley in it is an announcement with a smiley in
  // it, not a joke.
  if (clean.length > 120) return false;
  return LAUGHING.test(clean) || LAUGHING_WORDS.some((w) => lowered.includes(w));
}

/** A bot's message, by the name WhatsApp shows for it.
 *
 * The same rule the API uses to keep other teams' bots out of the history.
 * Marking another bot's announcement would read as ours endorsing it, in
 * front of the group that is judging both.
 */
export function writtenByABot(pushName) {
  const name = (pushName || '').trim().toLowerCase();
  return name.endsWith(' bot') || name.endsWith('-bot') || name.endsWith('_bot');
}
