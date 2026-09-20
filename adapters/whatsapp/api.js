/**
 * Everything this worker says to the UniConnect API.
 *
 * Kept apart from the WhatsApp side on purpose: index.js decides *whether*
 * the bot speaks, this file only knows *how* to ask. The rule that keeps the
 * group quiet lives in one place and it is not here.
 *
 * Two things every call needs. The worker token, because most of this API
 * reads or writes a private group's messages and is refused without it. And a
 * timeout, because a call that never returns takes the whole bot down with it
 * - Node will wait forever by default.
 */

const BASE = process.env.API_URL || 'http://127.0.0.1:8000';
const TOKEN = process.env.WORKER_TOKEN || '';

// Generation can genuinely take twenty seconds on a hard question. Ingestion
// and polling should never take that long, so they get a shorter leash and a
// stuck call is noticed rather than silently absorbed.
const SLOW_MS = 30000;
const FAST_MS = 10000;

// Reading the group's whole history is in another category. Nine hundred
// messages, and the model thinking about all of them before it writes.
//
// /ask inherits this because a request for the whole-group overview arrives
// as an ordinary question and the worker cannot know which it is until the
// answer comes back. At thirty seconds it aborted, the model finished and
// billed the tokens anyway, and the person who had watched "typing..." for
// half a minute got nothing at all. A long ceiling costs nothing when the
// answer is quick.
const VERY_SLOW_MS = 180000;

async function call(method, path, { body, timeout = FAST_MS } = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);

  try {
    const response = await fetch(`${BASE}${path}`, {
      method,
      signal: controller.signal,
      headers: {
        'content-type': 'application/json',
        // Not sent on /ask, which is public, but harmless there.
        'x-uniconnect-token': TOKEN,
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });

    if (!response.ok) {
      const detail = await response.text().catch(() => '');
      const error = new Error(`${method} ${path} → ${response.status} ${detail.slice(0, 200)}`);
      error.status = response.status;
      throw error;
    }
    return await response.json();
  } finally {
    clearTimeout(timer);
  }
}

/** Is the API up, and does it have what it needs? */
export const health = () => call('GET', '/health');

/** Answer a question. `privateChat` keeps it out of what the group is told. */
export const ask = (question, user, groupId, privateChat) =>
  call('POST', '/ask', {
    body: { question, user, group_id: groupId, private: privateChat },
    timeout: VERY_SLOW_MS,
  });

/** What one person missed. Moves their bookmark, so never call it to preview. */
export const catchup = (user, groupId, question) =>
  call('POST', '/catchup', { body: { user, group_id: groupId, question }, timeout: SLOW_MS });

/**
 * Every message seen, mentioned or not. This is what keeps the bot current:
 * without it the history stops at the last chat export.
 */
export const sendMessages = (groupId, messages) =>
  call('POST', '/messages', { body: { group_id: groupId, messages } });

/** A voice note. Transcription takes a few seconds, hence the longer timeout. */
export const sendVoice = (note) => call('POST', '/voice', { body: note, timeout: SLOW_MS });

/** Who has been named in the group and has not come back to it. */
export const pendingAlerts = (groupId) => call('GET', `/alerts/${encodeURIComponent(groupId)}`);

/** Confirm delivery, so nobody is told the same thing twice. */
export const alertsSent = (ids) => call('POST', '/alerts/sent', { body: { ids } });

/** Five lines on the last 24 hours. */
export const digest = (groupId, lang) =>
  call('GET', `/digest/${encodeURIComponent(groupId)}${lang ? `?lang=${lang}` : ''}`, {
    timeout: SLOW_MS,
  });

/** The group's schedule, as monospace text. */
export const timeline = (groupId) =>
  call('GET', `/timeline/${encodeURIComponent(groupId)}`, { timeout: SLOW_MS });

/** Rate the last answer a person received. */
export const feedback = (user, groupId, helpful) =>
  call('POST', '/feedback', { body: { user, group_id: groupId, helpful } });

export const surveyDue = (groupId) =>
  call('GET', `/survey/${encodeURIComponent(groupId)}`);

export const surveySent = (groupId, user, messageId) =>
  call('POST', '/survey/sent', {
    body: { group_id: groupId, user, message_id: messageId },
  });

// Returns {survey: true} when the reacted message was a survey, so the
// caller knows not to rate it as an ordinary answer as well.
export const surveyRating = (messageId, helpful) =>
  call('POST', '/survey/rating', { body: { message_id: messageId, helpful } });

/** What the group is, from all of its history. Slow: it reads everything. */
export const overview = (groupId, lang) =>
  call('GET', `/overview/${encodeURIComponent(groupId)}${lang ? `?lang=${lang}` : ''}`, {
    timeout: VERY_SLOW_MS,
  });
