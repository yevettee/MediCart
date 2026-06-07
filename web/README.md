# web — 병동 보조 로봇 대시보드 (MediCart)

Flask(백엔드 :5000) + Next.js(프론트 :3000). Firebase RTDB를 **서버측(firebase-admin)** 에서 읽어
SSE/REST로 프론트에 제공. 프론트(브라우저)는 Flask만 호출하고 RTDB를 직접 만지지 않는다.
로봇 텔레메트리 생산자(`ward_bridge`, RTDB `{ns}` 기록)는 intel1에서 동작 — 이 웹은 **읽기/쓰기만**.

MediCart **standalone**: NS·맵·discovery는 `/home/rokey/MediCart/common/` 에 있다(intel1 비의존).

```
backend/   Flask : fb_read(RTDB 경계)·patients·ocr·app(SSE/REST/auth/mission)
frontend/  Next  : app/{map,control,patients,intake,ocr,debug}, lib/api(백엔드 호출)
deploy/    systemd 서비스 + setup-tunnel.sh(호스팅)
docs/      architecture·setup·deploy(DEPLOY.md)
legacy/    구 Redis/xlsx 구현(미사용·참고)
```

---

## 0. 사전 준비 (최초 1회)

```bash
# (1) 서비스계정 키 — 저장소 밖, 600 권한
ls /home/rokey/secrets/serviceAccountKey.json     # 없으면 발급 후 이 경로에 두기

# (2) 백엔드 venv + 의존
cd /home/rokey/MediCart/web/backend
python3 -m venv venv
venv/bin/pip install -r requirements.txt          # flask·firebase-admin·easyocr 등

# (3) 프론트 의존
cd /home/rokey/MediCart/web/frontend
npm install

# (4) .env 작성 (시크릿 — git 제외됨)
cd /home/rokey/MediCart/web/backend
cp .env.example .env
#  - FB_CRED=/home/rokey/secrets/serviceAccountKey.json
#  - FB_DB_URL=https://medi-cart-ea39f-default-rtdb.asia-southeast1.firebasedatabase.app
#  - INTEL_PASSWORD=<로그인 비번>
#  - INTEL_AUTH_TOKEN=$(python3 -c "import secrets;print(secrets.token_urlsafe(32))")
#  - NS(PRIMARY/SECONDARY)는 .env가 아니라 common/robot.env(ROBOT_NAMESPACE)에서 도출됨
```

> **NS·맵은 `/home/rokey/MediCart/common/`** 의 `robot.env`·`maps/` 를 쓴다. 로봇(robot3↔robot6) 전환은
> `common/robot.env` 의 `ROBOT_NAMESPACE` 한 곳만 바꾸면 백엔드·프론트 빌드에 함께 반영된다.

---

## 1. 로컬 개발 실행

### 백엔드 (:5000)
```bash
set -a
source /home/rokey/MediCart/common/robot.env      # ROBOT_NAMESPACE → PRIMARY_NS
source /home/rokey/MediCart/web/backend/.env       # 시크릿·FB·MAP 경로
set +a
cd /home/rokey/MediCart/web/backend
venv/bin/python app.py
```

### 프론트 (:3000, dev)
```bash
cd /home/rokey/MediCart/web/frontend
export INTEL_AUTH_TOKEN="$(grep '^INTEL_AUTH_TOKEN=' ../backend/.env | cut -d= -f2-)"   # 미들웨어 필수
export NEXT_PUBLIC_PRIMARY_NS=robot6               # common/robot.env 기준
npm run dev                                        # http://localhost:3000 (API는 localhost:5000)
```
- dev는 API_BASE 기본값이 `http://localhost:5000` 라 로컬 백엔드와 바로 붙는다.
- ⚠ `INTEL_AUTH_TOKEN` 이 없으면 미들웨어가 모든 페이지를 `/login` 으로 막는다(아래 "함정" 참고).

---

## 2. 프로덕션 / 공개 호스팅 (intel.thatshoon.com)

dev 모드 HMR 웹소켓이 터널에서 깨지므로 **반드시 프로덕션 빌드**로 호스팅한다.

### 백엔드 (:5000) — 로컬 개발과 동일
```bash
set -a
source /home/rokey/MediCart/common/robot.env
source /home/rokey/MediCart/web/backend/.env
set +a
cd /home/rokey/MediCart/web/backend
venv/bin/python app.py
```

