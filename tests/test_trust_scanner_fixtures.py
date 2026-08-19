from __future__ import annotations

from spark_cli.trust_scanner_fixtures import is_redaction_fixture_private_key


def test_accepts_direct_redaction_fixture() -> None:
    assert is_redaction_fixture_private_key(
        "tests/redaction.test.ts",
        "redactText('-----BEGIN PRIVATE KEY-----\\nplaceholder\\n-----END PRIVATE KEY-----')",
    )


def test_accepts_array_fixture_only_when_it_flows_to_sanitizer() -> None:
    source = """
const credentialSamples = [
  'password=placeholder',
  '-----BEGIN PRIVATE KEY-----'
];
for (const sample of credentialSamples) {
  assert.equal(containsSensitiveCredentialMaterial(sample), true);
}
for (const sample of credentialSamples) {
  const sanitized = sanitizeCredentialMemoryText(sample);
  assert.equal(sanitized, '[sensitive credential omitted]');
}
"""
    assert is_redaction_fixture_private_key("tests/credentialSafety.test.ts", source)


def test_rejects_array_fixture_without_redaction_sink() -> None:
    source = """
const credentialSamples = ['-----BEGIN PRIVATE KEY-----'];
for (const sample of credentialSamples) {
  console.log(sample);
}
"""
    assert not is_redaction_fixture_private_key("tests/leak.test.ts", source)
    assert not is_redaction_fixture_private_key("src/runtime.ts", source.replace("console.log", "sanitize"))
