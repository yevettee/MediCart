"use client";
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

export default function OcrPage() {
  /* 환자/주사 목록 */
  const [patients, setPatients] = useState<Patient[]>([]);
  const [pid, setPid] = useState("");
  const [injections, setInjections] = useState<InjEntry[]>([]);
  const [injId, setInjId] = useState("");

  /* 웹캠 */
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [camOn, setCamOn] = useState(false);
  const [camErr, setCamErr] = useState("");
  const [camInfo, setCamInfo] = useState("");

  /* 완료 신호 */
  const [doneSending, setDoneSending] = useState(false);
  const [doneMsg, setDoneMsg] = useState("");

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


  /* OCR */
  const [ocrText, setOcrText] = useState("");
  const [scanning, setScanning] = useState(false);
  const [scanErr, setScanErr] = useState("");

  /* 검증 */
  const [verifying, setVerifying] = useState(false);
  const [result, setResult] = useState<VerifyResult>(null);

  /* 환자 로드 */
  useEffect(() => {
    getPatients().then(setPatients).catch(() => {});
  }, []);

  /* 환자 변경 → 주사 목록 갱신 */
  useEffect(() => {
    setInjections([]);
    setInjId("");
    setResult(null);
    setOcrText("");
    if (!pid) return;
    getInjections(pid)
      .then((raw) => {
        const list: InjEntry[] = Object.entries(raw || {}).map(([id, inj]) => ({ id, ...inj }));
        setInjections(list);
        if (list.length > 0) setInjId(list[0].id);
      })
      .catch(() => {});
  }, [pid]);

  /* 웹캠 시작 — USB 외부 카메라 우선 선택 */
  const startCam = useCallback(async () => {
    setCamErr("");
    try {
      // 1단계: 권한 취득 (라벨 접근에 필요) — 일단 기본 카메라로 열기
      const tempStream = await navigator.mediaDevices.getUserMedia({ video: true });

      // 2단계: 열거 후 USB 카메라 찾기
      const devices = await navigator.mediaDevices.enumerateDevices();
      const cams = devices.filter((d) => d.kind === "videoinput");
      const usbCam = cams.find(
        (d) => !/integrated|facetime|built.?in/i.test(d.label)
      );

      // 3단계: temp가 이미 USB 캠인지 확인 → 같으면 그대로 재사용
      const tempDeviceId = tempStream.getVideoTracks()[0]?.getSettings()?.deviceId;
      let stream = tempStream;

      if (usbCam && tempDeviceId !== usbCam.deviceId) {
        // 다른 카메라라면 교체 (stop 후 딜레이 없이 바로 재요청하면 검은 화면)
        tempStream.getTracks().forEach((t) => t.stop());
        stream = await navigator.mediaDevices.getUserMedia({
          video: { deviceId: { exact: usbCam.deviceId }, width: 1280, height: 720 },
        });
      }

      streamRef.current = stream;
      const v = videoRef.current;
      if (v) {
        v.srcObject = stream;
        // hidden 상태에서 play()하면 검은 화면 → 먼저 보이게 하고 재생
        setCamOn(true);
        await v.play();
        const label = stream.getVideoTracks()[0]?.label || usbCam?.label || cams[0]?.label || "카메라";
        setCamInfo(label);
      } else {
        // 언마운트 등으로 video 엘리먼트가 사라졌으면 즉시 정리
        stream.getTracks().forEach((t) => t.stop());
        streamRef.current = null;
      }
    } catch {
      setCamErr("웹캠을 열 수 없습니다. 브라우저 권한을 확인하세요.");
    }
  }, []);

  /* 웹캠 정지 — 트랙 종료 + 상태 초기화 */
  const stopCam = useCallback(() => {
    const s = streamRef.current;
    if (s) { s.getTracks().forEach((t) => t.stop()); streamRef.current = null; }
    const v = videoRef.current;
    if (v) v.srcObject = null;
    setCamOn(false);
    setCamInfo("");
  }, []);

  /* 진입 시 웹캠 자동 ON, 페이지 이탈(언마운트) 시 자동 OFF */
  useEffect(() => {
    startCam();
    return () => { stopCam(); };
  }, [startCam, stopCam]);

  /* 공통 캡처 + OCR — 단일/실시간 모드 모두 사용. 인식 텍스트 반환(체이닝용). */
  const captureAndOcr = useCallback(async (clearPrev = false): Promise<string | undefined> => {
    const v = videoRef.current;
    if (!v || !camOn || scanningRef.current) return undefined;
    scanningRef.current = true;
    setScanning(true);
    setScanErr("");
    if (clearPrev) { setOcrText(""); setResult(null); }

    const canvas = document.createElement("canvas");
    canvas.width = v.videoWidth;
    canvas.height = v.videoHeight;
    canvas.getContext("2d")!.drawImage(v, 0, 0);
    const blob: Blob | null = await new Promise((res) => canvas.toBlob(res, "image/png"));
    try {
      if (!blob) { setScanErr("캡처 실패"); return undefined; }
      const r = await runOcr(blob);
      setOcrText(r.text);
      return r.text;
    } catch (e) {
      setScanErr(String(e));
      return undefined;
    } finally {
      setScanning(false);
      scanningRef.current = false;
    }
  }, [camOn]);

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

  /* 단일 스캔 (버튼) → OCR 후 환자·처방이 선택돼 있으면 투약검증·DB저장까지 자동 수행 */
  async function handleScan() {
    if (!camOn) { setScanErr("웹캠을 먼저 켜세요."); return; }
    const text = await captureAndOcr(true);
    if (text && pid && injId) await verifyWith(text);
  }

  /* 검증 코어 — 명시적 OCR 텍스트로 검증(스캔 직후 state 반영 전에도 동작) */
  async function verifyWith(text: string) {
    if (!pid || !injId || !text) return;
    const inj = injections.find((i) => i.id === injId);
    if (!inj) return;
    setVerifying(true); setResult(null);
    // DB 키가 약품명 또는 약물명 둘 다 허용
    const medicineName = (inj.약품명 || inj["약물명"] || "") as string;
    try {
      const res = await verifyInjection(pid, injId, text, medicineName);
      setResult(res);
      // 로컬 목록 상태 즉시 반영
      setInjections((prev) =>
        prev.map((i) => i.id === injId ? { ...i, status: res.status as Injection["status"] } : i)
      );
    } catch (e) {
      setResult({ match: false, status: "error", reason: String(e) });
    } finally {
      setVerifying(false);
    }
  }

  /* 검증 버튼 */
  function handleVerify() { verifyWith(ocrText); }

  /* 완료 → RTDB robot6/nurse_cart/ocr_done = true */
  async function handleDone() {
    setDoneSending(true); setDoneMsg("");
    try {
      await setOcrDone("robot6");
      setDoneMsg("완료 신호 전송됨 — robot6/nurse_cart/ocr_done = true");
    } catch (e) {
      setDoneMsg("전송 실패: " + String(e));
    } finally {
      setDoneSending(false);
    }
  }

  const selectedInj = injections.find((i) => i.id === injId);
  const selectedPat = patients.find((p) => p.id === pid);

  return (
    <div className="p-6 max-w-5xl">
      <header className="mb-6">
        <h1 className="text-2xl font-bold text-ink">약품 OCR 검증</h1>
        <p className="text-ink-3 text-sm mt-1">
          환자 선택 → 주사 처방 확인 → 웹캠 스캔 → 약품 적합 여부 검증 → DB 업데이트
        </p>
      </header>

      <div className="grid md:grid-cols-2 gap-5">
        {/* ── 왼쪽: 웹캠 + 스캔 ── */}
        <div className="flex flex-col gap-4">
          <section className="card p-5">
            <h2 className="font-semibold text-ink mb-3 flex items-center gap-2">
              <CameraIcon />
              웹캠 스캔
            </h2>

            {/* OCR 모드 토글 */}
            <div className="flex rounded-xl border border-line overflow-hidden text-xs font-semibold mb-3">
              <button
                onClick={() => { setOcrMode("single"); setQrRaw(null); setQrResult(null); }}
                className={`flex-1 py-2 transition-colors ${
                  ocrMode === "single" ? "bg-teal text-white" : "text-ink-2 hover:bg-surface-2"
                }`}>
                단일 스캔
              </button>
              <button
                onClick={() => { setOcrMode("qr"); setOcrText(""); setResult(null); }}
                className={`flex-1 py-2 transition-colors ${
                  ocrMode === "qr" ? "bg-teal text-white" : "text-ink-2 hover:bg-surface-2"
                }`}>
                QR 환자 확인
              </button>
            </div>

            {!camOn ? (
              <button onClick={startCam}
                className="w-full rounded-xl border-2 border-dashed border-line py-10 text-ink-3 text-sm hover:border-teal hover:text-teal transition-colors flex flex-col items-center gap-2">
                <CameraIcon big />
                <span>웹캠 켜기</span>
              </button>
            ) : null}

            <video
              ref={videoRef}
              className={`w-full rounded-xl bg-black ${camOn ? "block" : "hidden"}`}
              autoPlay muted playsInline
            />

            {camErr && <p className="text-red text-xs mt-2">{camErr}</p>}
            {camInfo && !camErr && (
              <p className="text-green text-xs mt-2 flex items-center gap-1">
                <span>●</span> {camInfo}
              </p>
            )}

            {/* 단일 스캔 버튼 */}
            {camOn && ocrMode === "single" && (
              <button
                onClick={handleScan}
                disabled={scanning}
                className="mt-3 w-full rounded-xl bg-teal text-white py-2.5 text-sm font-semibold hover:bg-teal-600 disabled:opacity-50 transition-colors flex items-center justify-center gap-2">
                {scanning ? <Spinner /> : <ScanIcon />}
                {scanning ? "인식 중…" : "스캔 & OCR"}
              </button>
            )}

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

            {scanErr && <p className="text-red text-xs mt-2">{scanErr}</p>}
          </section>


          {/* OCR 결과 */}
          <section className="card p-5">
            <h2 className="font-semibold text-ink mb-2 flex items-center gap-2">
              <TextIcon />
              OCR 결과
            </h2>
            <pre className="whitespace-pre-wrap text-ink text-sm min-h-[6rem] bg-surface-2 rounded-xl p-3 border border-line font-mono leading-relaxed">
              {ocrText || <span className="text-ink-3">스캔 후 텍스트가 표시됩니다.</span>}
            </pre>
          </section>
        </div>

        {/* ── 오른쪽: 환자/주사 선택 + 검증 결과 ── */}
        <div className="flex flex-col gap-4">
          {/* 환자 선택 */}
          <section className="card p-5">
            <h2 className="font-semibold text-ink mb-3 flex items-center gap-2">
              <PatientIcon />
              환자 선택
            </h2>
            <label className="block">
              <span className="eyebrow mb-1.5 block">등록 환자</span>
              <select
                value={pid}
                onChange={(e) => setPid(e.target.value)}
                className="w-full rounded-xl border border-line bg-surface px-3 py-2.5 text-sm text-ink focus:outline-none focus:border-teal">
                <option value="">-- 환자를 선택하세요 --</option>
                {patients.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.성명} ({p.id})
                  </option>
                ))}
              </select>
            </label>

            {selectedPat && (
              <div className="mt-3 rounded-xl bg-teal-soft border border-teal/20 p-3 text-sm flex gap-4">
                <span className="text-teal-600 font-semibold">{selectedPat.성명}</span>
                {selectedPat.나이 && <span className="text-ink-2">{selectedPat.나이}세</span>}
                {selectedPat.혈액형 && <span className="text-ink-2">{selectedPat.혈액형}</span>}
                {"약물 알레르기" in selectedPat && selectedPat["약물 알레르기"] && (
                  <span className="text-red text-xs bg-red-soft px-2 py-0.5 rounded-lg">
                    알레르기: {String(selectedPat["약물 알레르기"])}
                  </span>
                )}
              </div>
            )}
          </section>

          {/* 주사 처방 선택 */}
          <section className="card p-5">
            <h2 className="font-semibold text-ink mb-3 flex items-center gap-2">
              <InjectIcon />
              주사 처방
            </h2>

            {!pid ? (
              <p className="text-ink-3 text-sm">환자를 선택하면 주사 처방 목록이 나타납니다.</p>
            ) : injections.length === 0 ? (
              <p className="text-ink-3 text-sm">등록된 주사 처방이 없습니다.</p>
            ) : (
              <>
                <label className="block mb-3">
                  <span className="eyebrow mb-1.5 block">처방 선택</span>
                  <select
                    value={injId}
                    onChange={(e) => { setInjId(e.target.value); setResult(null); }}
                    className="w-full rounded-xl border border-line bg-surface px-3 py-2.5 text-sm text-ink focus:outline-none focus:border-teal">
                    {injections.map((inj) => (
                      <option key={inj.id} value={inj.id}>
                        {(inj.약품명 || inj["약물명"] as string)} {inj.용량 ? `(${inj.용량})` : ""}
                      </option>
                    ))}
                  </select>
                </label>

                {selectedInj && (
                  <div className="rounded-xl border border-line p-3 text-sm space-y-1.5">
                    <Row label="약품명" value={(selectedInj.약품명 || selectedInj["약물명"] as string)} />
                    {selectedInj.용량 && <Row label="용량" value={selectedInj.용량} />}
                    {selectedInj.투약경로 && <Row label="경로" value={selectedInj.투약경로} />}
                    {selectedInj.투약시간 && <Row label="시간" value={selectedInj.투약시간} />}
                    <div className="flex items-center gap-2 pt-1">
                      <span className="text-ink-3">상태</span>
                      <StatusBadge status={selectedInj.status} />
                    </div>
                  </div>
                )}
              </>
            )}
          </section>

          {/* 검증 버튼 + 결과 */}
          <section className="card p-5">
            <h2 className="font-semibold text-ink mb-3 flex items-center gap-2">
              <CheckIcon />
              투약 검증
            </h2>

            <button
              onClick={handleVerify}
              disabled={!pid || !injId || !ocrText || verifying}
              className="w-full rounded-xl bg-teal text-white py-3 text-sm font-semibold hover:bg-teal-600 disabled:opacity-40 transition-colors flex items-center justify-center gap-2">
              {verifying ? <Spinner /> : <CheckIcon />}
              {verifying ? "검증 중…" : "약품 적합성 검증 & DB 저장"}
            </button>

            {!ocrText && pid && injId && (
              <p className="text-ink-3 text-xs mt-2 text-center">스캔을 먼저 실행하세요.</p>
            )}

            {result && (
              <div className={`mt-4 rounded-2xl p-4 border ${
                result.match
                  ? "bg-green-soft border-green/30"
                  : "bg-red-soft border-red/30"
              }`}>
                <div className="flex items-center gap-2 mb-2">
                  {result.match ? <MatchIcon /> : <MismatchIcon />}
                  <span className={`font-bold text-base ${result.match ? "text-green" : "text-red"}`}>
                    {result.match ? "투약 준비 완료" : "약품 불일치 — 재확인 필요"}
                  </span>
                </div>
                <p className="text-ink-2 text-sm leading-relaxed">{result.reason}</p>
                <p className="text-ink-3 text-xs mt-2">DB 상태: <strong>{result.status}</strong></p>
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}

/* ── 보조 컴포넌트 ─────────────────────────────────────────────────── */
function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex gap-2">
      <span className="text-ink-3 w-16 shrink-0">{label}</span>
      <span className="text-ink font-medium">{value}</span>
    </div>
  );
}

