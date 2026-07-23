# Gmail skill - one-time OAuth setup

Goal: produce `credentials.json` (OAuth **Desktop** client) in this folder, then run `auth`.
Takes about 5 minutes. No Google verification, no paid tier, no Workspace admin needed -
you are authorising your own account against your own client.

## In Google Cloud Console (signed in as the mailbox you want to drive)

1. **Project**: https://console.cloud.google.com/projectcreate → name e.g. `gmail-cli` → Create.
   (Or reuse any existing project.)
2. **Enable the Gmail API**: https://console.cloud.google.com/apis/library/gmail.googleapis.com
   → select the project → **Enable**.
3. **OAuth consent screen** (Google Auth Platform → Branding / Audience):
   - User type **External**.
   - App name `gmail-cli`, user support email = your email, developer contact = your email. Save.
   - **Audience** → add **Test user**: your own address.
     Test mode is fine and never expires for your own account - no verification review needed.
4. **Create the client**: APIs & Services → **Credentials** → **Create credentials** →
   **OAuth client ID** → Application type **Desktop app** → name `gmail-cli-desktop` →
   **Create** → **Download JSON**.
5. Save/rename the downloaded file to `credentials.json` next to `gmail_cli.py`
   (i.e. `~/.claude/skills/gmail/credentials.json`).

## Then

```bash
python3 gmail_cli.py auth
```

A browser tab opens → pick your account → "Google hasn't verified this app" →
**Advanced** → **Continue** → **Allow**. Done. `token.json` is written next to the script
(chmod 600) and refreshes itself from then on. You never do this again.

## Scopes requested

| Scope | Buys you |
|---|---|
| `gmail.modify` | search, read, download attachments, create drafts, add/remove labels, archive |
| `gmail.send` | send a message or an existing draft |

Deliberately **not** requested: `gmail.settings.*`, and any scope allowing permanent
deletion. Worst case, a bad instruction archives something - it cannot destroy mail.

## Revoking

https://myaccount.google.com/permissions → `gmail-cli` → Remove access.
Then delete `token.json`. That is the whole kill switch.

## Troubleshooting

- **`SSLCertVerificationError` / `unable to get local issuer certificate`** - your network
  intercepts TLS (corporate proxy, some VPNs and security agents). Export the trust roots
  your machine actually uses into `ca-bundle.pem` beside the script and it will be picked
  up automatically. On macOS:
  ```bash
  security find-certificate -a -p /System/Library/Keychains/SystemRootCertificates.keychain > ca-bundle.pem
  security find-certificate -a -p /Library/Keychains/System.keychain >> ca-bundle.pem
  ```
- **`access_denied` on the consent screen** - you did not add yourself as a **Test user** in
  step 3.
- **`invalid_grant` later on** - the token was revoked or the consent screen changed.
  Delete `token.json` and re-run `auth`.
- **Wrong account authorised** - delete `token.json`, re-run `auth`, pick carefully.
