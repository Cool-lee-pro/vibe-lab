import requests
import os
import re
import time
from datetime import datetime, timedelta

# 1. 환경 변수 설정 (GitHub Secrets)
SLACK_TOKEN = os.environ.get('SLACK_USER_TOKEN')
MY_SLACK_ID = os.environ.get('MY_SLACK_ID')
CHANNEL_ID = os.environ.get('SLACK_CHANNEL_ID')
THREADS_USER_ID = os.environ.get('THREADS_USER_ID')
THREADS_ACCESS_TOKEN = os.environ.get('THREADS_ACCESS_TOKEN')

def post_to_threads(tag, contents):
    """스레드 API 호출 (텍스트 전용)"""
    base_url = "https://graph.threads.net/v1.0"
    clean_tag = tag.replace("#", "")
    # 스레드 게시글 포맷: #태그명 + 불렛 포인트들
    thread_text = f"#{clean_tag}\n" + "\n".join([f"• {c}" for c in contents])
    
    try:
        # STEP 1: 미디어 컨테이너 생성
        c_res = requests.post(f"{base_url}/{THREADS_USER_ID}/threads", params={
            "media_type": "TEXT", "text": thread_text, "access_token": THREADS_ACCESS_TOKEN
        }).json()
        
        creation_id = c_res.get('id')
        if not creation_id: return False, c_res

        # STEP 2: 실제 게시 (Publish)
        p_res = requests.post(f"{base_url}/{THREADS_USER_ID}/threads_publish", params={
            "creation_id": creation_id, "access_token": THREADS_ACCESS_TOKEN
        }).json()
        
        return ("id" in p_res), p_res
    except Exception as e:
        return False, {"error": {"message": str(e)}}

def check_and_publish():
    """슬랙 DM에서 ✅ 승인된 건을 찾아 처리 (성공: 🚀, 실패: ⚠️ + 에러메시지)"""
    headers = {"Authorization": f"Bearer {SLACK_TOKEN}"}
    res = requests.get(f"https://slack.com/api/conversations.history?channel={MY_SLACK_ID}&limit=20", headers=headers).json()
    
    if not res.get('ok'): return
    
    for msg in res.get('messages', []):
        text = msg.get('text', '')
        ts = msg.get('ts')
        reactions = [r.get('name') for r in msg.get('reactions', [])]
        
        # 조건: ✅가 있고, 🚀(성공)와 ⚠️(실패)가 둘 다 없는 경우만 실행
        if 'white_check_mark' in reactions and 'rocket' not in reactions and 'warning' not in reactions:
            # 1. 인지 표시 (말풍선 추가)
            requests.post("https://slack.com/api/reactions.add", headers=headers, 
                          json={"channel": MY_SLACK_ID, "name": "speech_balloon", "timestamp": ts})
            
            # 2. 태그 및 본문 파싱
            tag_match = re.search(r'#([\w가-힣]+)', text)
            if tag_match:
                tag = tag_match.group(0)
                # '• ' 또는 '>• ' 패턴 뒤의 텍스트만 추출
                contents = [l.split('• ')[1].strip() for l in text.split('\n') if '• ' in l]
                
                # 3. 스레드 발행 시도
                success, result = post_to_threads(tag, contents)
                
                if success:
                    # ✅ 성공: 🚀 추가
                    requests.post("https://slack.com/api/reactions.add", headers=headers, 
                                  json={"channel": MY_SLACK_ID, "name": "rocket", "timestamp": ts})
                else:
                    # ❌ 실패: ⚠️ 추가 및 스레드 답글로 에러 로그 남기기
                    requests.post("https://slack.com/api/reactions.add", headers=headers, 
                                  json={"channel": MY_SLACK_ID, "name": "warning", "timestamp": ts})
                    
                    error_msg = result.get('error', {}).get('message', 'Unknown Error')
                    error_detail = f"❌ *Threads 발행 실패*\n원인: `{error_msg}`"
                    requests.post("https://slack.com/api/chat.postMessage", headers=headers, 
                                  json={"channel": MY_SLACK_ID, "text": error_detail, "thread_ts": ts})

def send_combined_report(tag_data, start_dt, kst_now):
    """기획자님 커스텀 UI 리포트 전송"""
    headers = {"Authorization": f"Bearer {SLACK_TOKEN}"}
    kst_start = start_dt + timedelta(hours=9)
    day_name = ['월','화','수','목','금','토','일'][kst_now.weekday()]
    
    # 상단 날짜 및 구분선
    header = f"📅 {kst_now.strftime('%Y-%m-%d')} ({day_name})\n-----------------------"
    requests.post("https://slack.com/api/chat.postMessage", headers=headers, json={"channel": MY_SLACK_ID, "text": header})
    
    # 태그별 본문 전송
    for tag, contents in tag_data.items():
        body = f"{tag}\n" + "\n".join([f">• {c}" for c in contents])
        requests.post("https://slack.com/api/chat.postMessage", headers=headers, json={"channel": MY_SLACK_ID, "text": body})
        time.sleep(0.5)

    # 하단 시간 로그 및 구분선
    footer = f"-----------------------\n🕒 {kst_start.strftime('%m-%d %H:%M')} ~ {kst_now.strftime('%m-%d %H:%M')}"
    requests.post("https://slack.com/api/chat.postMessage", headers=headers, json={"channel": MY_SLACK_ID, "text": footer})

if __name__ == "__main__":
    # 시간 설정 (KST 기준)
    kst_now = datetime.utcnow() + timedelta(hours=9)
    current_time_val = int(kst_now.strftime('%H%M'))
    
    # 오전 07:30 실행 시 약 15시간 전부터 / 오후 16:05 실행 시 약 8시간 전부터 수집
    if current_time_val < 1200:
        start_dt = datetime.utcnow() - timedelta(hours=15, minutes=30)
    else:
        start_dt = datetime.utcnow() - timedelta(hours=8, minutes=40)
    
    # 1. 승인된 건 발행 처리 (이모지 피드백 포함)
    check_and_publish()
    
    # 2. 새로운 기록 수집 및 슬랙 리포트 발송
    url = f"https://slack.com/api/conversations.history?channel={CHANNEL_ID}&oldest={start_dt.timestamp()}"
    headers = {"Authorization": f"Bearer {SLACK_TOKEN}"}
    slack_res = requests.get(url, headers=headers).json()
    
    if slack_res.get('ok'):
        tag_data = {}
        # 최신순 -> 과거순이므로 뒤집어서 처리
        for msg in reversed(slack_res.get('messages', [])):
            text = msg.get('text', '')
            tags = re.findall(r'#[\w가-힣]+', text)
            for t in tags:
                if t not in tag_data: tag_data[t] = []
                # 태그 제외한 본문만 정제
                clean_txt = text.replace(t, "").strip()
                if clean_txt: tag_data[t].append(clean_txt)
        
        if tag_data:
            send_combined_report(tag_data, start_dt, kst_now)
