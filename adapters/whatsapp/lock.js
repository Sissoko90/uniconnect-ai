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

const LOCK = new URL('auth_info/.lock', import.meta.url).pathname;

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
  if (pid) {
    console.error(
      `Another WhatsApp process is already using this session (pid ${pid}).\n` +
        'WhatsApp allows one connection per linked device: starting a second ' +
        'throws the first off and can invalidate the pairing.\n\n' +
        'Stop it first:  sudo systemctl stop uniconnect-bot'
    );
    process.exit(1);
  }

  mkdirSync(new URL('auth_info', import.meta.url).pathname, { recursive: true });
  writeFileSync(LOCK, String(process.pid));

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
