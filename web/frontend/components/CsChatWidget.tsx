"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { askCsBot, UI_TEXT, LANGS, type CsMsg, type Lang } from "@/lib/csChat";

/* 환자용 CS 챗봇 — 우측 하단 떠 있는 동그란 위젯(draggable). 클릭하면 챗봇 패널이 펼쳐진다.
   heo/kiosk.html 의 병원 안내 챗봇("메디")을 이식 — AI 봇(Ollama)만, 직원연결 제외. */

/* Web Speech API(STT) 최소 타입 — 표준 lib.dom 에 없어 직접 선언. */
type SpeechRecognitionLike = {
  lang: string; interimResults: boolean; maxAlternatives: number;
  onresult: (ev: { results: { [i: number]: { [j: number]: { transcript: string } } } }) => void;
  onend: () => void; onerror: () => void; start: () => void; stop: () => void;
};
type WindowSpeech = Window & {
  webkitSpeechRecognition?: new () => SpeechRecognitionLike;
  SpeechRecognition?: new () => SpeechRecognitionLike;
};

const FAB = 60;          // 위젯 지름(px)
const MARGIN = 22;       // 화면 가장자리 기본 여백
const PANEL_W = 360;
const PANEL_H = 540;
const DRAG_THRESHOLD = 6; // 이 거리 미만 이동은 '클릭'으로 간주
const POS_KEY = "cs:fabpos";
const LANG_KEY = "cs:lang";
const SID_KEY = "cs:sid";

type Bubble = { role: "user" | "bot"; text: string };
type Pos = { left: number; top: number };

const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));

