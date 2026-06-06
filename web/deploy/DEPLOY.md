# intel.thatshoon.com 호스팅 (Cloudflare Tunnel + 비밀번호 게이트)

병동 웹(hospital_web)을 PC3에서 그대로 돌리고 Cloudflare Tunnel로 `intel.thatshoon.com`에 노출한다.
백엔드는 PC1/PC2 Redis를 읽어야 하므로 로컬(PC3)에 남는다 — Cloudflare엔 코드 미배포(터널 노출만).

```
브라우저 → Cloudflare → Tunnel → PC3 cloudflared
                                   /api/*  → Flask :5000   (SSE 직결)
                                   그 외   → Next  :3000
접근 통제: 앱 비밀번호 게이트(rokey1234) — /login 에서 입력 → 쿠키 발급, Flask·Next 양쪽 검증.
```

## 전제
- `thatshoon.com` 이 **Cloudflare DNS(네임서버)** 에 연결돼 있어야 함(대시보드에서 도메인 추가 + 레지스트라 네임서버 변경).
- PC3에 redis-server 실행, 백엔드 venv 구성 완료(이미 됨).

## 절차

**1) Cloudflare 로그인(브라우저 인증 — 1회):**
```bash
cloudflared tunnel login
```
브라우저가 열리면 Cloudflare 계정 로그인 → `thatshoon.com` 선택 → 인증. `~/.cloudflared/cert.pem` 생성됨.

**2) 셋업 스크립트 실행(터널 생성·DNS·빌드·서비스 기동):**
```bash
~/rokey_ws/src/intel1/hospital_web/deploy/setup-tunnel.sh
```
완료되면 `https://intel.thatshoon.com` 접속 → 비밀번호 `rokey1234` → 입장.

## 구성
- `intel-backend.service` — Flask :5000 (COOKIE_SECURE=1, FRONTEND_ORIGIN=https://intel.thatshoon.com)
- `intel-frontend.service` — Next :3000 (`npm run start`, 프로덕션 빌드 필요)
- `intel-tunnel.service` — `cloudflared tunnel run intel` (`~/.cloudflared/config.yml`)
- `.env.production` — `NEXT_PUBLIC_API_BASE=`(빈 값 = 같은 오리진)

## 비밀번호·토큰 변경
- 비밀번호: `intel-backend.service` 의 `INTEL_PASSWORD`
- 쿠키 토큰(반드시 Flask·Next 동일): `INTEL_AUTH_TOKEN` (backend·frontend 서비스 양쪽)
변경 후 `sudo systemctl restart intel-backend intel-frontend`.

## 운영
```bash
systemctl status intel-backend intel-frontend intel-tunnel
journalctl -u intel-tunnel -f
sudo systemctl restart intel-frontend   # 프론트 재빌드 후
```

## 보안 메모(데모)
- 단일 공유 비밀번호 게이트 — 데모 수준. 실제 PHI 운영 시 Cloudflare Access(SSO) 또는 앱 RBAC 필요.
- 쿠키는 HttpOnly·SameSite=Lax·Secure(https). 토큰은 데모 상수 — 운영 시 무작위 비밀로 교체.
