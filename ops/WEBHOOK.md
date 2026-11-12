# Telegram controls on Vercel

Commands are delivered to `https://shining-news-controls.vercel.app/api/webhook`
by Telegram webhook, independently of GitHub schedules.

- The existing two Telegram admin IDs are verified in private chats.
- Telegram's secret header is derived from the bot token and verified before any update is handled.
- Bot credentials are sealed with RSA-OAEP SHA-256 in GitHub Actions. Only the dedicated Vercel project holds the private decryption key. No raw token or private key is committed.
- Private Blob stores immutable settings snapshots and processed update IDs. Telegram delivery uses one connection to serialize admin commands.
- The radar calls the authenticated settings endpoint before live runs; its news dedupe and market episode history remain in the existing state.
- `control.yml` is manual maintenance only. It synchronizes settings when a webhook is active.
- Redeploy API changes with the Vercel project `shining-news-controls`. Token rotation requires dispatching `Provision Telegram Webhook → seal`, redeploying the new sealed file, then dispatching `enable`.
- `enable` verifies credential decryption and storage before changing Telegram delivery. Pending messages are preserved.
- Local webhook tests: install root requirements and run `python ops/test_webhook.py`.

Advertising: ordinary news retains the configured percentage. Market alerts include the signature unless branding is disabled. AI copy must include a call to action; bland news recaps fall back to reviewed templates. Sensitive and 90+ news remain without advertising.
