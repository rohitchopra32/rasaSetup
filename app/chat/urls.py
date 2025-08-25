from django.urls import path
from .views import RasaRespondView, RasaParseView, ChatView


urlpatterns = [
    path("", ChatView(), name="chat-home"),
    path("respond/", RasaRespondView.as_view(), name="chat-respond"),
    path("parse/", RasaParseView.as_view(), name="chat-parse"),
]