function StatusBadge({ status }: { status?: string }) {
  const map: Record<string, { label: string; cls: string }> = {
    confirmed: { label: "투약 준비 완료", cls: "bg-green-soft text-green" },
    mismatch:  { label: "약품 불일치", cls: "bg-red-soft text-red" },
    pending:   { label: "투약 대기중", cls: "bg-amber-soft text-amber" },
  };
  const m = map[status || "pending"] ?? map.pending;
  return (
    <span className={`text-xs font-semibold px-2 py-0.5 rounded-lg ${m.cls}`}>{m.label}</span>
  );
}

function Spinner() {
  return (
    <svg className="animate-spin" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
      <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
    </svg>
  );
}

function CameraIcon({ big }: { big?: boolean }) {
  const s = big ? 32 : 17;
  return (
    <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
      <circle cx="12" cy="13" r="4" />
    </svg>
  );
}

function ScanIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <path d="M3 7V5a2 2 0 0 1 2-2h2M17 3h2a2 2 0 0 1 2 2v2M21 17v2a2 2 0 0 1-2 2h-2M7 21H5a2 2 0 0 1-2-2v-2M5 12h14" />
    </svg>
  );
}

function TextIcon() {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <rect x="5" y="3" width="14" height="18" rx="2.4" /><path d="M9 8h6M9 12h6M9 16h3" />
    </svg>
  );
}

function PatientIcon() {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="8" r="3.2" /><path d="M5 20c0-3.6 3.1-6 7-6s7 2.4 7 6" />
    </svg>
  );
}

function InjectIcon() {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="m18 2 4 4-4 4M14 6h8M6 12l6-6M2 22 12 12M8 16l-4 4" />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M20 6 9 17l-5-5" />
    </svg>
  );
}

function MatchIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#18a259" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" /><path d="m9 12 2 2 4-4" />
    </svg>
  );
}

function MismatchIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#df4448" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" /><path d="m15 9-6 6M9 9l6 6" />
    </svg>
  );
}
