from __future__ import annotations

from typing import Any, Dict, List, Text

from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher


PREDEFINED_RESPONSES: Dict[str, str] = {
    "reset password": "To reset your password, go to Settings > Security > Reset Password and follow the steps sent to your email.",
    "forgot password": "Click 'Forgot Password' on the sign-in page and check your inbox for the reset link.",
}


class ActionPredefinedRouter(Action):
    def name(self) -> Text:
        return "action_predefined_router"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        user_message = (tracker.latest_message.get("text") or "").strip().lower()

        for key, response_text in PREDEFINED_RESPONSES.items():
            if key in user_message:
                dispatcher.utter_message(text=response_text)
                return []

        dispatcher.utter_message(text="Here is the predefined answer for your request.")
        return []
