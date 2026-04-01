import requests
import os
import re
import time
from datetime import datetime, timedelta

# 1. 환경 변수 설정 (GitHub Secrets에 등록된 값들을 가져옵니다)
SLACK_TOKEN = os.environ.get('SLACK_USER_TOKEN')
MY_SLACK_ID = os.environ.get('MY_SLACK_ID')
CHANNEL_ID = os.environ.get('SLACK_CHANNEL_ID')

def get_recent_messages(start_timestamp):
    """지정된 시각 이후의 메시지를 슬랙에서 가져옵니다."""
    url = f"https://slack.com/api/conversations.history?channel={CHANNEL_ID}&oldest={start_timestamp}"
    headers = {"Authorization": f"Bearer {SLACK_TOKEN}"}
    response = requests.get(url, headers=headers).json()
    
    if not response.get('ok'):
        return [], response.get('error')
    return response.get('messages', []), "정상"

def parse_tags(messages):
    """메시지에서 #태그를 추출하여 태그별로 그룹화합니다."""
    organized = {}
    for msg in reversed(messages):
        text = msg.get('text', '')
        # 한글, 영문, 숫자 포함된 해시태그 찾기
        found_tags = re.findall(r'#[\w가-힣]+', text)
        if found_tags:
            for tag in found_tags:
                if tag not in organized:
                    organized[tag] = []
                # 본문에서 태그 자체는 제거하고 내용만 정제
                clean_text = text.replace(tag, "").strip()
                if clean_text:
                    organized[tag].append(clean_text)
    return organized

def check_and_publish_each(tag, contents):
    """나에게 온 DM 중 해당 태그 초안에 ✅ 반응이 있는지 확인합니다."""
    url = f"https://slack.com/api/conversations.history?channel={MY_SLACK_ID}&limit=20"
    headers = {"Authorization": f"Bearer {SLACK_TOKEN}"}
    res = requests.get(url, headers=headers).json()
    
    if not res.get('ok'):
        return False
    
    for msg in res.get('messages', []):
        # "[태그명] 초안" 문구가 포함된 로봇의 메시지를 찾습니다.
        if f"#{tag}" in msg.get('text', '') and "초안" in msg.get('text', ''):
            reactions = msg.get('reactions', [])
            # ✅ (white_check_mark) 이모지 확인
            is_approved = any(r.get('name') == 'white_check_mark' for r in reactions)
            
            if is_approved:
                # ------------------------------------------------------
                # [STEP 3: Threads API 연동 시 실제 발행 코드가 들어갈 자리]
                # ------------------------------------------------------
                print(f"✨ 승인 확인: {tag} 콘텐츠를 스레드 발행 큐에 넣습니다.")
                return True
    return False

def send_individual_draft(tag, contents, start_dt):
    url = "https://slack.com/api/chat.postMessage"
    headers = {"Authorization": f"Bearer {SLACK_TOKEN}"}
    
    # 1. UTC 서버 시간을 KST(UTC+9)로 변환
    kst_now = datetime.utcnow() + timedelta(hours=9)
    # start_dt도 UTC 기준일 것이므로 동일하게 9시간을 더해줍니다.
    kst_start = start_dt + timedelta(hours=9)
    
    now_str = kst_now.strftime('%m-%d %H:%M')
    start_str = kst_start.strftime('%m-%d %H:%M')
    today_str = kst_now.strftime('%Y-%m-%d')
    
    # 2. 본문 인용구 스타일
    formatted_contents = "\n".join([f"> • {c}" for c in contents])
    
    # 3. 최종 메시지 (기획자님 요청 스타일 적용)
    message_text = (
        f"📅 *{today_str}* | `{tag}`\n"
        f"🕒 {start_str} ~ {now_str}\n"
        f"{formatted_contents}"
    )
    
    payload = {
        "channel": MY_SLACK_ID, 
        "text": message_text,
        "mrkdwn": True 
    }
    requests.post(url, headers=headers, json=payload)

if __name__ == "__main__":
    now = datetime.now()
    current_time_num = int(now.strftime('%H%M'))
    
    # [시간 분할 로직]
    # 오전 12시 이전 실행(오전 스케줄): 어제 오후 4:05 ~ 현재 (약 15.5시간 전)
    if current_time_num < 1200:
        start_dt = now - timedelta(hours=15, minutes=25)
    # 오전 12시 이후 실행(오후 스케줄): 오늘 오전 7:30 ~ 현재 (약 8.5시간 전)
    else:
        start_dt = now - timedelta(hours=8, minutes=35)
        
    print(f"🚀 스크래핑 시작 시각: {start_dt.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 1. 메시지 수집
    msgs, status = get_recent_messages(start_dt.timestamp())
    
    if status == "정상":
        # 2. 태그별 그룹화
        tag_data = parse_tags(msgs)
        
        if not tag_data:
            print("📭 해당 시간 범위 내에 태그된 메시지가 없습니다.")
        else:
            for tag, contents in tag_data.items():
                # 3. 승인 여부 체크 (✅가 달려있으면 발행 프로세스 작동)
                if not check_and_publish_each(tag, contents):
                    # 4. 승인 전이라면 개별 초안 메시지 발송
                    send_individual_draft(tag, contents, start_dt)
                    print(f"📩 [{tag}] 초안 메시지를 보냈습니다.")
                    time.sleep(1) # API 안정성을 위한 짧은 대기
    else:
        print(f"❌ 슬랙 메시지 수집 실패: {status}")
