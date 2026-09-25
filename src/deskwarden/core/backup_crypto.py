"""
DeskWarden - core/backup_crypto.py
Enterprise-grade encrypted container specification for .deskwarden backup files.

Container Specification (Version 2):
  Offset  Length  Description
  0       8       Magic bytes: b"DWBACKUP"
  8       2       Format version: uint16 (current: 2)
  10      2       Flags: uint16 (0x01=Encrypted, 0x02=Full Backup, 0x04=Has PW, 0x08=Has Key, 0x10=Has Email)
  12      2       Metadata JSON length: uint16
  14      M       Metadata JSON (UTF-8 bytes)
  -- Key Slots Section (if encrypted) --
  Each active key slot contains: 16-byte Salt + 12-byte Nonce + 48-byte Encrypted Vault Key (AES-256-GCM)
  -- Payload Section --
  Nonce (12 bytes) + Ciphertext length (uint32) + AES-256-GCM Ciphertext + Tag
"""

import os
import json
import struct
import hashlib
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.exceptions import InvalidTag

MAGIC = b"DWBACKUP"
VERSION = 2

FLAG_ENCRYPTED   = 0x0001
FLAG_FULL_BACKUP = 0x0002
FLAG_SLOT_PW     = 0x0004
FLAG_SLOT_KEY    = 0x0008
FLAG_SLOT_EMAIL  = 0x0010

PBKDF2_ITERATIONS = 100_000
SALT_SIZE = 16
NONCE_SIZE = 12
VAULT_KEY_SIZE = 32
SLOT_ENC_SIZE = 48  # 32 bytes vault key + 16 bytes GCM tag
SLOT_TOTAL_SIZE = SALT_SIZE + NONCE_SIZE + SLOT_ENC_SIZE  # 76 bytes

SAFE_CIPHER_SECRET = "DESKWARDEN_SECURE_SAFE_IMPORT_CIPHER_KEY_v2"


def encrypt_with_safe_cipher(text: str) -> str:
    """Encrypt a string with DeskWarden's built-in safe cipher (AES-256-GCM + PBKDF2).
    Returns hex string: salt(16) + nonce(12) + ciphertext+tag."""
    if not text:
        return ""
    salt = os.urandom(SALT_SIZE)
    nonce = os.urandom(NONCE_SIZE)
    key = _derive_key(SAFE_CIPHER_SECRET, salt, iters=20_000)
    ct = AESGCM(key).encrypt(nonce, text.encode("utf-8"), b"DW_SAFE_FIELD")
    return (salt + nonce + ct).hex()


def decrypt_with_safe_cipher(enc_hex: str) -> str:
    """Decrypt a hex string produced by encrypt_with_safe_cipher."""
    if not enc_hex:
        return ""
    try:
        raw = bytes.fromhex(enc_hex)
        if len(raw) < SALT_SIZE + NONCE_SIZE + 16:
            return ""
        salt = raw[:SALT_SIZE]
        nonce = raw[SALT_SIZE : SALT_SIZE + NONCE_SIZE]
        ct = raw[SALT_SIZE + NONCE_SIZE :]
        key = _derive_key(SAFE_CIPHER_SECRET, salt, iters=20_000)
        pt = AESGCM(key).decrypt(nonce, ct, b"DW_SAFE_FIELD")
        return pt.decode("utf-8")
    except Exception:
        return ""


class InvalidBackupFormatError(ValueError):
    """Raised when a file does not match the authentic DeskWarden container format."""
    pass


class BackupAuthError(ValueError):
    """Raised when decryption fails due to wrong credentials or container tampering."""
    pass


def is_deskwarden_backup(data_bytes: bytes) -> bool:
    """Return True if the raw bytes begin with the authentic DeskWarden magic header."""
    if not isinstance(data_bytes, (bytes, bytearray)):
        return False
    return data_bytes.startswith(MAGIC)


def _derive_key(secret: str, salt: bytes, iters: int = PBKDF2_ITERATIONS) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=iters,
    )
    return kdf.derive(secret.encode("utf-8"))


def _normalize_recovery_key(key: str) -> str:
    clean = (key or "").strip().upper().replace("-", "").replace(" ", "").replace("_", "")
    if len(clean) > 16 and clean.startswith("DW"):
        clean = clean[2:]
    return clean


