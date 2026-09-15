# Phone access and background notifications

The computer runs the work; the phone controls it through private Tailscale HTTPS. Keep the computer on,
awake, and connected. Closing the phone app does not cancel work.

## Android: daily use

1. Connect Tailscale on the phone and computer using the authorized account.
2. Open the computer's private HTTPS address in Chrome.
3. Chrome menu → **Add to Home screen / Install app**. Open Harness from the new icon.
4. Tap the model/session pill → **Preferences** → **Enable background alerts** → allow notifications.
5. Tap **Send test alert**, return to the home screen, and check that it arrives.

Notifications contain generic completion/attention text, never prompts, results, paths, or credentials.
Tapping one opens the saved turn/receipt. Tailscale must be connected to open the app; delivery uses the
browser's push service. **Disable alerts** unsubscribes this device.

The model/session pill opens **Session setup**: Agent, Team, and Preferences tabs. Alerts, theme, and
the optional traffic-animation switch live in Preferences. Appearance choices apply immediately to
this device; Agent/Team changes use **Save changes**.

The **WISDOM** button in the top bar opens the separate **Playbook library**. WISDOM is the built-in
default. Use **Choose markdown** on your phone, or drop a `.md` file on desktop (UTF-8, up to 256 KB).
Uploading stores the document; **Use playbook** selects it and starts a fresh conversation on the next
turn, preserving history. Wait for an active turn to finish before switching. The selected playbook's
name replaces WISDOM in the top bar. WISDOM remains pinned first in the library for easy return.

**Latest exchanges** shows actual agent messages, with brief arrival motion. Tap a card for its full
feed entry. The graph shows three recent cards on a wide screen and the newest one on a phone. It
respects reduced motion and stops visual animations while the app is hidden.

**Sessions** opens the control drawer. Stop a harness turn, cancel one worker, or end an idle orchestrator
session. Other Claude/Codex sessions appear separately with their directory. External sessions require
confirmation before graceful End. Shared daemon/MCP/remote-control services have no End button.
History is retained; cancellation does not undo file edits. Claude activity labels come from its agent
list; Codex's “running” means its process exists, not that it is generating. Refresh updates the drawer.

## Operator setup

Keep the backend on loopback. Save these values in `~/.config/agent-harness/ui.env` with mode `0600`,
substituting the verified device name and account:

```ini
HARNESS_UI_ORIGIN=https://your-computer.your-tailnet.ts.net
HARNESS_UI_TAILSCALE_USER=your-account@example.com
HARNESS_UI_PUSH=1
HARNESS_UI_PUSH_SUBJECT=mailto:your-account@example.com
```

```sh
python3 -m venv ~/.local/share/agent-harness-ui/venv
~/.local/share/agent-harness-ui/venv/bin/pip install -r requirements-push.txt
bin/harness-ui install-unit
systemctl --user enable --now harness-ui.service
tailscale serve --bg --yes http://127.0.0.1:7788
```

Stop any manual server before enabling the unit to free port 7788. The launcher uses that venv when push
is enabled; `HARNESS_UI_PYTHON` overrides its location. Tailscale may require one-time browser consent for
HTTPS. User linger must be enabled for startup without a desktop login.

Serve strips incoming identity headers and injects the verified account. The UI accepts only its exact
configured HTTPS hostname/account and matching mutation Origin. Never expose the backend directly on
LAN/tailnet addresses. Remote users need no copied token; local access retains optional `HARNESS_UI_TOKEN`.

The VAPID key lives under `~/.config/agent-harness/push/`; subscriptions and SQLite outbox are under
`~/.local/state/agent-harness/push/`. Directories are private; do not commit their contents. Back up the key
and database together. Deleting the key requires devices to unsubscribe and subscribe again.

The outbox survives restarts, retries transient failures up to six times with backoff, removes expired
subscriptions on HTTP 404/410, and records permanent failures. Provider acceptance does not prove phone
display. Ambiguous retries can repeat delivery; a stable tag lets the browser replace the same alert.

## Check and rollback

```sh
systemctl --user status harness-ui.service
tailscale serve status
curl --fail http://127.0.0.1:7788/api/push
```

Push status includes readiness, subscription/pending/failed counts, and a generic error; it never exposes
endpoints or private keys. If an alert does not arrive, check browser/site/Android notification permissions
and test again from the installed app.

Disable private hosting: `tailscale serve --https=443 off`. Disable startup:
`systemctl --user disable --now harness-ui.service`. Restore the previous code/configuration and disable
push in `ui.env` to return to the prior loopback release; preserve saved state/history. To disable only
one device's notifications, use **Disable alerts**.

Sources: [Tailscale Serve](https://tailscale.com/docs/features/tailscale-serve),
[Web Push implementation](https://github.com/web-push-libs/pywebpush).
