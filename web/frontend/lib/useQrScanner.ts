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
