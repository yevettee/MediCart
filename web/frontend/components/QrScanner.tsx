"use client";
import { useCallback, useEffect, useRef, useState } from "react";

const PID_RE = /^P-\d{4}-\d{4}$/;
const SCAN_INTERVAL_MS = 300;   // QR 디코딩 주기
const COOLDOWN_MS = 2500;       // 같은 결과 연속 호출 방지

type Props = {
  active: boolean;                      // false면 카메라 끔
  onScan: (pid: string) => void;        // 유효 PID 디코드 시 호출
  className?: string;
};

/** 재사용 QR 스캐너 — USB 외부 카메라 우선, 없으면 기본(아이패드) 카메라.
 *  active 동안 카메라를 켜고 jsQR 로 디코드해 유효 PID 를 onScan 으로 올린다. */
export default function QrScanner({ active, onScan, className }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const cooldownRef = useRef(0);
  const onScanRef = useRef(onScan);
  useEffect(() => { onScanRef.current = onScan; }, [onScan]);
  const [camErr, setCamErr] = useState("");
  const [camLabel, setCamLabel] = useState("");

  const start = useCallback(async () => {
    try {
      const tmp = await navigator.mediaDevices.getUserMedia({ video: true });
      const cams = (await navigator.mediaDevices.enumerateDevices())
        .filter((d) => d.kind === "videoinput");
      const usb = cams.find((d) => !/integrated|facetime|built.?in/i.test(d.label));
      const tmpId = tmp.getVideoTracks()[0]?.getSettings()?.deviceId;
      let stream = tmp;
      if (usb && tmpId !== usb.deviceId) {
        tmp.getTracks().forEach((t) => t.stop());
        stream = await navigator.mediaDevices.getUserMedia({
          video: { deviceId: { exact: usb.deviceId }, width: 1280, height: 720 },
        });
      }
      streamRef.current = stream;
      const v = videoRef.current;
      if (v) { v.srcObject = stream; await v.play(); setCamLabel(stream.getVideoTracks()[0]?.label || "카메라"); setCamErr(""); }
    } catch {
      setCamErr("카메라를 열 수 없습니다. HTTPS·브라우저 권한을 확인하세요.");
    }
  }, []);

  const stop = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
  }, []);

  const tick = useCallback(async () => {
    const v = videoRef.current;
    if (!v || !v.videoWidth || !v.videoHeight) return;
    if (Date.now() - cooldownRef.current < COOLDOWN_MS) return;
    const canvas = document.createElement("canvas");
    canvas.width = v.videoWidth; canvas.height = v.videoHeight;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.drawImage(v, 0, 0);
    const img = ctx.getImageData(0, 0, canvas.width, canvas.height);
    const { default: jsQR } = await import("jsqr");
    const code = jsQR(img.data, img.width, img.height);
    if (!code) return;
    const raw = code.data.trim();
    if (!PID_RE.test(raw)) return;
    cooldownRef.current = Date.now();
    onScanRef.current(raw);
  }, []);

  useEffect(() => {
    if (!active) { stop(); return; }
    start();
    intervalRef.current = setInterval(tick, SCAN_INTERVAL_MS);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
      stop();
    };
  }, [active, start, stop, tick]);

  return (
    <div className={className}>
      <video ref={videoRef} className="w-full rounded-2xl bg-black aspect-video object-cover"
             autoPlay muted playsInline />
      {camErr
        ? <p className="text-red-300 text-sm mt-2">{camErr}</p>
        : camLabel && <p className="text-white/60 text-xs mt-2">● {camLabel}</p>}
    </div>
  );
}