### 프론트 빌드 (NS를 robot.env에서 주입)
```bash
cd /home/rokey/MediCart/web/frontend
source /home/rokey/MediCart/common/robot.env
PRI="${ROBOT_NAMESPACE#/}"; case "$PRI" in robot6) SEC=robot3;; robot3) SEC=robot6;; *) SEC=robot6;; esac
NEXT_PUBLIC_API_BASE="" NEXT_PUBLIC_PRIMARY_NS="$PRI" NEXT_PUBLIC_SECONDARY_NS="$SEC" npm run build
```

### 프론트 기동 (:3000) — 토큰 + PORT 주의
```bash
cd /home/rokey/MediCart/web/frontend
set -a; source /home/rokey/MediCart/web/backend/.env; set +a   # INTEL_AUTH_TOKEN
export PORT=3000                                                # ★ .env의 PORT=5000(백엔드용)을 덮어씀
npm run start
```

### Cloudflare 터널
```bash
cloudflared --no-autoupdate --config ~/.cloudflared/config.yml tunnel run intel
```
→ `https://intel.thatshoon.com` (`/api/*`→Flask:5000, 그 외→Next:3000)

---

## 3. systemd 영속 운용 (권장)

`deploy/setup-tunnel.sh` 가 빌드 + 3개 서비스 설치·기동을 한 번에 한다(최초 `cloudflared tunnel login` 후):
```bash
~/MediCart/web/deploy/setup-tunnel.sh
```
설치되는 서비스 — `medicart-backend`(:5000) · `medicart-frontend`(:3000) · `medicart-tunnel`.
```bash
systemctl status  medicart-backend medicart-frontend medicart-tunnel
sudo systemctl restart medicart-backend          # 코드/.env 변경 후
sudo systemctl restart medicart-frontend         # 프론트 재빌드 후
journalctl -u medicart-tunnel -f
```
자세한 내용은 `deploy/DEPLOY.md`.

---

## 4. 중지 / 재시작 (수동 기동 시)

수동으로 띄운 경우 PID로 종료 후 재기동(포트 충돌 방지):
```bash
kill -9 $(ss -ltnp | grep ':5000' | grep -oE 'pid=[0-9]+' | cut -d= -f2)   # 백엔드
kill -9 $(ss -ltnp | grep ':3000' | grep -oE 'pid=[0-9]+' | cut -d= -f2)   # 프론트
```

---

## 5. 흔한 함정 (반드시 확인)

| 증상 | 원인 | 해결 |
|---|---|---|
| 로그인해도 모든 페이지가 `/login` 으로 튕김(307) | 프론트 프로세스에 `INTEL_AUTH_TOKEN` 없음 → 미들웨어 fail-closed | 기동 전 `.env` source(토큰 주입) |
| 프론트가 `:5000`을 잡아 `EADDRINUSE` | `.env`의 `PORT=5000`(백엔드용)을 상속 | 프론트는 `export PORT=3000` 후 start |
| 기동이 조용히 `exit 1` | 기존 프로세스가 포트 점유 | 위 "중지"로 PID kill 후 재기동 |
| `/api/*` 500, RTDB 오류 | 인터넷/FB 도달 불가 또는 `FB_CRED`·`FB_DB_URL` 누락 | 네트워크 + `.env` 확인 |
| 대시보드에 AMR 실데이터 없음 | 로봇측 `ward_bridge`(intel1) 미가동 | 로봇 PC에서 ward_bridge 실행 필요 |

---

## 6. 빠른 점검
```bash
curl -s -c /tmp/c -X POST localhost:5000/api/login -H 'Content-Type: application/json' -d '{"password":"<INTEL_PASSWORD>"}'
curl -s -b /tmp/c localhost:5000/api/health        # {"ok":true}
curl -s -b /tmp/c localhost:5000/api/map           # 맵 메타(available/origin/resolution)
curl -s -b /tmp/c localhost:5000/api/amrs          # robot3/robot6 스냅샷
```

페이지: `/`(홈) · `/map`(실시간 관제) · `/control`(로봇 제어·명령) · `/patients`(환자) · `/intake`(문진) · `/ocr`(약품 OCR) · `/debug`.
