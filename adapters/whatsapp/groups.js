/**
 * Pair the bot's number, then print the JID of every group it is in.
 *
 *   npm run groups                              QR code, or an existing session
 *   PAIR_NUMBER=<the number> npm run groups     eight character code instead
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
 *   Pairing code. Set PAIR_NUMBER to the bot's own number, digits only,
 *   country code included, no plus sign. WhatsApp prints eight characters
 *   here and you type them on the phone under Linked devices, Link with phone
 *   number. Nothing has to render correctly for that to work.
 */

import { existsSync, rmSync } from 'node:fs';

import makeWASocket, { useMultiFileAuthState } from '@whiskeysockets/baileys';
import qrcode from 'qrcode-terminal';

import { claimSession } from './lock.js';

// Which session directory to pair into. The backup number is paired with
// AUTH_DIR=auth_info_backup, ahead of time, so that the day it is needed
// nobody has to find a phone and type a code.
const AUTH_DIR = process.env.AUTH_DIR || 'auth_info';
const PAIR_NUMBER = (process.env.PAIR_NUMBER || '').replace(/\D/g, '');

// The number this file used to print as an example. Somebody ran it verbatim,
// WhatsApp issued a code for an account that does not exist, and the phone
// answered "impossible de se connecter" with nothing to say why. An example
// that looks like a real number will be pasted as one.
const PLACEHOLDER = '22370001234';

if (PAIR_NUMBER === PLACEHOLDER) {
  console.error('\n  PAIR_NUMBER is still the example from the documentation.');
  console.error("  Use the bot phone's own number: digits only, country code");
  console.error('  included, no plus sign and no spaces.\n');
  process.exit(1);
}

if (PAIR_NUMBER && (PAIR_NUMBER.length < 8 || PAIR_NUMBER.length > 15)) {
  console.error(`\n  PAIR_NUMBER has ${PAIR_NUMBER.length} digits, which is not a`);
  console.error('  phone number with a country code. Expected between 8 and 15.');
  console.error('  A number without its country code is rejected by WhatsApp.\n');
  process.exit(1);
}

// Passing PAIR_NUMBER means "pair this number now", so anything already on
// disk goes. Keeping a session that matched the number looked careful and was
// the opposite: a pairing can register on the phone and still leave
// credentials that match nothing, and those credentials name the right
// number. The check meant to protect a working session protected the broken
// one instead, and every run afterwards failed the same way.
//
// Running without PAIR_NUMBER is the way to use an existing session.
if (PAIR_NUMBER && existsSync(AUTH_DIR)) {
  rmSync(AUTH_DIR, { recursive: true, force: true });
  console.log('\n  Starting a fresh pairing.');
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// Baileys logs its whole protocol conversation at info level: pre-key
// uploads, app state sync, history notifications, hundreds of lines. The one
// thing this tool exists to print, the group id, scrolls past in the middle
// of it. Warnings and errors still come through, so a real failure is not
// hidden, only the running commentary.
//
// Written out rather than pulled from pino, which is Baileys' own dependency
// and not ours to import.
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

// Asked once per run. After a pairing the socket reconnects, and asking again
// on the new one would request a second code nobody needs.
let askedForCode = false;

async function connect() {
  claimSession('groups.js');

  const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);

  const sock = makeWASocket({
    auth: state,
    logger: quiet,
    // With a pairing code the QR is noise: it scrolls the code out of view.
    printQRInTerminal: false,
    // Baileys cycles a few QR references and then gives up with "QR refs
    // attempts ended". The default leaves about two minutes to find the right
    // screen on a phone and type eight characters, which is not enough the
    // first time somebody does it.
    qrTimeout: 180_000,
  });
  sock.ev.on('creds.update', saveCreds);

  if (PAIR_NUMBER && !state.creds?.registered && !askedForCode) {
    askedForCode = true;
    await sleep(4000); // let the socket finish opening, or the request is refused
    try {
      const code = await sock.requestPairingCode(PAIR_NUMBER);
      // Printed twice on purpose: grouped so it can be read off the screen,
      // and plain so nobody types the separator WhatsApp does not want.
      console.log('\n  Pairing code:  ' + code.match(/.{1,4}/g).join(' '));
      console.log('  Type exactly:  ' + code + '   (eight characters, no dash)\n');
      console.log('  On the bot phone, in this order:');
      console.log('    WhatsApp, Settings, Linked devices, Link a device,');
      console.log('    then "Link with phone number instead", then type it.\n');
    } catch (error) {
      console.error('\n  Could not request a pairing code:', error.message);
      console.error("  PAIR_NUMBER must be the bot phone's own number: digits");
      console.error('  only, country code included, no plus sign.\n');
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

      // 515 is not a failure. WhatsApp sends it immediately after a
      // successful pairing to say the socket must be reopened, and Baileys
      // logs "pairing configured successfully, expect to restart the
      // connection" just before it. Treating it as fatal made a pairing that
      // had actually worked look like an error, and sent people back to the
      // beginning of a process that was already finished.
      if (reason === 515) {
        console.log('  Paired. Reconnecting...\n');
        await sleep(1500);
        return connect();
      }

      if (reason === 408) {
        console.error('\n  The code expired before it was entered.');
        console.error('  Open the phone on WhatsApp, Settings, Linked devices,');
        console.error('  Link a device, "Link with phone number instead" FIRST,');
        console.error('  then run this again and type the code straight away.\n');
      } else if (reason === 401) {
        // The session on disk is dead, so there is nothing to protect by
        // keeping it, and keeping it guarantees the next run fails the same
        // way. This happens when a pairing registered on the phone but the
        // socket closed before the handshake finished writing: the number is
        // right, the credentials match nothing, and the strict check above
        // keeps them precisely because the number matches.
        rmSync(AUTH_DIR, { recursive: true, force: true });
        console.error('\n  WhatsApp rejected the session (401), so it has been cleared.');
        console.error('  On the bot phone, open WhatsApp, Settings, Linked devices');
        console.error('  and remove any entry for this server, then run:\n');
        console.error(`    PAIR_NUMBER=${PAIR_NUMBER || '<the bot number>'} npm run groups\n`);
      } else {
        console.error(`\n  Connection closed (${reason ?? 'unknown'}).\n`);
      }
      process.exit(1);
    }

    if (connection !== 'open') return;

    console.log('  Connected. Reading the group list...');
    await sleep(3000); // the group list arrives shortly after the socket opens

    const groups = Object.values(await sock.groupFetchAllParticipating());
    if (!groups.length) {
      console.log('\n  This number is not in any group yet.');
      console.log('  Add it to the group first, then run this again.\n');
      process.exit(0);
    }

    console.log('\nGroups this number is in:\n');
    for (const group of groups) {
      console.log(`  ${group.subject}`);
      console.log(`    GROUP_JID=${group.id}`);
      console.log(`    ${group.participants?.length ?? '?'} participants\n`);
    }
    console.log('Copy the GROUP_JID line for the right group into .env.\n');
    process.exit(0);
  });
}

await connect();
