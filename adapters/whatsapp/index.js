/**
 * UniConnect AI - the WhatsApp worker.
 *
 * Built on Liza's Baileys connection: QR pairing, reconnect, and the silent
 * group listener. What is added here is everything that decides when the bot
 * speaks, and the API calls behind each of those decisions.
 *
 * THE RULE, and it is the whole product:
 *
 *   Silent in the group, talkative in private.
 *
 * In the group the bot writes only when mentioned with @ask, when a question
 * is a duplicate (once per topic, not once per asker), and for the daily
 * digest. In a direct message it always answers. The group has a noise
 * problem; a bot that adds to it has failed even when every answer is right.
 *
 * The API decides none of this. It answers when asked and initiates nothing,
 * so the decision lives here, in one file.
 */

import makeWASocket, {
  DisconnectReason,
  downloadMediaMessage,
  useMultiFileAuthState,
} from '@whiskeysockets/baileys';
import qrcode from 'qrcode-terminal';

import * as api from './api.js';

const GROUP_JID = process.env.GROUP_JID || '';

// Other bots in the group, by JID, comma separated. Their messages are not
// indexed and never trigger a reply.
//
// There is already one in the METI group that answers without being asked.
// Two bots that answer each other run all night and the bill arrives in the
// morning; and a bot's chatter in our history makes it a source we might one
// day cite, which it should never be.
const IGNORED = new Set(
  (process.env.IGNORED_JIDS || '')
    .split(',')
    .map((j) => j.trim())
    .filter(Boolean)
);

// How often to look for people who were named and have not come back. Five
// minutes is often enough to be useful and rare enough to be invisible.
const ALERT_INTERVAL_MS = Number(process.env.ALERT_INTERVAL_MINUTES || 5) * 60_000;

// The hour, in UTC, at which the daily digest goes out. 18:00 UTC is early
// evening across the countries in this group.
const DIGEST_HOUR_UTC = Number(process.env.DIGEST_HOUR_UTC || 18);

// A number that answers in 200 milliseconds, every time, at four in the
// morning, is a number Meta blocks. The pause costs nothing and it is the
// cheapest insurance we have against losing the account outright.
const MIN_DELAY_MS = 1500;
const MAX_DELAY_MS = 3500;

const CATCHUP_PHRASES = [
  'what did i miss', 'catch me up', 'catch up', 'whats new', "what's new",
  'quoi de neuf', "qu'est-ce que j'ai raté", 'quest ce que jai rate',
  'rattrapage', 'resume moi', 'update me',
];

const TIMELINE_PHRASES = [
  'timeline', 'schedule', 'roadmap', 'planning', 'calendrier', 'agenda',
];

// Topics already answered aloud in the group. The duplicate rule is "once per
// topic", not "once per person": the second asker gets the answer, the fifth
// gets silence, because by then it is on the screen just above them.
const answeredAloud = new Map();
const TOPIC_TTL_MS = 6 * 60 * 60 * 1000;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const humanPause = () => sleep(MIN_DELAY_MS + Math.random() * (MAX_DELAY_MS - MIN_DELAY_MS));

/** The text of a message, whatever shape WhatsApp wrapped it in. */
function textOf(msg) {
  const m = msg.message || {};
  return (
    m.conversation ||
    m.extendedTextMessage?.text ||
    m.imageMessage?.caption ||
    m.videoMessage?.caption ||
    ''
  ).trim();
}

/** Who sent it: the participant in a group, the chat itself in a direct message. */
const senderOf = (msg) => msg.key.participant || msg.key.remoteJid || '';

const isGroup = (jid) => (jid || '').endsWith('@g.us');

const matches = (text, phrases) => {
  const lower = text.toLowerCase();
  return phrases.some((p) => lower.includes(p));
};

// Said once to each person, on their first answer ever. Everybody learns that
// a thumb corrects the bot; nobody reads it fifty times. Putting it under
// every answer would add a line of housekeeping to the one place we have
// worked to keep quiet.
const FIRST_TIME_HINT =
  'React 👍 or 👎 to any answer. A 👎 retires it, so it stops being reused ' +
  'when somebody asks the same thing.';

/** Format an answer for a phone: the answer, then where it came from. */
function withSources(result) {
  const source = result.sources?.[0];
  let text = result.answer;

  if (source) {
    const when = new Date(source.said_at).toLocaleDateString('en-GB', {
      day: 'numeric',
      month: 'short',
    });
    text += `\n\n- ${source.author}, ${when}`;
  }

  if (result.meta?.first_answer) text += `\n\n${FIRST_TIME_HINT}`;
  return text;
}

