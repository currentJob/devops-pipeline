"""
텔레그램 메시지 전송 테스트 / chat_id 1회 탐지 유틸리티.

실행 전:
- .env 에 TELEGRAM_TOKEN 설정 (또는 환경 변수로 직접 export)
- 텔레그램에서 본인 봇(@test_jik_bot)에게 /start 메시지 먼저 전송
"""

import asyncio
import os

from dotenv import load_dotenv
from telegram import Bot

load_dotenv()
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]


async def get_my_chat_id():
    """봇에게 메시지를 보낸 사람의 chat_id 출력"""
    bot = Bot(token=TELEGRAM_TOKEN)
    updates = await bot.get_updates()

    if not updates:
        print("수신된 메시지가 없습니다.")
        print("→ 텔레그램 앱에서 본인 봇(@test_jik_bot)에게 /start 를 보낸 후 다시 실행하세요.")
        return None

    for update in updates:
        if update.message:
            chat_id = update.message.chat.id
            username = update.message.chat.username
            print(f"chat_id 발견: {chat_id}  (username: @{username})")
            return chat_id

    return None


async def send_test_message(chat_id: int):
    """지정한 chat_id로 테스트 메시지 전송"""
    bot = Bot(token=TELEGRAM_TOKEN)

    await bot.send_message(
        chat_id=chat_id,
        text=(
            "✅ *텔레그램 연동 테스트 성공!*\n\n이 메시지가 보이면 자동화 알림이 정상 작동합니다."
        ),
        parse_mode="Markdown",
    )
    print(f"메시지 전송 완료 → chat_id: {chat_id}")


async def main():
    print("=== 텔레그램 테스트 시작 ===\n")

    # 1단계: chat_id 자동 탐지
    chat_id = await get_my_chat_id()
    if chat_id is None:
        return

    # 2단계: 테스트 메시지 전송
    await send_test_message(chat_id)

    print("\n.env 파일의 TELEGRAM_CHAT_ID 를 아래 값으로 업데이트하세요:")
    print(f"TELEGRAM_CHAT_ID={chat_id}")


asyncio.run(main())
