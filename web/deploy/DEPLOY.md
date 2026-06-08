# intel.thatshoon.com 호스팅 (Cloudflare Tunnel + 비밀번호 게이트)

MediCart 웹(`/home/rokey/MediCart/web`)을 PC3에서 돌리고 Cloudflare Tunnel로 `intel.thatshoon.com`에 노출한다.
백엔드는 Firebase RTDB(firebase-admin)를 서버측에서 읽어 SSE/REST로 프론트에 제공한다 — Cloudflare엔 코드 미배포(터널 노출만).

```
브라우저 → Cloudflare → Tunnel → PC3 cloudflared
                                   /api/*  → Flask :5000   (SSE 직결)
                                   그 외   → Next  :3000
접근 통제: 앱 비밀번호 게이트 — /login 에서 입력 → 쿠키 발급, Flask·Next 양쪽 검증.
데이터: Flask ↔ Firebase RTDB(읽기/쓰기). 로봇 텔레메트리 생산자(ward_bridge)는 intel1.
```

## 전제
- `thatshoon.com` 이 **Cloudflare DNS(네임서버)** 에 연결돼 있어야 함.
- PC3에 백엔드 venv(firebase-admin 등) + 프론트 빌드 구성 완료.
- `MediCart/common/`(robot.env·maps) 존재 — web 자기완결(intel1 비의존).

## 절차

**1) Cloudflare 로그인(브라우저 인증 — 1회):**
```bash
cloudflared tunnel login
```
브라우저가 열리면 Cloudflare 계정 로그인 → `thatshoon.com` 선택 → 인증. `~/.cloudflared/cert.pem` 생성됨.

**2) 셋업 스크립트 실행(터널 생성·DNS·빌드·서비스 기동):**
```bash
~/MediCart/web/deploy/setup-tunnel.sh
```
완료되면 `https://intel.thatshoon.com` 접속 → 비밀번호(web/backend/.env 의 `INTEL_PASSWORD`) → 입장.

## 구성
- `medicart-backend.service` — Flask :5000. EnvironmentFile: `MediCart/common/robot.env`(NS) + `web/backend/.env`(시크릿).
- `medicart-frontend.service` — Next :3000 (`npm run start`, 프로덕션 빌드 필요. `.env` 뒤 `PORT=3000` override).
- `medicart-tunnel.service` — `cloudflared tunnel run intel` (`~/.cloudflared/config.yml`).

## 비밀번호·토큰 변경
- 비밀번호: `web/backend/.env` 의 `INTEL_PASSWORD`
- 쿠키 토큰(반드시 Flask·Next 동일): `INTEL_AUTH_TOKEN` (`.env` — backend·frontend 서비스 모두 이 파일 로드)
변경 후 `sudo systemctl restart medicart-backend medicart-frontend`.

## 운영
```bash
systemctl status medicart-backend medicart-frontend medicart-tunnel
journalctl -u medicart-tunnel -f
sudo systemctl restart medicart-frontend   # 프론트 재빌드 후
```

## 보안 메모(데모)
- 단일 공유 비밀번호 게이트 — 데모 수준. 실제 PHI 운영 시 Cloudflare Access(SSO) 또는 앱 RBAC 필요.
- 쿠키는 HttpOnly·SameSite=Lax·Secure(https). 토큰·비번은 `.env`(env-필수, 소스 하드코딩 없음).
- RTDB Rules 전면 잠금(admin SDK 전용). 클라이언트는 RTDB 직접 미접촉.
