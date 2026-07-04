from django.urls import path, include
from django.views.generic import RedirectView
from django.shortcuts import redirect
from . import views
from .questlog_web import views as ql_views
from .questlog_web.views_eso import (
    eso_builds_browse, eso_build_create, eso_build_detail, eso_build_edit,
    api_eso_build_vote, api_eso_build_comment, api_eso_build_bookmark, api_eso_build_delete,
)
from .questlog_web.views_ffxiv import (
    ffxiv_tools_hub, ffxiv_ocean_fishing, ffxiv_gathering, ffxiv_resets, ffxiv_fc,
    api_ffxiv_ocean_fishing_rsvp, api_ffxiv_ocean_fishing_schedule,
    ffxiv_collection,
    api_ffxiv_search_characters, api_ffxiv_link_character, api_ffxiv_sync_character,
    api_ffxiv_achievements_ready, api_ffxiv_toggle_clear,
)
from .questlog_web.views_ffxiv_hunts import (
    ffxiv_hunt_board, api_ffxiv_hunt_report, api_ffxiv_hunt_clear,
    api_ffxiv_hunt_clear_all,
    api_hunt_subs_list, api_hunt_sub_save, api_hunt_sub_delete,
)
from .questlog_web.views_ffxiv_deepdungeon import (
    ffxiv_deep_dungeon, api_ffxiv_dd_log_run, api_ffxiv_dd_edit_run,
    api_ffxiv_dd_delete_run, api_ffxiv_dd_admin_wipe,
)
from .questlog_web.views_ffxiv_fieldops import (
    ffxiv_field_ops, api_ffxiv_fo_update, api_ffxiv_fo_delete, api_ffxiv_fo_admin_delete,
)
from .questlog_web.views_ffxiv_marketboard import (
    ffxiv_market_board, api_mb_search, api_mb_prices,
)
from .questlog_web.views_ffxiv_triad import (
    ffxiv_triple_triad, api_triad_cards, api_triad_toggle,
    api_triad_bulk_mark, api_triad_deck_save, api_triad_deck_delete,
    api_triad_clear_all,
)
from .questlog_web.views_ffxiv_apply import (
    ffxiv_apply, api_ffxiv_apply,
    api_admin_ffxiv_applications, api_admin_ffxiv_application_review,
)
from .questlog_web.views_eso_apply import (
    eso_apply, api_eso_apply,
    api_admin_eso_applications, api_admin_eso_application_review,
)
from .questlog_web.views_ffxiv_guides import (
    ffxiv_job_guides, ffxiv_job_hub, ffxiv_guide_detail,
    ffxiv_guide_create, ffxiv_guide_edit,
    api_ffxiv_guide_save, api_ffxiv_guide_update,
    api_ffxiv_guide_like, api_ffxiv_guide_delete, api_ffxiv_guide_hide,
    api_ffxiv_guide_comment, api_ffxiv_guide_comment_like,
    api_ffxiv_guide_comment_delete,
)
from .questlog_web.views_ffxiv_housing import (
    ffxiv_housing, api_ffxiv_housing_worlds, api_ffxiv_housing_plots, api_ffxiv_housing_sync,
)
from .questlog_web.views_bot_dashboard import (
    discord_guild_live_alerts,
    api_discord_guild_streamer_subs,
    api_discord_guild_streamer_sub_detail,
)