async function connectToWhatsApp() {
  const { state, saveCreds } = await useMultiFileAuthState('auth_info');

  const sock = makeWASocket({ auth: state });
  sock.ev.on('creds.update', saveCreds);

  sock.ev.on('connection.update', (update) => {
    const { connection, lastDisconnect, qr } = update;

    if (qr) {
      console.log('\nScan this QR code with WhatsApp:\n');
      qrcode.generate(qr, { small: true });
    }

    if (connection === 'close') {
      const shouldReconnect =
        lastDisconnect?.error?.output?.statusCode !== DisconnectReason.loggedOut;
      console.log('Connection closed. Reconnecting:', shouldReconnect);
      if (shouldReconnect) connectToWhatsApp();
      else console.error('Logged out. Delete auth_info/ and scan the QR again.');
    } else if (connection === 'open') {
      console.log('WhatsApp bot is online.');
      startBackgroundJobs(sock);
    }
  });

  // A thumb on one of the bot's answers is the only feedback anybody will
  // ever give it. Nobody types "that was wrong"; they react and move on.
  // It also does real work: an answer marked unhelpful stops being reused as
  // a duplicate, so one thumb down retires a bad answer for everybody.
  sock.ev.on('messages.reaction', async (reactions) => {
    for (const r of reactions) {
      try {
        await handleReaction(r);
      } catch (error) {
        console.error('reaction failed:', error.message);
      }
    }
  });

  sock.ev.on('messages.upsert', async ({ messages, type }) => {
    if (type !== 'notify') return;
    for (const msg of messages) {
      try {
        await handle(sock, msg);
      } catch (error) {
        // One bad message must never stop the listener: losing the loop means
        // losing every message after it, silently.
        console.error('handling message failed:', error.message);
      }
    }
  });
}

// Deliberately narrow. A 🤔 or a 😂 on an answer means something, but not
// something we can turn into a rating, and guessing would poison the only
// quality signal we have.
const POSITIVE = new Set(['👍', '❤️', '🙏', '✅', '💯', '🔥']);
const NEGATIVE = new Set(['👎', '❌', '🚫']);

async function handleReaction(event) {
  // Only reactions on messages the bot itself sent.
  if (!event.key?.fromMe) return;

  const emoji = event.reaction?.text || '';
  const helpful = POSITIVE.has(emoji) ? true : NEGATIVE.has(emoji) ? false : null;
  if (helpful === null) return; // removing a reaction sends an empty string

  const user = event.reaction?.key?.participant || event.reaction?.key?.remoteJid;
  if (!user) return;

  await api.feedback(user, GROUP_JID, helpful);
  console.log(`${emoji} from ${user}: rated ${helpful ? 'helpful' : 'unhelpful'}`);
}

async function handle(sock, msg) {
  // Never answer ourselves. Two bots in one group will otherwise talk to each
  // other all night, and the bill arrives in the morning.
  if (msg.key.fromMe) return;

  const chat = msg.key.remoteJid || '';
  const inGroup = isGroup(chat);

  // Only the group we were configured for. The bot may sit in others.
  if (inGroup && GROUP_JID && chat !== GROUP_JID) return;

  const sender = senderOf(msg);
  // Another bot. Not indexed, not answered, not cited.
  if (IGNORED.has(sender)) return;
  const when = Number(msg.messageTimestamp);

  // A voice note: the most invisible thing in the group. Store it and say
  // nothing - reading everything, writing almost nothing.
  if (msg.message?.audioMessage && inGroup) {
    await ingestVoice(msg, sender, when);
    return;
  }

  const text = textOf(msg);
  if (!text) return;

  if (inGroup) {
    await ingestText(msg, text, sender, when);
    await handleGroup(sock, msg, text, sender);
  } else {
    await handlePrivate(sock, msg, text, sender);
  }
}

/** Everything said in the group goes to the API, mentioned or not. */
async function ingestText(msg, text, sender, when) {
  try {
    await api.sendMessages(GROUP_JID, [
      {
        author: sender,
        author_name: msg.pushName || null,
        content: text,
        said_at: when,
        // What lets the bot tell somebody privately that the group is waiting
        // on them. Without it, mention alerts have nothing to work from.
        mentions: msg.message?.extendedTextMessage?.contextInfo?.mentionedJid || [],
      },
    ]);
  } catch (error) {
    console.error('ingest failed:', error.message);
  }
}

async function ingestVoice(msg, sender, when) {
  try {
    const buffer = await downloadMediaMessage(msg, 'buffer', {});
    const result = await api.sendVoice({
      group_id: GROUP_JID,
      author: sender,
      author_name: msg.pushName || null,
      said_at: when,
      mime_type: msg.message.audioMessage.mimetype || 'audio/ogg',
      audio_base64: buffer.toString('base64'),
    });
    console.log(
      result.empty
        ? 'voice note had no intelligible speech, ignored'
        : `voice note transcribed: ${result.transcript.slice(0, 60)}...`
    );
  } catch (error) {
    console.error('voice note failed:', error.message);
  }
}