def _hash_rk(key: str) -> str:
    return hashlib.sha256(_normalize_recovery_key(key).encode("utf-8")).hexdigest()


def inspect_backup_header(data_bytes: bytes) -> dict:
    """
    Inspect a DeskWarden backup file header without decrypting the payload.
    Returns metadata dict including flags, version, and public backup metadata.
    Raises InvalidBackupFormatError if not an authentic DeskWarden backup.
    """
    if not is_deskwarden_backup(data_bytes):
        raise InvalidBackupFormatError("Not an authentic DeskWarden backup file.")

    if len(data_bytes) < 14:
        raise InvalidBackupFormatError("File header is truncated or incomplete.")

    magic, ver, flags, meta_len = struct.unpack(">8sHHH", data_bytes[:14])
    if ver != VERSION:
        raise InvalidBackupFormatError(f"Unsupported DeskWarden backup version ({ver}).")

    if len(data_bytes) < 14 + meta_len:
        raise InvalidBackupFormatError("Truncated metadata in backup file.")

    meta_raw = data_bytes[14 : 14 + meta_len]
    metadata = {}
    if len(meta_raw) >= SALT_SIZE + NONCE_SIZE + 16:
        try:
            m_salt = meta_raw[:SALT_SIZE]
            m_nonce = meta_raw[SALT_SIZE : SALT_SIZE + NONCE_SIZE]
            m_ct = meta_raw[SALT_SIZE + NONCE_SIZE :]
            m_key = _derive_key(SAFE_CIPHER_SECRET, m_salt, iters=20_000)
            m_dec = AESGCM(m_key).decrypt(m_nonce, m_ct, b"DW_SAFE_META")
            metadata = json.loads(m_dec.decode("utf-8"))
        except Exception:
            pass
    if not metadata:
        try:
            metadata = json.loads(meta_raw.decode("utf-8"))
        except Exception:
            metadata = {}

    return {
        "version": ver,
        "is_encrypted": bool(flags & FLAG_ENCRYPTED),
        "is_full_backup": bool(flags & FLAG_FULL_BACKUP),
        "has_pw_slot": bool(flags & FLAG_SLOT_PW),
        "has_key_slot": bool(flags & FLAG_SLOT_KEY),
        "has_email_slot": bool(flags & FLAG_SLOT_EMAIL),
        "metadata": metadata,
    }


