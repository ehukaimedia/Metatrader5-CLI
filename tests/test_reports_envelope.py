from mt5_cli.reports import ok, fail


def test_ok_envelope_shape():
    env = ok({"x": 1})
    assert env == {"ok": True, "data": {"x": 1}}


def test_fail_envelope_shape():
    env = fail("E_CODE", "human-readable message")
    assert env["ok"] is False
    assert env["error"]["code"] == "E_CODE"
    assert env["error"]["message"] == "human-readable message"


def test_fail_with_data():
    env = fail("E_RETCODE", "broker rejected", data={"retcode": 10030})
    assert env["error"]["data"] == {"retcode": 10030}
