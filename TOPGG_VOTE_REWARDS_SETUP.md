# Top.gg vote rewards setup

The bot now includes `/profile` and `/vote`. A confirmed Top.gg vote awards **5,000 virtual coins**. A double-weight Top.gg vote awards **10,000 coins**. Each vote event is recorded by its vote ID so webhook retries do not pay the same vote twice.

## WispByte environment variables

Add these variables to the bot service:

```text
TOPGG_WEBHOOK_SECRET=the_secret_from_the_topgg_webhooks_page
TOPGG_WEBHOOK_PORT=8080
```

Keep the secret private. The bot starts the endpoint at:

```text
POST /topgg/webhook
```

Use the public HTTPS URL provided by WispByte for that port, followed by `/topgg/webhook`, in the Top.gg project dashboard under **Webhooks**. For example:

```text
https://your-wispbyte-public-host/topgg/webhook
```

Top.gg v1 webhooks use the `x-topgg-signature` header. The bot verifies the HMAC signature before processing a vote. The handler also accepts legacy Top.gg authorization-header events.

After adding the variables, restart the service and send a test webhook from the Top.gg dashboard. Check the bot logs for the webhook startup message and use `/profile` to confirm the reward after a real vote.

The profile command displays wallet, bank, total wealth, games played, recorded wins, investments, claimed Top.gg votes, and account status. The `/vote` command displays the Top.gg voting link and reward information.
