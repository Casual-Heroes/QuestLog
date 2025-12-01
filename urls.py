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
    # path('wow/', views.wow_page, name='wow'),
    # path('enshrouded/', views.enshrouded, name='enshrouded'),
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
    path("dashboard/", views.dashboard, name="dashboard"),

    # Discord OAuth2 Authentication
    path('auth/discord/login/', views.discord_login, name='discord_login'),
    path('auth/discord/callback/', views.discord_callback, name='discord_callback'),
    path('auth/discord/logout/', views.discord_logout, name='discord_logout'),

    # User Pages
    path('profile/', views.user_profile, name='user_profile'),

    # Warden Bot Dashboard
    path('warden/', views.warden_dashboard, name='warden_dashboard'),
    path('warden/guild/<str:guild_id>/', views.guild_dashboard, name='guild_dashboard'),
    path('warden/guild/<str:guild_id>/trackers/', views.guild_trackers, name='guild_trackers'),

    # Warden API (REST endpoints for dashboard AJAX)
    path('api/guild/<str:guild_id>/trackers/', views.api_trackers_list, name='api_trackers_list'),
    path('api/guild/<str:guild_id>/trackers/create/', views.api_tracker_create, name='api_tracker_create'),
    path('api/guild/<str:guild_id>/trackers/<int:tracker_id>/', views.api_tracker_update, name='api_tracker_update'),
    path('api/guild/<str:guild_id>/trackers/<int:tracker_id>/delete/', views.api_tracker_delete, name='api_tracker_delete'),

    # XP Dashboard
    path('warden/guild/<str:guild_id>/xp/', views.guild_xp, name='guild_xp'),

    # XP API Endpoints
    path('api/guild/<str:guild_id>/xp/config/', views.api_xp_config, name='api_xp_config'),
    path('api/guild/<str:guild_id>/xp/config/update/', views.api_xp_config_update, name='api_xp_config_update'),
    path('api/guild/<str:guild_id>/xp/leaderboard/', views.api_xp_leaderboard, name='api_xp_leaderboard'),
    path('api/guild/<str:guild_id>/xp/member/<str:user_id>/', views.api_xp_member_update, name='api_xp_member_update'),
    path('api/guild/<str:guild_id>/xp/roles/', views.api_xp_level_roles, name='api_xp_level_roles'),
    path('api/guild/<str:guild_id>/xp/roles/create/', views.api_xp_level_role_create, name='api_xp_level_role_create'),
    path('api/guild/<str:guild_id>/xp/roles/<int:role_id>/delete/', views.api_xp_level_role_delete, name='api_xp_level_role_delete'),

    # Role Management Dashboard
    path('warden/guild/<str:guild_id>/roles/', views.guild_roles, name='guild_roles'),

    # Role API Endpoints
    path('api/guild/<str:guild_id>/roles/action/', views.api_role_action, name='api_role_action'),
    path('api/guild/<str:guild_id>/roles/import/', views.api_role_bulk_import, name='api_role_bulk_import'),
    path('api/guild/<str:guild_id>/roles/import/<int:job_id>/', views.api_bulk_import_status, name='api_bulk_import_status'),

    # Audit Logs Dashboard
    path('warden/guild/<str:guild_id>/audit/', views.guild_audit_logs, name='guild_audit_logs'),

    # Audit Logs API Endpoints
    path('api/guild/<str:guild_id>/audit/', views.api_audit_logs, name='api_audit_logs'),
    path('api/guild/<str:guild_id>/audit/stats/', views.api_audit_stats, name='api_audit_stats'),

    # Welcome/Goodbye Messages Dashboard
    path('warden/guild/<str:guild_id>/welcome/', views.guild_welcome, name='guild_welcome'),

    # Welcome API Endpoints
    path('api/guild/<str:guild_id>/welcome/config/', views.api_welcome_config, name='api_welcome_config'),
    path('api/guild/<str:guild_id>/welcome/config/update/', views.api_welcome_config_update, name='api_welcome_config_update'),
    path('api/guild/<str:guild_id>/welcome/test/', views.api_welcome_test, name='api_welcome_test'),

    # Level-Up Messages Dashboard
    path('warden/guild/<str:guild_id>/levelup/', views.guild_levelup, name='guild_levelup'),

    # Level-Up API Endpoints
    path('api/guild/<str:guild_id>/levelup/config/update/', views.api_levelup_config_update, name='api_levelup_config_update'),

    # Server Settings Dashboard
    path('warden/guild/<str:guild_id>/settings/', views.guild_settings, name='guild_settings'),

    # Settings API Endpoints
    path('api/guild/<str:guild_id>/settings/update/', views.api_settings_update, name='api_settings_update'),

    # Verification Dashboard
    path('warden/guild/<str:guild_id>/verification/', views.guild_verification, name='guild_verification'),

    # Verification API Endpoints
    path('api/guild/<str:guild_id>/verification/config/update/', views.api_verification_config_update, name='api_verification_config_update'),

    # Moderation Dashboard
    path('warden/guild/<str:guild_id>/moderation/', views.guild_moderation, name='guild_moderation'),

    # Moderation API Endpoints
    path('api/guild/<str:guild_id>/warnings/', views.api_warnings_list, name='api_warnings_list'),
    path('api/guild/<str:guild_id>/warnings/<int:warning_id>/pardon/', views.api_warning_pardon, name='api_warning_pardon'),

    # Templates Dashboard
    path('warden/guild/<str:guild_id>/templates/', views.guild_templates, name='guild_templates'),

    # Templates API Endpoints
    path('api/guild/<str:guild_id>/templates/channels/', views.api_channel_template_create, name='api_channel_template_create'),
    path('api/guild/<str:guild_id>/templates/channels/<int:template_id>/', views.api_channel_template_delete, name='api_channel_template_delete'),
    path('api/guild/<str:guild_id>/templates/channels/<int:template_id>/apply/', views.api_channel_template_apply, name='api_channel_template_apply'),
    path('api/guild/<str:guild_id>/templates/roles/', views.api_role_template_create, name='api_role_template_create'),
    path('api/guild/<str:guild_id>/templates/roles/<int:template_id>/', views.api_role_template_delete, name='api_role_template_delete'),
    path('api/guild/<str:guild_id>/templates/roles/<int:template_id>/apply/', views.api_role_template_apply, name='api_role_template_apply'),

    # Discovery/Self-Promo Dashboard
    path('warden/guild/<str:guild_id>/discovery/', views.guild_discovery, name='guild_discovery'),

    # Discovery API Endpoints
    path('api/guild/<str:guild_id>/discovery/config/update/', views.api_discovery_config_update, name='api_discovery_config_update'),
    path('api/guild/<str:guild_id>/discovery/pool/', views.api_discovery_pool, name='api_discovery_pool'),
    path('api/guild/<str:guild_id>/discovery/pool/<int:entry_id>/', views.api_discovery_pool_remove, name='api_discovery_pool_remove'),
    path('api/guild/<str:guild_id>/discovery/feature/', views.api_discovery_force_feature, name='api_discovery_force_feature'),

    # LFG Dashboard
    path('warden/guild/<str:guild_id>/lfg/', views.guild_lfg, name='guild_lfg'),

    # LFG API Endpoints
    path('api/guild/<str:guild_id>/lfg/search/', views.api_lfg_search, name='api_lfg_search'),
    path('api/guild/<str:guild_id>/lfg/add/', views.api_lfg_add, name='api_lfg_add'),
    path('api/guild/<str:guild_id>/lfg/<int:game_id>/', views.api_lfg_remove, name='api_lfg_remove'),
    path('api/guild/<str:guild_id>/lfg/<int:game_id>/update/', views.api_lfg_game_update, name='api_lfg_game_update'),

    # LFG Premium API Endpoints (Attendance & Reliability)
    path('api/guild/<str:guild_id>/lfg/config/', views.api_lfg_config, name='api_lfg_config'),
    path('api/guild/<str:guild_id>/lfg/stats/', views.api_lfg_stats, name='api_lfg_stats'),
    path('api/guild/<str:guild_id>/lfg/groups/', views.api_lfg_groups, name='api_lfg_groups'),
    path('api/guild/<str:guild_id>/lfg/blacklist/', views.api_lfg_blacklist, name='api_lfg_blacklist'),
    path('api/guild/<str:guild_id>/lfg/blacklist/<str:user_id>/', views.api_lfg_blacklist_update, name='api_lfg_blacklist_update'),
]
