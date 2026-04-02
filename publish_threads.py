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
    """리포트 채널을 확인하여 ✅가 달린 개별 태그 메시지만 발행합니다"""
    headers = {"Authorization": f"Bearer {SLACK_TOKEN}"}
    res = requests.get(f"https://slack.com/api/conversations.history?channel={REPORT_CHANNEL_ID}&limit=100", headers=headers).json()
    if not res.get('ok'): return
    
    for msg in res.get('messages', []):
        text = msg.get('text', '')
        ts = msg.get('ts')
        reactions = [r.get('name') for r in msg.get('reactions', [])]
        
        # 개별 태그 메시지 식별 (날짜 헤더가 아닌 일반 태그 메시지)
        is_tag_report = text.startswith("#") 
        
        if is_tag_report and 'white_check_mark' in reactions and 'rocket' not in reactions:
            # 해당 메시지에만 로켓 달기 준비
            requests.post("https://slack.com/api/reactions.add", headers=headers, json={"channel": REPORT_CHANNEL_ID, "name": "speech_balloon", "timestamp": ts})
            
            # 본문 파싱 (현재 메시지의 태그와 내용만 추출)
            lines = text.strip().split('\n')
            tag = lines[0].strip() # 첫 줄이 #태그
            contents = [l.replace('• ', '').strip() for l in lines if l.startswith('• ')]
            
            if contents:
                success, result = post_to_threads(tag, contents)
                if success:
                    # 해당 리포트 메시지에 로켓 발사!
                    requests.post("https://slack.com/api/reactions.add", headers=headers, json={"channel": REPORT_CHANNEL_ID, "name": "rocket", "timestamp": ts})
                else:
                    requests.post("https://slack.com/api/reactions.add", headers=headers, json={"channel": REPORT_CHANNEL_ID, "name": "warning", "timestamp": ts})
                    error_msg = result.get('error', {}).get('message', 'Unknown Error')
                    requests.post("https://slack.com/api/chat.postMessage", headers=headers, json={"channel": REPORT_CHANNEL_ID, "text": f"❌ *발행 실패*: `{error_msg}`", "thread_ts": ts})

def send_individual_reports(tag_data, start_dt, kst_now):
    """태그별로 메시지를 쪼개서 발송합니다 (기획자님 의도 복구)"""
    headers = {"Authorization": f"Bearer {SLACK_TOKEN}"}
    
    # 1. 날짜 헤더 발송
    day_name = ['월','화','수','목','금','토','일'][kst_now.weekday()]
    header = f"📅 {kst_now.strftime('%Y-%m-%d')} ({day_name}) 리포트\n-----------------------"
    requests.post("https://slack.com/api/chat.postMessage", headers=headers, json={"channel": REPORT_CHANNEL_ID, "text": header})
    
    # 2. 태그별 개별 메시지 발송
    for tag, contents in tag_data.items():
        body = f"{tag}\n" + "\n".join([f"• {c}" for c in contents])
        requests.post("https://slack.com/api/chat.postMessage", headers=headers, json={"channel": REPORT_CHANNEL_ID, "text": body})
        time.sleep(0.5) # 슬랙 API 속도 제한 방지

if __name__ == "__main__":
    kst_now = datetime.utcnow() + timedelta(hours=9)
    
    # 1. ✅ 체크된 건들 발행 처리
    check_and_publish()
    
    # 2. 새 리포트 데이터 수집
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
            
            # 원본 메시지에 이미 ☑️가 달려있으면 중복 포함 방지
            if 'ballot_box_with_check' in reactions: continue
            
            tags = re.findall(r'#[\w가-힣]+', text)
            for t in tags:
                if t not in tag_data: tag_data[t] = []
                clean_txt = text.replace(t, "").strip()
                if clean_txt:
                    tag_data[t].append(clean_txt)
                    # 원본 데이터에 리포트 포함 완료 표식
                    requests.post("https://slack.com/api/reactions.add", headers=headers, json={"channel": SOURCE_CHANNEL_ID, "name": "ballot_box_with_check", "timestamp": ts})
        
        # 3. 수집된 데이터를 태그별 메시지로 발송
        if tag_data:
            send_individual_reports(tag_data, start_dt, kst_now)