urlpatterns = [
    # SEO and crawlers
    path('robots.txt', views.robots_txt, name='robots_txt'),
    path('sitemap.xml', views.sitemap_xml, name='sitemap_xml'),

    path('', views.home, name='home'),

    # Legacy /ql/ redirects - anyone with old cached URLs lands here
    path('ql/', RedirectView.as_view(url='/discover/', permanent=False)),
    path('ql/<path:rest>', views.ql_legacy_redirect, name='ql_legacy_redirect'),
    path('gamesweplay/', views.games_we_play, name='games_we_play'),
    path('api/activity-counts/', views.api_activity_counts, name='api_activity_counts'),
    path('api/ffxiv/world-status/', views.api_ffxiv_world_status, name='api_ffxiv_world_status'),
    path('api/ffxiv/news/', views.api_ffxiv_news, name='api_ffxiv_news'),
    path('api/eso/server-status/', views.api_eso_server_status, name='api_eso_server_status'),


    # Site Activity Tracker (Bot Owner Only - in QuestLog Guild Dashboard)
    path('questlog/guild/<str:guild_id>/site-activity-tracker/', views.site_activity_tracker_admin, name='site_activity_tracker_admin'),
    path('api/guild/<str:guild_id>/site-activity-tracker/games/', views.api_site_activity_games, name='api_site_activity_games_list'),
    path('api/guild/<str:guild_id>/site-activity-tracker/games/<int:game_id>/', views.api_site_activity_games, name='api_site_activity_games_detail'),
    path('api/guild/<str:guild_id>/site-activity-tracker/roles/', views.api_site_activity_roles, name='api_site_activity_roles_create'),
    path('api/guild/<str:guild_id>/site-activity-tracker/roles/<int:role_mapping_id>/', views.api_site_activity_roles, name='api_site_activity_roles_delete'),

    path('gameshype/', views.gameshype, name='gameshype'),
    path('gamesuggest/', views.gamesuggest, name='gamesuggest'),
    path('api/gamesuggest/', views.api_gamesuggest, name='api_gamesuggest'),
    path('hosting/', views.hosting, name='hosting'),
    path('7dtd/', views.sevendtd, name='7dtd'),
    path('dragonwilds/', views.dragonwilds, name='dragonwilds'),
    # path('dune/', views.dune_page, name='dune'),
    # path('pantheon/', views.pantheon_page, name='pantheon'),
    path('wow/', views.wow_page, name='wow'),
    path('eso/', views.eso_page, name='eso'),
    path('eso', views.eso_page),
    path('eso/builds/', eso_builds_browse, name='eso_builds'),
    path('eso/builds/create/', eso_build_create, name='eso_build_create'),
    path('eso/builds/<slug:slug>/', eso_build_detail, name='eso_build_detail'),
    path('eso/builds/<slug:slug>/edit/', eso_build_edit, name='eso_build_edit'),
    path('api/eso/builds/<int:build_id>/vote/', api_eso_build_vote, name='api_eso_build_vote'),
    path('api/eso/builds/<int:build_id>/comment/', api_eso_build_comment, name='api_eso_build_comment'),
    path('api/eso/builds/<int:build_id>/bookmark/', api_eso_build_bookmark, name='api_eso_build_bookmark'),
    path('api/eso/builds/<int:build_id>/delete/', api_eso_build_delete, name='api_eso_build_delete'),
    path('eso/apply/',                            eso_apply,                             name='eso_apply'),
    path('api/eso/apply/',                        api_eso_apply,                         name='api_eso_apply'),
    path('api/admin/eso/applications/',           api_admin_eso_applications,            name='api_admin_eso_applications'),
    path('api/admin/eso/applications/<int:app_id>/review/', api_admin_eso_application_review, name='api_admin_eso_application_review'),
    path('ffxiv/', views.ffxiv_page, name='ffxiv'),
    path('ffxiv', views.ffxiv_page),
    path('ffxiv/tools/', ffxiv_tools_hub, name='ffxiv_tools'),
    path('ffxiv/tools/ocean-fishing/', ffxiv_ocean_fishing, name='ffxiv_ocean_fishing'),
    path('ffxiv/apply/',                         ffxiv_apply,                           name='ffxiv_apply'),
    path('api/ffxiv/apply/',                     api_ffxiv_apply,                       name='api_ffxiv_apply'),
    path('api/admin/ffxiv/applications/',        api_admin_ffxiv_applications,          name='api_admin_ffxiv_applications'),
    path('api/admin/ffxiv/applications/<int:app_id>/review/', api_admin_ffxiv_application_review, name='api_admin_ffxiv_application_review'),
    path('ffxiv/builds/', RedirectView.as_view(url='/ffxiv/tools/job-guides/', permanent=True)),
    path('ffxiv/tools/collection/', ffxiv_collection, name='ffxiv_collection'),
    path('ffxiv/tools/gathering/', ffxiv_gathering, name='ffxiv_gathering'),
    path('ffxiv/tools/resets/', ffxiv_resets, name='ffxiv_resets'),
    path('ffxiv/tools/fc/', ffxiv_fc, name='ffxiv_fc'),
    path('ffxiv/tools/hunt-board/',    ffxiv_hunt_board,    name='ffxiv_hunt_board'),
    path('ffxiv/tools/triple-triad/', ffxiv_triple_triad,   name='ffxiv_triple_triad'),
    path('api/ffxiv/triad/cards/',       api_triad_cards,       name='api_triad_cards'),
    path('api/ffxiv/triad/toggle/',      api_triad_toggle,      name='api_triad_toggle'),
    path('api/ffxiv/triad/bulk-mark/',   api_triad_bulk_mark,   name='api_triad_bulk_mark'),
    path('api/ffxiv/triad/deck/save/',   api_triad_deck_save,   name='api_triad_deck_save'),
    path('api/ffxiv/triad/deck/delete/', api_triad_deck_delete, name='api_triad_deck_delete'),
    path('api/ffxiv/triad/clear-all/',   api_triad_clear_all,   name='api_triad_clear_all'),
    path('ffxiv/tools/deep-dungeon/', ffxiv_deep_dungeon,  name='ffxiv_deep_dungeon'),
    path('api/ffxiv/hunt/report/',    api_ffxiv_hunt_report,  name='api_ffxiv_hunt_report'),
    path('api/ffxiv/hunt/clear/',     api_ffxiv_hunt_clear,     name='api_ffxiv_hunt_clear'),
    path('api/ffxiv/hunt/clear-all/', api_ffxiv_hunt_clear_all, name='api_ffxiv_hunt_clear_all'),
    path('api/ffxiv/hunt/subs/',      api_hunt_subs_list,     name='api_hunt_subs_list'),
    path('api/ffxiv/hunt/subs/save/', api_hunt_sub_save,      name='api_hunt_sub_save'),
    path('api/ffxiv/hunt/subs/delete/', api_hunt_sub_delete,  name='api_hunt_sub_delete'),
    path('api/ffxiv/dd/log/',         api_ffxiv_dd_log_run,    name='api_ffxiv_dd_log_run'),
    path('api/ffxiv/dd/edit/',        api_ffxiv_dd_edit_run,   name='api_ffxiv_dd_edit_run'),
    path('api/ffxiv/dd/delete/',      api_ffxiv_dd_delete_run, name='api_ffxiv_dd_delete_run'),
    path('api/ffxiv/dd/admin-wipe/',  api_ffxiv_dd_admin_wipe, name='api_ffxiv_dd_admin_wipe'),
    path('ffxiv/tools/field-ops/',         ffxiv_field_ops,            name='ffxiv_field_ops'),
    path('api/ffxiv/field-ops/update/',    api_ffxiv_fo_update,        name='api_ffxiv_fo_update'),
    path('api/ffxiv/field-ops/delete/',    api_ffxiv_fo_delete,        name='api_ffxiv_fo_delete'),
    path('api/ffxiv/field-ops/admin-delete/', api_ffxiv_fo_admin_delete, name='api_ffxiv_fo_admin_delete'),
    path('ffxiv/tools/market-board/',  ffxiv_market_board, name='ffxiv_market_board'),
    path('api/ffxiv/mb/search/',       api_mb_search,      name='api_mb_search'),
    path('api/ffxiv/mb/prices/',       api_mb_prices,      name='api_mb_prices'),
    # Job Guides
    path('ffxiv/tools/job-guides/',                         ffxiv_job_guides,    name='ffxiv_job_guides'),
    path('ffxiv/tools/job-guides/<str:job_key>/',           ffxiv_job_hub,       name='ffxiv_job_hub'),
    path('ffxiv/tools/job-guides/<str:job_key>/create/',    ffxiv_guide_create,  name='ffxiv_guide_create'),
    path('ffxiv/tools/job-guides/guide/<slug:slug>/',       ffxiv_guide_detail,  name='ffxiv_guide_detail'),
    path('ffxiv/tools/job-guides/guide/<slug:slug>/edit/',  ffxiv_guide_edit,    name='ffxiv_guide_edit'),
    path('api/ffxiv/guides/<str:job_key>/create/',          api_ffxiv_guide_save,         name='api_ffxiv_guide_save'),
    path('api/ffxiv/guides/<int:guide_id>/edit/',           api_ffxiv_guide_update,       name='api_ffxiv_guide_update'),
    path('api/ffxiv/guides/<int:guide_id>/like/',           api_ffxiv_guide_like,         name='api_ffxiv_guide_like'),
    path('api/ffxiv/guides/<int:guide_id>/delete/',         api_ffxiv_guide_delete,       name='api_ffxiv_guide_delete'),
    path('api/ffxiv/guides/<int:guide_id>/hide/',           api_ffxiv_guide_hide,         name='api_ffxiv_guide_hide'),
    path('api/ffxiv/guides/<int:guide_id>/comments/',       api_ffxiv_guide_comment,      name='api_ffxiv_guide_comment'),
    path('api/ffxiv/guide-comments/<int:comment_id>/like/', api_ffxiv_guide_comment_like, name='api_ffxiv_guide_comment_like'),
    path('api/ffxiv/guide-comments/<int:comment_id>/delete/', api_ffxiv_guide_comment_delete, name='api_ffxiv_guide_comment_delete'),
    # Housing Tracker
    path('ffxiv/tools/housing/',                         ffxiv_housing,               name='ffxiv_housing'),
    path('api/ffxiv/housing/worlds/',                    api_ffxiv_housing_worlds,    name='api_ffxiv_housing_worlds'),
    path('api/ffxiv/housing/plots/<int:world_id>/',      api_ffxiv_housing_plots,     name='api_ffxiv_housing_plots'),
    path('api/ffxiv/housing/sync/',                      api_ffxiv_housing_sync,      name='api_ffxiv_housing_sync'),
    path('api/ffxiv/ocean-fishing/rsvp/', api_ffxiv_ocean_fishing_rsvp, name='api_ffxiv_ocean_fishing_rsvp'),
    path('api/ffxiv/ocean-fishing/schedule/', api_ffxiv_ocean_fishing_schedule, name='api_ffxiv_ocean_fishing_schedule'),
    path('api/ffxiv/characters/search/', api_ffxiv_search_characters, name='api_ffxiv_search_characters'),
    path('api/ffxiv/characters/link/', api_ffxiv_link_character, name='api_ffxiv_link_character'),
    path('api/ffxiv/characters/sync/', api_ffxiv_sync_character, name='api_ffxiv_sync_character'),
    path('api/ffxiv/characters/achievements-ready/', api_ffxiv_achievements_ready, name='api_ffxiv_achievements_ready'),
    path('api/ffxiv/clears/<str:content_key>/toggle/', api_ffxiv_toggle_clear, name='api_ffxiv_toggle_clear'),
    # path('enshrouded/', views.enshrouded, name='enshrouded'),
    path('icaurs/', views.icarus, name='icarus'),
    path('vrising/', views.vrising, name='vrising'),
    path('mockup/game-library/', lambda r: redirect('/library/', permanent=False)),
    path('features/', lambda r: redirect('/blog/', permanent=True), name='features'),
    path('features/<slug:slug>/', lambda r, slug: redirect(f'/blog/{slug}/', permanent=True), name='features_detail'),
    path('guides/', views.guides, name='guides'),
    path('content/', views.content, name='content'),
    path('aboutus/', views.aboutus, name='aboutus'),
    path('bot/discord/', views.bot_discord, name='bot_discord'),
    path('bot/discord/guide/', views.guide_discord, name='guide_discord'),
    path('bot/fluxer/', views.bot_fluxer, name='bot_fluxer'),
    path('bot/fluxer/guide/', views.guide_fluxer, name='guide_fluxer'),
    path('questchat/', views.questchat, name='questchat'),
    path('self-host/', views.self_host, name='self_host'),
    path('privacy/', views.privacy, name='privacy'),
    path('terms/', views.terms, name='terms'),
    path('contactus/', views.contactus, name='contactus'),
    path('faq/', views.faq, name='faq'),
    path('security/', views.security_policy, name='security_policy'),
    path('security/hall-of-fame/', views.security_hof, name='security_hof'),
    # =========================================================================
    # SITE-WIDE AUTH
    # =========================================================================
    # path('login/', ql_views.ql_login, name='site_login'),  # disabled - closed-access mode
    path('register/', ql_views.ql_register, name='site_register'),
    path('verify-email/<str:token>/', ql_views.verify_email, name='site_verify_email'),
    path('resend-verification/',      ql_views.resend_verification, name='site_resend_verification'),
    path('logout/',   ql_views.logout,      name='site_logout'),

    # Steam - optional connection (game features)
    path('auth/steam/link/',     ql_views.steam_link,          name='site_steam_link'),
    path('auth/steam/callback/', ql_views.steam_link_callback, name='site_steam_callback'),

    path("dashboard/", views.dashboard, name="dashboard"),

    # QuestLog Web (web-native, no Discord dependency)
    # casual-heroes.com/ql/ - distinct from dashboard.casual-heroes.com/questlog/
    path('', include('app.questlog_web.urls')),

    # QuestLog (Discord bot dashboard - on dashboard.casual-heroes.com)
    path('questlog/overview/', views.questlog_overview, name='questlog_overview'),
    path('questlog/login/', views.questlog_login, name='questlog_login'),
    path('questlog/creatorofthemonth/', views.creator_of_the_month_page, name='creator_of_the_month'),
    path('questlog/creatoroftheweek/', views.creator_of_the_week_page, name='creator_of_the_week'),

    # Discord auth - re-enabled for dashboard.casual-heroes.com (Discord bot dashboard)
    # Matrix SSO runs separately for casual-heroes.com/ql
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

    # Game Server Management Dashboard
    # path('questlog/guild/<str:guild_id>/game-servers/', views.game_servers, name='game_servers'),


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
    path('api/guild/<str:guild_id>/found-games/search/', views.api_found_games_search, name='api_found_games_search'),
    path('api/guild/<str:guild_id>/found-games/keywords/', views.api_found_games_keywords, name='api_found_games_keywords'),
    path('api/discovery/keywords/', views.api_discovery_network_keywords, name='api_discovery_network_keywords'),

    # RSS Feeds (standalone page)
    path('questlog/guild/<str:guild_id>/rss-feeds/', views.guild_rss_feeds, name='guild_rss_feeds'),
    # RSS Articles (member dashboard - view all articles)
    path('questlog/guild/<str:guild_id>/rss-articles/', views.guild_rss_articles, name='guild_rss_articles'),

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
    # SEC-002/003 fix: Guild ID now in URL for proper authorization
    path('api/guild/<int:guild_id>/discovery/apply/', views.api_discovery_network_apply, name='api_discovery_network_apply'),
    path('api/guild/<int:guild_id>/discovery/preferences/', views.api_discovery_network_preferences, name='api_discovery_network_preferences'),
    path('api/guild/<int:guild_id>/discovery/leave/', views.api_discovery_network_leave, name='api_discovery_network_leave'),
    path('api/guild/<int:guild_id>/discovery/rejoin/', views.api_discovery_network_rejoin, name='api_discovery_network_rejoin'),

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

    # Discovery Network Admin API Endpoints (Discovery Approvers Only)
    path('api/discovery/admin/applications', views.api_discovery_network_admin_applications, name='api_discovery_network_admin_applications'),
    path('api/discovery/admin/applications/<int:application_id>/approve', views.api_discovery_network_admin_approve, name='api_discovery_network_admin_approve'),
    path('api/discovery/admin/applications/<int:application_id>/deny', views.api_discovery_network_admin_deny, name='api_discovery_network_admin_deny'),
    path('api/discovery/admin/applications/<int:application_id>/ban', views.api_discovery_network_admin_ban, name='api_discovery_network_admin_ban'),
    path('api/discovery/admin/servers', views.api_discovery_network_admin_servers, name='api_discovery_network_admin_servers'),
    path('api/discovery/admin/servers/<str:guild_id>/kick', views.api_discovery_network_admin_kick_server, name='api_discovery_network_admin_kick_server'),
    path('api/discovery/admin/servers/<str:guild_id>/reinstate', views.api_discovery_network_admin_reinstate_server, name='api_discovery_network_admin_reinstate_server'),
    path('api/discovery/admin/users/<str:user_id_to_ban>/ban', views.api_discovery_network_admin_ban_user, name='api_discovery_network_admin_ban_user'),
    path('api/guild/<str:guild_id>/discovery/searches/<int:search_id>/delete/', views.api_game_search_config_delete, name='api_game_search_config_delete'),
    path('api/guild/<str:guild_id>/discovery/keywords/search/', views.api_igdb_keywords_search, name='api_igdb_keywords_search'),

    # RSS Feed Management
    path('api/guild/<str:guild_id>/rss/', views.api_rss_feeds_list, name='api_rss_feeds_list'),
    path('api/guild/<str:guild_id>/rss/create/', views.api_rss_feed_create, name='api_rss_feed_create'),
    path('api/guild/<str:guild_id>/rss/<int:feed_id>/', views.api_rss_feed_detail, name='api_rss_feed_detail'),
    path('api/guild/<str:guild_id>/rss/<int:feed_id>/update/', views.api_rss_feed_update, name='api_rss_feed_update'),
    path('api/guild/<str:guild_id>/rss/<int:feed_id>/delete/', views.api_rss_feed_delete, name='api_rss_feed_delete'),
    path('api/guild/<str:guild_id>/rss/<int:feed_id>/test/', views.api_rss_feed_test, name='api_rss_feed_test'),
    path('api/guild/<str:guild_id>/rss/<int:feed_id>/send-test/', views.api_rss_feed_send_test, name='api_rss_feed_send_test'),
    path('api/guild/<str:guild_id>/rss/validate-url/', views.api_rss_validate_url, name='api_rss_validate_url'),

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
    path('api/guild/<str:guild_id>/creator/clear-cotw/', views.clear_creator_of_week, name='clear_creator_of_week'),
    path('api/guild/<str:guild_id>/creator/clear-cotm/', views.clear_creator_of_month, name='clear_creator_of_month'),

    # Network Creator of the Week/Month (DISCOVERY_APPROVERS only)
    path('api/network/creator/set-cotw/', views.set_network_creator_of_week, name='set_network_creator_of_week'),
    path('api/network/creator/set-cotm/', views.set_network_creator_of_month, name='set_network_creator_of_month'),
    path('api/network/creator/clear-cotw/', views.clear_network_creator_of_week, name='clear_network_creator_of_week'),
    path('api/network/creator/clear-cotm/', views.clear_network_creator_of_month, name='clear_network_creator_of_month'),

    # YouTube OAuth Integration
    path('api/youtube/oauth/initiate/<str:guild_id>/', views.youtube_oauth_initiate, name='youtube_oauth_initiate'),
    path('api/youtube/oauth/callback/', views.youtube_oauth_callback, name='youtube_oauth_callback'),
    path('api/youtube/disconnect/<str:guild_id>/', views.youtube_disconnect, name='youtube_disconnect'),

    # Twitch OAuth Integration
    path('api/twitch/oauth/initiate/<str:guild_id>/', views.twitch_oauth_initiate, name='twitch_oauth_initiate'),
    path('api/twitch/oauth/callback/', views.twitch_oauth_callback, name='twitch_oauth_callback'),
    path('api/twitch/disconnect/<str:guild_id>/', views.twitch_disconnect, name='twitch_disconnect'),

    # Streaming Notifications Management
    path('api/guild/<str:guild_id>/streaming/config/', views.streaming_notifications_config, name='streaming_notifications_config'),
    path('api/guild/<str:guild_id>/streaming/approved/', views.approved_streamers_list, name='approved_streamers_list'),
    path('api/guild/<str:guild_id>/streaming/creators/', views.all_creators_with_streaming, name='all_creators_with_streaming'),
    path('api/guild/<str:guild_id>/streaming/approve/', views.approve_streamer, name='approve_streamer'),
    path('api/guild/<str:guild_id>/streaming/revoke/', views.revoke_streamer, name='revoke_streamer'),
    path('api/guild/<str:guild_id>/streaming/test/', views.test_streaming_notification, name='test_streaming_notification'),

    # LFG API Endpoints
    path('api/guild/<str:guild_id>/lfg/search/', views.api_lfg_search, name='api_lfg_search'),
    path('api/guild/<str:guild_id>/lfg/add/', views.api_lfg_add, name='api_lfg_add'),
    path('api/guild/<str:guild_id>/lfg/<int:game_id>/', views.api_lfg_remove, name='api_lfg_remove'),
    path('api/guild/<str:guild_id>/lfg/<int:game_id>/update/', views.api_lfg_game_update, name='api_lfg_game_update'),

    # QuestLog Network LFG subscription (Discord dashboard)
    path('api/guild/<str:guild_id>/lfg/network/', views.api_guild_network_lfg, name='api_guild_network_lfg'),

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
    path('api/guild/<str:guild_id>/lfg/browser/<int:group_id>/convert-to-thread/', views.api_lfg_convert_to_thread, name='api_lfg_convert_to_thread'),
    path('api/guild/<str:guild_id>/lfg/browser/audit-logs/', views.api_lfg_browser_audit_logs, name='api_lfg_browser_audit_logs'),
    path('api/guild/<str:guild_id>/lfg/browser-notifications/', views.api_lfg_browser_notifications, name='api_lfg_browser_notifications'),

    # =========================================================================
    # RAID MANAGEMENT ENDPOINTS
    # =========================================================================
    path('api/guild/<str:guild_id>/raids/', views.api_raid_list, name='api_raid_list'),  # GET - List raids
    path('api/guild/<str:guild_id>/raids/create/', views.api_raid_create, name='api_raid_create'),  # POST - Create raid
    path('api/guild/<str:guild_id>/raids/<int:raid_id>/', views.api_raid_detail, name='api_raid_detail'),  # GET - Raid details
    path('api/guild/<str:guild_id>/raids/<int:raid_id>/signup/', views.api_raid_signup, name='api_raid_signup'),  # POST - Sign up
    path('api/guild/<str:guild_id>/raids/<int:raid_id>/leave/', views.api_raid_leave, name='api_raid_leave'),  # DELETE - Leave raid

    # CSP Violation Reporting
    path('csp-violations/', views.csp_violation_report, name='csp_violations'),

    # =========================================================================
    # UNIFIED DISCORD DASHBOARD ALIASES
    # /ql/dashboard/discord/ is the guild list (same as /questlog/)
    # /ql/dashboard/discord/<guild_id>/ mirrors /questlog/guild/<guild_id>/
    # Same views, same templates - just accessible from the QuestLog site nav.
    # API endpoints (/api/guild/<id>/...) don't need aliasing - JS calls them directly.
    # =========================================================================
    path('dashboard/discord/',                                      views.questlog_dashboard,       name='ql_discord_dashboard'),
    path('dashboard/discord/<str:guild_id>/',                   views.guild_dashboard,          name='ql_discord_guild_dashboard'),
    path('dashboard/discord/<str:guild_id>/xp/',                views.guild_xp,                 name='ql_discord_guild_xp'),
    path('dashboard/discord/<str:guild_id>/welcome/',           views.guild_welcome,            name='ql_discord_guild_welcome'),
    path('dashboard/discord/<str:guild_id>/levelup/',           views.guild_levelup,            name='ql_discord_guild_levelup'),
    path('dashboard/discord/<str:guild_id>/moderation/',        views.guild_moderation,         name='ql_discord_guild_moderation'),
    path('dashboard/discord/<str:guild_id>/moderation/settings/', views.guild_moderation_settings, name='ql_discord_guild_moderation_settings'),
    path('dashboard/discord/<str:guild_id>/roles/',             views.guild_roles,              name='ql_discord_guild_roles'),
    path('dashboard/discord/<str:guild_id>/reaction-roles/',    views.guild_reaction_roles,     name='ql_discord_guild_reaction_roles'),
    path('dashboard/discord/<str:guild_id>/verification/',      views.guild_verification,       name='ql_discord_guild_verification'),
    path('dashboard/discord/<str:guild_id>/raffles/',           views.guild_raffles,            name='ql_discord_guild_raffles'),
    path('dashboard/discord/<str:guild_id>/raffle-browser/',    views.guild_raffle_browser,     name='ql_discord_guild_raffle_browser'),
    path('dashboard/discord/<str:guild_id>/audit/',             views.guild_audit_logs,         name='ql_discord_guild_audit'),
    path('dashboard/discord/<str:guild_id>/templates/',         views.guild_templates,          name='ql_discord_guild_templates'),
    path('dashboard/discord/<str:guild_id>/messages/',          views.guild_messages,           name='ql_discord_guild_messages'),
    path('dashboard/discord/<str:guild_id>/settings/',          views.guild_settings,           name='ql_discord_guild_settings'),
    path('dashboard/discord/<str:guild_id>/rss-feeds/',         views.guild_rss_feeds,          name='ql_discord_guild_rss_feeds'),
    path('dashboard/discord/<str:guild_id>/rss-articles/',      views.guild_rss_articles,       name='ql_discord_guild_rss_articles'),
    path('dashboard/discord/<str:guild_id>/lfg/',               views.guild_lfg,                name='ql_discord_guild_lfg'),
    path('dashboard/discord/<str:guild_id>/lfg/browser/',       views.guild_lfg_browser,        name='ql_discord_guild_lfg_browser'),
    path('dashboard/discord/<str:guild_id>/attendance/',        views.guild_attendance,         name='ql_discord_guild_attendance'),
    path('dashboard/discord/<str:guild_id>/lfg/calendar/',     views.guild_lfg_calendar,       name='ql_discord_guild_lfg_calendar'),
    path('dashboard/discord/<str:guild_id>/trackers/',          views.guild_trackers,           name='ql_discord_guild_trackers'),
    path('dashboard/discord/<str:guild_id>/discovery/',         views.guild_discovery,          name='ql_discord_guild_discovery'),
    path('dashboard/discord/<str:guild_id>/leaderboards/',      views.guild_leaderboards,       name='ql_discord_guild_leaderboards'),
    path('dashboard/discord/<str:guild_id>/profile/',           views.member_profile,           name='ql_discord_guild_profile'),
    path('dashboard/discord/<str:guild_id>/flair-management/',  views.flair_management,         name='ql_discord_guild_flair_management'),
    path('dashboard/discord/<str:guild_id>/featured-creators/', views.guild_featured_creators,  name='ql_discord_guild_featured_creators'),
    path('dashboard/discord/<str:guild_id>/bridge/',            views.guild_bridge,             name='ql_discord_guild_bridge'),
    # Quest Control (Discord)
    path('dashboard/discord/<str:guild_id>/quest-control/',          views.guild_quest_control,          name='ql_discord_guild_quest_control'),
    # Community Spotlight (Discord)
    path('dashboard/discord/<str:guild_id>/spotlight/',              views.guild_spotlight,              name='ql_discord_guild_spotlight'),
    # Live Alerts (Discord)
    path('dashboard/discord/<str:guild_id>/live-alerts/',
         discord_guild_live_alerts,                                      name='ql_discord_guild_live_alerts'),
    # Live Alerts API (Discord)
    path('api/discord/<str:guild_id>/streamer-subs/',
         api_discord_guild_streamer_subs,                                name='api_discord_guild_streamer_subs'),
    path('api/discord/<str:guild_id>/streamer-subs/<int:sub_id>/',
         api_discord_guild_streamer_sub_detail,                          name='api_discord_guild_streamer_sub_detail'),
    # Bridge API (guild-scoped, Discord auth)
    path('api/discord/<str:guild_id>/bridges/',                 views.api_discord_guild_bridges,      name='api_discord_guild_bridges'),
    path('api/discord/<str:guild_id>/bridges/<int:bridge_id>/', views.api_discord_guild_bridge_detail, name='api_discord_guild_bridge_detail'),
]
