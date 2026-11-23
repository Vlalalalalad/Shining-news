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

Advertising defaults to 100% for eligible news and market alerts, rendered as a Telegram blockquote. Sensitive events and news scored 98+ are excluded by default. The advertising-policy migration applies the owner's 100% request once; subsequent admin edits are preserved. Percentage, exclusions, quote format, brand label and URL are now configurable.

Detailed controls are defined in `settings_schema.py` and rendered by `advanced_ui.py`. The command handler and radar both validate through this schema. The API deployment must include both modules. Fact verification and deduplication remain enforced independently of the importance threshold.
