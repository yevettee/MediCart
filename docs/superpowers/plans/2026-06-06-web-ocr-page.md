# 웹 OCR 페이지 (EasyOCR) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.
> **선행 의존:** 웹 이전 계획 `c15d49b`(hospital_web→MediCart/web + fb_read RTDB 백엔드) **완료 후** 실행. 그래야 `MediCart/web/backend/{app.py,fb_read.py}` 경로가 존재한다.
> **실행 제약(CLAUDE.md):** Flask·프론트·easyocr 구동은 **직접 실행 금지 — 사용자에게 명령·순서 제시**. 순수 로직 pytest·git·파일 이동은 직접 가능.

**Goal:** MediCart/web 에 OCR 페이지를 추가 — 브라우저에서 이미지(업로드/웹캠 스냅샷)를 Flask로 보내 EasyOCR(ko+en)로 텍스트를 추출·표시하고, 결과를 RTDB `ocr/latest` 에 기록한다.

**Architecture:** 순수 로직(신뢰도 필터·줄결합, ocr 페이로드)을 EasyOCR/Flask/firebase와 분리해 단위테스트한다. `ocr.py`가 EasyOCR 경계(lazy 싱글톤)다. `app.py`에 `/api/ocr` 추가, `fb_read.set_ocr`로 RTDB 기록. 프론트는 Next.js 화이트테마 페이지(Gradio 폐기).

**Tech Stack:** Flask, easyocr, Pillow, numpy, firebase-admin, Next.js, pytest.

**스펙:** `MediCart/docs/superpowers/specs/2026-06-06-web-ocr-page-design.md`
**경로:** `WB=/home/rokey/MediCart/web/backend`, `WF=/home/rokey/MediCart/web/frontend`.

---

## File Structure
- `WB/ocr.py`(신규) — EasyOCR 래퍼(`filter_join` 순수 + `recognized_text`).
- `WB/test/test_ocr.py`(신규) — filter_join 테스트.
- `WB/fb_read.py`(수정) — `ocr_payload`(순수) + `set_ocr`.
- `WB/test/test_fb_read.py`(수정) — ocr_payload 테스트 추가.
- `WB/app.py`(수정) — `POST /api/ocr` + MAX_CONTENT_LENGTH 상향.
- `WB/requirements.txt`(수정) — easyocr·Pillow·numpy.
- `WF/lib/api.ts`(수정) — `ocr(blob)`.
- `WF/app/ocr/page.tsx`(신규) — OCR 페이지.
- `WF/components/Sidebar.tsx`(수정) — OCR 메뉴.
- `~/secrets/serviceAccountKey.json` — 자격증명 이동(설정).

---

### Task 1: `ocr.py` — 신뢰도 필터·줄결합 (순수) + EasyOCR 결선

**Files:**
- Create: `WB/ocr.py`, `WB/test/test_ocr.py`

- [ ] **Step 1: Write the failing test**

Create `/home/rokey/MediCart/web/backend/test/test_ocr.py`:

```python
"""ocr 순수 로직 단위 테스트 (easyocr 무관).

실행: cd MediCart/web/backend && python3 -m pytest test/test_ocr.py -v
"""
from ocr import filter_join


def test_filter_join_keeps_high_conf():
    results = [(None, "타이레놀", 0.92), (None, "noise", 0.10), (None, "500mg", 0.55)]
    assert filter_join(results, 0.3) == "타이레놀\n500mg"


def test_filter_join_empty_when_all_low():
    assert filter_join([(None, "x", 0.1)], 0.3) == "인식된 텍스트 없음"


def test_filter_join_no_results():
    assert filter_join([], 0.3) == "인식된 텍스트 없음"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/rokey/MediCart/web/backend && python3 -m pytest test/test_ocr.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ocr'`

- [ ] **Step 3: Write minimal implementation**

Create `/home/rokey/MediCart/web/backend/ocr.py`:

```python
"""ocr — EasyOCR 텍스트 추출 (ocr_realtime.py 이식).

순수 로직(신뢰도 필터·줄결합)은 easyocr 무관이라 단위테스트한다. EasyOCR Reader는
ko+en 로컬 추론으로 lazy 싱글톤(최초 1회 ~500MB 다운로드). 웹 백엔드 전용.
"""
_reader = None


def filter_join(results, min_conf):
    """easyocr readtext 결과 [(bbox, text, conf), ...] → conf>min_conf text 줄결합."""
    texts = [t for (_bbox, t, c) in results if c > min_conf]
    return "\n".join(texts) if texts else "인식된 텍스트 없음"


def _get_reader():
    global _reader
    if _reader is None:
        import easyocr
        _reader = easyocr.Reader(["ko", "en"], gpu=False)
    return _reader


def recognized_text(image_bytes, min_conf=0.3):
    """이미지 bytes → 인식 텍스트(여러 줄). easyocr 로컬 추론."""
    import io
    import numpy as np
    from PIL import Image
    img = np.array(Image.open(io.BytesIO(image_bytes)).convert("RGB"))
    return filter_join(_get_reader().readtext(img), min_conf)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/rokey/MediCart/web/backend && python3 -m pytest test/test_ocr.py -v`