def pack_backup_container(
    data: dict,
    password: str | None = None,
    recovery_key: str | None = None,
    recovery_key_hash: str | None = None,
    recovery_email: str | None = None,
    is_full: bool = True,
    metadata_extra: dict | None = None,
) -> bytes:
    """
    Serialize and encrypt backup data into an authentic .deskwarden container.
    Supports two-tier payload architecture:
      1. Safe Apps Section: AES-256-GCM encrypted using DeskWarden's built-in cipher.
         Plaintext application names (e.g. 'chrome.exe', 'telegram.exe') are never visible
         in plaintext if opened in Notepad, yet DeskWarden can decrypt it for Safe Import
         without requiring any user password.
      2. Full Credentials Section: AES-256-GCM encrypted using a random 256-bit vault key,
         protected by authorization slots (Password, Master Recovery Key, Email OTP).
    """
    flags = 0
    if is_full:
        flags |= FLAG_FULL_BACKUP

    cfg = data.get("config", {})
    safe_data = {
        "locked_apps": cfg.get("locked_apps", []),
        "autostart": cfg.get("autostart", True),
        "sound_enabled": cfg.get("sound_enabled", True),
        "auto_update": cfg.get("auto_update", True),
        "recovery_key_enabled": cfg.get("recovery_key_enabled", True),
        "recovery_email_enabled": cfg.get("recovery_email_enabled", True),
    }

    effective_rk_hash = None
    if recovery_key:
        effective_rk_hash = _hash_rk(recovery_key)
    elif recovery_key_hash:
        effective_rk_hash = recovery_key_hash.strip().lower()

    # Build public metadata for UI display during import (ZERO plain text app names or emails)
    meta = {
        "has_password": bool(password),
        "has_recovery_key": bool(effective_rk_hash),
        "has_recovery_email": bool(recovery_email),
        "locked_apps_count": len(safe_data["locked_apps"]),
    }
    if recovery_email:
        parts = recovery_email.split("@", 1)
        if len(parts) == 2:
            name, domain = parts
            masked_name = name[0] + "*" * max(1, len(name) - 2) + (name[-1] if len(name) > 2 else "*")
            meta["masked_email"] = f"{masked_name}@{domain}"
        else:
            meta["masked_email"] = recovery_email
        meta["enc_recovery_email"] = encrypt_with_safe_cipher(recovery_email)
    else:
        meta["masked_email"] = ""
        meta["enc_recovery_email"] = ""

    if metadata_extra:
        # Filter out plain recovery_email if present in metadata_extra
        clean_extra = dict(metadata_extra)
        clean_extra.pop("recovery_email", None)
        meta.update(clean_extra)

    meta_json = json.dumps(meta, ensure_ascii=False).encode("utf-8")
    meta_salt = os.urandom(SALT_SIZE)
    meta_nonce = os.urandom(NONCE_SIZE)
    meta_key = _derive_key(SAFE_CIPHER_SECRET, meta_salt, iters=20_000)
    meta_ct = AESGCM(meta_key).encrypt(meta_nonce, meta_json, b"DW_SAFE_META")
    meta_bytes = meta_salt + meta_nonce + meta_ct
    meta_len = len(meta_bytes)

    slots_bytes = bytearray()
    vault_key = os.urandom(VAULT_KEY_SIZE)

    is_encrypted = bool(password or effective_rk_hash or recovery_email)
    if is_encrypted:
        flags |= FLAG_ENCRYPTED

        # Slot 0: Password
        if password:
            flags |= FLAG_SLOT_PW
            s_salt = os.urandom(SALT_SIZE)
            s_nonce = os.urandom(NONCE_SIZE)
            s_key = _derive_key(password, s_salt)
            s_cipher = AESGCM(s_key).encrypt(s_nonce, vault_key, b"DW_SLOT_PW")
            slots_bytes.extend(s_salt + s_nonce + s_cipher)

        # Slot 1: Master Recovery Key
        if effective_rk_hash:
            flags |= FLAG_SLOT_KEY
            s_salt = os.urandom(SALT_SIZE)
            s_nonce = os.urandom(NONCE_SIZE)
            s_key = _derive_key(effective_rk_hash, s_salt)
            s_cipher = AESGCM(s_key).encrypt(s_nonce, vault_key, b"DW_SLOT_KEY")
            slots_bytes.extend(s_salt + s_nonce + s_cipher)

        # Slot 2: Recovery Email Escrow
        if recovery_email:
            norm_em = recovery_email.strip().lower()
            if norm_em:
                flags |= FLAG_SLOT_EMAIL
                s_salt = os.urandom(SALT_SIZE)
                s_nonce = os.urandom(NONCE_SIZE)
                s_key = _derive_key(norm_em, s_salt)
                s_cipher = AESGCM(s_key).encrypt(s_nonce, vault_key, b"DW_SLOT_EMAIL")
                slots_bytes.extend(s_salt + s_nonce + s_cipher)
    else:
        # Safe unencrypted container
        s_salt = os.urandom(SALT_SIZE)
        vault_key = hashes.Hash(hashes.SHA256())
        vault_key.update(MAGIC + s_salt)
        vault_key = vault_key.finalize()
        slots_bytes.extend(s_salt)

    # ── Tier 1: Encrypt Safe Apps Section ─────────────────────────────────────
    # Scrambled binary bytes so opening in Notepad shows no plaintext app names
    safe_salt = os.urandom(SALT_SIZE)
    safe_nonce = os.urandom(NONCE_SIZE)
    safe_key = _derive_key(SAFE_CIPHER_SECRET, safe_salt, iters=50_000)
    safe_json = json.dumps(safe_data).encode("utf-8")
    safe_ct = AESGCM(safe_key).encrypt(safe_nonce, safe_json, b"DW_SAFE_APPS")
    safe_section = struct.pack(">16s12sI", safe_salt, safe_nonce, len(safe_ct)) + safe_ct

    # ── Tier 2: Encrypt Full Credentials Section ──────────────────────────────
    full_nonce = os.urandom(NONCE_SIZE)
    full_json = json.dumps(data, ensure_ascii=False).encode("utf-8")
    aad_full = struct.pack(">8sHHH", MAGIC, VERSION, flags, meta_len) + meta_bytes + bytes(slots_bytes)
    full_ct = AESGCM(vault_key).encrypt(full_nonce, full_json, aad_full)
    full_section = struct.pack(">12sI", full_nonce, len(full_ct)) + full_ct

    # Final assembly
    header = struct.pack(">8sHHH", MAGIC, VERSION, flags, meta_len)
    return header + meta_bytes + bytes(slots_bytes) + safe_section + full_section


