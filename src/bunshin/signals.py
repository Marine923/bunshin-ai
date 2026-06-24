"""Signal scoring + sender extraction for the learning-based noise filter.

`signal_score` is a 0-100 readability/signal value Bunshin assigns to every
record so it can sort the user's flashbacks and search results by "worth
re-reading" instead of raw timestamp. Higher = more likely to be human-
written content the user actually wants to see again.

The scoring is deliberately simple — a handful of hand-tuned heuristics
that can be re-run on the whole DB in seconds. The downstream filter
(case-by-case "this is noise" marking, plus `learning_rules`) does the
heavy lifting; the score just gives the user a reasonable default order
before they teach Bunshin anything.
"""
from __future__ import annotations

import json
import re
from typing import Optional, Tuple

URL_RE = re.compile(r'https?://\S+')
SENDER_ADDR_RE = re.compile(r'<([^>]+)>')
EMAIL_RE = re.compile(r'[\w\.\-+]+@[\w\.\-]+')

# Stuff we want to strip from a record before showing it to the user.
# Anchored to start-of-line so we don't accidentally chew up a Subject:
# that happens to appear mid-sentence in legitimate text.
_HEADER_LINE_RE = re.compile(
    r'^(?:Subject|From|To|Cc|Bcc|Date|Reply-To|Content-Type|Content-Transfer-Encoding|MIME-Version|X-[\w\-]+|List-Unsubscribe(?:-Post)?|Return-Path|Received|Message-ID|DKIM-Signature|ARC-[\w\-]+|Authentication-Results|Feedback-ID|Precedence)\s*:\s*[^\n]*\n?',
    re.MULTILINE | re.IGNORECASE,
)
# Run of 32+ chars with no whitespace and at least one digit — almost
# always a tracking ID, base64 chunk, or URL fragment. The digit guard
# keeps real Japanese / English words safe (very long compound words
# rarely contain digits in running text).
_LONG_NOISE_RE = re.compile(r'(?<![\w])[\w\-+/=]{0,5}\d[\w\-+/=\.~]{30,}(?![\w])')
_HTML_TAG_RE = re.compile(r'<[^>]+>')
# Empty paren/bracket pairs left behind after URL removal — both ASCII
# and full-width Japanese variants.
_EMPTY_PAREN_RE = re.compile(r'[\(\[【（［「『][\s　]*[\)\]】）］」』]')
# 3+ runs of any non-word, non-whitespace symbol (▲▲▲▲ / ─── / *** / === etc.).
# Whitespace is excluded so we don't accidentally eat consecutive newlines
# that other passes rely on to detect paragraph breaks.
_REPEATED_SYMBOL_RE = re.compile(r'([^\w\s])\1{2,}')
# Dashes / underscores / equals signs used as separator lines
_DECOR_LINE_RE = re.compile(r'^[\s\-\—\─\━\=_\*\.\+\|\#\▲\▼\◆\◇\■\□\●\○\★\☆]{3,}$', re.MULTILINE)
# Trailing leftover punctuation after URL removal: " ） " " ） )" etc.
_DANGLING_PUNCT_RE = re.compile(r'^[\s\)\]\}\）\】\］\」\』]{1,}$', re.MULTILINE)
_LEADING_WS_RE = re.compile(r'\n[ \t　]+')
_SOFT_BREAK_RE = re.compile(r'[ \t]+')
# Collapse ALL multi-newline runs to a single newline. We deliberately
# don't preserve paragraph breaks because the source data (HTML email
# bodies dumped to text) has dozens of blank lines per "paragraph" and
# trying to recover meaningful structure is a lost cause — denser is
# better for readability.
_MULTI_NEWLINE_RE = re.compile(r'(\n[\s　]*){2,}')


def clean_for_display(content: str) -> str:
    """Strip tracking codes, mail headers, HTML tags, decoration lines,
    and empty leftover punctuation. Returns the cleaned content, or ''
    if almost nothing readable remains.
    """
    if not content:
        return ""
    s = content
    s = URL_RE.sub("", s)
    s = _HEADER_LINE_RE.sub("", s)
    s = _LONG_NOISE_RE.sub("", s)
    s = _HTML_TAG_RE.sub("", s)
    s = _EMPTY_PAREN_RE.sub("", s)
    s = _DECOR_LINE_RE.sub("", s)
    s = _REPEATED_SYMBOL_RE.sub("", s)
    s = _DANGLING_PUNCT_RE.sub("", s)
    s = _SOFT_BREAK_RE.sub(" ", s)
    s = _LEADING_WS_RE.sub("\n", s)
    s = _MULTI_NEWLINE_RE.sub("\n", s)
    return s.strip()


