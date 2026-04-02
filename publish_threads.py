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
    clean_tag = tag.replace("#", "").replace("`", "") # 백틱 제거
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
    """✅ 승인된 '태그 메시지'만 골라서 발행"""
    headers = {"Authorization": f"Bearer {SLACK_TOKEN}"}
    res = requests.get(f"https://slack.com/api/conversations.history?channel={REPORT_CHANNEL_ID}&limit=50", headers=headers).json()
    if not res.get('ok'): return
    
    for msg in res.get('messages', []):
        text = msg.get('text', '')
        ts = msg.get('ts')
        reactions = [r.get('name') for r in msg.get('reactions', [])]
        
        # 태그(#)로 시작하는 메시지에 ✅가 달렸을 때만 실행
        if (text.startswith("#") or text.startswith("`#")) and 'white_check_mark' in reactions and 'rocket' not in reactions:
            requests.post("https://slack.com/api/reactions.add", headers=headers, json={"channel": REPORT_CHANNEL_ID, "name": "speech_balloon", "timestamp": ts})
            
            lines = text.strip().split('\n')
            # `#태그` 또는 `#태그` 추출
            tag = lines[0].strip().replace("`", "")
            contents = [l.replace('• ', '').strip() for l in lines if l.startswith('• ')]
            
            if contents:
                success, result = post_to_threads(tag, contents)
                if success:
                    requests.post("https://slack.com/api/reactions.add", headers=headers, json={"channel": REPORT_CHANNEL_ID, "name": "rocket", "timestamp": ts})
                else:
                    requests.post("https://slack.com/api/reactions.add", headers=headers, json={"channel": REPORT_CHANNEL_ID, "name": "warning", "timestamp": ts})
                    error_info = result.get('error', {})
                    requests.post("https://slack.com/api/chat.postMessage", headers=headers, json={
                        "channel": REPORT_CHANNEL_ID, "text": f"❌ *발행 실패*: `{error_info.get('message')}`", "thread_ts": ts
                    })

def send_individual_reports(tag_data, kst_start, kst_now):
    """헤더, 태그 메시지, 푸터를 각각 분리해서 발송"""
    headers = {"Authorization": f"Bearer {SLACK_TOKEN}"}
    day_name = ['월','화','수','목','금','토','일'][kst_now.weekday()]
    
    # 1. 헤더 (리포트 시작 알림)
    header_text = f"📅 *{kst_now.strftime('%Y-%m-%d')} ({day_name}) 리포트 생성* 🚀\n"
    requests.post("https://slack.com/api/chat.postMessage", headers=headers, json={"channel": REPORT_CHANNEL_ID, "text": header_text})
    
    # 2. 태그별 개별 메시지 (이 메시지들에 ✅를 다는 겁니다)
    for tag, contents in tag_data.items():
        # 가독성을 위해 태그에 백틱(`)을 감싸서 발송
        body = f"`{tag}`\n" + "\n".join([f"• {c}" for c in contents])
        requests.post("https://slack.com/api/chat.postMessage", headers=headers, json={"channel": REPORT_CHANNEL_ID, "text": body})
        time.sleep(0.5)

    # 3. 푸터 (시간 범위 안내)
    footer_text = (
        f"-----------------------\n"
        f"🕒 *수집 범위:* {kst_start.strftime('%m/%d %H:%M')} ~ {kst_now.strftime('%m/%d %H:%M')}\n"
        f"✅ 발행을 원하는 태그 메시지에 체크 이모지를 달아주세요!"
    )
    requests.post("https://slack.com/api/chat.postMessage", headers=headers, json={"channel": REPORT_CHANNEL_ID, "text": footer_text})

if __name__ == "__main__":
    kst_now = datetime.utcnow() + timedelta(hours=9)
    current_hour = kst_now.hour
    
    # 먼저 승인된 건들 발행 처리
    check_and_publish()
    
    # 시간 범위 설정
    if current_hour < 12:
        kst_start = (kst_now - timedelta(days=1)).replace(hour=16, minute=0, second=0, microsecond=0)
    else:
        kst_start = kst_now.replace(hour=7, minute=30, second=0, microsecond=0)
    
    utc_start_ts = (kst_start - timedelta(hours=9)).timestamp()
    
    # 로그 수집 및 리포트 발송
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
