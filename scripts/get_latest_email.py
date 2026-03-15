#!/usr/bin/env python3
"""Fetch the latest email from an IMAP mailbox and print a JSON summary.

Usage (env vars):
  EMAIL_HOST, EMAIL_PORT, EMAIL_USER, EMAIL_PASS, MAILBOX (optional, default INBOX), IMAP_USE_SSL (optional: 1/true)

Or CLI:
  python3 scripts/get_latest_email.py --host imap.example.com --user me@example.com --password SECRET --ssl

Outputs JSON with keys: subject, from, date, snippet, body_raw (only with --full)
"""
import imaplib
import os
import argparse
import email
from email import policy
import json
import sys


def _get_env_or_arg(env, arg):
    return arg if arg is not None else os.environ.get(env)


def fetch_latest_email(host, port, user, password, mailbox='INBOX', use_ssl=True, full=False, timeout=30):
    # Connect
    try:
        if use_ssl:
            M = imaplib.IMAP4_SSL(host, port)
        else:
            M = imaplib.IMAP4(host, port)
    except Exception as e:
        raise RuntimeError(f"Failed to connect to IMAP server: {e}")

    try:
        M.login(user, password)
    except imaplib.IMAP4.error as e:
        M.logout()
        raise RuntimeError(f"IMAP login failed: {e}")

    try:
        typ, data = M.select(mailbox, readonly=True)
        if typ != 'OK':
            raise RuntimeError(f"Cannot select mailbox {mailbox}: {data}")

        # Search all messages and take the last one
        typ, data = M.search(None, 'ALL')
        if typ != 'OK':
            raise RuntimeError(f"Search failed: {data}")

        ids = data[0].split()
        if not ids:
            return None

        latest_id = ids[-1]
        typ, msg_data = M.fetch(latest_id, '(RFC822)')
        if typ != 'OK':
            raise RuntimeError(f"Fetch failed: {msg_data}")

        # msg_data is a list of tuples; find bytes
        raw = None
        for part in msg_data:
            if isinstance(part, tuple) and part[1] is not None:
                raw = part[1]
                break
        if raw is None:
            raise RuntimeError("No message content found")

        msg = email.message_from_bytes(raw, policy=policy.default)

        # Extract headers
        subject = str(msg['subject']) if msg['subject'] is not None else ''
        from_ = str(msg['from']) if msg['from'] is not None else ''
        date = str(msg['date']) if msg['date'] is not None else ''

        # Extract body: prefer text/plain
        body = None
        if msg.is_multipart():
            for part in msg.walk():
                ctype = part.get_content_type()
                disp = str(part.get_content_disposition() or '')
                if ctype == 'text/plain' and disp != 'attachment':
                    try:
                        body = part.get_content()
                        break
                    except Exception:
                        body = part.get_payload(decode=True).decode(part.get_content_charset() or 'utf-8', errors='replace')
                # fallback to first text/* non-attachment
                if body is None and ctype.startswith('text/') and disp != 'attachment':
                    try:
                        body = part.get_content()
                    except Exception:
                        body = part.get_payload(decode=True).decode(part.get_content_charset() or 'utf-8', errors='replace')
        else:
            try:
                body = msg.get_content()
            except Exception:
                body = msg.get_payload(decode=True).decode(msg.get_content_charset() or 'utf-8', errors='replace')

        snippet = ''
        if body:
            snippet = ' '.join(body.strip().split())[:500]

        out = {
            'subject': subject,
            'from': from_,
            'date': date,
            'snippet': snippet,
        }
        if full:
            out['body_raw'] = body

        return out

    finally:
        try:
            M.logout()
        except Exception:
            pass


def main():
    p = argparse.ArgumentParser(description='Fetch latest email from IMAP')
    p.add_argument('--host', help='IMAP host')
    p.add_argument('--port', type=int, help='IMAP port')
    p.add_argument('--user', help='Username/email')
    p.add_argument('--password', help='Password')
    p.add_argument('--mailbox', default=None, help='Mailbox name (default INBOX)')
    p.add_argument('--no-ssl', action='store_true', help='Disable SSL (use plain IMAP)')
    p.add_argument('--full', action='store_true', help='Include full body in output')
    args = p.parse_args()

    host = _get_env_or_arg('EMAIL_HOST', args.host)
    port = _get_env_or_arg('EMAIL_PORT', args.port)
    user = _get_env_or_arg('EMAIL_USER', args.user)
    password = _get_env_or_arg('EMAIL_PASS', args.password)
    mailbox = _get_env_or_arg('MAILBOX', args.mailbox) or 'INBOX'
    env_ssl = os.environ.get('IMAP_USE_SSL', '').lower() in ('1', 'true', 'yes')
    use_ssl = (not args.no_ssl) and env_ssl if (args.no_ssl or os.environ.get('IMAP_USE_SSL') is not None) else (not args.no_ssl)

    # reasonable defaults
    if host is None or user is None or password is None:
        print('Missing credentials: provide EMAIL_HOST, EMAIL_USER, and EMAIL_PASS via env or CLI', file=sys.stderr)
        sys.exit(2)

    if port is None:
        port = 993 if use_ssl else 143
    else:
        port = int(port)

    try:
        result = fetch_latest_email(host, port, user, password, mailbox=mailbox, use_ssl=use_ssl, full=args.full)
    except Exception as e:
        print(f'Error: {e}', file=sys.stderr)
        sys.exit(3)

    if result is None:
        print(json.dumps({'message': 'No messages found'}))
    else:
        print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
