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

import { existsSync, readFileSync, writeFileSync } from 'node:fs';

import makeWASocket, {
  DisconnectReason,
  downloadMediaMessage,
  useMultiFileAuthState,
} from '@whiskeysockets/baileys';
import qrcode from 'qrcode-terminal';

import * as api from './api.js';

import { claimSession } from './lock.js';

// The WhatsApp session in use, and the one to fall back to.
//
// A spare number, paired in advance and already in the group, sitting idle
// in auth_info_backup. Pairing needs a human typing eight characters on a
// phone and cannot be automated, so the only way a switch can be automatic
// is if the second session already exists before it is needed.
//
// It is used for one thing: WhatsApp rejecting the first session outright.
// Not for a dropped connection, which reconnects on its own, and not for a
// rate limit, which passes. Switching numbers over a passing problem is how
// you lose both.
const AUTH_DIR = process.env.AUTH_DIR || 'auth_info';
const AUTH_DIR_BACKUP = process.env.AUTH_DIR_BACKUP || 'auth_info_backup';
let usingBackup = AUTH_DIR === AUTH_DIR_BACKUP;

const GROUP_JID = process.env.GROUP_JID || '';

// The group's name in the database, which is not its address on WhatsApp.
//
// These were the same value and that was a bug hiding in plain sight. The
// history is loaded by the parser under a name somebody chooses on the
// command line, "meti-cohort-1", while the worker was storing and searching
// under the WhatsApp JID. So every question asked through WhatsApp searched
// a corpus containing only what the bot had seen live, and the 875 messages
// of the export, the hackathon brief and the video guide were reachable from
// the web page alone.
//
// It is invisible because neither side is wrong on its own: both store and
// both retrieve, just in two different groups.
//
// Defaults to the JID so an existing deployment keeps working unchanged.
const GROUP_ID = process.env.GROUP_ID || GROUP_JID;

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

// The hour, in UTC, at which the daily digest goes out.
//
// 07:00 UTC, because the group runs from UTC+0 to UTC+3: nobody gets it
// before 7am their time (Mali, Senegal) and nobody after 10am (Uganda,
// Kenya). Morning beats evening for this: people open WhatsApp, see what they
// missed, and start the day with it.
const DIGEST_HOUR_UTC = Number(process.env.DIGEST_HOUR_UTC || 7);

// Whether the bot is allowed to write in the group at all, uninvited.
//
// The daily digest and the one-off introduction are the only two things it
// says without being asked, and both go to everybody. The group's own
// administrator has asked that bots not be deployed without telling her
// first, and members are asking for fewer bot messages in the main thread
// while they test, so this has to be something a human turns on knowingly
// rather than something that happens at 07:00 because nobody thought about
// it.
//
// Answers to @ask are unaffected: those were invited.
const POSTS_IN_GROUP = process.env.DIGEST_ENABLED !== 'false';

// Post the introduction as soon as the bot connects, instead of waiting for
// the digest hour. For the day the bot joins the group: nobody wants to
// wait until tomorrow morning to show the group what it does.
//
// It runs once. The state file marks the day as done the moment the message
// goes out, so a restart with the flag still set changes nothing, and the
// morning job takes over from tomorrow. Remove the line afterwards anyway.
//
// A flag rather than a separate script, because a second Baileys process
// sharing this session throws the worker off WhatsApp, which has already
// cost us the paired session three times.
const INTRODUCE_NOW = process.env.INTRODUCE_NOW === 'true';

// A message written by a person, posted to the group once, on purpose.
//
// For the announcement that the team is ready to be tested. It is the team
// speaking, not the bot, which is why the text is a file somebody wrote and
// read back rather than anything generated here.
//
// Set both, start the worker, watch for "announcement posted", then remove
// ANNOUNCE_NOW. The marker file makes a restart harmless in the meantime.
const ANNOUNCE_NOW = process.env.ANNOUNCE_NOW === 'true';
const ANNOUNCE_FILE = process.env.ANNOUNCE_FILE || 'announcement.txt';
const ANNOUNCE_STATE = new URL('.announced', import.meta.url).pathname;

/** Which group the announcement has already gone to, if any. */
function announcedTo() {
  try {
    return readFileSync(ANNOUNCE_STATE, 'utf8').trim();
  } catch {
    return null;
  }
}

// Who the bot says it is. The same name avatar.js writes to the WhatsApp
// profile, so the message and the contact card agree.
const BOT_NAME = process.env.BOT_NAME || 'UniConnect-BOT';
const TEAM_NAME = process.env.TEAM_NAME || 'UniConnect';

/** The first thing the group ever reads from the bot.
 *
 * Written here rather than asked of the model: it has to be exact, it
 * costs nothing, and it says the same thing every time. The model writes
 * what follows, which is the group's own history.
 *
 * Bilingual, and not as a courtesy. Half this group works in French, and
 * its own history records them saying they are served less well than the
 * anglophone members. Introducing itself in both languages says more about
 * what this bot is for than any sentence claiming it.
 */
function introduction() {
  return (
    `Hello, I am ${BOT_NAME}, built by team ${TEAM_NAME}.\n\n` +
    'I have read everything said in this group, plus the hackathon brief ' +
    'and the video guide. Two ways to use me:\n\n' +
    `- In the group: write @ask then your question. I answer only when ` +
    'called, never otherwise.\n' +
    '- In private: just write to me, no @ask needed, and nobody else sees ' +
    'it. That is where I am most useful.\n\n' +
    `Bonjour, je suis ${BOT_NAME}, développé par l'équipe ${TEAM_NAME}.\n\n` +
    "J'ai lu tout ce qui s'est dit dans ce groupe, ainsi que le brief du " +
    'hackathon et le guide vidéo. Deux façons de me parler :\n\n' +
    '- Dans le groupe : écris @ask puis ta question. Je ne réponds que si ' +
    'on m’appelle, jamais autrement.\n' +
    '- En privé : écris moi directement, sans @ask, et personne d’autre ne ' +
    'le voit. C’est là que je sers le plus.\n\n' +
    'Voici ce que je sais de ce groupe.\n\n' +
    '- - -'
  );
}

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

