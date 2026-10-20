# 261020_bucheon_chatbot_kch

Groq API 기반 **대학병원 진료과 추천·예약 챗봇** (터미널 대화형).
환자가 증상·아픈 기간·아픈 정도를 말하면 알맞은 진료과를 추천하고, 비어 있는 시간을 보여주고 예약까지 해줍니다.
Groq 한도가 소진되거나 오류가 나면 **Gemini API로 자동 전환**됩니다.

> ⚠️ 학습용 데모입니다. 진단이 아니라 참고용 안내이며, 응급 상황은 119 / 응급실로 안내합니다.

## 구성
| 파일 | 설명 |
|---|---|
| `chatbot.py` | 챗봇 본체 (진료과 추천, 빈 시간 조회, 예약, Groq → Gemini 폴백) + 터미널 실행 |
| `app.py` | Flask 웹 서버 (`/api/chat`). API 키는 서버(.env)에만 있음 |
| `index.html` | 채팅 웹 화면 (모바일/다크모드 대응) |
| `requirements.txt` | 필요 라이브러리 (groq, python-dotenv, requests, flask) |
| `.env.example` | 환경변수 예시 (복사해서 `.env`로 사용) |
| `.gitignore` | `.env`, `bookings.json` 등 비공개 파일 제외 |
| `bookings.json` | 예약 저장 파일 (예약 시 자동 생성, 개인정보라 커밋 제외) |

## 사용법
1. 저장소 받기
   ```bash
   git clone https://github.com/<계정>/261020_bucheon_chatbot_kch.git
   cd 261020_bucheon_chatbot_kch
   ```
2. 라이브러리 설치
   ```bash
   pip install -r requirements.txt
   ```
3. 환경변수 설정: `.env.example`을 `.env`로 복사한 뒤 키 입력
   ```
   GROQ_API_KEY=발급받은_groq_키        # https://console.groq.com/keys
   GEMINI_API_KEY=발급받은_gemini_키    # https://aistudio.google.com/apikey (선택, 폴백용)
   ```
4. 실행 (둘 중 선택)
   - **웹 화면**: 아래 실행 후 브라우저에서 http://127.0.0.1:5000 접속
     ```bash
     python app.py
     ```
   - **터미널**: `python chatbot.py` (종료는 `exit`)

## 대화 예시
```
환자 : 3일 전부터 목이 아프고 콧물이 나요. 아픈 정도는 4예요
상담원 : 이비인후과가 가장 적합합니다. 내과도 고려해 보세요. (참고용 안내입니다)
환자 : 이비인후과 예약하고 싶어요
상담원 : 예약 가능한 시간은 2026-10-21 09:00, 09:30, ... 입니다.
환자 : 첫 번째로 할게요. 홍길동 010-1234-5678
상담원 : 예약이 완료되었습니다.
```

## 동작 방식
- 모델은 `{"reply": ..., "action": ...}` 형태의 JSON으로만 답하고, 프로그램이 `action`을 실행합니다.
  - `slots`: 해당 과의 빈 시간 조회 (평일 09:00~11:30, 13:00~16:30 / 30분 단위, 내일부터 약 2주)
  - `book`: 이름·연락처와 함께 예약 저장 (중복·잘못된 시간은 거부)
- 빈 시간은 `bookings.json`의 예약 + 데모용 가상 기존 예약으로 계산합니다. 실제 병원 시스템(DB)과 연동하려면 `free_slots`, `run_action`을 교체하세요.
- 기본은 Groq(`openai/gpt-oss-20b`), 실패 시 Gemini(`gemini-2.0-flash`). `.env`의 `GROQ_MODEL`, `GEMINI_MODEL`로 변경 가능.

## 주의
- `.env`와 `bookings.json`(환자 이름·연락처)은 절대 커밋하지 마세요. 키가 노출되면 즉시 재발급하세요.
