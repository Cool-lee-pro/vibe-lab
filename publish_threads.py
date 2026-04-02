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
        # 1. 미디어 컨테이너 생성
        c_res = requests.post(f"{base_url}/{THREADS_USER_ID}/threads", params={
            "media_type": "TEXT", "text": thread_text, "access_token": THREADS_ACCESS_TOKEN
        }).json()
        
        creation_id = c_res.get('id')
        if not creation_id: 
            return False, c_res # 실패 시 결과값 반환
            
        # 2. 미디어 발행
        p_res = requests.post(f"{base_url}/{THREADS_USER_ID}/threads_publish", params={
            "creation_id": creation_id, "access_token": THREADS_ACCESS_TOKEN
        }).json()
        
        return ("id" in p_res), p_res
    except Exception as e:
        return False, {"error": {"message": str(e)}}

def check_and_publish():
    """✅ 승인된 리포트 메시지를 찾아 발행하고, 실패 시 에러 메시지 전송"""
    headers = {"Authorization": f"Bearer {SLACK_TOKEN}"}
    res = requests.get(f"https://slack.com/api/conversations.history?channel={REPORT_CHANNEL_ID}&limit=50", headers=headers).json()
    if not res.get('ok'): return
    
    for msg in res.get('messages', []):
        text = msg.get('text', '')
        ts = msg.get('ts')
        reactions = [r.get('name') for r in msg.get('reactions', [])]
        
        # ✅가 있고 🚀가 없는 태그 메시지 대상
        if text.startswith("#") and 'white_check_mark' in reactions and 'rocket' not in reactions:
            # 작업 중 표시 (💬)
            requests.post("https://slack.com/api/reactions.add", headers=headers, json={"channel": REPORT_CHANNEL_ID, "name": "speech_balloon", "timestamp": ts})
            
            lines = text.strip().split('\n')
            tag = lines[0].strip()
            # 구분선(----) 이전의 내용만 추출 (순수 본문)
            contents = [l.replace('• ', '').strip() for l in lines if l.startswith('• ')]
            
            if contents:
                success, result = post_to_threads(tag, contents)
                
                if success:
                    # 성공 시 로켓(🚀)
                    requests.post("https://slack.com/api/reactions.add", headers=headers, json={"channel": REPORT_CHANNEL_ID, "name": "rocket", "timestamp": ts})
                else:
                    # 실패 시 경고(⚠️) 및 에러 메시지 댓글 작성
                    requests.post("https://slack.com/api/reactions.add", headers=headers, json={"channel": REPORT_CHANNEL_ID, "name": "warning", "timestamp": ts})
                    
                    # [복구된 로직] 에러 원인 파악 및 슬랙 전송
                    error_info = result.get('error', {})
                    error_msg = error_info.get('message', '알 수 없는 오류가 발생했습니다.')
                    error_code = error_info.get('code', 'N/A')
                    
                    full_error_text = f"❌ *발행 실패 알림*\n> *사유*: `{error_msg}`\n> *코드*: `{error_code}`"
                    
                    requests.post("https://slack.com/api/chat.postMessage", headers=headers, json={
                        "channel": REPORT_CHANNEL_ID, 
                        "text": full_error_text,
                        "thread_ts": ts  # 해당 리포트 메시지의 댓글로 달기
                    })

def send_individual_reports(tag_data, kst_start, kst_now):
    """구분선과 시간 범위가 포함된 리포트 발송"""
    headers = {"Authorization": f"Bearer {SLACK_TOKEN}"}
    day_name = ['월','화','수','목','금','토','일'][kst_now.weekday()]
    
    header = f"📅 {kst_now.strftime('%Y-%m-%d')} ({day_name}) 리포트 \n-----------------------\n"
    requests.post("https://slack.com/api/chat.postMessage", headers=headers, json={"channel": REPORT_CHANNEL_ID, "text": header})
    
    for tag, contents in tag_data.items():
        body = f"`{tag}`\n" + "\n".join([f"• {c}" for c in contents])
        footer = f"\n-----------------------\n🕒 {kst_start.strftime('%m/%d %H:%M')} ~ {kst_now.strftime('%m/%d %H:%M')}"
        full_msg = body + footer
        
        requests.post("https://slack.com/api/chat.postMessage", headers=headers, json={"channel": REPORT_CHANNEL_ID, "text": full_msg})
        time.sleep(0.5)

if __name__ == "__main__":
    kst_now = datetime.utcnow() + timedelta(hours=9)
    current_hour = kst_now.hour
    
    # 1. 승인 건 발행 로직 실행
    check_and_publish()
    
    # 2. 시간 범위 설정
    if current_hour < 12:
        kst_start = (kst_now - timedelta(days=1)).replace(hour=16, minute=0, second=0, microsecond=0)
    else:
        kst_start = kst_now.replace(hour=7, minute=30, second=0, microsecond=0)
    
    utc_start_ts = (kst_start - timedelta(hours=9)).timestamp()
    
    # 3. 새로운 로그 수집 및 리포트 발송
    url = f"https://slack.com/api/conversations.history?channel={SOURCE_CHANNEL_ID}&oldest={utc_start_ts}"
    headers = {"Authorization": f"Bearer {SLACK_TOKEN}"}
    slack_res = requests.get(url, headers=headers).json()
    
    if slack_res.get('ok'):
        tag_data = {}
        for msg in reversed(slack_res.get('messages', [])):
            text = msg.get('text', '')
            ts = msg.get('ts')
            reactions = [r.get('name') for r in msg.get('reactions', [])]
            
            if 'ballot_box_with_check' in reactions: continue
            
            tags = re.findall(r'#[\w가-힣]+', text)
            for t in tags:
                if t not in tag_data: tag_data[t] = []
                clean_txt = text.replace(t, "").strip()
                if clean_txt:
                    tag_data[t].append(clean_txt)
                    requests.post("https://slack.com/api/reactions.add", headers=headers, json={"channel": SOURCE_CHANNEL_ID, "name": "ballot_box_with_check", "timestamp": ts})
        
        if tag_data:
            send_individual_reports(tag_data, kst_start, kst_now)
