# 두브란스 병원 안내 시스템

두산 로보틱스 부트캠프 — 간호사 보조 로봇 프로젝트의 병원 내 키오스크 & 직원 대시보드 웹 앱입니다.

## 화면 구성

| 페이지 | 경로 | 설명 |
|--------|------|------|
| 키오스크 | `kiosk.html` | 환자용 AI 챗봇 + 4개국어 지원 |
| 직원 대시보드 | `staff.html` | 호출 알림, 환자 채팅, 건의함 실시간 수신 |
| QR 약품 관리 | `index.html` | 약품 QR 등록 및 스캔 |

## 주요 기능

- **AI 안내 챗봇** — Ollama (gemma3:4b) 기반 병원 정보 Q&A
- **다국어 지원** — KO 한국어 / EN English / 中 中文 / 日 日本語
- **음성 입력(STT)** — Web Speech API, 언어별 자동 전환
- **음성 출력(TTS)** — SpeechSynthesis, 언어별 음성 선택
- **실시간 통신** — BroadcastChannel (로봇 호출 / 간호사 호출 / 직원 채팅 / 건의함)
- **PWA** — 오프라인 캐시, 홈 화면 설치 지원
- **모바일 AI 연결** — 같은 Wi-Fi 환경이면 PC의 Ollama에 자동 접속

## 로컬 실행

```bash
# Ollama 실행 (AI 챗봇용)
ollama serve
ollama run gemma3:4b

# 웹 서버 실행
cd medqr
python3 -m http.server 3000

# 브라우저에서 열기
# http://localhost:3000/kiosk.html   ← 환자용 키오스크
# http://localhost:3000/staff.html   ← 직원 대시보드
```

## 모바일에서 AI 사용하기

모바일 기기가 **PC와 같은 Wi-Fi**에 연결되어 있으면 AI 챗봇이 자동으로 작동합니다.

1. PC에서 Ollama 실행: `ollama serve`
2. PC의 로컬 IP 확인: `ip addr` (예: `192.168.1.10`)
3. 모바일 브라우저에서 접속:
   ```
   http://192.168.1.10:3000/kiosk.html
   ```
4. AI 채팅 탭에서 정상 동작 확인

> GitHub Pages 버전(`https://heopaulo.github.io/...`)은 HTTPS 페이지에서
> 로컬 Ollama(HTTP)를 호출할 수 없어 AI 기능이 동작하지 않습니다.
> 반드시 **로컬 서버**로 접속하세요.

## 모바일 설치

### iOS (iPhone / iPad)
1. **Safari**에서 로컬 서버 주소 접속
   ```
   http://<PC_IP>:3000/kiosk.html
   ```
2. 하단 **공유 버튼** (□↑) 탭
3. **홈 화면에 추가** 선택 → 추가
4. 홈 화면 아이콘으로 전체화면 실행

> Chrome은 홈 화면 추가를 지원하지 않으므로 반드시 **Safari** 사용

## 기술 스택

- **Frontend** — Vanilla HTML/CSS/JS (프레임워크 없음)
- **아이콘** — Lucide Icons v1.17.0 (로컬 번들, CDN 미사용)
- **AI** — Ollama API (포트 `11434`, model: `gemma3:4b`), 같은 네트워크 호스트 자동 감지
- **실시간** — BroadcastChannel API + localStorage storage event
- **음성** — Web Speech API (SpeechRecognition + SpeechSynthesis)
- **PWA** — Service Worker + Web App Manifest

## 프로젝트 구조

```
medqr/
├── kiosk.html          # 환자용 키오스크 (메인)
├── staff.html          # 직원 대시보드
├── index.html          # QR 약품 관리
├── sw.js               # Service Worker
├── manifest.json       # PWA 매니페스트
├── lucide.min.js       # Lucide 아이콘 번들 (v1.17.0)
├── doovrance_logo.png  # 두브란스 로고
└── icons/              # PWA 아이콘
```

## 개발 팀

두산 로보틱스 부트캠프 — 간호사 보조 로봇 팀  
병원명: 두브란스 (Doovrance)