// Asking for the whole group rather than for what changed. These go to the
// API untouched, which reads the difference and answers with an overview.
//
// The distinction was missed twice in a row: "fais moi un grand résumé que
// je puisse me situer" matched 'resume moi' here, went to the catch-up, and
// came back "nothing new since your last visit" to somebody who had read
// none of it.
const OVERVIEW_MARKERS = [
  'complet', 'complète', 'entier', 'intégral', 'général', 'generale',
  'globale', 'grand résumé', 'tout ce qui', 'toutes les discussions',
  'tous les discussions', 'depuis le début', 'me situer', 'comprends rien',
  'everything', 'whole', 'full summary', 'from the start', 'big picture',
];

const TIMELINE_PHRASES = [
  'timeline', 'schedule', 'roadmap', 'planning', 'calendrier', 'agenda',
];

// Topics already answered aloud in the group. The duplicate rule is "once per
// topic", not "once per person": the second asker gets the answer, the fifth
// gets silence, because by then it is on the screen just above them.
const answeredAloud = new Map();

// How long the bot stays quiet on a topic it has already answered aloud.
//
// Six hours is right in normal use: the answer is a few messages up and
// repeating it is the noise this bot exists to remove.
//
// It is wrong on a testing day. Three hundred people trying the bot all ask
// the same handful of questions, so from the third person onwards the bot
// says nothing, and "I asked it and it ignored me" is exactly what this
// group said about another bot. Nobody who has just been ignored concludes
// that the bot was being considerate.
//
// TOPIC_QUIET_MINUTES=0 answers everybody, every time. It costs almost
// nothing: a repeated question is recognised as one already asked and comes
// back from the stored answer without calling the model at all. Use it for
// a day when the group is judging, and put it back to 360 afterwards.
const TOPIC_TTL_MS = Number(process.env.TOPIC_QUIET_MINUTES ?? 360) * 60_000;

// Groups we have already said we are ignoring. One line each, not one per
// message: the bot may legitimately sit in other groups and we are not going
// to fill the journal with it.
const warnedAbout = new Set();

// How many group messages we have stored since this process started, and
// how many the handler has been given in total. The difference between the
// two is every message dropped on purpose, and it is the number that was
// missing all week.
let ingested = 0;
let seen = 0;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// Baileys logs its whole protocol conversation at info level. In journalctl
// that buries the lines that matter, and the lines that matter here are the
// ones somebody reads at four in the morning to find out what the bot is
// doing. Warnings and errors still come through.
//
// BAILEYS_LOG=info brings the commentary back when debugging the connection.
const quiet = {
  level: process.env.BAILEYS_LOG || 'warn',
  child: () => quiet,
  trace: () => {},
  debug: () => {},
  info: () => {},
  warn: (...args) => console.error(...args),
  error: (...args) => console.error(...args),
  fatal: (...args) => console.error(...args),
};
const humanPause = () => sleep(MIN_DELAY_MS + Math.random() * (MAX_DELAY_MS - MIN_DELAY_MS));

// A ceiling on everything the bot sends, answers included.
//
// WhatsApp restricted this number for five hours the day it joined a group
// of 390 people. A pause between messages is not enough on its own: fifteen
// people asking at once still produces fifteen outgoing messages in a
// minute from an account four days old, which is what a spam run looks like
// from outside.
//
// Ten a minute. Six was the first value, set the hour of the restriction,
// and it is too tight to demonstrate anything: the fifteenth person would
// wait two and a half minutes, which reads as a broken bot in front of the
// people who vote. What this counts is almost entirely replies to somebody
// who has just written, the safest kind of message there is; writing to
// people who had not written is what caused the restriction, and that is
// fixed elsewhere. Raise it for a busy hour if you must, never remove it.
const MAX_SENDS_PER_MINUTE = Number(process.env.MAX_SENDS_PER_MINUTE || 10);
const sendTimes = [];

// Whether the bot may write to anybody who has not just written to it.
//
// Covers the mention alerts and the satisfaction survey, the only two
// things it says uninvited in private. Both are good features and both are
// indistinguishable, from WhatsApp's side, from a new number messaging
// strangers. Worth switching off while an account is under scrutiny, and
// worth being a switch rather than an edit at midnight.
const PROACTIVE_DM = process.env.PROACTIVE_DM !== 'false';

/** Wait until sending one more message stays under the per-minute ceiling. */
async function underTheCeiling() {
  for (;;) {
    const cutoff = Date.now() - 60_000;
    while (sendTimes.length && sendTimes[0] < cutoff) sendTimes.shift();
    if (sendTimes.length < MAX_SENDS_PER_MINUTE) {
      sendTimes.push(Date.now());
      return;
    }
    const waitFor = sendTimes[0] + 60_000 - Date.now();
    console.log(`holding a message for ${Math.ceil(waitFor / 1000)}s: send ceiling reached`);
    await sleep(Math.max(waitFor, 1000));
  }
}

