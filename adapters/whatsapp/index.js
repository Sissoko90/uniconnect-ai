import makeWASocket, { useMultiFileAuthState, DisconnectReason } from '@whiskeysockets/baileys';
import qrcode from 'qrcode-terminal';

async function connectToWhatsApp() {
  const { state, saveCreds } = await useMultiFileAuthState('auth_info');

  const sock = makeWASocket({
    auth: state,
  });

  sock.ev.on('creds.update', saveCreds);

  // Connection Lifecycle & QR Handler
  sock.ev.on('connection.update', (update) => {
    const { connection, lastDisconnect, qr } = update;

    if (qr) {
      console.log('\nScan this QR code with WhatsApp:\n');
      qrcode.generate(qr, { small: true });
    }

    if (connection === 'close') {
      const shouldReconnect =
        lastDisconnect?.error?.output?.statusCode !== DisconnectReason.loggedOut;
      console.log('Connection closed. Reconnecting...', shouldReconnect);
      if (shouldReconnect) connectToWhatsApp();
    } else if (connection === 'open') {
      console.log('WhatsApp Bot is ONLINE and listening in groups!');
    }
  });

  // Incoming Message Handler
  sock.ev.on('messages.upsert', async ({ messages, type }) => {
    if (type !== 'notify') return;

    for (const msg of messages) {
      // Ignore self messages
      if (msg.key.fromMe) continue;

      const remoteJid = msg.key.remoteJid || '';
      const isGroup = remoteJid.endsWith('@g.us');

      // IGNORE ALL DIRECT MESSAGES COMPLETELY
      if (!isGroup) continue;

      const text = (msg.message?.conversation || msg.message?.extendedTextMessage?.text || '').trim();
      if (!text) continue;

      // Group Chat Logic: Only reply if starts with @ask
      if (text.toLowerCase().startsWith('@ask')) {
        console.log(`Triggered in group by: "${text}". Replying "pong"...`);
        await sock.sendMessage(remoteJid, { text: 'pong' }, { quoted: msg });
      } else {
        // Silent background reading for database indexing
        console.log(`[Group Log - Silent]: ${text}`);
      }
    }
  });
}

connectToWhatsApp();