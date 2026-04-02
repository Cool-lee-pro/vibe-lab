import requests
import os
import re
import time
from datetime import datetime, timedelta

# 환경 변수 설정
SLACK_TOKEN = os.environ.get('SLACK_USER_TOKEN')
SOURCE_CHANNEL_ID = os.environ.get('SLACK_CHANNEL_ID')   # 원본 로그 채널
REPORT_CHANNEL_ID = os.environ.get('REPORT_CHANNEL_ID') # 리포트 & 승인 채널
THREADS_USER_ID = os.environ.get('THREADS_USER_ID')
THREADS_ACCESS_TOKEN = os.environ.get('THREADS_ACCESS_TOKEN')

def post_to_threads(tag, contents):
    base_url = "https://graph.threads.net/v1.0"
    clean_tag = tag.replace("#", "")
    thread_text = f"#{clean_tag}\n" + "\n".join([f"• {c}" for c in contents])

    # 내 토큰으로 '나'의 진짜 ID를 찾아보는 코드 (디버그용)
    me_res = requests.get(f"https://graph.threads.net/v1.0/me?fields=id,username&access_token={THREADS_ACCESS_TOKEN}").json()
    print(f"--- [DEBUG] My Real ID    : {me_res} ---")  
    
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
    """리포트 채널에서 ✅가 달린 메시지만 발행"""
    headers = {"Authorization": f"Bearer {SLACK_TOKEN}"}
    res = requests.get(f"https://slack.com/api/conversations.history?channel={REPORT_CHANNEL_ID}&limit=50", headers=headers).json()
    if not res.get('ok'): return
    
    for msg in res.get('messages', []):
        text = msg.get('text', '')
        ts = msg.get('ts')
        reactions = [r.get('name') for r in msg.get('reactions', [])]
        
        if text.startswith("#") and 'white_check_mark' in reactions and 'rocket' not in reactions:
            requests.post("https://slack.com/api/reactions.add", headers=headers, json={"channel": REPORT_CHANNEL_ID, "name": "speech_balloon", "timestamp": ts})
            lines = text.strip().split('\n')
            tag = lines[0].strip()
            contents = [l.replace('• ', '').strip() for l in lines if l.startswith('• ')]
            
            if contents:
                success, result = post_to_threads(tag, contents)
                if success:
                    requests.post("https://slack.com/api/reactions.add", headers=headers, json={"channel": REPORT_CHANNEL_ID, "name": "rocket", "timestamp": ts})
                else:
                    requests.post("https://slack.com/api/reactions.add", headers=headers, json={"channel": REPORT_CHANNEL_ID, "name": "warning", "timestamp": ts})

def send_individual_reports(tag_data, kst_now):
    headers = {"Authorization": f"Bearer {SLACK_TOKEN}"}
    day_name = ['월','화','수','목','금','토','일'][kst_now.weekday()]
    header = f"📅 {kst_now.strftime('%Y-%m-%d')} ({day_name}) 리포트\n-----------------------"
    requests.post("https://slack.com/api/chat.postMessage", headers=headers, json={"channel": REPORT_CHANNEL_ID, "text": header})
    
    for tag, contents in tag_data.items():
        body = f"{tag}\n" + "\n".join([f"• {c}" for c in contents])
        requests.post("https://slack.com/api/chat.postMessage", headers=headers, json={"channel": REPORT_CHANNEL_ID, "text": body})
        time.sleep(0.5)

if __name__ == "__main__":
    # 한국 시간 기준 설정
    kst_now = datetime.utcnow() + timedelta(hours=9)
    current_hour = kst_now.hour
    
    # 1. ✅ 승인 건 먼저 처리
    check_and_publish()
    
    # 2. [중요] 시간 범위 설정 (기획자님 원래 기획 복구)
    if current_hour < 12: # 오전 세션 실행 시
        # 어제 오후 4시(16:00) ~ 오늘 현재까지
        start_dt = (kst_now - timedelta(days=1)).replace(hour=16, minute=0, second=0) - timedelta(hours=9)
    else: # 오후 세션 실행 시
        # 오늘 오전 7시 30분 ~ 오늘 현재까지
        start_dt = kst_now.replace(hour=7, minute=30, second=0) - timedelta(hours=9)
    
    # 3. 데이터 수집
    url = f"https://slack.com/api/conversations.history?channel={SOURCE_CHANNEL_ID}&oldest={start_dt.timestamp()}"
    headers = {"Authorization": f"Bearer {SLACK_TOKEN}"}
    slack_res = requests.get(url, headers=headers).json()
    
    if slack_res.get('ok'):
        tag_data = {}
        # 시간 순서대로 처리하기 위해 메시지 반전
        for msg in reversed(slack_res.get('messages', [])):
            text = msg.get('text', '')
            ts = msg.get('ts')
            reactions = [r.get('name') for r in msg.get('reactions', [])]
            
            # 이미 리포트에 포함된 건(☑️) 패스
            if 'ballot_box_with_check' in reactions: continue
            
            tags = re.findall(r'#[\w가-힣]+', text)
            for t in tags:
                if t not in tag_data: tag_data[t] = []
                clean_txt = text.replace(t, "").strip()
                if clean_txt:
                    tag_data[t].append(clean_txt)
                    # 원본에 리포트 포함 표식 남기기
                    requests.post("https://slack.com/api/reactions.add", headers=headers, json={"channel": SOURCE_CHANNEL_ID, "name": "ballot_box_with_check", "timestamp": ts})
        
        if tag_data:
            send_individual_reports(tag_data, kst_now)