Expected: PASS (3 passed) — easyocr/numpy/PIL 은 `recognized_text` 내부 import라 미설치에도 filter_join 테스트 통과.

- [ ] **Step 5: Commit**

```bash
cd /home/rokey/MediCart
git add web/backend/ocr.py web/backend/test/test_ocr.py
git commit -m "feat(web): ocr.py — EasyOCR 텍스트 추출(필터·줄결합 순수+결선)"
```

---

### Task 2: `fb_read.set_ocr` (RTDB 기록)

**Files:**
- Modify: `WB/fb_read.py`, `WB/test/test_fb_read.py`

- [ ] **Step 1: Write the failing test** — APPEND to `WB/test/test_fb_read.py`:

```python
def test_ocr_payload():
    from fb_read import ocr_payload
    assert ocr_payload("타이레놀", 0.9, 1000) == {"text": "타이레놀", "conf": 0.9, "ts": 1000}
    assert ocr_payload("x", None, 5)["conf"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/rokey/MediCart/web/backend && python3 -m pytest test/test_fb_read.py::test_ocr_payload -v`
Expected: FAIL — `ImportError: cannot import name 'ocr_payload'`

- [ ] **Step 3: Add to fb_read.py** — APPEND to `WB/fb_read.py` (after the firebase wiring; `time` already imported in Task 3 of c15d49b):

```python
def ocr_payload(text, conf, ts):
    """RTDB ocr/latest 페이로드(순수)."""
    return {"text": text, "conf": conf, "ts": int(ts)}


def set_ocr(text, conf=None):
    """OCR 결과를 RTDB ocr/latest 에 기록."""
    db = _init()
    db.reference("ocr/latest").set(ocr_payload(text, conf, int(time.time() * 1000)))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/rokey/MediCart/web/backend && python3 -m pytest test/test_fb_read.py -q`
Expected: PASS (8 passed — 기존 7 + ocr_payload).

- [ ] **Step 5: Commit**

```bash
cd /home/rokey/MediCart
git add web/backend/fb_read.py web/backend/test/test_fb_read.py
git commit -m "feat(web): fb_read.set_ocr — OCR 결과 RTDB ocr/latest 기록"
```

---

### Task 3: `app.py` — `/api/ocr` 엔드포인트

**Files:**
- Modify: `WB/app.py`

- [ ] **Step 1: import + MAX_CONTENT_LENGTH 상향** — In `WB/app.py`:

상단 import에 추가:
```python
import ocr
```
`app.config["MAX_CONTENT_LENGTH"]` 줄을 이미지 허용치로 상향(기존 256KB → 8MB):
```python
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024   # 이미지 업로드 허용(OCR)
```

- [ ] **Step 2: `/api/ocr` 핸들러 추가** — 다른 엔드포인트 근처에 추가:

```python
@app.post("/api/ocr")
def api_ocr():
    f = request.files.get("image")
    if f is None:
        return jsonify({"error": "no image"}), 400
    data = f.read()
    if not data:
        return jsonify({"error": "empty image"}), 400
    text = ocr.recognized_text(data)
    try:
        fb_read.set_ocr(text)
    except Exception:
        pass   # OCR 표시는 유지, RTDB 기록 실패는 비치명
    return jsonify({"text": text})
```

- [ ] **Step 3: 문법 검증**

Run: `cd /home/rokey/MediCart/web/backend && python3 -c "import ast; ast.parse(open('app.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
cd /home/rokey/MediCart
git add web/backend/app.py
git commit -m "feat(web): /api/ocr 엔드포인트(EasyOCR→텍스트+RTDB 기록) + 업로드 상한 상향"
```

---

### Task 4: requirements + serviceAccountKey 배치

**Files:**
- Modify: `WB/requirements.txt`
- Setup: `~/secrets/serviceAccountKey.json`

- [ ] **Step 1: requirements.txt에 easyocr 추가** — `WB/requirements.txt` 끝에 추가:
```
easyocr
Pillow
numpy
```

- [ ] **Step 2: serviceAccountKey 이동(저장소 밖)**

