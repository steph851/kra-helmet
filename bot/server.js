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
const fs = require('fs');
const path = require('path');

const app = express();
app.use(express.json());

const PORT = process.env.BOT_PORT || 3001;
const AUTH_DIR = path.join(__dirname, '.wwebjs_auth');
const RETRY_QUEUE_PATH = path.join(__dirname, 'retry_queue.json');

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

  // Process any queued messages from when bot was disconnected
  const queue = loadRetryQueue();
  if (queue.length > 0) {
    console.log(`🔄 Processing ${queue.length} queued messages...`);
    setTimeout(processRetryQueue, 5000);
  }
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

// ── Retry Queue ───────────────────────────────────────────────

const MAX_RETRIES = 3;
const RETRY_DELAYS = [30_000, 120_000, 300_000]; // 30s, 2min, 5min

function loadRetryQueue() {
  try {
    if (fs.existsSync(RETRY_QUEUE_PATH)) {
      return JSON.parse(fs.readFileSync(RETRY_QUEUE_PATH, 'utf8'));
    }
  } catch (err) {
    console.error('⚠️  Failed to load retry queue:', err.message);
  }
  return [];
}

function saveRetryQueue(queue) {
  try {
    fs.writeFileSync(RETRY_QUEUE_PATH, JSON.stringify(queue, null, 2), 'utf8');
  } catch (err) {
    console.error('⚠️  Failed to save retry queue:', err.message);
  }
}

function enqueueRetry(phone, message, error) {
  const queue = loadRetryQueue();
  // Don't queue if phone isn't on WhatsApp — retrying won't help
  if (error && error.includes('not registered on WhatsApp')) return;

  const existing = queue.find(e => e.phone === phone && e.message === message);
  if (existing) return; // Already queued

  queue.push({
    phone,
    message,
    attempts: 0,
    last_error: error,
    created_at: new Date().toISOString(),
    next_retry_at: new Date(Date.now() + RETRY_DELAYS[0]).toISOString(),
  });
  saveRetryQueue(queue);
  console.log(`🔄 Queued retry for ${phone} (${queue.length} in queue)`);
}

async function processRetryQueue() {
  if (!botReady) return;

  const queue = loadRetryQueue();
  if (queue.length === 0) return;

  const now = Date.now();
  let changed = false;
  const remaining = [];

  for (const entry of queue) {
    if (new Date(entry.next_retry_at).getTime() > now) {
      remaining.push(entry);
      continue;
    }

    try {
      await sendMessage(entry.phone, entry.message);
      console.log(`✅ Retry succeeded for ${entry.phone} (attempt ${entry.attempts + 1})`);
      changed = true;
      // Don't push to remaining — it's done
    } catch (err) {
      entry.attempts += 1;
      entry.last_error = err.message;
      changed = true;

      if (entry.attempts >= MAX_RETRIES) {
        console.warn(`❌ Giving up on ${entry.phone} after ${MAX_RETRIES} retries: ${err.message}`);
        // Drop from queue
      } else {
        const delay = RETRY_DELAYS[Math.min(entry.attempts, RETRY_DELAYS.length - 1)];
        entry.next_retry_at = new Date(now + delay).toISOString();
        remaining.push(entry);
        console.log(`🔄 Retry ${entry.attempts}/${MAX_RETRIES} failed for ${entry.phone}, next in ${delay / 1000}s`);
      }
    }

    // Rate limit between retries
    await new Promise(r => setTimeout(r, 1500));
  }

  if (changed) {
    saveRetryQueue(remaining);
  }
}

// Process retry queue every 60 seconds
setInterval(processRetryQueue, 60_000);

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
    enqueueRetry(req.body.phone, req.body.message, err.message);
    res.status(500).json({ error: err.message, success: false, queued_for_retry: true });
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
      enqueueRetry(phone, message, err.message);
      results.push({ phone, success: false, error: err.message, queued_for_retry: true });
    }
  }

  const sent = results.filter(r => r.success).length;
  const retried = results.filter(r => r.queued_for_retry).length;
  console.log(`📤 Bulk send: ${sent}/${messages.length} delivered, ${retried} queued for retry`);
  res.json({ total: messages.length, sent, failed: messages.length - sent, retried, results });
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
 * GET /retry-queue — View pending retry queue
 */
app.get('/retry-queue', (req, res) => {
  const queue = loadRetryQueue();
  res.json({
    pending: queue.length,
    entries: queue.map(e => ({
      phone: e.phone,
      attempts: e.attempts,
      last_error: e.last_error,
      next_retry_at: e.next_retry_at,
      created_at: e.created_at,
    })),
  });
});

/**
 * DELETE /retry-queue — Clear the retry queue
 */
app.delete('/retry-queue', (req, res) => {
  saveRetryQueue([]);
  res.json({ cleared: true });
});

/**
 * GET /health — Simple health check
 */
app.get('/health', (req, res) => {
  const queue = loadRetryQueue();
  res.json({
    status: botReady ? 'connected' : 'disconnected',
    service: 'kra-helmet-whatsapp-bot',
    retry_queue_pending: queue.length,
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
