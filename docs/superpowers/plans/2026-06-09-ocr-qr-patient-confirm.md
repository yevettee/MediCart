# 처치실 OCR "QR 환자 확인" 모드 이식 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** integration `/ocr`의 "실시간 OCR" 탭을 jeon의 "QR 환자 확인" 탭(3단계 게이트)으로 교체하고, jeon이 미연결로 둔 `confirmInjection`을 complete 시 실제 호출해 DB에 확정 기록한다.

**Architecture:** 3단계 판정은 순수 함수 `decideQr`로 분리(vitest)하고, `/ocr` 페이지는 realtime 인터벌만 제거하고 qr 스캔 루프(300ms jsQR)·결과 패널을 이식한다. 백엔드는 verify 라우트와 동형의 confirm 라우트를 추가(기존 `update_injection_status` 재사용). single 자동검증·USB 카메라·`setOcrDone`는 유지.

**Tech Stack:** Next.js 16 App Router(web/frontend), Flask(web/backend), jsqr, Firebase RTDB, vitest, pytest.

---

## File Structure

- `web/frontend/lib/ocrQr.ts` — Create: `decideQr` 순수 판정 + 타입
- `web/frontend/lib/ocrQr.test.ts` — Create: vitest
- `web/frontend/lib/api.ts` — Modify: `confirmInjection` 추가(verify 헬퍼 뒤, ~line 257)
- `web/backend/app.py` — Modify: confirm 라우트 추가(verify 라우트 뒤, ~line 192)
- `web/backend/test/test_app_auth.py` — Modify: confirm 라우트 테스트
- `web/frontend/app/ocr/page.tsx` — Modify: realtime 모드 제거 → qr 모드(+complete 시 confirmInjection)

> **Next.js note:** `web/frontend/AGENTS.md` 경고 — 이 Next.js(16.2.7 App Router)는 학습데이터와 다름. `app/` 수정 전 `node_modules/next/dist/docs/` 확인. 본 작업은 표준 클라이언트 훅 + jsqr 동적 import만 사용(기존 페이지가 이미 사용).

> **jeon 원본 참고:** `git show origin/jeon:web/frontend/app/ocr/page.tsx` (커밋 267e8ee). 단, jeon은 `confirmInjection` 미호출(버그) — 본 플랜은 complete 시 호출하도록 고친다.

---

## Task 1: 순수 판정 로직 `decideQr` (vitest)

**Files:**
- Create: `web/frontend/lib/ocrQr.ts`
- Test: `web/frontend/lib/ocrQr.test.ts`

- [ ] **Step 1: 실패 테스트 작성**

Create `web/frontend/lib/ocrQr.test.ts`:
```ts
import { describe, expect, it } from "vitest";
import { decideQr } from "./ocrQr";

const inj = (id: string, status?: string, 약품명?: string) => ({ id, status, 약품명 });

describe("decideQr", () => {
  it("스캔 PID가 선택 환자와 다르면 blocked_patient", () => {
    const d = decideQr("P-2024-0002", "P-2024-0001", [inj("a", "confirmed")]);
    expect(d).toEqual({ kind: "blocked_patient", scannedPid: "P-2024-0002" });
  });

  it("미confirmed 약품이 있으면 blocked_meds (미준비 목록)", () => {
    const d = decideQr("P-2024-0001", "P-2024-0001", [
      inj("a", "confirmed", "세파졸린"),
      inj("b", "pending", "수액"),
      inj("c", "mismatch", "포도당"),
    ]);
    expect(d).toEqual({
      kind: "blocked_meds",
      unready: [
        { name: "수액", status: "pending" },
        { name: "포도당", status: "mismatch" },
      ],
    });
  });

  it("status 없으면 pending 으로 표시", () => {
    const d = decideQr("P-2024-0001", "P-2024-0001", [inj("a")]);
    expect(d).toEqual({ kind: "blocked_meds", unready: [{ name: "a", status: "pending" }] });
  });

  it("전부 confirmed 면 complete (injCount)", () => {
    const d = decideQr("P-2024-0001", "P-2024-0001", [inj("a", "confirmed"), inj("b", "confirmed")]);
    expect(d).toEqual({ kind: "complete", injCount: 2 });
  });

  it("주사 목록이 비면 complete injCount 0", () => {
    const d = decideQr("P-2024-0001", "P-2024-0001", []);
    expect(d).toEqual({ kind: "complete", injCount: 0 });
  });
});
```

- [ ] **Step 2: 실패 확인**

