from django.urls import path
from .views import RasaRespondView, RasaParseView


urlpatterns = [
    path("respond/", RasaRespondView.as_view(), name="chat-respond"),
    path("parse/", RasaParseView.as_view(), name="chat-parse"),
]
