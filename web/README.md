# web — 병동 보조 로봇 대시보드 (MediCart)

Flask(백엔드) + Next.js(프론트). Firebase RTDB를 서버측에서 읽어 SSE/REST로 제공.
로봇(intel1 ward_bridge)이 RTDB `robots/{ns}` 에 기록 → 이 백엔드가 읽어 표시.

- `backend/` Flask: fb_read(RTDB 경계)·patients·app(SSE/REST/auth)
- `frontend/` Next.js: lib/api로 백엔드 호출(RTDB 미접촉)
- `docs/` architecture·setup·deploy
- `legacy/` 더 이상 안 쓰는 Redis/xlsx 구현(참고 보존)

빠른 시작은 `docs/setup.md`.
