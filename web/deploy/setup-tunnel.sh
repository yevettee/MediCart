#!/usr/bin/env bash
# intel2.thatshoon.com 호스팅 셋업 — `cloudflared tunnel login` 완료 후 실행.
# 터널 생성 → config 작성 → DNS 라우트 → 프론트 prod 빌드 → systemd 3서비스 기동.
# MediCart standalone(intel1 비의존). NS/맵은 MediCart/common 에서 가져온다.
set -euo pipefail

HOST=intel2.thatshoon.com
NAME=intel2
REPO=/home/rokey/MediCart
ROBOT_ENV=/home/rokey/MediCart/common/robot.env
CF="$HOME/.cloudflared"

[ -f "$CF/cert.pem" ] || { echo "✗ 먼저 'cloudflared tunnel login' 을 실행하세요(브라우저 인증)."; exit 1; }

# 1) 터널 생성(이미 있으면 재사용)
cloudflared tunnel list | awk '{print $2}' | grep -qx "$NAME" || cloudflared tunnel create "$NAME"
TID=$(cloudflared tunnel list | awk -v n="$NAME" '$2==n{print $1}')
echo "▶ tunnel: $NAME ($TID)"

# 2) config.yml — /api 는 Flask, 그 외는 Next 로 경로 분기
cat > "$CF/config.yml" <<EOF
tunnel: $TID
credentials-file: $CF/$TID.json
ingress:
  - hostname: $HOST
    path: ^/api
    service: http://localhost:5000
  - hostname: $HOST
    service: http://localhost:3000
  - service: http_status:404
EOF
echo "▶ wrote $CF/config.yml"

# 3) DNS 라우트(intel.thatshoon.com → 이 터널)
cloudflared tunnel route dns "$NAME" "$HOST" || echo "  (DNS 라우트 이미 존재 가능 — 무시)"

# 4) 프론트 프로덕션 빌드 — robot.env 의 ROBOT_NAMESPACE 를 PRIMARY/SECONDARY 로 주입(같은 오리진 /api)
# shellcheck disable=SC1090
set -a; source "$ROBOT_ENV"; set +a
PRI="${ROBOT_NAMESPACE#/}"
case "$PRI" in robot6) SEC=robot3;; robot3) SEC=robot6;; *) SEC=robot6;; esac
( cd "$REPO/web/frontend" \
  && NEXT_PUBLIC_API_BASE="" NEXT_PUBLIC_PRIMARY_NS="$PRI" NEXT_PUBLIC_SECONDARY_NS="$SEC" npm run build )

# 5) systemd 서비스 설치·기동
sudo cp "$REPO/web/deploy/medicart-backend.service"  /etc/systemd/system/
sudo cp "$REPO/web/deploy/medicart-frontend.service" /etc/systemd/system/
sudo cp "$REPO/web/deploy/medicart-tunnel.service"   /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now medicart-backend medicart-frontend medicart-tunnel

echo "✅ 완료 → https://$HOST  (접속 비밀번호는 web/backend/.env 의 INTEL_PASSWORD)"
echo "   상태: systemctl status medicart-backend medicart-frontend medicart-tunnel"
