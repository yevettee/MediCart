# 처치실 OCR — "QR 환자 확인" 모드 이식 (jeon → integration) 설계

> 작성일: 2026-06-09 · 대상: `MediCart/web` · 브랜치: integration · 출처: `origin/jeon@267e8ee`

## 1. 목적

jeon이 처치실 `/ocr` 페이지의 **"실시간 OCR" 탭을 "QR 환자 확인" 탭으로 교체**했다(커밋 `267e8ee`).
이를 현재 integration `/ocr`에 이식하되, jeon 버전의 **버그(처방 완료가 DB에 기록되지 않음)를 고쳐
"제대로" 동작**하게 만든다. 같은 커밋의 Next.js 프록시·iOS Safari 수정은 **이식 범위에서 제외**한다.

## 2. 배경 — jeon 버전의 실제 상태

- `/ocr` 모드 토글: `single | realtime` → **`single | qr("QR 환자 확인")`** 로 변경(실시간 2초 루프 제거).
- QR 환자 확인 = 처치실에서 **환자 QR을 스캔해 투약 직전 3단계 게이트**:
  1. **blocked_patient** — 스캔 PID ≠ 선택 환자 → 환자 불일치 차단
  2. **blocked_meds** — 해당 환자 주사 중 `status !== "confirmed"`가 있으면 차단(미준비 목록 표시)
  3. **complete** — 전부 `confirmed` → "처방 완료"
- 백엔드 `POST /api/patients/<pid>/injections/<inj_id>/confirm` + `confirmInjection()` 헬퍼가 **추가됐으나
  페이지에서 호출되지 않음** → complete는 화면 표시만, DB 미기록. **이 미연결이 우리가 고칠 지점.**

## 3. 핵심 결정 (브레인스토밍 확정)

- **모드**: jeon처럼 교체 — `single | QR 환자 확인`(실시간 OCR 제거).
- **범위**: QR 환자 확인 기능만(confirm 엔드포인트 + `confirmInjection` + 3단계 판정). 프록시/iOS/next.config 제외.
- **complete 동작**: `confirmInjection`을 **실제 호출**해 그 환자의 전 injection을 `"QR 환자 확인"` 출처로 확정 기록(죽은 엔드포인트를 살림).
- **setOcrDone(robot6 완료신호) 유지**: 실시간과 무관한 로봇 워크플로 신호라 single 모드 영역에 완료 버튼으로 존치.

## 4. 접근 — 통째 교체가 아니라 수술적 이식

integration `/ocr`의 단일 스캔(자동 OCR→투약검증), USB 카메라 우선, `setOcrDone` 완료신호 등 **기존 장점은 유지**하고,
**realtime 모드/인터벌만 제거하고 jeon의 qr 모드(스캔 루프·3케이스·결과 패널)를 이식**한다. 직전 순회문진 작업
(Task 1–7의 `lib/api` patrol 추가분, `useQrScanner`/`IntakeForm` 추출)과는 함수가 겹치지 않아 충돌 없음.

## 5. 구성요소

