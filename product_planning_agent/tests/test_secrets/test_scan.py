"""Secret scanning tests (T06). Every Done-when box in
tasks/t06_event_log_and_secret_scanning.md that concerns scanning maps to at
least one test here. Fixture values are deliberately NOT shaped like
`sk-ant-...` (Anthropic's own prefix) — that literal shape is exactly what
tests/test_secrets/test_repo_hygiene.py's own credential-value scan looks
for repo-wide, and a test fixture is still a committed value.
"""

from __future__ import annotations

from ppa.ledger.secrets import REDACTED, Finding, scan_and_redact


def _families(findings: list[Finding]) -> set[str]:
    return {f.family for f in findings}


# ---------------------------------------------------------------------------
# api_key — sk- / ghp_ / AKIA / generic high-entropy run
# ---------------------------------------------------------------------------


def test_sk_prefixed_key_is_redacted():
    text = "here is my key sk-test-abcdefghijklmnopqrstuvwxyz123456 for the demo"
    redacted, findings = scan_and_redact(text)
    assert "sk-test-" not in redacted
    assert REDACTED in redacted
    assert _families(findings) == {"api_key"}


def test_sk_near_miss_is_not_redacted():
    text = "the skateboard park opens sk_test_underscore_not_hyphen at noon"
    redacted, findings = scan_and_redact(text)
    assert redacted == text
    assert findings == []


def test_github_token_is_redacted():
    text = "token: ghp_abcdefghijklmnopqrstuvwxyz12345678"
    redacted, findings = scan_and_redact(text)
    assert "ghp_" not in redacted
    assert REDACTED in redacted
    assert _families(findings) == {"api_key"}


def test_github_token_near_miss_is_not_redacted():
    text = "the ghp_ prefix alone means nothing without a real token"
    redacted, findings = scan_and_redact(text)
    assert redacted == text
    assert findings == []


def test_aws_access_key_is_redacted():
    text = "AWS_ACCESS_KEY_ID is AKIAABCDEFGHIJKLMNOP in the old config"
    redacted, findings = scan_and_redact(text)
    assert "AKIAABCDEFGHIJKLMNOP" not in redacted
    assert REDACTED in redacted
    assert _families(findings) == {"api_key"}


def test_aws_access_key_near_miss_is_not_redacted():
    text = "AKIA is just the four-letter prefix AWS uses, not a full key"
    redacted, findings = scan_and_redact(text)
    assert redacted == text
    assert findings == []


def test_high_entropy_run_is_redacted():
    text = "the raw value was Xk9F2vQmZ8pL3jN7wY6tR4hB1cD5sA0eW2gH9 in the log"
    redacted, findings = scan_and_redact(text)
    assert REDACTED in redacted
    assert _families(findings) == {"api_key"}


def test_low_entropy_long_run_is_not_redacted():
    text = "a placeholder value like aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa is fine"
    redacted, findings = scan_and_redact(text)
    assert redacted == text
    assert findings == []


# ---------------------------------------------------------------------------
# credentialed_uri
# ---------------------------------------------------------------------------


def test_credentialed_postgres_uri_is_redacted():
    text = "connect via postgres://appuser:S3cretPass@db.internal:5432/prod"
    redacted, findings = scan_and_redact(text)
    assert "S3cretPass" not in redacted
    assert "appuser" not in redacted
    assert REDACTED in redacted
    assert _families(findings) == {"credentialed_uri"}


def test_uri_without_credentials_is_not_redacted():
    text = "connect via postgres://db.internal:5432/prod"
    redacted, findings = scan_and_redact(text)
    assert redacted == text
    assert findings == []


# ---------------------------------------------------------------------------
# private_key
# ---------------------------------------------------------------------------


def test_private_key_header_is_redacted():
    text = "-----BEGIN RSA PRIVATE KEY-----\nMIIEow...redacted-body...\n-----END RSA PRIVATE KEY-----"
    redacted, findings = scan_and_redact(text)
    assert "BEGIN RSA PRIVATE KEY" not in redacted
    assert REDACTED in redacted
    assert _families(findings) == {"private_key"}


def test_certificate_header_is_not_a_private_key_near_miss():
    text = "-----BEGIN CERTIFICATE-----\nMIIEow...\n-----END CERTIFICATE-----"
    redacted, findings = scan_and_redact(text)
    assert redacted == text
    assert findings == []


# ---------------------------------------------------------------------------
# auth_header
# ---------------------------------------------------------------------------


def test_authorization_header_is_redacted():
    text = "the request sent Authorization: Bearer abcdef1234567890 upstream"
    redacted, findings = scan_and_redact(text)
    assert "abcdef1234567890" not in redacted
    assert REDACTED in redacted
    assert "auth_header" in _families(findings)


def test_bearer_word_alone_is_not_redacted():
    text = "the bearer of good news arrived early"
    redacted, findings = scan_and_redact(text)
    assert redacted == text
    assert findings == []


# ---------------------------------------------------------------------------
# env_assignment
# ---------------------------------------------------------------------------


def test_env_style_password_assignment_is_redacted():
    text = "our staging config has DB_PASSWORD=SuperSecretValue123 in it"
    redacted, findings = scan_and_redact(text)
    assert "SuperSecretValue123" not in redacted
    assert REDACTED in redacted
    assert _families(findings) == {"env_assignment"}


def test_password_hint_is_not_an_assignment_near_miss():
    text = "PASSWORD_HINT=what is your pet's name"
    redacted, findings = scan_and_redact(text)
    assert redacted == text
    assert findings == []


# ---------------------------------------------------------------------------
# General behaviour
# ---------------------------------------------------------------------------


def test_clean_text_passes_through_unchanged():
    text = "The system must support single sign-on for enterprise customers."
    redacted, findings = scan_and_redact(text)
    assert redacted == text
    assert findings == []


def test_multiple_hits_in_one_string_are_all_redacted():
    text = "leaked postgres://u:p@h/db and also DB_TOKEN=abcdefghijklmnop here"
    redacted, findings = scan_and_redact(text)
    assert "u:p@h" not in redacted
    assert "abcdefghijklmnop" not in redacted
    assert len(findings) == 2
    assert _families(findings) == {"credentialed_uri", "env_assignment"}


def test_finding_never_carries_the_raw_matched_text():
    text = "DB_PASSWORD=SuperSecretValue123"
    _redacted, findings = scan_and_redact(text)
    assert findings[0].model_dump() == {"family": "env_assignment"}
