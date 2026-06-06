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