Run:
```bash
mkdir -p /home/rokey/secrets
mv /home/rokey/Downloads/serviceAccountKey.json /home/rokey/secrets/serviceAccountKey.json
chmod 600 /home/rokey/secrets/serviceAccountKey.json
ls -l /home/rokey/secrets/serviceAccountKey.json
```
Expected: `-rw-------` 권한으로 존재.

- [ ] **Step 3: .env에 FB_CRED 경로(사용자)**

> `MediCart/web/backend/.env`(c15d49b의 .env.example 복사본)와 로봇/마이그레이션 환경의 `FB_CRED` 를 다음으로 설정:
> `FB_CRED=/home/rokey/secrets/serviceAccountKey.json`
> (코드 변경 아님 — 사용자 .env 편집. 커밋 대상 아님.)

- [ ] **Step 4: Commit (requirements만)**

```bash
cd /home/rokey/MediCart
git add web/backend/requirements.txt
git commit -m "build(web): easyocr·Pillow·numpy 의존 추가(OCR)"
```

---

### Task 5: 프론트 — api.ts + OCR 페이지 + Sidebar

**Files:**
- Modify: `WF/lib/api.ts`, `WF/components/Sidebar.tsx`
- Create: `WF/app/ocr/page.tsx`

- [ ] **Step 1: api.ts에 ocr 헬퍼** — `WF/lib/api.ts` 끝에 추가:

```typescript
export async function ocr(blob: Blob): Promise<{ text: string }> {
  const fd = new FormData();
  fd.append("image", blob, "capture.png");
  const r = await fetch(`${API_BASE}/api/ocr`, { method: "POST", credentials: "include", body: fd });
  if (!r.ok) throw new Error(`/api/ocr → ${r.status}`);
  return r.json();
}
```

- [ ] **Step 2: Sidebar 메뉴 추가** — `WF/components/Sidebar.tsx` 의 `NAV` 배열에서 `/intake` 다음에 추가:

```typescript
  { href: "/ocr", label: "약품 OCR", sub: "텍스트 인식", icon: FormIcon },
```
(기존 `FormIcon` 재사용 — 새 아이콘 불필요.)

- [ ] **Step 3: OCR 페이지 생성** — Create `WF/app/ocr/page.tsx`:

```tsx
"use client";
import { useRef, useState } from "react";
import { ocr } from "@/lib/api";

export default function OcrPage() {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [preview, setPreview] = useState<string>("");
  const videoRef = useRef<HTMLVideoElement>(null);
  const [camOn, setCamOn] = useState(false);

  async function run(blob: Blob) {
    setBusy(true); setErr(""); setText("");
    setPreview(URL.createObjectURL(blob));
    try {
      const r = await ocr(blob);
      setText(r.text);
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  }

  function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (f) run(f);
  }

  async function startCam() {
    const stream = await navigator.mediaDevices.getUserMedia({ video: true });
    if (videoRef.current) {
      videoRef.current.srcObject = stream;
      await videoRef.current.play();
      setCamOn(true);
    }
  }

  function snap() {
    const v = videoRef.current;
    if (!v) return;
    const c = document.createElement("canvas");
    c.width = v.videoWidth; c.height = v.videoHeight;
    c.getContext("2d")!.drawImage(v, 0, 0);
    c.toBlob((b) => { if (b) run(b); }, "image/png");
  }

  return (
    <div className="p-7 max-w-4xl">
      <header className="mb-6">
        <h1 className="text-2xl font-bold text-ink">약품 OCR</h1>
        <p className="text-ink-3 text-sm mt-1">이미지 업로드 또는 웹캠 스냅샷으로 약품 텍스트를 인식합니다.</p>
      </header>

      <div className="grid md:grid-cols-2 gap-5">
        {/* 입력 카드 */}
        <section className="bg-surface border border-line rounded-2xl p-5">
          <h2 className="font-semibold text-ink mb-3">입력</h2>
          <label className="block">
            <span className="text-sm text-ink-3">이미지 파일</span>
            <input type="file" accept="image/*" onChange={onFile}
              className="mt-1 block w-full text-sm file:mr-3 file:rounded-lg file:border-0 file:bg-teal file:text-white file:px-3 file:py-2" />
          </label>

          <div className="mt-4">
            {!camOn ? (
              <button onClick={startCam}
                className="rounded-lg bg-surface-2 text-ink px-3 py-2 text-sm hover:bg-line">웹캠 켜기</button>
            ) : (
              <button onClick={snap}
                className="rounded-lg bg-teal text-white px-3 py-2 text-sm">스냅샷 인식</button>
            )}
            <video ref={videoRef} className={`mt-3 w-full rounded-xl bg-black ${camOn ? "" : "hidden"}`} muted playsInline />
          </div>

          {preview && <img src={preview} alt="미리보기" className="mt-3 w-full rounded-xl border border-line" />}
        </section>

        {/* 결과 카드 */}
        <section className="bg-surface border border-line rounded-2xl p-5">
          <h2 className="font-semibold text-ink mb-3">인식 결과</h2>
          {busy && <p className="text-ink-3 text-sm">인식 중…</p>}
          {err && <p className="text-red-600 text-sm">{err}</p>}
          {!busy && !err && (
            <pre className="whitespace-pre-wrap text-ink text-sm min-h-[8rem]">{text || "이미지를 입력하세요."}</pre>
          )}
        </section>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: 타입/문법 점검(빌드 없이)**

Run: `cd /home/rokey/MediCart/web/frontend && npx tsc --noEmit -p tsconfig.json 2>&1 | grep -E "ocr|api\.ts" | head || echo "ocr 관련 타입오류 없음"`
Expected: `ocr 관련 타입오류 없음` (node_modules 설치돼 있어야 tsc 동작 — 미설치면 이 단계는 통합에서).

- [ ] **Step 5: Commit**

```bash
cd /home/rokey/MediCart
git add web/frontend/lib/api.ts web/frontend/components/Sidebar.tsx web/frontend/app/ocr/page.tsx
git commit -m "feat(web): OCR 페이지(업로드/웹캠 스냅샷→/api/ocr) + 사이드바 메뉴"
```

---

### Task 6: 통합 검증 (사용자 실행)

**Files:** 없음(검증).

> ⚠️ Flask·프론트·easyocr 구동은 **사용자 직접 실행**. (최초 easyocr 모델 ~500MB 다운로드.)

- [ ] **Step 1: 의존성(사용자)**
```bash
cd /home/rokey/MediCart/web/backend && venv/bin/pip install -r requirements.txt
```

- [ ] **Step 2: 단위테스트(컨트롤러/사용자)**
```bash
cd /home/rokey/MediCart/web/backend && python3 -m pytest test/ -q
```
Expected: ocr 3 + fb_read 8 + patients 2 = 13 passed.

- [ ] **Step 3: Flask 기동 + OCR(사용자)**
```bash
cd /home/rokey/MediCart/web/backend && venv/bin/python app.py
# 다른 터미널: 로그인 쿠키 후 이미지 업로드
curl -s -c /tmp/c -X POST localhost:5000/api/login -H 'Content-Type: application/json' -d '{"password":"rokey1234"}'
curl -s -b /tmp/c -F image=@/path/to/drug.jpg localhost:5000/api/ocr
```
Expected: `{"text": "..."}`(인식 텍스트). Firebase 콘솔 `ocr/latest` 에 {text,conf,ts} 기록.

- [ ] **Step 4: 프론트(사용자)**
```bash
cd /home/rokey/MediCart/web/frontend && npm install && npm run dev
```
브라우저 → 로그인 → /ocr → 이미지 업로드 또는 웹캠 스냅샷 → 결과 텍스트 표시, RTDB ocr/latest 갱신 확인.

---

## Self-Review

**1. Spec coverage:**
- EasyOCR 로컬(ko+en) → Task 1 ✓
- 단발 업로드/웹캠 스냅샷 → Task 5 페이지 ✓
- /api/ocr → 텍스트 + RTDB ocr/latest → Task 2·3 ✓
- Flask DB 명령(publish_mode_cmd 기존) → c15d49b, 변경 없음 ✓
- 우리 화이트테마 이식(AppShell/카드/Sidebar) → Task 5 ✓
- serviceAccountKey → ~/secrets, FB_CRED → Task 4 ✓
- requirements easyocr → Task 4 ✓
- 검증 단위/통합 → Task 1·2·6 ✓

**2. Placeholder scan:** 코드·명령 완전. .env FB_CRED는 사용자 설정(코드 아님)으로 명시.

**3. Type consistency:**
- `filter_join(results,min_conf)`·`recognized_text(bytes,min_conf)`(Task 1) = app /api/ocr 호출(Task 3) 일치.
- `ocr_payload(text,conf,ts)`·`set_ocr(text,conf)`(Task 2) = app(Task 3) 일치.
- `ocr(blob)`(api.ts, Task 5) = 페이지 호출 일치, 백엔드 `/api/ocr` multipart `image` 필드 일치.
- RTDB `ocr/latest` 경로 = 스펙 일치. Sidebar `/ocr` = 페이지 라우트 일치.
