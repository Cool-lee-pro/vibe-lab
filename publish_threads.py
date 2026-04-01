import requests
import os
import re
import time
from datetime import datetime, timedelta

# 환경 변수 (기존과 동일)
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

def check_and_publish_each(tag, contents):
    """특정 태그 메시지에 ✅가 있는지 확인하고 발행"""
    url = f"https://slack.com/api/conversations.history?channel={MY_SLACK_ID}&limit=10"
    headers = {"Authorization": f"Bearer {SLACK_TOKEN}"}
    res = requests.get(url, headers=headers).json()
    
    if not res.get('ok'): return
    
    # 해당 태그명이 포함된 최근 초안 메시지 찾기
    for msg in res.get('messages', []):
        if f"[{tag}] 초안입니다" in msg.get('text', ''):
            reactions = msg.get('reactions', [])
            is_approved = any(r.get('name') == 'white_check_mark' for r in reactions)
            
            if is_approved:
                post_body = f"{tag}\n" + "\n".join([f"• {c}" for c in contents])
                # [Threads API 연동 지점]
                print(f"🚀 [발행 확정] {tag} 내용을 스레드에 올립니다.")
                return True
    return False

def send_individual_draft(tag, contents):
    """태그별로 개별 DM 발송"""
    url = "https://slack.com/api/chat.postMessage"
    headers = {"Authorization": f"Bearer {SLACK_TOKEN}"}
    
    formatted_contents = "\n".join([f"• {c}" for c in contents])
    message_text = f"🔔 *[{tag}] 초안입니다.*\n발행하시려면 이 메시지에 ✅를 달아주세요!\n\n---\n{formatted_contents}"
    
    payload = {"channel": MY_SLACK_ID, "text": message_text}
    requests.post(url, headers=headers, json=payload)

if __name__ == "__main__":
    msgs, status = get_recent_messages()
    if status == "정상":
        tag_data = parse_tags(msgs)
        for tag, contents in tag_data.items():
            # 1. 이미 승인된 게 있는지 확인해서 발행
            if not check_and_publish_each(tag, contents):
                # 2. 승인 전이라면 개별 초안 발송
                send_individual_draft(tag, contents)
                time.sleep(1) # 슬랙 API 부하 방지
