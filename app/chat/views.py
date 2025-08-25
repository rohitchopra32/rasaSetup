from __future__ import annotations

import os
from typing import Any, Dict

import httpx
from django.conf import settings
from django.shortcuts import render
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView


RASA_URL = getattr(settings, "RASA_URL", os.getenv("RASA_URL", "http://rasa:5005"))


class ChatView:
    def __init__(self):
        pass
    
    def __call__(self, request):
        return render(request, 'chat/index.html')


class RasaRespondView(APIView):
    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        payload: Dict[str, Any] = request.data or {}
        sender_id: str = payload.get("sender", "anonymous")
        message: str = payload.get("message", "")
        if not message:
            return Response({"detail": "message is required"}, status=status.HTTP_400_BAD_REQUEST)

        # POST /webhooks/rest/webhook
        url = f"{RASA_URL}/webhooks/rest/webhook"
        body = {"sender": sender_id, "message": message}
        try:
            with httpx.Client(timeout=15.0) as client:
                r = client.post(url, json=body)
                r.raise_for_status()
        except httpx.HTTPError as e:
            return Response({"detail": f"Rasa error: {e}"}, status=status.HTTP_502_BAD_GATEWAY)

        # Rasa returns a list of messages
        replies = r.json()
        return Response({"replies": replies})


class RasaParseView(APIView):
    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        payload: Dict[str, Any] = request.data or {}
        text: str = payload.get("text", "")
        if not text:
            return Response({"detail": "text is required"}, status=status.HTTP_400_BAD_REQUEST)

        # POST /model/parse
        url = f"{RASA_URL}/model/parse"
        try:
            with httpx.Client(timeout=15.0) as client:
                r = client.post(url, json={"text": text})
                r.raise_for_status()
        except httpx.HTTPError as e:
            return Response({"detail": f"Rasa error: {e}"}, status=status.HTTP_502_BAD_GATEWAY)

        return Response(r.json())

