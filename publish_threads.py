# 테스트용 요약 코드 (메시지 수집 및 슬랙 발송만 확인)
import requests
import os
import re
from datetime import datetime

SLACK_TOKEN = os.environ.get('SLACK_USER_TOKEN')
MY_SLACK_ID = os.environ.get('MY_SLACK_ID')
CHANNEL_ID = os.environ.get('SLACK_CHANNEL_ID')

def test_run():
    # 오늘 쓴 메시지 중 #태그가 있는 것만 가져오는 로직 (생략)
    content = "🎨 #서비스기획자생활\n• 오늘은 스레드 봇 설정을 시작했다. 설렌다!\n\n#워킹맘생활\n• 애기 재우고 코딩하는 이 시간이 제일 꿀맛이다."
    
    url = "https://slack.com/api/chat.postMessage"
    headers = {"Authorization": f"Bearer {SLACK_TOKEN}"}
    payload = {
        "channel": MY_SLACK_ID,
        "text": f"🔔 *오늘의 스레드 발행 초안 테스트입니다.*\n\n---\n{content}"
    }
    res = requests.post(url, headers=headers, json=payload).json()
    if res.get('ok'):
        print("슬랙으로 초안 보내기 성공!")
    else:
        print(f"실패: {res.get('error')}")

if __name__ == "__main__":
    test_run()