// Invisible characters WhatsApp puts inside message text: bidirectional
// isolates and embeddings, zero width spaces, the byte order mark.
//
// This is not cosmetic. Typing "@ask" makes WhatsApp treat it as a mention
// and wrap the word in U+2068 and U+2069, so the message that arrives is
// "@\u2068ask\u2069 what is this hackathon about", and startsWith('@ask')
// is false. The bot therefore ignored every @ask ever sent in a group,
// indexed the question as ordinary group content, and said nothing. In a
// private chat there is no trigger to recognise, which is why that half
// worked perfectly and hid the problem for two days.
const INVISIBLE = /[\u200B-\u200F\u202A-\u202E\u2066-\u2069\uFEFF]/g;

/** The text of a message, whatever shape WhatsApp wrapped it in. */
function textOf(msg) {
  const m = msg.message || {};
  return (
    m.conversation ||
    m.extendedTextMessage?.text ||
    m.imageMessage?.caption ||
    m.videoMessage?.caption ||
    ''
  )
    .replace(INVISIBLE, '')
    .trim();
}

/** The message this one is replying to, if any.
 *
 * "@ask translate this" is a reply to something. Without the quoted text
 * the bot has no idea what "this" is, and it answered three people in a row
 * with the same list of French messages picked at random from the history,
 * one of which was a command somebody had typed at another team's bot.
 *
 * WhatsApp sends the quoted message with the reply. We were throwing it
 * away, which made every "translate this", "explain this" and "what does
 * this mean" unanswerable, and those are the most natural things to ask a
 * bot sitting in a busy group.
 */
/** The question, with the message it was a reply to attached.
 *
 * Labelled rather than merged, so the model can tell the person's words
 * from the words they pointed at, and so that a request to translate or
 * explain has something to act on.
 */
function withQuoted(question, quoted) {
  if (!quoted) return question;
  const trimmed =
    quoted.text.length > 1500 ? `${quoted.text.slice(0, 1500)}...` : quoted.text;
  return `${question}\n\n[replying to this message]\n${trimmed}`;
}

function quotedIn(msg) {
  const context = msg.message?.extendedTextMessage?.contextInfo;
  const quoted = context?.quotedMessage;
  if (!quoted) return null;

  const text = (
    quoted.conversation ||
    quoted.extendedTextMessage?.text ||
    quoted.imageMessage?.caption ||
    quoted.videoMessage?.caption ||
    ''
  )
    .replace(INVISIBLE, '')
    .trim();

  return text ? { text, from: context.participant || '' } : null;
}

/** Who sent it: the participant in a group, the chat itself in a direct message. */
const senderOf = (msg) => msg.key.participant || msg.key.remoteJid || '';

const isGroup = (jid) => (jid || '').endsWith('@g.us');

// Phone keyboards produce a curly apostrophe (U+2019), the phrases below are
// written with a straight one, and the two do not match. Without this, every
// French speaker typing "qu'est-ce que j'ai raté" on an iPhone would get an
// ordinary answer instead of their catch-up, and nothing would look broken.
const normalise = (text) => text.toLowerCase().replace(/[\u2018\u2019\u02bc]/g, "'");

const matches = (text, phrases) => {
  const lower = normalise(text);
  return phrases.some((p) => lower.includes(normalise(p)));
};

// Said once to each person, on their first answer ever. Everybody learns that
// a thumb corrects the bot; nobody reads it fifty times. Putting it under
// every answer would add a line of housekeeping to the one place we have
// worked to keep quiet.
const FIRST_TIME_HINT =
  'React 👍 or 👎 to any answer. A 👎 retires it, so it stops being reused ' +
  'when somebody asks the same thing.';

const SOURCES_SHOWN = 3;

/** One source, named the way a reader would name it.
 *
 * A document is named and not dated: "the UniPods Video Demo Guide" is the
 * useful thing to know, and the date it was written tells the reader
 * nothing. A person is named and dated, because in a chat, when something
 * was said is half of what it means.
 */
function credit(source) {
  if (source.kind === 'document') return source.author;
  if (source.kind === 'call') return `${source.author} (call)`;

  const when = new Date(source.said_at).toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'short',
  });
  return `${source.author}, ${when}`;
}

/** Format an answer for a phone: the answer, then where it came from.
 *
 * The [1] markers are stripped. They are meaningful on the web page, which
 * prints a numbered list of every source, and they are noise in WhatsApp,
 * where one attribution line sits under the answer and nothing is numbered.
 */
function withSources(result) {
  // The timeline is drawn in code with aligned columns. WhatsApp only keeps
  // that alignment inside a fenced block, and the citation markers are not
  // stripped from it because there are none to strip.
  if (result.meta?.preformatted) {
    return '```\n' + (result.answer || '') + '\n```';
  }

  let text = (result.answer || '').replace(/\s*\[\d+\]/g, '');

  // Every source the answer used, not just the first.
  //
  // An answer about the demo video, built from the official guide and four
  // messages, went out signed "+229…56, 18 Sept". That names one person for
  // work five sources did, hides the document that made it trustworthy, and
  // puts a stranger's phone number under a claim they did not make.
  //
  // Capped at three: the point is to show what it rests on, not to print a
  // bibliography under every answer on a phone.
  const sources = result.sources || [];
  if (sources.length) {
    const named = [...new Set(sources.slice(0, SOURCES_SHOWN).map(credit))];
    const more = sources.length - SOURCES_SHOWN;
    text += `\n\n- ${named.join(' · ')}`;
    if (more > 0) text += ` and ${more} more`;
  }

  if (result.meta?.first_answer) text += `\n\n${FIRST_TIME_HINT}`;
  return text;
}

