// 환자 CS 챗봇 — 병원 안내 로봇 "메디". heo/kiosk.html 의 안내 챗봇을 이식.
// 시스템 프롬프트(페르소나)는 백엔드(/api/cs_chat)가 언어별로 보유 — 여기선 UI 문자열만.
import { API_BASE } from "./api";

export type Lang = "ko" | "en" | "zh" | "ja";
export const LANGS: { code: Lang; label: string }[] = [
  { code: "ko", label: "한국어" },
  { code: "en", label: "EN" },
  { code: "zh", label: "中文" },
  { code: "ja", label: "日本語" },
];

export type CsMsg = { role: "user" | "assistant"; content: string };

type Quick = { key: string; chip: string; send: string };
type Strings = {
  title: string;
  statusMain: string;
  statusSub: string;
  badge: string;
  chatEmpty: string;
  placeholder: string;
  send: string;
  thinking: string;
  errPrefix: string;
  sttLang: string;
  quicks: Quick[];
};

export const UI_TEXT: Record<Lang, Strings> = {
  ko: {
    title: "병원 안내",
    statusMain: "무엇을 도와드릴까요?",
    statusSub: "아래 버튼을 눌러 질문해주세요",
    badge: "AI 안내 모드",
    chatEmpty: "아직 대화가 없습니다.\n질문을 입력하거나 말씀해주세요.",
    placeholder: "질문을 입력하세요…",
    send: "전송",
    thinking: "답변 중…",
    errPrefix: "잠시 연결이 어렵습니다: ",
    sttLang: "ko-KR",
    quicks: [
      { key: "reception", chip: "접수처", send: "접수처가 어디에 있나요?" },
      { key: "dept", chip: "진료과", send: "진료과 안내해주세요" },
      { key: "hours", chip: "운영시간", send: "운영시간이 어떻게 되나요?" },
      { key: "toilet", chip: "화장실", send: "화장실이 어디에 있나요?" },
    ],
  },
  en: {
    title: "Hospital Guide",
    statusMain: "How can I help you?",
    statusSub: "Tap a button below to ask",
    badge: "AI Guide",
    chatEmpty: "No messages yet.\nType or speak your question.",
    placeholder: "Type your question…",
    send: "Send",
    thinking: "Thinking…",
    errPrefix: "Connection trouble: ",
    sttLang: "en-US",
    quicks: [
      { key: "reception", chip: "Reception", send: "Where is the reception?" },
      { key: "dept", chip: "Departments", send: "Tell me about the departments" },
      { key: "hours", chip: "Hours", send: "What are the operating hours?" },
      { key: "toilet", chip: "Restroom", send: "Where is the restroom?" },
    ],
  },
  zh: {
    title: "医院向导",
    statusMain: "我能帮您什么？",
    statusSub: "请点击下方按钮提问",
    badge: "AI 向导",
    chatEmpty: "暂无对话。\n请输入问题或说话。",
    placeholder: "请输入您的问题…",
    send: "发送",
    thinking: "回答中…",
    errPrefix: "连接出现问题：",
    sttLang: "zh-CN",
    quicks: [
      { key: "reception", chip: "挂号处", send: "挂号处在哪里？" },
      { key: "dept", chip: "科室", send: "请介绍科室" },
      { key: "hours", chip: "营业时间", send: "营业时间是什么时候？" },
      { key: "toilet", chip: "洗手间", send: "洗手间在哪里？" },
    ],
  },
  ja: {
    title: "病院案内",
    statusMain: "ご用件をどうぞ",
    statusSub: "下のボタンを押してご質問ください",
    badge: "AI 案内",
    chatEmpty: "まだ会話はありません。\n質問を入力または話しかけてください。",
    placeholder: "ご質問を入力してください…",
    send: "送信",
    thinking: "回答中…",
    errPrefix: "接続に問題があります：",
    sttLang: "ja-JP",
    quicks: [
      { key: "reception", chip: "受付", send: "受付はどこですか？" },
      { key: "dept", chip: "診療科", send: "診療科を教えてください" },
      { key: "hours", chip: "診療時間", send: "診療時間はいつですか？" },
      { key: "toilet", chip: "トイレ", send: "トイレはどこですか？" },
    ],
  },
};

/** 대화 이력 + 언어 → 백엔드(Ollama 프록시) → 봇 답변 텍스트. 실패 시 throw. */
export async function askCsBot(messages: CsMsg[], lang: Lang): Promise<string> {
  const r = await fetch(`${API_BASE}/api/cs_chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages, lang }),
  });
  if (!r.ok) throw new Error(`/api/cs_chat → ${r.status}`);
  const data = (await r.json()) as { ok: boolean; reply?: string };
  if (!data.ok || !data.reply) throw new Error("no_reply");
  return data.reply;
}
