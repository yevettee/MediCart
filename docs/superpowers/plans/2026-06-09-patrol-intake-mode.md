# 순회 문진 모드 (Patrol Intake Mode) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 의료진 이상 등급이 홈에서 "순회 문진 시작"을 누르면 로봇이 101호 1·2번 병상을 순차 순회하며 QR 스캔으로 순회당 1회 문진을 자동 수행하고 홈 복귀·도킹한다.

**Architecture:** 브라우저가 단일 풀스크린 오버레이 상태머신(`PatrolIntakeOverlay`)으로 전체 흐름을 오케스트레이션한다. goto는 기존 `pushMission`, 도착은 pose 근접(`nearestArrival`), 문진 분기는 RTDB `patients/{pid}/intake_done` 회차 플래그. QR 스캔과 문진표는 기존 페이지에서 추출한 재사용 훅/컴포넌트를 오버레이 안에서 단계로 렌더한다.

**Tech Stack:** Next.js 16 App Router (web/frontend), Flask (web/backend), Firebase RTDB, vitest, pytest.

---

## File Structure

**Backend (web/backend/):**
- `fb_read.py` — Modify: add `_intake_reset_updates`, `reset_intake_flags`, `mark_intake_done`
- `patients.py` — Modify: `patient_node_to_api` exposes `intake_done`
- `auth.py` — Modify: add `/api/patrol` to `_STAFF_PREFIXES`
- `app.py` — Modify: add `POST /api/patrol/reset`, `POST /api/patrol/intake-done`
- `test/test_fb_read.py`, `test/test_patients.py`, `test/test_app_auth.py` — Modify: add tests

**Frontend (web/frontend/):**
- `lib/patrol.ts` — Create: pure state-machine helpers
- `lib/patrol.test.ts` — Create: vitest
- `lib/api.ts` — Modify: `resetIntakeRound`, `markIntakeDone`, `Patient.intake_done`
- `lib/useQrScanner.ts` — Create: webcam+jsQR hook (extracted from qr page)
- `app/qr/page.tsx` — Modify: use the hook (no behavior change)
- `components/IntakeForm.tsx` — Create: shared `SECTIONS`/`FieldInput`/`IntakeFields` + staff `IntakeForm`
- `app/intake/page.tsx` — Modify: import shared field defs (no behavior change)
- `components/PatrolIntakeOverlay.tsx` — Create: the state machine overlay
- `app/page.tsx` — Modify: add "순회 문진 시작" button (staff+) wiring the overlay

> **Next.js note:** `web/frontend/AGENTS.md` warns this Next.js (16.2.7, App Router) differs from training data. Before editing any `app/` or component file, consult `node_modules/next/dist/docs/` for the relevant API (client components, `useSearchParams`/`Suspense`, etc.).

---

## Task 1: Backend — expose `intake_done` on patient API

**Files:**
- Modify: `web/backend/patients.py:9-18`
- Test: `web/backend/test/test_patients.py`

- [ ] **Step 1: Write the failing test**

