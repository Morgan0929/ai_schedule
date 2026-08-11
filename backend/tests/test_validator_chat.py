import asyncio
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_service.graph.validator import validator_node
from agent_service.graph.graph import reply_node


class ValidatorChatTest(unittest.TestCase):
    def test_chat_intent_does_not_require_sub_tasks(self):
        result = asyncio.run(
            validator_node({
                "intent": "chat",
                "sub_tasks": [],
                "user_input": "你好",
                "_confidence": 0.85,
            })
        )

        self.assertFalse(result["needs_confirmation"])
        self.assertEqual(result["_issues"], [])
        self.assertTrue(result["_validated"])

    def test_executable_intent_still_requires_sub_tasks(self):
        result = asyncio.run(
            validator_node({
                "intent": "create_event",
                "sub_tasks": [],
                "user_input": "明天三点开会",
                "_confidence": 0.85,
            })
        )

        self.assertTrue(result["needs_confirmation"])
        self.assertEqual(result["_issues"], ["no_sub_tasks"])

    def test_greeting_gets_a_direct_chat_reply(self):
        result = asyncio.run(
            reply_node({
                "intent": "chat",
                "user_input": "你好",
                "needs_confirmation": False,
                "actions_taken": [],
                "conflicts_found": [],
                "external_data": {},
            })
        )

        self.assertEqual(result["final_reply"], "你好，我是林。")


if __name__ == "__main__":
    unittest.main()
