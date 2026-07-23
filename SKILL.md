---
name: gmail
description: Review, search, read, draft, attach, send, and label Gmail programmatically via the Gmail API (no browser automation). Use whenever the user wants to check email, find a message/thread, read a message or its attachments, draft or reply to an email (with attachments), send email, or label/archive. Prefer this over any browser-based Gmail approach.
---

# gmail

Local CLI over the Gmail API. Replaces fragile browser automation for email.
All commands: `python3 ~/.claude/skills/gmail/gmail_cli.py <cmd>`.

## Setup (one time)
1. `credentials.json` (OAuth Desktop client) must sit in this skill dir. See `SETUP.md`.
2. `python3 ~/.claude/skills/gmail/gmail_cli.py auth` → opens a browser once; user clicks Allow. Saves `token.json` (auto-refreshes after).

## Commands
- `search "<gmail query>" [--max N]` — list matches (msgId, from, date, subject, snippet, labels). Query is normal Gmail search syntax, e.g. `from:airline.com`, `subject:invoice newer_than:2d`, `has:attachment`.
- `read <msgId>` — headers + text body + attachment list (with attachmentIds).
- `download <msgId> [--out DIR]` — save all attachments (default cwd).
- `draft [--reply-to-msg <msgId>] --to a@b --cc c@d --subject "..." (--body "..."|--body-file f) [--attach f1,f2]` — create a draft. With `--reply-to-msg`, it threads the reply and auto-sets Re: subject/In-Reply-To (omit --to/--subject to inherit).
- `send ...` — same flags as draft, OR `send --draft <draftId>` to send an existing draft.
- `label <msgId> [--add L1,L2] [--remove L1,L2]` — e.g. `--remove UNREAD` (mark read), `--add STARRED`, `--remove INBOX` (archive).

## Conventions
- **Default to `draft`, not `send`.** Prepare the email and let the user review and hit send, or explicitly ask before sending. Nothing leaves the mailbox without a human OK.
- Write bodies to a file and use `--body-file` for multi-line / non-ASCII (Hebrew, Croatian diacritics) safety.
- To reply within a thread, pass the target `--reply-to-msg <msgId>` (get the msgId from `search`).

## Scopes
`gmail.modify` (read/search/draft/labels) + `gmail.send`. No permanent-delete scope — the agent cannot destroy mail.
