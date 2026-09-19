/**
 * Pair the bot's number, then print the JID of every group it is in.
 *
 *   npm run groups                  QR code
 *   PAIR_NUMBER=22370001234 npm run groups    eight character code instead
 *
 * You need GROUP_JID to configure the worker and there is no way to read it
 * off a phone screen. Run this once after pairing, copy the line for the METI
 * group into .env, and never think about it again.
 *
 * Two ways to pair, because the first one fails often over SSH:
 *
 *   QR code. Works when the terminal renders half-block characters at a
 *   readable size on a dark background. A small window, a light theme or a
 *   scrolled-past expired code all make it silently unscannable, and nothing
 *   tells you which of those it was.
 *
 *   Pairing code. Set PAIR_NUMBER to the bot's number, digits only, country
 *   code included, no plus sign. WhatsApp prints eight characters here and
 *   you type them on the phone under Linked devices, Link with phone number.
 *   Nothing has to render correctly for that to work.
 */

import { existsSync, readFileSync, rmSync } from 'node:fs';

import makeWASocket, { useMultiFileAuthState } from '@whiskeysockets/baileys';
import qrcode from 'qrcode-terminal';

const PAIR_NUMBER = (process.env.PAIR_NUMBER || '').replace(/\D/g, '');

// The number written in the documentation as an example. Somebody ran it
// verbatim, WhatsApp issued a code for an account that does not exist, and
// the phone answered "impossible de se connecter" with nothing to say why.
// An example that looks like a real number will be pasted as one.
const PLACEHOLDER = '22370001234';

if (PAIR_NUMBER === PLACEHOLDER) {
  console.error('\n  PAIR_NUMBER is still the example from the documentation.');
  console.error('  Use the bot phone\'s own number: digits only, country code');
  console.error('  included, no plus sign and no spaces.\n');
  console.error('    +223 70 00 12 34   becomes   22370001234\n');
  process.exit(1);
}

if (PAIR_NUMBER && (PAIR_NUMBER.length < 8 || PAIR_NUMBER.length > 15)) {
  console.error(`\n  PAIR_NUMBER has ${PAIR_NUMBER.length} digits, which is not a`);
  console.error('  phone number with a country code. Expected between 8 and 15.\n');
  process.exit(1);
}

const AUTH_DIR = 'auth_info';

/** Is there a finished, usable session on disk? */
function hasRealSession() {
  try {
    const creds = JSON.parse(readFileSync(`${AUTH_DIR}/creds.json`, 'utf8'));
    return Boolean(creds.registered);
  } catch {
    return false;
  }
}

// A failed pairing attempt leaves credentials behind that are worse than
// nothing: the next run finds them, tries to log in as whatever number was
// given last time, is rejected, and the socket is dead before the new pairing
// request can even be sent. The error then points at the new number, which is
// fine, instead of the old one, which is not there any more to be seen.
//
// This is deleted automatically rather than left as a step to remember,
// because it was forgotten three times in a row, and a half-finished attempt
// has no value worth keeping.
if (PAIR_NUMBER && existsSync(AUTH_DIR) && !hasRealSession()) {
  rmSync(AUTH_DIR, { recursive: true, force: true });
  console.log('\n  Cleared a half-finished pairing attempt.');
}

const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
const alreadyPaired = Boolean(state.creds?.registered);

const sock = makeWASocket({
  auth: state,
  // With a pairing code the QR is noise: it scrolls the code out of view.
  printQRInTerminal: false,
  // Baileys cycles a few QR references and then gives up with "QR refs
  // attempts ended". The default leaves about two minutes to find the right
  // screen on the phone and type eight characters, which is not enough the
  // first time somebody does it. Three minutes per reference is.
  qrTimeout: 180_000,
});
sock.ev.on('creds.update', saveCreds);

if (PAIR_NUMBER && !alreadyPaired) {
  // A moment for the socket to finish opening, or the request is refused.
  await new Promise((r) => setTimeout(r, 4000));
  try {
    const code = await sock.requestPairingCode(PAIR_NUMBER);
    // Printed twice on purpose: grouped so it can be read off the screen,
    // and plain so nobody types the hyphen. WhatsApp wants the eight
    // characters and nothing else.
    console.log('\n  Pairing code:  ' + code.match(/.{1,4}/g).join(' '));
    console.log('  Type exactly:  ' + code + '   (eight characters, no dash)\n');
    console.log('  On the bot phone, in this order:');
    console.log('    WhatsApp, Settings, Linked devices, Link a device,');
    console.log('    then "Link with phone number instead", then type it.\n');
    console.log('  Be on that screen before running this: the code lasts about');
    console.log('  three minutes, then the connection closes and you start over.\n');
  } catch (error) {
    console.error('Could not request a pairing code:', error.message);
    console.error('PAIR_NUMBER must be the bot phone\'s own number: digits only,');
    console.error('country code included, no plus sign and no spaces.');
    console.error('A number without its country code is rejected the same way.\n');
    process.exit(1);
  }
}

sock.ev.on('connection.update', async ({ connection, qr, lastDisconnect }) => {
  if (qr && !PAIR_NUMBER) {
    console.log('\nScan this QR code with WhatsApp:');
    console.log('(if it will not scan, widen the terminal, use a dark');
    console.log(' background, and scan the LAST code printed)\n');
    qrcode.generate(qr, { small: true });
  }

  if (connection === 'close') {
    const reason = lastDisconnect?.error?.output?.statusCode;
    if (reason === 408) {
      console.error('\n  The code expired before it was entered.');
      console.error('  Open WhatsApp, Settings, Linked devices, Link a device,');
      console.error('  "Link with phone number instead" FIRST, then run this again');
      console.error('  and type the code straight away.\n');
    } else {
      console.error(`\nConnection closed (${reason ?? 'unknown'}).`);
    }
    console.error('  rm -rf auth_info   before retrying, a half-finished');
    console.error('  attempt blocks the next one.\n');
    process.exit(1);
  }

  if (connection !== 'open') return;

  console.log('\nPaired. Reading the group list...');

  // A moment for the group list to arrive after the socket opens.
  await new Promise((r) => setTimeout(r, 3000));
  const groups = await sock.groupFetchAllParticipating();

  const rows = Object.values(groups);
  if (!rows.length) {
    console.log('\nThis number is not in any group yet. Add it to the group first,');
    console.log('then run this again.\n');
    process.exit(0);
  }

  console.log('\nGroups this number is in:\n');
  for (const g of rows) {
    console.log(`  ${g.subject}`);
    console.log(`    GROUP_JID=${g.id}`);
    console.log(`    ${g.participants?.length ?? '?'} participants\n`);
  }
  console.log('Copy the GROUP_JID line for the right group into .env.\n');
  process.exit(0);
});
