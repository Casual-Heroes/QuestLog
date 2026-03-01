# QuestLog Web URLs
# These routes are for casual-heroes.com/ql/

from django.urls import path

from .views_auth import (
    ql_login, ql_register, ql_admin_login,
    verify_email, resend_verification, check_email, logout,
    steam_link, steam_link_callback, steam_unlink,
    discord_link, discord_link_callback, discord_unlink,
    twitch_oauth_initiate, twitch_oauth_callback, twitch_disconnect,
    youtube_oauth_initiate, youtube_oauth_callback, youtube_disconnect,
)
from .views_pages import (
    home,
    lfg_browse, lfg_create, lfg_my_groups, lfg_group_detail,
    lfg_join, lfg_leave, lfg_edit, lfg_update_member, lfg_delete, lfg_kick, lfg_set_co_leader,
    network, games, creators, articles,
    communities, community_register, community_detail,
    profile, profile_edit, creator_register, settings, hero_shop,
    game_servers_ql,
    api_active_poll, api_poll_vote,
    giveaways_page,
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
)
from .views_discovery import (
    api_lfg_list, api_lfg_detail,
    api_communities, api_community_detail, api_creators, api_games, api_articles,
    api_igdb_search,
)
from .views_uploads import (
    api_upload_image, api_upload_avatar, api_upload_banner,
    api_upload_community_icon, api_upload_community_banner,
    api_gif_search, api_gif_trending,
)
from .views_social import (
    api_block, api_block_list,
    api_follow, api_followers, api_following, api_follow_status,
    api_posts, _get_feed_posts, api_post_detail, api_user_posts, api_global_posts,
    api_recent_activity, _get_recent_activity,
    api_post_like, api_post_share,
    api_comments, _get_comments, api_comment_detail, api_comment_like,
    api_notifications, api_notification_count, api_notifications_mark_read, api_notification_mark_read,
    api_giveaways, api_giveaway_enter,
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
    path('admin-login/', ql_admin_login, name='questlog_web_admin_login'),
    path('register/', ql_register, name='questlog_web_register'),
    path('verify-email/<str:token>/', verify_email, name='questlog_web_verify_email'),
    path('resend-verification/',      resend_verification, name='questlog_web_resend_verification'),
    path('logout/',   logout,      name='questlog_web_logout'),

    # Steam — optional connection (unlocks game-tracking features)
    path('auth/steam/link/',     steam_link,          name='questlog_web_steam_link'),
    path('auth/steam/callback/', steam_link_callback, name='questlog_web_steam_callback'),
    path('auth/steam/unlink/',   steam_unlink,        name='questlog_web_steam_unlink'),

    # Discord — optional account linking
    path('auth/discord/link/',          discord_link,          name='questlog_web_discord_link'),
    path('auth/discord/link/callback/', discord_link_callback, name='questlog_web_discord_link_callback'),
    path('auth/discord/unlink/',        discord_unlink,        name='questlog_web_discord_unlink'),

    # Twitch OAuth — creator profile integration
    path('auth/twitch/link/',     twitch_oauth_initiate, name='questlog_web_twitch_link'),
    path('auth/twitch/callback/', twitch_oauth_callback, name='questlog_web_twitch_callback'),
    path('auth/twitch/unlink/',   twitch_disconnect,     name='questlog_web_twitch_unlink'),

    # YouTube OAuth — creator profile integration
    path('auth/youtube/link/',     youtube_oauth_initiate, name='questlog_web_youtube_link'),
    path('auth/youtube/callback/', youtube_oauth_callback, name='questlog_web_youtube_callback'),
    path('auth/youtube/unlink/',   youtube_disconnect,     name='questlog_web_youtube_unlink'),

    # LFG
    path('lfg/', lfg_browse, name='questlog_web_lfg_browse'),
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
    path('games/', games, name='questlog_web_games'),
    path('creators/', creators, name='questlog_web_creators'),
    path('articles/', articles, name='questlog_web_articles'),

    # Communities
    path('communities/', communities, name='questlog_web_communities'),
    path('communities/register/', community_register, name='questlog_web_community_register'),
    path('communities/<int:community_id>/', community_detail, name='questlog_web_community_detail'),

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
    path('api/communities/', api_communities, name='questlog_web_api_communities'),
    path('api/communities/<int:community_id>/', api_community_detail, name='questlog_web_api_community_detail'),
    path('api/creators/', api_creators, name='questlog_web_api_creators'),
    path('api/games/', api_games, name='questlog_web_api_games'),
    path('api/igdb/search/', api_igdb_search, name='questlog_web_api_igdb_search'),
    path('api/articles/', api_articles, name='questlog_web_api_articles'),

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
    path('api/posts/<int:post_id>/like/', api_post_like, name='questlog_web_api_post_like'),

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

    # Notification API
    path('api/notifications/', api_notifications, name='questlog_web_api_notifications'),
    path('api/notifications/count/', api_notification_count, name='questlog_web_api_notification_count'),
    path('api/notifications/read/', api_notifications_mark_read, name='questlog_web_api_notifications_read'),
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
]