/**
 * Logged out: stop, loudly, and never try again on its own.
 *
 * The process used to exit here, and systemd restarts it ten seconds later.
 * Each restart is another login attempt on a session WhatsApp has already
 * rejected, so one logout became dozens of attempts an hour. That is what a
 * compromised account looks like from Meta's side, and the number was
 * restricted for five hours the day it happened.
 *
 * So the process stays alive and does nothing: systemd sees a running
 * service and restarts nothing, and the journal repeats the one line that
 * matters until a person re-pairs. Doing nothing is the right behaviour
 * here, and it has to be a deliberate state rather than a crash.
 */
/**
 * Rejected by WhatsApp: use the spare number if there is one.
 *
 * Only on an outright logout. A dropped connection reconnects on its own
 * and a rate limit passes; switching numbers over either is how you lose
 * both of them.
 *
 * The spare is paired ahead of time into auth_info_backup and is already a
 * member of the group, because pairing needs a human typing eight
 * characters on a phone and there is no version of that which happens by
 * itself at the moment it is needed.
 */
function switchToTheSpareNumber() {
  if (usingBackup || !existsSync(new URL(AUTH_DIR_BACKUP, import.meta.url).pathname)) {
    stayDownUntilSomebodyRepairs();
    return;
  }

  usingBackup = true;
  console.error(
    `LOGGED OUT of the main number. Switching to the spare session in ` +
      `${AUTH_DIR_BACKUP}. Tell somebody: the first number needs re-pairing ` +
      'and there is no second spare.'
  );
  // A moment before reconnecting. Two sessions changing over inside a
  // second, from one machine, is itself a thing worth not doing.
  setTimeout(() => connectToWhatsApp(AUTH_DIR_BACKUP), 5000);
}

function stayDownUntilSomebodyRepairs() {
  const say = () =>
    console.error(
      'LOGGED OUT of WhatsApp. Not retrying: every retry is another login ' +
        'attempt on a rejected session, which is how a number gets blocked. ' +
        'Re-pair by hand: stop the service, remove auth_info, run npm run groups.'
    );

  say();
  // Every ten minutes: visible to whoever reads the journal tomorrow,
  // without filling the disk tonight.
  setInterval(say, 10 * 60_000);
}

async function connectToWhatsApp(authDir = AUTH_DIR) {
  claimSession(`the worker (${authDir})`);
  const { state, saveCreds } = await useMultiFileAuthState(authDir);

  const sock = makeWASocket({ auth: state, logger: quiet });
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
      if (shouldReconnect) connectToWhatsApp(authDir);
      else switchToTheSpareNumber();
    } else if (connection === 'open') {
      console.log('WhatsApp bot is online.');
      checkGroupJid(sock).catch((e) => console.error('group check failed:', e.message));
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

  // A reaction carries the id of the message it sits on and nothing else,
  // so ask first whether that message was the satisfaction survey. Getting
  // this wrong would retire whatever answer the person last received, on
  // the strength of a thumb they meant for the bot as a whole.
  const reacted = event.key?.id;
  if (reacted) {
    const { survey } = await api.surveyRating(reacted, helpful);
    if (survey) {
      console.log(`${emoji} from ${user}: rated the bot ${helpful ? 'up' : 'down'}`);
      return;
    }
  }

  await api.feedback(user, GROUP_ID, helpful);
  console.log(`${emoji} from ${user}: rated ${helpful ? 'helpful' : 'unhelpful'}`);
}

async function handle(sock, msg) {
  // Logged before any decision about the message.
  //
  // Without this, "nothing arrived" and "something arrived and was dropped"
  // are indistinguishable from the journal, and every drop below is silent
  // by design: our own messages, other bots, other groups, messages with no
  // text. Three separate faults this week were each diagnosed twice over
  // for want of that distinction, and one of them wrongly.
  //
  // No content and no author: this is 390 people's conversation and the
  // journal is readable by anybody with a shell on the machine.
  seen += 1;
  console.log(
    `message ${seen} (${isGroup(msg.key.remoteJid || '') ? 'group' : 'private'}` +
      `${msg.key.fromMe ? ', ours' : ''}, ${ingested} kept)`
  );
  // Never answer ourselves. Two bots in one group will otherwise talk to each
  // other all night, and the bill arrives in the morning.
  if (msg.key.fromMe) return;

  const chat = msg.key.remoteJid || '';
  const inGroup = isGroup(chat);

  // Only the group we were configured for. The bot may sit in others.
  if (inGroup && GROUP_JID && chat !== GROUP_JID) {
    // Said once per group, then never again. A wrong GROUP_JID drops every
    // message the group writes and looks exactly like a quiet group: the bot
    // still answers private messages, nothing fails, nothing is logged, and
    // the history silently stops growing. That cost us most of a day.
    if (!warnedAbout.has(chat)) {
      warnedAbout.add(chat);
      console.warn(
        `ignoring messages from ${chat}: GROUP_JID is ${GROUP_JID}. ` +
          'If that is the group we are meant to read, fix GROUP_JID in .env.'
      );
    }
    return;
  }

  const sender = senderOf(msg);
  // Another bot. Not indexed, not answered, not cited.
  if (IGNORED.has(sender)) {
    // Said once per sender. An over-broad IGNORED_JIDS silences real people
    // and looks exactly like the bot being broken.
    if (!warnedAbout.has(sender)) {
      warnedAbout.add(sender);
      console.warn(`ignoring ${sender}: it is in IGNORED_JIDS`);
    }
    return;
  }
  const when = Number(msg.messageTimestamp);

  // A voice note: the most invisible thing in the group. Store it and say
  // nothing - reading everything, writing almost nothing.
  if (msg.message?.audioMessage && inGroup) {
    await ingestVoice(sock, msg, sender, when);
    return;
  }

  const text = textOf(msg);
  if (!text) return;

  if (inGroup) {
    // A message addressed to the bot is a command, not something the group
    // said. Indexing it made the bot quote questions back as answers:
    // "According to Steven: @ask bonjour". It also let one person's question
    // become the source for the next person's.
    if (!text.toLowerCase().startsWith('@ask')) {
      await ingestText(msg, text, sender, when);
    }
    await handleGroup(sock, msg, text, sender);
  } else {
    await handlePrivate(sock, msg, text, sender);
  }
}

