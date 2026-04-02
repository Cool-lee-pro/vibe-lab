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
    """스레드 API 호출: 텍스트 포스팅"""
    base_url = "https://graph.threads.net/v1.0"
    clean_tag = tag.replace("#", "")
    thread_text = f"#{clean_tag}\n" + "\n".join([f"• {c}" for c in contents])
    
    try:
        # STEP 1 로그 출력
        print(f"--- [DEBUG] Posting to Threads: {tag} ---")
        c_res = requests.post(f"{base_url}/{THREADS_USER_ID}/threads", params={
            "media_type": "TEXT", "text": thread_text, "access_token": THREADS_ACCESS_TOKEN
        }).json()
        print(f"--- [DEBUG] Container Creation Res: {c_res}") # 컨테이너 생성 결과 확인
        
        creation_id = c_res.get('id')
        if not creation_id: return False, c_res

        # STEP 2 로그 출력
        p_res = requests.post(f"{base_url}/{THREADS_USER_ID}/threads_publish", params={
            "creation_id": creation_id, "access_token": THREADS_ACCESS_TOKEN
        }).json()
        print(f"--- [DEBUG] Publish Res: {p_res}") # 실제 발행 결과 확인
        
        return ("id" in p_res), p_res
    except Exception as e:
        return False, {"error": {"message": str(e)}}

def check_and_publish():
    """✅ 승인된 리포트를 찾아 스레드 발행 및 이모지 업데이트"""
    headers = {"Authorization": f"Bearer {SLACK_TOKEN}"}
    # 최근 100개 메시지를 훑어 과거 리포트 추적
    res = requests.get(f"https://slack.com/api/conversations.history?channel={MY_SLACK_ID}&limit=100", headers=headers).json()
    
    if not res.get('ok'): return
    
    for msg in res.get('messages', []):
        text = msg.get('text', '')
        ts = msg.get('ts')
        reactions = [r.get('name') for r in msg.get('reactions', [])]
        
        # 리포트 메시지 식별 (날짜 이모지로 시작하거나 구분선이 있는 경우)
        is_report = text.startswith("📅") or "---" in text
        
        if is_report and 'white_check_mark' in reactions and 'rocket' not in reactions:
            # 1. 인지 표시 (말풍선)
            requests.post("https://slack.com/api/reactions.add", headers=headers, 
                          json={"channel": MY_SLACK_ID, "name": "speech_balloon", "timestamp": ts})
            
            # 2. 리포트 본문 파싱 (#태그 단위로 분리)
            sections = text.split('#')[1:]
            for section in sections:
                lines = section.strip().split('\n')
                tag = "#" + lines[0].strip()
                contents = [l.replace('• ', '').replace('>• ', '').strip() for l in lines if '• ' in l]
                
                if contents:
                    success, result = post_to_threads(tag, contents)
                    if success:
                        # 성공 시 로켓 발사
                        requests.post("https://slack.com/api/reactions.add", headers=headers, 
                                      json={"channel": MY_SLACK_ID, "name": "rocket", "timestamp": ts})
                    else:
                        # 실패 시 경고 및 에러 답글
                        requests.post("https://slack.com/api/reactions.add", headers=headers, 
                                      json={"channel": MY_SLACK_ID, "name": "warning", "timestamp": ts})
                        error_msg = result.get('error', {}).get('message', 'Unknown Error')
                        requests.post("https://slack.com/api/chat.postMessage", headers=headers, 
                                      json={"channel": MY_SLACK_ID, "text": f"❌ *발행 실패*: `{error_msg}`", "thread_ts": ts})

def send_combined_report(tag_data, start_dt, kst_now):
    """통합 리포트 발송"""
    headers = {"Authorization": f"Bearer {SLACK_TOKEN}"}
    kst_start = start_dt + timedelta(hours=9)
    day_name = ['월','화','수','목','금','토','일'][kst_now.weekday()]
    
    header = f"📅 {kst_now.strftime('%Y-%m-%d')} ({day_name})\n-----------------------"
    requests.post("https://slack.com/api/chat.postMessage", headers=headers, json={"channel": MY_SLACK_ID, "text": header})
    
    for tag, contents in tag_data.items():
        body = f"{tag}\n" + "\n".join([f"• {c}" for c in contents])
        requests.post("https://slack.com/api/chat.postMessage", headers=headers, json={"channel": MY_SLACK_ID, "text": body})
        time.sleep(0.5)

    footer = f"-----------------------\n🕒 {kst_start.strftime('%m-%d %H:%M')} ~ {kst_now.strftime('%m-%d %H:%M')}"
    requests.post("https://slack.com/api/chat.postMessage", headers=headers, json={"channel": MY_SLACK_ID, "text": footer})

if __name__ == "__main__":
    kst_now = datetime.utcnow() + timedelta(hours=9)
    current_time_val = int(kst_now.strftime('%H%M'))
    
    # 1. 먼저 과거 리포트 중 ✅ 체크된 건이 있는지 확인하고 처리
    check_and_publish()
    
    # 2. 새 리포트를 위한 데이터 수집 (최근 24시간 범위)
    start_dt = datetime.utcnow() - timedelta(hours=24)
    url = f"https://slack.com/api/conversations.history?channel={CHANNEL_ID}&oldest={start_dt.timestamp()}"
    headers = {"Authorization": f"Bearer {SLACK_TOKEN}"}
    slack_res = requests.get(url, headers=headers).json()
    
    if slack_res.get('ok'):
        tag_data = {}
        for msg in reversed(slack_res.get('messages', [])):
            text = msg.get('text', '')
            ts = msg.get('ts')
            reactions = [r.get('name') for r in msg.get('reactions', [])]
            
            # [핵심] 이미 발행(rocket)이나 경고(warning)가 달린 원본 메시지는 리포트에서 제외
            if 'rocket' in reactions or 'warning' in reactions:
                continue
                
            tags = re.findall(r'#[\w가-힣]+', text)
            for t in tags:
                if t not in tag_data: tag_data[t] = []
                clean_txt = text.replace(t, "").strip()
                if clean_txt:
                    tag_data[t].append(clean_txt)
                    # 리포트에 포함되었다는 표시로 원본에 로켓을 달아 중복 방지
                    requests.post("https://slack.com/api/reactions.add", headers=headers, 
                                  json={"channel": CHANNEL_ID, "name": "rocket", "timestamp": ts})
        
        # 3. 새로운 내용이 있을 때만 리포트 전송
        if tag_data:
            send_combined_report(tag_data, start_dt, kst_now)