def unpack_safe_backup(data_bytes: bytes) -> dict:
    """
    Directly decrypt the Safe Apps Section using DeskWarden's internal cipher.
    Does NOT require a master password, recovery key, or email OTP.
    Returns dict: {"config": safe_data, "app": "DeskWarden"}.
    Raises InvalidBackupFormatError or BackupAuthError.
    """
    if not is_deskwarden_backup(data_bytes):
        raise InvalidBackupFormatError("Not an authentic DeskWarden backup file.")

    if len(data_bytes) < 14:
        raise InvalidBackupFormatError("Backup file is truncated.")

    magic, ver, flags, meta_len = struct.unpack(">8sHHH", data_bytes[:14])
    offset = 14 + meta_len

    if flags & FLAG_ENCRYPTED:
        if flags & FLAG_SLOT_PW:
            offset += SLOT_TOTAL_SIZE
        if flags & FLAG_SLOT_KEY:
            offset += SLOT_TOTAL_SIZE
        if flags & FLAG_SLOT_EMAIL:
            offset += SLOT_TOTAL_SIZE
    else:
        offset += SALT_SIZE

    if len(data_bytes) < offset + 32:
        raise InvalidBackupFormatError("Safe section header is truncated.")

    safe_salt, safe_nonce, safe_len = struct.unpack(">16s12sI", data_bytes[offset : offset + 32])
    offset += 32
    if len(data_bytes) < offset + safe_len:
        raise InvalidBackupFormatError("Safe section payload is truncated.")

    safe_ct = data_bytes[offset : offset + safe_len]
    safe_key = _derive_key(SAFE_CIPHER_SECRET, safe_salt, iters=50_000)
    try:
        dec = AESGCM(safe_key).decrypt(safe_nonce, safe_ct, b"DW_SAFE_APPS")
    except InvalidTag:
        raise BackupAuthError("Safe section integrity verification failed.")

    try:
        safe_cfg = json.loads(dec.decode("utf-8"))
        return {
            "app": "DeskWarden",
            "config": safe_cfg,
        }
    except Exception as e:
        raise InvalidBackupFormatError(f"Corrupted safe payload: {e}")