export default function CsChatWidget() {
  const [mounted, setMounted] = useState(false);
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<Pos>({ left: 0, top: 0 });
  const [lang, setLang] = useState<Lang>("ko");
  const [langOpen, setLangOpen] = useState(false);

  const [bubbles, setBubbles] = useState<Bubble[]>([]);
  const [input, setInput] = useState("");
  const [thinking, setThinking] = useState(false);
  const [listening, setListening] = useState(false);

  const dragRef = useRef<{ dx: number; dy: number; moved: boolean } | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const recRef = useRef<SpeechRecognitionLike | null>(null);
  const sidRef = useRef<string>("");
  const t = UI_TEXT[lang];

  /* 마운트 — 저장된 위치/언어 복원, 없으면 우측 하단 기본값. 세션ID 발급(로그 키) */
  useEffect(() => {
    setMounted(true);
    const savedSid = sessionStorage.getItem(SID_KEY);
    sidRef.current = savedSid || `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    if (!savedSid) sessionStorage.setItem(SID_KEY, sidRef.current);
    const savedLang = localStorage.getItem(LANG_KEY) as Lang | null;
    if (savedLang && LANGS.some((l) => l.code === savedLang)) setLang(savedLang);
    const saved = localStorage.getItem(POS_KEY);
    const def = { left: window.innerWidth - FAB - MARGIN, top: window.innerHeight - FAB - MARGIN };
    if (saved) {
      try {
        const p = JSON.parse(saved) as Pos;
        setPos({
          left: clamp(p.left, MARGIN, window.innerWidth - FAB - MARGIN),
          top: clamp(p.top, MARGIN, window.innerHeight - FAB - MARGIN),
        });
      } catch { setPos(def); }
    } else setPos(def);
  }, []);

  /* 새 메시지 → 맨 아래로 스크롤 */
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [bubbles, thinking]);

  useEffect(() => { if (mounted) localStorage.setItem(LANG_KEY, lang); }, [lang, mounted]);

  /* ── 드래그(포인터) — 임계 미만 이동은 클릭으로 처리 ── */
  const onPointerDown = useCallback((e: React.PointerEvent) => {
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
    dragRef.current = { dx: e.clientX - pos.left, dy: e.clientY - pos.top, moved: false };
  }, [pos]);

  const onPointerMove = useCallback((e: React.PointerEvent) => {
    const d = dragRef.current;
    if (!d) return;
    const left = clamp(e.clientX - d.dx, MARGIN, window.innerWidth - FAB - MARGIN);
    const top = clamp(e.clientY - d.dy, MARGIN, window.innerHeight - FAB - MARGIN);
    if (Math.abs(e.clientX - d.dx - pos.left) > DRAG_THRESHOLD ||
        Math.abs(e.clientY - d.dy - pos.top) > DRAG_THRESHOLD) d.moved = true;
    setPos({ left, top });
  }, [pos]);

  const onPointerUp = useCallback((e: React.PointerEvent) => {
    const d = dragRef.current;
    dragRef.current = null;
    if (!d) return;
    if (d.moved) localStorage.setItem(POS_KEY, JSON.stringify({ left: pos.left, top: pos.top }));
    else setOpen((o) => !o);   // 이동 없음 = 클릭 → 토글
    (e.target as HTMLElement).releasePointerCapture?.(e.pointerId);
  }, [pos]);

  /* ── 전송 → Ollama 봇 ── */
  const send = useCallback(async (text: string) => {
    const q = text.trim();
    if (!q || thinking) return;
    setInput("");
    setBubbles((b) => [...b, { role: "user", text: q }]);
    setThinking(true);
    const history: CsMsg[] = [
      ...bubbles.map((b) => ({ role: (b.role === "bot" ? "assistant" : "user") as CsMsg["role"], content: b.text })),
      { role: "user", content: q },
    ];
    try {
      const reply = await askCsBot(history, lang, sidRef.current);
      setBubbles((b) => [...b, { role: "bot", text: reply }]);
    } catch (err) {
      setBubbles((b) => [...b, { role: "bot", text: t.errPrefix + (err instanceof Error ? err.message : "error") }]);
    } finally {
      setThinking(false);
    }
  }, [bubbles, lang, thinking, t]);

  /* ── 음성 입력(STT) — 미지원 브라우저면 마이크 숨김 ── */
  const sttSupported = mounted && typeof window !== "undefined" &&
    !!((window as WindowSpeech).webkitSpeechRecognition || (window as WindowSpeech).SpeechRecognition);

  const toggleStt = useCallback(() => {
    if (listening) { recRef.current?.stop(); return; }
    const Ctor = (window as WindowSpeech).webkitSpeechRecognition || (window as WindowSpeech).SpeechRecognition;
    if (!Ctor) return;
    const rec = new Ctor();
    rec.lang = t.sttLang;
    rec.interimResults = false;
    rec.maxAlternatives = 1;
    rec.onresult = (ev) => { const txt = ev.results[0]?.[0]?.transcript ?? ""; if (txt) send(txt); };
    rec.onend = () => setListening(false);
    rec.onerror = () => setListening(false);
    recRef.current = rec;
    setListening(true);
    rec.start();
  }, [listening, t.sttLang, send]);

  if (!mounted) return null;

  /* 패널은 위젯 모서리 기준 위쪽/왼쪽으로 펼치되 화면 안으로 클램프 */
  const panelLeft = clamp(pos.left + FAB - PANEL_W, MARGIN, window.innerWidth - PANEL_W - MARGIN);
  const panelTop = clamp(pos.top - PANEL_H - 12, MARGIN, window.innerHeight - PANEL_H - MARGIN);

  return (
    <>
      {/* ── 채팅 패널 ── */}
      {open && (
        <div
          className="fixed z-[60] flex flex-col rounded-[22px] bg-surface border border-line overflow-hidden animate-[csPop_.18s_ease-out]"
          style={{ left: panelLeft, top: panelTop, width: PANEL_W, height: PANEL_H, boxShadow: "0 24px 60px -18px rgba(20,32,43,.34)" }}
        >
          {/* 헤더 */}
          <div className="relative px-4 pt-4 pb-3 text-white" style={{ background: "linear-gradient(135deg,#2f74e0,#1e5fc4)" }}>
            <div className="flex items-center gap-3">
              <span className={`grid place-items-center w-11 h-11 rounded-full bg-white/15 ring-2 ring-white/40 ${thinking ? "animate-pulse" : ""}`}>
                <MediFace />
              </span>
              <div className="min-w-0 flex-1">
                <div className="font-bold text-[15px] leading-tight">{t.statusMain}</div>
                <div className="text-white/75 text-[12px] mt-0.5 flex items-center gap-1.5">
                  <span className="w-1.5 h-1.5 rounded-full" style={{ background: "#6ee7a8" }} /> {t.badge}
                </div>
              </div>

              {/* 언어 선택 */}
              <div className="relative">
                <button onClick={() => setLangOpen((v) => !v)}
                  className="px-2.5 h-8 rounded-lg bg-white/15 hover:bg-white/25 text-[12px] font-semibold flex items-center gap-1 transition-colors">
                  {LANGS.find((l) => l.code === lang)?.label}
                  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round"><path d="m6 9 6 6 6-6" /></svg>
                </button>
                {langOpen && (
                  <div className="absolute right-0 top-9 z-10 w-28 rounded-xl bg-surface border border-line shadow-lg overflow-hidden">
                    {LANGS.map((l) => (
                      <button key={l.code} onClick={() => { setLang(l.code); setLangOpen(false); }}
                        className={`w-full text-left px-3 py-2 text-[13px] hover:bg-surface-2 ${l.code === lang ? "text-blue font-semibold" : "text-ink-2"}`}>
                        {l.label}
                      </button>
                    ))}
                  </div>
                )}
              </div>

              <button onClick={() => setOpen(false)} aria-label="닫기"
                className="grid place-items-center w-8 h-8 rounded-lg bg-white/10 hover:bg-white/25 transition-colors">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round"><path d="M18 6 6 18M6 6l12 12" /></svg>
              </button>
            </div>
          </div>

          {/* 대화 영역 */}
          <div ref={scrollRef} className="flex-1 overflow-y-auto px-3.5 py-4 flex flex-col gap-2.5 bg-canvas">
            {bubbles.length === 0 && (
              <div className="m-auto text-center text-ink-3 text-[13.5px] leading-relaxed whitespace-pre-line px-6">
                {t.chatEmpty}
              </div>
            )}
            {bubbles.map((b, i) => <BubbleRow key={i} role={b.role} text={b.text} />)}
            {thinking && (
              <div className="flex items-end gap-2">
                <Avatar bot />
                <div className="rounded-2xl rounded-bl-md bg-blue-soft px-3.5 py-3 flex items-center gap-1">
                  <Dot /> <Dot d=".15s" /> <Dot d=".3s" />
                </div>
              </div>
            )}
          </div>

          {/* 빠른 질문 칩 */}
          <div className="px-3.5 pt-2.5 flex gap-1.5 flex-wrap border-t border-line bg-surface">
            {t.quicks.map((q) => (
              <button key={q.key} onClick={() => send(q.send)} disabled={thinking}
                className="px-3 py-1.5 rounded-full border border-line text-[12.5px] text-ink-2 hover:border-blue hover:text-blue disabled:opacity-50 transition-colors">
                {q.chip}
              </button>
            ))}
          </div>

          {/* 입력 */}
          <div className="px-3.5 py-3 bg-surface flex items-center gap-2">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") send(input); }}
              placeholder={t.placeholder}
              className="flex-1 h-11 rounded-xl border border-line bg-surface px-3.5 text-[14px] text-ink focus:outline-none focus:border-blue transition-colors"
            />
            {sttSupported && (
              <button onClick={toggleStt} aria-label="음성 입력"
                className={`grid place-items-center w-11 h-11 rounded-xl shrink-0 transition-colors ${listening ? "bg-red text-white animate-pulse" : "bg-surface-2 text-ink-2 hover:text-blue border border-line"}`}>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="9" y="2" width="6" height="12" rx="3" /><path d="M5 10a7 7 0 0 0 14 0M12 19v3" /></svg>
              </button>
            )}
            <button onClick={() => send(input)} disabled={thinking || !input.trim()} aria-label={t.send}
              className="grid place-items-center w-11 h-11 rounded-xl shrink-0 bg-blue text-white hover:bg-[#1e5fc4] disabled:opacity-40 transition-colors">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m22 2-7 20-4-9-9-4Z" /><path d="M22 2 11 13" /></svg>
            </button>
          </div>
        </div>
      )}

      {/* ── 동그란 위젯(FAB) ── */}
      <button
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        aria-label="병원 안내 챗봇 열기"
        className="fixed z-[60] rounded-full grid place-items-center text-white touch-none select-none cursor-grab active:cursor-grabbing transition-transform hover:scale-105"
        style={{
          left: pos.left, top: pos.top, width: FAB, height: FAB,
          background: "linear-gradient(135deg,#2f74e0,#1e5fc4)",
          boxShadow: "0 10px 26px -8px rgba(47,116,224,.7)",
        }}
      >
        {!open && <span className="absolute inset-0 rounded-full animate-ping opacity-25" style={{ background: "#2f74e0" }} />}
        <span className="relative">{open ? <ChevronDown /> : <MediFace big />}</span>
      </button>
    </>
  );
}

/* ── 보조 컴포넌트 ─────────────────────────────────────────────── */
function BubbleRow({ role, text }: { role: "user" | "bot"; text: string }) {
  const user = role === "user";
  return (
    <div className={`flex items-end gap-2 ${user ? "flex-row-reverse" : ""}`}>
      <Avatar bot={!user} />
      <div className={`max-w-[78%] px-3.5 py-2.5 text-[14px] leading-relaxed whitespace-pre-line ${
        user ? "bg-blue text-white rounded-2xl rounded-br-md" : "bg-blue-soft text-ink rounded-2xl rounded-bl-md"
      }`}>
        {text}
      </div>
    </div>
  );
}

function Avatar({ bot }: { bot?: boolean }) {
  return (
    <span className={`grid place-items-center w-7 h-7 rounded-full shrink-0 ${bot ? "bg-blue-soft text-blue" : "bg-surface-2 text-ink-3"}`}>
      {bot
        ? <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round"><rect x="4" y="8" width="16" height="11" rx="3" /><path d="M12 8V4M9 13h.01M15 13h.01" /></svg>
        : <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="8" r="3.4" /><path d="M5 20c0-3.6 3.1-6 7-6s7 2.4 7 6" /></svg>}
    </span>
  );
}

function MediFace({ big }: { big?: boolean }) {
  const s = big ? 28 : 22;
  return (
    <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
      <rect x="4" y="8" width="16" height="11" rx="3.4" /><path d="M12 8V4.5" /><circle cx="12" cy="4" r="1.2" fill="currentColor" stroke="none" />
      <circle cx="9.2" cy="13.5" r="1.1" fill="currentColor" stroke="none" /><circle cx="14.8" cy="13.5" r="1.1" fill="currentColor" stroke="none" />
      <path d="M9.5 16.4h5" />
    </svg>
  );
}

function ChevronDown() {
  return <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"><path d="m6 9 6 6 6-6" /></svg>;
}

function Dot({ d = "0s" }: { d?: string }) {
  return <span className="w-1.5 h-1.5 rounded-full bg-blue inline-block" style={{ animation: "csBounce .9s infinite", animationDelay: d }} />;
}
