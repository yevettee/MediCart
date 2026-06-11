"""auth — 순수 역할(RBAC) 로직. Flask 의존 없음(단위테스트 가능).

역할 서열: patient(0) < staff(1) < admin(2). 상위는 하위 권한 포함.
권한 판정은 위변조 불가한 비밀 토큰/비번 비교(상수시간)로만 한다.
"""
import hmac

ROLE_RANK = {"patient": 0, "staff": 1, "admin": 2}

_OPEN = {"/api/health", "/api/login", "/api/me", "/api/logout", "/api/intake",
         "/api/nurse_cart/phase",   # 약품실 공용 화면 — 로봇 단계 폴링(인증 불필요)
         "/api/cs_chat"}            # 환자 CS 챗봇 — 비로그인 환자도 사용(공개)
# 키오스크 디스플레이 현재 환자(읽기/표시) — 비로그인 허용. (display/expected 는 staff)
_PATIENT_PREFIXES = ("/api/display/current",)
_STAFF_PREFIXES = ("/api/patients", "/api/ocr", "/api/patrol", "/api/nurse_cart",
                   "/api/identify", "/api/display/expected", "/api/cs_logs",
                   # 순회 문진(staff)이 읽는 참조/텔레메트리(GET 전용) — admin 기본값이라
                   # 의료진이 targets 를 못 받아 stops 가 비던 버그 수정.
                   "/api/targets", "/api/rooms", "/api/amrs")


def _eq(a, b):
    return bool(b) and hmac.compare_digest(str(a or ""), str(b))


def role_for_token(token, staff_token, admin_token):
    if _eq(token, admin_token):
        return "admin"
    if _eq(token, staff_token):
        return "staff"
    return "patient"


def role_for_password(password, staff_pw, admin_pw):
    if _eq(password, admin_pw):
        return "admin"
    if _eq(password, staff_pw):
        return "staff"
    return None


def required_role_for_path(path):
    if path in _OPEN:
        return "patient"
    if path.startswith(_PATIENT_PREFIXES):
        return "patient"
    if path.startswith(_STAFF_PREFIXES):
        return "staff"
    if path.startswith("/api/"):
        return "admin"
    return "patient"


def allowed(role, required):
    return ROLE_RANK.get(role, 0) >= ROLE_RANK.get(required, 99)


def token_for_role(role, staff_token, admin_token):
    return admin_token if role == "admin" else staff_token