Run: `cd web/frontend && npx vitest run lib/ocrQr.test.ts`
Expected: FAIL — cannot resolve `./ocrQr`

- [ ] **Step 3: 구현**

Create `web/frontend/lib/ocrQr.ts`:
```ts
// 처치실 QR 환자 확인 — 순수 3단계 판정(의존성 0, vitest). 표시명은 호출측에서 부여.
export type QrDecision =
  | { kind: "blocked_patient"; scannedPid: string }
  | { kind: "blocked_meds"; unready: { name: string; status: string }[] }
  | { kind: "complete"; injCount: number };

export type InjLike = { id: string; status?: string; 약품명?: string; 약물명?: string };

// 스캔 PID·선택 PID·주사목록 → 판정.
//   다른 환자          → blocked_patient
//   미confirmed 약품 有 → blocked_meds (미준비 목록)
//   전부 confirmed     → complete
export function decideQr(
  scannedPid: string,
  selectedPid: string,
  injections: InjLike[],
): QrDecision {
  if (scannedPid !== selectedPid) return { kind: "blocked_patient", scannedPid };
  const unready = injections
    .filter((i) => i.status !== "confirmed")
    .map((i) => ({ name: (i.약품명 || i.약물명 || i.id), status: i.status ?? "pending" }));
  if (unready.length > 0) return { kind: "blocked_meds", unready };
  return { kind: "complete", injCount: injections.length };
}
```

- [ ] **Step 4: 통과 확인**

Run: `cd web/frontend && npx vitest run lib/ocrQr.test.ts`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add web/frontend/lib/ocrQr.ts web/frontend/lib/ocrQr.test.ts
git commit -m "feat(web): decideQr — 처치실 QR 환자확인 3단계 판정"
```

---

## Task 2: `confirmInjection` API 헬퍼

**Files:**
- Modify: `web/frontend/lib/api.ts` (verify 헬퍼 뒤)

- [ ] **Step 1: 구현**

`web/frontend/lib/api.ts`의 `verifyInjection` 함수(끝 `return r.json(); }`) 바로 뒤에 추가:
```ts
export async function confirmInjection(
  pid: string,
  inj_id: string,
): Promise<{ ok: boolean; status: string }> {
  const r = await fetch(`${API_BASE}/api/patients/${pid}/injections/${inj_id}/confirm`, {
    method: "POST",
    credentials: "include",
  });
  if (!r.ok) throw new Error(`/api/patients/${pid}/injections/${inj_id}/confirm → ${r.status}`);
  return r.json();
}
```
READ `web/frontend/lib/api.ts` 먼저 — `verifyInjection`(~line 245)이 `${API_BASE}` + `credentials: "include"` 패턴을 쓴다(동일 스타일). `API_BASE`는 파일 상단 정의.

- [ ] **Step 2: 타입체크**

Run: `cd web/frontend && npx tsc --noEmit`
Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add web/frontend/lib/api.ts
git commit -m "feat(web): confirmInjection API 헬퍼"
```

---

## Task 3: 백엔드 confirm 엔드포인트

**Files:**
- Modify: `web/backend/app.py` (verify 라우트 뒤, ~line 192)
- Test: `web/backend/test/test_app_auth.py`

- [ ] **Step 1: 실패 테스트 작성**

`web/backend/test/test_app_auth.py` 끝에 추가:
```python
def test_confirm_injection_records_confirmed(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        flask_app.fb_read, "update_injection_status",
        lambda pid, inj_id, status, ocr_text=None: seen.update(
            {"pid": pid, "inj": inj_id, "status": status, "note": ocr_text}),
    )
    client.set_cookie("intel_auth", "STAFFTOK")
    r = client.post("/api/patients/P-2024-0001/injections/inj1/confirm")
    assert r.status_code == 200
    assert r.get_json() == {"ok": True, "status": "confirmed"}
    assert seen == {"pid": "P-2024-0001", "inj": "inj1", "status": "confirmed", "note": "QR 환자 확인"}


def test_confirm_injection_bad_pid(monkeypatch):
    monkeypatch.setattr(flask_app.fb_read, "update_injection_status",
                        lambda *a, **k: None)
    client.set_cookie("intel_auth", "STAFFTOK")
    assert client.post("/api/patients/bad/injections/inj1/confirm").status_code == 400


def test_confirm_injection_requires_staff():
    client.set_cookie("intel_auth", "")
    assert client.post("/api/patients/P-2024-0001/injections/inj1/confirm").status_code == 401
```

- [ ] **Step 2: 실패 확인**