def is_readable(content: str, min_chars: int = 50) -> bool:
    """Cheap test: is there enough actual text here to bother showing?

    Raised from 30 → 50 because email-fragment records often clear 30
    via empty parens / Japanese particle scraps that aren't worth seeing.
    """
    cleaned = clean_for_display(content)
    return len(cleaned) >= min_chars

# Local-part patterns that strongly suggest auto-generated mail
NOREPLY_PATTERNS = (
    'noreply', 'no-reply', 'no_reply', 'donotreply', 'do-not-reply',
    'notification', 'notifications', 'auto-confirm', 'mailer',
)
# Domains / substrings that almost always mean bulk marketing email
KNOWN_MARKETING = (
    'mailchimp', 'sendgrid', 'constantcontact', 'amazonses.com',
    'note.com', 'mail.note.com', 'mercari.jp', 'newsletter',
    'campaign-monitor', 'mailerlite', 'klaviyo', 'hubspot',
    'sendinblue', 'brevo', 'getresponse', 'createsend',
)


def extract_sender(metadata_raw) -> Tuple[Optional[str], Optional[str]]:
    """Return (sender_email, sender_domain) from a record's metadata JSON.

    Tolerates both raw JSON strings (as stored in SQLite) and pre-parsed
    dicts. Returns (None, None) if the record has no parseable sender.
    """
    if not metadata_raw:
        return None, None
    if isinstance(metadata_raw, str):
        try:
            m = json.loads(metadata_raw)
        except (ValueError, TypeError):
            return None, None
    else:
        m = metadata_raw
    if not isinstance(m, dict):
        return None, None
    from_field = m.get('from') or m.get('sender') or m.get('From')
    if not from_field or not isinstance(from_field, str):
        return None, None
    # "name <addr@domain>" form takes precedence over a stray address
    addr_match = SENDER_ADDR_RE.search(from_field)
    if addr_match:
        addr = addr_match.group(1).strip().lower()
    else:
        em = EMAIL_RE.search(from_field)
        addr = em.group(0).lower() if em else None
    if not addr or '@' not in addr:
        return None, None
    domain = addr.split('@', 1)[1]
    return addr, domain


# Browser-history entries from passive consumption (video / SNS) flood
# the timeline & flashback with "金のため23匹のヘビが入った寝袋で寝る男達 - YouTube"
# type entries. They're not useless — sometimes you want them — but they
# shouldn't dominate. Lower their default signal so they drop below the
# auto-filter threshold (30) without being deleted.
_PASSIVE_BROWSING_HOSTS = (
    "youtube.com", "youtu.be",
    "x.com", "twitter.com", "t.co",
    "instagram.com",
    "tiktok.com",
    "reddit.com",
    "facebook.com",
    "nicovideo.jp",
)
_PASSIVE_BROWSING_MARKERS = (" - YouTube", " | TikTok", " on X:", " on Twitter:", " | Instagram")


def compute_signal_score(
    content: str,
    source: Optional[str] = None,
    sender: Optional[str] = None,
    domain: Optional[str] = None,
) -> float:
    """Score a record's readability — higher is better.

    Anchors at 50 and moves up/down based on signals. Capped at [0, 100].
    """
    if not content:
        return 0.0
    sample = content[:600]
    n = len(sample) or 1
    score = 50.0

    # Browser entries that are passive media consumption (videos, SNS
    # scrolls) get a heavy penalty so the auto-filter (30) hides them by
    # default. The user can flip the filter off in settings.
    if source == "browser":
        lowered = sample.lower()
        if any(h in lowered for h in _PASSIVE_BROWSING_HOSTS) or \
           any(m in sample for m in _PASSIVE_BROWSING_MARKERS):
            score -= 35

    # Japanese / CJK content is almost always human-written for this user.
    cjk = sum(
        1 for c in sample
        if '぀' <= c <= 'ヿ' or '一' <= c <= '鿿'
    )
    score += (cjk / n) * 30

    # URL spam and tracking pixels hurt readability sharply.
    score -= len(URL_RE.findall(sample)) * 4

    # Unbroken tokens longer than 32 chars are usually hashes/URLs/headers.
    score -= sum(1 for t in sample.split() if len(t) > 32) * 8

    # Raw mail header leakage
    headers = (
        'Subject:', 'From:', 'To:', 'Cc:', 'Content-Type:',
        '=?UTF-8?', 'X-Google-', 'List-Unsubscribe', 'Mime-Version', 'Return-Path:',
    )
    score -= sum(sample.count(h) for h in headers) * 4

    if sender:
        local = sender.split('@', 1)[0]
        if any(p in local for p in NOREPLY_PATTERNS):
            score -= 18
        if any(m in sender for m in KNOWN_MARKETING):
            score -= 20

    # Almost-empty records are usually auto-generated alerts.
    if len(content) < 80:
        score -= 5

    return max(0.0, min(100.0, score))
