import requests
import os
import re
import time
from datetime import datetime, timedelta

# 환경 변수
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
        return False, {"error": {"message": str(e)}}

def check_and_publish():
    """✅ 승인 건 확인 및 발행"""
    headers = {"Authorization": f"Bearer {SLACK_TOKEN}"}
    res = requests.get(f"https://slack.com/api/conversations.history?channel={MY_SLACK_ID}&limit=50", headers=headers).json()
    if not res.get('ok'): return
    
    for msg in res.get('messages', []):
        text = msg.get('text', '')
        ts = msg.get('ts')
        reactions = [r.get('name') for r in msg.get('reactions', [])]
        
        if 'white_check_mark' in reactions and 'rocket' not in reactions and 'warning' not in reactions:
            # 💬 표시
            requests.post("https://slack.com/api/reactions.add", headers=headers, json={"channel": MY_SLACK_ID, "name": "speech_balloon", "timestamp": ts})
            tag_match = re.search(r'#([\w가-힣]+)', text)
            if tag_match:
                tag = tag_match.group(0)
                contents = [l.split('• ')[1].strip() for l in text.split('\n') if '• ' in l]
                success, result = post_to_threads(tag, contents)
                if success:
                    requests.post("https://slack.com/api/reactions.add", headers=headers, json={"channel": MY_SLACK_ID, "name": "rocket", "timestamp": ts})
                else:
                    requests.post("https://slack.com/api/reactions.add", headers=headers, json={"channel": MY_SLACK_ID, "name": "warning", "timestamp": ts})
                    error_msg = result.get('error', {}).get('message', 'Unknown Error')
                    requests.post("https://slack.com/api/chat.postMessage", headers=headers, json={"channel": MY_SLACK_ID, "text": f"❌ *발행 실패*: `{error_msg}`", "thread_ts": ts})

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
    kst_now = datetime.utcnow() + timedelta(hours=9)
    current_time_val = int(kst_now.strftime('%H%M'))
    
    # 1. 기존 리포트 중 ✅ 된 것들 먼저 처리 (이모지 업데이트)
    check_and_publish()
    
    # 2. 새 리포트 생성을 위한 데이터 수집
    if current_time_val < 1200:
        start_dt = datetime.utcnow() - timedelta(hours=15, minutes=30)
    else:
        start_dt = datetime.utcnow() - timedelta(hours=8, minutes=40)
        
    url = f"https://slack.com/api/conversations.history?channel={CHANNEL_ID}&oldest={start_dt.timestamp()}"
    headers = {"Authorization": f"Bearer {SLACK_TOKEN}"}
    slack_res = requests.get(url, headers=headers).json()
    
    if slack_res.get('ok'):
        tag_data = {}
        for msg in reversed(slack_res.get('messages', [])):
            text = msg.get('text', '')
            reactions = [r.get('name') for r in msg.get('reactions', [])]
            
            # [핵심] 이미 발행 성공(🚀)했거나 실패(⚠️)로 처리된 원본 메시지는 리포트에서 제외
            if 'rocket' in reactions or 'warning' in reactions:
                continue
                
            tags = re.findall(r'#[\w가-힣]+', text)
            for t in tags:
                if t not in tag_data: tag_data[t] = []
                clean_txt = text.replace(t, "").strip()
                if clean_txt: tag_data[t].append(clean_txt)
        
        # 3. 신선한 데이터가 있을 때만 새 리포트 발송
        if tag_data:
            send_combined_report(tag_data, start_dt, kst_now)
