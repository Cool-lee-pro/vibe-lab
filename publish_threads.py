import requests
import os
import re
import time
from datetime import datetime, timedelta

# 환경 변수
SLACK_TOKEN = os.environ.get('SLACK_USER_TOKEN')
MY_SLACK_ID = os.environ.get('MY_SLACK_ID')
CHANNEL_ID = os.environ.get('SLACK_CHANNEL_ID')

def get_recent_messages():
    now = datetime.now()
    current_hour_min = int(now.strftime('%H%M'))
    
    # [시간 설계]
    # 1. 오전 7시 30분 실행 시: 어제 16:05 ~ 오늘 07:30 (약 15.5시간)
    if current_hour_min < 1200: 
        start_time = (now - timedelta(hours=15, minutes=25)).timestamp()
        period_label = "어제 오후 ~ 오늘 아침"
    # 2. 오후 4시 5분 실행 시: 오늘 07:30 ~ 오늘 16:05 (약 8.5시간)
    else:
        start_time = (now - timedelta(hours=8, minutes=35)).timestamp()
        period_label = "오늘 오전 ~ 오늘 오후"
        
    print(f"🔍 디버깅: {period_label} 범위를 수집 중입니다...")
    
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

def check_and_publish_each(tag, contents):
    """특정 태그 초안에 ✅가 달렸는지 확인 (최근 10개 DM 뒤지기)"""
    url = f"https://slack.com/api/conversations.history?channel={MY_SLACK_ID}&limit=15"
    headers = {"Authorization": f"Bearer {SLACK_TOKEN}"}
    res = requests.get(url, headers=headers).json()
    
    if not res.get('ok'): return False
    
    for msg in res.get('messages', []):
        # "[태그명] 초안입니다" 문구가 포함된 메시지 찾기
        if f"[{tag}] 초안입니다" in msg.get('text', ''):
            reactions = msg.get('reactions', [])
            # ✅ (white_check_mark) 이모지 확인
            is_approved = any(r.get('name') == 'white_check_mark' for r in reactions)
            
            if is_approved:
                # [이후 Threads API 연동될 곳]
                print(f"🚀 [발행 확정] {tag} 내용이 스레드로 전송됩니다.")
                # 한 번 발행된 것에 다시 ✅를 달아도 중복 발행되지 않도록 
                # 실제 API 연동 시 '발행 완료' 체크 로직을 추가할 예정입니다.
                return True
    return False

def send_individual_draft(tag, contents):
    url = "https://slack.com/api/chat.postMessage"
    headers = {"Authorization": f"Bearer {SLACK_TOKEN}"}
    
    today_str = datetime.now().strftime('%Y-%m-%d')
    # 각 줄 앞에 > 를 붙여 인용구(Blockquote)로 만듭니다.
    formatted_contents = "\n".join([f"> • {c}" for c in contents])
    
    # 헤더와 본문을 확실히 구분하되, 선 대신 공백과 인용구를 활용
    message_text = (
        f"📅 *{today_str}* |  #{tag}\n"
        f"{formatted_contents}"
    )
    
    payload = {
        "channel": MY_SLACK_ID, 
        "text": message_text,
        "mrkdwn": True 
    }
    requests.post(url, headers=headers, json=payload)

if __name__ == "__main__":
    msgs, status = get_recent_messages()
    if status == "정상":
        tag_data = parse_tags(msgs)
        if not tag_data:
            print("📭 수집된 태그 메시지가 없습니다.")
        
        for tag, contents in tag_data.items():
            # 1. 해당 태그의 초안이 이미 승인되었는지 확인
            if not check_and_publish_each(tag, contents):
                # 2. 승인 전이면 새로 초안 발송
                send_individual_draft(tag, contents)
                print(f"📩 {tag} 초안 메시지를 보냈습니다.")
                time.sleep(1)
    else:
        print(f"❌ 에러: {status}")
