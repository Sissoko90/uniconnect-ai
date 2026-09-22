/**
 * Set the bot's WhatsApp profile picture and name, then exit.
 *
 *   npm run avatar
 *   BOT_NAME="UNICONNECT BOT" npm run avatar
 *
 * The name matters as much as the picture here. The programme's organiser
 * has asked every team to name its bot "<TEAM NAME> BOT", so that members
 * can tell them apart while they test and vote. A bot that ignores that
 * instruction is the one nobody can find in their chat list.
 *
 * Run once, after pairing. It is what 153 people actually see: the avatar next
 * to every answer, in the group list, and at the top of the private chat where
 * the useful half of this product happens. A default grey silhouette reads as
 * an unfinished script; the logo reads as something somebody built.
 *
 * Separate from index.js on purpose. Setting it on every connect would mean
 * asking WhatsApp to rewrite the profile each time the socket reconnects,
 * which is a pointless call on a platform that blocks numbers for behaving
 * mechanically.
 */

import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import makeWASocket, { useMultiFileAuthState } from '@whiskeysockets/baileys';
import qrcode from 'qrcode-terminal';

import { claimSession } from './lock.js';

const here = dirname(fileURLToPath(import.meta.url));

// The copy the API serves, so the avatar, the web page and the README are
// always the same image. See assets/README.md.
const LOGO = resolve(here, '../../core/static/logo.png');

const image = readFileSync(LOGO);
console.log(`Using ${LOGO} (${Math.round(image.length / 1024)} kB)`);

claimSession('avatar.js');

// Which session to dress. The spare number has its own, so it can carry the
// same name and picture as the main one and nobody notices the switch.
const AUTH_DIR = process.env.AUTH_DIR || 'auth_info';

const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
const sock = makeWASocket({ auth: state });
sock.ev.on('creds.update', saveCreds);

sock.ev.on('connection.update', async ({ connection, qr }) => {
  if (qr) {
    console.log('\nScan this QR code with WhatsApp:\n');
    qrcode.generate(qr, { small: true });
  }

  if (connection !== 'open') return;

  // A moment for the socket to settle before asking it to write anything.
  await new Promise((r) => setTimeout(r, 2000));

  const me = sock.user?.id;
  if (!me) {
    console.error('Connected but no account id. Try again.');
    process.exit(1);
  }

  const name = (process.env.BOT_NAME || '').trim();
  if (name) {
    try {
      await sock.updateProfileName(name);
      console.log(`Name set to "${name}".`);
    } catch (error) {
      console.error('Could not set the name:', error.message);
    }
  }

  try {
    await sock.updateProfilePicture(me, image);
    console.log(`Profile picture set for ${me}.`);
    console.log('Check it on the bot phone: it can take a minute to appear.');
  } catch (error) {
    console.error('Could not set the profile picture:', error.message);
    console.error(
      'If the worker is running, that is why: WhatsApp allows one connection ' +
        'per linked device and the second one is thrown off. Stop it first ' +
        '(systemctl stop uniconnect-bot), run this, then start it again.'
    );
    console.error('Or set it by hand on the bot phone, from core/static/logo.png.');
    process.exit(1);
  }

  process.exit(0);
});