Append to `web/backend/test/test_patients.py`:
```python
def test_patient_node_exposes_intake_done_true():
    out = patients.patient_node_to_api("P-2024-0001", {"info": {}, "intake_done": True})
    assert out["intake_done"] is True


def test_patient_node_intake_done_defaults_false():
    out = patients.patient_node_to_api("P-2024-0001", {"info": {}})
    assert out["intake_done"] is False
```
(If `test_patients.py` does not already `import patients`, add `import patients` at the top following the existing import style in that file.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web/backend && python -m pytest test/test_patients.py -q`
Expected: FAIL — `KeyError: 'intake_done'`

- [ ] **Step 3: Implement**

In `web/backend/patients.py`, in `patient_node_to_api`, add before `return out`:
```python
    out["intake_done"] = bool(node.get("intake_done"))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web/backend && python -m pytest test/test_patients.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add web/backend/patients.py web/backend/test/test_patients.py
git commit -m "feat(web): expose intake_done on patient API"
```

---

## Task 2: Backend — RTDB intake-flag helpers

**Files:**
- Modify: `web/backend/fb_read.py` (add helpers near `save_intake`/`get_intake`, ~line 378)
- Test: `web/backend/test/test_fb_read.py`

- [ ] **Step 1: Write the failing test**

Append to `web/backend/test/test_fb_read.py`:
```python
def test_intake_reset_updates_builds_false_map():
    raw = {"P-2024-0001": {"info": {}}, "P-2024-0002": {"info": {}}}
    upd = fb_read._intake_reset_updates(raw)
    assert upd == {"P-2024-0001/intake_done": False, "P-2024-0002/intake_done": False}


def test_intake_reset_updates_empty():
    assert fb_read._intake_reset_updates(None) == {}
    assert fb_read._intake_reset_updates({}) == {}


def test_mark_intake_done_rejects_bad_pid():
    assert fb_read.mark_intake_done("not-a-pid") is False
```
(If `test_fb_read.py` does not already `import fb_read`, add it at the top following the existing import style.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web/backend && python -m pytest test/test_fb_read.py -q`
Expected: FAIL — `AttributeError: module 'fb_read' has no attribute '_intake_reset_updates'`

- [ ] **Step 3: Implement**

In `web/backend/fb_read.py`, add after `get_intake` (end of file region near line 386):
```python
# ── 순회 문진 회차 플래그 (patients/{pid}/intake_done) ────────────────────────
def _intake_reset_updates(raw):
    """patients get() 결과 → {pid/intake_done: False} 멀티패스 업데이트 dict(순수)."""
    return {f"{pid}/intake_done": False for pid in (raw or {}).keys()}


def reset_intake_flags():
    """순회 시작 — 전 환자 intake_done=False 일괄 리셋. 리셋된 환자 수 반환."""
    ref = _init().reference("patients")
    updates = _intake_reset_updates(ref.get() or {})
    if updates:
        ref.update(updates)
    return len(updates)


def mark_intake_done(pid):
    """문진 완료 — 해당 환자 intake_done=True. 잘못된 pid면 False."""
    if not valid_pid(pid):
        return False
    _init().reference(f"patients/{pid}/intake_done").set(True)
    return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web/backend && python -m pytest test/test_fb_read.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add web/backend/fb_read.py web/backend/test/test_fb_read.py
git commit -m "feat(web): intake-flag RTDB helpers (reset/mark)"
```

---

## Task 3: Backend — patrol routes (staff+)

**Files:**
- Modify: `web/backend/auth.py:12`
- Modify: `web/backend/app.py` (add routes after `targets`/`rooms` region, ~line 346)
- Test: `web/backend/test/test_app_auth.py`

- [ ] **Step 1: Write the failing test**

Append to `web/backend/test/test_app_auth.py`:
```python
def test_patrol_reset_requires_staff(monkeypatch):
    monkeypatch.setattr(flask_app.fb_read, "reset_intake_flags", lambda: 3)
    client.set_cookie("intel_auth", "")           # patient
    assert client.post("/api/patrol/reset").status_code == 401
    client.set_cookie("intel_auth", "STAFFTOK")   # staff
    r = client.post("/api/patrol/reset")
    assert r.status_code == 200 and r.get_json() == {"ok": True, "count": 3}


def test_patrol_intake_done(monkeypatch):
    seen = {}
    monkeypatch.setattr(flask_app.fb_read, "mark_intake_done",
                        lambda pid: seen.setdefault("pid", pid) or True)
    client.set_cookie("intel_auth", "STAFFTOK")
    r = client.post("/api/patrol/intake-done", json={"pid": "P-2024-0001"})
    assert r.status_code == 200 and r.get_json()["ok"] is True
    assert seen["pid"] == "P-2024-0001"


def test_patrol_intake_done_bad_pid(monkeypatch):
    monkeypatch.setattr(flask_app.fb_read, "mark_intake_done", lambda pid: False)
    client.set_cookie("intel_auth", "STAFFTOK")
    assert client.post("/api/patrol/intake-done", json={"pid": "x"}).status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web/backend && python -m pytest test/test_app_auth.py -q`
Expected: FAIL — patrol routes 404 (and `/api/patrol/reset` returns 401 for staff because it currently maps to admin).

- [ ] **Step 3: Implement auth prefix + routes**

In `web/backend/auth.py` line 12, add `/api/patrol` to staff prefixes:
```python
_STAFF_PREFIXES = ("/api/patients", "/api/ocr", "/api/patrol")
```

In `web/backend/app.py`, add after the `rooms()` route (around line 351):
```python
# ── 순회 문진 (회차 플래그) ───────────────────────────────────────────────────
@app.post("/api/patrol/reset")
def patrol_reset():
    return jsonify({"ok": True, "count": fb_read.reset_intake_flags()})


@app.post("/api/patrol/intake-done")
def patrol_intake_done():
    body = request.get_json(force=True, silent=True) or {}
    if fb_read.mark_intake_done(str(body.get("pid") or "")):
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "invalid pid"}), 400
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web/backend && python -m pytest test/ -q`
Expected: PASS (whole backend suite green)

- [ ] **Step 5: Commit**

```bash
git add web/backend/auth.py web/backend/app.py web/backend/test/test_app_auth.py
git commit -m "feat(web): patrol reset/intake-done routes (staff+)"
```

---

## Task 4: Frontend — patrol pure logic

**Files:**
- Create: `web/frontend/lib/patrol.ts`
- Test: `web/frontend/lib/patrol.test.ts`

- [ ] **Step 1: Write the failing test**

Create `web/frontend/lib/patrol.test.ts`:
```ts
import { describe, expect, it } from "vitest";
import { PATROL_STOPS, decideAfterScan, nextStop } from "./patrol";

describe("decideAfterScan", () => {
  it("needs intake when not done", () => {
    expect(decideAfterScan({ intake_done: false })).toBe("intake");
  });
  it("skips when already done", () => {
    expect(decideAfterScan({ intake_done: true })).toBe("skip");
  });
  it("treats missing flag as needing intake", () => {
    expect(decideAfterScan({})).toBe("intake");
  });
  it("unknown when patient missing", () => {
    expect(decideAfterScan(null)).toBe("unknown");
  });
});

describe("nextStop", () => {
  it("advances to next index", () => {
    expect(nextStop(0, 2)).toBe(1);
  });
  it("returns 'return' after last stop", () => {
    expect(nextStop(1, 2)).toBe("return");
  });
});

describe("PATROL_STOPS", () => {
  it("is the two 101호 beds in order", () => {
    expect(PATROL_STOPS).toEqual(["t101_1", "t101_2"]);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web/frontend && npx vitest run lib/patrol.test.ts`
Expected: FAIL — cannot resolve `./patrol`

- [ ] **Step 3: Implement**

Create `web/frontend/lib/patrol.ts`:
```ts
// 순회 문진 순수 로직(의존성 0 — vitest 단위테스트). 오버레이 상태머신이 사용.

// 정류장 키(= /api/targets 의 키). 라벨은 targets 에서 가져온다.
export const PATROL_STOPS = ["t101_1", "t101_2"] as const;

// 스캔된 환자 → 다음 동작 분기.
//   intake : 문진표로 (intake_done=false 또는 미설정)
//   skip   : 다음 호실 (intake_done=true)
//   unknown: 미등록 QR (환자 조회 실패) — 계속 스캔 대기
export function decideAfterScan(
  p: { intake_done?: boolean } | null,
): "intake" | "skip" | "unknown" {
  if (!p) return "unknown";
  return p.intake_done ? "skip" : "intake";
}

// 현재 정류장 인덱스 → 다음 인덱스 또는 복귀 신호.
export function nextStop(idx: number, total: number): number | "return" {
  return idx + 1 < total ? idx + 1 : "return";
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web/frontend && npx vitest run lib/patrol.test.ts`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add web/frontend/lib/patrol.ts web/frontend/lib/patrol.test.ts
git commit -m "feat(web): patrol pure state-machine helpers"
```

---

## Task 5: Frontend — api client for patrol

**Files:**
- Modify: `web/frontend/lib/api.ts` (Patient type ~line 51; add fns near `saveMode` ~line 108)

- [ ] **Step 1: Add `intake_done` to Patient type**

In `web/frontend/lib/api.ts`, inside `export type Patient = {` add after `intake?: unknown;`:
```ts
  intake_done?: boolean;
```

- [ ] **Step 2: Add patrol API functions**

In `web/frontend/lib/api.ts`, after `saveMode(...)` (around line 108), add:
```ts
// ── 순회 문진 회차 플래그 ────────────────────────────────────────────────────
export async function resetIntakeRound(): Promise<{ ok: boolean; count: number }> {
  const r = await fetch(`${API_BASE}/api/patrol/reset`, {
    method: "POST", credentials: "include",
  });
  if (!r.ok) throw new Error(`/api/patrol/reset → ${r.status}`);
  return r.json();
}

export async function markIntakeDone(pid: string): Promise<{ ok: boolean }> {
  const r = await fetch(`${API_BASE}/api/patrol/intake-done`, {
    method: "POST", credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ pid }),
  });
  if (!r.ok) throw new Error(`/api/patrol/intake-done → ${r.status}`);
  return r.json();
}
```

- [ ] **Step 3: Typecheck**

Run: `cd web/frontend && npx tsc --noEmit`
Expected: no errors

- [ ] **Step 4: Commit**

```bash
git add web/frontend/lib/api.ts
git commit -m "feat(web): patrol api client (resetIntakeRound, markIntakeDone)"
```

---

## Task 6: Frontend — extract `useQrScanner` hook

**Files:**
- Create: `web/frontend/lib/useQrScanner.ts`
- Modify: `web/frontend/app/qr/page.tsx`

Goal: move the webcam-open + jsQR decode loop into a reusable hook with **no behavior change** to `/qr`. The hook calls `onDecode(raw)` with every decoded string; PID validation, cooldown, and `setDisplayPatient` stay in the page.

- [ ] **Step 1: Create the hook**

Create `web/frontend/lib/useQrScanner.ts`:
```ts
"use client";
import { useCallback, useEffect, useRef, useState } from "react";

