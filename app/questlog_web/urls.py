# QuestLog Web URLs
# These routes are for casual-heroes.com/ql/

from django.urls import path
from django.shortcuts import redirect

from .views_auth import (
    ql_login, ql_register, ql_admin_login,
    verify_email, resend_verification, check_email, logout,
    password_reset_request, password_reset_confirm,
    steam_link, steam_link_callback, steam_unlink,
    discord_link, discord_link_callback, discord_unlink,
    fluxer_link, fluxer_link_callback, fluxer_unlink,
    twitch_oauth_initiate, twitch_oauth_callback, twitch_disconnect,
    youtube_oauth_initiate, youtube_oauth_callback, youtube_disconnect,
    kick_oauth_initiate, kick_oauth_callback, kick_disconnect,
    api_check_invite,
    matrix_link_initiate, matrix_link_verify, matrix_unlink,
)
from .views_pages import (
    home,
    lfg_browse, lfg_calendar, lfg_create, lfg_my_groups, lfg_group_detail,
    lfg_join, lfg_leave, lfg_edit, lfg_update_member, lfg_delete, lfg_kick, lfg_set_co_leader,
    network, network_leaderboard, api_leaderboard_top, games, creators, articles, gamers,
    communities, community_register, community_detail, community_guidelines,
    profile, profile_edit, creator_register, settings, hero_shop,
    game_servers_ql,
    api_active_poll, api_poll_vote,
    giveaways_page,
    fluxer_member_portal,
    fluxer_guild_member_profile,
    fluxer_guild_member_raffles,
    api_fluxer_member_raffles,
    api_fluxer_member_raffle_enter,
    fluxer_guild_member_rss,
    fluxer_guild_member_games,
    fluxer_guild_member_flairs,
    api_fluxer_guild_flair_buy,
    api_fluxer_guild_flair_equip,
    api_fluxer_guild_flair_unequip,
    fluxer_guild_member_lfg_browse,
    api_fluxer_member_lfg_join,
    api_fluxer_member_lfg_leave,
    api_fluxer_member_lfg_groups,
    api_fluxer_member_lfg_group_delete,
)
from .views_internal import api_internal_bot_config, api_internal_broadcast_lfg, api_internal_guild_names, api_internal_bridge_relay, api_internal_bridge_pending, api_internal_bridge_message_map, api_internal_bridge_thread_map, api_internal_bridge_reaction, api_internal_bridge_pending_reactions, api_internal_bridge_delete, api_internal_bridge_pending_deletions, api_internal_guild_roles, api_internal_guild_sync, api_internal_guild_remove, api_internal_guild_actions_pending, api_internal_guild_action_done, api_bridge_media_proxy
from .views_billing import hero_subscribe, hero_success, hero_return, api_hero_checkout, api_stripe_webhook, hero_portal
from .views_bot_dashboard import (
    unified_dashboard,
    fluxer_dashboard, fluxer_guild_dashboard, api_fluxer_guild_settings,
    api_bot_dashboard_configs, api_bot_dashboard_config_detail,
    fluxer_guild_xp, fluxer_guild_welcome, fluxer_guild_moderation,
    fluxer_guild_lfg, fluxer_guild_settings_page, fluxer_guild_bridge,
    fluxer_guild_verification, fluxer_guild_reaction_roles, fluxer_guild_trackers,
    fluxer_guild_live_alerts,
    fluxer_guild_audit, fluxer_guild_roles, fluxer_guild_messages,
    fluxer_guild_templates_page, fluxer_guild_discovery, fluxer_guild_raffles,
    fluxer_guild_flair,
    fluxer_guild_lfg_attendance, fluxer_guild_lfg_calendar,
    fluxer_guild_soon,
    # Fluxer guild API endpoints
    api_fluxer_reaction_roles, api_fluxer_reaction_role_detail,
    api_fluxer_guild_raffles, api_fluxer_guild_raffle_pick, api_fluxer_guild_raffle_detail,
    api_fluxer_guild_bridges, api_fluxer_guild_bridge_detail,
    api_fluxer_guild_channels, api_fluxer_guild_roles,
    api_fluxer_guild_trackers, api_fluxer_guild_tracker_detail,
    api_fluxer_discovery_rss, api_fluxer_discovery_rss_detail,
    api_fluxer_discovery_rss_force_send, api_fluxer_discovery_rss_preview,
    api_fluxer_guild_roles_list, api_fluxer_guild_roles_actions,
    api_fluxer_guild_role_action, api_fluxer_guild_role_create,
    api_fluxer_guild_role_bulk_create, api_fluxer_guild_role_import,
    api_fluxer_guild_templates_list,
    api_fluxer_guild_template_create, api_fluxer_guild_template_detail,
    api_fluxer_guild_template_apply,
    api_fluxer_guild_members,
    # New real API endpoints
    api_fluxer_guild_lfg_games, api_fluxer_guild_lfg_game_detail,
    api_fluxer_igdb_search,
    api_fluxer_guild_lfg_config, api_fluxer_guild_lfg_stats,
    api_fluxer_guild_lfg_blacklist, api_fluxer_guild_lfg_blacklist_action,
    api_fluxer_guild_warnings, api_fluxer_guild_warning_pardon,
    api_fluxer_guild_welcome_config, api_fluxer_guild_welcome_test,
    api_fluxer_guild_flairs, api_fluxer_guild_flair_create, api_fluxer_guild_flair_detail,
    # Level roles
    api_fluxer_guild_level_roles, api_fluxer_guild_level_role_detail, api_fluxer_guild_level_roles_bulk,
    api_fluxer_guild_member_xp,
    api_fluxer_guild_levelup_config,
    api_fluxer_guild_xp_boosts, api_fluxer_guild_xp_boost_detail,
    api_fluxer_guild_live_info,
    # Attendance
    api_fluxer_guild_lfg_attendance, api_fluxer_guild_attendance_export,
    # Dashboard browse + group management APIs
    fluxer_guild_lfg_browse_admin,
    api_fluxer_guild_lfg_groups, api_fluxer_guild_lfg_group_detail, api_fluxer_guild_lfg_group_kick,
    # Live Alerts - streamer subscriptions
    api_fluxer_guild_streamer_subs, api_fluxer_guild_streamer_sub_detail,
    # Game discovery (IGDB-based)
    api_fluxer_guild_game_search_configs, api_fluxer_guild_game_search_config_detail,
    api_fluxer_guild_found_games, api_fluxer_guild_igdb_keywords,
    api_fluxer_guild_game_discovery_settings,
    api_fluxer_guild_force_check_games,
    api_fluxer_messages_send_embed,
)
from .views_matrix_dashboard import (
    matrix_dashboard, matrix_guild_dashboard,
    matrix_guild_rooms, matrix_guild_members, matrix_guild_xp,
    matrix_guild_moderation, matrix_guild_welcome, matrix_guild_ban_lists,
    matrix_guild_rss, matrix_guild_messages, matrix_guild_settings,
    matrix_guild_audit, matrix_guild_verification, matrix_guild_bridge,
    api_matrix_space_settings, api_matrix_rooms, api_matrix_room_create,
    api_matrix_room_detail, api_matrix_members, api_matrix_member_kick,
    api_matrix_member_ban, api_matrix_member_invite, api_matrix_member_powerlevel,
    api_matrix_warnings, api_matrix_warning_pardon,
    api_matrix_welcome_config, api_matrix_xp_settings,
    api_matrix_xp_leaderboard, api_matrix_xp_boosts, api_matrix_xp_boost_detail,
    api_matrix_level_roles, api_matrix_level_role_detail,
    api_matrix_rss, api_matrix_rss_detail,
    api_matrix_ban_lists, api_matrix_ban_list_detail,
    api_matrix_ban_list_entries, api_matrix_ban_list_entry_detail,
    api_matrix_send_message, api_matrix_sync_status,
    api_matrix_action_history,
    api_matrix_audit_log,
    api_matrix_propagate_audit,
    api_matrix_bridges, api_matrix_bridge_detail,
)
from .views_admin import (
    admin_verify_pin, admin_panel,
    api_admin_stats,
    api_admin_lfg_games, api_admin_lfg_game_detail,
    api_admin_communities, api_admin_community_action,
    api_admin_creators, api_admin_creator_action,
    api_admin_rotate_cotw, api_admin_rotate_cotm,
    api_admin_steam_searches, api_admin_steam_search_detail, api_admin_run_steam_search,
    api_admin_found_games, api_admin_found_game_action,
    api_admin_raffles, api_admin_raffle_detail, api_admin_raffle_pick_winners,
    api_admin_rss_feeds, api_admin_rss_feed_detail, api_admin_validate_rss,
    api_admin_rss_feed_fetch_now,
    api_admin_users, api_admin_user_action,
    api_admin_audit_log,
    api_admin_posts, api_admin_post_action, api_admin_comment_action,
    admin_games_tracker, api_admin_site_activity_games, api_admin_site_activity_roles,
    api_admin_maintenance, api_admin_maintenance_status,
    api_admin_toggle_logins, api_admin_logins_status,
    api_admin_flairs, api_admin_flair_detail,
    api_admin_rank_titles, api_admin_rank_title_detail,
    api_admin_xp_leaderboard,
    api_admin_server_polls, api_admin_server_poll_detail,
    api_admin_server_poll_option, api_admin_server_poll_option_detail,
    api_admin_server_poll_declare_winner,
    api_admin_steam_game_search,
    api_admin_giveaways, api_admin_giveaway_detail,
    api_admin_giveaway_launch, api_admin_giveaway_close, api_admin_giveaway_pick_winner,
    api_admin_fluxer_webhooks, api_admin_fluxer_webhook_detail, api_admin_fluxer_webhook_test,
    api_admin_fluxer_guilds,
    api_admin_fluxer_subscribers, api_admin_fluxer_subscriber_detail,
    api_admin_fluxer_guild_detail, api_admin_fluxer_guild_channels,
    api_admin_discord_guild_channels,
    api_admin_matrix_spaces, api_admin_matrix_space_rooms,
    api_admin_invite_codes, api_admin_invite_code_detail, api_admin_invite_codes_bulk_revoke,
    api_admin_hero_subscribers,
    api_admin_bot_network,
    api_admin_bridge_configs, api_admin_bridge_config_detail,
    api_admin_emoji, api_admin_emoji_detail,
)
from .views_discovery import (
    api_lfg_list, api_lfg_detail,
    api_communities, api_community_detail, api_creators, api_games, api_articles,
    api_igdb_search, api_gamers,
    api_lfg_broadcast_network,
    api_lfg_community_guilds,
    api_lfg_fluxer_edit, api_lfg_fluxer_close, api_lfg_fluxer_mark_full,
    api_lfg_fluxer_guild_close,
    api_lfg_fluxer_guild_edit, api_lfg_fluxer_guild_update_member,
    api_lfg_fluxer_guild_reopen, api_lfg_fluxer_guild_my_closed,
    api_lfg_fluxer_guild_join, api_lfg_fluxer_guild_leave,
    api_community_leave_network, api_community_rejoin_network, api_community_set_primary,
)
from .views_uploads import (
    api_upload_image, api_upload_avatar, api_upload_banner,
    api_upload_community_icon, api_upload_community_banner,
    api_gif_search, api_gif_trending,
    api_custom_emoji_list,
)
from .views_social import (
    api_block, api_block_list,
    api_follow, api_followers, api_following, api_follow_status,
    api_posts, _get_feed_posts, api_post_detail, api_post_pin, api_user_posts, api_global_posts,
    api_recent_activity, _get_recent_activity,
    api_post_like, api_post_share,
    api_post_edit, api_post_edit_history,
    api_comments, _get_comments, api_comment_detail, api_comment_like,
    api_notifications, api_notification_count, api_notifications_mark_read, api_notification_mark_read,
    api_notifications_clear_all,
    api_giveaways, api_giveaway_enter,
    post_detail_page,
)
from .views_profile import (
    api_profile_update, api_validate_embed,
    public_profile, public_profile_followers, public_profile_following, social_feed,
    api_privacy_data_summary, api_privacy_export, api_privacy_delete,
    api_pull_avatar, api_save_steam_prefs, api_save_user_prefs, api_invite_link,
    api_me_now_playing, api_user_now_playing,
    api_flairs, api_flair_buy, api_flair_equip,
)

