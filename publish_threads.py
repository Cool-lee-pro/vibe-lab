import requests
import os
import re
import time
from datetime import datetime, timedelta

# 환경 변수 설정
SLACK_TOKEN = os.environ.get('SLACK_USER_TOKEN')
SOURCE_CHANNEL_ID = os.environ.get('SLACK_CHANNEL_ID')
REPORT_CHANNEL_ID = os.environ.get('REPORT_CHANNEL_ID')
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
    """✅ 승인된 리포트 메시지를 찾아 스레드에 발행"""
    headers = {"Authorization": f"Bearer {SLACK_TOKEN}"}
    res = requests.get(f"https://slack.com/api/conversations.history?channel={REPORT_CHANNEL_ID}&limit=50", headers=headers).json()
    if not res.get('ok'): return
    
    for msg in res.get('messages', []):
        text = msg.get('text', '')
        ts = msg.get('ts')
        reactions = [r.get('name') for r in msg.get('reactions', [])]
        
        # 태그(#)로 시작하고 체크(✅)가 있지만 로켓(🚀)은 없는 메시지 대상
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

def send_individual_reports(tag_data, kst_start, kst_now):
    """요청하신 구분선(----)과 시간 범위가 포함된 리포트 발송"""
    headers = {"Authorization": f"Bearer {SLACK_TOKEN}"}
    day_name = ['월','화','수','목','금','토','일'][kst_now.weekday()]
    
    # 1. 상단 헤더 발송
    header = f"📅 {kst_now.strftime('%Y-%m-%d')} ({day_name}) 리포트 시작"
    requests.post("https://slack.com/api/chat.postMessage", headers=headers, json={"channel": REPORT_CHANNEL_ID, "text": header})
    
    # 2. 태그별 본문 발송
    for tag, contents in tag_data.items():
        body = f"{tag}\n" + "\n".join([f"• {c}" for c in contents])
        # 푸터 추가: 구분선과 시간 범위
        footer = f"\n-----------------------\n🕒 {kst_start.strftime('%m/%d %H:%M')} ~ {kst_now.strftime('%m/%d %H:%M')}"
        full_msg = body + footer
        
        requests.post("https://slack.com/api/chat.postMessage", headers=headers, json={"channel": REPORT_CHANNEL_ID, "text": full_msg})
        time.sleep(0.5)

if __name__ == "__main__":
    # 한국 시간(KST) 기준 설정
    kst_now = datetime.utcnow() + timedelta(hours=9)
    current_hour = kst_now.hour
    
    # 1. ✅ 승인 건 먼저 처리
    check_and_publish()
    
    # 2. 시간 범위(start_dt) 계산
    if current_hour < 12: # 오전 세션 (07:30 실행 등)
        # 어제 오후 4시 ~ 현재
        kst_start = (kst_now - timedelta(days=1)).replace(hour=16, minute=0, second=0, microsecond=0)
    else: # 오후 세션 (16:05 실행 등)
        # 오늘 오전 7시 30분 ~ 현재
        kst_start = kst_now.replace(hour=7, minute=30, second=0, microsecond=0)
    
    # UTC 기준 검색을 위한 변환
    utc_start_ts = (kst_start - timedelta(hours=9)).timestamp()
    
    # 3. 데이터 수집
    url = f"https://slack.com/api/conversations.history?channel={SOURCE_CHANNEL_ID}&oldest={utc_start_ts}"
    headers = {"Authorization": f"Bearer {SLACK_TOKEN}"}
    slack_res = requests.get(url, headers=headers).json()
    
    if slack_res.get('ok'):
        tag_data = {}
        for msg in reversed(slack_res.get('messages', [])):
            text = msg.get('text', '')
            ts = msg.get('ts')
            reactions = [r.get('name') for r in msg.get('reactions', [])]
            
            # 리포트 중복 방지 (이미 처리된 원본 제외)
            if 'ballot_box_with_check' in reactions: continue
            
            tags = re.findall(r'#[\w가-힣]+', text)
            for t in tags:
                if t not in tag_data: tag_data[t] = []
                # 태그를 제외한 순수 본문 추출
                clean_txt = text.replace(t, "").strip()
                if clean_txt:
                    tag_data[t].append(clean_txt)
                    # 원본에 체크 표시
                    requests.post("https://slack.com/api/reactions.add", headers=headers, json={"channel": SOURCE_CHANNEL_ID, "name": "ballot_box_with_check", "timestamp": ts})
        
        # 4. 리포트 전송 (푸터 포함)
        if tag_data:
            send_individual_reports(tag_data, kst_start, kst_now)
