# 아키텍처

```
로봇 PC(intel1) ward_bridge ──firebase-admin──▶ Firebase RTDB ◀──firebase-admin── web/backend Flask
                                  robots/{ns}/{state,cmd,alerts}        │ SSE/REST(쿠키 인증)
                                  patients/{pid}, rooms/                ▼
                                                                   web/frontend Next.js
```
- 프론트는 Firebase 직접 접근 안 함 → RTDB Rules 전면 잠금(admin SDK만). 인증은 Flask 쿠키.
- backend: `fb_read.py`(snapshots·리스너→SSE·cmd set·intake), `patients.py`(RTDB→프론트 형식), `app.py`(엔드포인트).
- 데이터: `robots/{ns}/state`(2Hz, scan 제외)·`cmd`·`alerts`, `patients/{pid}/{info,vitals,intake}`, `rooms/`.
