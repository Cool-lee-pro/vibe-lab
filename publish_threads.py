import requests
import os
import re
import time
from datetime import datetime, timedelta

# 환경 변수 설정
SLACK_TOKEN = os.environ.get('SLACK_USER_TOKEN')
MY_SLACK_ID = os.environ.get('MY_SLACK_ID')
CHANNEL_ID = os.environ.get('SLACK_CHANNEL_ID')

def get_recent_messages():
    start_time = (datetime.now() - timedelta(days=1)).timestamp()
    url = f"https://slack.com/api/conversations.history?channel={CHANNEL_ID}&oldest={start_time}"
    headers = {"Authorization": f"Bearer {SLACK_TOKEN}"}
    response = requests.get(url, headers=headers).json()
    return response.get('messages', []), "정상" if response.get('ok') else response.get('error')

def parse_tags(messages):
    organized = {}
    for msg in reversed(messages):
        text = msg.get('text', '')
        found_tags = re.findall(r'#[\w가-힣]+', text)
        if found_tags:
            for tag in found_tags:
                if tag not in organized: organized[tag] = []
                clean_text = text.replace(tag, "").strip()
                if clean_text: organized[tag].append(clean_text)
    return organized

def check_approval_and_publish(organized_data):
    """나에게 온 마지막 DM에 ✅ 반응이 있는지 확인 후 발행"""
    # 1. 나에게 온 DM 이력 가져오기
    url = f"https://slack.com/api/conversations.history?channel={MY_SLACK_ID}&limit=5"
    headers = {"Authorization": f"Bearer {SLACK_TOKEN}"}
    res = requests.get(url, headers=headers).json()
    
    if not res.get('ok'): return print(f"❌ DM 확인 실패: {res.get('error')}")

    # 2. 최근 메시지 중 로봇이 보낸 '초안' 메시지 찾기
    for msg in res.get('messages', []):
        if "오늘의 초안입니다" in msg.get('text', ''):
            reactions = msg.get('reactions', [])
            # ✅(white_check_mark) 반응이 있는지 확인
            is_approved = any(r.get('name') == 'white_check_mark' for r in reactions)
            
            if is_approved:
                print("✨ 승인 확인! 태그별 발행을 시작합니다.")
                for tag, contents in organized_data.items():
                    post_content = f"{tag}\n" + "\n".join([f"• {c}" for c in contents])
                    
                    # [중요] 여기에 나중에 Threads API 연동 코드가 들어갑니다!
                    print(f"🚀 [발행 예정] {post_content}")
                    
                    # API 부하 방지를 위한 간격
                    time.sleep(2)
                return True
    
    print("⏳ 아직 승인(✅)이 되지 않았습니다.")
    return False

def send_draft(content):
    url = "https://slack.com/api/chat.postMessage"
    headers = {"Authorization": f"Bearer {SLACK_TOKEN}"}
    message_text = f"🔔 *오늘의 초안입니다.*\n발행하시려면 이 메시지에 ✅ 반응을 달아주세요!\n\n---\n{content}"
    payload = {"channel": MY_SLACK_ID, "text": message_text}
    requests.post(url, headers=headers, json=payload)

if __name__ == "__main__":
    msgs, status = get_recent_messages()
    if status == "정상":
        data = parse_tags(msgs)
        if data:
            # 승인 여부 먼저 체크
            if not check_approval_and_publish(data):
                # 승인이 안 되어 있다면 초안 다시 발송 (또는 기존 로직 유지)
                formatted = ""
                for tag, contents in data.items():
                    formatted += f"*{tag}*\n" + "\n".join([f"• {c}" for c in contents]) + "\n\n"
                send_draft(formatted)
