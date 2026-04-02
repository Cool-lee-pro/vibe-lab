import requests
import os
import re
import time
from datetime import datetime, timedelta

# 1. 환경 변수 설정
SLACK_TOKEN = os.environ.get('SLACK_USER_TOKEN')
MY_SLACK_ID = os.environ.get('MY_SLACK_ID')
CHANNEL_ID = os.environ.get('SLACK_CHANNEL_ID')
THREADS_USER_ID = os.environ.get('THREADS_USER_ID')
THREADS_ACCESS_TOKEN = os.environ.get('THREADS_ACCESS_TOKEN')

def post_to_threads(tag, contents):
    base_url = "https://graph.threads.net/v1.0"
    clean_tag = tag.replace("#", "")
    thread_text = f"#{clean_tag}\n" + "\n".join([f"• {c}" for c in contents])
    
    try:
        c_res = requests.post(f"{base_url}/{THREADS_USER_ID}/threads", params={
            "media_type": "TEXT", "text": thread_text, "access_token": THREADS_ACCESS_TOKEN
        }).json()
        
        creation_id = c_res.get('id')
        if not creation_id: return False, c_res

        p_res = requests.post(f"{base_url}/{THREADS_USER_ID}/threads_publish", params={
            "creation_id": creation_id, "access_token": THREADS_ACCESS_TOKEN
        }).json()
        
        return ("id" in p_res), p_res
    except Exception as e:
        return False, str(e)

def check_and_publish():
    headers = {"Authorization": f"Bearer {SLACK_TOKEN}"}
    res = requests.get(f"https://slack.com/api/conversations.history?channel={MY_SLACK_ID}&limit=20", headers=headers).json()
    
    if not res.get('ok'): return
    
    for msg in res.get('messages', []):
        text = msg.get('text', '')
        ts = msg.get('ts')
        reactions = msg.get('reactions', [])
        
        has_check = any(r.get('name') == 'white_check_mark' for r in reactions)
        has_rocket = any(r.get('name') == 'rocket' for r in reactions)
        
        if has_check and not has_rocket:
            tag_match = re.search(r'#([\w가-힣]+)', text)
            if tag_match:
                tag = tag_match.group(0)
                # 인용구 스타일(>• ) 제거 로직
                contents = [l.replace('>• ', '').strip() for l in text.split('\n') if l.startswith('>•')]
                
                success, _ = post_to_threads(tag, contents)
                if success:
                    requests.post("https://slack.com/api/reactions.add", headers=headers, 
                                  json={"channel": MY_SLACK_ID, "name": "rocket", "timestamp": ts})

def send_combined_report(tag_data, start_dt, kst_now):
    headers = {"Authorization": f"Bearer {SLACK_TOKEN}"}
    kst_start = start_dt + timedelta(hours=9)
    day_name = ['월','화','수','목','금','토','일'][kst_now.weekday()]
    
    header = f"📅 {kst_now.strftime('%Y-%m-%d')} ({day_name})\n-----------------------"
    requests.post("https://slack.com/api/chat.postMessage", headers=headers, json={"channel": MY_SLACK_ID, "text": header})
    
    for tag, contents in tag_data.items():
        body = f"{tag}\n" + "\n".join([f">• {c}" for c in contents])
        requests.post("https://slack.com/api/chat.postMessage", headers=headers, json={"channel": MY_SLACK_ID, "text": body})
        time.sleep(0.5)

    footer = f"-----------------------\n🕒 {kst_start.strftime('%m-%d %H:%M')} ~ {kst_now.strftime('%m-%d %H:%M')}"
    requests.post("https://slack.com/api/chat.postMessage", headers=headers, json={"channel": MY_SLACK_ID, "text": footer})

if __name__ == "__main__":
    # 서버(UTC) 시간을 KST로 변환하여 기준 잡기
    kst_now = datetime.utcnow() + timedelta(hours=9)
    current_time_str = kst_now.strftime('%H%M')
    
    # 오전 실행 시 약 15시간 전(어제 오후부터), 오후 실행 시 약 8시간 전(오늘 오전부터) 데이터 수집
    if int(current_time_str) < 1200:
        start_dt = datetime.utcnow() - timedelta(hours=15, minutes=25)
    else:
        start_dt = datetime.utcnow() - timedelta(hours=8, minutes=35)
    
    # 1. 승인된 건 발행
    check_and_publish()
    
    # 2. 메시지 수집 및 리포트
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
            send_combined_report(tag_data, start_dt, kst_now)
