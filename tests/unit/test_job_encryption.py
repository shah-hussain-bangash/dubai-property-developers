"""Tests for encrypted background-job envelopes."""

from __future__ import annotations

import os

import pytest

from apps.worker.jobs.envelope import JobEnvelope
from core.security.job_encryption import (
    JobEncryptionError,
    JobEnvelopeCipher,
)


@pytest.fixture
def cipher():
    """Use fictional keys generated only for these tests."""

    return JobEnvelopeCipher(
        keys={"test-key-1": os.urandom(32)},
        active_key_id="test-key-1",
    )


@pytest.fixture
def job():
    return JobEnvelope(
        job_id="fictional-job-001",
        job_type="knowledge.ingest",
        tenant_id="demo-org",
        payload={
            "document_id": "fictional-document",
            "message": "Confidential test content",
        },
    )


def test_encryption_round_trip(cipher, job):
    ciphertext, key_id = cipher.encrypt(job)

    restored = cipher.decrypt(
        ciphertext,
        key_id,
        tenant_id=job.tenant_id,
        job_id=job.job_id,
    )

    assert restored == job
    assert b"Confidential test content" not in ciphertext


def test_ciphertext_tampering_is_rejected(cipher, job):
    ciphertext, key_id = cipher.encrypt(job)

    tampered = bytearray(ciphertext)
    tampered[-1] ^= 1

    with pytest.raises(JobEncryptionError):
        cipher.decrypt(
            bytes(tampered),
            key_id,
            tenant_id=job.tenant_id,
            job_id=job.job_id,
        )


def test_wrong_tenant_is_rejected(cipher, job):
    ciphertext, key_id = cipher.encrypt(job)

    with pytest.raises(JobEncryptionError):
        cipher.decrypt(
            ciphertext,
            key_id,
            tenant_id="another-organization",
            job_id=job.job_id,
        )


def test_wrong_job_id_is_rejected(cipher, job):
    ciphertext, key_id = cipher.encrypt(job)

    with pytest.raises(JobEncryptionError):
        cipher.decrypt(
            ciphertext,
            key_id,
            tenant_id=job.tenant_id,
            job_id="different-job",
        )


def test_incorrect_key_is_rejected(cipher, job):
    ciphertext, key_id = cipher.encrypt(job)

    wrong_cipher = JobEnvelopeCipher(
        keys={key_id: os.urandom(32)},
        active_key_id=key_id,
    )

    with pytest.raises(JobEncryptionError):
        wrong_cipher.decrypt(
            ciphertext,
            key_id,
            tenant_id=job.tenant_id,
            job_id=job.job_id,
        )


def test_each_encryption_uses_a_fresh_nonce(cipher, job):
    first, _ = cipher.encrypt(job)
    second, _ = cipher.encrypt(job)

    assert first != second


def test_key_rotation_supports_previous_key(job):
    old_key = os.urandom(32)
    new_key = os.urandom(32)

    original_cipher = JobEnvelopeCipher(
        keys={"old": old_key},
        active_key_id="old",
    )

    ciphertext, key_id = original_cipher.encrypt(job)

    rotated_cipher = JobEnvelopeCipher(
        keys={
            "old": old_key,
            "new": new_key,
        },
        active_key_id="new",
    )

    restored = rotated_cipher.decrypt(
        ciphertext,
        key_id,
        tenant_id=job.tenant_id,
        job_id=job.job_id,
    )

    assert restored == job

    new_ciphertext, new_key_id = rotated_cipher.encrypt(job)
    assert new_key_id == "new"
    assert new_ciphertext != ciphertext
