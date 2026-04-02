import requests
import os
import re
import time
from datetime import datetime, timedelta

# 1. GitHub Secrets에서 값 가져오기
SLACK_TOKEN = os.environ.get('SLACK_USER_TOKEN')
MY_SLACK_ID = os.environ.get('MY_SLACK_ID')
CHANNEL_ID = os.environ.get('SLACK_CHANNEL_ID')
THREADS_USER_ID = os.environ.get('THREADS_USER_ID')
THREADS_ACCESS_TOKEN = os.environ.get('THREADS_ACCESS_TOKEN')

def post_to_threads(tag, contents):
    """스레드 API 호출 (텍스트 전용)"""
    base_url = "https://graph.threads.net/v1.0"
    # 태그에서 # 제거 후 본문 구성
    clean_tag = tag.replace("#", "")
    thread_text = f"#{clean_tag}\n" + "\n".join([f"• {c}" for c in contents])
    
    try:
        # STEP 1: 컨테이너 생성
        c_res = requests.post(f"{base_url}/{THREADS_USER_ID}/threads", params={
            "media_type": "TEXT", "text": thread_text, "access_token": THREADS_ACCESS_TOKEN
        }).json()
        
        creation_id = c_res.get('id')
        if not creation_id: return False, c_res

        # STEP 2: 게시
        p_res = requests.post(f"{base_url}/{THREADS_USER_ID}/threads_publish", params={
            "creation_id": creation_id, "access_token": THREADS_ACCESS_TOKEN
        }).json()
        
        return ("id" in p_res), p_res
    except Exception as e:
        return False, str(e)

def check_and_publish():
    """슬랙 DM에서 ✅ 승인된 건 찾아서 발행"""
    headers = {"Authorization": f"Bearer {SLACK_TOKEN}"}
    res = requests.get(f"https://slack.com/api/conversations.history?channel={MY_SLACK_ID}&limit=20", headers=headers).json()
    
    if not res.get('ok'): return
    
    for msg in res.get('messages', []):
        text = msg.get('text', '')
        ts = msg.get('ts')
        reactions = msg.get('reactions', [])
        
        # ✅는 있고 🚀는 없는 메시지 찾기
        has_check = any(r.get('name') == 'white_check_mark' for r in reactions)
        has_rocket = any(r.get('name') == 'rocket' for r in reactions)
        
        if has_check and not has_rocket:
            # 태그 추출 및 본문 파싱
            tag_match = re.search(r'#([\w가-힣]+)', text)
            if tag_match:
                tag = tag_match.group(0)
                # 인용구 기호 제거하고 내용만 추출
                contents = [l.replace('>• ', '').strip() for l in text.split('\n') if l.startswith('>•')]
                
                success, _ = post_to_threads(tag, contents)
                if success:
                    # 성공하면 🚀 이모지 달아주기
                    requests.post("https://slack.com/api/reactions.add", headers=headers, 
                                  json={"channel": MY_SLACK_ID, "name": "rocket", "timestamp": ts})

def send_combined_report(tag_data, start_dt):
    """오늘의 통합 리포트 전송 (기획자님 커스텀 UI)"""
    headers = {"Authorization": f"Bearer {SLACK_TOKEN}"}
    kst_now = datetime.utcnow() + timedelta(hours=9)
    kst_start = start_dt + timedelta(hours=9)
    day_name = ['월','화','수','목','금','토','일'][kst_now.weekday()]
    
    # 헤더
    header = f"📅 {kst_now.strftime('%Y-%m-%d')} ({day_name})\n-----------------------"
    requests.post("https://slack.com/api/chat.postMessage", headers=headers, json={"channel": MY_SLACK_ID, "text": header})
    
    # 본문 (태그별 개별 메시지)
    for tag, contents in tag_data.items():
        body = f"{tag}\n" + "\n".join([f">• {c}" for c in contents])
        requests.post("https://slack.com/api/chat.postMessage", headers=headers, json={"channel": MY_SLACK_ID, "text": body})
        time.sleep(0.5)

    # 푸터
    footer = f"-----------------------\n🕒 {kst_start.strftime('%m-%d %H:%M')} ~ {kst_now.strftime('%m-%d %H:%M')}"
    requests.post("https://slack.com/api/chat.postMessage", headers=headers, json={"channel": MY_SLACK_ID, "text": footer})

if __name__ == "__main__":
    now = datetime.now()
    # KST 기준 시간 분할
    current_time = int(now.strftime('%H%M'))
    start_dt = now - timedelta(hours=15, minutes=25) if current_time < 1200 else now - timedelta(hours=8, minutes=35)
    
    # 1. 승인된 건 있으면 스레드 발행부터!
    check_and_publish()
    
    # 2. 새로운 기록들 긁어와서 슬랙 리포트 쏘기
    url = f"https://slack.com/api/conversations.history?channel={CHANNEL_ID}&oldest={start_dt.timestamp()}"
    headers = {"Authorization": f"Bearer {SLACK_TOKEN}"}
    slack_res = requests.get(url, headers=headers).json()
    
    if slack_res.get('ok'):
        tag_data = {}
        for msg in reversed(slack_res.get('messages', [])):
            text = msg.get('text', '')
            tags = re.findall(r'#[\w가-힣]+', text)
            for t in tags:
                if t not in tag_data: tag_data[t] = []
                clean_txt = text.replace(t, "").strip()
                if clean_txt: tag_data[t].append(clean_txt)
        
        if tag_data:
            send_combined_report(tag_data, start_dt)
