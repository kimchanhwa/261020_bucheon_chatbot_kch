import hashlib
import json
import os
import sys
from datetime import date, datetime, timedelta

import requests
from dotenv import load_dotenv
from groq import Groq, RateLimitError, APIStatusError, APIConnectionError

# 1. 환경 변수 불러오기 (.env)
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

if not GROQ_API_KEY and not GEMINI_API_KEY:
    sys.exit(".env에 GROQ_API_KEY(또는 GEMINI_API_KEY)를 설정하세요. (.env.example 참고)")

groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

BOOKING_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bookings.json")

# 2. 진료과 목록 (예약 가능한 과)
DEPARTMENTS = [
    "내과", "외과", "정형외과", "신경과", "신경외과", "이비인후과", "안과", "피부과",
    "비뇨의학과", "산부인과", "소아청소년과", "정신건강의학과", "재활의학과", "가정의학과",
]

# 3. 챗봇 성격/규칙 (모델은 항상 JSON으로만 답함)
SYSTEM_PROMPT = f"""너는 대학병원 '진료과 안내·예약 도우미'야. 오늘 날짜는 {date.today().isoformat()}({"월화수목금토일"[date.today().weekday()]})이다.
예약 가능한 진료과: {", ".join(DEPARTMENTS)}

[역할]
1. 환자가 증상, 아픈 기간, 아픈 정도(1~10)를 말하면 가장 알맞은 진료과 1~2곳을 이유와 함께 추천한다.
   정보가 부족하면 위 세 가지 중 빠진 것을 먼저 짧게 물어본다. 질문은 한 번에 1~2개만 한다.
2. 환자가 예약을 원하면 {{"type":"slots","department":"진료과"}} 액션으로 예약 가능한 시간을 조회한다. 시간은 절대 지어내지 말고 조회 결과만 안내한다.
3. 환자가 시간을 고르면 이름과 연락처를 받은 뒤, 환자의 확인을 받고 {{"type":"book",...}} 액션으로 예약한다.
4. 의사가 아니므로 진단하지 않는다. 추천은 참고용이라고 짧게 알린다.
5. 응급 징후(심한 흉통, 호흡곤란, 의식저하, 마비, 대량 출혈, 심한 외상 등)가 있으면 예약 대신 즉시 119 또는 응급실 방문을 안내한다.
6. 병원 업무와 무관한 질문은 정중히 거절한다.

[출력 형식] 반드시 아래 JSON 객체 하나만 출력한다. 다른 텍스트 금지.
{{"reply": "환자에게 보여줄 한국어 답변", "action": null 또는 액션}}
액션 종류:
- {{"type":"slots","department":"진료과"}}
- {{"type":"book","department":"진료과","slot":"YYYY-MM-DD HH:MM","name":"이름","phone":"연락처"}}
액션을 쓸 때 reply는 "확인해 볼게요" 정도로 짧게 쓴다. (결과를 받은 뒤 다시 안내하게 된다)
시스템이 "[시스템 결과]"로 조회/예약 결과를 보내면 그 내용을 바탕으로 환자에게 안내하는 reply를 작성한다.
"""


