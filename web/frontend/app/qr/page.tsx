"use client";
import { useCallback, useRef, useState } from "react";
import { getPatient, setDisplayPatient, type Patient } from "@/lib/api";
import { useQrScanner } from "@/lib/useQrScanner";

const PID_RE = /^P-\d{4}-\d{4}$/;
const COOLDOWN_MS = 3000;       // 같은 QR 연속 스캔 방지 (ms)

export default function QrPage() {
  const cooldownRef = useRef<number>(0); // 마지막 스캔 성공 시각
  const scanningRef = useRef(false);

  const [lastPid, setLastPid] = useState("");
  const [lastPatient, setLastPatient] = useState<Patient | null>(null);
  const [sending, setSending] = useState(false);
  const [sendErr, setSendErr] = useState("");
  const [rawQr, setRawQr] = useState<string | null>(null); // 디버그: 읽힌 원본 QR 값

  /* QR 디코드 → PID 검증·쿨다운·Firebase 전송 */
  const onDecode = useCallback(async (raw: string) => {
    if (Date.now() - cooldownRef.current < COOLDOWN_MS) return;
    setRawQr(raw); // 읽힌 내용 항상 표시 (디버그)

    // 환자 ID 형식이 아니면 전송하지 않음
    if (!PID_RE.test(raw)) return;

    // 같은 QR 반복 전송 방지
    cooldownRef.current = Date.now();

    // API 전송은 별도 플래그로 중복 방지
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

  return (
    <div className="p-6 max-w-2xl">
      <header className="mb-6">
        <h1 className="text-2xl font-bold text-ink">QR 스캔</h1>
        <p className="text-ink-3 text-sm mt-1">
          환자 QR 코드를 카메라에 비추면 병실 디스플레이에 문진표가 자동으로 표시됩니다.
        </p>
      </header>

      <section className="card p-5 flex flex-col gap-4">
        <h2 className="font-semibold text-ink flex items-center gap-2">
          <QrIcon /> 웹캠 QR 인식
        </h2>

        {!camOn && (
          <button onClick={startCam}
            className="w-full rounded-xl border-2 border-dashed border-line py-12 text-ink-3 text-sm hover:border-teal hover:text-teal transition-colors flex flex-col items-center gap-2">
            <QrIcon big />
            <span>웹캠 켜기</span>
          </button>
        )}

        <video
          ref={videoRef}
          className={`w-full rounded-xl bg-black ${camOn ? "block" : "hidden"}`}
          autoPlay muted playsInline
        />

        {camErr && <p className="text-red text-xs">{camErr}</p>}
        {camInfo && !camErr && (
          <p className="text-green text-xs flex items-center gap-1">
            <span>●</span> {camInfo} — QR 코드를 화면에 비추세요
          </p>
        )}

        {/* 스캔 상태 */}
        {camOn && (
          <div className={`flex items-center gap-2 rounded-xl border px-4 py-3 text-sm ${
            sending ? "border-amber/30 bg-amber-soft" : "border-teal/30 bg-teal-soft"
          }`}>
            {sending
              ? <><Spinner /><span className="text-amber font-semibold">전송 중…</span></>
              : <><span className="text-teal animate-pulse">●</span><span className="text-teal font-semibold">QR 인식 대기 중</span></>
            }
          </div>
        )}
        {sendErr && <p className="text-red text-xs">{sendErr}</p>}

        {/* 읽힌 QR 원본 표시 */}
        {rawQr && (
          <div className="rounded-xl border border-line bg-surface-2 px-4 py-2.5 text-xs font-mono">
            <span className="text-ink-3">QR 감지: </span>
            <span className={PID_RE.test(rawQr) ? "text-teal font-semibold" : "text-amber"}>
              {rawQr}
            </span>
            {!PID_RE.test(rawQr) && (
              <span className="text-ink-3 ml-2">(P-YYYY-NNNN 형식 아님)</span>
            )}
          </div>
        )}
      </section>

      {/* 마지막 스캔 결과 */}
      {lastPid && (
        <section className="card p-5 mt-4">
          <h2 className="font-semibold text-ink mb-3 flex items-center gap-2">
            <CheckIcon /> 마지막 스캔 결과
          </h2>
          <div className="rounded-xl bg-green-soft border border-green/30 p-4 flex items-center gap-4">
            <div className="w-10 h-10 rounded-xl bg-green/20 grid place-items-center shrink-0">
              <UserIcon />
            </div>
            <div>
              {lastPatient
                ? <p className="font-bold text-ink text-base">{lastPatient.성명}</p>
                : null
              }
              <p className="text-ink-3 text-sm font-mono">{lastPid}</p>
            </div>
            <span className="ml-auto text-green text-xs font-semibold">디스플레이 전송 완료 ✓</span>
          </div>
        </section>
      )}
    </div>
  );
}

/* ── 아이콘 ── */
function QrIcon({ big }: { big?: boolean }) {
  const s = big ? 32 : 17;
  return (
    <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" />
      <rect x="3" y="14" width="7" height="7" rx="1" />
      <path d="M14 14h1M19 14h1M14 19h3M19 19h1M14 17h1M17 17v2" />
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
function UserIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#18a259" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="8" r="3.5" /><path d="M5 20c0-3.9 3.1-6.5 7-6.5s7 2.6 7 6.5" />
    </svg>
  );
}
function Spinner() {
  return (
    <svg className="animate-spin" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
      <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
    </svg>
  );
}
