import os
import sys
import json
import asyncio

# Mock environment variables before importing webhook
os.environ["TELE_BOT_DHIKSDHIKY"] = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
os.environ["TELE_CHAT_ID_DHIKA"] = "123456789"
os.environ["TEST_MODE"] = "true"

sys.path.append(os.path.join(os.path.dirname(__file__), "api"))
import webhook

async def test_update():
    from telegram import Update
    # Mock an update for /info
    update_data = {
        "update_id": 123456789,
        "message": {
            "message_id": 1,
            "from": {
                "id": int(os.getenv("TELE_CHAT_ID_DHIKA", 0)),
                "is_bot": False,
                "first_name": "Test",
                "username": "testuser"
            },
            "chat": {
                "id": int(os.getenv("TELE_CHAT_ID_DHIKA", 0)),
                "first_name": "Test",
                "username": "testuser",
                "type": "private"
            },
            "date": 1690000000,
            "text": "/info",
            "entities": [
                {
                    "offset": 0,
                    "length": 5,
                    "type": "bot_command"
                }
            ]
        }
    }
    
    print("Testing webhook...")
    try:
        update = Update.de_json(update_data, webhook.app.bot)
        await webhook.app.initialize()
        await webhook.app.start()
        print("Processing update...")
        await webhook.app.process_update(update)
        # Give it a second to process
        await asyncio.sleep(2)
        print("Stopping app...")
        await webhook.app.stop()
        await webhook.app.shutdown()
        print("Done.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_update())
