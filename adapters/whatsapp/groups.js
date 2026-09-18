/**
 * Print the JID of every group this number is in, then exit.
 *
 * You need GROUP_JID to configure the worker and there is no way to read it
 * off a phone screen. Run this once after pairing, copy the line for the METI
 * group into .env, and never think about it again.
 *
 *   npm run groups
 */

import makeWASocket, { useMultiFileAuthState } from '@whiskeysockets/baileys';
import qrcode from 'qrcode-terminal';

const { state, saveCreds } = await useMultiFileAuthState('auth_info');
const sock = makeWASocket({ auth: state });
sock.ev.on('creds.update', saveCreds);

sock.ev.on('connection.update', async ({ connection, qr }) => {
  if (qr) {
    console.log('\nScan this QR code with WhatsApp:\n');
    qrcode.generate(qr, { small: true });
  }

  if (connection !== 'open') return;

  // A moment for the group list to arrive after the socket opens.
  await new Promise((r) => setTimeout(r, 3000));
  const groups = await sock.groupFetchAllParticipating();

  const rows = Object.values(groups);
  if (!rows.length) {
    console.log('\nThis number is not in any group yet. Add it to the group first.\n');
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
