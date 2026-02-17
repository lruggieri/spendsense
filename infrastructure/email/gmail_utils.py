"""Gmail utility functions for handling message IDs."""

import base64
import html
import re
from typing import Optional


def decode_gmail_ui_message_id(ui_id: str) -> Optional[str]:
    """
    Convert a Gmail UI message ID to a Gmail API message ID.

    Gmail uses different ID formats:
    - UI format: FMfcgzQfBGfsVHzgNPZvccFHwCmhpvCQ (from URL)
    - API format: 18c2a3b4e5f6g7h8 (hexadecimal)

    This function converts UI format to API format using the decoding algorithm
    from Arsenal Recon's Gmail URL Decoder.

    Args:
        ui_id: Gmail UI message ID (from URL fragment)

    Returns:
        Gmail API message ID, or None if decoding fails

    References:
        https://github.com/ArsenalRecon/GmailURLDecoder
        https://arsenalrecon.com/insights/digging-deeper-into-gmail-urls-and-introducing-gmail-url-decoder
    """
    charset_full = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
    charset_reduced = "BCDFGHJKLMNPQRSTVWXZbcdfghjklmnpqrstvwxz"

    try:
        # Transform from reduced charset to full base64 charset
        transformed = _transform_charset(ui_id, charset_reduced, charset_full)

        # Add base64 padding
        padding = "=" * (-len(transformed) % 4)

        # Decode base64
        decoded = base64.b64decode(transformed + padding).decode("utf-8")

        # Extract message ID from decoded string
        # Format is typically "msg-f:DECIMAL" or "f:DECIMAL"
        # The number is in decimal format and needs to be converted to hex
        match = re.search(r"(?:msg-)?([a-z]):(\d+)", decoded)
        if match:
            decimal_id = match.group(2)
            # Convert decimal to hexadecimal (Gmail API expects hex format)
            hex_id = hex(int(decimal_id))[2:]  # [2:] removes '0x' prefix
            return hex_id

        # If no prefix found, return the decoded string as-is
        return decoded.strip()

    except Exception:
        # If decoding fails, return None
        return None


def _transform_charset(token: str, charset_in: str, charset_out: str) -> str:
    """
    Transform a token from one character set to another.

    This implements the character set transformation algorithm used by Gmail
    to convert between the reduced consonant-only charset and standard base64.

    Args:
        token: Input string to transform
        charset_in: Input character set
        charset_out: Output character set

    Returns:
        Transformed string
    """
    size_str = len(token)
    size_in = len(charset_in)
    size_out = len(charset_out)

    # Build character to index mapping
    alph_map = {}
    for i in range(size_in):
        alph_map[charset_in[i]] = i

    # Convert input string to indices (reversed)
    in_str_idx = []
    for i in reversed(range(size_str)):
        chr = token[i]
        idx = alph_map[chr]
        in_str_idx.append(idx)

    # Transform indices from input base to output base
    out_str_idx = []
    for i in reversed(range(len(in_str_idx))):
        offset = 0

        # Process existing output indices
        for j in range(len(out_str_idx)):
            idx = size_in * out_str_idx[j] + offset
            if idx >= size_out:
                rest = idx % size_out
                offset = (idx - rest) // size_out
                idx = rest
            else:
                offset = 0
            out_str_idx[j] = idx

        # Add new output indices for remaining offset
        while offset:
            rest = offset % size_out
            out_str_idx.append(rest)
            offset = (offset - rest) // size_out

        # Add current input digit
        offset = in_str_idx[i]
        j = 0
        while offset:
            if j >= len(out_str_idx):
                out_str_idx.append(0)
            idx = out_str_idx[j] + offset
            if idx >= size_out:
                rest = idx % size_out
                offset = (idx - rest) // size_out
                idx = rest
            else:
                offset = 0
            out_str_idx[j] = idx
            j += 1

    # Convert output indices to characters (reversed)
    out_buff = []
    for i in reversed(range(len(out_str_idx))):
        idx = out_str_idx[i]
        out_buff.append(charset_out[idx])

    return "".join(out_buff)


def normalize_gmail_message_id(message_id: str) -> str:
    """
    Normalize a Gmail message ID to API format.

    Accepts both UI format (from URL) and API format (hexadecimal).
    Returns the API-compatible format.

    Args:
        message_id: Gmail message ID in either format

    Returns:
        API-compatible message ID
    """
    # Strip whitespace
    message_id = message_id.strip()

    # If it looks like a UI ID (contains only consonants from the reduced charset),
    # try to decode it
    charset_reduced = "BCDFGHJKLMNPQRSTVWXZbcdfghjklmnpqrstvwxz"
    if all(c in charset_reduced for c in message_id):
        decoded = decode_gmail_ui_message_id(message_id)
        if decoded:
            return decoded

    # Otherwise, assume it's already in API format
    return message_id


def get_body_from_message(msg):
    """
    Extract text body from Gmail message.

    Tries to extract text/plain first, falls back to text/html if needed.
    HTML tags are stripped to get plain text.

    Args:
        msg: Gmail API message object (dict with 'payload' key)

    Returns:
        Extracted text body or None if extraction fails
    """

    def extract_text_by_mime(part, mime_type):
        """Extract text content by MIME type."""
        if part["mimeType"] == mime_type and "data" in part["body"]:
            text = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8")
            return text
        if "parts" in part:
            for subpart in part["parts"]:
                result = extract_text_by_mime(subpart, mime_type)
                if result:
                    return result
        return None

    def strip_html_tags(html_text):
        """Simple HTML tag stripper for extracting text from HTML."""
        # Remove style and script blocks (including their content)
        text = re.sub(r"<style[^>]*>.*?</style>", "", html_text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL | re.IGNORECASE)
        # Remove HTML tags
        text = re.sub(r"<[^>]+>", "", text)
        # Decode HTML entities (handles all named and numeric entities)
        text = html.unescape(text)
        # Normalize whitespace
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    # Try to extract text/plain first (preferred)
    plain_text = None
    if "parts" in msg["payload"]:
        plain_text = extract_text_by_mime(msg["payload"], "text/plain")
    elif msg["payload"].get("mimeType") == "text/plain" and "data" in msg["payload"]["body"]:
        plain_text = base64.urlsafe_b64decode(msg["payload"]["body"]["data"]).decode("utf-8")

    if plain_text:
        # Check if "plain text" is actually HTML (some senders put HTML in text/plain)
        plain_text_stripped = plain_text.strip()
        if plain_text_stripped.startswith(
            ("<!DOCTYPE", "<!doctype", "<html", "<HTML", "<head", "<HEAD")
        ):
            return strip_html_tags(plain_text)
        # Decode HTML entities even in plain text (some senders encode entities in text/plain)
        return html.unescape(plain_text)

    # Fall back to text/html if no plain text available
    html_text = None
    if "parts" in msg["payload"]:
        html_text = extract_text_by_mime(msg["payload"], "text/html")
    elif msg["payload"].get("mimeType") == "text/html" and "data" in msg["payload"]["body"]:
        html_text = base64.urlsafe_b64decode(msg["payload"]["body"]["data"]).decode("utf-8")

    if html_text:
        return strip_html_tags(html_text)

    return None