Run: `cd web/backend && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 ./venv/bin/python -m pytest test/test_app_auth.py -q`
Expected: FAIL — confirm 라우트가 없어 404(staff)·또는 비staff 401만 통과.

- [ ] **Step 3: 구현**

`web/backend/app.py`의 `verify_injection` 함수(끝 `return jsonify({"ok": True, "match": match, "status": status, "reason": reason})`) 바로 뒤에 추가:
```python
@app.post("/api/patients/<pid>/injections/<inj_id>/confirm")
def confirm_injection(pid, inj_id):
    """QR 환자 확인 — 처방 완료를 DB에 직접 기록."""
    if not _PID_RE.match(pid):
        return jsonify({"error": "invalid id"}), 400
    try:
        fb_read.update_injection_status(pid, inj_id, "confirmed", "QR 환자 확인")
    except Exception as e:                      # noqa: BLE001
        return jsonify({"error": str(e)}), 500
    return jsonify({"ok": True, "status": "confirmed"})
```
`_PID_RE`(app.py:63)·`fb_read.update_injection_status`(fb_read.py:538)는 이미 존재(verify가 사용). `/api/patients` 프리픽스라 staff 게이트 자동 적용.

- [ ] **Step 4: 통과 확인**

Run: `cd web/backend && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 ./venv/bin/python -m pytest test/test_app_auth.py -q`
Expected: PASS (3 new + 기존 통과). 참고: 전체 스위트엔 무관한 기존 실패 `test_targets_seed_shape`가 있을 수 있음(이 작업과 무관).

- [ ] **Step 5: Commit**

```bash
git add web/backend/app.py web/backend/test/test_app_auth.py
git commit -m "feat(web): /api/patients/<pid>/injections/<inj_id>/confirm 라우트"
```

---

## Task 4: `/ocr` 페이지 — realtime 모드 → QR 환자 확인 모드

**Files:**
- Modify: `web/frontend/app/ocr/page.tsx`

여러 정밀 편집(surgical edit)으로 진행한다. 각 편집은 정확한 old→new 블록을 적용한다. 시작 전 `web/frontend/app/ocr/page.tsx` 전체를 READ 할 것.

- [ ] **Step 1: import + 상단 상수 + QrResult 타입**

찾기(파일 상단):
```tsx
import { useCallback, useEffect, useRef, useState } from "react";
import {
  getPatients, getInjections, verifyInjection, ocr as runOcr, setOcrDone,
  type Patient, type Injection,
} from "@/lib/api";

type InjEntry = { id: string } & Injection;

type VerifyResult = { match: boolean; status: string; reason: string } | null;
```
바꾸기:
```tsx
import { useCallback, useEffect, useRef, useState } from "react";
import {
  getPatients, getInjections, verifyInjection, confirmInjection, ocr as runOcr, setOcrDone,
  type Patient, type Injection,
} from "@/lib/api";
import { decideQr } from "@/lib/ocrQr";

const PID_RE = /^P-\d{4}-\d{4}$/;
const QR_COOLDOWN_MS = 3000;

type InjEntry = { id: string } & Injection;

type VerifyResult = { match: boolean; status: string; reason: string } | null;

type QrResult =
  | { type: "complete";        patientName: string; injCount: number }
  | { type: "blocked_meds";    patientName: string; unready: { name: string; status: string }[] }
  | { type: "blocked_patient"; scannedPid: string;  selectedName: string }
  | null;
```

- [ ] **Step 2: 모드 상태 타입 변경 + QR 상태 추가**

찾기:
```tsx
  /* OCR 모드 */
  const [ocrMode, setOcrMode] = useState<"single" | "realtime">("single");
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const scanningRef = useRef(false); // 동시 요청 방지
```
바꾸기:
```tsx
  /* OCR 모드 */
  const [ocrMode, setOcrMode] = useState<"single" | "qr">("single");
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const scanningRef = useRef(false); // 동시 요청 방지

  /* QR 환자 확인 모드 */
  const [qrRaw, setQrRaw] = useState<string | null>(null);
  const [qrResult, setQrResult] = useState<QrResult>(null);
  const [qrConfirming, setQrConfirming] = useState(false);
  const qrCooldownRef = useRef<number>(0);
  const qrConfirmingRef = useRef(false);
```

- [ ] **Step 3: realtime 인터벌 effect → scanQr + qr 인터벌 effect**