async function handleGroup(sock, msg, text, sender) {
  if (!text.toLowerCase().startsWith('@ask')) return; // silent, by design

  const question = text.slice(4).trim();
  if (!question) {
    await reply(sock, msg, 'Ask me something after @ask - for example: @ask what is the deadline?');
    return;
  }

  const result = await api.ask(question, sender, GROUP_JID, false);

  // Once per topic. The second person to ask gets the answer; the fifth gets
  // silence, because by then it is on the screen just above them.
  if (result.meta?.duplicate) {
    const topic = result.meta.original_question || question;
    const last = answeredAloud.get(topic);
    if (last && Date.now() - last < TOPIC_TTL_MS) {
      console.log('duplicate already answered aloud, staying quiet');
      return;
    }
    answeredAloud.set(topic, Date.now());
  }

  await reply(sock, msg, withSources(result));
}

async function handlePrivate(sock, msg, text, sender) {
  // In private the bot always answers. This half of the product costs the
  // group nothing, which is exactly why it is allowed to be talkative.
  if (matches(text, CATCHUP_PHRASES)) {
    const result = await api.catchup(sender, GROUP_JID, text);
    const lead = result.first_time
      ? 'I had no record of your last visit, so here are the last two days.\n\n'
      : '';
    await reply(sock, msg, lead + result.summary);
    return;
  }

  if (matches(text, TIMELINE_PHRASES)) {
    const result = await api.timeline(GROUP_JID);
    await reply(
      sock,
      msg,
      result.empty
        ? 'The group has not fixed any dates I can show yet.'
        : '```\n' + result.timeline + '\n```'
    );
    return;
  }

  const result = await api.ask(text, sender, GROUP_JID, true);
  await reply(sock, msg, withSources(result));
}

/** Send, after a pause, quoting what it answers. */
async function reply(sock, msg, text) {
  await humanPause();
  await sock.sendMessage(msg.key.remoteJid, { text }, { quoted: msg });
}

// --------------------------------------------------------------------------
// The two things the bot does without being asked
// --------------------------------------------------------------------------

function startBackgroundJobs(sock) {
  if (startBackgroundJobs.started) return; // survive a reconnect
  startBackgroundJobs.started = true;

  setInterval(() => deliverAlerts(sock).catch((e) => console.error(e.message)), ALERT_INTERVAL_MS);
  setInterval(() => maybePostDigest(sock).catch((e) => console.error(e.message)), 10 * 60_000);
}

/**
 * Tell people privately that the group is waiting on them.
 *
 * The API decides who qualifies: only members who have used the bot before,
 * only after a grace period, only if they have not spoken since, and never
 * the same mention twice. Nothing is posted in the group.
 */
async function deliverAlerts(sock) {
  const { alerts } = await api.pendingAlerts(GROUP_JID);
  if (!alerts.length) return;

  const delivered = [];
  for (const alert of alerts) {
    const jid = alert.to.includes('@') ? alert.to : `${alert.to}@s.whatsapp.net`;
    try {
      await humanPause();
      await sock.sendMessage(jid, {
        text:
          `${alert.from_author} asked you this in the group and it is still open:\n\n` +
          `"${alert.excerpt}"\n\n` +
          'Reply there when you can. You can ask me anything about the group in this chat.',
      });
      delivered.push(alert.id);
    } catch (error) {
      console.error(`alert to ${jid} failed:`, error.message);
    }
  }

  // Only what actually went out. An id marked sent that never arrived is a
  // notification suppressed for good.
  if (delivered.length) await api.alertsSent(delivered);
  console.log(`delivered ${delivered.length} mention alerts`);
}

let lastDigestDay = null;

/** Five lines, once a day, in the group. Checked every ten minutes. */
async function maybePostDigest(sock) {
  const now = new Date();
  const today = now.toISOString().slice(0, 10);

  if (now.getUTCHours() !== DIGEST_HOUR_UTC) return;
  if (lastDigestDay === today) return;
  lastDigestDay = today;

  const result = await api.digest(GROUP_JID, process.env.DIGEST_LANG || 'en');

  // A quiet day is a result, not an error. Announcing silence is noise.
  if (result.quiet || !result.digest) {
    console.log('quiet day, no digest posted');
    return;
  }

  await humanPause();
  await sock.sendMessage(GROUP_JID, {
    text: `Today in the group:\n\n${result.digest}\n\nAsk me anything about it in private.`,
  });
  console.log('digest posted');
}

// --------------------------------------------------------------------------

async function main() {
  if (!GROUP_JID) {
    console.error('GROUP_JID is not set. Put the group JID in .env and restart.');
    process.exit(1);
  }

  // Fail here, loudly, rather than on the first message somebody sends.
  try {
    const status = await api.health();
    console.log(
      `API reachable: ${status.utterances} messages indexed, ` +
        `generation ${status.generation}, embeddings ${status.embeddings}`
    );
    if (!status.worker_auth) {
      console.error('The API has no WORKER_TOKEN configured. Everything but /ask will be refused.');
    }
  } catch (error) {
    console.error('Cannot reach the API:', error.message);
    process.exit(1);
  }

  await connectToWhatsApp();
}

main();
