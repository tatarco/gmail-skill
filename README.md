# gmail-skill

A ~260-line Python CLI that gives a coding agent (Claude Code, or anything that can run a
shell command) real access to a Gmail mailbox: **search, read, download attachments, draft,
reply in-thread, send, label, archive.**

No browser automation. No scraping. No MCP server to keep alive. One file, the official
Gmail API, an OAuth token in a local file that only you hold.

```bash
python3 gmail_cli.py search "from:airline.com subject:booking newer_than:7d"
python3 gmail_cli.py read 198f2c0a1b3d4e5f
python3 gmail_cli.py download 198f2c0a1b3d4e5f --out ./attachments
python3 gmail_cli.py draft --reply-to-msg 198f2c0a1b3d4e5f --body-file reply.txt --attach doc.pdf
python3 gmail_cli.py send --draft r-88213...
```

## Why not the browser?

Driving Gmail through a browser extension works right up until it doesn't: the DOM changes,
a message is lazily rendered, an attachment download lands somewhere unpredictable, threading
a reply means clicking three things in the right order. Every one of those is a flaky step
in the middle of an otherwise deterministic task.

The Gmail API has none of that. `search` takes the same query syntax you already type into
the Gmail box. `read` returns headers plus a decoded `text/plain` body. `download` writes the
attachment bytes to a path you chose. `draft --reply-to-msg <id>` sets `In-Reply-To`,
`References`, the `Re:` subject and the `threadId` for you, so the reply lands *inside* the
thread instead of starting a new one.

**Where the browser is still the right tool: everywhere that isn't email.** The interesting
work happens when you combine the two — see the worked example below.

## Install

```bash
git clone https://github.com/tatarco/gmail-skill.git ~/.claude/skills/gmail
cd ~/.claude/skills/gmail
pip3 install -r requirements.txt
```

Then follow [SETUP.md](SETUP.md) to create your OAuth Desktop client (about 5 minutes,
free, no Google app-verification review), drop `credentials.json` next to the script, and run:

```bash
python3 gmail_cli.py auth
```

One browser consent screen, once. `token.json` is written beside the script with mode 600
and auto-refreshes from then on.

As a **Claude Code skill**, that clone path is all it takes — [SKILL.md](SKILL.md) is the
frontmatter file Claude reads to know when and how to use it. Not using Claude Code? It is
still just a CLI; point any agent at `gmail_cli.py --help`.

## Commands

| Command | What it does |
|---|---|
| `auth` | One-time OAuth consent; writes `token.json` |
| `search "<query>" [--max N]` | Gmail search syntax. Prints msgId, from, date, subject, snippet, labels |
| `read <msgId>` | Headers, decoded body, attachment list with ids |
| `download <msgId> [--out DIR]` | Save every attachment to disk |
| `draft [--reply-to-msg <msgId>] --to --cc --subject (--body\|--body-file) [--attach a,b]` | Create a draft; threads correctly when replying |
| `send ...` | Same flags as `draft`, or `send --draft <draftId>` |
| `label <msgId> [--add L1,L2] [--remove L1,L2]` | `--remove UNREAD` to mark read, `--remove INBOX` to archive, `--add STARRED` |

### Scopes, and what the agent deliberately cannot do

`gmail.modify` + `gmail.send`. **No permanent-delete scope is requested.** The worst a bad
instruction can do is archive something. Revoke any time at
[myaccount.google.com/permissions](https://myaccount.google.com/permissions) and delete
`token.json` — that is the entire kill switch.

The skill's own convention (see [SKILL.md](SKILL.md)) is **default to `draft`, never `send`**.
The agent composes; a human reads it and hits send. Cheap rule, and it is the one that lets
you leave this thing switched on.

## Worked example: online flight check-in, end to end

The task: check two elderly relatives in for their flight — El Al, Zagreb → Tel Aviv,
one of them travelling with wheelchair assistance. The booking confirmation was somewhere in
a mailbox with tens of thousands of messages.

Neither tool can do this alone. Gmail has the booking reference and cannot open a check-in
form; the browser can drive the form and has no idea what the booking reference is.

```
1. search   "El Al OR elal OR אל על newer_than:30d"     → the confirmation email
2. read     <msgId>                                     → PNR, ticket no., flight no.,
                                                          route, scheduled departure
3. browser  → airline check-in page, PNR + surname, both passengers selected
4. browser  → verify passenger details, confirm baggage, accept assigned seats, submit
5. search   "from:WebCheckin@<airline> newer_than:1h"   → the boarding-pass email
6. download <msgId> --out ~/Desktop                     → boarding passes, as PDFs, on disk
7. draft    --reply-to-msg <msgId> ...                  → note to the airport special-
                                                          assistance desk, in-thread
```

Steps 1, 2, 5, 6 and 7 are this CLI. Steps 3 and 4 are the browser. The handoff between them
is just text the agent carried across — and that handoff is the whole point.

What the run actually surfaced, which is the part that argues for doing it this way:

- The departure time in the booking email (23:30) did **not** match the check-in system
  (23:50). Two sources, compared, discrepancy caught.
- One boarding pass came back with a **blank seat field** while the other had a seat.
- The wheelchair-assistance flag did **not** appear on the boarding pass at all — which is
  exactly the thing you want to discover the day before, not at the gate. Hence step 7:
  a threaded reply to the airport's assistance desk, drafted for review, asking them to
  confirm.

A human doing this is unlikely to diff two departure times or notice a missing SSR code on a
PDF. That is not because the agent is clever; it is because reading carefully is boring and
software does not get bored.

## Other things the same seven commands cover

The command set is small on purpose. Almost every real request decomposes into
search → read → (download | draft):

- **"Find the invoice from the freight forwarder and file it."** `search has:attachment
  from:...` → `download` → hand the PDF to whatever does the bookkeeping.
- **"Did they ever answer?"** `search` a thread, `read` the last message, `draft` the chase.
- **"Reply to this in Hebrew/Croatian."** Body written to a file, `--body-file` — no shell
  quoting nightmare, no mangled UTF-8, no RTL surprises.
- **"Watch for their reply and ping me."** `search ... is:unread newer_than:1d` on a cron or
  a loop, and a notification when it hits.
- **Inbox triage.** `search`, then `label --remove INBOX` on the noise, `--add STARRED` on
  what needs a human.

## Requirements

Python 3.9+, and:

```
google-api-python-client
google-auth-oauthlib
google-auth-httplib2
```

## Files

| File | |
|---|---|
| `gmail_cli.py` | The whole thing |
| `SKILL.md` | Claude Code skill definition — when to use it, conventions |
| `SETUP.md` | Google Cloud OAuth walkthrough + troubleshooting |
| `credentials.json` | **Yours. Never committed.** OAuth Desktop client from Google Cloud |
| `token.json` | **Yours. Never committed.** Written by `auth`, mode 600, auto-refreshes |
| `ca-bundle.pem` | Optional, only for TLS-intercepting networks. See SETUP.md |

## Licence

MIT.
