from django.urls import path
from . import views

urlpatterns = [
    path("gamesweplay/", views.gamesweplay, name="gamesweplay"),
]
