"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { getPatients, getInjections, verifyInjection, ocr as runOcr, type Patient, type Injection } from "@/lib/api";

// 약품 OCR + 처방 DB검증 패널 (간호사 투약 도착 단계 임베드용).
// /ocr 페이지의 검증 로직(verifyInjection)·웹캠 캡처를 동일하게 사용하되,
// QR/시나리오 제어 없이 '환자·처방 선택 → 스캔 → 검증' 만 담는 단일 책임 컴포넌트.
// 검증 통과(match) 여부를 onVerifiedChange 로 부모(오버레이)에 알려 '확인' 버튼을 게이팅한다.

type InjEntry = { id: string } & Injection;

export default function MedOcrPanel({ onVerifiedChange }: { onVerifiedChange?: (ok: boolean) => void }) {
  const [patients, setPatients] = useState<Patient[]>([]);
  const [pid, setPid] = useState("");
  const [injections, setInjections] = useState<InjEntry[]>([]);
  const [injId, setInjId] = useState("");

  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const scanningRef = useRef(false);
  const [camOn, setCamOn] = useState(false);
  const [camErr, setCamErr] = useState("");
  const [ocrText, setOcrText] = useState("");
  const [scanning, setScanning] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [result, setResult] = useState<{ match: boolean; status: string; reason: string } | null>(null);

  useEffect(() => { getPatients().then(setPatients).catch(() => {}); }, []);

  // 환자 변경 → 처방 목록 갱신 + 검증 상태 초기화
  useEffect(() => {
    setInjections([]); setInjId(""); setResult(null); setOcrText(""); onVerifiedChange?.(false);
    if (!pid) return;
    getInjections(pid).then((raw) => {
      const list: InjEntry[] = Object.entries(raw || {}).map(([id, inj]) => ({ id, ...inj }));
      setInjections(list);
      if (list.length > 0) setInjId(list[0].id);
    }).catch(() => {});
  }, [pid]); // eslint-disable-line react-hooks/exhaustive-deps

  // 웹캠 시작 — USB 외부 카메라 우선(/ocr 와 동일 로직)
  const startCam = useCallback(async () => {
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
      streamRef.current = stream;
      const v = videoRef.current;
      if (v) { v.srcObject = stream; setCamOn(true); await v.play(); }
      else { stream.getTracks().forEach((t) => t.stop()); streamRef.current = null; }
    } catch {
      setCamErr("웹캠을 열 수 없습니다. 브라우저 권한을 확인하세요.");
    }
  }, []);

  const stopCam = useCallback(() => {
    const s = streamRef.current;
    if (s) { s.getTracks().forEach((t) => t.stop()); streamRef.current = null; }
    const v = videoRef.current;
    if (v) v.srcObject = null;
    setCamOn(false);
  }, []);

  useEffect(() => { startCam(); return () => stopCam(); }, [startCam, stopCam]);

  const captureAndOcr = useCallback(async (): Promise<string | undefined> => {
    const v = videoRef.current;
    if (!v || !camOn || scanningRef.current) return undefined;
    scanningRef.current = true; setScanning(true); setCamErr("");
    setOcrText(""); setResult(null); onVerifiedChange?.(false);
    const canvas = document.createElement("canvas");
    canvas.width = v.videoWidth; canvas.height = v.videoHeight;
    canvas.getContext("2d")!.drawImage(v, 0, 0);
    const blob: Blob | null = await new Promise((res) => canvas.toBlob(res, "image/png"));
    try {
      if (!blob) { setCamErr("캡처 실패"); return undefined; }
      const r = await runOcr(blob);
      setOcrText(r.text);
      return r.text;
    } catch (e) {
      setCamErr(String(e));
      return undefined;
    } finally {
      setScanning(false); scanningRef.current = false;
    }
  }, [camOn]); // eslint-disable-line react-hooks/exhaustive-deps

  async function verifyWith(text: string) {
    if (!pid || !injId || !text) return;
    const inj = injections.find((i) => i.id === injId);
    if (!inj) return;
    setVerifying(true); setResult(null);
    const medicineName = (inj.약품명 || inj["약물명"] || "") as string;
    try {
      const res = await verifyInjection(pid, injId, text, medicineName);
      setResult({ match: res.match, status: res.status, reason: res.reason });
      setInjections((prev) => prev.map((i) => i.id === injId ? { ...i, status: res.status as Injection["status"] } : i));
      onVerifiedChange?.(res.match);
    } catch (e) {
      setResult({ match: false, status: "error", reason: String(e) });
      onVerifiedChange?.(false);
    } finally {
      setVerifying(false);
    }
  }

  async function handleScan() {
    if (!camOn) { setCamErr("웹캠을 먼저 켜세요."); return; }
    const text = await captureAndOcr();
    if (text && pid && injId) await verifyWith(text);
  }

  const selInj = injections.find((i) => i.id === injId);

  return (
    <div className="grid md:grid-cols-2 gap-4 text-left">
      {/* 좌: 환자·처방 선택 + 검증 결과 */}
      <div className="flex flex-col gap-3">
        <label className="block">
          <span className="text-[12.5px] font-semibold text-ink-2">환자</span>
          <select className="field mt-1" value={pid} onChange={(e) => setPid(e.target.value)}>
            <option value="">환자 선택</option>
            {patients.map((p) => <option key={p.id} value={p.id}>{p.성명} · {p.id}</option>)}
          </select>
        </label>
        <label className="block">
          <span className="text-[12.5px] font-semibold text-ink-2">처방(주사)</span>
          <select className="field mt-1" value={injId} onChange={(e) => setInjId(e.target.value)} disabled={!injections.length}>
            {!injections.length && <option value="">처방 없음</option>}
            {injections.map((i) => (
              <option key={i.id} value={i.id}>{(i.약품명 || i.약물명 || i.id) as string}{i.용량 ? ` · ${i.용량}` : ""}</option>
            ))}
          </select>
        </label>
        {ocrText && (
          <div className="rounded-xl bg-surface-2 border border-line px-3 py-2">
            <div className="text-[11px] text-ink-3 font-semibold">OCR 인식</div>
            <div className="text-[13px] text-ink mt-0.5 break-all">{ocrText}</div>
          </div>
        )}
        {result && (
          <div className={`rounded-xl px-3 py-2.5 text-[13px] font-semibold ${result.match ? "bg-green-soft text-green" : "bg-red-soft text-red"}`}>
            {result.match ? "✓ DB 검증 완료 — 약품 적합" : `✗ 불일치: ${result.reason || result.status}`}
          </div>
        )}
      </div>

      {/* 우: 웹캠 + 스캔 */}
      <div className="flex flex-col gap-3">
        <div className="relative rounded-xl bg-black overflow-hidden aspect-video">
          <video ref={videoRef} className={`w-full h-full object-cover ${camOn ? "block" : "hidden"}`} autoPlay muted playsInline />
          {!camOn && <div className="absolute inset-0 grid place-items-center text-white/60 text-[13px]">{camErr || "웹캠 준비 중…"}</div>}
        </div>
        <button onClick={handleScan} disabled={!camOn || scanning || verifying || !pid || !injId}
          className="rounded-xl bg-teal text-white px-4 py-2.5 text-[14px] font-semibold hover:bg-teal-600 disabled:opacity-50">
          {scanning ? "스캔 중…" : verifying ? "검증 중…" : "약품 스캔 · DB 검증"}
        </button>
        {selInj && <p className="text-[11.5px] text-ink-3">기준 약품명: <b className="text-ink-2">{(selInj.약품명 || selInj.약물명 || "—") as string}</b></p>}
        {camErr && <p className="text-[12px] text-red">{camErr}</p>}
      </div>
    </div>
  );
}
