#!/usr/bin/env python3
"""Gmail CLI - review / draft / attach / send via the Gmail API.

Auth: OAuth desktop flow. Needs credentials.json (OAuth client) beside this
file; token.json is created on first `auth` and auto-refreshes after.

Optional: if a `ca-bundle.pem` sits beside this file, every TLS layer is
pointed at it. Only needed on networks that intercept TLS (corporate proxy,
some VPNs), where the default CA store fails. See README.
"""
import argparse, base64, json, mimetypes, os, sys
from email.message import EmailMessage
from pathlib import Path

HERE = Path(__file__).resolve().parent
CA = HERE / "ca-bundle.pem"
CREDS = HERE / "credentials.json"
TOKEN = HERE / "token.json"

# Point every TLS layer (requests/oauthlib, httplib2, ssl) at our bundle.
if CA.exists():
    os.environ.setdefault("SSL_CERT_FILE", str(CA))
    os.environ.setdefault("REQUESTS_CA_BUNDLE", str(CA))

import httplib2
import google_auth_httplib2
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",  # read, search, draft, labels
    "https://www.googleapis.com/auth/gmail.send",    # send
]


def _http():
    return httplib2.Http(ca_certs=str(CA) if CA.exists() else None, timeout=30)


def service():
    creds = None
    if TOKEN.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDS.exists():
                sys.exit(f"Missing {CREDS}. Create an OAuth Desktop client in Google "
                         f"Cloud Console, download it, and save it there.")
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDS), SCOPES)
            creds = flow.run_local_server(port=0, prompt="consent")
        TOKEN.write_text(creds.to_json())
        os.chmod(TOKEN, 0o600)
    return build("gmail", "v1", http=google_auth_httplib2.AuthorizedHttp(creds, http=_http()))


# ---------- helpers ----------
def _hdr(msg, name):
    for h in msg.get("payload", {}).get("headers", []):
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


def _walk(part, out):
    if part.get("parts"):
        for p in part["parts"]:
            _walk(p, out)
    mt = part.get("mimeType", "")
    body = part.get("body", {})
    if part.get("filename"):
        out["attachments"].append({"filename": part["filename"], "mimeType": mt,
                                    "attachmentId": body.get("attachmentId"),
                                    "size": body.get("size")})
    elif mt == "text/plain" and body.get("data"):
        out["text"] += base64.urlsafe_b64decode(body["data"]).decode("utf-8", "replace")
    elif mt == "text/html" and body.get("data") and not out["text"]:
        out["html"] += base64.urlsafe_b64decode(body["data"]).decode("utf-8", "replace")


def _parse(msg):
    out = {"text": "", "html": "", "attachments": []}
    _walk(msg.get("payload", {}), out)
    return out


# ---------- commands ----------
def cmd_auth(a):
    service()
    print("Authorized. token.json saved.")


def cmd_search(a):
    svc = service()
    res = svc.users().messages().list(userId="me", q=a.query, maxResults=a.max).execute()
    ids = res.get("messages", [])
    print(f"{len(ids)} message(s) for: {a.query}\n")
    for m in ids:
        full = svc.users().messages().get(userId="me", id=m["id"], format="metadata",
              metadataHeaders=["From", "Date", "Subject"]).execute()
        print(f"[{m['id']}]  {_hdr(full,'Date')}")
        print(f"   From: {_hdr(full,'From')}")
        print(f"   Subj: {_hdr(full,'Subject')}")
        print(f"   {full.get('snippet','')[:140]}")
        print(f"   labels: {','.join(full.get('labelIds',[]))}\n")


def cmd_read(a):
    svc = service()
    msg = svc.users().messages().get(userId="me", id=a.id, format="full").execute()
    p = _parse(msg)
    print(f"From:    {_hdr(msg,'From')}")
    print(f"To:      {_hdr(msg,'To')}")
    print(f"Cc:      {_hdr(msg,'Cc')}")
    print(f"Date:    {_hdr(msg,'Date')}")
    print(f"Subject: {_hdr(msg,'Subject')}")
    print(f"ThreadId:{msg.get('threadId')}  Labels: {','.join(msg.get('labelIds',[]))}")
    if p["attachments"]:
        print("Attachments:")
        for at in p["attachments"]:
            print(f"   - {at['filename']} ({at['mimeType']}, {at['size']} B) id={at['attachmentId']}")
    print("\n----- body -----")
    print(p["text"] or "(no text/plain part; html present)" if p["html"] else p["text"])


def cmd_download(a):
    svc = service()
    msg = svc.users().messages().get(userId="me", id=a.id, format="full").execute()
    outdir = Path(a.out).expanduser(); outdir.mkdir(parents=True, exist_ok=True)
    saved = []
    for at in _parse(msg)["attachments"]:
        if not at["attachmentId"]:
            continue
        data = svc.users().messages().attachments().get(
            userId="me", messageId=a.id, id=at["attachmentId"]).execute()
        raw = base64.urlsafe_b64decode(data["data"])
        dest = outdir / at["filename"]
        dest.write_bytes(raw)
        saved.append(str(dest))
    print("\n".join(saved) if saved else "no attachments")


