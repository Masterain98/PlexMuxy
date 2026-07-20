from plexmuxy_gui.activation import parse_activation_args, parse_activation_uri


def test_notification_activation_accepts_only_canonical_job_actions():
    job_id = "5bf5467d-a161-4753-8d55-673265aae746"
    request = parse_activation_uri(f"plexmuxy://job/{job_id}?action=output")
    assert request is not None
    assert request.job_id == job_id
    assert request.action == "output"
    assert parse_activation_uri("plexmuxy://job/not-a-uuid") is None
    assert parse_activation_uri(f"plexmuxy://job/{job_id}?action=run-command") is None
    assert parse_activation_uri(f"plexmuxy://job/{job_id}?path=C:/Windows") is None
    assert parse_activation_args([f"plexmuxy://job/{job_id}", "extra"]) is None
