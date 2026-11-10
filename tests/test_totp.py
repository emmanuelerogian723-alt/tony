from tony import totp


def test_codes_verify_and_reject():
    secret = totp.new_secret()
    code = totp.code_at(secret)
    assert totp.verify(secret, code)
    assert not totp.verify(secret, "000000")
    assert not totp.verify(secret, "abc")


def test_two_factor_lifecycle(client):
    client.post("/v1/account/signup", json={"email": "2fa@example.com", "password": "Tony-tour-9271"})
    start = client.post("/v1/account/2fa/start").json()
    secret = start["secret"]
    assert start["otpauth_url"].startswith("otpauth://totp/")
    bad = client.post("/v1/account/2fa/enable", json={"code": "000000"})
    assert bad.status_code == 400
    ok = client.post("/v1/account/2fa/enable", json={"code": totp.code_at(secret)})
    assert ok.status_code == 200 and ok.json()["enabled"] is True
    client.post("/v1/account/logout")
    no_code = client.post("/v1/account/login", json={"email": "2fa@example.com", "password": "Tony-tour-9271"})
    assert no_code.status_code == 401
    with_code = client.post("/v1/account/login", json={"email": "2fa@example.com",
                                                      "password": "Tony-tour-9271",
                                                      "code": totp.code_at(secret)})
    assert with_code.status_code == 200
