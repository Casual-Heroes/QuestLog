from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('gamesweplay/', views.games_we_play, name='games_we_play'),
    path('gameshype/', views.gameshype, name='gameshype'),
    path('gamesuggest/', views.gamesuggest, name='gamesuggest'),
    path('hosting/', views.hosting, name='hosting'),
    path('dragonwilds/', views.dragonwilds, name='dragonwilds'),
    path('enshrouded/', views.enshrouded, name='enshrouded'),
    path('conan/', views.conan, name='conan'),
    path('vrising/', views.vrising, name='vrising'),
    path('guides/', views.guides, name='guides'),
    path('reviews/', views.reviews, name='reviews'),
    path('content/', views.content, name='content'),
    path('aboutus/', views.aboutus, name='aboutus'),
    path('privacy/', views.privacy, name='privacy'),
    path('terms/', views.terms, name='terms'),
    path('contactus/', views.contactus, name='contactus'),
    path('faq/', views.faq, name='faq'),
]