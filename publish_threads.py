import requests
import os
import re
from datetime import datetime, timedelta

# 환경 변수 로드
SLACK_TOKEN = os.environ.get('SLACK_USER_TOKEN')
MY_SLACK_ID = os.environ.get('MY_SLACK_ID')
CHANNEL_ID = os.environ.get('SLACK_CHANNEL_ID')

def get_recent_messages():
    # 테스트를 위해 '어제 0시'부터 '현재 시각'까지 범위를 넓힙니다.
    yesterday = datetime.now() - timedelta(days=1)
    start_time = datetime.combine(yesterday, datetime.min.time()).timestamp()
    
    url = f"https://slack.com/api/conversations.history?channel={CHANNEL_ID}&oldest={start_time}"
    headers = {"Authorization": f"Bearer {SLACK_TOKEN}"}
    
    response = requests.get(url, headers=headers).json()
    if not response.get('ok'):
        return [], f"에러 발생: {response.get('error')}"
    
    return response.get('messages', []), "정상"

def format_content(messages):
    organized = {}
    
    for msg in reversed(messages):
        text = msg.get('text', '')
        # #태그 추출
        found_tags = re.findall(r'#[\w가-힣]+', text)
        
        if found_tags:
            for tag in found_tags:
                if tag not in organized:
                    organized[tag] = []
                clean_text = text.replace(tag, "").strip()
                if clean_text:
                    organized[tag].append(clean_text)
    
    if not organized:
        return None

    final_text = f"🗓️ {datetime.now().strftime('%Y-%m-%d')} 기획자 로그\n\n"
    for tag, contents in organized.items():
        final_text += f"*{tag}*\n" + "\n".join([f"• {c}" for c in contents]) + "\n\n"
            
    return final_text

def send_to_slack(content, is_empty=False):
    url = "https://slack.com/api/chat.postMessage"
    headers = {"Authorization": f"Bearer {SLACK_TOKEN}"}
    
    if is_empty:
        message_text = "📭 *오늘(어제)은 기록된 태그 메시지가 없네요!*\n업무 중간중간 `#회사생활` 처럼 태그를 달아 메모를 남겨보세요. ㅋㅋ"
    else:
        message_text = f"🔔 *오늘의 스레드 발행 초안입니다.*\n발행하시려면 이 메시지에 ✅ 이모지를 달아주세요!\n\n---\n{content}"
    
    payload = {
        "channel": MY_SLACK_ID,
        "text": message_text
    }
    requests.post(url, headers=headers, json=payload)

if __name__ == "__main__":
    msgs, status = get_recent_messages()
    
    if status != "정상":
        # 권한 문제나 채널 ID 오류 시 슬랙으로 에러 보고
        send_to_slack(f"시스템 에러: {status}", is_empty=False)
    else:
        content = format_content(msgs)
        if content:
            send_to_slack(content, is_empty=False)
        else:
            # 기록이 없을 때도 메시지 발송!
            send_to_slack(None, is_empty=True)
