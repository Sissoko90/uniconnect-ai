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

import makeWASocket, { useMultiFileAuthState } from '@whiskeysockets/baileys';
import qrcode from 'qrcode-terminal';

const PAIR_NUMBER = (process.env.PAIR_NUMBER || '').replace(/\D/g, '');

const { state, saveCreds } = await useMultiFileAuthState('auth_info');
const alreadyPaired = Boolean(state.creds?.registered);

const sock = makeWASocket({
  auth: state,
  // With a pairing code the QR is noise: it scrolls the code out of view.
  printQRInTerminal: false,
});
sock.ev.on('creds.update', saveCreds);

if (PAIR_NUMBER && !alreadyPaired) {
  // A moment for the socket to finish opening, or the request is refused.
  await new Promise((r) => setTimeout(r, 4000));
  try {
    const code = await sock.requestPairingCode(PAIR_NUMBER);
    console.log('\n  Pairing code:  ' + code.match(/.{1,4}/g).join('-') + '\n');
    console.log('  On the bot phone: WhatsApp, Settings, Linked devices,');
    console.log('  Link a device, then "Link with phone number instead".');
    console.log('  Type the code above. It expires after a minute or two.\n');
  } catch (error) {
    console.error('Could not request a pairing code:', error.message);
    console.error('Check that PAIR_NUMBER is the bot number in full, digits only,');
    console.error('country code included and no plus sign. Example: 22370001234\n');
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
    console.error(`\nConnection closed (${reason ?? 'unknown'}).`);
    console.error('If pairing did not complete, delete auth_info/ and try again.\n');
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
