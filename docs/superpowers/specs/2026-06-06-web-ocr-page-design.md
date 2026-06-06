# 웹 OCR 페이지 (EasyOCR) — 설계

**작성일:** 2026-06-06
**상태:** 승인됨 (구현 계획 대기)
**대상:** `MediCart/web` 에 OCR 페이지·엔드포인트 추가. 레퍼런스 `~/Downloads/MediCart-feature-ocr-demo/ocr`(Gradio) 이식, 디자인은 우리 Next.js 화이트테마.
**선행 의존:** 웹 RTDB전환+MediCart이전 계획 `c15d49b`(MediCart/web + Flask RTDB 백엔드 fb_read) **완료 후** 진행.

## 배경 / 목적

레퍼런스 OCR 데모는 Gradio 단독 앱 2종(`ocr_demo.py`=Cloud Vision, `ocr_realtime.py`=EasyOCR)이다.
이를 우리 web(Flask + Next.js)에 **EasyOCR 로컬**로 이식한다: 브라우저에서 이미지(업로드/웹캠 스냅샷)를 보내면
Flask가 EasyOCR로 텍스트를 추출해 표시하고, 결과를 **RTDB에 기록**한다. Flask는 기존 `publish_mode_cmd`로
**DB에 명령도 전송**할 수 있다(시나리오 B 약품 OCR 검증의 기초).

**확정 결정(브레인스토밍):**
1. 엔진 = **EasyOCR 로컬**(ko+en, API키 불필요, 최초 1회 모델 ~500MB). Cloud Vision 미사용.
2. 흐름 = **단발 스냅샷/업로드** → Flask OCR → 텍스트 표시 + **RTDB `ocr/latest` 기록**. (실시간 스트리밍 아님)
3. 위치 = **MediCart/web**(c15d49b 이전 완료 후). Gradio 폐기, 우리 페이지 패턴.
4. `serviceAccountKey.json` → **`/home/rokey/secrets/serviceAccountKey.json`**(저장소 밖, chmod 600), `FB_CRED` 적용.
5. 프론트는 Flask 경유(RTDB 미접촉) — RTDB Rules 잠금 유지(Flask=admin만 쓰기).

## 아키텍처 / 데이터 흐름

```
[브라우저] /ocr 페이지(AppShell·카드, 화이트테마)
   파일 업로드 또는 웹캠 스냅샷(getUserMedia→canvas→blob) → POST /api/ocr (multipart 이미지)
        │
[web/backend] Flask (인증 쿠키 게이트)
   ocr.py: EasyOCR Reader(ko,en, gpu=False) lazy 1회 로드 → recognized_text(bytes, min_conf=0.3)
   /api/ocr: 이미지 bytes → text 반환 + fb_read.set_ocr({text,conf,ts})
   (명령: fb_read.publish_mode_cmd → robots/{ns}/cmd — 기존, "Flask가 DB에 명령")
        │ firebase-admin (service account=admin, Rules 우회)
[Firebase RTDB] ocr/latest = {text, conf, ts}     (+ robots/{ns}/cmd)
        │ 프론트는 Flask SSE/REST만 (RTDB 직접 미접촉)
[프론트] 결과 텍스트 카드 + (최근 OCR 표시 / 명령 버튼)
```

## 구성요소

### 1. `web/backend/ocr.py` (신규)
- **순수 로직(EasyOCR 무관, 단위테스트):** `filter_join(results, min_conf)` — `[(bbox, text, conf), ...]`에서 `conf > min_conf`인 text를 줄바꿈으로 결합, 없으면 `"인식된 텍스트 없음"`.
- **얇은 엔진 결선:** `_reader()` lazy 싱글톤(`easyocr.Reader(['ko','en'], gpu=False)`, 최초 1회). `recognized_text(image_bytes, min_conf=0.3)` — bytes→numpy(PIL)→`reader.readtext`→`filter_join`.