// 웹캠(USB 외장 우선) 열고 jsQR 로 주기 디코드 → onDecode(raw) 콜백.
// PID 형식 검증·쿨다운·전송은 호출측 책임(이 훅은 순수 카메라+디코드).
export function useQrScanner(
  onDecode: (raw: string) => void,
  opts?: { intervalMs?: number },
) {
  const intervalMs = opts?.intervalMs ?? 300;
  const videoRef = useRef<HTMLVideoElement>(null);
  const [camOn, setCamOn] = useState(false);
  const [camErr, setCamErr] = useState("");
  const [camInfo, setCamInfo] = useState("");
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const onDecodeRef = useRef(onDecode);
  onDecodeRef.current = onDecode;

  const start = useCallback(async () => {
    setCamErr("");
    try {
      const tempStream = await navigator.mediaDevices.getUserMedia({ video: true });
      const devices = await navigator.mediaDevices.enumerateDevices();
      const cams = devices.filter((d) => d.kind === "videoinput");
      const usbCam = cams.find((d) => !/integrated|facetime|built.?in/i.test(d.label));
      const tempDeviceId = tempStream.getVideoTracks()[0]?.getSettings()?.deviceId;
      let stream = tempStream;
      if (usbCam && tempDeviceId !== usbCam.deviceId) {
        tempStream.getTracks().forEach((t) => t.stop());
        stream = await navigator.mediaDevices.getUserMedia({
          video: { deviceId: { exact: usbCam.deviceId }, width: 1280, height: 720 },
        });
      }
      const v = videoRef.current;
      if (v) {
        v.srcObject = stream;
        setCamOn(true);
        await v.play();
        setCamInfo(stream.getVideoTracks()[0]?.label || "카메라");
      }
    } catch {
      setCamErr("웹캠을 열 수 없습니다. 브라우저 권한을 확인하세요.");
    }
  }, []);

  const stop = useCallback(() => {
    const v = videoRef.current;
    const s = (v?.srcObject as MediaStream | null) ?? null;
    s?.getTracks().forEach((t) => t.stop());
    if (v) v.srcObject = null;
    setCamOn(false);
  }, []);

  const scanFrame = useCallback(async () => {
    const v = videoRef.current;
    if (!v || !camOn || !v.videoWidth || !v.videoHeight) return;
    const canvas = document.createElement("canvas");
    canvas.width = v.videoWidth;
    canvas.height = v.videoHeight;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.drawImage(v, 0, 0);
    const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
    const { default: jsQR } = await import("jsqr");
    const code = jsQR(imageData.data, imageData.width, imageData.height);
    if (code) onDecodeRef.current(code.data.trim());
  }, [camOn]);

  useEffect(() => {
    if (camOn) intervalRef.current = setInterval(scanFrame, intervalMs);
    return () => {
      if (intervalRef.current) { clearInterval(intervalRef.current); intervalRef.current = null; }
    };
  }, [camOn, scanFrame, intervalMs]);

  // 언마운트 시 카메라 정리
  useEffect(() => () => { stop(); }, [stop]);

  return { videoRef, camOn, camErr, camInfo, start, stop };
}
```

- [ ] **Step 2: Refactor `app/qr/page.tsx` to use the hook**

Replace the top of `QrPage` — remove the local `startCam`/`scanFrame`/interval effect and the `videoRef`/`camOn`/`camErr`/`camInfo`/`intervalRef`/`scanningRef` state, and wire the hook. Concretely:

Add import:
```ts
import { useQrScanner } from "@/lib/useQrScanner";
```

Replace the camera state declarations and `startCam`/`scanFrame`/interval effect with the hook + an `onDecode` that keeps the existing PID/cooldown/send logic:
```ts
  const cooldownRef = useRef<number>(0);
  const scanningRef = useRef(false);
  const [lastPid, setLastPid] = useState("");
  const [lastPatient, setLastPatient] = useState<Patient | null>(null);
  const [sending, setSending] = useState(false);
  const [sendErr, setSendErr] = useState("");
  const [rawQr, setRawQr] = useState<string | null>(null);

  const onDecode = useCallback(async (raw: string) => {
    if (Date.now() - cooldownRef.current < COOLDOWN_MS) return;
    setRawQr(raw);
    if (!PID_RE.test(raw)) return;
    cooldownRef.current = Date.now();
    if (scanningRef.current) return;
    scanningRef.current = true;
    setSending(true); setSendErr("");
    try {
      await setDisplayPatient(raw);
      setLastPid(raw);
      const p = await getPatient(raw).catch(() => null);
      setLastPatient(p);
    } catch (e) {
      setSendErr(String(e));
    } finally {
      setSending(false);
      scanningRef.current = false;
    }
  }, []);

  const { videoRef, camOn, camErr, camInfo, start: startCam } = useQrScanner(onDecode);
