from __future__ import annotations

import traceback
from typing import Any, Dict, List, Text
import os
import json
import urllib.request
import urllib.error

from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher


class ActionLLMFallback(Action):
    """Fallback action that queries an LLM for a helpful response when NLU confidence is low."""

    def name(self) -> Text:
        return "action_llm_fallback"

    def _call_openai_chat(self, user_text: str) -> Dict[str, Any]:
        """Call OpenAI Chat Completions API.
        Returns a dict with keys: reply (str), label (str|None), examples (list[str]|None).
        """
        api_key = os.getenv("OPENAI_API_KEY", None).strip()
        if not api_key:
            raise RuntimeError("Missing OPENAI_API_KEY")

        # Allow model override via env; choose a fast, inexpensive default
        model = os.getenv("LLM_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
        url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1/chat/completions")

        payload: Dict[str, Any] = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        """
                            You are representing KSlegal, tasked with contacting a non-responsive borrower regarding 
                            their overdue loan. The loan has been delinquent for 36, and despite multiple attempts at 
                            communication, including sending 1, there has been no response from the borrower. Your 
                            conversation should be firm, direct, and unambiguous, stressing the seriousness of the 
                            situation and the legal ramifications of continued non-response. 
                            Do not use phrases like 'thank you', 'sorry', or 'regards', and ensure the tone is 
                            professional and strictly to the point. Don't reply in more than 3 sentences. 
                            Don't want very long replies. Keep it short & concise. 
                            Your objectives are:
                            1. To emphasize that ongoing avoidance of communication is viewed as a deliberate tactic to 
                            evade repayment, indicating fraudulent intentions.
                            2. To warn that further non-response will lead to contacting the references provided by the 
                            borrower at the time of loan issuance.
                            3. To state that such behaviour could lead to legal proceedings, including potential charges
                             of fraud or deception.
                            4. To clearly articulate that this is the final opportunity for the borrower to settle their
                             debt out of court, and failure to do so will result in immediate legal action.
                            5. To remind them of the increasing financial burden due to accruing interest, additional
                             penalties, and the deteriorating impact on their credit score.
                            6. To advise the borrower to appoint a legal representative to respond to the notices and to 
                            communicate any steps taken in this regard.
                            7. To request an immediate response within 24 hours, either through direct payment of the 
                            outstanding amount or initiating a dialogue to discuss payment terms.
                            8. To underline the importance of immediate action to avoid further legal complications and 
                            financial distress.
                            9. Ensure that your responses are dynamic and human-like. Avoid repeating the same 
                            information or copying previous messages. Each response should be tailored to the 
                            borrower's replies, demonstrating active listening and understanding. Keep the conversation 
                            engaging, relevant, and adaptive to the flow of the dialogue. The goal is to provide a 
                            natural, conversational experience that effectively addresses the borrower's situation and 
                            concerns, while also fulfilling the objectives outlined in the prompt. 
                            Don’t say thank you and sorry or regards in the entire conversation. 
                            10. Keep pushing for replies if there is no response from the borrowers. Send some messages 
                            and ask them to reply.
                            11. Dont mention ever you are an AI 
                            12. Dont put a time stamp or let the borrower ever know its automated response.
                            13. Make it look like human response and keep it conversational
                            14. Convey the critical nature of the situation, highlighting the legal and financial 
                            consequences of non-action, and urging immediate resolution either through full payment or 
                            opening a dialogue to discuss feasible repayment options.
                            15. Additional Instruction for Dynamic Interaction: Ensure that your responses are tailored 
                            to the specific context of each borrower's situation. Avoid repetition and maintain a fluid,
                            engaging conversation that shows understanding of the dialogue's context. Adapt your 
                            responses to be natural and human-like, focusing on achieving the conversation's objectives
                            without deviating from the main topic. Don't add thank you, regards, sorry etc in the 
                            conversation.
                            When asked, return JSON with fields: reply (assistant answer), label (suggested intent label
                            in snake_case using short words, or null), examples (3-6 short user utterance variants, or 
                            empty array).
                        """
                    ),
                },
                {"role": "user", "content": user_text},
            ],
            "temperature": 0.3,
            "response_format": {"type": "json_object"},
        }

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                body = resp.read().decode("utf-8")
                parsed = json.loads(body)
                content = (
                    parsed.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "{}")
                )
                try:
                    obj = json.loads(content)
                except Exception:
                    obj = {"reply": content, "label": None, "examples": []}
                # Normalize
                reply = (obj.get("reply") or "").strip()
                label = obj.get("label")
                examples = obj.get("examples") or []
                if not isinstance(examples, list):
                    examples = []
                return {"reply": reply, "label": label, "examples": examples}
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
            raise RuntimeError(f"LLM call failed: {e}")

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        user_message = (tracker.latest_message.get("text") or "").strip()

        try:
            result = self._call_openai_chat(user_message)
            answer = (result.get("reply") or "").strip()
            if not answer:
                raise RuntimeError("Empty response from LLM")
            dispatcher.utter_message(text=answer)

            # Persist suggestion for training (human review later)
            if os.getenv("SAVE_FALLBACKS", "1") == "1":
                record = {
                    "text": user_message,
                    "suggested_intent": result.get("label"),
                    "suggested_examples": result.get("examples") or [],
                    "llm_reply": answer,
                }
                # Write to shared volume if available
                inbox_path = os.getenv(
                    "FALLBACK_INBOX_PATH", "/rasa_project/data/fallback_inbox.jsonl"
                )
                try:
                    os.makedirs(os.path.dirname(inbox_path), exist_ok=True)
                    with open(inbox_path, "a", encoding="utf-8") as f:
                        f.write(json.dumps(record, ensure_ascii=False) + "\n")
                except Exception:
                    traceback.print_exc()
        except Exception:
            traceback.print_exc()
        return []

