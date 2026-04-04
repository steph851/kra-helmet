# Deploying KRA Deadline Tracker & Compliance Tool

Free deployment options optimized for Kenya.

---

## Option 1: Render (Recommended — Easiest)

**Free tier**: 750 hours/month, auto-deploy from GitHub, free SSL.
**Sleep fix**: Free tier sleeps after 15 min — we fix this with UptimeRobot (free) + webhook buffer.

### Steps:

1. Push your code to GitHub
2. Go to [render.com](https://render.com) → sign up with GitHub
3. Click **New → Web Service** → connect your `kra-helmet` repo
4. Render auto-detects `render.yaml` — just confirm:
   - **Name**: `kra-deadline-tracker`
   - **Region**: Frankfurt (closest to Kenya)
   - **Plan**: Free
5. Add environment variables in dashboard:
   - `ANTHROPIC_API_KEY` = your key
   - `HELMET_API_KEY` = your API key
6. Click **Deploy** — takes ~3 minutes
7. Your app is live at: `https://kra-deadline-tracker.onrender.com`

### Keep-Alive Setup (IMPORTANT — prevents sleep):

8. Go to [uptimerobot.com](https://uptimerobot.com) → sign up (free, no card)
9. Click **Add New Monitor**:
   - **Type**: HTTP(s)
   - **Friendly Name**: KRA Deadline Tracker
   - **URL**: `https://kra-deadline-tracker.onrender.com/health`
   - **Interval**: 5 minutes
10. Save — UptimeRobot pings your app every 5 min, Render never sleeps

### M-Pesa Webhook Safety (built-in):

Even if Render briefly sleeps before UptimeRobot wakes it:
- Safaricom retries failed webhooks automatically
- All incoming webhooks are **buffered to disk first** before processing
- On startup, unprocessed webhooks are **automatically retried**
- Zero payments lost

---

## Option 2: Koyeb (Always-On Free Tier)

**Free tier**: 1 nano instance, always running (no sleep!), free SSL.
**Best for**: Production use — no cold starts.

### Steps:

1. Go to [koyeb.com](https://koyeb.com) → sign up with GitHub
2. Click **Create App** → **Docker**
3. Connect your GitHub repo, select the Dockerfile
4. Configure:
   - **Instance**: Free (nano)
   - **Region**: Frankfurt
   - **Port**: 8000
5. Add secrets: `ANTHROPIC_API_KEY`, `HELMET_API_KEY`
6. Deploy — live at: `https://kra-deadline-tracker-<id>.koyeb.app`

---

## Option 3: Fly.io (Closest Server to Kenya)

**Free tier**: 3 shared VMs, 256MB RAM each.
**Best for**: Lowest latency — Johannesburg data center.

### Steps:

```bash
# Install Fly CLI
curl -L https://fly.io/install.sh | sh

# Login & deploy
fly auth login
fly launch --now

# Set secrets
fly secrets set ANTHROPIC_API_KEY=sk-ant-... HELMET_API_KEY=your-key
```

Live at: `https://kra-deadline-tracker.fly.dev`

---

## Option 4: Railway (Simple, $5 Free Credit)

**Free tier**: $5/month credit (enough for light use).

1. Go to [railway.app](https://railway.app) → sign up with GitHub
2. **New Project → Deploy from GitHub Repo**
3. Railway auto-detects the Dockerfile
4. Add env vars: `ANTHROPIC_API_KEY`, `HELMET_API_KEY`, `PORT=8000`
5. Deploy — generates a public URL

---

## WhatsApp Bot (Runs Locally)

The WhatsApp bot **must run on your local machine** because it needs:
- Chromium browser for WhatsApp Web
- QR code scan from your phone
- Persistent session storage

```bash
cd bot
npm install
node server.js
# Scan QR code with WhatsApp → linked devices
```

The deployed API works fine without the bot — messages fall back to dry-run logging.
To connect your local bot to the deployed API, you'd need a tunnel:

```bash
# Using ngrok (free)
ngrok http 3001
# Then set BOT_URL env var on your deployment to the ngrok URL
```

---

## Environment Variables Reference

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Claude AI API key |
| `HELMET_API_KEY` | No | Dashboard API key (auth disabled if unset) |
| `PORT` | Auto | Set by platform automatically |
| `RENDER_EXTERNAL_URL` | Auto | Set by Render (enables keep-alive) |
| `BOT_URL` | No | WhatsApp bot URL (default: http://localhost:3001) |

---

## After Deployment

1. Visit your URL → you'll see the landing page at `/signup`
2. Dashboard is at `/` (or any route — React handles routing)
3. API docs at `/docs`
4. Health check at `/health`
5. Share the signup link with SMEs in Kenya!
