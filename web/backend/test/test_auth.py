import auth


def test_role_for_token():
    assert auth.role_for_token("ADM", "STF", "ADM") == "admin"
    assert auth.role_for_token("STF", "STF", "ADM") == "staff"
    assert auth.role_for_token("nope", "STF", "ADM") == "patient"
    assert auth.role_for_token(None, "STF", "ADM") == "patient"
    assert auth.role_for_token("", "STF", "ADM") == "patient"


def test_role_for_password():
    assert auth.role_for_password("apw", "spw", "apw") == "admin"
    assert auth.role_for_password("spw", "spw", "apw") == "staff"
    assert auth.role_for_password("x", "spw", "apw") is None
    assert auth.role_for_password(None, "spw", "apw") is None


def test_required_role_for_path():
    for p in ["/api/health", "/api/login", "/api/me", "/api/logout", "/api/intake"]:
        assert auth.required_role_for_path(p) == "patient"
    assert auth.required_role_for_path("/api/patients") == "staff"
    assert auth.required_role_for_path("/api/patients/P-2024-0001/visits") == "staff"
    assert auth.required_role_for_path("/api/ocr") == "staff"
    assert auth.required_role_for_path("/api/amrs") == "admin"
    assert auth.required_role_for_path("/api/stream") == "admin"
    assert auth.required_role_for_path("/login") == "patient"


def test_allowed_and_token_for_role():
    assert auth.allowed("admin", "staff") is True
    assert auth.allowed("staff", "staff") is True
    assert auth.allowed("staff", "admin") is False
    assert auth.allowed("patient", "patient") is True
    assert auth.allowed("patient", "staff") is False
    assert auth.token_for_role("admin", "STF", "ADM") == "ADM"
    assert auth.token_for_role("staff", "STF", "ADM") == "STF"
