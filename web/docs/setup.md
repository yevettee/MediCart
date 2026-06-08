# 설치 / 실행

## 1. Firebase
- RTDB(asia-southeast1) + serviceAccountKey.json 발급. Rules는 `intel1/database.rules.json`(전면 잠금) 게시.

## 2. backend
```bash
cd MediCart/web/backend
python3 -m venv venv && venv/bin/pip install -r requirements.txt
cp .env.example .env   # FB_CRED/FB_DB_URL 등 채움
venv/bin/python app.py   # :5000
```

## 3. frontend
```bash
cd MediCart/web/frontend
npm install
NEXT_PUBLIC_PRIMARY_NS=robot6 npm run dev   # :3000 (또는 build/start)
```

## 4. 테스트(로봇/firebase 무관)
```bash
cd MediCart/web/backend && python3 -m pytest test/ -q
```
