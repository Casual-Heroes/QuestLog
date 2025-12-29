from django.urls import path, include
from . import views

urlpatterns = [
    # SEO and crawlers
    path('robots.txt', views.robots_txt, name='robots_txt'),

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
    path('icaurs/', views.icarus, name='icarus'),
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

    # QuestLog
    path('questlog/overview/', views.questlog_overview, name='questlog_overview'),
    path('questlog/login/', views.questlog_login, name='questlog_login'),
    path('questlog/creatorofthemonth/', views.creator_of_the_month_page, name='creator_of_the_month'),
    path('questlog/creatoroftheweek/', views.creator_of_the_week_page, name='creator_of_the_week'),

    # Discord OAuth2 Authentication
    path('auth/discord/login/', views.discord_login, name='discord_login'),
    path('auth/discord/callback/', views.discord_callback, name='discord_callback'),
    path('auth/discord/logout/', views.discord_logout, name='discord_logout'),
    path('auth/discord/refresh-guilds/', views.discord_refresh_guilds, name='discord_refresh_guilds'),

    # Bot Installation
    path('bot/install/callback/', views.bot_install_callback, name='bot_install_callback'),

    # User Pages
    path('profile/', views.user_profile, name='user_profile'),

    # QuestLog Dashboard
    path('questlog/', views.questlog_dashboard, name='questlog_dashboard'),
    path('questlog/guild/<str:guild_id>/', views.guild_dashboard, name='guild_dashboard'),
    path('questlog/guild/<str:guild_id>/profile/', views.member_profile, name='member_profile'),
    path('questlog/guild/<str:guild_id>/leaderboards/', views.guild_leaderboards, name='guild_leaderboards'),
    path('questlog/guild/<str:guild_id>/trackers/', views.guild_trackers, name='guild_trackers'),
    path('questlog/guild/<str:guild_id>/billing/', views.guild_billing, name='guild_billing'),
    path('questlog/guild/<str:guild_id>/flair-store/', views.flair_store, name='flair_store'),
    path('questlog/guild/<str:guild_id>/flair-management/', views.flair_management, name='flair_management'),
    path('questlog/api/guild/<str:guild_id>/sync/', views.force_sync_guild, name='force_sync_guild'),
    path('questlog/api/guild/<str:guild_id>/invalidate-cache/', views.invalidate_cache, name='invalidate_cache'),

    # Flair API Endpoints
    path('api/guild/<str:guild_id>/flairs/', views.api_flair_list, name='api_flair_list'),
    path('api/guild/<str:guild_id>/flairs/bulk-update/', views.api_flair_bulk_update, name='api_flair_bulk_update'),
    path('api/guild/<str:guild_id>/flairs/create/', views.api_flair_create, name='api_flair_create'),
    path('api/guild/<str:guild_id>/flairs/create-default-roles/', views.api_flair_create_default_roles, name='api_flair_create_default_roles'),
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
    path('questlog/guild/<str:guild_id>/xp/', views.guild_xp, name='guild_xp'),

    # XP API Endpoints
    path('api/guild/<str:guild_id>/xp/config/', views.api_xp_config, name='api_xp_config'),
    path('api/guild/<str:guild_id>/xp/config/update/', views.api_xp_config_update, name='api_xp_config_update'),
    path('api/guild/<str:guild_id>/xp/toggle/', views.api_xp_toggle, name='api_xp_toggle'),
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

    # XP Boost Events API
    path('api/guild/<str:guild_id>/xp/boost-events/', views.api_xp_boost_events_list, name='api_xp_boost_events_list'),
    path('api/guild/<str:guild_id>/xp/boost-events/create/', views.api_xp_boost_event_create, name='api_xp_boost_event_create'),
    path('api/guild/<str:guild_id>/xp/boost-events/<int:event_id>/', views.api_xp_boost_event_update, name='api_xp_boost_event_update'),
    path('api/guild/<str:guild_id>/xp/boost-events/<int:event_id>/delete/', views.api_xp_boost_event_delete, name='api_xp_boost_event_delete'),

    # Role Management Dashboard
    path('questlog/guild/<str:guild_id>/roles/', views.guild_roles, name='guild_roles'),

    # Reaction Roles Dashboard
    path('questlog/guild/<str:guild_id>/reaction-roles/', views.guild_reaction_roles, name='guild_reaction_roles'),

    # Reaction Roles API
    path('api/guild/<str:guild_id>/reaction-roles/', views.api_reaction_roles, name='api_reaction_roles'),
    path('api/guild/<str:guild_id>/reaction-roles/<str:message_id>/', views.api_reaction_role_detail, name='api_reaction_role_detail'),

    # Role API Endpoints
    path('api/guild/<str:guild_id>/roles/action/', views.api_role_action, name='api_role_action'),
    path('api/guild/<str:guild_id>/roles/import/', views.api_role_bulk_import, name='api_role_bulk_import'),
    path('api/guild/<str:guild_id>/roles/import/<int:job_id>/', views.api_bulk_import_status, name='api_bulk_import_status'),
    path('api/guild/<str:guild_id>/roles/export-template/', views.api_role_export_template, name='api_role_export_template'),
    path('api/guild/<str:guild_id>/roles/export-roles/', views.api_role_export_current, name='api_role_export_current'),
    path('api/guild/<str:guild_id>/roles/create/', views.api_role_create, name='api_role_create'),
    path('api/guild/<str:guild_id>/roles/bulk-create/', views.api_role_bulk_create, name='api_role_bulk_create'),
    path('api/guild/<str:guild_id>/roles/export-create-template/', views.api_role_export_create_template, name='api_role_export_create_template'),

    # Raffles (Engagement)
    path('questlog/guild/<str:guild_id>/raffles/', views.guild_raffles, name='guild_raffles'),
    path('questlog/guild/<str:guild_id>/raffle-browser/', views.guild_raffle_browser, name='guild_raffle_browser'),
    path('api/guild/<str:guild_id>/raffles/', views.api_raffle_list, name='api_raffle_list'),
    path('api/guild/<str:guild_id>/raffles/create/', views.api_raffle_create, name='api_raffle_create'),
    path('api/guild/<str:guild_id>/raffles/<int:raffle_id>/update/', views.api_raffle_update, name='api_raffle_update'),
    path('api/guild/<str:guild_id>/raffles/<int:raffle_id>/enter/', views.api_raffle_enter, name='api_raffle_enter'),
    path('api/guild/<str:guild_id>/raffles/<int:raffle_id>/pick/', views.api_raffle_pick, name='api_raffle_pick'),
    path('api/guild/<str:guild_id>/raffles/<int:raffle_id>/start/', views.api_raffle_start_now, name='api_raffle_start_now'),
    path('api/guild/<str:guild_id>/raffles/<int:raffle_id>/end/', views.api_raffle_end_now, name='api_raffle_end_now'),

    # Audit Logs Dashboard
    path('questlog/guild/<str:guild_id>/audit/', views.guild_audit_logs, name='guild_audit_logs'),

    # Audit Logs API Endpoints
    path('api/guild/<str:guild_id>/audit/', views.api_audit_logs, name='api_audit_logs'),
    path('api/guild/<str:guild_id>/audit/stats/', views.api_audit_stats, name='api_audit_stats'),
    path('api/guild/<str:guild_id>/audit/config/', views.api_audit_config_update, name='api_audit_config_update'),
    path('api/guild/<str:guild_id>/audit/export/', views.api_audit_export, name='api_audit_export'),

    # Welcome/Goodbye Messages Dashboard
    path('questlog/guild/<str:guild_id>/welcome/', views.guild_welcome, name='guild_welcome'),

    # Welcome API Endpoints
    path('api/guild/<str:guild_id>/welcome/config/', views.api_welcome_config, name='api_welcome_config'),
    path('api/guild/<str:guild_id>/welcome/config/update/', views.api_welcome_config_update, name='api_welcome_config_update'),
    path('api/guild/<str:guild_id>/welcome/test/', views.api_welcome_test, name='api_welcome_test'),

    # Level-Up Messages Dashboard
    path('questlog/guild/<str:guild_id>/levelup/', views.guild_levelup, name='guild_levelup'),

    # Level-Up API Endpoints
    path('api/guild/<str:guild_id>/levelup/config/update/', views.api_levelup_config_update, name='api_levelup_config_update'),

    # Discord Resource API Endpoints (cached to reduce rate limiting)
    path('api/guild/<str:guild_id>/channels/', views.api_guild_channels, name='api_guild_channels'),
    path('api/guild/<str:guild_id>/roles/', views.api_guild_roles, name='api_guild_roles'),
    path('api/guild/<str:guild_id>/members/', views.api_guild_members, name='api_guild_members'),
    path('api/guild/<str:guild_id>/emojis/', views.api_guild_emojis, name='api_guild_emojis'),
    path('api/guild/<str:guild_id>/messages/', views.api_message_action, name='api_message_action'),

    # Scheduled Messages API Endpoints
    path('api/guild/<str:guild_id>/scheduled-messages/', views.api_scheduled_messages_list, name='api_scheduled_messages_list'),
    path('api/guild/<str:guild_id>/scheduled-messages/create/', views.api_scheduled_messages_create, name='api_scheduled_messages_create'),
    path('api/guild/<str:guild_id>/scheduled-messages/<int:message_id>/update/', views.api_scheduled_messages_update, name='api_scheduled_messages_update'),
    path('api/guild/<str:guild_id>/scheduled-messages/<int:message_id>/cancel/', views.api_scheduled_messages_cancel, name='api_scheduled_messages_cancel'),

    # Server Settings Dashboard
    path('questlog/guild/<str:guild_id>/settings/', views.guild_settings, name='guild_settings'),
    path('questlog/guild/<str:guild_id>/messages/', views.guild_messages, name='guild_messages'),

    # Settings API Endpoints
    path('api/guild/<str:guild_id>/settings/update/', views.api_settings_update, name='api_settings_update'),
    path('api/guild/<str:guild_id>/settings/reset/', views.api_settings_reset, name='api_settings_reset'),
    path('api/guild/<str:guild_id>/settings/remove-data/', views.api_settings_remove_data, name='api_settings_remove_data'),

    # Stripe Integration Endpoints
    path('api/guild/<str:guild_id>/stripe/checkout/', views.stripe_create_checkout, name='stripe_create_checkout'),
    path('api/guild/<str:guild_id>/stripe/cancel/', views.stripe_cancel_subscription, name='stripe_cancel_subscription'),
    path('api/guild/<str:guild_id>/stripe/status/', views.stripe_subscription_status, name='stripe_subscription_status'),
    path('api/guild/<str:guild_id>/stripe/portal/', views.stripe_billing_portal, name='stripe_billing_portal'),
    path('api/guild/<str:guild_id>/stripe/transfer/', views.stripe_transfer_subscription, name='stripe_transfer_subscription'),
    path('webhooks/stripe/', views.stripe_webhook, name='stripe_webhook'),

    # Verification Dashboard
    path('questlog/guild/<str:guild_id>/verification/', views.guild_verification, name='guild_verification'),

    # Verification API Endpoints
    path('api/guild/<str:guild_id>/verification/config/update/', views.api_verification_config_update, name='api_verification_config_update'),

    # Moderation Dashboard
    path('questlog/guild/<str:guild_id>/moderation/', views.guild_moderation, name='guild_moderation'),
    path('questlog/guild/<str:guild_id>/moderation/settings/', views.guild_moderation_settings, name='guild_moderation_settings'),

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
    path('questlog/guild/<str:guild_id>/templates/', views.guild_templates, name='guild_templates'),

    # Templates API Endpoints
    path('api/guild/<str:guild_id>/templates/channels/', views.api_channel_template_create, name='api_channel_template_create'),
    path('api/guild/<str:guild_id>/templates/channels/<int:template_id>/', views.api_channel_template_detail_update_delete, name='api_channel_template_ops'),
    path('api/guild/<str:guild_id>/templates/channels/<int:template_id>/apply/', views.api_channel_template_apply, name='api_channel_template_apply'),
    path('api/guild/<str:guild_id>/templates/roles/', views.api_role_template_create, name='api_role_template_create'),
    path('api/guild/<str:guild_id>/templates/roles/<int:template_id>/', views.api_role_template_detail_update_delete, name='api_role_template_ops'),
    path('api/guild/<str:guild_id>/templates/roles/<int:template_id>/apply/', views.api_role_template_apply, name='api_role_template_apply'),
    path('api/guild/<str:guild_id>/roles/', views.api_guild_roles, name='api_guild_roles'),

    # Discovery/Self-Promo Dashboard
    path('questlog/guild/<str:guild_id>/discovery/', views.guild_discovery, name='guild_discovery'),
    path('questlog/guild/<str:guild_id>/discovery-network/', views.guild_discovery_network, name='guild_discovery_network'),
    path('questlog/guild/<str:guild_id>/found-games/', views.guild_found_games, name='guild_found_games'),

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
    path('api/guild/<str:guild_id>/discovery/purge-announced-games/', views.api_purge_announced_games, name='api_purge_announced_games'),

    # Game Search Configs
    path('api/guild/<str:guild_id>/discovery/searches/', views.api_game_search_configs_list, name='api_game_search_configs_list'),
    path('api/guild/<str:guild_id>/discovery/searches/create/', views.api_game_search_config_create, name='api_game_search_config_create'),
    path('api/guild/<str:guild_id>/discovery/searches/<int:search_id>/update/', views.api_game_search_config_update, name='api_game_search_config_update'),

    # Discovery Network API Endpoints
    path('api/discovery/servers', views.api_discovery_network_servers, name='api_discovery_network_servers'),
    path('api/discovery/lfg', views.api_discovery_network_lfg, name='api_discovery_network_lfg'),
    path('api/discovery/lfg/create', views.api_discovery_lfg_create, name='api_discovery_lfg_create'),
    path('api/discovery/lfg/<int:post_id>/join', views.api_discovery_lfg_join, name='api_discovery_lfg_join'),
    path('api/discovery/lfg/<int:post_id>/update', views.api_discovery_lfg_update, name='api_discovery_lfg_update'),
    path('api/discovery/lfg/<int:post_id>/update-class', views.api_discovery_lfg_update_class, name='api_discovery_lfg_update_class'),
    path('api/discovery/lfg/<int:post_id>/delete', views.api_discovery_lfg_delete, name='api_discovery_lfg_delete'),
    path('api/discovery/lfg-games', views.api_discovery_network_lfg_games, name='api_discovery_network_lfg_games'),
    path('api/discovery/lfg-activities', views.api_discovery_network_lfg_activities, name='api_discovery_network_lfg_activities'),
    path('api/discovery/game-config', views.api_discovery_game_config, name='api_discovery_game_config'),
    path('api/discovery/games', views.api_discovery_network_games, name='api_discovery_network_games'),
    path('api/discovery/game-templates', views.api_discovery_game_templates, name='api_discovery_game_templates'),
    path('api/discovery/game-roles', views.api_discovery_game_roles, name='api_discovery_game_roles'),
    path('api/discovery/apply', views.api_discovery_network_apply, name='api_discovery_network_apply'),
    path('api/discovery/preferences', views.api_discovery_network_preferences, name='api_discovery_network_preferences'),
    path('api/discovery/leave', views.api_discovery_network_leave, name='api_discovery_network_leave'),
    path('api/discovery/rejoin', views.api_discovery_network_rejoin, name='api_discovery_network_rejoin'),

    # Game Discovery Endpoints (new)
    path('api/igdb/search', views.api_igdb_search, name='api_igdb_search'),
    path('api/discovery/games-list', views.api_discovery_games_list, name='api_discovery_games_list'),
    path('api/discovery/share-game', views.api_discovery_share_game, name='api_discovery_share_game'),
    path('api/discovery/game-share-limit', views.api_discovery_game_share_limit, name='api_discovery_game_share_limit'),
    path('api/discovery/games/<str:game_id>/reviews', views.api_discovery_game_reviews, name='api_discovery_game_reviews'),
    path('api/discovery/games/<str:game_id>/discussions', views.api_discovery_game_discussions, name='api_discovery_game_discussions'),
    path('api/discovery/discussions/<int:discussion_id>/upvote', views.api_discovery_discussion_upvote, name='api_discovery_discussion_upvote'),

    # User Settings for Discovery Network
    path('api/discovery/user/main-server', views.api_discovery_user_main_server, name='api_discovery_user_main_server'),
    path('api/discovery/user/set-main-server', views.api_discovery_user_set_main_server, name='api_discovery_user_set_main_server'),

    # Creator Discovery Endpoints
    path('api/discovery/creators-list', views.api_discovery_creators_list, name='api_discovery_creators_list'),
    path('api/discovery/feature-creator', views.api_discovery_feature_creator, name='api_discovery_feature_creator'),
    path('api/discovery/network-creators', views.api_discovery_network_creators, name='api_discovery_network_creators'),

    # Discovery Network Admin API Endpoints (Bot Owner Only)
    path('api/discovery/admin/applications', views.api_discovery_network_admin_applications, name='api_discovery_network_admin_applications'),
    path('api/discovery/admin/applications/<int:application_id>/approve', views.api_discovery_network_admin_approve, name='api_discovery_network_admin_approve'),
    path('api/discovery/admin/applications/<int:application_id>/deny', views.api_discovery_network_admin_deny, name='api_discovery_network_admin_deny'),
    path('api/discovery/admin/applications/<int:application_id>/ban', views.api_discovery_network_admin_ban, name='api_discovery_network_admin_ban'),
    path('api/guild/<str:guild_id>/discovery/searches/<int:search_id>/delete/', views.api_game_search_config_delete, name='api_game_search_config_delete'),

    # Action Status
    path('api/guild/<str:guild_id>/action/<str:action_id>/status/', views.api_action_status, name='api_action_status'),

    # LFG Dashboard
    path('questlog/guild/<str:guild_id>/lfg/', views.guild_lfg, name='guild_lfg'),
    path('questlog/guild/<str:guild_id>/lfg/browser/', views.guild_lfg_browser, name='guild_lfg_browser'),
    path('questlog/guild/<str:guild_id>/attendance/', views.guild_attendance, name='guild_attendance'),
    path('questlog/guild/<str:guild_id>/featured-creators/', views.guild_featured_creators, name='guild_featured_creators'),
    path('questlog/guild/<str:guild_id>/cotw/', views.guild_cotw, name='guild_cotw'),
    path('questlog/guild/<str:guild_id>/cotm/', views.guild_cotm, name='guild_cotm'),

    # Creator Profile Management (Phase 1)
    path('questlog/guild/<str:guild_id>/creator/register/', views.creator_profile_register, name='creator_profile_register'),
    path('api/guild/<str:guild_id>/creator/delete/', views.creator_profile_delete, name='creator_profile_delete'),
    path('api/guild/<str:guild_id>/creator/set-cotw/', views.set_creator_of_week, name='set_creator_of_week'),
    path('api/guild/<str:guild_id>/creator/set-cotm/', views.set_creator_of_month, name='set_creator_of_month'),

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
    path('api/guild/<str:guild_id>/lfg/pardon/', views.api_lfg_pardon, name='api_lfg_pardon'),
    path('api/guild/<str:guild_id>/lfg/blacklist/<str:user_id>/', views.api_lfg_blacklist_update, name='api_lfg_blacklist_update'),
    path('api/guild/<str:guild_id>/lfg/attendance/update/', views.api_lfg_attendance_update, name='api_lfg_attendance_update'),
    path('api/guild/<str:guild_id>/lfg/attendance/export/', views.api_lfg_attendance_export, name='api_lfg_attendance_export'),
    path('api/guild/<str:guild_id>/lfg/attendance/user/<str:user_id>/', views.api_lfg_user_history, name='api_lfg_user_history'),

    # LFG Browser API Endpoints (All Tiers - Game limits enforced)
    path('api/guild/<str:guild_id>/lfg/manager-check/', views.api_lfg_manager_check, name='api_lfg_manager_check'),
    path('api/guild/<str:guild_id>/lfg/browser/groups/', views.api_lfg_browser_groups, name='api_lfg_browser_groups'),
    path('api/guild/<str:guild_id>/lfg/browser/create/', views.api_lfg_browser_create, name='api_lfg_browser_create'),
    path('api/guild/<str:guild_id>/lfg/browser/<int:group_id>/join/', views.api_lfg_browser_join, name='api_lfg_browser_join'),
    path('api/guild/<str:guild_id>/lfg/browser/<int:group_id>/leave/', views.api_lfg_browser_leave, name='api_lfg_browser_leave'),
    path('api/guild/<str:guild_id>/lfg/browser/<int:group_id>/remove-member/', views.api_lfg_browser_remove_member, name='api_lfg_browser_remove_member'),
    path('api/guild/<str:guild_id>/lfg/browser/<int:group_id>/join-thread/', views.api_lfg_browser_join_thread, name='api_lfg_browser_join_thread'),
    path('api/guild/<str:guild_id>/lfg/browser/<int:group_id>/update/', views.api_lfg_browser_update, name='api_lfg_browser_update'),
    path('api/guild/<str:guild_id>/lfg/browser/<int:group_id>/update-class/', views.api_lfg_browser_update_class, name='api_lfg_browser_update_class'),
    path('api/guild/<str:guild_id>/lfg/browser/<int:group_id>/delete/', views.api_lfg_browser_delete, name='api_lfg_browser_delete'),
    path('api/guild/<str:guild_id>/lfg/browser/audit-logs/', views.api_lfg_browser_audit_logs, name='api_lfg_browser_audit_logs'),
    path('api/guild/<str:guild_id>/lfg/browser-notifications/', views.api_lfg_browser_notifications, name='api_lfg_browser_notifications'),
]