```
Keep the existing JSX (it already references `videoRef`, `camOn`, `camErr`, `camInfo`, `startCam`, `sending`, `sendErr`, `rawQr`, `lastPid`, `lastPatient`). Remove now-unused imports (`useEffect` if unused) and the old `SCAN_INTERVAL_MS` constant is no longer needed (hook defaults to 300ms) — delete it. Ensure `useCallback`/`useRef`/`useState` remain imported.

- [ ] **Step 3: Typecheck + build**

Run: `cd web/frontend && npx tsc --noEmit && npm run build`
Expected: no type errors; build succeeds.

- [ ] **Step 4: Manual smoke (user, optional now)**

`/qr` 페이지에서 "웹캠 켜기" → QR 인식 → 디스플레이 전송이 종전과 동일해야 한다. (런타임 확인은 사용자가 수행)

- [ ] **Step 5: Commit**

```bash
git add web/frontend/lib/useQrScanner.ts web/frontend/app/qr/page.tsx
git commit -m "refactor(web): extract useQrScanner hook from /qr page"
```

---

## Task 7: Frontend — extract shared intake fields + staff `IntakeForm`

**Files:**
- Create: `web/frontend/components/IntakeForm.tsx`
- Modify: `web/frontend/app/intake/page.tsx`

Goal: move the shared field definitions (`SECTIONS`, `FieldInput`, `today`) into a component module and expose `IntakeFields` (the cards renderer) plus a self-contained staff `IntakeForm` (pid → `addVisit` → `onSaved`) for the overlay. `/intake` page keeps identical behavior, just sourcing fields from the shared module.

- [ ] **Step 1: Create `components/IntakeForm.tsx`**

Create `web/frontend/components/IntakeForm.tsx` (move `Field`, `SECTIONS`, `today`, `FieldInput` verbatim from `app/intake/page.tsx`, then add `IntakeFields` and `IntakeForm`):
```tsx
"use client";
import { useState } from "react";
import { addVisit } from "@/lib/api";

type Field =
  | { id: string; label: string; type: "text" | "textarea" | "number" | "date" }
  | { id: string; label: string; type: "select" | "radio"; options: string[] }
  | { id: string; label: string; type: "scale"; max: number };

export const SECTIONS: { n: string; title: string; fields: Field[] }[] = [
  { n: "01", title: "내원 정보", fields: [
    { id: "방문일", label: "방문일", type: "date" },
    { id: "진료유형", label: "진료유형", type: "radio", options: ["초진", "재진"] },
    { id: "진료과", label: "진료과", type: "text" },
  ]},
  { n: "02", title: "주호소 (CC)", fields: [
    { id: "주호소(CC)", label: "주호소 / 내원 사유", type: "textarea" },
    { id: "증상 발생시기_경과", label: "증상 발생시기 / 경과", type: "text" },
    { id: "통증부위", label: "통증 부위", type: "text" },
    { id: "통증점수", label: "통증 점수 (NRS)", type: "scale", max: 10 },
  ]},
  { n: "03", title: "생체징후", fields: [
    { id: "수축기혈압", label: "수축기혈압 (mmHg)", type: "number" },
    { id: "이완기혈압", label: "이완기혈압 (mmHg)", type: "number" },
    { id: "맥박", label: "맥박 (bpm)", type: "number" },
    { id: "호흡", label: "호흡 (/min)", type: "number" },
    { id: "체온", label: "체온 (℃)", type: "number" },
    { id: "SpO2", label: "SpO₂ (%)", type: "number" },
    { id: "의식상태", label: "의식상태", type: "select", options: ["명료", "기면", "혼미", "반혼수", "혼수"] },
    { id: "낙상위험", label: "낙상위험", type: "select", options: ["하", "중", "고"] },
  ]},
  { n: "04", title: "간호 / 기타", fields: [
    { id: "금일 복약 여부", label: "금일 복약 여부", type: "select", options: ["복용", "미복용", "해당없음"] },
    { id: "최근 발열_감염노출", label: "최근 발열 / 감염 노출", type: "text" },
    { id: "최근 검사_예정 검사", label: "최근 / 예정 검사", type: "text" },
    { id: "보고 필요", label: "의료진 보고 필요", type: "radio", options: ["N", "Y"] },
    { id: "간호 관찰사항", label: "간호 관찰사항", type: "textarea" },
    { id: "작성 간호사", label: "작성 간호사", type: "text" },
  ]},
];

