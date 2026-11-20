
"""Authenticated encryption for background-job envelopes.

AES-256-GCM protects confidentiality and detects ciphertext changes.
Tenant ID and job ID are authenticated as additional associated data.

Keys are supplied by the caller and must not be stored in source code,
PostgreSQL, or the encrypted message itself.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from apps.worker.jobs.envelope import JobEnvelope


FORMAT_VERSION = b"JBE1"
NONCE_SIZE = 12
MAX_PLAINTEXT_BYTES = 1024 * 1024


class JobEncryptionError(ValueError):
    """An encrypted job is invalid or cannot be authenticated."""


class JobEnvelopeCipher:
    """Encrypt and decrypt tenant-bound background-job envelopes."""

    def __init__(
        self,
        keys: Mapping[str, bytes],
        active_key_id: str,
    ) -> None:
        if not keys:
            raise ValueError("At least one encryption key is required")

        if not active_key_id or active_key_id not in keys:
            raise ValueError("Active encryption key is unavailable")

        validated: dict[str, bytes] = {}

        for key_id, key in keys.items():
            if (
                not isinstance(key_id, str)
                or not key_id
                or len(key_id) > 64
            ):
                raise ValueError("Invalid encryption key identifier")

            if not isinstance(key, bytes) or len(key) != 32:
                raise ValueError(
                    "Each AES-256 encryption key must contain 32 bytes"
                )

            validated[key_id] = key

        self._keys = validated
        self.active_key_id = active_key_id

    @staticmethod
    def _associated_data(
        tenant_id: str,
        job_id: str,
        key_id: str,
    ) -> bytes:
        if not tenant_id or not job_id or not key_id:
            raise ValueError(
                "Tenant, job, and key identifiers are required"
            )

        context = {
            "version": 1,
            "purpose": "background-job-outbox",
            "tenant_id": tenant_id,
            "job_id": job_id,
            "key_id": key_id,
        }

        return json.dumps(
            context,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

    def encrypt(
        self,
        job: JobEnvelope,
    ) -> tuple[bytes, str]:
        """Return authenticated ciphertext and its key identifier."""

        key_id = self.active_key_id

        plaintext = job.model_dump_json().encode("utf-8")

        if len(plaintext) > MAX_PLAINTEXT_BYTES:
            raise ValueError("Job envelope exceeds encryption size limit")

        nonce = os.urandom(NONCE_SIZE)

        authenticated_context = self._associated_data(
            job.tenant_id,
            job.job_id,
            key_id,
        )

        ciphertext = AESGCM(self._keys[key_id]).encrypt(
            nonce,
            plaintext,
            authenticated_context,
        )

        # Format: 4-byte version + 12-byte nonce + GCM ciphertext/tag.
        return FORMAT_VERSION + nonce + ciphertext, key_id

    def decrypt(
        self,
        ciphertext: bytes,
        key_id: str,
        *,
        tenant_id: str,
        job_id: str,
    ) -> JobEnvelope:
        """Authenticate and reconstruct an encrypted job envelope."""

        if key_id not in self._keys:
            raise JobEncryptionError("Encryption key unavailable")

        if not isinstance(ciphertext, bytes):
            raise JobEncryptionError("Invalid encrypted message")

        minimum_length = len(FORMAT_VERSION) + NONCE_SIZE + 16

        if (
            len(ciphertext) < minimum_length
            or not ciphertext.startswith(FORMAT_VERSION)
            or len(ciphertext)
            > len(FORMAT_VERSION)
            + NONCE_SIZE
            + MAX_PLAINTEXT_BYTES
            + 16
        ):
            raise JobEncryptionError("Invalid encrypted message format")

        nonce_start = len(FORMAT_VERSION)
        nonce_end = nonce_start + NONCE_SIZE

        nonce = ciphertext[nonce_start:nonce_end]
        encrypted_data = ciphertext[nonce_end:]

        authenticated_context = self._associated_data(
            tenant_id,
            job_id,
            key_id,
        )

        try:
            plaintext = AESGCM(self._keys[key_id]).decrypt(
                nonce,
                encrypted_data,
                authenticated_context,
            )

            job = JobEnvelope.model_validate_json(plaintext)

        except (InvalidTag, ValueError) as exc:
            raise JobEncryptionError(
                "Job envelope authentication or validation failed"
            ) from exc

        if job.tenant_id != tenant_id or job.job_id != job_id:
            raise JobEncryptionError(
                "Decrypted job identity does not match"
            )

        return job