### 2. `web/backend/fb_read.py` (수정)
- `set_ocr(text, conf=None)`: `db.reference("ocr/latest").set({"text": text, "conf": conf, "ts": now_ms})`. (publish_mode_cmd 기존 유지.)

### 3. `web/backend/app.py` (수정)
- `POST /api/ocr`: 인증 게이트 후 `request.files["image"]`(또는 base64 본문) → bytes → `ocr.recognized_text(bytes)` → `fb_read.set_ocr(text)` → `jsonify({"text": text})`. 입력 없음/형식오류 400. `MAX_CONTENT_LENGTH` 내(이미지 상한 별도 — 예 8MB).

### 4. `web/backend/requirements.txt` (수정)
- `easyocr`, `Pillow`, `numpy` 추가.

### 5. `web/frontend/app/ocr/page.tsx` (신규)
- AppShell + 카드(intake/patients와 동일 톤). **입력 카드**: 파일 업로드(`<input type=file accept=image/*>`) + 웹캠 스냅샷(`getUserMedia`→`<video>`→캡처 버튼→`<canvas>`→blob). **결과 카드**: `/api/ocr` 응답 텍스트(여러 줄). 로딩/에러 상태. (선택) 최근 `ocr/latest`·명령 전송 버튼.

### 6. `web/frontend/lib/api.ts` (수정)
- `ocr(blob: Blob): Promise<{text: string}>` — `FormData`에 image 첨부, `POST /api/ocr`(credentials include).

### 7. `web/frontend/components/Sidebar.tsx` (수정)
- OCR 메뉴 항목 추가(기존 메뉴 패턴).

### 8. `serviceAccountKey` 배치 (설정)
- `~/Downloads/serviceAccountKey.json` → `/home/rokey/secrets/serviceAccountKey.json`(`mkdir -p ~/secrets`, `chmod 600`). web/.env·로봇·마이그레이션의 `FB_CRED`가 이 경로. 저장소 밖이라 커밋 위험 없음.

## RTDB
- `ocr/latest = {text, conf, ts}` — Flask(admin)만 기록, 프론트는 Flask 경유. Rules 전면 잠금 유지(추가 변경 불필요).

## 검증
- **단위(로봇/firebase/easyocr 무관, pytest):** `ocr.filter_join`(신뢰도 필터·줄결합·빈 결과), `fb_read.set_ocr` 페이로드(now_ms 주입 분리해 테스트), `/api/ocr` 입력검증 로직.
- **통합(사용자 실행 — 서버 직접 실행 금지, 명령·순서 제시):** Flask 기동(easyocr 설치) → /ocr 페이지에서 이미지 업로드 → 텍스트 표시 + Firebase 콘솔 `ocr/latest` 기록 확인, 웹캠 스냅샷 동작, 명령 버튼→robots/{ns}/cmd.

## 재사용 / 영향
| 필요 | 위치 |
|---|---|
| EasyOCR 사용법 | 레퍼런스 `ocr/ocr_realtime.py`(reader·readtext·conf 필터) |
| RTDB 쓰기·명령 | `fb_read`(c15d49b) |
| 페이지/디자인 톤 | 기존 `app/intake`·`components/AppShell`·`Sidebar` |
| 인증/엔드포인트 | 기존 `app.py` 게이트 |

**변경 영향 점검:** OCR은 신규 페이지·엔드포인트라 기존 기능 무영향. EasyOCR 모델 로드(최초 지연·메모리)는 lazy 싱글톤으로 첫 요청에서만. requirements 증가(easyocr 무거움 — 백엔드 환경에만). RTDB `ocr/latest`는 신규 경로. serviceAccountKey 이동은 FB_CRED 경로만 갱신.

## 범위 밖
- 실시간 스트리밍 OCR(단발만).
- 처방/환자 데이터 대조 검증(pass/fail) — 별도.
- Cloud Vision 엔진.
- 로봇 ocr_detector(OAK-D) 연동 — 본 건은 웹 OCR 페이지.
