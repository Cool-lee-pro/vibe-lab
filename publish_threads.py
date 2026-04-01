import requests
import os
import re
from datetime import datetime, timedelta

SLACK_TOKEN = os.environ.get('SLACK_USER_TOKEN')
MY_SLACK_ID = os.environ.get('MY_SLACK_ID')
CHANNEL_ID = os.environ.get('SLACK_CHANNEL_ID')

def get_recent_messages():
    # 현재 시각 기준 24시간 전부터 긁어옵니다.
    start_time = (datetime.now() - timedelta(days=1)).timestamp()
    
    # [디버깅] 로봇이 지금 어디를 보고 있는지 로그에 출력합니다.
    print(f"🔍 디버깅: 채널 {CHANNEL_ID}에서 메시지를 찾고 있습니다...")
    
    url = f"https://slack.com/api/conversations.history?channel={CHANNEL_ID}&oldest={start_time}"
    headers = {"Authorization": f"Bearer {SLACK_TOKEN}"}
    
    response = requests.get(url, headers=headers).json()
    if not response.get('ok'):
        return [], f"슬랙 API 에러: {response.get('error')}"
    
    messages = response.get('messages', [])
    print(f"🔍 디버깅: 해당 채널에서 총 {len(messages)}개의 메시지를 발견했습니다.")
    return messages, "정상"

def format_content(messages):
    organized = {}
    for msg in reversed(messages):
        text = msg.get('text', '')
        found_tags = re.findall(r'#[\w가-힣]+', text)
        if found_tags:
            for tag in found_tags:
                if tag not in organized: organized[tag] = []
                clean_text = text.replace(tag, "").strip()
                if clean_text: organized[tag].append(clean_text)
    
    if not organized: return None
    
    final_text = f"🗓️ {datetime.now().strftime('%Y-%m-%d')} 기획자 로그\n\n"
    for tag, contents in organized.items():
        final_text += f"*{tag}*\n" + "\n".join([f"• {c}" for c in contents]) + "\n\n"
    return final_text

def send_to_slack(content, is_empty=False):
    url = "https://slack.com/api/chat.postMessage"
    headers = {"Authorization": f"Bearer {SLACK_TOKEN}"}
    
    message_text = content if content else "📭 기록된 태그 메시지가 없네요!"
    if not is_empty:
        message_text = f"🔔 *오늘의 초안입니다.*\n\n---\n{content}"

    payload = {"channel": MY_SLACK_ID, "text": message_text}
    res = requests.post(url, headers=headers, json=payload).json()
    print(f"🔍 디버깅: 메시지 전송 결과 -> {res.get('ok')}")

if __name__ == "__main__":
    msgs, status = get_recent_messages()
    if status != "정상":
        send_to_slack(f"❌ 시스템 에러: {status}", is_empty=True)
    else:
        content = format_content(msgs)
        send_to_slack(content, is_empty=(content is None))
