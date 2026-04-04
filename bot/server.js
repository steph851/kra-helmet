/**
 * KRA Deadline Tracker — WhatsApp Bot Server
 *
 * Uses whatsapp-web.js to send messages from your own WhatsApp number.
 * Exposes a simple HTTP API for the Python backend to call.
 *
 * First run: scan the QR code with your phone (WhatsApp > Linked Devices > Link a Device)
 * After that: session is saved and auto-reconnects.
 *
 * API:
 *   POST /send        — Send a text message
 *   POST /send-image  — Send an image with caption
 *   GET  /status      — Bot connection status
 *   GET  /health      — Health check
 */

const { Client, LocalAuth } = require('whatsapp-web.js');
const qrcode = require('qrcode-terminal');
const express = require('express');
const path = require('path');

const app = express();
app.use(express.json());

const PORT = process.env.BOT_PORT || 3001;
const AUTH_DIR = path.join(__dirname, '.wwebjs_auth');

// ── WhatsApp Client ────────────────────────────────────────────

let botReady = false;
let lastQR = null;

const client = new Client({
  authStrategy: new LocalAuth({ dataPath: AUTH_DIR }),
  puppeteer: {
    headless: true,
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-dev-shm-usage',
      '--disable-gpu',
    ],
  },
});

client.on('qr', (qr) => {
  lastQR = qr;
  console.log('\n╔══════════════════════════════════════════════╗');
  console.log('║  SCAN THIS QR CODE WITH YOUR WHATSAPP PHONE  ║');
  console.log('║  WhatsApp > Settings > Linked Devices > Link  ║');
  console.log('╚══════════════════════════════════════════════╝\n');
  qrcode.generate(qr, { small: true });
});

client.on('ready', () => {
  botReady = true;
  lastQR = null;
  const info = client.info;
  console.log(`\n✅ WhatsApp Bot connected: ${info.pushname} (${info.wid.user})`);
  console.log(`   Bot API running on http://localhost:${PORT}`);
  console.log(`   Ready to send messages.\n`);
});

client.on('authenticated', () => {
  console.log('🔐 WhatsApp authenticated (session saved)');
});

client.on('auth_failure', (msg) => {
  console.error('❌ WhatsApp auth failed:', msg);
  botReady = false;
});

client.on('disconnected', (reason) => {
  console.warn('⚠️  WhatsApp disconnected:', reason);
  botReady = false;
  // Auto-reconnect
  setTimeout(() => {
    console.log('🔄 Reconnecting...');
    client.initialize();
  }, 5000);
});

// ── Helpers ────────────────────────────────────────────────────

/**
 * Normalize Kenya phone to WhatsApp ID format: 254XXXXXXXXX@c.us
 */
function normalizePhone(phone) {
  let clean = phone.replace(/[\s\-\(\)]/g, '');
  if (clean.startsWith('+')) clean = clean.slice(1);
  if (clean.startsWith('0')) clean = '254' + clean.slice(1);
  if (!clean.startsWith('254')) clean = '254' + clean;
  return clean + '@c.us';
}

/**
 * Send a text message and return result.
 */
async function sendMessage(phone, message) {
  if (!botReady) {
    throw new Error('WhatsApp bot not connected. Scan QR code first.');
  }
  const chatId = normalizePhone(phone);

  // Check if number is registered on WhatsApp
  const isRegistered = await client.isRegisteredUser(chatId);
  if (!isRegistered) {
    throw new Error(`${phone} is not registered on WhatsApp`);
  }

  const result = await client.sendMessage(chatId, message);
  return {
    success: true,
    messageId: result.id.id,
    to: chatId,
    timestamp: new Date().toISOString(),
  };
}

// ── API Routes ─────────────────────────────────────────────────

/**
 * POST /send
 * Body: { phone: "0712345678", message: "Hello..." }
 */
app.post('/send', async (req, res) => {
  try {
    const { phone, message } = req.body;
    if (!phone || !message) {
      return res.status(400).json({ error: 'phone and message required' });
    }
    const result = await sendMessage(phone, message);
    console.log(`📤 Sent to ${phone}: ${message.slice(0, 60)}...`);
    res.json(result);
  } catch (err) {
    console.error(`❌ Send failed: ${err.message}`);
    res.status(500).json({ error: err.message, success: false });
  }
});

/**
 * POST /send-bulk
 * Body: { messages: [{ phone: "...", message: "..." }, ...] }
 */
app.post('/send-bulk', async (req, res) => {
  const { messages } = req.body;
  if (!Array.isArray(messages)) {
    return res.status(400).json({ error: 'messages array required' });
  }

  const results = [];
  for (const { phone, message } of messages) {
    try {
      const result = await sendMessage(phone, message);
      results.push({ phone, ...result });
      // Rate limit: 1 message per second to avoid WhatsApp ban
      await new Promise(r => setTimeout(r, 1000));
    } catch (err) {
      results.push({ phone, success: false, error: err.message });
    }
  }

  const sent = results.filter(r => r.success).length;
  console.log(`📤 Bulk send: ${sent}/${messages.length} delivered`);
  res.json({ total: messages.length, sent, failed: messages.length - sent, results });
});

/**
 * GET /status — Bot connection status
 */
app.get('/status', (req, res) => {
  const info = botReady ? client.info : null;
  res.json({
    connected: botReady,
    phone: info ? info.wid.user : null,
    name: info ? info.pushname : null,
    qr_pending: !!lastQR,
  });
});

/**
 * GET /health — Simple health check
 */
app.get('/health', (req, res) => {
  res.json({
    status: botReady ? 'connected' : 'disconnected',
    service: 'kra-helmet-whatsapp-bot',
    timestamp: new Date().toISOString(),
  });
});

// ── Start ──────────────────────────────────────────────────────

app.listen(PORT, () => {
  console.log('╔═══════════════════════════════════════════════╗');
  console.log('║  KRA Deadline Tracker — WhatsApp Bot                    ║');
  console.log(`║  API: http://localhost:${PORT}                    ║`);
  console.log('║  Initializing WhatsApp connection...           ║');
  console.log('╚═══════════════════════════════════════════════╝');
  client.initialize();
});