export const today = () => new Date().toISOString().slice(0, 10);

export function FieldInput(
  { f, value, set }: { f: Field; value: unknown; set: (id: string, v: unknown) => void },
) {
  if (f.type === "text" || f.type === "number" || f.type === "date")
    return <input className="field" type={f.type} value={(value as string) ?? ""} onChange={(e) => set(f.id, e.target.value)} />;
  if (f.type === "textarea")
    return <textarea className="field min-h-[78px] resize-y" value={(value as string) ?? ""} onChange={(e) => set(f.id, e.target.value)} />;
  if (f.type === "select")
    return (
      <select className="field" value={(value as string) ?? ""} onChange={(e) => set(f.id, e.target.value)}>
        <option value="">선택</option>
        {f.options.map((o) => <option key={o} value={o}>{o}</option>)}
      </select>
    );
  if (f.type === "radio")
    return (
      <div className="flex flex-wrap gap-2">
        {f.options.map((o) => {
          const on = value === o;
          return <button key={o} type="button" onClick={() => set(f.id, o)}
            className={`px-3.5 py-1.5 rounded-lg text-[13px] font-medium border transition-colors ${on ? "bg-teal text-white border-teal" : "bg-surface-2 text-ink-2 border-line hover:border-teal"}`}>{o}</button>;
        })}
      </div>
    );
  if (f.type === "scale") {
    const cur = Number(value ?? -1);
    return (
      <div className="flex flex-wrap gap-1.5">
        {Array.from({ length: f.max + 1 }, (_, i) => (
          <button key={i} type="button" onClick={() => set(f.id, String(i))}
            className={`w-8 h-8 rounded-lg mono text-[13px] font-semibold border transition-colors ${cur === i ? "bg-teal text-white border-teal" : "bg-surface-2 text-ink-2 border-line hover:border-teal"}`}>{i}</button>
        ))}
      </div>
    );
  }
  return null;
}