urlpatterns = [
    # Home
    path('', home, name='questlog_web_home'),

    # Auth
    # /ql/login/ is blocked by MaintenanceMiddleware during closed-access mode.
    # Admins use /ql/admin-login/ instead. Route kept active so URL name resolves.
    path('login/', ql_login, name='questlog_web_login'),
    path('earlyaccess/login/', ql_login, {'early_access_bypass': True}, name='questlog_web_earlyaccess_login'),
    path('admin-login/', ql_admin_login, name='questlog_web_admin_login'),
    path('register/', ql_register, name='questlog_web_register'),
    path('api/register/check-invite/', api_check_invite, name='questlog_web_api_check_invite'),
    path('verify-email/<str:token>/', verify_email, name='questlog_web_verify_email'),
    path('resend-verification/',      resend_verification, name='questlog_web_resend_verification'),
    path('logout/',   logout,      name='questlog_web_logout'),
    path('password-reset/',                          password_reset_request, name='questlog_web_password_reset'),
    path('password-reset/confirm/<str:token>/',      password_reset_confirm, name='questlog_web_password_reset_confirm'),

    # Steam — optional connection (unlocks game-tracking features)
    path('auth/steam/link/',     steam_link,          name='questlog_web_steam_link'),
    path('auth/steam/callback/', steam_link_callback, name='questlog_web_steam_callback'),
    path('auth/steam/unlink/',   steam_unlink,        name='questlog_web_steam_unlink'),

    # Discord — optional account linking
    path('auth/discord/link/',          discord_link,          name='questlog_web_discord_link'),
    path('auth/discord/link/callback/', discord_link_callback, name='questlog_web_discord_link_callback'),
    path('auth/discord/unlink/',        discord_unlink,        name='questlog_web_discord_unlink'),

    # Fluxer — optional account linking
    path('auth/fluxer/link/',          fluxer_link,          name='questlog_web_fluxer_link'),
    path('auth/fluxer/link/callback/', fluxer_link_callback, name='questlog_web_fluxer_link_callback'),
    path('auth/fluxer/unlink/',        fluxer_unlink,        name='questlog_web_fluxer_unlink'),

    # Twitch OAuth — creator profile integration
    path('auth/twitch/link/',     twitch_oauth_initiate, name='questlog_web_twitch_link'),
    path('auth/twitch/callback/', twitch_oauth_callback, name='questlog_web_twitch_callback'),
    path('auth/twitch/unlink/',   twitch_disconnect,     name='questlog_web_twitch_unlink'),

    # YouTube OAuth — creator profile integration
    path('auth/youtube/link/',     youtube_oauth_initiate, name='questlog_web_youtube_link'),
    path('auth/youtube/callback/', youtube_oauth_callback, name='questlog_web_youtube_callback'),
    path('auth/youtube/unlink/',   youtube_disconnect,     name='questlog_web_youtube_unlink'),

    # Kick OAuth — creator profile integration
    path('auth/kick/link/',     kick_oauth_initiate, name='questlog_web_kick_link'),
    path('auth/kick/callback/', kick_oauth_callback, name='questlog_web_kick_callback'),
    path('auth/kick/unlink/',   kick_disconnect,     name='questlog_web_kick_unlink'),

    # Matrix account linking (MAS OAuth)
    path('auth/matrix/link/',     matrix_link_initiate, name='questlog_web_matrix_link'),
    path('auth/matrix/callback/', matrix_link_verify,   name='questlog_web_matrix_link_verify'),
    path('auth/matrix/unlink/',   matrix_unlink,        name='questlog_web_matrix_unlink'),

    # Fluxer member-facing pages
    path('fluxer/<str:guild_id>/',          fluxer_member_portal,          name='questlog_web_fluxer_member_portal'),
    path('fluxer/<str:guild_id>/profile/',  fluxer_guild_member_profile,   name='questlog_web_fluxer_member_profile'),
    path('fluxer/<str:guild_id>/raffles/',  fluxer_guild_member_raffles,   name='questlog_web_fluxer_member_raffles'),
    path('fluxer/<str:guild_id>/rss/',      fluxer_guild_member_rss,       name='questlog_web_fluxer_member_rss'),
    path('fluxer/<str:guild_id>/games/',    fluxer_guild_member_games,     name='questlog_web_fluxer_member_games'),
    path('fluxer/<str:guild_id>/flairs/',        fluxer_guild_member_flairs,       name='questlog_web_fluxer_member_flairs'),
    path('fluxer/<str:guild_id>/lfg/browse/',   fluxer_guild_member_lfg_browse,   name='questlog_web_fluxer_member_lfg_browse'),
    # Fluxer guild flair store APIs
    path('api/fluxer/<str:guild_id>/flairs/<int:flair_id>/buy/',     api_fluxer_guild_flair_buy,     name='questlog_web_api_fluxer_guild_flair_buy'),
    path('api/fluxer/<str:guild_id>/flairs/<int:flair_id>/equip/',   api_fluxer_guild_flair_equip,   name='questlog_web_api_fluxer_guild_flair_equip'),
    path('api/fluxer/<str:guild_id>/flairs/<int:flair_id>/unequip/', api_fluxer_guild_flair_unequip, name='questlog_web_api_fluxer_guild_flair_unequip'),
    # Fluxer member APIs
    path('api/fluxer/<str:guild_id>/raffles/',                       api_fluxer_member_raffles,      name='questlog_web_api_fluxer_member_raffles'),
    path('api/fluxer/<str:guild_id>/raffles/<int:raffle_id>/enter/', api_fluxer_member_raffle_enter, name='questlog_web_api_fluxer_member_raffle_enter'),
    path('api/fluxer/<str:guild_id>/lfg/groups/',                     api_fluxer_member_lfg_groups,       name='questlog_web_api_fluxer_member_lfg_groups'),
    path('api/fluxer/<str:guild_id>/lfg/<int:group_id>/',            api_fluxer_member_lfg_group_delete, name='questlog_web_api_fluxer_member_lfg_group_delete'),
    path('api/fluxer/<str:guild_id>/lfg/<int:group_id>/join/',       api_fluxer_member_lfg_join,         name='questlog_web_api_fluxer_member_lfg_join'),
    path('api/fluxer/<str:guild_id>/lfg/<int:group_id>/leave/',      api_fluxer_member_lfg_leave,        name='questlog_web_api_fluxer_member_lfg_leave'),

    # LFG
    path('lfg/', lfg_browse, name='questlog_web_lfg_browse'),
    path('lfg/calendar/', lfg_calendar, name='questlog_web_lfg_calendar'),
    path('lfg/create/', lfg_create, name='questlog_web_lfg_create'),
    path('lfg/my-groups/', lfg_my_groups, name='questlog_web_lfg_my_groups'),
    path('lfg/<int:group_id>/', lfg_group_detail, name='questlog_web_lfg_detail'),
    path('lfg/<int:group_id>/join/',                          lfg_join,          name='questlog_web_lfg_join'),
    path('lfg/<int:group_id>/leave/',                         lfg_leave,         name='questlog_web_lfg_leave'),
    path('lfg/<int:group_id>/edit/',                          lfg_edit,          name='questlog_web_lfg_edit'),
    path('lfg/<int:group_id>/update-member/',                 lfg_update_member, name='questlog_web_lfg_update_member'),
    path('lfg/<int:group_id>/delete/',                        lfg_delete,        name='questlog_web_lfg_delete'),
    path('lfg/<int:group_id>/kick/<int:user_id>/',            lfg_kick,          name='questlog_web_lfg_kick'),
    path('lfg/<int:group_id>/set-co-leaders/',                lfg_set_co_leader, name='questlog_web_lfg_set_co_leader'),

    # Discovery
    path('network/', network, name='questlog_web_network'),
    path('leaderboard/', network_leaderboard, name='questlog_web_leaderboard'),
    path('api/leaderboard/top/', api_leaderboard_top, name='questlog_web_api_leaderboard_top'),
    path('games/', games, name='questlog_web_games'),
    path('creators/', creators, name='questlog_web_creators'),
    path('articles/', articles, name='questlog_web_articles'),
    path('gamers/', gamers, name='questlog_web_gamers'),

    # Communities
    path('communities/', communities, name='questlog_web_communities'),
    path('communities/register/', community_register, name='questlog_web_community_register'),
    path('communities/<int:community_id>/', community_detail, name='questlog_web_community_detail'),
    path('community-guidelines/', community_guidelines, name='questlog_web_community_guidelines'),

    # Profile
    path('profile/', profile, name='questlog_web_profile'),
    path('profile/edit/', profile_edit, name='questlog_web_profile_edit'),
    path('shop/', hero_shop, name='questlog_web_shop'),
    path('creator/register/', creator_register, name='questlog_web_creator_register'),
    path('settings/', settings, name='questlog_web_settings'),
    path('gameservers/', game_servers_ql, name='questlog_web_gameservers'),

    # Admin (site admin only - multi-layer security)
    path('admin/', admin_panel, name='questlog_web_admin'),
    path('admin/verify/', admin_verify_pin, name='questlog_web_admin_verify'),

    # API endpoints for AJAX
    path('api/lfg/', api_lfg_list, name='questlog_web_api_lfg'),
    path('api/lfg/<int:group_id>/', api_lfg_detail, name='questlog_web_api_lfg_detail'),
    path('api/lfg/<int:group_id>/broadcast-network/', api_lfg_broadcast_network, name='questlog_web_api_lfg_broadcast'),
    path('api/lfg/community-guilds/', api_lfg_community_guilds, name='questlog_web_api_lfg_community_guilds'),

    # Fluxer LFG management (requires linked Fluxer account)
    path('api/lfg/fluxer/<int:post_id>/edit/',            api_lfg_fluxer_edit,        name='questlog_web_api_lfg_fluxer_edit'),
    path('api/lfg/fluxer/<int:post_id>/close/',           api_lfg_fluxer_close,       name='questlog_web_api_lfg_fluxer_close'),
    path('api/lfg/fluxer/<int:post_id>/mark-full/',       api_lfg_fluxer_mark_full,   name='questlog_web_api_lfg_fluxer_mark_full'),
    path('api/lfg/fluxer-guild/<int:group_id>/close/',         api_lfg_fluxer_guild_close,         name='questlog_web_api_lfg_fluxer_guild_close'),
    path('api/lfg/fluxer-guild/<int:group_id>/edit/',          api_lfg_fluxer_guild_edit,          name='questlog_web_api_lfg_fluxer_guild_edit'),
    path('api/lfg/fluxer-guild/<int:group_id>/update-member/', api_lfg_fluxer_guild_update_member, name='questlog_web_api_lfg_fluxer_guild_update_member'),
    path('api/lfg/fluxer-guild/<int:group_id>/reopen/',        api_lfg_fluxer_guild_reopen,        name='questlog_web_api_lfg_fluxer_guild_reopen'),
    path('api/lfg/fluxer-guild/<int:group_id>/join/',         api_lfg_fluxer_guild_join,          name='questlog_web_api_lfg_fluxer_guild_join'),
    path('api/lfg/fluxer-guild/<int:group_id>/leave/',        api_lfg_fluxer_guild_leave,         name='questlog_web_api_lfg_fluxer_guild_leave'),
    path('api/lfg/fluxer-guild/my-closed/',                    api_lfg_fluxer_guild_my_closed,     name='questlog_web_api_lfg_fluxer_guild_my_closed'),
    path('api/communities/', api_communities, name='questlog_web_api_communities'),
    path('api/communities/<int:community_id>/', api_community_detail, name='questlog_web_api_community_detail'),
    path('api/communities/<int:community_id>/leave-network/', api_community_leave_network, name='questlog_web_api_community_leave_network'),
    path('api/communities/<int:community_id>/rejoin-network/', api_community_rejoin_network, name='questlog_web_api_community_rejoin_network'),
    path('api/communities/<int:community_id>/set-primary/', api_community_set_primary, name='questlog_web_api_community_set_primary'),
    path('api/creators/', api_creators, name='questlog_web_api_creators'),
    path('api/games/', api_games, name='questlog_web_api_games'),
    path('api/igdb/search/', api_igdb_search, name='questlog_web_api_igdb_search'),
    path('api/articles/', api_articles, name='questlog_web_api_articles'),
    path('api/gamers/', api_gamers, name='questlog_web_api_gamers'),

    # Admin API endpoints
    path('api/admin/stats/', api_admin_stats, name='questlog_web_api_admin_stats'),

    # Admin: LFG Game Configs
    path('api/admin/lfg-games/', api_admin_lfg_games, name='questlog_web_api_admin_lfg_games'),
    path('api/admin/lfg-games/<int:game_id>/', api_admin_lfg_game_detail, name='questlog_web_api_admin_lfg_game_detail'),

    # Admin: Communities
    path('api/admin/communities/', api_admin_communities, name='questlog_web_api_admin_communities'),
    path('api/admin/communities/<int:community_id>/action/', api_admin_community_action, name='questlog_web_api_admin_community_action'),

    # Admin: Creators + COTW/COTM
    path('api/admin/creators/', api_admin_creators, name='questlog_web_api_admin_creators'),
    path('api/admin/creators/<int:creator_id>/action/', api_admin_creator_action, name='questlog_web_api_admin_creator_action'),
    path('api/admin/creators/rotate-cotw/', api_admin_rotate_cotw, name='questlog_web_api_admin_rotate_cotw'),
    path('api/admin/creators/rotate-cotm/', api_admin_rotate_cotm, name='questlog_web_api_admin_rotate_cotm'),

    # Admin: Steam Search Configs
    path('api/admin/steam-searches/', api_admin_steam_searches, name='questlog_web_api_admin_steam_searches'),
    path('api/admin/steam-searches/<int:search_id>/', api_admin_steam_search_detail, name='questlog_web_api_admin_steam_search_detail'),
    path('api/admin/steam-searches/<int:search_id>/run/', api_admin_run_steam_search, name='questlog_web_api_admin_run_steam_search'),

    # Admin: Found Games
    path('api/admin/found-games/', api_admin_found_games, name='questlog_web_api_admin_found_games'),
    path('api/admin/found-games/<int:game_id>/action/', api_admin_found_game_action, name='questlog_web_api_admin_found_game_action'),

    # Admin: Raffles
    path('api/admin/raffles/', api_admin_raffles, name='questlog_web_api_admin_raffles'),
    path('api/admin/raffles/<int:raffle_id>/', api_admin_raffle_detail, name='questlog_web_api_admin_raffle_detail'),
    path('api/admin/raffles/<int:raffle_id>/pick-winners/', api_admin_raffle_pick_winners, name='questlog_web_api_admin_raffle_pick'),

    # Admin: RSS Feeds
    path('api/admin/rss-feeds/', api_admin_rss_feeds, name='questlog_web_api_admin_rss_feeds'),
    path('api/admin/rss-feeds/validate/', api_admin_validate_rss, name='questlog_web_api_admin_rss_validate'),
    path('api/admin/rss-feeds/<int:feed_id>/', api_admin_rss_feed_detail, name='questlog_web_api_admin_rss_feed_detail'),
    path('api/admin/rss-feeds/<int:feed_id>/fetch-now/', api_admin_rss_feed_fetch_now, name='questlog_web_api_admin_rss_fetch_now'),

    # Admin: Users
    path('api/admin/users/', api_admin_users, name='questlog_web_api_admin_users'),
    path('api/admin/users/<int:user_id>/action/', api_admin_user_action, name='questlog_web_api_admin_user_action'),

    # Admin: Audit Log
    path('api/admin/audit-log/', api_admin_audit_log, name='questlog_web_api_admin_audit_log'),

    # =========================================================================
    # SOCIAL LAYER (QuestLog Network)
    # =========================================================================

    # Public Profiles
    path('u/<str:username>/', public_profile, name='questlog_web_public_profile'),
    path('u/<str:username>/followers/', public_profile_followers, name='questlog_web_public_profile_followers'),
    path('u/<str:username>/following/', public_profile_following, name='questlog_web_public_profile_following'),

    # Social Feed
    path('feed/', social_feed, name='questlog_web_feed'),
    path('post/<str:public_id>/', post_detail_page, name='questlog_web_post_detail'),

    # Follow API
    path('api/follow/<int:user_id>/', api_follow, name='questlog_web_api_follow'),
    path('api/followers/<int:user_id>/', api_followers, name='questlog_web_api_followers'),
    path('api/following/<int:user_id>/', api_following, name='questlog_web_api_following'),
    path('api/follow-status/<int:user_id>/', api_follow_status, name='questlog_web_api_follow_status'),

    # Post API
    path('api/posts/', api_posts, name='questlog_web_api_posts'),
    path('api/posts/global/', api_global_posts, name='questlog_web_api_global_posts'),
    path('api/posts/<int:post_id>/', api_post_detail, name='questlog_web_api_post_detail'),
    path('api/posts/user/<int:user_id>/', api_user_posts, name='questlog_web_api_user_posts'),

    # Home Activity API
    path('api/activity/', api_recent_activity, name='questlog_web_api_activity'),

    # Like API
    path('api/posts/<int:post_id>/pin/', api_post_pin, name='questlog_web_api_post_pin'),
    path('api/posts/<int:post_id>/like/', api_post_like, name='questlog_web_api_post_like'),
    path('api/posts/<int:post_id>/edit/', api_post_edit, name='questlog_web_api_post_edit'),
    path('api/posts/<int:post_id>/edit-history/', api_post_edit_history, name='questlog_web_api_post_edit_history'),

    # Share API (HP tracking)
    path('api/posts/<int:post_id>/share/', api_post_share, name='questlog_web_api_post_share'),

    # Comment API
    path('api/posts/<int:post_id>/comments/', api_comments, name='questlog_web_api_comments'),
    path('api/comments/<int:comment_id>/', api_comment_detail, name='questlog_web_api_comment_detail'),
    path('api/comments/<int:comment_id>/like/', api_comment_like, name='questlog_web_api_comment_like'),

    # Image Upload API
    path('api/upload/image/', api_upload_image, name='questlog_web_api_upload_image'),
    path('api/upload/avatar/', api_upload_avatar, name='questlog_web_api_upload_avatar'),
    path('api/upload/banner/', api_upload_banner, name='questlog_web_api_upload_banner'),
    path('api/upload/community/<int:community_id>/icon/', api_upload_community_icon, name='questlog_web_api_upload_community_icon'),
    path('api/upload/community/<int:community_id>/banner/', api_upload_community_banner, name='questlog_web_api_upload_community_banner'),

    # GIF Search API (Tenor proxy)
    path('api/gifs/search/', api_gif_search, name='questlog_web_api_gif_search'),
    path('api/gifs/trending/', api_gif_trending, name='questlog_web_api_gif_trending'),
    path('api/emoji/', api_custom_emoji_list, name='questlog_web_api_custom_emoji'),

    # Notification API
    path('api/notifications/', api_notifications, name='questlog_web_api_notifications'),
    path('api/notifications/count/', api_notification_count, name='questlog_web_api_notification_count'),
    path('api/notifications/read/', api_notifications_mark_read, name='questlog_web_api_notifications_read'),
    path('api/notifications/clear/', api_notifications_clear_all, name='questlog_web_api_notifications_clear'),
    path('api/notifications/<int:notification_id>/read/', api_notification_mark_read, name='questlog_web_api_notification_read'),

    # Block API
    path('api/block/<int:user_id>/', api_block, name='questlog_web_api_block'),
    path('api/blocks/', api_block_list, name='questlog_web_api_block_list'),

    # Profile Update API
    path('api/profile/update/', api_profile_update, name='questlog_web_api_profile_update'),
    path('api/profile/pull-avatar/', api_pull_avatar, name='questlog_web_api_pull_avatar'),
    path('api/profile/steam-prefs/', api_save_steam_prefs, name='questlog_web_api_steam_prefs'),
    path('api/me/now-playing/', api_me_now_playing, name='questlog_web_api_now_playing'),
    path('api/u/<str:username>/now-playing/', api_user_now_playing, name='questlog_web_api_user_now_playing'),
    path('api/profile/user-prefs/', api_save_user_prefs, name='questlog_web_api_user_prefs'),
    path('api/invite/',             api_invite_link,    name='questlog_web_api_invite'),

    # Embed Validation API
    path('api/embed/validate/', api_validate_embed, name='questlog_web_api_validate_embed'),

    # Admin Social Moderation
    path('api/admin/social-posts/', api_admin_posts, name='questlog_web_api_admin_posts'),
    path('api/admin/social-posts/<int:post_id>/action/', api_admin_post_action, name='questlog_web_api_admin_post_action'),
    path('api/admin/social-comments/<int:comment_id>/action/', api_admin_comment_action, name='questlog_web_api_admin_comment_action'),

    # Admin Games We Play Tracker
    path('admin/games-tracker/', admin_games_tracker, name='questlog_web_admin_games_tracker'),
    path('api/admin/site-activity/games/', api_admin_site_activity_games, name='questlog_web_api_admin_site_activity_games'),
    path('api/admin/site-activity/games/<int:game_id>/', api_admin_site_activity_games, name='questlog_web_api_admin_site_activity_game_detail'),
    path('api/admin/site-activity/roles/', api_admin_site_activity_roles, name='questlog_web_api_admin_site_activity_roles'),
    path('api/admin/site-activity/roles/<int:role_id>/', api_admin_site_activity_roles, name='questlog_web_api_admin_site_activity_role_detail'),

    # Admin: Emergency Maintenance Mode
    path('api/admin/maintenance/toggle/', api_admin_maintenance, name='questlog_web_api_admin_maintenance'),
    path('api/admin/maintenance/status/', api_admin_maintenance_status, name='questlog_web_api_admin_maintenance_status'),
    path('api/admin/logins/toggle/', api_admin_toggle_logins, name='questlog_web_api_admin_toggle_logins'),
    path('api/admin/logins/status/', api_admin_logins_status, name='questlog_web_api_admin_logins_status'),

    # Admin: Flairs
    path('api/admin/flairs/', api_admin_flairs, name='questlog_web_api_admin_flairs'),
    path('api/admin/flairs/<int:flair_id>/', api_admin_flair_detail, name='questlog_web_api_admin_flair_detail'),

    # Admin: Rank Titles
    path('api/admin/rank-titles/', api_admin_rank_titles, name='questlog_web_api_admin_rank_titles'),
    path('api/admin/rank-titles/<int:title_id>/', api_admin_rank_title_detail, name='questlog_web_api_admin_rank_title_detail'),

    # Admin: XP Leaderboard
    path('api/admin/xp-leaderboard/', api_admin_xp_leaderboard, name='questlog_web_api_admin_xp_leaderboard'),

    # Admin: Server Rotation Polls
    path('api/admin/server-polls/', api_admin_server_polls, name='questlog_web_api_admin_server_polls'),
    path('api/admin/server-polls/<int:poll_id>/', api_admin_server_poll_detail, name='questlog_web_api_admin_server_poll_detail'),
    path('api/admin/server-polls/<int:poll_id>/options/', api_admin_server_poll_option, name='questlog_web_api_admin_server_poll_option'),
    path('api/admin/server-polls/<int:poll_id>/options/<int:option_id>/', api_admin_server_poll_option_detail, name='questlog_web_api_admin_server_poll_option_detail'),
    path('api/admin/server-polls/<int:poll_id>/declare-winner/', api_admin_server_poll_declare_winner, name='questlog_web_api_admin_server_poll_winner'),
    path('api/admin/steam-game-search/', api_admin_steam_game_search, name='questlog_web_api_admin_steam_game_search'),

    # Server Rotation Poll (public)
    path('api/polls/active/', api_active_poll, name='questlog_web_api_active_poll'),
    path('api/polls/<int:poll_id>/vote/', api_poll_vote, name='questlog_web_api_poll_vote'),

    # Flair (user-facing)
    path('api/flairs/', api_flairs, name='questlog_web_api_flairs'),
    path('api/flairs/<int:flair_id>/buy/', api_flair_buy, name='questlog_web_api_flair_buy'),
    path('api/flairs/<int:flair_id>/equip/', api_flair_equip, name='questlog_web_api_flair_equip'),
    path('api/flairs/unequip/', api_flair_equip, {'flair_id': 0}, name='questlog_web_api_flair_unequip'),

    # =========================================================================
    # PRIVACY / GDPR
    # =========================================================================
    path('api/privacy/data-summary/', api_privacy_data_summary, name='questlog_web_api_privacy_summary'),
    path('api/privacy/export/', api_privacy_export, name='questlog_web_api_privacy_export'),
    path('api/privacy/delete/', api_privacy_delete, name='questlog_web_api_privacy_delete'),

    # =========================================================================
    # GIVEAWAYS
    # =========================================================================
    path('giveaways/', giveaways_page, name='questlog_web_giveaways'),
    path('api/giveaways/', api_giveaways, name='questlog_web_api_giveaways'),
    path('api/giveaways/<int:giveaway_id>/enter/', api_giveaway_enter, name='questlog_web_api_giveaway_enter'),

    # Admin: Giveaways
    path('api/admin/giveaways/', api_admin_giveaways, name='questlog_web_api_admin_giveaways'),
    path('api/admin/giveaways/<int:giveaway_id>/', api_admin_giveaway_detail, name='questlog_web_api_admin_giveaway_detail'),
    path('api/admin/giveaways/<int:giveaway_id>/launch/', api_admin_giveaway_launch, name='questlog_web_api_admin_giveaway_launch'),
    path('api/admin/giveaways/<int:giveaway_id>/close/', api_admin_giveaway_close, name='questlog_web_api_admin_giveaway_close'),
    path('api/admin/giveaways/<int:giveaway_id>/pick-winner/', api_admin_giveaway_pick_winner, name='questlog_web_api_admin_giveaway_winner'),

    # =========================================================================
    # FLUXER WEBHOOKS (Admin global config)
    # =========================================================================
    path('api/admin/fluxer-webhooks/', api_admin_fluxer_webhooks, name='questlog_web_api_admin_fluxer_webhooks'),
    path('api/admin/fluxer-webhooks/<int:config_id>/', api_admin_fluxer_webhook_detail, name='questlog_web_api_admin_fluxer_webhook_detail'),
    path('api/admin/fluxer-webhooks/<int:config_id>/test/', api_admin_fluxer_webhook_test, name='questlog_web_api_admin_fluxer_webhook_test'),
    path('api/admin/fluxer-guilds/', api_admin_fluxer_guilds, name='questlog_web_api_admin_fluxer_guilds'),

    # Admin: Fluxer Network Subscribers (all communities subscribed via bot)
    path('api/admin/fluxer-subscribers/', api_admin_fluxer_subscribers, name='questlog_web_api_admin_fluxer_subscribers'),
    path('api/admin/fluxer-subscribers/<int:config_id>/', api_admin_fluxer_subscriber_detail, name='questlog_web_api_admin_fluxer_subscriber_detail'),
    path('api/admin/fluxer-subscribers/<int:config_id>/detail/', api_admin_fluxer_guild_detail, name='questlog_web_api_admin_fluxer_guild_detail'),
    path('api/admin/fluxer-guild/<str:guild_id>/channels/', api_admin_fluxer_guild_channels, name='questlog_web_api_admin_fluxer_guild_channels'),
    path('api/admin/discord-guild/<str:guild_id>/channels/', api_admin_discord_guild_channels, name='questlog_web_api_admin_discord_guild_channels'),
    path('api/admin/matrix-spaces/', api_admin_matrix_spaces, name='questlog_web_api_admin_matrix_spaces'),
    path('api/admin/matrix-space/<path:space_id>/rooms/', api_admin_matrix_space_rooms, name='questlog_web_api_admin_matrix_space_rooms'),

    # =========================================================================
    # EARLY ACCESS INVITE CODES
    # =========================================================================
    path('api/admin/invite-codes/', api_admin_invite_codes, name='questlog_web_api_admin_invite_codes'),
    path('api/admin/invite-codes/bulk-revoke/', api_admin_invite_codes_bulk_revoke, name='questlog_web_api_admin_invite_codes_bulk_revoke'),
    path('api/admin/invite-codes/<int:code_id>/', api_admin_invite_code_detail, name='questlog_web_api_admin_invite_code_detail'),

    # =========================================================================
    # UNIFIED SERVER DASHBOARD (all platforms: Discord, Fluxer, Matrix)
    # Discord aliases live in app/urls.py as ql/dashboard/discord/<guild_id>/
    path('dashboard/', unified_dashboard, name='questlog_web_dashboard'),

    # FLUXER BOT DASHBOARD (admin-only per-guild configuration)
    # =========================================================================
    path('dashboard/fluxer/',                                  fluxer_dashboard,          name='questlog_web_fluxer_dashboard'),
    path('dashboard/fluxer/<str:guild_id>/',                   fluxer_guild_dashboard,    name='questlog_web_fluxer_guild_dashboard'),
    # Feature pages
    path('dashboard/fluxer/<str:guild_id>/xp/',                fluxer_guild_xp,           name='fluxer_guild_xp'),
    path('dashboard/fluxer/<str:guild_id>/welcome/',           fluxer_guild_welcome,      name='fluxer_guild_welcome'),
    path('dashboard/fluxer/<str:guild_id>/moderation/',        fluxer_guild_moderation,   name='fluxer_guild_moderation'),
    path('dashboard/fluxer/<str:guild_id>/lfg/',               fluxer_guild_lfg,             name='fluxer_guild_lfg'),
    path('dashboard/fluxer/<str:guild_id>/lfg/attendance/',   fluxer_guild_lfg_attendance,   name='fluxer_guild_lfg_attendance'),
    path('dashboard/fluxer/<str:guild_id>/lfg/calendar/',     fluxer_guild_lfg_calendar,     name='fluxer_guild_lfg_calendar'),
    path('dashboard/fluxer/<str:guild_id>/lfg/browse/',       fluxer_guild_lfg_browse_admin, name='fluxer_guild_lfg_browse_admin'),
    path('dashboard/fluxer/<str:guild_id>/settings/',          fluxer_guild_settings_page, name='fluxer_guild_settings_page'),
    path('dashboard/fluxer/<str:guild_id>/bridge/',            fluxer_guild_bridge,       name='fluxer_guild_bridge'),
    # Feature pages (bot integration pending for some)
    path('dashboard/fluxer/<str:guild_id>/verification/',      fluxer_guild_verification,  name='fluxer_guild_verification'),
    path('dashboard/fluxer/<str:guild_id>/reaction-roles/',    fluxer_guild_reaction_roles, name='fluxer_guild_reaction_roles'),
    path('dashboard/fluxer/<str:guild_id>/trackers/',          fluxer_guild_trackers,      name='fluxer_guild_trackers'),
    path('dashboard/fluxer/<str:guild_id>/audit/',             fluxer_guild_audit,         name='fluxer_guild_audit'),
    path('dashboard/fluxer/<str:guild_id>/templates/',         fluxer_guild_templates_page, name='fluxer_guild_templates'),
    path('dashboard/fluxer/<str:guild_id>/discovery/',         fluxer_guild_discovery,     name='fluxer_guild_discovery'),
    path('dashboard/fluxer/<str:guild_id>/raffles/',           fluxer_guild_raffles,       name='fluxer_guild_raffles'),
    path('dashboard/fluxer/<str:guild_id>/roles/',             fluxer_guild_roles,         name='fluxer_guild_roles'),
    path('dashboard/fluxer/<str:guild_id>/messages/',          fluxer_guild_messages,      name='fluxer_guild_messages'),
    path('dashboard/fluxer/<str:guild_id>/live-alerts/',       fluxer_guild_live_alerts,   name='fluxer_guild_live_alerts'),
    path('dashboard/fluxer/<str:guild_id>/flairs/',            fluxer_guild_flair,         name='fluxer_guild_flair'),
    # API
    path('api/dashboard/fluxer/<str:guild_id>/settings/',     api_fluxer_guild_settings, name='questlog_web_api_fluxer_guild_settings'),
    path('api/dashboard/bot-configs/',                         api_bot_dashboard_configs, name='questlog_web_api_bot_configs'),
    path('api/dashboard/bot-configs/<int:config_id>/',         api_bot_dashboard_config_detail, name='questlog_web_api_bot_config_detail'),
    # Reaction Roles
    path('api/dashboard/fluxer/<str:guild_id>/reaction-roles/',                                   api_fluxer_reaction_roles,        name='questlog_web_api_fluxer_reaction_roles'),
    path('api/dashboard/fluxer/<str:guild_id>/reaction-roles/<str:message_id>/',                  api_fluxer_reaction_role_detail,  name='questlog_web_api_fluxer_reaction_role_detail'),
    # Raffles
    path('api/dashboard/fluxer/<str:guild_id>/raffles/',                                          api_fluxer_guild_raffles,         name='questlog_web_api_fluxer_guild_raffles'),
    path('api/dashboard/fluxer/<str:guild_id>/raffles/<int:raffle_id>/',                          api_fluxer_guild_raffle_detail,   name='questlog_web_api_fluxer_guild_raffle_detail'),
    path('api/dashboard/fluxer/<str:guild_id>/raffles/<int:raffle_id>/pick/',                     api_fluxer_guild_raffle_pick,     name='questlog_web_api_fluxer_guild_raffle_pick'),
    # Bridges
    path('api/dashboard/fluxer/<str:guild_id>/bridges/',                                              api_fluxer_guild_bridges,             name='questlog_web_api_fluxer_guild_bridges'),
    path('api/dashboard/fluxer/<str:guild_id>/bridges/<int:bridge_id>/',                              api_fluxer_guild_bridge_detail,       name='questlog_web_api_fluxer_guild_bridge_detail'),
    # Guild channel/role pickers (used by trackers modal and other pages)
    path('api/dashboard/fluxer/<str:guild_id>/channels/',                                             api_fluxer_guild_channels,            name='questlog_web_api_fluxer_guild_channels'),
    path('api/dashboard/fluxer/<str:guild_id>/roles/',                                                api_fluxer_guild_roles,               name='questlog_web_api_fluxer_guild_roles'),
    # Channel Stat Trackers
    path('api/dashboard/fluxer/<str:guild_id>/trackers/',                                             api_fluxer_guild_trackers,            name='questlog_web_api_fluxer_guild_trackers'),
    path('api/dashboard/fluxer/<str:guild_id>/trackers/<int:tracker_id>/',                            api_fluxer_guild_tracker_detail,      name='questlog_web_api_fluxer_guild_tracker_detail'),
    # Discovery RSS feeds
    path('api/dashboard/fluxer/<str:guild_id>/discovery/rss/',                                        api_fluxer_discovery_rss,             name='questlog_web_api_fluxer_discovery_rss'),
    path('api/dashboard/fluxer/<str:guild_id>/discovery/rss/<int:feed_id>/',                          api_fluxer_discovery_rss_detail,      name='questlog_web_api_fluxer_discovery_rss_detail'),
    path('api/dashboard/fluxer/<str:guild_id>/discovery/rss/<int:feed_id>/force-send/',               api_fluxer_discovery_rss_force_send,  name='questlog_web_api_fluxer_discovery_rss_force_send'),
    path('api/dashboard/fluxer/<str:guild_id>/discovery/rss/<int:feed_id>/preview/',                  api_fluxer_discovery_rss_preview,     name='questlog_web_api_fluxer_discovery_rss_preview'),
    # Messages
    path('api/dashboard/fluxer/<str:guild_id>/messages/send-embed/',                                  api_fluxer_messages_send_embed,       name='questlog_web_api_fluxer_messages_send_embed'),
    # Roles management
    path('api/dashboard/fluxer/<str:guild_id>/roles/list/',                                       api_fluxer_guild_roles_list,      name='questlog_web_api_fluxer_guild_roles_list'),
    path('api/dashboard/fluxer/<str:guild_id>/roles/actions/',                                    api_fluxer_guild_roles_actions,   name='questlog_web_api_fluxer_guild_roles_actions'),
    path('api/dashboard/fluxer/<str:guild_id>/roles/action/',                                     api_fluxer_guild_role_action,     name='questlog_web_api_fluxer_guild_role_action'),
    path('api/dashboard/fluxer/<str:guild_id>/roles/create/',                                     api_fluxer_guild_role_create,     name='questlog_web_api_fluxer_guild_role_create'),
    path('api/dashboard/fluxer/<str:guild_id>/roles/bulk-create/',                                api_fluxer_guild_role_bulk_create, name='questlog_web_api_fluxer_guild_role_bulk_create'),
    path('api/dashboard/fluxer/<str:guild_id>/roles/import/',                                     api_fluxer_guild_role_import,     name='questlog_web_api_fluxer_guild_role_import'),
    # Templates
    path('api/dashboard/fluxer/<str:guild_id>/templates/list/',                                         api_fluxer_guild_templates_list,  name='questlog_web_api_fluxer_guild_templates_list'),
    path('api/dashboard/fluxer/<str:guild_id>/templates/<str:template_type>/',                          api_fluxer_guild_template_create, name='questlog_web_api_fluxer_guild_template_create'),
    path('api/dashboard/fluxer/<str:guild_id>/templates/<str:template_type>/<int:template_id>/',        api_fluxer_guild_template_detail, name='questlog_web_api_fluxer_guild_template_detail'),
    path('api/dashboard/fluxer/<str:guild_id>/templates/<str:template_type>/<int:template_id>/apply/',  api_fluxer_guild_template_apply,  name='questlog_web_api_fluxer_guild_template_apply'),
    path('api/dashboard/fluxer/<str:guild_id>/members/',                                               api_fluxer_guild_members,         name='questlog_web_api_fluxer_guild_members'),
    # IGDB search proxy
    path('api/dashboard/fluxer/igdb-search/', api_fluxer_igdb_search, name='questlog_web_api_fluxer_igdb_search'),
    # LFG Games (per-guild)
    path('api/dashboard/fluxer/<str:guild_id>/lfg-games/',              api_fluxer_guild_lfg_games,        name='questlog_web_api_fluxer_guild_lfg_games'),
    path('api/dashboard/fluxer/<str:guild_id>/lfg-games/<int:game_id>/', api_fluxer_guild_lfg_game_detail, name='questlog_web_api_fluxer_guild_lfg_game_detail'),
    # LFG Attendance config / stats / blacklist (per-guild)
    path('api/dashboard/fluxer/<str:guild_id>/lfg-config/',                               api_fluxer_guild_lfg_config,          name='questlog_web_api_fluxer_guild_lfg_config'),
    path('api/dashboard/fluxer/<str:guild_id>/lfg-stats/',                                api_fluxer_guild_lfg_stats,           name='questlog_web_api_fluxer_guild_lfg_stats'),
    path('api/dashboard/fluxer/<str:guild_id>/lfg-blacklist/',                            api_fluxer_guild_lfg_blacklist,       name='questlog_web_api_fluxer_guild_lfg_blacklist'),
    path('api/dashboard/fluxer/<str:guild_id>/lfg-blacklist/<str:user_id>/action/',      api_fluxer_guild_lfg_blacklist_action, name='questlog_web_api_fluxer_guild_lfg_blacklist_action'),
    # LFG Group CRUD (browse admin)
    path('api/dashboard/fluxer/<str:guild_id>/lfg/groups/',                              api_fluxer_guild_lfg_groups,       name='questlog_web_api_fluxer_lfg_groups'),
    path('api/dashboard/fluxer/<str:guild_id>/lfg/groups/<int:group_id>/',               api_fluxer_guild_lfg_group_detail, name='questlog_web_api_fluxer_lfg_group_detail'),
    path('api/dashboard/fluxer/<str:guild_id>/lfg/groups/<int:group_id>/kick/<int:member_id>/', api_fluxer_guild_lfg_group_kick, name='questlog_web_api_fluxer_lfg_group_kick'),
    # LFG Attendance data + CSV export
    path('api/dashboard/fluxer/<str:guild_id>/lfg/attendance/',        api_fluxer_guild_lfg_attendance,    name='questlog_web_api_fluxer_lfg_attendance'),
    path('api/dashboard/fluxer/<str:guild_id>/lfg/attendance/export/', api_fluxer_guild_attendance_export, name='questlog_web_api_fluxer_attendance_export'),
    # Live Alerts - streamer subscriptions
    path('api/dashboard/fluxer/<str:guild_id>/streamer-subs/',               api_fluxer_guild_streamer_subs,       name='questlog_web_api_fluxer_streamer_subs'),
    path('api/dashboard/fluxer/<str:guild_id>/streamer-subs/<int:sub_id>/', api_fluxer_guild_streamer_sub_detail, name='questlog_web_api_fluxer_streamer_sub_detail'),
    # Game discovery (IGDB-based search configs + found games)
    path('api/dashboard/fluxer/<str:guild_id>/game-search-configs/',                         api_fluxer_guild_game_search_configs,       name='questlog_web_api_fluxer_game_search_configs'),
    path('api/dashboard/fluxer/<str:guild_id>/game-search-configs/<int:config_id>/',         api_fluxer_guild_game_search_config_detail, name='questlog_web_api_fluxer_game_search_config_detail'),
    path('api/dashboard/fluxer/<str:guild_id>/found-games/',                                 api_fluxer_guild_found_games,               name='questlog_web_api_fluxer_found_games'),
    path('api/dashboard/fluxer/<str:guild_id>/igdb-keywords/',                               api_fluxer_guild_igdb_keywords,             name='questlog_web_api_fluxer_igdb_keywords'),
    path('api/dashboard/fluxer/<str:guild_id>/game-discovery-settings/',                     api_fluxer_guild_game_discovery_settings,   name='questlog_web_api_fluxer_game_discovery_settings'),
    path('api/dashboard/fluxer/<str:guild_id>/force-check-games/',                           api_fluxer_guild_force_check_games,         name='questlog_web_api_fluxer_force_check_games'),
    # Welcome config (per-guild)
    path('api/dashboard/fluxer/<str:guild_id>/welcome/',         api_fluxer_guild_welcome_config, name='questlog_web_api_fluxer_guild_welcome_config'),
    path('api/dashboard/fluxer/<str:guild_id>/welcome/test/',    api_fluxer_guild_welcome_test,   name='questlog_web_api_fluxer_guild_welcome_test'),
    # Flair management (per-guild)
    path('api/dashboard/fluxer/<str:guild_id>/flairs/',                        api_fluxer_guild_flairs,        name='questlog_web_api_fluxer_guild_flairs'),
    path('api/dashboard/fluxer/<str:guild_id>/flairs/create/',                 api_fluxer_guild_flair_create,  name='questlog_web_api_fluxer_guild_flair_create'),
    path('api/dashboard/fluxer/<str:guild_id>/flairs/<int:flair_id>/',        api_fluxer_guild_flair_detail,  name='questlog_web_api_fluxer_guild_flair_detail'),
    # Level roles (per-guild)
    path('api/dashboard/fluxer/<str:guild_id>/level-roles/',                   api_fluxer_guild_level_roles,         name='questlog_web_api_fluxer_guild_level_roles'),
    path('api/dashboard/fluxer/<str:guild_id>/level-roles/bulk/',              api_fluxer_guild_level_roles_bulk,    name='questlog_web_api_fluxer_guild_level_roles_bulk'),
    path('api/dashboard/fluxer/<str:guild_id>/level-roles/<int:lr_id>/',       api_fluxer_guild_level_role_detail,   name='questlog_web_api_fluxer_guild_level_role_detail'),
    path('api/dashboard/fluxer/<str:guild_id>/member-xp/',                     api_fluxer_guild_member_xp,           name='questlog_web_api_fluxer_guild_member_xp'),
    path('api/dashboard/fluxer/<str:guild_id>/levelup-config/',                api_fluxer_guild_levelup_config,      name='questlog_web_api_fluxer_guild_levelup_config'),
    path('api/dashboard/fluxer/<str:guild_id>/xp-boosts/',                    api_fluxer_guild_xp_boosts,           name='questlog_web_api_fluxer_guild_xp_boosts'),
    path('api/dashboard/fluxer/<str:guild_id>/xp-boosts/<int:boost_id>/',     api_fluxer_guild_xp_boost_detail,     name='questlog_web_api_fluxer_guild_xp_boost_detail'),
    path('api/dashboard/fluxer/<str:guild_id>/live-info/',                    api_fluxer_guild_live_info,           name='questlog_web_api_fluxer_guild_live_info'),
    # Moderation Warnings (per-guild)
    path('api/dashboard/fluxer/<str:guild_id>/warnings/',                        api_fluxer_guild_warnings,       name='questlog_web_api_fluxer_guild_warnings'),
    path('api/dashboard/fluxer/<str:guild_id>/warnings/<int:warning_id>/pardon/', api_fluxer_guild_warning_pardon, name='questlog_web_api_fluxer_guild_warning_pardon'),

    # =========================================================================
    # INTERNAL BOT API (called by bots, not browsers)
    # =========================================================================
    path('api/internal/bot-config/', api_internal_bot_config, name='questlog_web_api_internal_bot_config'),
    path('api/internal/lfg/<int:lfg_id>/broadcast/', api_internal_broadcast_lfg, name='questlog_web_api_internal_broadcast_lfg'),
    path('api/internal/guild-names/', api_internal_guild_names, name='questlog_web_api_internal_guild_names'),
    path('api/internal/guild-roles/', api_internal_guild_roles, name='questlog_web_api_internal_guild_roles'),
    path('api/internal/guild-sync/', api_internal_guild_sync, name='questlog_web_api_internal_guild_sync'),
    path('api/internal/guild-remove/', api_internal_guild_remove, name='questlog_web_api_internal_guild_remove'),
    path('api/internal/guild-actions/', api_internal_guild_actions_pending, name='questlog_web_api_internal_guild_actions_pending'),
    path('api/internal/guild-actions/<int:action_id>/done/', api_internal_guild_action_done, name='questlog_web_api_internal_guild_action_done'),
    path('api/internal/bridge/relay/', api_internal_bridge_relay, name='questlog_web_api_internal_bridge_relay'),
    path('api/internal/bridge/pending/<str:platform>/', api_internal_bridge_pending, name='questlog_web_api_internal_bridge_pending'),
    path('api/internal/bridge/message-map/', api_internal_bridge_message_map, name='questlog_web_api_internal_bridge_message_map'),
    path('api/internal/bridge/thread-map/', api_internal_bridge_thread_map, name='questlog_web_api_internal_bridge_thread_map'),
    path('api/internal/bridge/reaction/', api_internal_bridge_reaction, name='questlog_web_api_internal_bridge_reaction'),
    path('api/internal/bridge/pending-reactions/<str:platform>/', api_internal_bridge_pending_reactions, name='questlog_web_api_internal_bridge_pending_reactions'),
    path('api/internal/bridge/delete/', api_internal_bridge_delete, name='questlog_web_api_internal_bridge_delete'),
    path('api/internal/bridge/pending-deletions/<str:platform>/', api_internal_bridge_pending_deletions, name='questlog_web_api_internal_bridge_pending_deletions'),
    path('api/internal/bridge/media-proxy/', api_bridge_media_proxy, name='questlog_web_api_bridge_media_proxy'),

    # =========================================================================
    # HERO SUBSCRIPTION (Stripe)
    # =========================================================================
    path('hero/', hero_subscribe, name='questlog_web_hero_subscribe'),
    path('hero/return/', hero_return, name='questlog_web_hero_return'),
    path('hero/success/', hero_success, name='questlog_web_hero_success'),
    path('credits/', lambda req: redirect('/ql/hero/#credits'), name='questlog_web_credits'),
    path('api/billing/checkout/', api_hero_checkout, name='questlog_web_api_hero_checkout'),
    path('api/billing/webhook/', api_stripe_webhook, name='questlog_web_api_stripe_webhook'),
    path('api/billing/portal/', hero_portal, name='questlog_web_hero_portal'),

    # =========================================================================
    # ADMIN: HERO SUBSCRIBERS + BOT NETWORK + BRIDGE
    # =========================================================================
    path('api/admin/hero-subscribers/', api_admin_hero_subscribers, name='questlog_web_api_admin_hero_subscribers'),
    path('api/admin/bot-network/', api_admin_bot_network, name='questlog_web_api_admin_bot_network'),
    path('api/admin/bridge-configs/', api_admin_bridge_configs, name='questlog_web_api_admin_bridge_configs'),
    path('api/admin/bridge-configs/<int:config_id>/', api_admin_bridge_config_detail, name='questlog_web_api_admin_bridge_config_detail'),
    path('api/admin/emoji/', api_admin_emoji, name='questlog_web_api_admin_emoji'),
    path('api/admin/emoji/<int:emoji_id>/', api_admin_emoji_detail, name='questlog_web_api_admin_emoji_detail'),

    # =========================================================================
    # MATRIX BOT DASHBOARD (QuestLogMatrix)
    # =========================================================================
    # Space IDs (e.g. !KhWcZg:server.com) are URL-encoded in templates as
    # %21KhWcZg%3Aserver.com (no slashes), so <str:space_id> works fine.
    # Django auto-decodes the parameter back to the real space ID.
    path('dashboard/matrix/',                                              matrix_dashboard,          name='questlog_web_matrix_dashboard'),
    path('dashboard/matrix/<str:space_id>/',                               matrix_guild_dashboard,    name='questlog_web_matrix_guild_dashboard'),
    path('dashboard/matrix/<str:space_id>/rooms/',                         matrix_guild_rooms,        name='questlog_web_matrix_guild_rooms'),
    path('dashboard/matrix/<str:space_id>/members/',                       matrix_guild_members,      name='questlog_web_matrix_guild_members'),
    path('dashboard/matrix/<str:space_id>/xp/',                            matrix_guild_xp,           name='questlog_web_matrix_guild_xp'),
    path('dashboard/matrix/<str:space_id>/moderation/',                    matrix_guild_moderation,   name='questlog_web_matrix_guild_moderation'),
    path('dashboard/matrix/<str:space_id>/welcome/',                       matrix_guild_welcome,      name='questlog_web_matrix_guild_welcome'),
    path('dashboard/matrix/<str:space_id>/ban-lists/',                     matrix_guild_ban_lists,    name='questlog_web_matrix_guild_ban_lists'),
    path('dashboard/matrix/<str:space_id>/rss/',                           matrix_guild_rss,          name='questlog_web_matrix_guild_rss'),
    path('dashboard/matrix/<str:space_id>/messages/',                      matrix_guild_messages,     name='questlog_web_matrix_guild_messages'),
    path('dashboard/matrix/<str:space_id>/settings/',                      matrix_guild_settings,     name='questlog_web_matrix_guild_settings'),
    path('dashboard/matrix/<str:space_id>/audit/',                         matrix_guild_audit,        name='questlog_web_matrix_guild_audit'),
    path('dashboard/matrix/<str:space_id>/verification/',                  matrix_guild_verification, name='questlog_web_matrix_guild_verification'),
    path('dashboard/matrix/<str:space_id>/bridge/',                        matrix_guild_bridge,       name='questlog_web_matrix_guild_bridge'),
    # Matrix API endpoints
    path('api/dashboard/matrix/<str:space_id>/settings/',                  api_matrix_space_settings,     name='questlog_web_api_matrix_settings'),
    path('api/dashboard/matrix/<str:space_id>/rooms/',                     api_matrix_rooms,              name='questlog_web_api_matrix_rooms'),
    path('api/dashboard/matrix/<str:space_id>/rooms/create/',              api_matrix_room_create,        name='questlog_web_api_matrix_room_create'),
    path('api/dashboard/matrix/<str:space_id>/rooms/<str:room_id>/',       api_matrix_room_detail,        name='questlog_web_api_matrix_room_detail'),
    path('api/dashboard/matrix/<str:space_id>/members/',                   api_matrix_members,            name='questlog_web_api_matrix_members'),
    path('api/dashboard/matrix/<str:space_id>/members/kick/',              api_matrix_member_kick,        name='questlog_web_api_matrix_member_kick'),
    path('api/dashboard/matrix/<str:space_id>/members/ban/',               api_matrix_member_ban,         name='questlog_web_api_matrix_member_ban'),
    path('api/dashboard/matrix/<str:space_id>/members/invite/',            api_matrix_member_invite,      name='questlog_web_api_matrix_member_invite'),
    path('api/dashboard/matrix/<str:space_id>/members/powerlevel/',        api_matrix_member_powerlevel,  name='questlog_web_api_matrix_member_powerlevel'),
    path('api/dashboard/matrix/<str:space_id>/warnings/',                  api_matrix_warnings,           name='questlog_web_api_matrix_warnings'),
    path('api/dashboard/matrix/<str:space_id>/warnings/<int:warning_id>/pardon/', api_matrix_warning_pardon, name='questlog_web_api_matrix_warning_pardon'),
    path('api/dashboard/matrix/<str:space_id>/welcome/',                   api_matrix_welcome_config,     name='questlog_web_api_matrix_welcome'),
    path('api/dashboard/matrix/<str:space_id>/xp/',                        api_matrix_xp_settings,        name='questlog_web_api_matrix_xp'),
    path('api/dashboard/matrix/<str:space_id>/xp/leaderboard/',            api_matrix_xp_leaderboard,     name='questlog_web_api_matrix_xp_leaderboard'),
    path('api/dashboard/matrix/<str:space_id>/xp/boosts/',                 api_matrix_xp_boosts,          name='questlog_web_api_matrix_xp_boosts'),
    path('api/dashboard/matrix/<str:space_id>/xp/boosts/<int:boost_id>/',  api_matrix_xp_boost_detail,    name='questlog_web_api_matrix_xp_boost_detail'),
    path('api/dashboard/matrix/<str:space_id>/xp/level-roles/',            api_matrix_level_roles,        name='questlog_web_api_matrix_level_roles'),
    path('api/dashboard/matrix/<str:space_id>/xp/level-roles/<int:role_id>/', api_matrix_level_role_detail, name='questlog_web_api_matrix_level_role_detail'),
    path('api/dashboard/matrix/<str:space_id>/rss/',                       api_matrix_rss,                name='questlog_web_api_matrix_rss'),
    path('api/dashboard/matrix/<str:space_id>/rss/<int:feed_id>/',         api_matrix_rss_detail,         name='questlog_web_api_matrix_rss_detail'),
    path('api/dashboard/matrix/<str:space_id>/ban-lists/',                 api_matrix_ban_lists,          name='questlog_web_api_matrix_ban_lists'),
    path('api/dashboard/matrix/<str:space_id>/ban-lists/<int:list_id>/',   api_matrix_ban_list_detail,    name='questlog_web_api_matrix_ban_list_detail'),
    path('api/dashboard/matrix/<str:space_id>/ban-lists/<int:list_id>/entries/', api_matrix_ban_list_entries, name='questlog_web_api_matrix_ban_list_entries'),
    path('api/dashboard/matrix/<str:space_id>/ban-lists/entries/<int:entry_id>/', api_matrix_ban_list_entry_detail, name='questlog_web_api_matrix_ban_list_entry_detail'),
    path('api/dashboard/matrix/<str:space_id>/messages/',                  api_matrix_send_message,       name='questlog_web_api_matrix_messages'),
    path('api/dashboard/matrix/<str:space_id>/sync/',                      api_matrix_sync_status,        name='questlog_web_api_matrix_sync'),
    path('api/dashboard/matrix/<str:space_id>/actions/',                   api_matrix_action_history,     name='questlog_web_api_matrix_action_history'),
    path('api/dashboard/matrix/<str:space_id>/audit-log/',                 api_matrix_audit_log,          name='questlog_web_api_matrix_audit_log'),
    path('api/dashboard/matrix/<str:space_id>/audit-propagate/',           api_matrix_propagate_audit,    name='questlog_web_api_matrix_audit_propagate'),
    path('api/dashboard/matrix/<str:space_id>/bridges/',                   api_matrix_bridges,            name='questlog_web_api_matrix_bridges'),
    path('api/dashboard/matrix/<str:space_id>/bridges/<int:bridge_id>/',   api_matrix_bridge_detail,      name='questlog_web_api_matrix_bridge_detail'),
]