찾기:
```tsx
  /* 실시간 OCR 인터벌 관리 */
  useEffect(() => {
    if (ocrMode === "realtime" && camOn) {
      captureAndOcr();
      intervalRef.current = setInterval(() => captureAndOcr(), 2000);
    } else {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    }
    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [ocrMode, camOn, captureAndOcr]);
```
바꾸기:
```tsx
  /* QR 환자 확인 스캔 — jsQR 디코드 → decideQr 판정. complete면 confirmInjection 으로 DB 확정. */
  const scanQr = useCallback(async () => {
    const v = videoRef.current;
    if (!v || !camOn || !v.videoWidth || !v.videoHeight) return;
    if (qrConfirmingRef.current) return;

    const canvas = document.createElement("canvas");
    canvas.width = v.videoWidth;
    canvas.height = v.videoHeight;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.drawImage(v, 0, 0);
    const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);

    const { default: jsQR } = await import("jsqr");
    const code = jsQR(imageData.data, imageData.width, imageData.height);
    if (!code) return;

    const raw = code.data.trim();
    setQrRaw(raw);
    if (!PID_RE.test(raw)) return;

    const selName = patients.find((p) => p.id === pid)?.성명 ?? pid;
    const decision = decideQr(raw, pid, injections);

    if (decision.kind === "blocked_patient") {
      setQrResult({ type: "blocked_patient", scannedPid: decision.scannedPid, selectedName: selName });
      return;
    }
    if (decision.kind === "blocked_meds") {
      setQrResult({ type: "blocked_meds", patientName: selName, unready: decision.unready });
      return;
    }

    // complete — 쿨다운 + 가드 후 confirmInjection 으로 DB 확정 기록(jeon 미연결 버그 수정)
    if (Date.now() - qrCooldownRef.current < QR_COOLDOWN_MS) return;
    qrCooldownRef.current = Date.now();
    qrConfirmingRef.current = true;
    setQrConfirming(true);
    try {
      await Promise.all(injections.map((i) => confirmInjection(pid, i.id)));
      setInjections((prev) => prev.map((i) => ({ ...i, status: "confirmed" as Injection["status"] })));
      setQrResult({ type: "complete", patientName: selName, injCount: decision.injCount });
      setScanErr("");
    } catch (e) {
      setScanErr("처방 완료 기록 실패: " + String(e));
    } finally {
      setQrConfirming(false);
      qrConfirmingRef.current = false;
    }
  }, [camOn, pid, injections, patients]);

  /* QR 모드 인터벌(300ms) */
  useEffect(() => {
    if (ocrMode === "qr" && camOn) {
      intervalRef.current = setInterval(scanQr, 300);
    } else {
      if (intervalRef.current) { clearInterval(intervalRef.current); intervalRef.current = null; }
    }
    return () => {
      if (intervalRef.current) { clearInterval(intervalRef.current); intervalRef.current = null; }
    };
  }, [ocrMode, camOn, scanQr]);
```
(`captureAndOcr`는 single 모드 `handleScan`이 계속 사용하므로 **삭제하지 않는다** — 이 편집은 realtime effect만 대체.)

- [ ] **Step 4: 모드 토글 버튼(실시간 → QR 환자 확인)**

찾기:
```tsx
              <button
                onClick={() => setOcrMode("realtime")}
                className={`flex-1 py-2 transition-colors ${
                  ocrMode === "realtime" ? "bg-teal text-white" : "text-ink-2 hover:bg-surface-2"
                }`}>
                실시간 OCR
              </button>
```
바꾸기:
```tsx
              <button
                onClick={() => { setOcrMode("qr"); setOcrText(""); setResult(null); }}
                className={`flex-1 py-2 transition-colors ${
                  ocrMode === "qr" ? "bg-teal text-white" : "text-ink-2 hover:bg-surface-2"
                }`}>
                QR 환자 확인
              </button>
```
그리고 단일 버튼의 onClick도 qr 상태 초기화하도록 — 찾기:
```tsx
              <button
                onClick={() => setOcrMode("single")}
                className={`flex-1 py-2 transition-colors ${
                  ocrMode === "single" ? "bg-teal text-white" : "text-ink-2 hover:bg-surface-2"
                }`}>
                단일 스캔
              </button>
```
바꾸기:
```tsx
              <button
                onClick={() => { setOcrMode("single"); setQrRaw(null); setQrResult(null); }}
                className={`flex-1 py-2 transition-colors ${
                  ocrMode === "single" ? "bg-teal text-white" : "text-ink-2 hover:bg-surface-2"
                }`}>
                단일 스캔
              </button>
```