def _build_mime(a, thread_headers=None):
    em = EmailMessage()
    if a.to: em["To"] = a.to
    if a.cc: em["Cc"] = a.cc
    if a.subject: em["Subject"] = a.subject
    if thread_headers:
        for k, v in thread_headers.items():
            if v and k not in em: em[k] = v
    body = Path(a.body_file).read_text() if a.body_file else (a.body or "")
    em.set_content(body)
    for f in (a.attach or "").split(",") if a.attach else []:
        f = f.strip()
        if not f: continue
        path = Path(f).expanduser()
        ctype, _ = mimetypes.guess_type(path)
        maintype, subtype = (ctype or "application/octet-stream").split("/", 1)
        em.add_attachment(path.read_bytes(), maintype=maintype, subtype=subtype,
                          filename=path.name)
    return em


def _thread_ctx(svc, reply_to_msg):
    """Return (threadId, {To, In-Reply-To, References, Subject}) for a reply."""
    msg = svc.users().messages().get(userId="me", id=reply_to_msg, format="metadata",
          metadataHeaders=["Message-ID", "References", "Subject", "From", "To"]).execute()
    mid = _hdr(msg, "Message-ID"); refs = _hdr(msg, "References")
    subj = _hdr(msg, "Subject")
    if subj and not subj.lower().startswith("re:"):
        subj = "Re: " + subj
    # ponytail: reply to the sender; if that's us (replying to our own sent mail), reply to its To.
    to = _hdr(msg, "From")
    if "SENT" in msg.get("labelIds", []): to = _hdr(msg, "To")
    return msg["threadId"], {"To": to, "In-Reply-To": mid,
                             "References": (refs + " " + mid).strip(), "Subject": subj}


def cmd_draft(a):
    svc = service()
    thread_id, th = (None, None)
    if a.reply_to_msg:
        thread_id, th = _thread_ctx(svc, a.reply_to_msg)
        if a.subject is None: a.subject = th["Subject"]
    em = _build_mime(a, th)
    raw = base64.urlsafe_b64encode(em.as_bytes()).decode()
    msg = {"raw": raw}
    if thread_id: msg["threadId"] = thread_id
    d = svc.users().drafts().create(userId="me", body={"message": msg}).execute()
    print(f"draft created: draftId={d['id']} messageId={d['message']['id']}"
          f"{' thread='+thread_id if thread_id else ''}")


def cmd_send(a):
    svc = service()
    if a.draft:
        r = svc.users().drafts().send(userId="me", body={"id": a.draft}).execute()
        print(f"sent draft {a.draft}: id={r['id']} thread={r.get('threadId')}")
        return
    thread_id, th = (None, None)
    if a.reply_to_msg:
        thread_id, th = _thread_ctx(svc, a.reply_to_msg)
        if a.subject is None: a.subject = th["Subject"]
    em = _build_mime(a, th)
    raw = base64.urlsafe_b64encode(em.as_bytes()).decode()
    msg = {"raw": raw}
    if thread_id: msg["threadId"] = thread_id
    r = svc.users().messages().send(userId="me", body=msg).execute()
    print(f"sent: id={r['id']} thread={r.get('threadId')}")


def cmd_label(a):
    svc = service()
    body = {}
    if a.add: body["addLabelIds"] = a.add.split(",")
    if a.remove: body["removeLabelIds"] = a.remove.split(",")
    svc.users().messages().modify(userId="me", id=a.id, body=body).execute()
    print(f"modified {a.id}: {body}")


def main():
    ap = argparse.ArgumentParser(prog="gmail", description="Gmail review/draft/send CLI")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("auth").set_defaults(func=cmd_auth)

    s = sub.add_parser("search"); s.add_argument("query"); s.add_argument("--max", type=int, default=15)
    s.set_defaults(func=cmd_search)

    s = sub.add_parser("read"); s.add_argument("id"); s.set_defaults(func=cmd_read)

    s = sub.add_parser("download"); s.add_argument("id"); s.add_argument("--out", default=".")
    s.set_defaults(func=cmd_download)

    for name in ("draft", "send"):
        s = sub.add_parser(name)
        s.add_argument("--to", default="")
        s.add_argument("--cc", default="")
        s.add_argument("--subject", default=None)
        s.add_argument("--body", default=None)
        s.add_argument("--body-file", dest="body_file", default=None)
        s.add_argument("--attach", default=None, help="comma-separated file paths")
        s.add_argument("--reply-to-msg", dest="reply_to_msg", default=None,
                       help="messageId to reply within its thread")
        if name == "send":
            s.add_argument("--draft", default=None, help="send an existing draftId")
        s.set_defaults(func=cmd_draft if name == "draft" else cmd_send)

    s = sub.add_parser("label"); s.add_argument("id")
    s.add_argument("--add", default=""); s.add_argument("--remove", default="")
    s.set_defaults(func=cmd_label)

    a = ap.parse_args()
    try:
        a.func(a)
    except HttpError as e:
        sys.exit(f"Gmail API error: {e}")


if __name__ == "__main__":
    main()