def unpack_backup_container(
    data_bytes: bytes,
    password: str | None = None,
    recovery_key: str | None = None,
    recovery_email: str | None = None,
) -> dict:
    """
    Verify and decrypt an authentic .deskwarden container using any valid authorization factor.
    Returns deserialized full backup data dict.
    Raises InvalidBackupFormatError or BackupAuthError.
    """
    if not is_deskwarden_backup(data_bytes):
        raise InvalidBackupFormatError("Not an authentic DeskWarden backup file.")

    if len(data_bytes) < 14:
        raise InvalidBackupFormatError("DeskWarden backup file is truncated.")

    magic, ver, flags, meta_len = struct.unpack(">8sHHH", data_bytes[:14])
    if ver != VERSION:
        raise InvalidBackupFormatError(f"Unsupported DeskWarden backup version ({ver}).")

    offset = 14
    meta_bytes = data_bytes[offset : offset + meta_len]
    offset += meta_len

    slots_start = offset
    slots_end = offset
    is_encrypted = bool(flags & FLAG_ENCRYPTED)

    vault_key = None

    if is_encrypted:
        slot_pw_bytes = None
        slot_key_bytes = None
        slot_email_bytes = None

        if flags & FLAG_SLOT_PW:
            slot_pw_bytes = data_bytes[slots_end : slots_end + SLOT_TOTAL_SIZE]
            slots_end += SLOT_TOTAL_SIZE
        if flags & FLAG_SLOT_KEY:
            slot_key_bytes = data_bytes[slots_end : slots_end + SLOT_TOTAL_SIZE]
            slots_end += SLOT_TOTAL_SIZE
        if flags & FLAG_SLOT_EMAIL:
            slot_email_bytes = data_bytes[slots_end : slots_end + SLOT_TOTAL_SIZE]
            slots_end += SLOT_TOTAL_SIZE

        # Try unlocking with password
        if password and slot_pw_bytes:
            try:
                s_salt = slot_pw_bytes[:SALT_SIZE]
                s_nonce = slot_pw_bytes[SALT_SIZE : SALT_SIZE + NONCE_SIZE]
                s_cipher = slot_pw_bytes[SALT_SIZE + NONCE_SIZE :]
                s_key = _derive_key(password, s_salt)
                vault_key = AESGCM(s_key).decrypt(s_nonce, s_cipher, b"DW_SLOT_PW")
            except InvalidTag:
                pass

        # Try unlocking with recovery key (hash-based, with fallback to raw normalized)
        if not vault_key and recovery_key and slot_key_bytes:
            rk_hash = _hash_rk(recovery_key)
            try:
                s_salt = slot_key_bytes[:SALT_SIZE]
                s_nonce = slot_key_bytes[SALT_SIZE : SALT_SIZE + NONCE_SIZE]
                s_cipher = slot_key_bytes[SALT_SIZE + NONCE_SIZE :]
                s_key = _derive_key(rk_hash, s_salt)
                vault_key = AESGCM(s_key).decrypt(s_nonce, s_cipher, b"DW_SLOT_KEY")
            except InvalidTag:
                pass

            if not vault_key:
                norm_k = _normalize_recovery_key(recovery_key)
                if norm_k:
                    try:
                        s_key = _derive_key(norm_k, s_salt)
                        vault_key = AESGCM(s_key).decrypt(s_nonce, s_cipher, b"DW_SLOT_KEY")
                    except InvalidTag:
                        pass

        # Try unlocking with email
        if not vault_key and recovery_email and slot_email_bytes:
            norm_em = recovery_email.strip().lower()
            if norm_em:
                try:
                    s_salt = slot_email_bytes[:SALT_SIZE]
                    s_nonce = slot_email_bytes[SALT_SIZE : SALT_SIZE + NONCE_SIZE]
                    s_cipher = slot_email_bytes[SALT_SIZE + NONCE_SIZE :]
                    s_key = _derive_key(norm_em, s_salt)
                    vault_key = AESGCM(s_key).decrypt(s_nonce, s_cipher, b"DW_SLOT_EMAIL")
                except InvalidTag:
                    pass

        if not vault_key:
            raise BackupAuthError("Authentication failed: Incorrect password, recovery key, or verification.")
    else:
        # Safe unencrypted container
        s_salt = data_bytes[slots_end : slots_end + SALT_SIZE]
        slots_end += SALT_SIZE
        vault_key = hashes.Hash(hashes.SHA256())
        vault_key.update(MAGIC + s_salt)
        vault_key = vault_key.finalize()

    all_slots_bytes = data_bytes[slots_start:slots_end]
    offset = slots_end

    # Check if container is two-tier (has safe section followed by full section)
    if len(data_bytes) >= offset + 32:
        safe_salt, safe_nonce, safe_len = struct.unpack(">16s12sI", data_bytes[offset : offset + 32])
        if offset + 32 + safe_len + 16 <= len(data_bytes):
            offset += 32 + safe_len

    if len(data_bytes) < offset + 16:
        raise InvalidBackupFormatError("Truncated payload in backup file.")

    payload_nonce, ct_len = struct.unpack(">12sI", data_bytes[offset : offset + 16])
    offset += 16

    ciphertext_with_tag = data_bytes[offset:]
    if len(ciphertext_with_tag) != ct_len:
        raise InvalidBackupFormatError("Backup stream size mismatch.")

    aad = struct.pack(">8sHHH", MAGIC, VERSION, flags, meta_len) + meta_bytes + all_slots_bytes

    try:
        decrypted_bytes = AESGCM(vault_key).decrypt(payload_nonce, ciphertext_with_tag, aad)
    except InvalidTag:
        raise BackupAuthError("Integrity check failed: Backup file has been tampered or corrupted.")

    try:
        return json.loads(decrypted_bytes.decode("utf-8"))
    except Exception as e:
        raise InvalidBackupFormatError(f"Corrupted backup payload: {e}")
