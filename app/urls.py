from django.urls import path, include
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('gamesweplay/', views.games_we_play, name='games_we_play'),
    path('gameshype/', views.gameshype, name='gameshype'),
    path('gamesuggest/', views.gamesuggest, name='gamesuggest'),
    path('hosting/', views.hosting, name='hosting'),
    path('7dtd/', views.sevendtd, name='7dtd'),
    path('dragonwilds/', views.dragonwilds, name='dragonwilds'),
    path('dune/', views.dune_page, name='dune'),
    path('pantheon/', views.pantheon_page, name='pantheon'),
    path('wow/', views.wow_page, name='wow'),
    path('enshrouded/', views.enshrouded, name='enshrouded'),
    path('conan/', views.conan, name='conan'),
    path('vrising/', views.vrising, name='vrising'),
    path('features/', views.features, name='features'),
    path('features/<slug:slug>/', views.features_detail, name='features_detail'),
    path('guides/', views.guides, name='guides'),
    path('content/', views.content, name='content'),
    path('aboutus/', views.aboutus, name='aboutus'),
    path('privacy/', views.privacy, name='privacy'),
    path('terms/', views.terms, name='terms'),
    path('contactus/', views.contactus, name='contactus'),
    path('faq/', views.faq, name='faq'),
    path('login/', views.login_view, name='login'),
    path("dashboard/", views.dashboard, name="dashboard")
]