# 4. 예약 시간 관리 (로컬 json 파일)
def load_bookings():
    if not os.path.exists(BOOKING_FILE):
        return []
    with open(BOOKING_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_bookings(bookings):
    with open(BOOKING_FILE, "w", encoding="utf-8") as f:
        json.dump(bookings, f, ensure_ascii=False, indent=2)


def all_slots(days=7):
    """오늘 이후 평일 진료 시간(30분 단위) 목록"""
    now = datetime.now()
    slots = []
    for d in range(1, days + 8):
        day = date.today() + timedelta(days=d)
        if day.weekday() >= 5:      # 주말 제외
            continue
        for hour, minute in [(h, m) for h in (9, 10, 11, 13, 14, 15, 16) for m in (0, 30)]:
            t = datetime(day.year, day.month, day.day, hour, minute)
            if t > now:
                slots.append(t.strftime("%Y-%m-%d %H:%M"))
    return slots


def is_busy(department, slot):
    """데모용: 이미 예약된 시간 + 가상의 기존 예약(약 1/3)"""
    if any(b["department"] == department and b["slot"] == slot for b in load_bookings()):
        return True
    return int(hashlib.md5(f"{department}{slot}".encode()).hexdigest(), 16) % 3 == 0


def free_slots(department, limit=10):
    return [s for s in all_slots() if not is_busy(department, s)][:limit]


# 5. 모델이 요청한 액션 실행
def run_action(action):
    if not isinstance(action, dict):
        return "액션 형식 오류"
    dept = action.get("department")
    if dept not in DEPARTMENTS:
        return f"예약할 수 없는 진료과입니다: {dept}. 가능한 진료과: {', '.join(DEPARTMENTS)}"

    if action.get("type") == "slots":
        slots = free_slots(dept)
        return f"{dept} 예약 가능 시간(빠른 순): " + ", ".join(slots)

    if action.get("type") == "book":
        slot, name, phone = action.get("slot"), action.get("name"), action.get("phone")
        if not (slot and name and phone):
            return "예약 실패: 시간, 이름, 연락처가 모두 필요합니다."
        if slot not in all_slots() or is_busy(dept, slot):
            return f"예약 실패: {slot}은 예약할 수 없는 시간입니다. 다른 시간을 안내하세요."
        bookings = load_bookings()
        bookings.append({"department": dept, "slot": slot, "name": name, "phone": phone,
                         "created": datetime.now().isoformat(timespec="seconds")})
        save_bookings(bookings)
        return f"예약 완료: {dept} {slot} / {name} / {phone}"

    return "알 수 없는 액션입니다."


# 6. LLM 호출 (Groq 우선, 한도 소진 시 Gemini)
def ask_groq(messages):
    res = groq_client.chat.completions.create(
        model=GROQ_MODEL,
        messages=messages,
        temperature=0.2,
        max_completion_tokens=800,
        reasoning_effort="low",
        response_format={"type": "json_object"},
    )
    return res.choices[0].message.content


def ask_gemini(messages):
    system = next((m["content"] for m in messages if m["role"] == "system"), "")
    contents = [
        {"role": "user" if m["role"] == "user" else "model", "parts": [{"text": m["content"]}]}
        for m in messages
        if m["role"] != "system"
    ]
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    res = requests.post(
        url,
        headers={"x-goog-api-key": GEMINI_API_KEY},
        json={
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": contents,
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 800,
                                 "responseMimeType": "application/json"},
        },
        timeout=60,
    )
    res.raise_for_status()
    return res.json()["candidates"][0]["content"]["parts"][0]["text"]


def get_answer(messages):
    if groq_client:
        try:
            return ask_groq(messages)
        except (RateLimitError, APIStatusError, APIConnectionError) as e:
            if not GEMINI_API_KEY:
                raise
            print(f"[알림] Groq 사용 불가({type(e).__name__}) → Gemini로 전환합니다.")
    return ask_gemini(messages)


def parse(text):
    try:
        data = json.loads(text)
        return str(data.get("reply", "")), data.get("action")
    except (json.JSONDecodeError, AttributeError):
        return text, None   # JSON이 아니면 그대로 보여줌


def chat_turn(messages, q):
    """질문 1개 처리 → 답변 문자열 반환 (터미널/웹 공용). 실패 시 대화 기록을 되돌리고 예외 발생"""
    start = len(messages)
    messages.append({"role": "user", "content": q})
    try:
        # 액션(조회/예약) 결과를 받아 다시 답변하는 과정을 최대 3번 반복
        for _ in range(3):
            raw = get_answer(messages)
            messages.append({"role": "assistant", "content": raw})
            reply, action = parse(raw)
            if not action:
                return reply
            result = run_action(action)
            messages.append({"role": "user", "content": f"[시스템 결과] {result}"})
        return "처리 중 문제가 생겼어요. 다시 말씀해 주세요."
    except Exception:
        del messages[start:]   # 실패한 턴은 기록에서 제거
        raise


def new_conversation():
    return [{"role": "system", "content": SYSTEM_PROMPT}]


# 7. 터미널 대화 루프
def main():
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    print("🏥 대학병원 진료과 안내·예약 챗봇입니다. 증상, 기간, 아픈 정도를 알려주세요. (종료: exit)")
    print("※ 참고용 안내이며 진단이 아닙니다. 응급 상황이면 119로 연락하세요.")

    while True:
        q = input("\n환자 : ").strip()
        if not q:
            continue
        if q.lower() in ("exit", "quit", "q"):
            print("종료합니다.")
            break

        try:
            print(f"상담원 : {chat_turn(messages, q)}")
        except Exception as e:
            print(f"[오류] 답변 실패: {e}")


if __name__ == "__main__":
    main()