- [ ] **Step 5: 실시간 상태 패널 → QR 결과 패널**

찾기:
```tsx
            {/* 실시간 OCR 상태 표시 */}
            {camOn && ocrMode === "realtime" && (
              <div className="mt-3 flex items-center gap-2 rounded-xl border border-teal/30 bg-teal-soft px-4 py-2.5 text-sm">
                {scanning
                  ? <><Spinner /><span className="text-teal font-semibold">인식 중…</span></>
                  : <><span className="text-teal animate-pulse">●</span><span className="text-teal font-semibold">실시간 OCR 활성</span></>
                }
                <span className="text-ink-3 text-xs ml-auto">2초 간격</span>
              </div>
            )}
```
바꾸기:
```tsx
            {/* QR 환자 확인 상태/결과 */}
            {camOn && ocrMode === "qr" && (
              <div className="mt-3 flex flex-col gap-2">
                {!qrResult && (
                  <div className="flex items-center gap-2 rounded-xl border border-teal/30 bg-teal-soft px-4 py-2.5 text-sm">
                    {qrConfirming
                      ? <><Spinner /><span className="text-teal font-semibold">처방 완료 기록 중…</span></>
                      : <><span className="text-teal animate-pulse">●</span><span className="text-teal font-semibold">환자 QR 인식 대기 중</span></>}
                    <span className="text-ink-3 text-xs ml-auto">환자 선택 후 QR 스캔</span>
                  </div>
                )}

                {qrRaw && (
                  <div className="rounded-xl border border-line bg-surface-2 px-4 py-2 text-xs font-mono">
                    <span className="text-ink-3">QR 감지: </span>
                    <span className="text-teal font-semibold">{qrRaw}</span>
                  </div>
                )}

                {/* Case 1 — 처방 완료 */}
                {qrResult?.type === "complete" && (
                  <div className="rounded-2xl p-4 border bg-green-soft border-green/30">
                    <div className="flex items-center gap-3 mb-2">
                      <MatchIcon />
                      <p className="font-bold text-green text-base">처방 완료</p>
                    </div>
                    <p className="text-ink-2 text-sm leading-relaxed">
                      {qrResult.patientName} 환자의 모든 약품({qrResult.injCount}종)이
                      확인되었습니다. 안전하게 투약을 진행하세요.
                    </p>
                  </div>
                )}

                {/* Case 2 — 처방 불가 (미완료 약품) */}
                {qrResult?.type === "blocked_meds" && (
                  <div className="rounded-2xl p-4 border bg-red-soft border-red/30">
                    <div className="flex items-center gap-3 mb-2">
                      <MismatchIcon />
                      <p className="font-bold text-red text-base">처방 불가</p>
                    </div>
                    <p className="text-ink-2 text-sm leading-relaxed">
                      미확인 약품이 있어 투약이 불가합니다. OCR 검증을 먼저 완료하세요.
                    </p>
                    <ul className="mt-2 space-y-1">
                      {qrResult.unready.map((u, i) => (
                        <li key={i} className="flex items-center gap-2 text-xs">
                          <span className="w-1.5 h-1.5 rounded-full bg-red shrink-0" />
                          <span className="font-semibold text-ink">{u.name}</span>
                          <span className="text-ink-3">
                            {u.status === "pending" ? "투약 대기중" :
                             u.status === "mismatch" ? "약품 불일치" : u.status}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Case 3 — 처방 불가 (환자 정보 불일치) */}
                {qrResult?.type === "blocked_patient" && (
                  <div className="rounded-2xl p-4 border bg-red-soft border-red/30">
                    <div className="flex items-center gap-3 mb-2">
                      <MismatchIcon />
                      <p className="font-bold text-red text-base">처방 불가 — 환자 정보 불일치</p>
                    </div>
                    <p className="text-ink-2 text-sm leading-relaxed">
                      스캔된 QR이 선택된 환자와 다릅니다. 올바른 환자의 QR인지 확인하세요.
                    </p>
                    <div className="mt-2 grid grid-cols-2 gap-2 text-xs">
                      <div className="rounded-lg bg-surface px-3 py-2 border border-line">
                        <p className="text-ink-3 mb-0.5">선택된 환자</p>
                        <p className="font-semibold text-ink">{qrResult.selectedName}</p>
                      </div>
                      <div className="rounded-lg bg-surface px-3 py-2 border border-red/30">
                        <p className="text-ink-3 mb-0.5">스캔된 QR</p>
                        <p className="font-semibold text-red font-mono">{qrResult.scannedPid}</p>
                      </div>
                    </div>
                  </div>
                )}

                {qrResult && (
                  <button
                    onClick={() => { setQrResult(null); setQrRaw(null); qrCooldownRef.current = 0; }}
                    className="text-xs text-ink-3 hover:text-teal underline text-center mt-1 transition-colors">
                    다시 스캔
                  </button>
                )}
              </div>
            )}
```
(이 패널은 `MatchIcon`/`MismatchIcon`/`Spinner`를 쓰는데 셋 다 페이지 하단 보조 컴포넌트에 이미 존재.)