### 5.1 `web/frontend/lib/ocrQr.ts` (신규 — 순수 판정 로직, vitest)
```ts
export type QrDecision =
  | { kind: "blocked_patient"; scannedPid: string }
  | { kind: "blocked_meds"; unready: { name: string; status: string }[] }
  | { kind: "complete"; injCount: number };

export type InjLike = { id: string; status?: string; 약품명?: string; 약물명?: string };

// 스캔 PID·선택 PID·주사목록 → 3단계 판정(표시명은 호출측에서 부여).
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

### 5.2 `web/frontend/lib/api.ts` (수정)
`confirmInjection` 헬퍼 추가(verify 헬퍼와 같은 스타일, body 없음):
```ts
export async function confirmInjection(
  pid: string, inj_id: string,
): Promise<{ ok: boolean; status: string }> {
  const r = await fetch(`${API_BASE}/api/patients/${pid}/injections/${inj_id}/confirm`, {
    method: "POST", credentials: "include",
  });
  if (!r.ok) throw new Error(`/api/patients/${pid}/injections/${inj_id}/confirm → ${r.status}`);
  return r.json();
}
```

### 5.3 `web/frontend/app/ocr/page.tsx` (수정 — realtime → qr)
- 모드 타입 `"single" | "realtime"` → `"single" | "qr"`. 토글 라벨 "실시간 OCR" → **"QR 환자 확인"**.
- realtime 인터벌 effect 제거. 대신 **qr 인터벌 effect**: `ocrMode==="qr" && camOn` → `setInterval(scanQr, 300)`.
- 상태 추가: `qrRaw`, `qrResult`(아래 표시형), `qrConfirming`, `qrCooldownRef`(3000ms), `qrConfirmingRef`.
- `scanQr`(useCallback, deps `[camOn,pid,injections,patients]`): jsQR 디코드 → `PID_RE`(`/^P-\d{4}-\d{4}$/`) 검증 →
  `decideQr(raw, pid, injections)` 호출. blocked_*는 즉시 표시. **complete면**:
  - `qrConfirmingRef` 가드 + `QR_COOLDOWN_MS` 쿨다운,
  - `await Promise.all(injections.map((i) => confirmInjection(pid, i.id)))` → DB 확정 기록,
  - 로컬 injections status를 `confirmed`로 반영,
  - `setQrResult({ type:"complete", patientName, injCount })`,
  - 실패 시 `scanErr` 표시(complete 미확정).
  - 표시명(`patientName`, `selectedName`)은 `patients`에서 부여.
- 결과 패널 3종(complete/blocked_meds/blocked_patient) + "다시 스캔" 버튼: jeon JSX 그대로 이식.
- **유지**: single 모드 자동 OCR→검증, USB 카메라 우선, `setOcrDone` 완료 버튼, OCR 결과 카드, 환자/주사 선택·검증 결과.

### 5.4 `web/backend/app.py` (수정)
verify 라우트 바로 뒤에 confirm 라우트 추가(인증은 `/api/patients` staff 프리픽스로 자동):
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
`fb_read.update_injection_status(pid, inj_id, status, ocr_text)`·`_PID_RE`는 integration에 이미 존재(verify가 사용) — 재사용.

## 6. 데이터 흐름

```
[처치실 워크플로]
 1) 환자 선택 → 주사 처방 목록 로드
 2) (single 모드) 약품 라벨 OCR 스캔 → verifyInjection → status=confirmed|mismatch  ← 기존
 3) (QR 환자 확인 모드) 환자 QR 스캔(300ms 루프)
      └ decideQr:
          ≠환자        → blocked_patient (차단)
          미confirmed 有 → blocked_meds (미준비 목록)
          전부 confirmed → complete:
              confirmInjection × 전 injection  → RTDB patients/{pid}/injections/{id}.status="confirmed"(+"QR 환자 확인")
              "처방 완료" 표시
 4) (옵션) setOcrDone("robot6") → robot6/nurse_cart/ocr_done=true  ← 기존 유지
```

## 7. 엣지 케이스
| 상황 | 처리 |
|---|---|
| 비PID QR | `qrRaw` 표시만, 판정 안 함(계속 스캔) |
| 같은 환자 연속 스캔 | `QR_COOLDOWN_MS=3000` 쿨다운으로 중복 confirm 방지 |
| confirm 중 재진입 | `qrConfirmingRef` 가드 |
| confirmInjection 실패 | `scanErr` 표시, complete 미확정(부분 실패 시 재스캔으로 재시도) |
| 환자/주사 미선택 상태로 qr 모드 | pid 없으면 스캔 무시(가드) |

## 8. 테스트
- **vitest** (`lib/ocrQr.test.ts`): `decideQr` — 환자 불일치, 미confirmed 1건 이상(unready 목록·status 매핑), 전부 confirmed(complete·injCount), 빈 주사목록(complete injCount=0).
- **pytest** (`web/backend/test/`): confirm 엔드포인트 — 정상(staff, `update_injection_status` monkeypatch 호출 인자 검증 → 200 `{ok,status:confirmed}`), 잘못된 pid → 400, 비staff → 401(프리픽스 게이트).

## 9. 영향도
- 신규: `lib/ocrQr.ts`(+test), 백엔드 confirm 라우트, `confirmInjection`(api.ts).
- 수정: `app/ocr/page.tsx`(realtime→qr), `app.py`(라우트 1개). `fb_read`·`update_injection_status` 무변경(재사용).
- 무관/무변경: `/qr`(문진표 호출)·`/display`·`/console`·순회문진 자산.
- 런타임(웹캠·실DB) 검증은 사용자(서버 직접 구동은 가능, 로봇 구동은 제외).

## 10. 비범위 (YAGNI)
- Next.js 프록시 아키텍처(`API_BASE=""`+rewrites), iOS Safari 로그인 수정, `next.config` allowedDevOrigins, README — jeon 커밋에 묶여 있으나 이식 제외.
- 실시간 연속 OCR 모드(제거됨).
