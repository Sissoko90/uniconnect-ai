/**
 * One Baileys connection per session, enforced rather than requested.
 *
 * WhatsApp allows a single connection per linked device. A second process
 * using the same auth_info throws the first one off, and repeating that
 * invalidates the session outright: it cost us the paired number four times
 * in eighteen hours, three of them because somebody ran `npm run groups` or
 * `npm run avatar` while the worker was up.
 *
 * The deploy guide says not to. It said not to before all three. A lock is
 * worth more than a warning.
 *
 * The lock holds the pid, so a crash leaves a file that the next process
 * recognises as dead and takes over. It is inside auth_info because that is
 * the thing being protected, and because deleting auth_info to re-pair
 * clears the lock as a side effect, which is what you want.
 */

import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';

const AUTH_DIR = process.env.AUTH_DIR || 'auth_info';
const LOCK = new URL(`${AUTH_DIR}/.lock`, import.meta.url).pathname;

function holder() {
  try {
    const pid = Number(readFileSync(LOCK, 'utf8').trim());
    if (!pid) return null;
    // Signal 0 tests for existence without touching the process.
    process.kill(pid, 0);
    return pid;
  } catch {
    return null; // no lock, or the holder is gone
  }
}

/**
 * Claim the session, or exit with an explanation.
 *
 * `what` names the caller, so the message says which of the three is
 * already running rather than leaving somebody to guess.
 */
export function claimSession(what) {
  const pid = holder();

  // Our own lock. groups.js pairs, then reconnects, and the reconnect asks
  // again: it found its own pid, decided a rival was running, and killed
  // itself right after a successful pairing. The lock is there to keep two
  // processes apart, not to stop one from continuing.
  if (pid === process.pid) return;

  if (pid) {
    console.error(
      `Another WhatsApp process is already using this session (pid ${pid}).\n` +
        'WhatsApp allows one connection per linked device: starting a second ' +
        'throws the first off and can invalidate the pairing.\n\n' +
        'Stop it first:  sudo systemctl stop uniconnect-bot'
    );
    process.exit(1);
  }

  const dir = new URL(AUTH_DIR, import.meta.url).pathname;
  try {
    mkdirSync(dir, { recursive: true });
    writeFileSync(LOCK, String(process.pid));
  } catch (error) {
    if (error.code !== 'EACCES' && error.code !== 'EPERM') throw error;

    // Pairing as one user and running as another.
    //
    // `npm run groups` under sudo leaves auth_info owned by root, the
    // service runs as somebody else, and the failure that follows is far
    // worse than this crash: Baileys rewrites its keys continuously, so a
    // session it cannot save breaks, and WhatsApp answers the next
    // connection with a 401 that reads exactly like being logged out. We
    // spent an evening re-pairing a number over that, which is the one
    // thing that must not be done repeatedly.
    console.error(
      `Cannot write to ${AUTH_DIR}: ${error.code}.\n\n` +
        'The session files belong to another user. This process cannot save ' +
        'the keys WhatsApp rotates, and the connection would be dropped a ' +
        'few seconds after it opens.\n\n' +
        `Give them to the user this runs as:\n` +
        `  sudo chown -R $(id -un):$(id -gn) ${dir}\n\n` +
        'And pair as that user, not with sudo:\n' +
        '  sudo -u <service user> npm run groups'
    );
    process.exit(1);
  }

  const release = () => {
    try {
      if (existsSync(LOCK) && readFileSync(LOCK, 'utf8').trim() === String(process.pid)) {
        rmSync(LOCK);
      }
    } catch {
      // Losing the lock file on the way out is harmless: the next process
      // checks whether the pid is alive, not whether the file exists.
    }
  };

  process.on('exit', release);
  for (const signal of ['SIGINT', 'SIGTERM']) {
    process.on(signal, () => {
      release();
      process.exit(0);
    });
  }

  console.log(`${what} holds the WhatsApp session (pid ${process.pid})`);
}