// 공유 폼 본문(섹션 카드). 페이지/오버레이가 같은 필드를 렌더.
export function IntakeFields(
  { form, set }: { form: Record<string, unknown>; set: (id: string, v: unknown) => void },
) {
  return (
    <div className="flex flex-col gap-4 mt-6">
      {SECTIONS.map((sec) => (
        <section key={sec.n} className="card p-6 rise">
          <div className="flex items-center gap-3 mb-4">
            <span className="mono text-[12px] text-teal-600 bg-teal-soft rounded-md px-2 py-0.5 font-semibold">{sec.n}</span>
            <h2 className="text-[16px] font-bold">{sec.title}</h2>
          </div>
          <div className="grid grid-cols-2 gap-x-5 gap-y-4">
            {sec.fields.map((f) => (
              <div key={f.id} className={f.type === "textarea" ? "col-span-2" : ""}>
                <label className="block text-[12.5px] font-semibold text-ink-2 mb-1.5">{f.label}</label>
                <FieldInput f={f} value={form[f.id]} set={set} />
              </div>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}

// 오버레이용 자기완결 의료진 폼: pid 의 새 외래방문 기록 추가 → onSaved.
export default function IntakeForm(
  { pid, prefillDept, onSaved }: { pid: string; prefillDept?: string; onSaved?: () => void },
) {
  const [form, setForm] = useState<Record<string, unknown>>({ 방문일: today(), 진료과: prefillDept || "" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(false);
  const set = (id: string, v: unknown) => { setForm((f) => ({ ...f, [id]: v })); setErr(false); };

  async function submit() {
    if (!pid || busy) return;
    setBusy(true); setErr(false);
    try {
      const r = await addVisit(pid, { ...form, 방문일: form.방문일 || today() });
      if (r?.ok) { onSaved?.(); } else { setErr(true); }
    } catch { setErr(true); }
    finally { setBusy(false); }
  }

  return (
    <div className="w-full max-w-[880px] mx-auto">
      <IntakeFields form={form} set={set} />
      <div className="mt-5 flex items-center justify-end gap-3">
        {err && <span className="pill bg-red-soft text-red"><span className="dot bg-red" /> 저장 실패</span>}
        <button onClick={submit} disabled={busy}
          className="bg-teal text-white font-semibold text-[14px] px-6 py-2.5 rounded-xl hover:bg-teal-600 transition-colors disabled:opacity-40 shadow-[0_6px_16px_-6px_rgba(12,163,154,.6)]">
          {busy ? "저장 중…" : "문진 저장 후 다음"}
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Refactor `app/intake/page.tsx` to import shared fields**

In `app/intake/page.tsx`:
1. Delete the local `Field` type, `SECTIONS`, `today`, and `FieldInput` definitions.
2. Add import: `import { SECTIONS, today, FieldInput, IntakeFields } from "@/components/IntakeForm";`
3. Replace the inline `<div className="flex flex-col gap-4 mt-6">{SECTIONS.map(...)}</div>` block in the returned JSX with `<IntakeFields form={form} set={set} />`.

(The page's role logic, patient selector, polling, and both submit paths stay unchanged. `FieldInput` import may be unused after using `IntakeFields` — if so, drop it from the import to satisfy eslint. `SECTIONS`/`today` remain used.)

- [ ] **Step 3: Typecheck + build**

Run: `cd web/frontend && npx tsc --noEmit && npm run build`
Expected: no type errors; build succeeds.

- [ ] **Step 4: Manual smoke (user, optional now)**

`/intake` 페이지가 환자/의료진 양쪽에서 종전과 동일하게 렌더·저장되어야 한다.

- [ ] **Step 5: Commit**

```bash
git add web/frontend/components/IntakeForm.tsx web/frontend/app/intake/page.tsx
git commit -m "refactor(web): extract shared intake fields + staff IntakeForm"
```

---

## Task 8: Frontend — `PatrolIntakeOverlay` state machine

**Files:**
- Create: `web/frontend/components/PatrolIntakeOverlay.tsx`

Implements the full flow: intro → (per stop: moving → scanning → intake|skip|timeout) → returning → done, with an always-present 중단 button. Reuses `useQrScanner`, `IntakeForm`, `nearestArrival`, `pushMission`, `getPatient`, `resetIntakeRound`, `markIntakeDone`.

- [ ] **Step 1: Create the overlay**

Create `web/frontend/components/PatrolIntakeOverlay.tsx`:
```tsx
"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { API_BASE, getPatient, markIntakeDone, pushMission, resetIntakeRound, type GotoTarget } from "@/lib/api";
import { nearestArrival, type ArrivalTarget, type Pt } from "@/lib/follow";
import { PATROL_STOPS, decideAfterScan, nextStop } from "@/lib/patrol";
import { useQrScanner } from "@/lib/useQrScanner";
import IntakeForm from "@/components/IntakeForm";

const PID_RE = /^P-\d{4}-\d{4}$/;
const QR_WAIT_MS = 60_000;     // 호실당 QR 대기
const TIMEOUT_DWELL_MS = 5_000; // 시간초과 메시지 후 다음 호실
const MSG_DWELL_MS = 2_500;     // intro/skip 메시지
const ARRIVE_TIMEOUT_MS = 90_000;

type Step =
  | "intro" | "moving" | "moveDelay" | "scanning"
  | "intake" | "skip" | "timeout" | "returning" | "done";

type Props = { active: boolean; ns: string; targets: Record<string, GotoTarget>; onExit: () => void };

export default function PatrolIntakeOverlay({ active, ns, targets, onExit }: Props) {
  const [step, setStep] = useState<Step>("intro");
  const [idx, setIdx] = useState(0);
  const [pose, setPose] = useState<Pt | undefined>();
  const [isDocked, setIsDocked] = useState<boolean | undefined>();
  const [pid, setPid] = useState<string>("");
  const [note, setNote] = useState<string>("");
  const stepRef = useRef<Step>("intro");
  stepRef.current = step;
  const idxRef = useRef(0);
  idxRef.current = idx;

  const stopKey = PATROL_STOPS[idx];
  const stopTarget = targets[stopKey];
  const stopLabel = stopTarget?.label ?? `정류장 ${idx + 1}`;
  const dock = targets["dock"] ?? { label: "도크", x: -8, y: -6, yaw: 0 };

  // QR 디코드 → 환자 분기 (scanning 단계에서만)
  const onDecode = useCallback(async (raw: string) => {
    if (stepRef.current !== "scanning" || !PID_RE.test(raw)) return;
    setStep("scanning"); // 유지
    const p = await getPatient(raw).catch(() => null);
    const decision = decideAfterScan(p);
    if (decision === "unknown") { setNote(`등록되지 않은 QR: ${raw}`); return; }
    setPid(raw);
    if (decision === "skip") { setNote(`${p?.성명 ?? raw} — 이미 문진 완료`); setStep("skip"); }
    else { setNote(""); setStep("intake"); }
  }, []);

  const { videoRef, camOn, camErr, start: startCam, stop: stopCam } = useQrScanner(onDecode);

  // SSE 자가 구독(active 동안). pose/dock 수신.
  useEffect(() => {
    if (!active) return;
    const es = new EventSource(`${API_BASE}/api/stream`, { withCredentials: true });
    es.onopen = () => { setStep("intro"); setIdx(0); setPose(undefined); setIsDocked(undefined); setNote(""); };
    es.onmessage = (e) => {
      try {
        const d = JSON.parse(e.data);
        if (d?.source !== ns) return;
        if (d.pose) setPose({ x: d.pose.x, y: d.pose.y });
        if (d.dock) setIsDocked(d.dock.is_docked);
      } catch { /* ignore */ }
    };
    return () => es.close();
  }, [active, ns]);

  // intro → 순회 시작(회차 리셋) → 첫 이동
  useEffect(() => {
    if (!active || step !== "intro") return;
    let alive = true;
    resetIntakeRound().catch(() => {});
    const t = setTimeout(() => { if (alive) setStep("moving"); }, MSG_DWELL_MS);
    return () => { alive = false; clearTimeout(t); };
  }, [active, step]);

  // moving → goto 발행 + 도착(반경) 대기 + 지연 워치독
  useEffect(() => {
    if (step !== "moving") return;
    const tgt = targets[PATROL_STOPS[idxRef.current]];
    if (tgt) pushMission(ns, "goto", { x: tgt.x, y: tgt.y, yaw: tgt.yaw ?? 0 }).catch(() => {});
    const wd = setTimeout(() => { if (stepRef.current === "moving") setStep("moveDelay"); }, ARRIVE_TIMEOUT_MS);
    return () => clearTimeout(wd);
  }, [step, ns, targets]);

  // pose 갱신마다 현재 타겟 근접판정 → 도착 시 scanning
  useEffect(() => {
    if (step !== "moving") return;
    if (!stopTarget) return;
    const at: ArrivalTarget[] = [{ key: stopKey, label: stopLabel, x: stopTarget.x, y: stopTarget.y }];
    if (nearestArrival(pose, at, null)) setStep("scanning");
  }, [step, pose, stopTarget, stopKey, stopLabel]);

  // scanning 진입 시 카메라 ON + 60s 타임아웃, 떠날 때 카메라 OFF
  useEffect(() => {
    if (step !== "scanning") return;
    setNote("");
    startCam();
    const to = setTimeout(() => { if (stepRef.current === "scanning") setStep("timeout"); }, QR_WAIT_MS);
    return () => { clearTimeout(to); stopCam(); };
  }, [step, startCam, stopCam]);

  // skip / timeout 메시지 후 다음 정류장
  useEffect(() => {
    if (step !== "skip" && step !== "timeout") return;
    const dwell = step === "timeout" ? TIMEOUT_DWELL_MS : MSG_DWELL_MS;
    const t = setTimeout(() => advance(), dwell);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step]);

  // returning 완료(도킹) → done
  useEffect(() => {
    if (step === "returning" && isDocked === true) { setStep("done"); }
  }, [step, isDocked]);

  useEffect(() => { if (step === "done") onExit(); }, [step, onExit]);

  const advance = useCallback(() => {
    const n = nextStop(idxRef.current, PATROL_STOPS.length);
    if (n === "return") { startReturn(); }
    else { setIdx(n); setNote(""); setPid(""); setStep("moving"); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const startReturn = useCallback(() => {
    setStep("returning");
    pushMission(ns, "goto", { x: dock.x, y: dock.y, yaw: dock.yaw ?? 0, dock_after: true }).catch(() => {});
  }, [ns, dock]);

  const onIntakeSaved = useCallback(() => {
    if (pid) markIntakeDone(pid).catch(() => {});
    setNote("문진 저장 완료");
    advance();
  }, [pid, advance]);

  const abort = useCallback(() => {
    pushMission(ns, "mission_cancel", {}).catch(() => {});
    startReturn();
  }, [ns, startReturn]);

  if (!active) return null;

  return (
    <div className="fixed inset-0 z-50 bg-[#0b1f1d] text-white overflow-auto">
      {step === "intake" ? (
        <div className="min-h-full bg-surface text-ink p-7">
          <div className="max-w-[880px] mx-auto">
            <div className="eyebrow">순회 문진 · {stopLabel}</div>
            <h1 className="text-[24px] font-bold mt-1 mb-2">{pid} 문진표 작성</h1>
            <IntakeForm pid={pid} onSaved={onIntakeSaved} />
          </div>
        </div>
      ) : step === "scanning" ? (
        <div className="min-h-full grid place-items-center p-8">
          <div className="w-full max-w-[560px] text-center">
            <div className="text-[clamp(22px,4vw,40px)] font-bold mb-2">{stopLabel} — 환자 QR을 스캔해 주세요</div>
            <div className="text-white/60 mb-6">1분 내 미스캔 시 다음 호실로 이동합니다</div>
            <video ref={videoRef} className="w-full rounded-2xl bg-black" autoPlay muted playsInline />
            {camErr && <p className="text-red-300 mt-3">{camErr}</p>}
            {!camOn && !camErr && <p className="text-white/60 mt-3">카메라 준비 중…</p>}
            {note && <p className="text-amber-200 mt-3">{note}</p>}
          </div>
        </div>
      ) : (
        <div className="min-h-full grid place-items-center p-8">
          <div className="text-center px-8">
            <div className="text-[clamp(40px,9vw,120px)] font-bold leading-tight">{bigText(step, stopLabel, note)}</div>
            <div className="text-[clamp(14px,2vw,22px)] text-white/60 mt-4">{ns.toUpperCase()} · 순회 문진</div>
            {step === "moveDelay" && (
              <button onClick={() => setStep("moving")} className="mt-6 px-6 py-3 rounded-2xl bg-white text-[#0b1f1d] font-semibold">이동 재시도</button>
            )}
          </div>
        </div>
      )}
      {step !== "done" && (
        <button onClick={abort}
          className="fixed bottom-8 right-8 px-7 py-4 rounded-2xl text-[18px] font-semibold bg-white text-[#0b1f1d] shadow-lg">
          순회 중단 · 복귀
        </button>
      )}
    </div>
  );
}

function bigText(step: Step, stopLabel: string, note: string): string {
  switch (step) {
    case "intro": return "순회 문진을 가동합니다.";
    case "moving": return `${stopLabel}(으)로 이동 중…`;
    case "moveDelay": return "이동 지연 — 위치 확인";
    case "skip": return note || "이미 문진 완료 — 다음 호실로";
    case "timeout": return "시간 초과 — 다음 호실로 이동합니다";
    case "returning": return "복귀 중…";
    case "done": return "순회 완료";
    default: return "";
  }
}
```

> **Note (mission_cancel):** `abort` publishes a `mission_cancel` action via `pushMission`. The backend `mission_payload` whitelist must accept `mission_cancel` (the robot side already subscribes `/{ns}/mission_cancel`). Verify in Step 2; if the whitelist rejects it, the call simply no-ops on the client (caught) and the robot still receives the return-home goto — abort remains functional.

- [ ] **Step 2: Verify mission_cancel whitelist (no code unless needed)**

Run: `cd web/backend && grep -n "mission_cancel\|ALLOWED\|whitelist\|action" fb_read.py | head`
If `mission_cancel` is **not** an accepted action in `mission_payload`, the abort's cancel is best-effort only (return-home still works). Do **not** expand robot behavior here — that's out of scope for this plan. Leave a code comment in the overlay noting the dependency (already present).

- [ ] **Step 3: Typecheck + build**

Run: `cd web/frontend && npx tsc --noEmit && npm run build`
Expected: no type errors; build succeeds.

- [ ] **Step 4: Commit**

```bash
git add web/frontend/components/PatrolIntakeOverlay.tsx
git commit -m "feat(web): PatrolIntakeOverlay state machine"
```

---

## Task 9: Frontend — home "순회 문진 시작" button (staff+)

**Files:**
- Modify: `web/frontend/app/page.tsx`

- [ ] **Step 1: Wire the overlay into Home**

In `app/page.tsx`:
1. Add import: `import PatrolIntakeOverlay from "@/components/PatrolIntakeOverlay";`
2. Add state in `Home()`:
```ts
  const [patrolConfirm, setPatrolConfirm] = useState(false);
  const [patrolActive, setPatrolActive] = useState(false);
```
3. After the existing `FollowOverlay` JSX block (around line 123), add the patrol button + overlay (visible to staff+ only, i.e. inside the `role !== "patient"` return which is already where the dashboard renders):
```tsx
      {roleAtLeast(role, "staff") && !patrolConfirm ? (
        <button
          onClick={() => setPatrolConfirm(true)}
          className="w-full rounded-2xl px-7 py-6 mb-6 text-left text-white shadow-md flex items-center justify-between"
          style={{ background: "linear-gradient(90deg,#16a34a,#0f7a37)" }}
        >
          <div>
            <div className="text-[20px] font-bold">순회 문진 시작</div>
            <div className="text-[13px] text-white/80 mt-1">101호 병상을 순회하며 환자 QR로 문진을 자동 진행합니다</div>
          </div>
          <span className="text-[26px]">▶</span>
        </button>
      ) : roleAtLeast(role, "staff") && patrolConfirm ? (
        <div
          className="w-full rounded-2xl px-7 py-6 mb-6 text-white shadow-md flex items-center justify-between gap-4"
          style={{ background: "linear-gradient(90deg,#16a34a,#0f7a37)" }}
        >
          <div className="text-[15px] font-semibold">순회 문진을 시작할까요? (전 환자 문진여부 리셋 후 101호 순회)</div>
          <div className="flex gap-2 shrink-0">
            <button onClick={() => { setPatrolConfirm(false); setPatrolActive(true); }} className="px-5 py-2.5 rounded-xl bg-white text-[#0f7a37] font-semibold">확인</button>
            <button onClick={() => setPatrolConfirm(false)} className="px-5 py-2.5 rounded-xl bg-white/20 font-semibold">취소</button>
          </div>
        </div>
      ) : null}
      <PatrolIntakeOverlay
        active={patrolActive}
        ns={PRIMARY_NS}
        targets={targets}
        onExit={() => setPatrolActive(false)}
      />
```
(`targets` state already exists in `Home`; `roleAtLeast`, `PRIMARY_NS` already imported.)

- [ ] **Step 2: Typecheck + build**

Run: `cd web/frontend && npx tsc --noEmit && npm run build`
Expected: no type errors; build succeeds.

- [ ] **Step 3: Commit**

```bash
git add web/frontend/app/page.tsx
git commit -m "feat(web): home 순회 문진 시작 button (staff+)"
```

---

## Final Verification

- [ ] **Backend suite:** `cd web/backend && python -m pytest test/ -q` → all pass
- [ ] **Frontend unit:** `cd web/frontend && npx vitest run` → all pass (incl. patrol + follow)
- [ ] **Frontend build:** `cd web/frontend && npx tsc --noEmit && npm run build` → green
- [ ] **Runtime (user):** 서버 기동 후 staff 로그인 → 홈 "순회 문진 시작" → 확인 → 풀스크린 "순회 문진을 가동합니다" → 101호 1번 이동(goto) → 도착 시 QR 스캔 화면 → (a) 미스캔 1분 → 시간초과 메시지 5초 → 101호 2번, (b) QR 스캔 + intake_done=false → 문진표 → 저장 → 다음, (c) intake_done=true → 즉시 다음. 두 정류장 종료 → 홈 복귀·도킹. 실제 로봇 goto/도킹 검증은 사용자가 직접 구동.

---

## Self-Review Notes

**Spec coverage:** §3 데이터 모델 → T1·T2·T5; §4 백엔드 → T1·T2·T3; §5.1 추출 → T6·T7; §5.2 patrol.ts → T4; §5.3 오버레이 → T8; §5.4 홈 버튼 → T9; §5.5 api → T5; §6 상태머신 → T8; §7 엣지(카메라/지연/pose/미등록/중단) → T8; §8 테스트 → T1·T2·T3·T4. 전부 매핑됨.

**Type consistency:** `decideAfterScan`/`nextStop`/`PATROL_STOPS`(T4) ↔ 오버레이 사용(T8) 일치. `resetIntakeRound`/`markIntakeDone`/`Patient.intake_done`(T5) ↔ 오버레이·백엔드 일치. `IntakeForm` default export props `{pid, prefillDept?, onSaved?}`(T7) ↔ 오버레이 `<IntakeForm pid onSaved>`(T8) 일치. `useQrScanner(onDecode)` 반환 `{videoRef,camOn,camErr,camInfo,start,stop}`(T6) ↔ qr 페이지·오버레이 사용 일치.

**Out-of-scope guardrails:** mission_cancel 로봇 동작 확장은 비범위(T8 Step2). 실제 로봇 구동은 사용자.
