"""
Secrets at rest: the bank account number and the Aadhaar number of a student are never written
to the database in plain text. Standard library only.

The key is 64 random bytes: the first half seals, the second half authenticates and makes the
look-up values. It comes from the setting KTS_STIPEND_KEY (128 hex digits, environment or
instance/portal.env) or, without that setting, from the file instance/stipend.key, which is
made at first need. Without a key nothing is sealed: the caller gets NoKey and stores nothing.

The database and the key belong together in every backup: without the key the numbers cannot
be read again. Once entries are stored, the key is bound to them (kts/stipend.py _seal): the
setting, if used, must hold the same key as instance/stipend.key, written as its 128 hex
digits, and under any other key the portal accepts no entry.
"""
import base64
import hashlib
import hmac
import os
import secrets
import threading
from pathlib import Path

from flask import current_app

from config import _env

KEY_FILE = "stipend.key"
KEY_SETTING = "KTS_STIPEND_KEY"
KEY_BYTES = 64
VERSION = "v1"
NONCE_BYTES = 16
TAG_BYTES = 32

# one key file is made by one thread only
_lock = threading.Lock()


class NoKey(ValueError):
    """There is no key and none can be made: nothing may be stored."""


def key_file():
    return Path(current_app.config["INSTANCE_DIR"]) / KEY_FILE


def _from_hex(text):
    """The key written as 128 hex digits, or None."""
    text = "".join(text.split())
    if len(text) != 2 * KEY_BYTES:
        return None
    try:
        return bytes.fromhex(text)
    except ValueError:
        return None


def _read(path):
    """The key of the file: 64 bytes as they are, or the same written as 128 hex digits."""
    raw = path.read_bytes()
    if len(raw) == KEY_BYTES:
        return raw
    try:
        return _from_hex(raw.decode("ascii"))
    except ValueError:
        return None


def _key(create=True):
    """
    (seal key, authentication key). The setting wins over the file. A key that is named but
    cannot be used is never replaced by another one: what was sealed before would be lost.
    """
    named = _env(KEY_SETTING)
    if named:
        key = _from_hex(str(named))
        if key is None:
            # the name, never the value
            current_app.logger.error("%s cannot be used: it must be %d hex digits.", KEY_SETTING, 2 * KEY_BYTES)
            raise NoKey("setting")
        return key[:32], key[32:]
    path = key_file()
    with _lock:
        try:
            key = _read(path)
        except FileNotFoundError:
            key = None
            if not create:
                raise NoKey("missing") from None
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                made = secrets.token_bytes(KEY_BYTES)
                # the key is written whole under a name of its own and only then named stipend.key:
                # no other process reads a file that is empty or half written, and a write that
                # fails leaves no stipend.key behind
                temp = path.with_name(f"{KEY_FILE}.{secrets.token_hex(8)}.tmp")
                handle = os.open(str(temp), os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)
                try:
                    with os.fdopen(handle, "wb") as fh:
                        fh.write(made)
                        fh.flush()
                        os.fsync(fh.fileno())
                    # never over a file that is there: the link fails when another process was faster
                    # (os.rename would replace an existing key on other systems than Windows)
                    os.link(temp, path)
                finally:
                    try:
                        temp.unlink()
                    except OSError:
                        pass
                # what is used is what the file holds
                key = _read(path)
                if key != made:
                    key = None
                else:
                    current_app.logger.warning("The key of the stipend module was made: %s. Keep this file "
                                               "with every backup of the database.", path)
            except FileExistsError:
                try:
                    key = _read(path)
                except OSError:
                    key = None
            except OSError as exc:
                current_app.logger.error("%s cannot be written (%s).", path, exc)
                raise NoKey("unwritable") from None
        except OSError as exc:
            current_app.logger.error("%s cannot be read (%s).", path, exc)
            raise NoKey("unreadable") from None
    if key is None:
        current_app.logger.error("%s holds no key of %d bytes. It is left as it is.", path, KEY_BYTES)
        raise NoKey("damaged")
    return key[:32], key[32:]


def have_key():
    """True when a key can be read now. Nothing is made."""
    try:
        _key(create=False)
    except NoKey:
        return False
    return True


def _stream(seal_key, nonce, length):
    """Block i of the key stream is HMAC-SHA256(seal key, nonce + i as 8 bytes)."""
    out = b""
    i = 0
    while len(out) < length:
        out += hmac.new(seal_key, nonce + i.to_bytes(8, "big"), hashlib.sha256).digest()
        i += 1
    return out[:length]


def _tag(auth_key, nonce, sealed):
    return hmac.new(auth_key, VERSION.encode("ascii") + nonce + sealed, hashlib.sha256).digest()


def seal(text):
    """'v1.' + urlsafe base64 of nonce + sealed text + tag. Two seals of one text differ."""
    seal_key, auth_key = _key()
    plain = str(text).encode("utf-8")
    nonce = secrets.token_bytes(NONCE_BYTES)
    sealed = bytes(a ^ b for a, b in zip(plain, _stream(seal_key, nonce, len(plain))))
    token = base64.urlsafe_b64encode(nonce + sealed + _tag(auth_key, nonce, sealed)).decode("ascii")
    return f"{VERSION}.{token}"


def unseal(token):
    """The text of a seal. ValueError when the seal is damaged, changed or made with another key."""
    if not isinstance(token, str) or not token.startswith(VERSION + "."):
        raise ValueError("not a seal")
    seal_key, auth_key = _key(create=False)
    try:
        raw = base64.b64decode(token[len(VERSION) + 1:].encode("ascii"), altchars=b"-_", validate=True)
    except ValueError:  # binascii.Error and UnicodeEncodeError are ValueErrors
        raise ValueError("not a seal") from None
    if len(raw) < NONCE_BYTES + TAG_BYTES:
        raise ValueError("not a seal")
    nonce, sealed, tag = raw[:NONCE_BYTES], raw[NONCE_BYTES:-TAG_BYTES], raw[-TAG_BYTES:]
    # the tag is compared before anything is opened
    if not hmac.compare_digest(tag, _tag(auth_key, nonce, sealed)):
        raise ValueError("the seal is broken")
    plain = bytes(a ^ b for a, b in zip(sealed, _stream(seal_key, nonce, len(sealed))))
    return plain.decode("utf-8")


def lookup(text):
    """
    A value that is the same for the same text and says nothing about it without the key:
    two students who give one account are found without reading the numbers.
    """
    _seal_key, auth_key = _key()
    return hmac.new(auth_key, b"lookup|" + str(text).encode("utf-8"), hashlib.sha256).hexdigest()


# ---- display ------------------------------------------------------------------

def mask(last4, shown_length=10):
    """'XXXXXX1234': the last digits behind a row of X, always of the same length."""
    last4 = str(last4 or "")
    return "X" * max(shown_length - len(last4), 0) + last4


def mask_account(last4):
    return mask(last4, 10)


def mask_aadhaar(last4):
    """'XXXX XXXX 1234'; nothing for an entry without an Aadhaar number."""
    return f"XXXX XXXX {last4}" if last4 else ""
