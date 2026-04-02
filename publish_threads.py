import requests
import os
import re
import time
from datetime import datetime, timedelta

# 1. 환경 변수 설정
SLACK_TOKEN = os.environ.get('SLACK_USER_TOKEN')
SOURCE_CHANNEL_ID = os.environ.get('SLACK_CHANNEL_ID')   # 원본 데이터 채널
REPORT_CHANNEL_ID = os.environ.get('REPORT_CHANNEL_ID') # 리포트 & 발행 채널
THREADS_USER_ID = os.environ.get('THREADS_USER_ID')
THREADS_ACCESS_TOKEN = os.environ.get('THREADS_ACCESS_TOKEN')

def post_to_threads(tag, contents):
    base_url = "https://graph.threads.net/v1.0"
    clean_tag = tag.replace("#", "")
    thread_text = f"#{clean_tag}\n" + "\n".join([f"• {c}" for c in contents])
    try:
        print(f"--- [DEBUG] Posting to Threads: {tag} ---")
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
    """리포트 채널에서 ✅ 체크된 건 발행"""
    headers = {"Authorization": f"Bearer {SLACK_TOKEN}"}
    res = requests.get(f"https://slack.com/api/conversations.history?channel={REPORT_CHANNEL_ID}&limit=100", headers=headers).json()
    if not res.get('ok'): return
    
    for msg in res.get('messages', []):
        text = msg.get('text', '')
        ts = msg.get('ts')
        reactions = [r.get('name') for r in msg.get('reactions', [])]
        is_report = text.startswith("📅") or "---" in text
        
        if is_report and 'white_check_mark' in reactions and 'rocket' not in reactions:
            requests.post("https://slack.com/api/reactions.add", headers=headers, json={"channel": REPORT_CHANNEL_ID, "name": "speech_balloon", "timestamp": ts})
            sections = text.split('#')[1:]
            for section in sections:
                lines = section.strip().split('\n')
                tag = "#" + lines[0].strip()
                contents = [l.replace('• ', '').replace('>• ', '').strip() for l in lines if '• ' in l]
                if contents:
                    success, result = post_to_threads(tag, contents)
                    if success:
                        requests.post("https://slack.com/api/reactions.add", headers=headers, json={"channel": REPORT_CHANNEL_ID, "name": "rocket", "timestamp": ts})
                    else:
                        requests.post("https://slack.com/api/reactions.add", headers=headers, json={"channel": REPORT_CHANNEL_ID, "name": "warning", "timestamp": ts})
                        error_msg = result.get('error', {}).get('message', 'Unknown Error')
                        requests.post("https://slack.com/api/chat.postMessage", headers=headers, json={"channel": REPORT_CHANNEL_ID, "text": f"❌ *발행 실패*: `{error_msg}`", "thread_ts": ts})

def send_combined_report(tag_data, start_dt, kst_now):
    """리포트 채널로 전송"""
    headers = {"Authorization": f"Bearer {SLACK_TOKEN}"}
    kst_start = start_dt + timedelta(hours=9)
    day_name = ['월','화','수','목','금','토','일'][kst_now.weekday()]
    header = f"📅 {kst_now.strftime('%Y-%m-%d')} ({day_name})\n-----------------------"
    requests.post("https://slack.com/api/chat.postMessage", headers=headers, json={"channel": REPORT_CHANNEL_ID, "text": header})
    for tag, contents in tag_data.items():
        body = f"`{tag}`\n" + "\n".join([f"• {c}" for c in contents])
        requests.post("https://slack.com/api/chat.postMessage", headers=headers, json={"channel": REPORT_CHANNEL_ID, "text": body})
        time.sleep(0.5)
    footer = f"-----------------------\n🕒 {kst_start.strftime('%m-%d %H:%M')} ~ {kst_now.strftime('%m-%d %H:%M')}"
    requests.post("https://slack.com/api/chat.postMessage", headers=headers, json={"channel": REPORT_CHANNEL_ID, "text": footer})

if __name__ == "__main__":
    kst_now = datetime.utcnow() + timedelta(hours=9)
    check_and_publish()
    start_dt = datetime.utcnow() - timedelta(hours=24)
    url = f"https://slack.com/api/conversations.history?channel={SOURCE_CHANNEL_ID}&oldest={start_dt.timestamp()}"
    headers = {"Authorization": f"Bearer {SLACK_TOKEN}"}
    slack_res = requests.get(url, headers=headers).json()
    
    if slack_res.get('ok'):
        tag_data = {}
        for msg in reversed(slack_res.get('messages', [])):
            text = msg.get('text', '')
            ts = msg.get('ts')
            reactions = [r.get('name') for r in msg.get('reactions', [])]
            if 'rocket' in reactions: continue
            tags = re.findall(r'#[\w가-힣]+', text)
            for t in tags:
                if t not in tag_data: tag_data[t] = []
                clean_txt = text.replace(t, "").strip()
                if clean_txt:
                    tag_data[t].append(clean_txt)
                    requests.post("https://slack.com/api/reactions.add", headers=headers, json={"channel": SOURCE_CHANNEL_ID, "name": "rocket", "timestamp": ts})
        
        if tag_data:
            send_combined_report(tag_data, start_dt, kst_now)