/** Everything said in the group goes to the API, mentioned or not. */
async function ingestText(msg, text, sender, when) {
  try {
    await api.sendMessages(GROUP_ID, [
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
    // Counted, not quoted. A working ingestion used to be completely silent,
    // which made "the group is quiet" and "we are dropping everything the
    // group says" look identical from the journal. The text itself stays out
    // of it: this is 153 people's private conversation and the journal is
    // readable by anybody with a shell on the box.
    ingested += 1;
  } catch (error) {
    console.error('ingest failed:', error.message);
  }
}

async function ingestVoice(sock, msg, sender, when) {
  try {
    // reuploadRequest matters: WhatsApp drops media from its CDN after a
    // while, and without this the download fails for anything not brand new.
    // A voice note the bot sees a minute late is exactly the normal case.
    const buffer = await downloadMediaMessage(msg, 'buffer', {}, {
      reuploadRequest: sock.updateMediaMessage,
    });
    const result = await api.sendVoice({
      group_id: GROUP_ID,
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

/**
 * Show "typing..." while the answer is being written.
 *
 * A whole-group overview takes the model the best part of a minute, and a
 * bot that says nothing for that long has failed in the reader's mind before
 * it answers: people ask again, or give up and decide it is broken. WhatsApp
 * has the one signal everybody already understands, so use it.
 *
 * The indicator expires on its own after a few seconds, which is why it is
 * refreshed on a timer rather than sent once. Cleared in a finally, so a
 * failed request does not leave the bot apparently typing forever.
 */
// Said when the API could not be reached or gave up. Short, honest, and not
// an apology: the person is waiting for an answer, not for contrition.
const BROKE = {
  en:
    'Something went wrong on my side and I could not finish that one. Try ' +
    'again in a moment, or ask it more narrowly.',
  fr:
    "Quelque chose a échoué de mon côté et je n'ai pas pu terminer. Réessaie " +
    'dans un instant, ou pose la question plus précisément.',
};

// Rough, and it only picks which of two sentences to send. The real language
// detection lives in the API, which cannot help here because the API is the
// thing that just failed.
const looksFrench = (text) =>
  /[àâçéèêëîïôùû]|\b(le|la|les|des|une|est|pour|quoi|qui|pourrais|donne)\b/i.test(text);

/** Run something, and say so if it fails instead of going quiet.
 *
 * A request that throws used to end the handler silently. The person had
 * watched "typing..." for half a minute and then got nothing, which reads as
 * a bot that ignored them: worse than an error, because they do not know
 * whether to ask again.
 */
async function answerOrExplain(sock, msg, text, work) {
  try {
    return await work();
  } catch (error) {
    console.error('answering failed:', error.message);
    await reply(sock, msg, BROKE[looksFrench(text) ? 'fr' : 'en']);
    return null;
  }
}

async function whileThinking(sock, jid, work) {
  const show = () => sock.sendPresenceUpdate('composing', jid).catch(() => {});
  await show();
  const keepAlive = setInterval(show, 8000);
  try {
    return await work();
  } finally {
    clearInterval(keepAlive);
    await sock.sendPresenceUpdate('paused', jid).catch(() => {});
  }
}

async function handleGroup(sock, msg, text, sender) {
  if (!text.toLowerCase().startsWith('@ask')) {
    // Silent, by design. But say so when the message looks like somebody
    // was trying to call the bot and the trigger did not fire, with the
    // exact bytes of the opening.
    //
    // This is what two days of "@ask does nothing" needed and did not have.
    // WhatsApp wraps a mention in invisible directional isolates, so the
    // text was "@\u2068ask\u2069 ..." and nothing matched; from the outside
    // that is indistinguishable from a bot that is switched off, from one
    // in the wrong group, and from one whose API is down.
    if (/ask/i.test(text.slice(0, 12))) {
      const bytes = [...text.slice(0, 8)]
        .map((c) => c.codePointAt(0).toString(16))
        .join(' ');
      console.warn(`group message looks like a call but did not trigger: [${bytes}]`);
    }
    return;
  }

  console.log('@ask in the group, answering');

  // Heard you. A reaction costs no message in a group that has asked for
  // fewer of them, and it arrives before the answer, which can take the
  // better part of a minute on a whole-group summary.
  await react(sock, msg, '👀');

  if (await maybeThank(sock, msg, text.slice(4))) return;

  const question = withQuoted(text.slice(4).trim(), quotedIn(msg));
  if (!question) {
    await reply(sock, msg, 'Ask me something after @ask - for example: @ask what is the deadline?');
    return;
  }

  const result = await answerOrExplain(sock, msg, question, () =>
    whileThinking(sock, msg.key.remoteJid, () =>
      api.ask(question, sender, GROUP_ID, false)
    )
  );
  if (!result) return;

  // Once per topic. The second person to ask gets the answer; the fifth gets
  // silence, because by then it is on the screen just above them.
  if (result.meta?.duplicate) {
    const topic = result.meta.original_question || question;
    const last = answeredAloud.get(topic);
    if (TOPIC_TTL_MS > 0 && last && Date.now() - last < TOPIC_TTL_MS) {
      console.log('duplicate already answered aloud, staying quiet');
      return;
    }
    answeredAloud.set(topic, Date.now());
  }

  await reply(sock, msg, withSources(result));
  if (result.meta?.send_document) {
    await sendDocument(sock, msg, result.meta.send_document);
  }
}

async function handlePrivate(sock, msg, text, sender) {
  // In private the bot always answers. This half of the product costs the
  // group nothing, which is exactly why it is allowed to be talkative.
  if (await maybeThank(sock, msg, text)) return;
  if (matches(text, CATCHUP_PHRASES) && !matches(text, OVERVIEW_MARKERS)) {
    const result = await answerOrExplain(sock, msg, text, () =>
      whileThinking(sock, msg.key.remoteJid, () =>
        api.catchup(sender, GROUP_ID, text)
      )
    );
    if (!result) return;
    const lead = result.first_time
      ? 'I had no record of your last visit, so here are the last two days.\n\n'
      : '';
    await reply(sock, msg, lead + result.summary);
    return;
  }

  if (matches(text, TIMELINE_PHRASES)) {
    const result = await answerOrExplain(sock, msg, text, () =>
      whileThinking(sock, msg.key.remoteJid, () => api.timeline(GROUP_ID))
    );
    if (!result) return;
    await reply(
      sock,
      msg,
      result.empty
        ? 'The group has not fixed any dates I can show yet.'
        : '```\n' + result.timeline + '\n```'
    );
    return;
  }

  const asked = withQuoted(text, quotedIn(msg));
  const result = await answerOrExplain(sock, msg, asked, () =>
    whileThinking(sock, msg.key.remoteJid, () =>
      api.ask(asked, sender, GROUP_ID, true)
    )
  );
  if (!result) return;
  await reply(sock, msg, withSources(result));
  if (result.meta?.send_document) {
    await sendDocument(sock, msg, result.meta.send_document);
  }
}

// Somebody thanking the bot, in either language.
//
// Worth catching because the right reply to "merci" is not a message. In a
// group that has asked for less bot noise, an answer to a thank-you is one
// more message nobody needed; a reaction says the same thing and adds
// nothing to the thread.
const THANKS = [
  'merci', 'thanks', 'thank you', 'thx', 'shukran', 'asante', 'nice one',
  'well done', 'good bot', 'bravo', 'super', 'parfait', 'perfect',
  'genial', 'génial', 'excellent', 'top', 'nickel', 'great',
];

/** React to a message, the way a person long-presses and picks an emoji.
 *
 * Never fails loudly: a reaction is a courtesy, and a courtesy that takes
 * the bot down is not one.
 */
async function react(sock, msg, emoji) {
  try {
    await sock.sendMessage(msg.key.remoteJid, {
      react: { text: emoji, key: msg.key },
    });
  } catch (error) {
    console.error('reaction failed:', error.message);
  }
}

/** Thanks, answered with a reaction instead of a message.
 *
 * Returns true when it handled the message, so the caller says nothing
 * more. Only for a message that is ONLY thanks: "thanks, and what is the
 * deadline" is a question with a polite opening and deserves an answer.
 */
async function maybeThank(sock, msg, text) {
  const words = normalise(text).replace(/[^\p{L}\s]/gu, ' ').split(/\s+/).filter(Boolean);
  if (!words.length || words.length > 4) return false;
  if (!THANKS.some((t) => normalise(text).includes(t))) return false;

  await react(sock, msg, '🙏');
  console.log('thanked, reacted rather than replied');
  return true;
}

/** Send a document as a file, after the answer that announced it.
 *
 * The file itself rather than a link: somebody who asks for the hackathon
 * guidelines in French wants the document, and on a phone with a poor
 * connection a link is one more thing to tap and wait for.
 *
 * A failure here is said out loud. The person has just been told the file
 * is coming, and silence after that is worse than never having offered.
 */
async function sendDocument(sock, msg, wanted) {
  try {
    const bytes = await api.documentPdf(wanted.source_id, wanted.lang);
    const fileName = `${wanted.title.replace(/[^\w -]+/g, '')}-${wanted.lang}.pdf`;

    await underTheCeiling();
    await sock.sendMessage(
      msg.key.remoteJid,
      { document: bytes, mimetype: 'application/pdf', fileName },
      { quoted: msg }
    );
    console.log(`sent ${fileName} (${Math.round(bytes.length / 1024)} kB)`);
  } catch (error) {
    console.error('document failed:', error.message);
    await reply(
      sock,
      msg,
      wanted.lang === 'fr'
        ? "Je n'ai pas réussi à préparer le document. Réessaie dans un moment."
        : 'I could not prepare that document. Try again in a moment.'
    );
  }
}

/** Send, after a pause, quoting what it answers. */
async function reply(sock, msg, text) {
  await underTheCeiling();
  await humanPause();
  await sock.sendMessage(msg.key.remoteJid, { text }, { quoted: msg });
}

// --------------------------------------------------------------------------
// The two things the bot does without being asked
// --------------------------------------------------------------------------

/**
 * Say at startup whether GROUP_JID is a group we are actually in.
 *
 * A wrong GROUP_JID is invisible in every other way. The bot connects, it
 * answers private messages perfectly, nothing errors, and every message the
 * group writes is discarded at the top of the handler. The only symptom is a
 * history that stops growing, which looks exactly like a quiet group.
 *
 * Diagnosing it used to need somebody to post a message and watch the log.
 * This asks WhatsApp directly, on the socket we already have, so it needs no
 * traffic and starts no second session.
 */
async function checkGroupJid(sock) {
  const groups = Object.values(await sock.groupFetchAllParticipating());

  if (!GROUP_JID) {
    console.warn('GROUP_JID is not set. Groups this number is in:');
    groups.forEach((g) => console.warn(`  ${g.id}  ${g.subject}`));
    return;
  }

  const match = groups.find((g) => g.id === GROUP_JID);
  if (match) {
    // The name it is filed under is printed too. It has to equal the
    // --group-id the parser was given, and there is no way to check that
    // from here: both values are valid on their own and a mismatch simply
    // means the questions and the history are in two different groups.
    console.log(
      `reading group "${match.subject}" as ${GROUP_ID}, ` +
        `${POSTS_IN_GROUP ? 'will post the morning digest' : 'silent in the group'}, ` +
        `${TOPIC_TTL_MS > 0 ? `quiet ${TOPIC_TTL_MS / 60000}min per topic` : 'answers every repeat'}`
    );
    return;
  }

  console.error(
    `GROUP_JID ${GROUP_JID} is not a group this number belongs to. ` +
      'Everything the group says is being discarded. Set one of these in .env:'
  );
  groups.forEach((g) => console.error(`  ${g.id}  ${g.subject}`));
}

/**
 * Post the team's announcement to the group, once.
 *
 * Read from a file rather than generated: this is the team saying it is
 * ready, and a bot that writes its own introduction to a group which has
 * complained about bot noise is the wrong voice for it.
 *
 * Marked done only once it has gone out, like the digest. Marking first
 * loses the message on any failure, which is the bug that suppressed a
 * whole morning's digest.
 */
async function maybeAnnounce(sock) {
  if (!ANNOUNCE_NOW || !GROUP_JID) return;

  // The marker records which group it was sent to. Rehearsing in the test
  // group would otherwise mark the job done, and the real announcement
  // would never go out: no error, no explanation, exactly the way the
  // group introduction was suppressed on launch day.
  if (announcedTo() === GROUP_JID) return;

  let text;
  try {
    text = readFileSync(new URL(ANNOUNCE_FILE, import.meta.url).pathname, 'utf8').trim();
  } catch (error) {
    console.error(`ANNOUNCE_NOW is set but ${ANNOUNCE_FILE} could not be read:`, error.message);
    return;
  }
  if (!text) {
    console.error(`${ANNOUNCE_FILE} is empty, nothing to announce`);
    return;
  }

  await underTheCeiling();
  await humanPause();
  await sock.sendMessage(GROUP_JID, { text });
  writeFileSync(ANNOUNCE_STATE, GROUP_JID);
  console.log('announcement posted');
}

function startBackgroundJobs(sock) {
  if (startBackgroundJobs.started) return; // survive a reconnect
  startBackgroundJobs.started = true;

  setInterval(() => deliverAlerts(sock).catch((e) => console.error(e.message)), ALERT_INTERVAL_MS);
  // Same timer, and the same rule: private, rare, and never twice to
  // the same person.
  setInterval(
    () => askHowItIsGoing(sock).catch((e) => console.error(e.message)),
    ALERT_INTERVAL_MS
  );
  setInterval(() => maybePostDigest(sock).catch((e) => console.error(e.message)), 10 * 60_000);
  // Once at startup as well. Without it, INTRODUCE_NOW still waits for the
  // first tick of the timer, which is ten minutes of wondering whether the
  // flag worked.
  maybePostDigest(sock).catch((e) => console.error(e.message));
  maybeAnnounce(sock).catch((e) => console.error('announcement failed:', e.message));
}

const SURVEY = {
  en:
    'You have asked me a few things now, so I would like to know what you ' +
    'think.\n\nReact to this message:\n\n👍  useful, keep it\n👎  not useful\n\n' +
    'That is the whole survey. Nothing else, and I will not ask again.',
  fr:
    "Tu m'as posé quelques questions, alors j'aimerais savoir ce que tu en " +
    'penses.\n\nRéagis à ce message :\n\n👍  utile, on garde\n👎  pas utile\n\n' +
    "C'est tout. Rien d'autre, et je ne te le redemanderai pas.",
};

/**
 * Ask a few members what they think of the bot, once each.
 *
 * The API decides who qualifies: five questions asked and never surveyed.
 * Sent privately, never in the group, for the same reason as everything
 * else the bot does uninvited.
 *
 * Marked as asked only once the message has gone out. Marking first would
 * lose the survey for good on any failure, which is the bug the daily digest
 * had and which suppressed a whole morning's digest.
 */
async function askHowItIsGoing(sock) {
  if (!PROACTIVE_DM) return;
  const { due } = await api.surveyDue(GROUP_ID);
  if (!due.length) return;

  for (const person of due) {
    const jid = person.asked_by.includes('@')
      ? person.asked_by
      : `${person.asked_by}@s.whatsapp.net`;
    try {
      await underTheCeiling();
      await humanPause();
      // In the language they ask their questions in. The API works it out
      // from the five questions they have already asked, which is a far
      // better sample than any single message.
      const sent = await sock.sendMessage(jid, {
        text: SURVEY[person.lang === 'fr' ? 'fr' : 'en'],
      });
      await api.surveySent(GROUP_ID, person.asked_by, sent?.key?.id || null);
      console.log(`asked ${jid} what they think (${person.questions} questions)`);
    } catch (error) {
      console.error(`survey to ${jid} failed:`, error.message);
    }
  }
}

/**
 * Tell people privately that the group is waiting on them.
 *
 * The API decides who qualifies: only members who have used the bot before,
 * only after a grace period, only if they have not spoken since, and never
 * the same mention twice. Nothing is posted in the group.
 */
async function deliverAlerts(sock) {
  if (!PROACTIVE_DM) return;
  const { alerts } = await api.pendingAlerts(GROUP_ID);
  if (!alerts.length) return;

  const delivered = [];
  for (const alert of alerts) {
    const jid = alert.to.includes('@') ? alert.to : `${alert.to}@s.whatsapp.net`;
    try {
      await underTheCeiling();
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

// The day the digest last went out, kept on disk rather than in memory.
//
// In memory it was a real bug: a restart anywhere inside the digest hour
// reset it to null and the group got the digest twice. A duplicate post is
// exactly the noise this whole product exists to avoid, and restarts during
// that hour are not rare, systemd restarts this worker on any failure.
const DIGEST_STATE = new URL('.digest-state', import.meta.url).pathname;

/**
 * What the morning job has already done.
 *
 * Two facts, in one small file: the last day a digest went out, and whether
 * the group has ever been introduced to the bot. The introduction is the
 * whole history explained, posted once and never again; every morning after
 * that is the ordinary five lines.
 *
 * The first thing 153 people ever see from this bot should tell them what it
 * knows. Posting the full history every morning instead would repeat itself
 * daily and be muted by the end of the week.
 */
function digestState() {
  try {
    const raw = readFileSync(DIGEST_STATE, 'utf8').trim();
    // The file used to hold a bare date. Read that as "already introduced":
    // a group the bot has been posting to for days does not need an
    // introduction, and sending one would look like a malfunction.
    const state = raw.startsWith('{') ? JSON.parse(raw) : { day: raw, met: [] };

    // Every group already introduced to, not just the last one.
    //
    // This held a single group, and that was wrong twice over. Held
    // globally, moving from the test group to the real one carried the
    // introduction across and the 390 new members were never greeted.
    // Held as one group, a rehearsal in the test group and back made the
    // real group look new again, and the whole forty-line introduction
    // went out to it a third time.
    //
    // A set has neither failure. The day still belongs to the group it was
    // counted for, because a digest is about one group's last 24 hours.
    const met = Array.isArray(state.met)
      ? state.met
      : state.introduced
        ? [state.group].filter(Boolean)
        : [];

    return {
      met,
      introduced: met.includes(GROUP_JID),
      day: state.group === GROUP_JID || !state.group ? state.day : null,
    };
  } catch {
    return { met: [], introduced: false, day: null }; // never posted
  }
}

function saveDigestState(state) {
  writeFileSync(DIGEST_STATE, JSON.stringify(state));
}

/** Mark this group done for today, and remembered as introduced. */
function markDone(state, today) {
  const met = state.met.includes(GROUP_JID) ? state.met : [...state.met, GROUP_JID];
  saveDigestState({ group: GROUP_JID, day: today, met });
}

/** Five lines, once a day, in the group. Checked every ten minutes. */
async function maybePostDigest(sock) {
  const now = new Date();
  const today = now.toISOString().slice(0, 10);
  const state = digestState();

  if (!POSTS_IN_GROUP) return;
  // The hour, unless we were told to introduce the bot straight away and it
  // has not been introduced yet.
  if (now.getUTCHours() !== DIGEST_HOUR_UTC && !(INTRODUCE_NOW && !state.introduced)) {
    return;
  }
  if (state.day === today) return;

  // The first morning: what this group is, from all of its history. After
  // that, only what changed since yesterday.
  if (!state.introduced) {
    const whole = await api.overview(GROUP_ID, process.env.DIGEST_LANG || null);
    if (whole.overview) {
      await underTheCeiling();
      await humanPause();
      await sock.sendMessage(GROUP_JID, {
        text:
          `${introduction()}\n\n${whole.overview}\n\n- - -\n\n` +
          'From tomorrow I will post five lines each morning on what ' +
          'changed, and nothing else. Demain matin je posterai cinq lignes ' +
          'sur ce qui a changé, et rien de plus.',
      });
      markDone(state, today);
      console.log('introduction posted');
      return;
    }
    // No overview, no introduction, and the day stays unmarked so the next
    // check tries again. Falling through to the digest would skip the
    // introduction for good.
    console.log('overview unavailable, will introduce tomorrow');
    return;
  }

  const result = await api.digest(GROUP_ID, process.env.DIGEST_LANG || 'en');

  // A quiet day is a result, not an error. Announcing silence is noise, and
  // the day counts as done: there is nothing to retry.
  if (result.quiet || !result.digest) {
    markDone(state, today);
    console.log('quiet day, no digest posted');
    return;
  }

  await underTheCeiling();
  await humanPause();
  await sock.sendMessage(GROUP_JID, {
    text:
      `Here is what happened since yesterday:\n\n${result.digest}\n\n` +
      'Ask me anything about it in private.',
  });

  // Marked done only once it has actually gone out.
  //
  // It used to be marked first, to make a double post impossible. That traded
  // a narrow risk for a certain one: the first attempt of the day failed
  // because the model was unreachable, the day was already marked done, and
  // no digest was ever posted. Anything thrown above leaves the day unmarked,
  // so the next check ten minutes later tries again, for as long as the
  // digest hour lasts.
  markDone(state, today);
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
    // Name the address. "fetch failed" on its own sends people looking at
    // WhatsApp, the token, the group id, anywhere but the one container that
    // is not running.
    const url = process.env.API_URL || 'http://127.0.0.1:8000';
    console.error(`Cannot reach the API at ${url}: ${error.message}`);
    console.error('  Is it up?   docker compose ps');
    console.error('  Start it:   docker compose up -d api');
    console.error('  Check it:   curl -s ' + url + '/health');
    process.exit(1);
  }

  await connectToWhatsApp();
}

main();