- [ ] **Step 6: OCR 결과 헤더의 realtime 라벨 제거**

찾기:
```tsx
            <h2 className="font-semibold text-ink mb-2 flex items-center gap-2">
              <TextIcon />
              OCR 결과
              {ocrMode === "realtime" && camOn && (
                <span className="ml-auto text-xs text-ink-3 font-normal">실시간 갱신 중</span>
              )}
            </h2>
```
바꾸기:
```tsx
            <h2 className="font-semibold text-ink mb-2 flex items-center gap-2">
              <TextIcon />
              OCR 결과
            </h2>
```

- [ ] **Step 7: 잔존 `realtime` 참조 확인**

Run: `cd web/frontend && grep -n "realtime" app/ocr/page.tsx`
Expected: 출력 없음(모든 realtime 참조 제거됨). 남아 있으면 위 단계에서 누락된 것 — 해당 블록을 qr 기준으로 수정.

- [ ] **Step 8: 타입체크 + 빌드**

Run: `cd web/frontend && npx tsc --noEmit && npm run build`
Expected: 타입 에러 없음, 빌드 성공. (eslint unused 경고가 나면 해당 파일 내에서만 정리: `qrConfirming`은 Step 5 패널에서 사용됨 — 미사용이면 패널 적용 누락.)

- [ ] **Step 9: Commit**

```bash
git add web/frontend/app/ocr/page.tsx
git commit -m "feat(web): 처치실 /ocr 실시간 OCR → QR 환자 확인 모드(complete 시 confirmInjection 기록)"
```

---

## Final Verification

- [ ] **백엔드:** `cd web/backend && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 ./venv/bin/python -m pytest test/test_app_auth.py -q` → confirm 3건 포함 통과
- [ ] **프론트 단위:** `cd web/frontend && npx vitest run` → `ocrQr` 포함 전 통과
- [ ] **프론트 빌드:** `cd web/frontend && npx tsc --noEmit && npm run build` → green
- [ ] **잔존 realtime 없음:** `grep -rn "realtime" web/frontend/app/ocr/page.tsx` → 없음
- [ ] **런타임(사용자):** 서버 기동 → staff 로그인 → /ocr → "QR 환자 확인" 탭. (a) 다른 환자 QR → "처방 불가 — 환자 정보 불일치" (b) 미confirmed 약품 → "처방 불가" + 미준비 목록 (c) 전부 confirmed → "처방 완료" + DB의 injections.status 가 confirmed/"QR 환자 확인" 으로 기록됨 확인. single 탭·setOcrDone 완료신호 종전대로.

---

## Self-Review Notes

**Spec coverage:** §5.1 decideQr→T1; §5.2 confirmInjection→T2; §5.4 confirm 라우트→T3; §5.3 페이지 realtime→qr·complete 시 confirmInjection→T4; §3 setOcrDone 유지→T4(삭제 안 함 명시); §8 테스트→T1·T3. 전부 매핑.

**Type consistency:** `decideQr(scannedPid, selectedPid, injections): QrDecision`(T1) ↔ 페이지 사용(T4 Step3) 일치. `QrDecision.kind`("blocked_patient"|"blocked_meds"|"complete") ↔ 페이지 분기 일치. 페이지 표시형 `QrResult.type`(complete|blocked_meds|blocked_patient)은 패널(T4 Step5)과 일치. `confirmInjection(pid, inj_id): Promise<{ok,status}>`(T2) ↔ 페이지 `Promise.all(injections.map(i => confirmInjection(pid, i.id)))`(T4) 일치. 백엔드 `update_injection_status(pid, inj_id, "confirmed", "QR 환자 확인")`(T3) ↔ pytest 인자 검증(T3) 일치.

**Guardrails:** `captureAndOcr`·single 자동검증·`setOcrDone` 보존(삭제 금지 명시). 프록시/iOS/next.config 비범위. 런타임 로봇 구동은 사용자.
