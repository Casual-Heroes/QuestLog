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

    # WardenBot
    path('wardenbot/overview/', views.wardenbot_overview, name='wardenbot_overview'),
    path('wardenbot/login/', views.wardenbot_login, name='wardenbot_login'),
    path('wardenbot/creatorofthemonth/', views.creator_of_the_month_page, name='creator_of_the_month'),
    path('wardenbot/creatoroftheweek/', views.creator_of_the_week_page, name='creator_of_the_week'),

    # Discord OAuth2 Authentication
    path('auth/discord/login/', views.discord_login, name='discord_login'),
    path('auth/discord/callback/', views.discord_callback, name='discord_callback'),
    path('auth/discord/logout/', views.discord_logout, name='discord_logout'),

    # Bot Installation
    path('bot/install/callback/', views.bot_install_callback, name='bot_install_callback'),

    # User Pages
    path('profile/', views.user_profile, name='user_profile'),

    # Warden Bot Dashboard
    path('warden/', views.warden_dashboard, name='warden_dashboard'),
    path('warden/guild/<str:guild_id>/', views.guild_dashboard, name='guild_dashboard'),
    path('warden/guild/<str:guild_id>/profile/', views.member_profile, name='member_profile'),
    path('warden/guild/<str:guild_id>/leaderboards/', views.guild_leaderboards, name='guild_leaderboards'),
    path('warden/guild/<str:guild_id>/trackers/', views.guild_trackers, name='guild_trackers'),
    path('warden/guild/<str:guild_id>/flair-store/', views.flair_store, name='flair_store'),
    path('warden/guild/<str:guild_id>/flair-management/', views.flair_management, name='flair_management'),
    path('warden/api/guild/<str:guild_id>/sync/', views.force_sync_guild, name='force_sync_guild'),
    path('warden/api/guild/<str:guild_id>/invalidate-cache/', views.invalidate_cache, name='invalidate_cache'),

    # Flair API Endpoints
    path('api/guild/<str:guild_id>/flairs/', views.api_flair_list, name='api_flair_list'),
    path('api/guild/<str:guild_id>/flairs/bulk-update/', views.api_flair_bulk_update, name='api_flair_bulk_update'),
    path('api/guild/<str:guild_id>/flairs/create/', views.api_flair_create, name='api_flair_create'),
    path('api/guild/<str:guild_id>/flairs/<int:flair_id>/delete/', views.api_flair_delete, name='api_flair_delete'),

    # Warden API (REST endpoints for dashboard AJAX)
    path('api/guild/<str:guild_id>/trackers/', views.api_trackers_list, name='api_trackers_list'),
    path('api/guild/<str:guild_id>/trackers/create/', views.api_tracker_create, name='api_tracker_create'),
    path('api/guild/<str:guild_id>/trackers/<int:tracker_id>/', views.api_tracker_update, name='api_tracker_update'),
    path('api/guild/<str:guild_id>/trackers/<int:tracker_id>/delete/', views.api_tracker_delete, name='api_tracker_delete'),

    # Guild Resources API (for dropdowns)
    path('api/guild/<str:guild_id>/resources/', views.api_guild_resources, name='api_guild_resources'),

    # Guild Management API
    path('api/guild/<str:guild_id>/leave/', views.api_guild_leave, name='api_guild_leave'),

    # XP Dashboard
    path('warden/guild/<str:guild_id>/xp/', views.guild_xp, name='guild_xp'),

    # XP API Endpoints
    path('api/guild/<str:guild_id>/xp/config/', views.api_xp_config, name='api_xp_config'),
    path('api/guild/<str:guild_id>/xp/config/update/', views.api_xp_config_update, name='api_xp_config_update'),
    path('api/guild/<str:guild_id>/xp/leaderboard/', views.api_xp_leaderboard, name='api_xp_leaderboard'),
    path('api/guild/<str:guild_id>/xp/member/<str:user_id>/', views.api_xp_member_update, name='api_xp_member_update'),
    path('api/guild/<str:guild_id>/xp/roles/', views.api_xp_level_roles, name='api_xp_level_roles'),
    path('api/guild/<str:guild_id>/xp/roles/create/', views.api_xp_level_role_create, name='api_xp_level_role_create'),
    path('api/guild/<str:guild_id>/xp/roles/bulk-create/', views.api_xp_level_role_bulk_create, name='api_xp_level_role_bulk_create'),
    path('api/guild/<str:guild_id>/xp/roles/<int:role_id>/delete/', views.api_xp_level_role_delete, name='api_xp_level_role_delete'),
    path('api/guild/<str:guild_id>/xp/member/<str:user_id>/delete/', views.api_xp_member_delete, name='api_xp_member_delete'),
    path('api/guild/<str:guild_id>/xp/member/add/', views.api_xp_member_add, name='api_xp_member_add'),
    path('api/guild/<str:guild_id>/xp/import/', views.api_xp_import_csv, name='api_xp_import_csv'),
    path('api/guild/<str:guild_id>/xp/export/', views.api_xp_export_csv, name='api_xp_export_csv'),
    path('api/guild/<str:guild_id>/xp/bulk-edit/', views.api_xp_bulk_edit, name='api_xp_bulk_edit'),

    # Role Management Dashboard
    path('warden/guild/<str:guild_id>/roles/', views.guild_roles, name='guild_roles'),

    # Reaction Roles Dashboard
    path('warden/guild/<str:guild_id>/reaction-roles/', views.guild_reaction_roles, name='guild_reaction_roles'),

    # Role API Endpoints
    path('api/guild/<str:guild_id>/roles/action/', views.api_role_action, name='api_role_action'),
    path('api/guild/<str:guild_id>/roles/import/', views.api_role_bulk_import, name='api_role_bulk_import'),
    path('api/guild/<str:guild_id>/roles/import/<int:job_id>/', views.api_bulk_import_status, name='api_bulk_import_status'),
    path('api/guild/<str:guild_id>/roles/export-template/', views.api_role_export_template, name='api_role_export_template'),
    path('api/guild/<str:guild_id>/roles/export-roles/', views.api_role_export_current, name='api_role_export_current'),
    path('api/guild/<str:guild_id>/roles/create/', views.api_role_create, name='api_role_create'),
    path('api/guild/<str:guild_id>/roles/bulk-create/', views.api_role_bulk_create, name='api_role_bulk_create'),
    path('api/guild/<str:guild_id>/roles/export-create-template/', views.api_role_export_create_template, name='api_role_export_create_template'),

    # Audit Logs Dashboard
    path('warden/guild/<str:guild_id>/audit/', views.guild_audit_logs, name='guild_audit_logs'),

    # Audit Logs API Endpoints
    path('api/guild/<str:guild_id>/audit/', views.api_audit_logs, name='api_audit_logs'),
    path('api/guild/<str:guild_id>/audit/stats/', views.api_audit_stats, name='api_audit_stats'),
    path('api/guild/<str:guild_id>/audit/config/', views.api_audit_config_update, name='api_audit_config_update'),

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

    # Discord Resource API Endpoints (cached to reduce rate limiting)
    path('api/guild/<str:guild_id>/channels/', views.api_guild_channels, name='api_guild_channels'),
    path('api/guild/<str:guild_id>/roles/', views.api_guild_roles, name='api_guild_roles'),
    path('api/guild/<str:guild_id>/emojis/', views.api_guild_emojis, name='api_guild_emojis'),

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
    path('warden/guild/<str:guild_id>/moderation/settings/', views.guild_moderation_settings, name='guild_moderation_settings'),

    # Moderation API Endpoints
    path('api/guild/<str:guild_id>/warnings/', views.api_warnings_list, name='api_warnings_list'),
    path('api/guild/<str:guild_id>/warnings/<int:warning_id>/pardon/', views.api_warning_pardon, name='api_warning_pardon'),
    path('api/guild/<str:guild_id>/mod/untimeout/', views.api_mod_untimeout, name='api_mod_untimeout'),
    path('api/guild/<str:guild_id>/mod/kick/', views.api_mod_kick, name='api_mod_kick'),
    path('api/guild/<str:guild_id>/mod/ban/', views.api_mod_ban, name='api_mod_ban'),
    path('api/guild/<str:guild_id>/mod/unban/', views.api_mod_unban, name='api_mod_unban'),
    path('api/guild/<str:guild_id>/mod/unmute/', views.api_mod_unmute, name='api_mod_unmute'),
    path('api/guild/<str:guild_id>/mod/unjail/', views.api_mod_unjail, name='api_mod_unjail'),
    path('api/guild/<str:guild_id>/moderation/settings/', views.api_mod_settings_update, name='api_mod_settings_update'),

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
    path('warden/guild/<str:guild_id>/found-games/', views.guild_found_games, name='guild_found_games'),

    # Discovery API Endpoints
    path('api/guild/<str:guild_id>/discovery/config/update/', views.api_discovery_config_update, name='api_discovery_config_update'),
    path('api/guild/<str:guild_id>/discovery/pool/', views.api_discovery_pool, name='api_discovery_pool'),
    path('api/guild/<str:guild_id>/discovery/pool/<int:entry_id>/', views.api_discovery_pool_remove, name='api_discovery_pool_remove'),
    path('api/guild/<str:guild_id>/discovery/feature/', views.api_discovery_force_feature, name='api_discovery_force_feature'),
    path('api/guild/<str:guild_id>/discovery/clear/', views.api_discovery_clear_featured, name='api_discovery_clear_featured'),
    path('api/guild/<str:guild_id>/discovery/test-channel-embed/', views.api_discovery_test_channel_embed, name='api_discovery_test_channel_embed'),
    path('api/guild/<str:guild_id>/discovery/test-forum-embed/', views.api_discovery_test_forum_embed, name='api_discovery_test_forum_embed'),
    path('api/guild/<str:guild_id>/discovery/game-config/update/', views.api_game_discovery_config_update, name='api_game_discovery_config_update'),
    path('api/guild/<str:guild_id>/discovery/check-games/', views.api_game_discovery_check, name='api_game_discovery_check'),

    # Game Search Configs
    path('api/guild/<str:guild_id>/discovery/searches/', views.api_game_search_configs_list, name='api_game_search_configs_list'),
    path('api/guild/<str:guild_id>/discovery/searches/create/', views.api_game_search_config_create, name='api_game_search_config_create'),
    path('api/guild/<str:guild_id>/discovery/searches/<int:search_id>/update/', views.api_game_search_config_update, name='api_game_search_config_update'),
    path('api/guild/<str:guild_id>/discovery/searches/<int:search_id>/delete/', views.api_game_search_config_delete, name='api_game_search_config_delete'),

    # Action Status
    path('api/guild/<str:guild_id>/action/<str:action_id>/status/', views.api_action_status, name='api_action_status'),

    # LFG Dashboard
    path('warden/guild/<str:guild_id>/lfg/', views.guild_lfg, name='guild_lfg'),
    path('warden/guild/<str:guild_id>/attendance/', views.guild_attendance, name='guild_attendance'),
    path('warden/guild/<str:guild_id>/featured-creators/', views.guild_featured_creators, name='guild_featured_creators'),
    path('warden/guild/<str:guild_id>/cotw/', views.guild_cotw, name='guild_cotw'),
    path('warden/guild/<str:guild_id>/cotm/', views.guild_cotm, name='guild_cotm'),

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
    path('api/guild/<str:guild_id>/lfg/blacklist/toggle/', views.api_lfg_blacklist_toggle, name='api_lfg_blacklist_toggle'),
    path('api/guild/<str:guild_id>/lfg/blacklist/<str:user_id>/', views.api_lfg_blacklist_update, name='api_lfg_blacklist_update'),
    path('api/guild/<str:guild_id>/lfg/attendance/update/', views.api_lfg_attendance_update, name='api_lfg_attendance_update'),
    path('api/guild/<str:guild_id>/lfg/attendance/export/', views.api_lfg_attendance_export, name='api_lfg_attendance_export'),
]
