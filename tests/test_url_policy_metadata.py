from spark_cli.security.url_policy import validate_url_safety


def test_aws_metadata_blocked():
    errs = validate_url_safety("https://metadata.amazonaws.com/latest/meta-data/")
    assert any("metadata" in e for e in errs)


def test_ecs_metadata_blocked():
    errs = validate_url_safety("https://169.254.170.2/v2/credentials")
    assert any("metadata" in e for e in errs)


def test_azure_metadata_blocked():
    errs = validate_url_safety("https://metadata.azure.com/metadata/instance")
    assert any("metadata" in e for e in errs)


def test_trailing_dot_blocked():
    errs = validate_url_safety("https://metadata.google.internal./computeMetadata")
    assert any("metadata" in e for e in errs)


def test_safe_url_not_blocked():
    errs = validate_url_safety("https://example.com/")
    assert errs == []
