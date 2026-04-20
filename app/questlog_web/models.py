# QuestLog Web Models - Web-native user and community models
# These are separate from Discord-based models to allow standalone web usage

from sqlalchemy import (
    Column, Integer, SmallInteger, BigInteger, String, Text, Boolean, Float, Enum, ForeignKey,
    UniqueConstraint, Index, and_, or_
)
from sqlalchemy.orm import relationship
from app.models import Base  # Base is defined in models.py
import enum
import time
import hashlib
import hmac
import secrets
from app.utils.encryption import encrypt_token, decrypt_token


class PlatformType(enum.Enum):
    """Supported community platforms"""
    MATRIX = "matrix"
    FLUXER = "fluxer"
    KLOAK = "kloak"
    STOAT = "stoat"
    TEAMSPEAK = "teamspeak"
    ROOT = "root"
    DISCORD = "discord"
    MUMBLE = "mumble"
    GUILDED = "guilded"
    OTHER = "other"


class WebUser(Base):
    """
    Web-native user account.
    Can be linked to Steam, Discord, Twitch, etc.
    Primary auth is Steam OAuth.
    """
    __tablename__ = 'web_users'

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Display info
    username = Column(String(100), nullable=False)
    display_name = Column(String(100), nullable=True)
    avatar_url = Column(String(500), nullable=True)
    bio = Column(Text, nullable=True)

    # Steam (optional linked account — unlocks game features)
    steam_id = Column(String(50), unique=True, nullable=True, index=True)
    steam_username = Column(String(100), nullable=True)
    steam_avatar = Column(String(500), nullable=True)
    steam_profile_url = Column(String(500), nullable=True)

    # Optional linked accounts
    discord_id = Column(String(50), unique=True, nullable=True, index=True)
    discord_username = Column(String(100), nullable=True)
    fluxer_id = Column(String(50), unique=True, nullable=True, index=True)
    fluxer_username = Column(String(100), nullable=True)
    matrix_id = Column(String(100), unique=True, nullable=True, index=True)
    matrix_username = Column(String(100), nullable=True)
    twitch_id = Column(String(50), unique=True, nullable=True, index=True)
    twitch_username = Column(String(100), nullable=True)
    youtube_channel_id = Column(String(100), nullable=True)
    youtube_channel_name = Column(String(100), nullable=True)

    # Contact (optional) - stored Fernet-encrypted; use .email property for access
    email_enc = Column(Text, nullable=True)
    email_verified = Column(Boolean, default=False)

    @property
    def email(self):
        """Decrypt and return the email address, or None if not set."""
        if not self.email_enc:
            return None
        try:
            return decrypt_token(self.email_enc)
        except Exception:
            return None

    @email.setter
    def email(self, value):
        """Encrypt the email address before storing."""
        if value:
            self.email_enc = encrypt_token(value.strip().lower())
        else:
            self.email_enc = None

    # Web XP system (unified with Fluxer bot activity)
    web_xp = Column(Integer, default=0)
    web_level = Column(Integer, default=1)
    hero_points = Column(Integer, default=0)
    active_flair_id = Column(Integer, ForeignKey('web_flairs.id'), nullable=True)
    fluxer_xp_migrated = Column(SmallInteger, default=0, nullable=False, server_default='0')

    # Legacy system - impact/trust passport across all CH platforms and game servers
    legacy_score = Column(Integer, default=0, nullable=False, server_default='0')
    legacy_tier  = Column(Integer, default=1, nullable=False, server_default='1')
    # Tiers: 1=Common, 2=Rare, 3=Epic, 4=Legendary, 5=Mythical
    primary_community_id = Column(Integer, ForeignKey('web_communities.id'), nullable=True)

    # Live stream status (updated by check_live_status cron)
    is_live = Column(SmallInteger, default=0, nullable=False, server_default='0')
    live_platform = Column(String(20), nullable=True)   # 'twitch' or 'youtube'
    live_title = Column(String(255), nullable=True)
    live_url = Column(String(500), nullable=True)
    live_checked_at = Column(BigInteger, nullable=True)

    # Steam tracking opt-ins (both default off — fully user-controlled)
    track_achievements = Column(Boolean, default=False)
    track_hours_played = Column(Boolean, default=False)
    steam_achievements_total = Column(Integer, default=0)  # last known total for delta
    steam_hours_total = Column(Integer, default=0)         # last known minutes for delta
    show_playing_status = Column(Boolean, default=False)   # Show currently-playing game on profile/posts
    current_game = Column(String(255), nullable=True)      # Name of game being played right now (null = not playing)
    current_game_appid = Column(Integer, nullable=True)    # Steam app ID for current_game (for direct store link)
    track_game_launches = Column(Boolean, default=False)   # Opt-in: earn XP when launching a new game
    last_game_launched_at = Column(BigInteger, nullable=True)  # Unix epoch of last game launch XP award (cooldown)
    fluxer_sync_custom_status = Column(Boolean, default=False)  # Opt-in: sync Now Playing to Fluxer custom status
    fluxer_access_token_enc = Column(Text, nullable=True)       # Fernet-encrypted Fluxer OAuth access token
    fluxer_refresh_token_enc = Column(Text, nullable=True)      # Fernet-encrypted Fluxer OAuth refresh token
    fluxer_token_expires_at = Column(BigInteger, nullable=True) # Unix epoch when access token expires

    # Preferences
    allow_discovery = Column(Boolean, default=True)  # Show in public directories
    email_notifications = Column(Boolean, default=True)

    # Privacy preferences
    show_steam_profile = Column(Boolean, default=True)   # Show Steam profile link on public profile
    show_activity = Column(Boolean, default=True)         # Show recent activity (groups joined, etc.)
    allow_messages = Column(Boolean, default=False)       # Allow DMs from other users

    # Notification preferences (in-site notifications)
    notify_follows = Column(Boolean, default=True)        # Someone follows me
    notify_likes = Column(Boolean, default=True)          # Someone likes my post
    notify_comments = Column(Boolean, default=True)       # Comment or reply on my content
    notify_comment_likes = Column(Boolean, default=True)  # Someone likes my comment
    notify_shares = Column(Boolean, default=True)         # Someone shares my post
    notify_mentions = Column(Boolean, default=True)       # Someone @mentions me
    notify_giveaways = Column(Boolean, default=True)      # New giveaway launched
    notify_lfg_join = Column(Boolean, default=True)       # Someone joins my LFG group
    notify_lfg_leave = Column(Boolean, default=True)      # Someone leaves my LFG group
    notify_lfg_full = Column(Boolean, default=True)       # My LFG group is full
    notify_community_join = Column(Boolean, default=False) # New member joins my community
    notify_now_playing = Column(Boolean, default=True)    # Someone you follow starts playing a game
    notify_level_up = Column(Boolean, default=True)       # You leveled up (system)

    # Ticker / activity feed opt-outs (controls what shows in the public marquee)
    ticker_show_live     = Column(Boolean, default=True)  # Show when I go live on the marquee
    ticker_show_playing  = Column(Boolean, default=True)  # Show when I start playing a game
    ticker_show_posts    = Column(Boolean, default=True)  # Show when I post
    ticker_show_follows  = Column(Boolean, default=True)  # Show when I follow someone
    ticker_show_lfg      = Column(Boolean, default=True)  # Show LFG create/join/leave events

    # Referral / invite
    invite_code = Column(String(16), unique=True, nullable=True, index=True)  # Personal invite code (generated on demand)
    referral_count = Column(Integer, default=0)  # Count of completed (verified) referrals

    # Social profile
    banner_url = Column(String(500), nullable=True)
    favorite_genres = Column(Text, default='[]')  # JSON array: ["RPG", "Souls-like", "MMO"]
    favorite_games = Column(Text, default='[]')  # JSON array: [{"name":"Elden Ring","steam_id":1245620}]
    playstyle = Column(String(100), nullable=True)  # Casual, Hardcore, Competitive, etc.
    gaming_platforms = Column(Text, default='[]')  # JSON array: ["PC", "PS5", "Xbox", "Switch"]

    # Denormalized social counters
    post_count = Column(Integer, default=0)
    follower_count = Column(Integer, default=0)
    following_count = Column(Integer, default=0)
    last_post_at = Column(BigInteger, nullable=True)

    # Champion subscription (Stripe) - displayed as "Champion", internal field names kept as is
    is_hero = Column(SmallInteger, default=0, nullable=False, server_default='0')
    hero_expires_at = Column(BigInteger, nullable=True)
    stripe_customer_id = Column(String(64), nullable=True, index=True)
    stripe_subscription_id = Column(String(64), nullable=True)
    # Champion perks
    active_flair2_id = Column(Integer, ForeignKey('web_flairs.id'), nullable=True)  # Second equipped flair (Champions only)
    show_as_champion = Column(SmallInteger, default=0, nullable=False, server_default='0')  # Opt-in public listing

    # Admin flags
    is_vip = Column(Boolean, default=False)    # Early tester / VIP status
    is_admin = Column(Boolean, default=False)  # Site admin
    is_banned = Column(Boolean, default=False)
    ban_reason = Column(Text, nullable=True)
    is_disabled = Column(Boolean, default=False)  # Account locked (soft ban - no login)
    posting_timeout_until = Column(BigInteger, nullable=True)  # Unix ts: cannot post/comment until this time

    # Timestamps
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)
    last_login_at = Column(BigInteger, nullable=True)

    # Relationships
    communities = relationship("WebCommunityMember", back_populates="user")
    owned_communities = relationship("WebCommunity", foreign_keys="WebCommunity.owner_id", back_populates="owner")
    lfg_groups = relationship("WebLFGGroup", back_populates="creator")
    creator_profile = relationship("WebCreatorProfile", back_populates="user", uselist=False)
    posts = relationship("WebPost", back_populates="author", foreign_keys="WebPost.author_id")
    notifications = relationship("WebNotification", back_populates="user", foreign_keys="WebNotification.user_id")
    user_flairs = relationship("WebUserFlair", back_populates="user", foreign_keys="WebUserFlair.user_id")

    @property
    def flair_emoji(self):
        """Return the active flair emoji (empty string if none). Safe after expunge."""
        if not self.active_flair_id:
            return ''
        try:
            from app.questlog_web.helpers import _get_flair_from_cache
            emoji, _ = _get_flair_from_cache(int(self.active_flair_id))
            return emoji
        except Exception:
            return ''

    @property
    def flair_name(self):
        """Return the active flair name (empty string if none). Safe after expunge."""
        if not self.active_flair_id:
            return ''
        try:
            from app.questlog_web.helpers import _get_flair_from_cache
            _, name = _get_flair_from_cache(int(self.active_flair_id))
            return name
        except Exception:
            return ''

    @property
    def flair2_emoji(self):
        """Return the second equipped flair emoji (Champions only). Safe after expunge."""
        if not self.active_flair2_id:
            return ''
        try:
            from app.questlog_web.helpers import _get_flair_from_cache
            emoji, _ = _get_flair_from_cache(int(self.active_flair2_id))
            return emoji or ''
        except Exception:
            return ''

    @property
    def flair2_name(self):
        """Return the second equipped flair name (Champions only). Safe after expunge."""
        if not self.active_flair2_id:
            return ''
        try:
            from app.questlog_web.helpers import _get_flair_from_cache
            _, name = _get_flair_from_cache(int(self.active_flair2_id))
            return name or ''
        except Exception:
            return ''

    def __repr__(self):
        return f"<WebUser {self.username} (id={self.id})>"


class WebReferral(Base):
    """
    Tracks invite/referral links.
    A referrer's personal invite_code is on WebUser; each use of that code
    creates one row here.  Status moves pending → completed when the
    invited user verifies their email.
    """
    __tablename__ = 'web_referrals'

    id = Column(Integer, primary_key=True, autoincrement=True)
    referrer_id = Column(Integer, ForeignKey('web_users.id'), nullable=False, index=True)
    invited_user_id = Column(Integer, ForeignKey('web_users.id'), nullable=True)
    status = Column(String(20), default='pending')  # 'pending' | 'completed'
    created_at = Column(BigInteger, nullable=False)
    completed_at = Column(BigInteger, nullable=True)

    def __repr__(self):
        return f"<WebReferral referrer={self.referrer_id} invited={self.invited_user_id} status={self.status}>"


class WebCommunity(Base):
    """
    Web-native community (can be Discord, Revolt, Matrix, Root, etc.)
    This replaces the Guild model for non-Discord communities.
    """
    __tablename__ = 'web_communities'

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Basic info
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    short_description = Column(String(500), nullable=True)  # For directory listings
    icon_url = Column(String(500), nullable=True)
    banner_url = Column(String(500), nullable=True)

    # Platform info
    platform = Column(Enum(PlatformType, values_callable=lambda obj: [e.value for e in obj]), default=PlatformType.DISCORD)
    platform_id = Column(String(100), nullable=True)  # Discord guild ID, Matrix room ID, etc.
    invite_url = Column(String(500), nullable=True)  # Invite link

    # Owner
    owner_id = Column(Integer, ForeignKey('web_users.id'), nullable=False)
    owner = relationship("WebUser", foreign_keys=[owner_id], back_populates="owned_communities")

    # Unified community group - rows with the same community_group_id are the same
    # community on different platforms (e.g. Fluxer + Discord). XP/HP is shared.
    community_group_id = Column(Integer, nullable=True, index=True)

    # Discovery settings
    allow_discovery = Column(Boolean, default=False)  # Opt-in to public directory
    allow_joins = Column(Boolean, default=False)  # Show invite link publicly

    # Tags for discovery (stored as JSON array string)
    tags = Column(Text, default='[]')  # JSON array of tags
    games = Column(Text, default='[]')  # JSON array of game names/IDs

    # Social links
    website_url = Column(String(500), nullable=True)
    twitter_url = Column(String(500), nullable=True)
    twitch_url = Column(String(500), nullable=True)
    youtube_url = Column(String(500), nullable=True)
    bluesky_url = Column(String(500), nullable=True)
    tiktok_url = Column(String(500), nullable=True)
    instagram_url = Column(String(500), nullable=True)

    # Stats (updated periodically)
    member_count = Column(Integer, default=0)
    online_count = Column(Integer, default=0)
    activity_level = Column(String(20), default='unknown')  # low, medium, high, very_high

    # QuestLog Network membership
    network_member = Column(Boolean, default=False)
    network_approved_at = Column(BigInteger, nullable=True)
    network_status = Column(String(20), default='none')  # none, pending, approved, denied, banned, left
    network_left_at = Column(BigInteger, nullable=True)  # Unix timestamp when owner voluntarily left
    is_primary = Column(Boolean, default=False)  # Primary/featured platform for this community owner
    site_xp_to_guild = Column(Boolean, default=False)  # Opt-in: site XP feeds this guild's leaderboard (admin-approved)

    # Moderation
    is_active = Column(Boolean, default=True)
    is_banned = Column(Boolean, default=False)
    ban_reason = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)

    # Relationships
    members = relationship("WebCommunityMember", back_populates="community")
    lfg_groups = relationship("WebLFGGroup", back_populates="community")

    # Unique constraint: same platform + platform_id can't be registered twice
    __table_args__ = (
        UniqueConstraint('platform', 'platform_id', name='uq_platform_id'),
        Index('idx_web_communities_discovery', 'allow_discovery', 'network_member', 'is_active'),
    )

    def __repr__(self):
        return f"<WebCommunity {self.name} ({self.platform.value})>"


class WebCommunityMember(Base):
    """
    Membership link between WebUser and WebCommunity.
    """
    __tablename__ = 'web_community_members'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('web_users.id'), nullable=False)
    community_id = Column(Integer, ForeignKey('web_communities.id'), nullable=False)

    # Role in community
    role = Column(String(50), default='member')  # member, moderator, admin, owner

    # Timestamps
    joined_at = Column(BigInteger, nullable=False)

    # Relationships
    user = relationship("WebUser", back_populates="communities")
    community = relationship("WebCommunity", back_populates="members")

    __table_args__ = (
        UniqueConstraint('user_id', 'community_id', name='uq_user_community'),
    )


class WebLFGGroup(Base):
    """
    Web-native LFG group (not tied to Discord).
    """
    __tablename__ = 'web_lfg_groups'

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Creator
    creator_id = Column(Integer, ForeignKey('web_users.id'), nullable=False)
    creator = relationship("WebUser", back_populates="lfg_groups")

    # Optional community association
    community_id = Column(Integer, ForeignKey('web_communities.id'), nullable=True)
    community = relationship("WebCommunity", back_populates="lfg_groups")

    # Group info
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)

    # Game info
    game_name = Column(String(200), nullable=False)
    game_id = Column(String(50), nullable=True)  # IGDB ID or Steam App ID
    game_image_url = Column(String(500), nullable=True)

    # Group settings
    group_size = Column(Integer, default=4)
    current_size = Column(Integer, default=1)  # Creator counts as 1

    # Role composition (optional)
    use_roles = Column(Boolean, default=False)
    tanks_needed = Column(Integer, default=0)
    healers_needed = Column(Integer, default=0)
    dps_needed = Column(Integer, default=0)
    support_needed = Column(Integer, default=0)
    # Custom role display schema (JSON array of 4 slot dicts: slot/label/color/icon)
    # null = use default Tank/Healer/DPS/Support labels
    role_schema = Column(Text, nullable=True)

    # Scheduling
    scheduled_time = Column(BigInteger, nullable=True)  # Unix timestamp
    duration_hours = Column(Integer, nullable=True)
    timezone = Column(String(50), nullable=True)

    # Platform for voice/communication
    voice_platform = Column(String(50), nullable=True)  # discord, teamspeak, etc.
    voice_link = Column(String(500), nullable=True)  # Invite link
    server_invite_link = Column(String(500), nullable=True)  # Server invite link shown in embeds

    # Status
    status = Column(String(20), default='open')  # open, full, started, completed, cancelled

    # Discovery
    allow_network_discovery = Column(Boolean, default=True)  # Show in QuestLog Network

    # Origin tracking (when created from Discord/Fluxer via "Post to Network")
    origin_platform = Column(String(20), nullable=True)   # 'discord', 'fluxer', or None (web-native)
    origin_group_id = Column(Integer, nullable=True)      # Source bot group ID (for embed update on join)
    origin_guild_id = Column(String(64), nullable=True)   # Discord guild_id or Fluxer guild_id
    origin_guild_name = Column(String(200), nullable=True) # Human-readable guild name for display

    # Public share token (non-guessable 8-char alphanumeric, used in URLs instead of integer ID)
    share_token = Column(String(8), nullable=True, unique=True, index=True)

    # Timestamps
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)
    started_at = Column(BigInteger, nullable=True)
    completed_at = Column(BigInteger, nullable=True)

    __table_args__ = (
        Index('idx_web_lfg_status', 'status', 'scheduled_time'),
        Index('idx_web_lfg_game', 'game_name'),
    )

    def __repr__(self):
        return f"<WebLFGGroup {self.title} ({self.game_name})>"


class WebLFGMember(Base):
    """
    Members who joined a web LFG group.
    """
    __tablename__ = 'web_lfg_members'

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(Integer, ForeignKey('web_lfg_groups.id'), nullable=False)
    user_id = Column(Integer, ForeignKey('web_users.id'), nullable=False)

    # Role in group (if using role composition)
    role = Column(String(20), nullable=True)  # tank, healer, dps, support

    # Game-specific selections (class, spec, job, activity, etc.) stored as JSON
    selections = Column(Text, nullable=True)

    # Leadership
    is_creator = Column(Boolean, default=False)
    is_co_leader = Column(Boolean, default=False)

    # Status
    status = Column(String(20), default='joined')  # joined, confirmed, left, kicked

    # Timestamps
    joined_at = Column(BigInteger, nullable=False)
    left_at = Column(BigInteger, nullable=True)

    __table_args__ = (
        UniqueConstraint('group_id', 'user_id', name='uq_lfg_member'),
    )


class WebCreatorProfile(Base):
    """
    Creator profile for Featured Creators / Creator Discovery.
    """
    __tablename__ = 'web_creator_profiles'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('web_users.id'), nullable=False, unique=True)
    user = relationship("WebUser", back_populates="creator_profile")

    # Profile info
    display_name = Column(String(100), nullable=False)
    bio = Column(Text, nullable=True)
    avatar_url = Column(String(500), nullable=True)
    banner_url = Column(String(500), nullable=True)

    # Platform links
    twitch_url = Column(String(500), nullable=True)
    youtube_url = Column(String(500), nullable=True)
    twitter_url = Column(String(500), nullable=True)
    tiktok_url = Column(String(500), nullable=True)
    kick_url = Column(String(500), nullable=True)          # Kick streaming
    instagram_url = Column(String(500), nullable=True)
    facebook_url = Column(String(500), nullable=True)
    bluesky_url = Column(String(500), nullable=True)
    website_url = Column(String(500), nullable=True)
    discord_url = Column(String(500), nullable=True)
    matrix_url = Column(String(500), nullable=True)       # Matrix room/space
    valor_url = Column(String(500), nullable=True)         # Valor chat
    fluxer_url = Column(String(500), nullable=True)        # Fluxer
    kloak_url = Column(String(500), nullable=True)         # Kloak
    teamspeak_url = Column(String(500), nullable=True)     # TeamSpeak
    revolt_url = Column(String(500), nullable=True)        # Stoat (formerly Revolt)
    root_url = Column(String(500), nullable=True)          # Root

    # Twitch OAuth (encrypted tokens)
    twitch_user_id = Column(String(100), nullable=True)
    twitch_display_name = Column(String(100), nullable=True)
    twitch_access_token = Column(Text, nullable=True)   # Fernet-encrypted
    twitch_refresh_token = Column(Text, nullable=True)   # Fernet-encrypted
    twitch_token_expires = Column(BigInteger, nullable=True)
    twitch_follower_count = Column(Integer, default=0)
    twitch_last_synced = Column(BigInteger, nullable=True)

    # YouTube OAuth (encrypted tokens)
    youtube_channel_id = Column(String(100), nullable=True)
    youtube_channel_name = Column(String(200), nullable=True)
    youtube_access_token = Column(Text, nullable=True)   # Fernet-encrypted
    youtube_refresh_token = Column(Text, nullable=True)  # Fernet-encrypted
    youtube_token_expires = Column(BigInteger, nullable=True)
    youtube_subscriber_count = Column(Integer, default=0)
    youtube_video_count = Column(Integer, default=0)
    youtube_last_synced = Column(BigInteger, nullable=True)

    # Kick OAuth (encrypted tokens)
    kick_user_id = Column(String(100), nullable=True)
    kick_display_name = Column(String(100), nullable=True)
    kick_access_token = Column(Text, nullable=True)      # Fernet-encrypted
    kick_refresh_token = Column(Text, nullable=True)     # Fernet-encrypted
    kick_token_expires = Column(BigInteger, nullable=True)

    # Kick channel info (for live status checks)
    kick_slug = Column(String(100), nullable=True)         # Kick channel slug for API checks
    kick_follower_count = Column(Integer, default=0)
    kick_last_synced = Column(BigInteger, nullable=True)

    # Categories/tags (JSON array)
    categories = Column(Text, default='[]')  # e.g., ["fps", "mmo", "variety"]
    games = Column(Text, default='[]')  # Games they play

    # Discovery settings
    allow_discovery = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)

    # Featured creator tracking
    featured_at = Column(BigInteger, nullable=True)  # Last time featured
    times_featured = Column(Integer, default=0)

    # Creator of the Week / Month (COTW/COTM)
    is_current_cotw = Column(Boolean, default=False)
    is_current_cotm = Column(Boolean, default=False)
    cotw_last_featured = Column(BigInteger, nullable=True)  # Last time they were COTW
    cotm_last_featured = Column(BigInteger, nullable=True)  # Last time they were COTM

    # Stats (can be updated periodically)
    follower_count = Column(Integer, default=0)

    # Latest YouTube video (synced by youtube_service)
    latest_youtube_video_id = Column(String(50), nullable=True)
    latest_youtube_video_title = Column(String(300), nullable=True)
    latest_youtube_thumbnail_url = Column(String(500), nullable=True)
    latest_youtube_video_published_at = Column(BigInteger, nullable=True)  # Unix epoch

    # Latest stream info (set when live ends)
    latest_stream_title = Column(String(300), nullable=True)
    latest_stream_thumbnail_url = Column(String(500), nullable=True)
    latest_stream_platform = Column(String(20), nullable=True)
    latest_stream_ended_at = Column(BigInteger, nullable=True)  # Unix epoch

    # Privacy / display options
    show_steam_on_profile = Column(Boolean, default=False)  # Opt-in: show current Steam game on creator card

    # Timestamps
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)

    def __repr__(self):
        return f"<WebCreatorProfile {self.display_name}>"


class WebLFGGameConfig(Base):
    """
    LFG game configuration - defines which games are available for LFG groups.
    Admin-managed. Similar to Discord bot's LFGGame model.
    """
    __tablename__ = 'web_lfg_game_configs'

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Game info
    game_name = Column(String(200), nullable=False, unique=True)
    game_short = Column(String(20), nullable=True)  # Short code e.g. "MHW"
    steam_app_id = Column(Integer, nullable=True)
    cover_url = Column(String(500), nullable=True)

    # Group defaults
    default_group_size = Column(Integer, default=4)
    max_group_size = Column(Integer, default=25)

    # Role composition mode: 'none', 'generic' (tank/healer/dps/support), 'custom'
    role_mode = Column(String(20), default='none')
    custom_roles = Column(Text, nullable=True)  # JSON array for custom role names

    # Status
    enabled = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)

    # Timestamps
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)

    def __repr__(self):
        return f"<WebLFGGameConfig {self.game_name}>"


class WebSteamSearchConfig(Base):
    """
    Steam-based game discovery search configuration.
    Admin creates searches using Steam tags (no IGDB).
    """
    __tablename__ = 'web_steam_search_configs'

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Search identity
    name = Column(String(200), nullable=False)
    enabled = Column(Boolean, default=True)

    # Steam tag filters (JSON arrays of tag IDs/names)
    steam_tags = Column(Text, default='[]')  # JSON array of Steam tag names
    exclude_tags = Column(Text, default='[]')  # Tags to exclude

    # Filters
    coming_soon_only = Column(Boolean, default=True)
    min_reviews = Column(Integer, default=0)
    min_price = Column(Integer, nullable=True)  # In cents, null = free ok
    max_price = Column(Integer, nullable=True)  # In cents, null = no limit
    os_filter = Column(Text, default='[]')  # JSON: ["windows", "mac", "linux"]

    # Display
    max_results = Column(Integer, default=50)
    show_on_site = Column(Boolean, default=True)

    # Schedule — admin controls how often this runs (minutes)
    fetch_interval = Column(Integer, default=1440)  # 1440 = once per day

    # Console enrichment via IGDB
    include_consoles = Column(Boolean, default=False)

    # Tracking
    last_run_at = Column(BigInteger, nullable=True)
    last_result_count = Column(Integer, default=0)
    last_error = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)

    def __repr__(self):
        return f"<WebSteamSearchConfig {self.name}>"


class WebFoundGame(Base):
    """
    Games found via Steam search configs.
    """
    __tablename__ = 'web_found_games'

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Steam data (primary)
    steam_app_id = Column(Integer, nullable=False, unique=True)
    name = Column(String(500), nullable=False)
    steam_url = Column(String(500), nullable=False)
    cover_url = Column(String(500), nullable=True)
    header_url = Column(String(500), nullable=True)

    # Details
    summary = Column(Text, nullable=True)
    release_date = Column(String(100), nullable=True)
    developer = Column(String(300), nullable=True)
    publisher = Column(String(300), nullable=True)
    price = Column(String(50), nullable=True)

    # Tags & categories (JSON arrays)
    steam_tags = Column(Text, default='[]')
    genres = Column(Text, default='[]')
    platforms = Column(Text, default='[]')  # ["windows", "mac", "linux"]

    # Metrics
    review_score = Column(Integer, nullable=True)  # 0-100
    review_count = Column(Integer, default=0)

    # Which search found it
    search_config_id = Column(Integer, ForeignKey('web_steam_search_configs.id'), nullable=True)

    # IGDB console data (populated when include_consoles=True on the search config)
    igdb_id = Column(Integer, nullable=True)
    igdb_url = Column(String(500), nullable=True)
    console_platforms = Column(Text, default='[]')  # JSON: ["PS5", "Xbox Series X|S", "Nintendo Switch"]

    # Display control
    is_featured = Column(Boolean, default=False)
    is_hidden = Column(Boolean, default=False)  # Admin can hide games

    # Timestamps
    found_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)

    __table_args__ = (
        Index('idx_web_found_games_featured', 'is_featured', 'found_at'),
    )

    def __repr__(self):
        return f"<WebFoundGame {self.name}>"


class WebRaffle(Base):
    """
    Web-native raffle system.
    """
    __tablename__ = 'web_raffles'

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Raffle info
    title = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)
    prize_description = Column(Text, nullable=True)
    image_url = Column(String(500), nullable=True)

    # Entry settings
    cost_hero_points = Column(Integer, default=0)  # 0 = free entry
    max_entries_per_user = Column(Integer, default=1)
    max_winners = Column(Integer, default=1)

    # Timing
    start_at = Column(BigInteger, nullable=True)
    end_at = Column(BigInteger, nullable=True)
    auto_pick = Column(Boolean, default=False)  # Auto-pick winners at end_at

    # Status
    is_active = Column(Boolean, default=True)
    is_ended = Column(Boolean, default=False)
    winners = Column(Text, default='[]')  # JSON array of winner user IDs
    winners_announced = Column(Boolean, default=False)

    # Created by (admin)
    created_by_id = Column(Integer, ForeignKey('web_users.id'), nullable=True)

    # Timestamps
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)

    def __repr__(self):
        return f"<WebRaffle {self.title}>"


class WebRaffleEntry(Base):
    """
    Raffle entry/ticket.
    """
    __tablename__ = 'web_raffle_entries'

    id = Column(Integer, primary_key=True, autoincrement=True)
    raffle_id = Column(Integer, ForeignKey('web_raffles.id'), nullable=False)
    user_id = Column(Integer, ForeignKey('web_users.id'), nullable=False)

    tickets = Column(Integer, default=1)

    # Timestamps
    created_at = Column(BigInteger, nullable=False)

    __table_args__ = (
        UniqueConstraint('raffle_id', 'user_id', name='uq_raffle_entry'),
    )


class WebSiteConfig(Base):
    """
    Global site configuration key-value store for admin settings.
    """
    __tablename__ = 'web_site_config'

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(100), nullable=False, unique=True)
    value = Column(Text, nullable=True)
    updated_at = Column(BigInteger, nullable=False)

    def __repr__(self):
        return f"<WebSiteConfig {self.key}={self.value}>"


class WebRSSFeed(Base):
    """
    RSS feeds for the web-native version.
    """
    __tablename__ = 'web_rss_feeds'

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Feed info
    name = Column(String(200), nullable=False)
    url = Column(String(500), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    icon_url = Column(String(500), nullable=True)

    # Fetch schedule
    fetch_interval = Column(Integer, default=15)  # Minutes between polls: 15, 30, 60, 360, 1440

    # Status
    is_active = Column(Boolean, default=True)
    last_fetched_at = Column(BigInteger, nullable=True)
    last_error = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)


class WebRSSArticle(Base):
    """
    Cached RSS articles.
    """
    __tablename__ = 'web_rss_articles'

    id = Column(Integer, primary_key=True, autoincrement=True)
    feed_id = Column(Integer, ForeignKey('web_rss_feeds.id'), nullable=False)

    # Article info
    title = Column(String(500), nullable=False)
    url = Column(String(500), nullable=False)
    summary = Column(Text, nullable=True)
    author = Column(String(200), nullable=True)
    image_url = Column(String(500), nullable=True)

    # Unique identifier from feed
    guid = Column(String(500), nullable=False)

    # Timestamps
    published_at = Column(BigInteger, nullable=True)
    fetched_at = Column(BigInteger, nullable=False)

    __table_args__ = (
        UniqueConstraint('feed_id', 'guid', name='uq_feed_guid'),
        Index('idx_rss_articles_published', 'published_at'),
    )


class AdminAuditLog(Base):
    """
    Audit log for all admin actions. Every admin action is logged with
    who did it, what they did, from what IP, and when.
    """
    __tablename__ = 'web_admin_audit_log'

    id = Column(Integer, primary_key=True, autoincrement=True)
    admin_user_id = Column(Integer, ForeignKey('web_users.id'), nullable=False)
    admin_username = Column(String(100), nullable=True)
    admin_steam_id = Column(String(50), nullable=True)  # legacy column, kept for schema compat
    action = Column(String(200), nullable=False)  # e.g. "make_admin", "ban_user", "create_raffle"
    target_type = Column(String(50), nullable=True)  # e.g. "user", "community", "raffle"
    target_id = Column(Integer, nullable=True)
    details = Column(Text, nullable=True)  # JSON details of the action
    ip_address = Column(String(45), nullable=False)  # IPv4 or IPv6
    user_agent = Column(String(500), nullable=True)
    created_at = Column(BigInteger, nullable=False)

    __table_args__ = (
        Index('idx_admin_audit_admin', 'admin_user_id', 'created_at'),
        Index('idx_admin_audit_action', 'action', 'created_at'),
        Index('idx_admin_audit_ip', 'ip_address', 'created_at'),
    )


# =============================================================================
# SOCIAL LAYER MODELS (QuestLog Network)
# =============================================================================

class WebFollow(Base):
    """
    Asymmetric follow system. A follows B != B follows A.
    Mutual follows (A follows B AND B follows A) = friends.
    """
    __tablename__ = 'web_follows'

    id = Column(Integer, primary_key=True, autoincrement=True)
    follower_id = Column(Integer, ForeignKey('web_users.id'), nullable=False)
    following_id = Column(Integer, ForeignKey('web_users.id'), nullable=False)
    created_at = Column(BigInteger, nullable=False)

    follower_user = relationship("WebUser", foreign_keys=[follower_id])
    following_user = relationship("WebUser", foreign_keys=[following_id])

    __table_args__ = (
        UniqueConstraint('follower_id', 'following_id', name='uq_follow'),
        Index('idx_follow_follower', 'follower_id', 'created_at'),
        Index('idx_follow_following', 'following_id', 'created_at'),
    )


class WebPost(Base):
    """
    Social feed post. Supports text, images, video embeds, and game tags.
    Videos are NEVER uploaded - only embed links from whitelisted platforms.
    Images stored locally and served via nginx.
    """
    __tablename__ = 'web_posts'

    id = Column(Integer, primary_key=True, autoincrement=True)
    public_id = Column(String(12), nullable=True, unique=True, index=True)  # Short random ID for public URLs
    author_id = Column(Integer, ForeignKey('web_users.id'), nullable=False)

    # Content
    content = Column(Text, nullable=True)  # Max 2000 chars enforced in code
    post_type = Column(String(20), nullable=False, default='text')  # text, image, video_embed, game_tag

    # Primary media (for single-image posts or video embeds)
    media_url = Column(String(500), nullable=True)
    thumbnail_url = Column(String(500), nullable=True)

    # Video embed fields (whitelist-only: YouTube, Twitch, TikTok, IG, Kick, X)
    embed_platform = Column(String(20), nullable=True)
    embed_id = Column(String(200), nullable=True)

    # Game tag (link post to a game)
    game_tag_id = Column(Integer, ForeignKey('web_found_games.id', ondelete='SET NULL'), nullable=True)
    game_tag_name = Column(String(500), nullable=True)  # Cached name survives game deletion
    game_tag_steam_id = Column(Integer, nullable=True)  # Steam app ID for store link

    # Link preview (OG metadata fetched at post creation time, stored as JSON text)
    link_preview = Column(Text, nullable=True)

    # Flags
    is_pinned = Column(Boolean, default=False)
    is_deleted = Column(Boolean, default=False)
    is_hidden = Column(Boolean, default=False)  # Admin-hidden

    # Denormalized counters
    like_count = Column(Integer, default=0)
    comment_count = Column(Integer, default=0)
    repost_count = Column(Integer, default=0)

    # Edit tracking
    edited_at = Column(BigInteger, nullable=True)   # Timestamp of last edit (null = never edited)
    edit_count = Column(Integer, default=0)          # How many times edited

    # Timestamps
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)

    # Relationships
    author = relationship("WebUser", back_populates="posts", foreign_keys=[author_id])
    images = relationship("WebPostImage", back_populates="post", order_by="WebPostImage.sort_order")
    likes = relationship("WebLike", back_populates="post")
    comments = relationship("WebComment", back_populates="post")

    __table_args__ = (
        Index('idx_post_author', 'author_id', 'created_at'),
        Index('idx_post_feed', 'is_deleted', 'is_hidden', 'created_at'),
        Index('idx_post_game_tag', 'game_tag_id'),
    )


class WebPostEdit(Base):
    """
    Edit history for a post. One row per edit, storing the content BEFORE the edit.
    This lets us show the full edit history ("show original").
    """
    __tablename__ = 'web_post_edits'

    id = Column(Integer, primary_key=True, autoincrement=True)
    post_id = Column(Integer, ForeignKey('web_posts.id', ondelete='CASCADE'), nullable=False)
    content_before = Column(Text, nullable=False)
    edited_at = Column(BigInteger, nullable=False)  # When the edit happened

    __table_args__ = (
        Index('idx_post_edit_post', 'post_id', 'edited_at'),
    )


class WebPostImage(Base):
    """
    Multiple images per post (up to 4). Stored locally as WebP.
    GIFs kept as-is for animation support.
    """
    __tablename__ = 'web_post_images'

    id = Column(Integer, primary_key=True, autoincrement=True)
    post_id = Column(Integer, ForeignKey('web_posts.id', ondelete='CASCADE'), nullable=False)
    image_url = Column(String(500), nullable=False)
    thumbnail_url = Column(String(500), nullable=False)
    sort_order = Column(Integer, default=0)  # 0-3
    file_size = Column(Integer, default=0)  # Bytes
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    created_at = Column(BigInteger, nullable=False)

    post = relationship("WebPost", back_populates="images")

    __table_args__ = (
        Index('idx_post_image_post', 'post_id', 'sort_order'),
    )


class WebLike(Base):
    """Post like. One like per user per post."""
    __tablename__ = 'web_likes'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('web_users.id'), nullable=False)
    post_id = Column(Integer, ForeignKey('web_posts.id', ondelete='CASCADE'), nullable=False)
    created_at = Column(BigInteger, nullable=False)

    user = relationship("WebUser")
    post = relationship("WebPost", back_populates="likes")

    __table_args__ = (
        UniqueConstraint('user_id', 'post_id', name='uq_like'),
        Index('idx_like_post', 'post_id'),
        Index('idx_like_user', 'user_id'),
    )


class WebComment(Base):
    """
    Post comment with threaded replies (max 1 level deep).
    parent_id = NULL means top-level comment.
    parent_id = <comment_id> means reply to that comment.
    """
    __tablename__ = 'web_comments'

    id = Column(Integer, primary_key=True, autoincrement=True)
    post_id = Column(Integer, ForeignKey('web_posts.id', ondelete='CASCADE'), nullable=False)
    author_id = Column(Integer, ForeignKey('web_users.id'), nullable=False)
    content = Column(Text, nullable=False)  # Max 500 chars enforced in code
    parent_id = Column(Integer, ForeignKey('web_comments.id', ondelete='CASCADE'), nullable=True)

    is_deleted = Column(Boolean, default=False)
    like_count = Column(Integer, default=0)

    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)

    post = relationship("WebPost", back_populates="comments")
    author = relationship("WebUser")
    parent = relationship("WebComment", remote_side=[id], backref="replies")
    comment_likes = relationship("WebCommentLike", back_populates="comment")

    __table_args__ = (
        Index('idx_comment_post', 'post_id', 'created_at'),
        Index('idx_comment_author', 'author_id'),
        Index('idx_comment_parent', 'parent_id'),
    )


class WebCommentLike(Base):
    """Comment like. One like per user per comment."""
    __tablename__ = 'web_comment_likes'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('web_users.id'), nullable=False)
    comment_id = Column(Integer, ForeignKey('web_comments.id', ondelete='CASCADE'), nullable=False)
    created_at = Column(BigInteger, nullable=False)

    user = relationship("WebUser")
    comment = relationship("WebComment", back_populates="comment_likes")

    __table_args__ = (
        UniqueConstraint('user_id', 'comment_id', name='uq_comment_like'),
        Index('idx_comment_like_comment', 'comment_id'),
    )


class WebNotification(Base):
    """
    Activity notification. Created on follow, like, comment, mention, etc.
    Polymorphic target via target_type + target_id.
    """
    __tablename__ = 'web_notifications'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('web_users.id'), nullable=False)   # Recipient
    actor_id = Column(Integer, ForeignKey('web_users.id'), nullable=False)  # Who caused it
    notification_type = Column(String(20), nullable=False)  # follow, like, comment, repost, mention, comment_like
    target_type = Column(String(20), nullable=True)  # post, comment, user, lfg_group
    target_id = Column(Integer, nullable=True)
    message = Column(String(500), nullable=True)  # Preview text
    is_read = Column(Boolean, default=False)
    created_at = Column(BigInteger, nullable=False)

    user = relationship("WebUser", foreign_keys=[user_id], back_populates="notifications")
    actor = relationship("WebUser", foreign_keys=[actor_id])

    __table_args__ = (
        Index('idx_notification_user', 'user_id', 'is_read', 'created_at'),
        Index('idx_notification_actor', 'actor_id'),
        Index('idx_notification_target', 'target_type', 'target_id'),
    )


class WebUserBlock(Base):
    """
    User blocking. Blocks prevent ALL interaction:
    - Cannot follow each other
    - Cannot like/comment on each other's posts
    - Hidden from each other's feeds and profiles
    """
    __tablename__ = 'web_user_blocks'

    id = Column(Integer, primary_key=True, autoincrement=True)
    blocker_id = Column(Integer, ForeignKey('web_users.id'), nullable=False)
    blocked_id = Column(Integer, ForeignKey('web_users.id'), nullable=False)
    created_at = Column(BigInteger, nullable=False)

    blocker = relationship("WebUser", foreign_keys=[blocker_id])
    blocked = relationship("WebUser", foreign_keys=[blocked_id])

    __table_args__ = (
        UniqueConstraint('blocker_id', 'blocked_id', name='uq_block'),
        Index('idx_block_blocker', 'blocker_id'),
        Index('idx_block_blocked', 'blocked_id'),
    )


class WebHeroPointEvent(Base):
    """
    Ledger of every Hero Point award.
    Used for daily cap enforcement, history display, and Matrix/Discord cross-platform tracking.
    """
    __tablename__ = 'web_hero_point_events'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('web_users.id'), nullable=False)
    action_type = Column(String(50), nullable=False)   # daily_visit, like, follow, share, post, steam_achievement, steam_hours, invite
    points = Column(Integer, nullable=False)
    source = Column(String(20), default='web')         # web, matrix, discord
    ref_id = Column(String(100), nullable=True)        # e.g. post_id, steam app_id
    created_at = Column(BigInteger, nullable=False)

    __table_args__ = (
        Index('idx_hp_user_action_date', 'user_id', 'action_type', 'created_at'),
    )


class WebXpEvent(Base):
    """
    Ledger of every XP award.
    XP is the primary earning currency; HP is derived from XP and level-ups.
    """
    __tablename__ = 'web_xp_events'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('web_users.id'), nullable=False)
    action_type = Column(String(50), nullable=False)  # daily_visit, like, follow, post, share, steam_achievement, invite
    xp = Column(Integer, nullable=False)
    source = Column(String(20), default='web')         # web, discord, matrix
    ref_id = Column(String(100), nullable=True)        # e.g. post_id, steam app_id
    created_at = Column(BigInteger, nullable=False)

    __table_args__ = (
        Index('idx_xp_user_action_date', 'user_id', 'action_type', 'created_at'),
    )


class WebLegacyEvent(Base):
    """
    Ledger of every Legacy point award.
    Legacy = impact metric (how much you matter to others).
    XP = activity metric (how much you do).
    """
    __tablename__ = 'web_legacy_events'

    id          = Column(Integer, primary_key=True, autoincrement=True)
    user_id     = Column(Integer, ForeignKey('web_users.id'), nullable=False)
    action_type = Column(String(60), nullable=False)
    points      = Column(Integer, nullable=False)
    source      = Column(String(20), default='web')   # web, discord, fluxer, 7dtd, dayz, minecraft, palworld, etc
    ref_id      = Column(String(100), nullable=True)  # prevent duplicate awards
    created_at  = Column(BigInteger, nullable=False)

    __table_args__ = (
        Index('idx_legacy_user_action', 'user_id', 'action_type', 'created_at'),
    )


class WebLegacyNomination(Base):
    """One nomination per nominator per category per month."""
    __tablename__ = 'web_legacy_nominations'

    id                       = Column(Integer, primary_key=True, autoincrement=True)
    month_year               = Column(String(7),  nullable=False)          # YYYY-MM
    category                 = Column(String(50), nullable=False)          # community, 7dtd, valheim, etc.
    nominated_user_id        = Column(Integer, ForeignKey('web_users.id'), nullable=False)
    nominated_by_web_user_id = Column(Integer, ForeignKey('web_users.id'), nullable=True)
    nominated_by_fluxer_id   = Column(String(25), nullable=True)
    guild_id                 = Column(String(25), nullable=True)
    platform                 = Column(String(10), nullable=False, default='web')
    reason                   = Column(Text, nullable=True)
    vote_count               = Column(Integer, nullable=False, default=0)
    awarded                  = Column(SmallInteger, nullable=False, default=0)
    created_at               = Column(BigInteger, nullable=False)
    updated_at               = Column(BigInteger, nullable=False)

    __table_args__ = (
        Index('idx_nom_month_category', 'month_year', 'category'),
        Index('idx_nom_user', 'nominated_user_id'),
    )


class WebFlair(Base):
    """Admin-created cosmetic flair that users can purchase with Hero Points."""
    __tablename__ = 'web_flairs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    emoji = Column(String(20), default='')
    description = Column(String(300), nullable=True)
    flair_type = Column(Enum('normal', 'seasonal', 'exclusive', 'hero'), default='normal')
    hp_cost = Column(Integer, default=0)
    equippable = Column(SmallInteger, nullable=False, default=1, server_default='1')  # 0 = trophy only, cannot equip
    enabled = Column(Boolean, default=True)
    display_order = Column(Integer, default=0)
    available_from = Column(BigInteger, nullable=True)   # Unix ts: flair not claimable before this date (None = always)
    available_until = Column(BigInteger, nullable=True)  # Unix ts: flair not claimable after this date (None = always)
    created_at = Column(BigInteger, nullable=False, default=lambda: int(time.time()))
    updated_at = Column(BigInteger, nullable=False, default=lambda: int(time.time()))

    owners = relationship('WebUserFlair', back_populates='flair', cascade='all, delete-orphan')


class WebUserFlair(Base):
    """Junction table: flairs owned (and optionally equipped) by a user."""
    __tablename__ = 'web_user_flairs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('web_users.id'), nullable=False)
    flair_id = Column(Integer, ForeignKey('web_flairs.id'), nullable=False)
    is_equipped = Column(Boolean, default=False)
    purchased_at = Column(BigInteger, nullable=False, default=lambda: int(time.time()))

    user = relationship('WebUser', back_populates='user_flairs')
    flair = relationship('WebFlair', back_populates='owners')

    __table_args__ = (
        UniqueConstraint('user_id', 'flair_id', name='uq_uf_user_flair'),
        Index('idx_uf_user', 'user_id'),
    )


class WebRankTitle(Base):
    """
    Admin-editable rank titles awarded at level milestones.
    Users get the title of the highest milestone they have reached.
    """
    __tablename__ = 'web_rank_titles'

    id = Column(Integer, primary_key=True, autoincrement=True)
    level = Column(Integer, nullable=False, unique=True)   # milestone level required
    title = Column(String(100), nullable=False)
    icon = Column(String(50), default='')                  # FontAwesome class
    created_at = Column(BigInteger, nullable=False, default=lambda: int(time.time()))
    updated_at = Column(BigInteger, nullable=False, default=lambda: int(time.time()))


# =============================================================================
# SERVER ROTATION VOTING
# =============================================================================

class WebServerPoll(Base):
    """
    Admin-created poll for voting on the next community game server rotation.
    Only one poll should be active at a time (enforced in admin).
    """
    __tablename__ = 'web_server_polls'

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)

    is_active = Column(Boolean, default=False)   # visible + accepting votes
    is_ended = Column(Boolean, default=False)    # voting closed, winner declared
    show_results_before_end = Column(Boolean, default=True)  # show live tally

    ends_at = Column(BigInteger, nullable=True)  # optional deadline (Unix epoch)
    winner_option_id = Column(Integer, ForeignKey('web_server_poll_options.id',
                              use_alter=True, name='fk_poll_winner'), nullable=True)

    created_by_id = Column(Integer, ForeignKey('web_users.id'), nullable=True)
    created_at = Column(BigInteger, nullable=False, default=lambda: int(time.time()))
    updated_at = Column(BigInteger, nullable=False, default=lambda: int(time.time()))

    def __repr__(self):
        return f"<WebServerPoll {self.title!r} active={self.is_active}>"


class WebServerPollOption(Base):
    """
    A single game choice within a WebServerPoll.
    """
    __tablename__ = 'web_server_poll_options'

    id = Column(Integer, primary_key=True, autoincrement=True)
    poll_id = Column(Integer, ForeignKey('web_server_polls.id'), nullable=False)
    game_name = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)
    image_url = Column(String(500), nullable=True)
    steam_appid = Column(String(50), nullable=True)  # auto-load Steam header image
    sort_order = Column(Integer, default=0)
    vote_count = Column(Integer, default=0)  # denormalized counter
    created_at = Column(BigInteger, nullable=False, default=lambda: int(time.time()))

    def __repr__(self):
        return f"<WebServerPollOption {self.game_name!r} votes={self.vote_count}>"


class WebServerPollVote(Base):
    """
    One vote per user per poll. Records which option they chose.
    """
    __tablename__ = 'web_server_poll_votes'

    id = Column(Integer, primary_key=True, autoincrement=True)
    poll_id = Column(Integer, ForeignKey('web_server_polls.id'), nullable=False)
    option_id = Column(Integer, ForeignKey('web_server_poll_options.id'), nullable=False)
    user_id = Column(Integer, ForeignKey('web_users.id'), nullable=False)
    created_at = Column(BigInteger, nullable=False, default=lambda: int(time.time()))

    __table_args__ = (
        UniqueConstraint('poll_id', 'user_id', name='uq_poll_user_vote'),
        Index('idx_poll_votes_option', 'option_id'),
    )

    def __repr__(self):
        return f"<WebServerPollVote poll={self.poll_id} user={self.user_id} option={self.option_id}>"


class WebUserTOTP(Base):
    """TOTP 2FA record for a user. One row per user, optional."""
    __tablename__ = 'web_user_totp'

    id           = Column(Integer, primary_key=True, autoincrement=True)
    user_id      = Column(Integer, ForeignKey('web_users.id', ondelete='CASCADE'), nullable=False, unique=True)
    secret_enc   = Column(Text, nullable=False)       # Fernet-encrypted TOTP secret
    is_enabled   = Column(Boolean, default=False)
    backup_codes = Column(Text, default='[]')         # JSON list of bcrypt-hashed backup codes
    created_at   = Column(BigInteger, nullable=False)
    enabled_at   = Column(BigInteger, nullable=True)

    def __repr__(self):
        return f"<WebUserTOTP user={self.user_id} enabled={self.is_enabled}>"


class WebGiveaway(Base):
    """
    A giveaway event. Admin creates drafts, then launches them to go live.
    Launching sends a global notification to all users.
    """
    __tablename__ = 'web_giveaways'

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    prize = Column(String(500), nullable=False)
    image_url = Column(String(500), nullable=True)
    status = Column(String(20), default='draft')  # draft, active, closed, winner_selected
    ends_at = Column(BigInteger, nullable=True)    # optional deadline timestamp
    entry_count = Column(Integer, default=0)       # denormalized: unique user count
    max_winners = Column(Integer, default=1, nullable=False)
    max_entries_per_user = Column(Integer, default=1, nullable=False)  # max tickets per user
    hp_per_extra_ticket = Column(Integer, default=0, nullable=False)   # 0 = no multi-entry
    winners_json = Column(Text, nullable=True)     # JSON list of winner user_ids
    winner_user_id = Column(Integer, ForeignKey('web_users.id'), nullable=True)
    created_by_id = Column(Integer, ForeignKey('web_users.id'), nullable=False)
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)
    launched_at = Column(BigInteger, nullable=True)
    closed_at = Column(BigInteger, nullable=True)

    winner = relationship("WebUser", foreign_keys=[winner_user_id])
    created_by = relationship("WebUser", foreign_keys=[created_by_id])

    __table_args__ = (
        Index('idx_giveaway_status', 'status'),
    )

    def __repr__(self):
        return f"<WebGiveaway {self.title!r} status={self.status}>"


class WebGiveawayEntry(Base):
    """
    A user's entry into a giveaway. One entry per user per giveaway.
    """
    __tablename__ = 'web_giveaway_entries'

    id = Column(Integer, primary_key=True, autoincrement=True)
    giveaway_id = Column(Integer, ForeignKey('web_giveaways.id'), nullable=False)
    user_id = Column(Integer, ForeignKey('web_users.id'), nullable=False)
    entered_at = Column(BigInteger, nullable=False)
    ticket_count = Column(Integer, default=1, nullable=False)  # how many chances to win

    user = relationship("WebUser", foreign_keys=[user_id])

    __table_args__ = (
        UniqueConstraint('giveaway_id', 'user_id', name='uq_giveaway_entry'),
        Index('idx_giveaway_entry_giveaway', 'giveaway_id'),
        Index('idx_giveaway_entry_user', 'user_id'),
    )

    def __repr__(self):
        return f"<WebGiveawayEntry giveaway={self.giveaway_id} user={self.user_id}>"


class WebFluxerWebhookConfig(Base):
    """
    Stores Fluxer webhook URLs for each event type.
    The web platform posts embeds to these URLs when events occur.
    One row per event_type; update in place via admin panel.
    """
    __tablename__ = 'web_fluxer_webhook_configs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(String(50), nullable=False, unique=True)  # new_post, new_member, giveaway_start, giveaway_winner
    label = Column(String(100), nullable=False)  # human-friendly name shown in admin
    webhook_url = Column(String(1000), nullable=True)  # legacy - no longer used
    discord_webhook_url = Column(String(1000), nullable=True)  # Discord webhook URL for new_post broadcasts
    is_enabled = Column(Boolean, default=False)
    guild_id = Column(String(32), nullable=True)
    channel_id = Column(String(32), nullable=True)
    channel_name = Column(String(200), nullable=True)
    embed_color = Column(String(7), nullable=True)      # hex like #5865F2
    message_template = Column(Text, nullable=True)      # welcome message body (new_member only)
    embed_title = Column(String(255), nullable=True)    # custom embed title override
    embed_footer = Column(String(255), nullable=True)   # custom embed footer override
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)

    def __repr__(self):
        return f"<WebFluxerWebhookConfig {self.event_type} enabled={self.is_enabled}>"


class WebBroadcastUser(Base):
    """Users whose posts are fanned out to Fluxer and Discord channels."""
    __tablename__ = 'web_broadcast_users'

    id       = Column(Integer, primary_key=True, autoincrement=True)
    user_id  = Column(Integer, nullable=False, unique=True)
    added_at = Column(BigInteger, nullable=False)


class WebCommunityBotConfig(Base):
    """
    Per-community bot channel subscriptions for QuestLog Network announcements.
    One row per (platform, guild_id, event_type).
    Populated when a community admin runs !setup <event> in their server,
    or manually via the Fluxer bot dashboard at /ql/dashboard/fluxer/.
    """
    __tablename__ = 'web_community_bot_configs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    community_id = Column(Integer, ForeignKey('web_communities.id'), nullable=True, index=True)

    # Which platform/server this config is for
    platform = Column(String(20), nullable=False)        # discord, fluxer
    guild_id = Column(String(100), nullable=False)       # Discord guild ID or Fluxer guild ID
    guild_name = Column(String(200), nullable=True)

    # Which channel to post to
    channel_id = Column(String(100), nullable=True)
    channel_name = Column(String(200), nullable=True)
    webhook_url = Column(String(1000), nullable=True)    # Webhook URL for posting embeds

    # What event to subscribe to
    event_type = Column(String(50), nullable=False)      # lfg_announce (more coming)

    is_enabled = Column(Boolean, default=True)
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)

    __table_args__ = (
        UniqueConstraint('platform', 'guild_id', 'event_type', name='uq_bot_config'),
        Index('idx_bot_config_event', 'event_type', 'is_enabled'),
    )

    def __repr__(self):
        return f"<WebCommunityBotConfig {self.platform}/{self.guild_id} {self.event_type}>"


class WebFluxerGuildChannel(Base):
    """
    Cached list of text channels per Fluxer guild.
    Bot syncs this on startup and guild join.
    Used by the admin panel channel picker.
    """
    __tablename__ = 'web_fluxer_guild_channels'

    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(String(32), nullable=False)
    guild_name = Column(String(200), nullable=True)
    channel_id = Column(String(32), nullable=False)
    channel_name = Column(String(200), nullable=False)
    channel_type = Column(Integer, default=0)   # 0=text, 5=news
    synced_at = Column(BigInteger, nullable=False)

    __table_args__ = (
        UniqueConstraint('guild_id', 'channel_id', name='uq_fluxer_guild_channel'),
    )

    def __repr__(self):
        return f"<WebFluxerGuildChannel {self.guild_id}#{self.channel_name}>"


class WebFluxerGuildRole(Base):
    """
    Cached list of roles per Fluxer guild.
    Bot syncs this on startup via /ql/api/internal/guild-roles/.
    Used by the admin panel role picker (auto-role, LFG notify role, etc.).
    """
    __tablename__ = 'web_fluxer_guild_roles'

    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(String(32), nullable=False)
    role_id = Column(String(32), nullable=False)
    role_name = Column(String(200), nullable=False)
    role_color = Column(Integer, default=0)     # decimal color (0 = no color)
    position = Column(Integer, default=0)       # higher = higher in hierarchy
    is_managed = Column(Integer, default=0)     # 1 = bot-managed (can't assign)
    synced_at = Column(BigInteger, nullable=False)

    __table_args__ = (
        UniqueConstraint('guild_id', 'role_id', name='uq_fluxer_guild_role'),
    )

    def __repr__(self):
        return f"<WebFluxerGuildRole {self.guild_id}#{self.role_name}>"


class WebEarlyAccessCode(Base):
    """
    Invite codes for early-access registration gating.
    Generated by admin (for manual sharing in Discord) or the Fluxer bot !invite command.
    One use per code. When EARLY_ACCESS_ENABLED=true in settings, registration requires a valid code.
    """
    __tablename__ = 'web_early_access_codes'

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(16), unique=True, nullable=False, index=True)
    platform = Column(String(20), nullable=True)    # 'fluxer', 'discord', None=admin-generated
    notes = Column(String(200), nullable=True)       # e.g. 'fluxer:1234567890' or batch label
    created_at = Column(BigInteger, nullable=False)
    used_by_user_id = Column(Integer, ForeignKey('web_users.id'), nullable=True)
    used_at = Column(BigInteger, nullable=True)
    is_revoked = Column(Boolean, default=False)

    used_by_user = relationship("WebUser", foreign_keys=[used_by_user_id])

    __table_args__ = (
        Index('idx_eac_platform', 'platform'),
        Index('idx_eac_used', 'used_by_user_id'),
    )

    def __repr__(self):
        return f"<WebEarlyAccessCode {self.code} platform={self.platform} used={self.used_at is not None}>"


class WebFluxerRoleUpdate(Base):
    """
    Queue for flair changes that need to be synced to Fluxer roles.
    Written by the site when a user equips/unequips a flair.
    Polled by the Fluxer bot every 10s to apply role changes.
    """
    __tablename__ = 'fluxer_pending_role_updates'

    id = Column(Integer, primary_key=True, autoincrement=True)
    web_user_id = Column(Integer, nullable=False, index=True)
    action = Column(String(20), nullable=False)      # 'set_flair' or 'clear_flair'
    flair_emoji = Column(String(20), nullable=True)
    flair_name = Column(String(100), nullable=True)
    created_at = Column(BigInteger, nullable=False)
    processed_at = Column(BigInteger, nullable=True)

    __table_args__ = (
        Index('idx_role_update_pending', 'processed_at', 'created_at'),
    )

    def __repr__(self):
        return f"<WebFluxerRoleUpdate user={self.web_user_id} action={self.action}>"


class WebDiscordPendingRoleUpdate(Base):
    """Queue for QuestLog flair -> Discord role sync. Written by web when user equips/unequips a flair.
    Polled by WardenBot's flair_sync cog every 10s. Only processed for guilds with flair_sync_enabled=1."""
    __tablename__ = 'discord_pending_role_updates'

    id = Column(Integer, primary_key=True, autoincrement=True)
    web_user_id = Column(Integer, nullable=False, index=True)
    action = Column(String(20), nullable=False)      # 'set_flair' or 'clear_flair'
    flair_emoji = Column(String(20), nullable=True)
    flair_name = Column(String(100), nullable=True)
    created_at = Column(BigInteger, nullable=False)
    processed_at = Column(BigInteger, nullable=True)

    __table_args__ = (
        Index('idx_discord_role_update_pending', 'processed_at', 'created_at'),
    )

    def __repr__(self):
        return f"<WebDiscordPendingRoleUpdate user={self.web_user_id} action={self.action}>"


class WebFluxerGuildAction(Base):
    """
    Queue for actions the dashboard requests the bot to perform in a Fluxer guild.
    Written by the site API. Polled by the bot every 15s.

    action_type: 'create_role'
    payload_json: JSON dict with action params (name, permissions, color, hoist, mentionable)
    status: 'pending' | 'done' | 'failed'
    result_json: JSON dict set by bot after execution ({role_id, role_name} on success, {error} on failure)
    """
    __tablename__ = 'web_fluxer_guild_actions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(String(25), nullable=False, index=True)
    action_type = Column(String(30), nullable=False)
    payload_json = Column(Text, nullable=False)
    status = Column(String(20), nullable=False, default='pending')
    created_at = Column(BigInteger, nullable=False)
    processed_at = Column(BigInteger, nullable=True)
    result_json = Column(Text, nullable=True)

    __table_args__ = (
        Index('idx_guild_action_pending', 'guild_id', 'status', 'created_at'),
    )

    def __repr__(self):
        return f"<WebFluxerGuildAction #{self.id} {self.guild_id} {self.action_type} {self.status}>"


class WebSubscriptionEvent(Base):
    """
    Audit log for Stripe subscription lifecycle events.
    One row per Stripe webhook event received (idempotent via stripe_event_id uniqueness).
    event_type values: checkout_started, activated, renewed, cancelled, expired
    """
    __tablename__ = 'web_subscription_events'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('web_users.id'), nullable=False, index=True)
    event_type = Column(String(32), nullable=False)
    stripe_event_id = Column(String(64), unique=True, nullable=True)
    amount_cents = Column(Integer, nullable=True)
    created_at = Column(BigInteger, nullable=False)

    user = relationship("WebUser", foreign_keys=[user_id])

    def __repr__(self):
        return f"<WebSubscriptionEvent user={self.user_id} type={self.event_type}>"


class WebFluxerGuildSettings(Base):
    """
    Per-guild configuration for the Fluxer bot dashboard.
    Stores settings for all feature areas. Features not yet implemented in the bot
    can still be pre-configured here and will be applied when the bot is updated.
    """
    __tablename__ = 'web_fluxer_guild_settings'

    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(String(25), unique=True, nullable=False, index=True)
    guild_name = Column(String(100), nullable=True)

    # Guild metadata (synced from bot on join/ready)
    owner_id = Column(String(25), nullable=True)
    guild_icon_hash = Column(String(255), nullable=True)
    member_count = Column(Integer, nullable=False, default=0, server_default='0')
    online_count = Column(Integer, nullable=False, default=0, server_default='0')
    cached_channels = Column(Text, nullable=True)   # JSON array of {id, name, type, category_name}
    cached_emojis = Column(Text, nullable=True)     # JSON array of {id, name, animated}
    cached_members = Column(Text, nullable=True)    # JSON array of {id, username, display_name, avatar, roles}
    bot_present = Column(SmallInteger, nullable=False, default=1, server_default='1')
    left_at = Column(BigInteger, nullable=True)
    joined_at = Column(BigInteger, nullable=True)

    # Network flags (admin-set)
    is_vip = Column(SmallInteger, nullable=False, default=0, server_default='0')
    discovery_enabled = Column(SmallInteger, nullable=False, default=0, server_default='0')
    audit_logging_enabled = Column(SmallInteger, nullable=False, default=0, server_default='0')
    audit_log_channel_id = Column(String(32), nullable=True)
    anti_raid_enabled = Column(SmallInteger, nullable=False, default=0, server_default='0')
    verification_enabled = Column(SmallInteger, nullable=False, default=0, server_default='0')

    # XP & Leveling (implemented in cogs/xp.py)
    xp_enabled = Column(SmallInteger, nullable=False, default=1, server_default='1')
    xp_per_message = Column(Integer, nullable=False, default=2, server_default='2')
    xp_per_reaction = Column(Integer, nullable=False, default=1, server_default='1')
    xp_per_voice_minute = Column(Integer, nullable=False, default=1, server_default='1')
    xp_cooldown_secs = Column(Integer, nullable=False, default=60, server_default='60')
    xp_media_cooldown_secs = Column(Integer, nullable=False, default=60, server_default='60')
    xp_reaction_cooldown_secs = Column(Integer, nullable=False, default=60, server_default='60')
    xp_ignored_channels = Column(Text, nullable=True)   # JSON list of channel IDs

    # Level-Up Messages
    level_up_enabled = Column(SmallInteger, nullable=False, default=0, server_default='0')
    level_up_channel_id = Column(String(25), nullable=True)      # null = send in same channel as triggering message
    level_up_destination = Column(String(20), nullable=False, default='current', server_default='current')  # current|channel|dm|none
    level_up_message = Column(Text, nullable=True)               # null = use default template

    # Moderation (implemented in cogs/moderation.py)
    mod_log_channel_id = Column(String(25), nullable=True)
    warn_threshold = Column(Integer, nullable=False, default=3, server_default='3')
    auto_ban_after_warns = Column(SmallInteger, nullable=False, default=0, server_default='0')

    # LFG (implemented in cogs/lfg.py)
    lfg_channel_id = Column(String(25), nullable=True)

    # Welcome Messages (bot update required)
    welcome_channel_id = Column(String(25), nullable=True)
    welcome_message = Column(Text, nullable=True)
    goodbye_channel_id = Column(String(25), nullable=True)
    goodbye_message = Column(Text, nullable=True)

    # General settings
    bot_prefix = Column(String(10), nullable=False, default='!', server_default='!')
    language = Column(String(10), nullable=False, default='en', server_default='en')
    timezone = Column(String(50), nullable=False, default='UTC', server_default='UTC')
    token_name = Column(String(50), nullable=False, default='Hero Tokens', server_default='Hero Tokens')
    token_emoji = Column(String(20), nullable=False, default=':coin:', server_default=':coin:')

    # Member management
    role_persistence_enabled = Column(SmallInteger, nullable=False, default=0, server_default='0')
    admin_roles = Column(Text, nullable=True)           # JSON list of role IDs
    channel_notify_channel_id = Column(String(25), nullable=True)
    temp_voice_category_ids = Column(Text, nullable=True)  # JSON list of category IDs

    # XP source toggles
    track_messages = Column(SmallInteger, nullable=False, default=1, server_default='1')
    track_media = Column(SmallInteger, nullable=False, default=1, server_default='1')
    track_reactions = Column(SmallInteger, nullable=False, default=1, server_default='1')
    track_voice = Column(SmallInteger, nullable=False, default=1, server_default='1')
    track_gaming = Column(SmallInteger, nullable=False, default=0, server_default='0')
    xp_per_media = Column(Integer, nullable=False, default=3, server_default='3')
    xp_per_gaming_hour = Column(Integer, nullable=False, default=10, server_default='10')

    # Flair Sync (opt-in - admin must enable before flair roles are created in this guild)
    flair_sync_enabled = Column(SmallInteger, nullable=False, default=0, server_default='0')

    # Creator Discovery / Spotlight (all settings as JSON blob)
    creator_discovery_json = Column(Text, nullable=True)   # JSON: enabled, channels, intervals, COTW/COTM, etc.

    # Community Spotlight (Most Helpful nominations + announcements)
    spotlight_channel_id = Column(String(25), nullable=True)        # Channel for nomination polls + winner announcements

    # Game Discovery (implemented in cogs/discovery.py)
    game_discovery_enabled = Column(SmallInteger, nullable=False, default=0, server_default='0')
    game_discovery_channel_id = Column(String(25), nullable=True)   # Channel to post new-game announcements
    game_discovery_ping_role_id = Column(String(25), nullable=True) # Optional role to ping on announcement
    game_check_interval_hours = Column(Integer, nullable=False, default=24, server_default='24')
    last_game_check_at = Column(BigInteger, nullable=True)          # Unix epoch of last IGDB check

    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)

    def __repr__(self):
        return f"<WebFluxerGuildSettings guild={self.guild_id}>"


class WebFluxerLevelRole(Base):
    """Per-guild level role rewards: when a member reaches `level_required` they get the role."""
    __tablename__ = 'web_fluxer_level_roles'

    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(String(32), nullable=False)
    level_required = Column(Integer, nullable=False)
    role_id = Column(String(32), nullable=False)
    role_name = Column(String(200), nullable=False, default='')
    remove_previous = Column(Integer, nullable=False, default=0)
    created_at = Column(BigInteger, nullable=False, default=lambda: int(time.time()))

    __table_args__ = (
        UniqueConstraint('guild_id', 'level_required', name='uq_fluxer_level_role'),
        Index('idx_fluxer_lr_guild', 'guild_id'),
    )


class WebFluxerXpBoostEvent(Base):
    """Timed XP multiplier events for a Fluxer guild. Bot reads these to scale XP awards."""
    __tablename__ = 'web_fluxer_xp_boost_events'

    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(String(32), nullable=False)
    name = Column(String(100), nullable=False)
    multiplier = Column(Integer, nullable=False, default=2)       # e.g. 2 = 2x XP
    is_active = Column(SmallInteger, nullable=False, default=0, server_default='0')
    start_time = Column(BigInteger, nullable=True)                # Unix epoch, null = manual only
    end_time = Column(BigInteger, nullable=True)                  # Unix epoch, null = no auto-expiry
    created_at = Column(BigInteger, nullable=False, default=lambda: int(time.time()))
    created_by = Column(Integer, nullable=True)                   # web_users.id of creator

    __table_args__ = (
        Index('idx_fluxer_boost_guild', 'guild_id'),
        Index('idx_fluxer_boost_active', 'guild_id', 'is_active'),
    )


class WebBridgeConfig(Base):
    """
    Cross-platform bridge: links channels across Discord, Fluxer, and Matrix for bidirectional
    message relay. Each bridge connects exactly two platforms. Both/all bots poll the relay queue.
    """
    __tablename__ = 'web_bridge_configs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=True)   # Human-readable label, e.g. "general-chat"
    discord_guild_id = Column(String(20), nullable=True)
    discord_channel_id = Column(String(20), nullable=True)
    fluxer_guild_id = Column(String(20), nullable=True)
    fluxer_channel_id = Column(String(20), nullable=True)
    matrix_space_id = Column(String(255), nullable=True)
    matrix_room_id = Column(String(255), nullable=True)
    relay_discord_to_fluxer = Column(SmallInteger, default=1, nullable=False, server_default='1')
    relay_fluxer_to_discord = Column(SmallInteger, default=1, nullable=False, server_default='1')
    relay_matrix_outbound = Column(SmallInteger, default=1, nullable=False, server_default='1')  # Matrix -> other platforms
    relay_matrix_inbound = Column(SmallInteger, default=1, nullable=False, server_default='1')   # other platforms -> Matrix
    max_msg_len = Column(Integer, default=1000, nullable=False, server_default='1000')
    enabled = Column(SmallInteger, default=1, nullable=False, server_default='1')
    created_at = Column(BigInteger, nullable=False)

    __table_args__ = (
        Index('idx_bridge_discord_ch', 'discord_channel_id'),
        Index('idx_bridge_fluxer_ch', 'fluxer_channel_id'),
        Index('idx_bridge_matrix_room', 'matrix_room_id'),
    )

    def __repr__(self):
        return f"<WebBridgeConfig #{self.id} discord:{self.discord_channel_id} <-> fluxer:{self.fluxer_channel_id}>"


class WebBridgeRelayQueue(Base):
    """
    Queue of messages awaiting relay from one platform to the other.
    Written by both bots via the internal API. Polled every 3s per platform.
    """
    __tablename__ = 'web_bridge_relay_queue'

    id = Column(Integer, primary_key=True, autoincrement=True)
    bridge_id = Column(Integer, ForeignKey('web_bridge_configs.id'), nullable=False, index=True)
    source_platform = Column(String(10), nullable=False)   # 'discord', 'fluxer', or 'matrix'
    source_message_id = Column(String(255), nullable=True) # original message ID on source platform
    author_name = Column(String(80), nullable=False)
    author_avatar = Column(String(300), nullable=True)
    content = Column(Text, nullable=False)
    reply_quote = Column(String(200), nullable=True)       # quoted text if this is a reply
    reply_to_source_message_id = Column(String(255), nullable=True)  # source platform message ID being replied to
    attachments_json = Column(Text, nullable=True)         # JSON list of {url, filename, content_type}
    mentions_json = Column(Text, nullable=True)            # JSON list of {id, display_name} (source platform IDs)
    thread_id = Column(String(255), nullable=True)         # source platform thread/channel ID if in a thread
    target_platform = Column(String(10), nullable=False)   # 'discord', 'fluxer', or 'matrix'
    target_channel_id = Column(String(255), nullable=False)
    created_at = Column(BigInteger, nullable=False)
    delivered_at = Column(BigInteger, nullable=True)

    bridge = relationship("WebBridgeConfig", foreign_keys=[bridge_id])

    __table_args__ = (
        Index('idx_relay_pending', 'target_platform', 'delivered_at', 'created_at'),
    )

    def __repr__(self):
        return f"<WebBridgeRelayQueue #{self.id} {self.source_platform}->{self.target_platform}>"


class WebBridgeMessageMap(Base):
    """
    Maps a relay queue row to the actual message IDs on each platform.
    Two rows per relay: one for source (added at relay creation), one for target (added after delivery).
    Used to look up which message to add reactions to.
    """
    __tablename__ = 'web_bridge_message_map'

    id = Column(Integer, primary_key=True, autoincrement=True)
    relay_queue_id = Column(Integer, nullable=False)
    platform = Column(String(10), nullable=False)   # 'discord', 'fluxer', or 'matrix'
    message_id = Column(String(255), nullable=False)
    channel_id = Column(String(255), nullable=False)
    created_at = Column(BigInteger, nullable=False)

    __table_args__ = (
        Index('idx_msg_map_lookup', 'platform', 'message_id'),
        Index('idx_msg_map_relay', 'relay_queue_id'),
    )

    def __repr__(self):
        return f"<WebBridgeMessageMap relay={self.relay_queue_id} {self.platform}:{self.message_id}>"


class WebBridgeThreadMap(Base):
    """
    Maps a thread on one platform to the corresponding thread on another.
    - discord_thread_id: Discord thread channel ID
    - matrix_thread_event_id: Matrix root event ID that the thread hangs off
    - bridge_id: which bridge this thread belongs to
    Created when the first thread message is delivered to the target platform.
    """
    __tablename__ = 'web_bridge_thread_map'

    id = Column(Integer, primary_key=True, autoincrement=True)
    bridge_id = Column(Integer, ForeignKey('web_bridge_configs.id'), nullable=False, index=True)
    discord_thread_id = Column(String(255), nullable=True)          # Discord thread channel ID
    discord_parent_message_id = Column(String(255), nullable=True) # Discord message the thread was created from
    matrix_thread_event_id = Column(String(255), nullable=True)    # Matrix root event ID
    created_at = Column(BigInteger, nullable=False)

    __table_args__ = (
        Index('idx_thread_map_discord', 'discord_thread_id'),
        Index('idx_thread_map_matrix', 'matrix_thread_event_id'),
    )

    def __repr__(self):
        return f"<WebBridgeThreadMap bridge={self.bridge_id} discord={self.discord_thread_id} matrix={self.matrix_thread_event_id}>"


class WebBridgePendingReaction(Base):
    """
    Queue of emoji reactions to relay cross-platform.
    Added by the hub when a reaction event is received from a bot.
    Polled every 6s (every other message poll tick) by each bot.
    Only unicode emojis are relayed - custom platform emojis are skipped.
    Deduplicated: one pending entry per (target_message_id, emoji) at a time.
    """
    __tablename__ = 'web_bridge_pending_reactions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_platform = Column(String(10), nullable=False)
    emoji = Column(String(100), nullable=False)
    target_platform = Column(String(10), nullable=False)
    target_message_id = Column(String(255), nullable=False)
    target_channel_id = Column(String(255), nullable=False)
    created_at = Column(BigInteger, nullable=False)
    delivered_at = Column(BigInteger, nullable=True)

    __table_args__ = (
        Index('idx_pending_react', 'target_platform', 'delivered_at', 'created_at'),
    )

    def __repr__(self):
        return f"<WebBridgePendingReaction {self.source_platform}->{self.target_platform} {self.emoji}>"


class WebBridgePendingDeletion(Base):
    """
    Queue of message deletions to relay cross-platform.
    Deduped by target_message_id: if a deletion is already queued for a message,
    subsequent events (echo from the bot-initiated delete) are ignored.
    """
    __tablename__ = 'web_bridge_pending_deletions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_platform = Column(String(10), nullable=False)
    target_platform = Column(String(10), nullable=False)
    target_message_id = Column(String(255), nullable=False)
    target_channel_id = Column(String(255), nullable=False)
    created_at = Column(BigInteger, nullable=False)
    delivered_at = Column(BigInteger, nullable=True)

    __table_args__ = (
        Index('idx_pending_del', 'target_platform', 'delivered_at', 'created_at'),
        Index('idx_pending_del_msg', 'target_message_id'),
    )

    def __repr__(self):
        return f"<WebBridgePendingDeletion {self.source_platform}->{self.target_platform} msg={self.target_message_id}>"


class WebBridgePendingEdit(Base):
    """
    Queue of message edits to relay cross-platform.
    Keyed by (platform, source_message_id) -> new content.
    Bots poll /ql/internal/bridge/pending-edits/<platform>/ every 6s.
    """
    __tablename__ = 'web_bridge_pending_edits'

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_platform = Column(String(10), nullable=False)
    target_platform = Column(String(10), nullable=False)
    target_message_id = Column(String(255), nullable=False)
    target_channel_id = Column(String(255), nullable=False)
    new_content = Column(Text, nullable=False)
    created_at = Column(BigInteger, nullable=False)
    delivered_at = Column(BigInteger, nullable=True)

    __table_args__ = (
        Index('idx_pending_edit', 'target_platform', 'delivered_at', 'created_at'),
        Index('idx_pending_edit_msg', 'target_message_id'),
    )

    def __repr__(self):
        return f"<WebBridgePendingEdit {self.source_platform}->{self.target_platform} msg={self.target_message_id}>"


class WebFluxerStreamerSub(Base):
    """
    A Fluxer guild's subscription to a specific streamer's live alerts.
    When the streamer goes live on Twitch or YouTube the bot will post an embed
    to `notify_channel_id` in that guild.

    Deduplication: is_live / last_notified_at prevent double-pinging on the same stream session.
    """
    __tablename__ = 'web_fluxer_streamer_subs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(String(25), nullable=False, index=True)
    # 'twitch' or 'youtube'
    streamer_platform = Column(String(20), nullable=False)
    # The username/channel handle as entered (e.g. "shroud" or "UCxxxxxx")
    streamer_handle = Column(String(100), nullable=False)
    # Optional display name override (e.g. "Shroud") - shown in embed
    streamer_display_name = Column(String(100), nullable=True)
    # Fluxer channel ID to post the live alert into
    notify_channel_id = Column(String(25), nullable=False)
    # Optional custom message prepended before the embed (supports {streamer}, {title}, {url})
    custom_message = Column(String(500), nullable=True)
    # Whether this sub is active
    is_active = Column(SmallInteger, nullable=False, default=1, server_default='1')
    # Dedupe: 1 while the streamer is currently live (cleared on offline)
    is_currently_live = Column(SmallInteger, nullable=False, default=0, server_default='0')
    # Unix timestamp of the last live notification sent (to avoid re-pinging same stream)
    last_notified_at = Column(BigInteger, nullable=True)
    created_at = Column(BigInteger, nullable=False, default=lambda: int(time.time()))
    updated_at = Column(BigInteger, nullable=False, default=lambda: int(time.time()))

    __table_args__ = (
        # One subscription per guild+platform+handle
        UniqueConstraint('guild_id', 'streamer_platform', 'streamer_handle',
                         name='uq_fluxer_streamer_sub'),
        Index('idx_fluxer_streamer_sub_guild', 'guild_id'),
        Index('idx_fluxer_streamer_sub_active', 'is_active'),
    )

    def __repr__(self):
        return f"<WebFluxerStreamerSub guild={self.guild_id} {self.streamer_platform}:{self.streamer_handle}>"


class WebDiscordStreamerSub(Base):
    """
    A Discord guild's subscription to a specific streamer's live alerts.
    Mirrors WebFluxerStreamerSub but uses BigInteger guild_id/notify_channel_id
    since Discord snowflakes are integers.
    """
    __tablename__ = 'web_discord_streamer_subs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(BigInteger, nullable=False, index=True)
    # 'twitch' or 'youtube'
    streamer_platform = Column(String(20), nullable=False)
    # The username/channel handle as entered (e.g. "shroud" or "UCxxxxxx")
    streamer_handle = Column(String(100), nullable=False)
    # Optional display name override (e.g. "Shroud") - shown in embed
    streamer_display_name = Column(String(100), nullable=True)
    # Discord channel ID to post the live alert into
    notify_channel_id = Column(BigInteger, nullable=False)
    # Optional custom message prepended before the embed (supports {streamer}, {title}, {url})
    custom_message = Column(String(500), nullable=True)
    # Whether this sub is active
    is_active = Column(SmallInteger, nullable=False, default=1, server_default='1')
    # Dedupe: 1 while the streamer is currently live (cleared on offline)
    is_currently_live = Column(SmallInteger, nullable=False, default=0, server_default='0')
    # Unix timestamp of the last live notification sent (to avoid re-pinging same stream)
    last_notified_at = Column(BigInteger, nullable=True)
    created_at = Column(BigInteger, nullable=False, default=lambda: int(time.time()))
    updated_at = Column(BigInteger, nullable=False, default=lambda: int(time.time()))

    __table_args__ = (
        UniqueConstraint('guild_id', 'streamer_platform', 'streamer_handle',
                         name='uq_discord_streamer_sub'),
        Index('idx_discord_streamer_sub_guild', 'guild_id'),
        Index('idx_discord_streamer_sub_active', 'is_active'),
    )

    def __repr__(self):
        return f"<WebDiscordStreamerSub guild={self.guild_id} {self.streamer_platform}:{self.streamer_handle}>"


# =============================================================================
# FLUXER GUILD FEATURE MODELS (per-guild bot features: LFG, Welcome, etc.)
# =============================================================================

class WebFluxerLfgGame(Base):
    """Games that can be used for LFG in a Fluxer guild."""
    __tablename__ = 'web_fluxer_lfg_games'

    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(String(32), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    igdb_id = Column(String(20), nullable=True)         # IGDB game ID (null if custom)
    game_short = Column(String(20), nullable=True)       # short code for bot commands
    platforms = Column(Text, nullable=True)              # comma-separated platform names
    emoji = Column(String(100), nullable=True)
    cover_url = Column(String(500), nullable=True)       # IGDB cover art URL
    channel_id = Column(String(32), nullable=True)       # per-game LFG channel override
    notify_role_id = Column(String(32), nullable=True)   # role to @mention on new group
    max_group_size = Column(Integer, default=5)
    auto_archive_hours = Column(Integer, default=24)     # thread auto-archive duration
    has_roles = Column(Integer, default=0)               # 1 = Tank/Healer/DPS/Support
    tank_slots = Column(Integer, default=0)
    healer_slots = Column(Integer, default=0)
    dps_slots = Column(Integer, default=0)
    support_slots = Column(Integer, default=0)
    require_rank = Column(Integer, default=0)            # 1 = require rank/level input
    rank_label = Column(String(50), nullable=True)       # e.g. "Hunter Rank", "Power Level"
    rank_min = Column(Integer, nullable=True)
    rank_max = Column(Integer, nullable=True)
    is_custom_game = Column(Integer, default=0)          # 1 = custom (not from IGDB)
    enabled = Column(Integer, default=1)                 # 0 = disabled but not deleted
    options_json = Column(Text, nullable=True)           # JSON: [{name, choices: [{label, role_tag}]}]
    receive_network_lfg = Column(Integer, default=0)     # 1 = receive network LFG broadcasts for this game
    is_active = Column(Integer, default=1)               # 0 = soft-deleted
    created_at = Column(BigInteger, default=0)

    __table_args__ = (
        Index('idx_fluxer_lfg_game_guild', 'guild_id', 'is_active'),
    )

    def __repr__(self):
        return f"<WebFluxerLfgGame {self.name} guild={self.guild_id}>"


class WebFluxerLfgGroup(Base):
    """An active LFG group in a Fluxer guild."""
    __tablename__ = 'web_fluxer_lfg_groups'

    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(String(32), nullable=False, index=True)
    game_id = Column(Integer, nullable=True)  # FK to web_fluxer_lfg_games.id
    game_name = Column(String(100), nullable=False)
    title = Column(String(200), nullable=True)
    description = Column(Text, nullable=True)
    max_size = Column(Integer, default=5)
    current_size = Column(Integer, default=1)
    creator_fluxer_id = Column(String(32), nullable=True)
    creator_web_user_id = Column(Integer, nullable=True)
    creator_name = Column(String(100), nullable=True)
    scheduled_time = Column(BigInteger, nullable=True)
    recurrence = Column(String(20), default='none')          # none, daily, weekly, monthly
    publish_override = Column(Integer, nullable=True)        # NULL=follow guild, 0=private, 1=public
    discord_message_id = Column(String(32), nullable=True)
    channel_id = Column(String(32), nullable=True)
    status = Column(String(20), default='open')  # open, full, closed
    created_at = Column(BigInteger, default=0)
    closed_at = Column(BigInteger, nullable=True)
    tanks_needed = Column(Integer, default=0)
    healers_needed = Column(Integer, default=0)
    dps_needed = Column(Integer, default=0)
    support_needed = Column(Integer, default=0)
    enforce_role_limits = Column(Integer, default=1)
    role_schema = Column(Text, nullable=True)  # JSON array of 4 slot dicts
    server_invite_link = Column(String(500), nullable=True)

    __table_args__ = (
        Index('idx_fluxer_lfg_group_guild_status', 'guild_id', 'status'),
        Index('idx_fluxer_lfg_group_created', 'guild_id', 'created_at'),
    )

    def __repr__(self):
        return f"<WebFluxerLfgGroup {self.game_name!r} status={self.status} guild={self.guild_id}>"


class WebFluxerLfgMember(Base):
    """A member in a Fluxer LFG group."""
    __tablename__ = 'web_fluxer_lfg_members'

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(Integer, nullable=False, index=True)
    fluxer_user_id = Column(String(32), nullable=True)
    web_user_id = Column(Integer, nullable=True)
    username = Column(String(100), nullable=True)
    role = Column(String(20), nullable=True)  # tank, healer, dps, support, member
    selections_json = Column(Text, nullable=True)  # JSON: {class: 'Mage', spec: 'Frost'}
    is_creator = Column(Integer, default=0)
    joined_at = Column(BigInteger, default=0)
    left_at = Column(BigInteger, nullable=True)

    __table_args__ = (
        Index('idx_fluxer_lfg_member_user', 'fluxer_user_id'),
        Index('idx_fluxer_lfg_member_web', 'web_user_id'),
    )

    def __repr__(self):
        return f"<WebFluxerLfgMember group={self.group_id} user={self.fluxer_user_id or self.web_user_id}>"


class WebFluxerWelcomeConfig(Base):
    """Welcome/goodbye message configuration per Fluxer guild."""
    __tablename__ = 'web_fluxer_welcome_config'

    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(String(32), nullable=False, unique=True)
    enabled = Column(Integer, default=0)
    welcome_channel_id = Column(String(32), nullable=True)
    welcome_message = Column(Text, nullable=True)
    welcome_embed_enabled = Column(Integer, default=0)
    welcome_embed_title = Column(String(200), nullable=True)
    welcome_embed_color = Column(String(10), nullable=True)
    welcome_embed_footer = Column(String(300), nullable=True)
    welcome_embed_thumbnail = Column(Integer, default=0)
    dm_enabled = Column(Integer, default=0)
    dm_message = Column(Text, nullable=True)
    goodbye_enabled = Column(Integer, default=0)
    goodbye_channel_id = Column(String(32), nullable=True)
    goodbye_message = Column(Text, nullable=True)
    auto_role_id = Column(String(32), nullable=True)
    updated_at = Column(BigInteger, default=0)

    def __repr__(self):
        return f"<WebFluxerWelcomeConfig guild={self.guild_id} enabled={self.enabled}>"


class WebFluxerReactionRole(Base):
    """A reaction role menu in a Fluxer guild."""
    __tablename__ = 'web_fluxer_reaction_roles'

    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(String(32), nullable=False, index=True)
    channel_id = Column(String(32), nullable=False)
    message_id = Column(String(32), nullable=True)  # set by bot after posting
    title = Column(String(200), nullable=True)
    description = Column(Text, nullable=True)
    mappings_json = Column(Text, nullable=True)  # JSON: [{emoji, role_id, role_name, label}]
    is_exclusive = Column(Integer, default=0)  # 1 = only one role at a time
    created_at = Column(BigInteger, default=0)
    updated_at = Column(BigInteger, default=0)

    __table_args__ = (
        Index('idx_fluxer_react_role_guild', 'guild_id'),
        Index('idx_fluxer_react_role_msg', 'message_id'),
    )

    def __repr__(self):
        return f"<WebFluxerReactionRole guild={self.guild_id} msg={self.message_id}>"


class WebFluxerRaffle(Base):
    """A raffle in a Fluxer guild."""
    __tablename__ = 'web_fluxer_raffles'

    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(String(32), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    prize = Column(String(300), nullable=True)
    channel_id = Column(String(32), nullable=True)
    message_id = Column(String(32), nullable=True)
    max_winners = Column(Integer, default=1)
    ticket_cost_hp = Column(Integer, default=0)  # 0 = free entry
    max_entries_per_user = Column(Integer, default=1)
    winners_json = Column(Text, nullable=True)  # JSON list of winner user IDs
    status = Column(String(20), default='pending')  # pending, active, ended
    starts_at = Column(BigInteger, nullable=True)
    ends_at = Column(BigInteger, nullable=True)
    created_by = Column(Integer, nullable=True)  # web_user_id
    created_at = Column(BigInteger, default=0)

    __table_args__ = (
        Index('idx_fluxer_raffle_guild_status', 'guild_id', 'status'),
    )

    def __repr__(self):
        return f"<WebFluxerRaffle {self.title!r} guild={self.guild_id} status={self.status}>"


class WebFluxerRaffleEntry(Base):
    """An entry in a Fluxer guild raffle."""
    __tablename__ = 'web_fluxer_raffle_entries'

    id = Column(Integer, primary_key=True, autoincrement=True)
    raffle_id = Column(Integer, nullable=False, index=True)
    web_user_id = Column(Integer, nullable=True)
    fluxer_user_id = Column(String(32), nullable=True)
    username = Column(String(100), nullable=True)
    ticket_count = Column(Integer, default=1)
    entered_at = Column(BigInteger, default=0)

    __table_args__ = (
        Index('idx_fluxer_raffle_entry_user', 'raffle_id', 'web_user_id'),
    )

    def __repr__(self):
        return f"<WebFluxerRaffleEntry raffle={self.raffle_id} user={self.web_user_id or self.fluxer_user_id}>"


class WebFluxerModWarning(Base):
    """A moderation warning issued in a Fluxer guild."""
    __tablename__ = 'web_fluxer_mod_warnings'

    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(String(32), nullable=False, index=True)
    target_user_id = Column(String(32), nullable=False)
    target_username = Column(String(100), nullable=True)
    moderator_user_id = Column(String(32), nullable=True)
    moderator_username = Column(String(100), nullable=True)
    reason = Column(Text, nullable=True)
    severity = Column(Integer, default=1)  # 1-3
    is_active = Column(Integer, default=1)
    pardoned_at = Column(BigInteger, nullable=True)
    created_at = Column(BigInteger, default=0)

    __table_args__ = (
        Index('idx_fluxer_mod_warn_guild_user', 'guild_id', 'target_user_id'),
        Index('idx_fluxer_mod_warn_guild_active', 'guild_id', 'is_active'),
    )

    def __repr__(self):
        return f"<WebFluxerModWarning guild={self.guild_id} target={self.target_user_id} severity={self.severity}>"


class WebFluxerVerificationConfig(Base):
    """Verification settings for a Fluxer guild."""
    __tablename__ = 'web_fluxer_verification_config'

    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(String(32), nullable=False, unique=True)
    verification_type = Column(String(20), default='none')  # none, button, age
    verification_channel_id = Column(String(32), nullable=True)
    verified_role_id = Column(String(32), nullable=True)
    account_age_days = Column(Integer, default=7)
    verified_message = Column(Text, nullable=True)
    failed_message = Column(Text, nullable=True)
    updated_at = Column(BigInteger, default=0)

    def __repr__(self):
        return f"<WebFluxerVerificationConfig guild={self.guild_id} type={self.verification_type}>"


class WebFluxerRssFeed(Base):
    """An RSS feed subscription for a Fluxer guild."""
    __tablename__ = 'web_fluxer_rss_feeds'

    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(String(32), nullable=False, index=True)
    url = Column(String(500), nullable=False)
    label = Column(String(200), nullable=True)
    channel_id = Column(String(32), nullable=False)
    channel_name = Column(String(100), nullable=True)
    ping_role_id = Column(String(32), nullable=True)
    poll_interval_minutes = Column(Integer, nullable=False, default=15, server_default='15')
    max_age_days = Column(Integer, nullable=True, default=None)
    category_filter_mode = Column(String(20), nullable=False, default='none', server_default='none')
    category_filters = Column(Text, nullable=True)   # JSON array
    embed_config = Column(Text, nullable=True)        # JSON object
    last_checked_at = Column(BigInteger, nullable=True)
    last_entry_id = Column(String(200), nullable=True)
    consecutive_failures = Column(Integer, nullable=False, default=0, server_default='0')
    last_error = Column(String(500), nullable=True)
    enabled = Column(Integer, nullable=False, default=1, server_default='1')
    is_active = Column(Integer, default=1)
    created_at = Column(BigInteger, default=0)

    __table_args__ = (
        Index('idx_fluxer_rss_guild_active', 'guild_id', 'is_active'),
    )

    def __repr__(self):
        return f"<WebFluxerRssFeed guild={self.guild_id} url={self.url[:50]}>"


class WebFluxerRssArticle(Base):
    """A posted RSS article stored for the member portal articles viewer."""
    __tablename__ = 'web_fluxer_rss_articles'

    id = Column(Integer, primary_key=True, autoincrement=True)
    feed_id = Column(Integer, nullable=False, index=True)
    guild_id = Column(String(32), nullable=False)
    entry_guid = Column(String(500), nullable=False)
    entry_link = Column(String(500), nullable=True)
    entry_title = Column(String(500), nullable=True)
    entry_summary = Column(Text, nullable=True)
    entry_author = Column(String(256), nullable=True)
    entry_thumbnail = Column(String(500), nullable=True)
    entry_categories = Column(Text, nullable=True)   # JSON array
    feed_label = Column(String(200), nullable=True)
    published_at = Column(BigInteger, nullable=True)
    posted_at = Column(BigInteger, nullable=False, default=lambda: int(__import__('time').time()))

    __table_args__ = (
        Index('idx_fluxer_rss_article_guild', 'guild_id', 'posted_at'),
        Index('idx_fluxer_rss_article_feed', 'feed_id'),
        UniqueConstraint('feed_id', 'entry_guid', name='uq_fluxer_rss_article_guid'),
    )

    def __repr__(self):
        return f"<WebFluxerRssArticle feed={self.feed_id} title={str(self.entry_title or '')[:40]}>"


class WebFluxerLfgAttendance(Base):
    """Attendance record for a member in a Fluxer LFG group."""
    __tablename__ = 'web_fluxer_lfg_attendance'

    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(String(32), nullable=False, index=True)
    group_id = Column(Integer, nullable=False, index=True)   # FK to web_fluxer_lfg_groups
    fluxer_user_id = Column(String(32), nullable=True)
    web_user_id = Column(Integer, nullable=True)
    display_name = Column(String(100), nullable=True)
    # Status: pending, confirmed, showed, no_show, late, cancelled, pardoned
    status = Column(String(20), default='pending', nullable=False)
    selections_json = Column(Text, nullable=True)             # {class, role, rank, etc.}
    created_at = Column(BigInteger, default=0)
    updated_at = Column(BigInteger, default=0)

    __table_args__ = (
        Index('idx_fluxer_attend_group', 'group_id'),
        Index('idx_fluxer_attend_user', 'guild_id', 'fluxer_user_id'),
        Index('idx_fluxer_attend_guild_status', 'guild_id', 'status'),
    )

    def __repr__(self):
        return f"<WebFluxerLfgAttendance group={self.group_id} user={self.fluxer_user_id} status={self.status}>"


class WebFluxerLfgMemberStats(Base):
    """Aggregated LFG attendance stats per member per guild."""
    __tablename__ = 'web_fluxer_lfg_member_stats'

    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(String(32), nullable=False, index=True)
    fluxer_user_id = Column(String(32), nullable=False)
    web_user_id = Column(Integer, nullable=True)
    display_name = Column(String(100), nullable=True)
    total_signups = Column(Integer, default=0)
    showed_count = Column(Integer, default=0)
    no_show_count = Column(Integer, default=0)
    late_count = Column(Integer, default=0)
    cancelled_count = Column(Integer, default=0)
    pardoned_count = Column(Integer, default=0)
    # reliability_score = 0-100 (showed / (showed + no_show + late) * 100)
    reliability_score = Column(Integer, default=100)
    is_blacklisted = Column(Integer, default=0)
    blacklist_reason = Column(Text, nullable=True)
    blacklisted_at = Column(BigInteger, nullable=True)
    global_pardon_at = Column(BigInteger, nullable=True)  # last time stats were reset
    updated_at = Column(BigInteger, default=0)

    __table_args__ = (
        Index('idx_fluxer_lfg_stats_guild_user', 'guild_id', 'fluxer_user_id', unique=True),
    )

    def __repr__(self):
        return f"<WebFluxerLfgMemberStats guild={self.guild_id} user={self.fluxer_user_id} rel={self.reliability_score}>"


class WebFluxerLfgConfig(Base):
    """Guild-level LFG attendance configuration."""
    __tablename__ = 'web_fluxer_lfg_config'

    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(String(32), nullable=False, unique=True)
    attendance_enabled = Column(Integer, default=0)         # opt-in
    require_confirmation = Column(Integer, default=0)       # require confirm before showing
    auto_noshow_hours = Column(Integer, default=1)          # hours after start -> auto no-show
    warn_at_reliability = Column(Integer, default=50)       # warn when below this %
    min_required_score = Column(Integer, default=0)         # min % to join groups
    auto_blacklist_noshow = Column(Integer, default=0)      # 0=disabled
    publish_to_network = Column(Integer, default=0)         # 1 = show groups on /ql/fluxer/lfg/
    updated_at = Column(BigInteger, default=0)

    def __repr__(self):
        return f"<WebFluxerLfgConfig guild={self.guild_id} attendance={self.attendance_enabled}>"


class WebFluxerGuildFlair(Base):
    """Per-guild flair settings. Auto-populated from web_flairs on first admin view."""
    __tablename__ = 'web_fluxer_guild_flairs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(String(32), nullable=False)
    flair_id = Column(Integer, nullable=True)    # None for guild-custom flairs
    flair_name = Column(String(100), nullable=False)
    flair_type = Column(String(20), default='normal')  # normal/seasonal/custom
    emoji = Column(String(20), default='')
    enabled = Column(Integer, default=1)
    admin_only = Column(Integer, default=0)      # 1 = admin-assign only, hidden from member store
    hp_cost = Column(Integer, default=0)         # 0 = free (purchasable), use positive int for cost
    display_order = Column(Integer, default=0)
    created_at = Column(BigInteger, nullable=False, default=lambda: int(time.time()))

    __table_args__ = (
        Index('idx_fluxer_guild_flair_guild', 'guild_id'),
    )

    def __repr__(self):
        return f"<WebFluxerGuildFlair guild={self.guild_id} flair={self.flair_name} type={self.flair_type}>"


class WebFluxerMemberFlair(Base):
    """Tracks which guild flairs a member owns and which is currently equipped, per guild."""
    __tablename__ = 'web_fluxer_member_flairs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(String(32), nullable=False)
    web_user_id = Column(Integer, nullable=False)
    guild_flair_id = Column(Integer, nullable=False)   # FK to web_fluxer_guild_flairs.id
    equipped = Column(Integer, default=0)               # 1 = currently active for this guild
    bought_at = Column(BigInteger, nullable=False, default=lambda: int(time.time()))

    __table_args__ = (
        Index('idx_fluxer_member_flair_guild_user', 'guild_id', 'web_user_id'),
        UniqueConstraint('guild_id', 'web_user_id', 'guild_flair_id',
                         name='uq_fluxer_member_flair'),
    )

    def __repr__(self):
        return f"<WebFluxerMemberFlair guild={self.guild_id} user={self.web_user_id} flair={self.guild_flair_id}>"


class WebFluxerGameSearchConfig(Base):
    """IGDB-based game search configs for a Fluxer guild (mirrors Discord GameSearchConfig)."""
    __tablename__ = 'web_fluxer_game_search_configs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(String(32), nullable=False, index=True)
    name = Column(String(100), nullable=False)        # e.g. "Souls-like RPGs"
    enabled = Column(Integer, default=1)              # 1 = active

    # IGDB filters (JSON arrays stored as Text)
    genres = Column(Text, nullable=True)              # JSON array of genre names
    themes = Column(Text, nullable=True)              # JSON array of theme names
    keywords = Column(Text, nullable=True)            # JSON array of IGDB keyword names
    game_modes = Column(Text, nullable=True)          # JSON array of mode names
    platforms = Column(Text, nullable=True)           # JSON array of platform names

    # Quality filters
    min_hype = Column(Integer, nullable=True)         # minimum IGDB hype score
    min_rating = Column(Float, nullable=True)         # minimum IGDB rating

    # Announcement window
    days_ahead = Column(Integer, default=30)          # how far ahead to surface games

    # Visibility
    show_on_website = Column(Integer, default=1)      # 1 = public to members portal

    # Timestamps
    created_at = Column(BigInteger, default=lambda: int(time.time()))
    updated_at = Column(BigInteger, default=lambda: int(time.time()))

    __table_args__ = (
        Index('idx_fluxer_game_search_guild', 'guild_id'),
        Index('idx_fluxer_game_search_enabled', 'guild_id', 'enabled'),
    )

    def __repr__(self):
        return f"<WebFluxerGameSearchConfig guild={self.guild_id} name={self.name}>"


class WebFluxerFoundGame(Base):
    """Cache of IGDB games surfaced by discovery checks for a Fluxer guild."""
    __tablename__ = 'web_fluxer_found_games'

    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(String(32), nullable=False, index=True)

    # Game identification
    igdb_id = Column(Integer, nullable=False)
    igdb_slug = Column(String(255), nullable=True)
    game_name = Column(String(255), nullable=False)

    # Game details
    release_date = Column(BigInteger, nullable=True)  # Unix timestamp
    summary = Column(Text, nullable=True)
    genres = Column(Text, nullable=True)              # JSON array
    themes = Column(Text, nullable=True)              # JSON array
    keywords = Column(Text, nullable=True)            # JSON array
    game_modes = Column(Text, nullable=True)          # JSON array
    platforms_json = Column(Text, nullable=True)      # JSON array (avoids clash with 'platforms')

    # Media & links
    cover_url = Column(String(500), nullable=True)
    igdb_url = Column(String(500), nullable=True)
    steam_url = Column(String(500), nullable=True)

    # Quality metrics
    hypes = Column(Integer, nullable=True)
    rating = Column(Float, nullable=True)

    # Discovery metadata
    search_config_id = Column(Integer, nullable=True)  # FK to WebFluxerGameSearchConfig.id
    search_config_name = Column(String(100), nullable=True)
    found_at = Column(BigInteger, nullable=False, default=lambda: int(time.time()))
    check_id = Column(String(50), nullable=True)      # unique ID per check run

    __table_args__ = (
        Index('idx_fluxer_found_game_guild', 'guild_id'),
        Index('idx_fluxer_found_game_igdb', 'guild_id', 'igdb_id'),
        Index('idx_fluxer_found_game_search', 'guild_id', 'search_config_id'),
        Index('idx_fluxer_found_game_check', 'guild_id', 'check_id'),
    )

    def __repr__(self):
        return f"<WebFluxerFoundGame {self.game_name} guild={self.guild_id}>"


class WebFluxerAnnouncedGame(Base):
    """
    Tracks which games have already been announced in a guild's discovery channel.
    Prevents re-announcing the same game on subsequent check runs.
    Mirrors WardenBot's AnnouncedGame model.
    """
    __tablename__ = 'web_fluxer_announced_games'

    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(String(32), nullable=False)
    igdb_id = Column(Integer, nullable=False)
    igdb_slug = Column(String(255), nullable=True)
    steam_id = Column(Integer, nullable=True)
    game_name = Column(String(255), nullable=False)
    release_date = Column(BigInteger, nullable=True)
    genres = Column(Text, nullable=True)        # JSON list
    platforms = Column(Text, nullable=True)     # JSON list
    cover_url = Column(String(500), nullable=True)
    announced_at = Column(BigInteger, nullable=False, default=lambda: int(time.time()))
    announcement_message_id = Column(String(32), nullable=True)  # Fluxer message ID

    __table_args__ = (
        Index('idx_fluxer_announced_guild', 'guild_id'),
        Index('idx_fluxer_announced_igdb', 'guild_id', 'igdb_id'),
    )

    def __repr__(self):
        return f"<WebFluxerAnnouncedGame {self.game_name} guild={self.guild_id}>"


class WebUnifiedLeaderboard(Base):
    """
    Unified engagement leaderboard for QuestLog Network guilds.
    One row per user per guild per platform.
    Only populated for guilds where site_xp_to_guild=True (opted in to unified XP).
    Stats are tracked here for leaderboard display; XP itself lives in web_users.web_xp.
    Platforms: discord, fluxer, matrix (future)
    """
    __tablename__ = 'web_unified_leaderboard'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('web_users.id'), nullable=False)
    guild_id = Column(String(32), nullable=False)       # Discord guild ID or Fluxer guild ID
    platform = Column(String(20), nullable=False)       # 'discord', 'fluxer', 'matrix'

    # Engagement stats (ever-increasing totals)
    messages = Column(Integer, nullable=False, default=0, server_default='0')
    voice_mins = Column(Integer, nullable=False, default=0, server_default='0')
    reactions = Column(Integer, nullable=False, default=0, server_default='0')
    media_count = Column(Integer, nullable=False, default=0, server_default='0')

    # XP snapshot - mirrors web_users.web_xp, updated on each XP event
    xp_total = Column(Integer, nullable=False, default=0, server_default='0')

    # Timestamps
    last_active = Column(BigInteger, nullable=True)
    updated_at = Column(BigInteger, nullable=False, default=lambda: int(time.time()))

    __table_args__ = (
        UniqueConstraint('user_id', 'guild_id', 'platform', name='uq_unified_lb_user_guild_platform'),
        Index('idx_unified_lb_guild_platform', 'guild_id', 'platform'),
        Index('idx_unified_lb_xp', 'guild_id', 'platform', 'xp_total'),
    )

    def __repr__(self):
        return f"<WebUnifiedLeaderboard user={self.user_id} guild={self.guild_id} platform={self.platform}>"


class FluxerChannelStatTracker(Base):
    """Per-guild channel topic trackers for the Fluxer bot."""
    __tablename__ = 'fluxer_channel_stat_trackers'

    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(String(64), nullable=False)
    channel_id = Column(String(64), nullable=False)
    role_id = Column(String(64), nullable=False)
    label = Column(String(100), nullable=False)
    emoji = Column(String(100), nullable=True)
    game_name = Column(String(100), nullable=True)
    show_playing_count = Column(Boolean, default=False)
    enabled = Column(Boolean, default=True)
    update_interval_seconds = Column(Integer, default=60)
    last_updated = Column(BigInteger, nullable=True)
    last_topic = Column(String(500), nullable=True)
    created_at = Column(BigInteger, nullable=False, default=lambda: int(time.time()))
    created_by = Column(String(64), nullable=True)

    __table_args__ = (
        UniqueConstraint('guild_id', 'channel_id', name='uq_fluxer_guild_channel_tracker'),
        Index('idx_fluxer_tracker_guild', 'guild_id'),
        Index('idx_fluxer_tracker_enabled', 'enabled'),
    )

    def __repr__(self):
        return f"<FluxerChannelStatTracker guild={self.guild_id} channel={self.channel_id} label={self.label}>"


# ==============================================================================
# QuestLogMatrix - Matrix Bot Models
# ==============================================================================

class WebMatrixSpaceSettings(Base):
    """Per-space configuration for QuestLogMatrix bot. Space = Matrix Space (guild equivalent)."""
    __tablename__ = 'web_matrix_space_settings'

    id = Column(Integer, primary_key=True, autoincrement=True)
    space_id = Column(String(255), nullable=False, unique=True)
    space_name = Column(String(200), nullable=True)
    space_avatar_url = Column(String(500), nullable=True)
    owner_matrix_id = Column(String(100), nullable=True)
    bot_present = Column(SmallInteger, nullable=False, default=1)
    joined_at = Column(BigInteger, nullable=True)
    left_at = Column(BigInteger, nullable=True)
    # XP
    xp_enabled = Column(SmallInteger, nullable=False, default=1)
    xp_per_message = Column(Integer, nullable=False, default=2)
    xp_cooldown_secs = Column(Integer, nullable=False, default=60)
    xp_ignored_rooms = Column(Text, nullable=True)
    level_up_enabled = Column(SmallInteger, nullable=False, default=0)
    level_up_room_id = Column(String(255), nullable=True)
    level_up_message = Column(Text, nullable=True)
    # Moderation
    mod_log_room_id = Column(String(255), nullable=True)
    warn_threshold = Column(Integer, nullable=False, default=3)
    auto_ban_after_warns = Column(SmallInteger, nullable=False, default=0)
    # Welcome
    welcome_room_id = Column(String(255), nullable=True)
    welcome_message = Column(Text, nullable=True)
    goodbye_room_id = Column(String(255), nullable=True)
    goodbye_message = Column(Text, nullable=True)
    # Admin access
    admin_power_level = Column(Integer, nullable=False, default=50)
    admin_matrix_ids = Column(Text, nullable=True)
    # General
    bot_prefix = Column(String(10), nullable=False, default='!')
    language = Column(String(10), nullable=False, default='en')
    timezone = Column(String(50), nullable=False, default='UTC')
    # Discovery
    discovery_enabled = Column(SmallInteger, nullable=False, default=0)
    discovery_room_id = Column(String(255), nullable=True)
    discovery_ping_matrix_id = Column(String(100), nullable=True)
    # Audit log
    audit_log_enabled = Column(SmallInteger, nullable=False, default=0)
    audit_log_room_id = Column(String(255), nullable=True)
    audit_event_config = Column(Text, nullable=True)
    # Verification
    verification_type = Column(String(20), nullable=False, default='none')
    verification_room_id = Column(String(255), nullable=True)
    verification_account_age_days = Column(Integer, nullable=False, default=7)
    verification_verified_message = Column(Text, nullable=True)
    verification_failed_message = Column(Text, nullable=True)
    # Stats (updated by SpaceSyncCog)
    room_count = Column(Integer, nullable=False, default=0)
    member_count = Column(Integer, nullable=False, default=0)
    # Timestamps
    created_at = Column(BigInteger, nullable=False, default=lambda: int(time.time()))
    updated_at = Column(BigInteger, nullable=False, default=lambda: int(time.time()))

    def __repr__(self):
        return f"<WebMatrixSpaceSettings space={self.space_id} name={self.space_name}>"


class WebMatrixRoom(Base):
    """Room cache for a Matrix space (channel equivalent)."""
    __tablename__ = 'web_matrix_rooms'

    id = Column(Integer, primary_key=True, autoincrement=True)
    space_id = Column(String(255), nullable=False)
    room_id = Column(String(255), nullable=False)
    room_name = Column(String(200), nullable=True)
    room_alias = Column(String(200), nullable=True)
    topic = Column(Text, nullable=True)
    is_encrypted = Column(SmallInteger, nullable=False, default=0)
    is_space = Column(SmallInteger, nullable=False, default=0)
    member_count = Column(Integer, nullable=False, default=0)
    power_levels_json = Column(Text, nullable=True)
    last_synced_at = Column(BigInteger, nullable=True)
    created_at = Column(BigInteger, nullable=False, default=lambda: int(time.time()))

    __table_args__ = (
        UniqueConstraint('space_id', 'room_id', name='uq_matrix_room'),
        Index('idx_matrix_rooms_space', 'space_id'),
    )

    def __repr__(self):
        return f"<WebMatrixRoom space={self.space_id} room={self.room_id} name={self.room_name}>"


class WebMatrixMember(Base):
    """Member cache for a Matrix space."""
    __tablename__ = 'web_matrix_members'

    id = Column(Integer, primary_key=True, autoincrement=True)
    space_id = Column(String(255), nullable=False)
    matrix_id = Column(String(100), nullable=False)
    display_name = Column(String(200), nullable=True)
    avatar_url = Column(String(500), nullable=True)
    power_level = Column(Integer, nullable=False, default=0)
    web_user_id = Column(Integer, nullable=True)
    joined_at = Column(BigInteger, nullable=True)
    left_at = Column(BigInteger, nullable=True)
    last_seen = Column(BigInteger, nullable=True)
    synced_at = Column(BigInteger, nullable=False, default=lambda: int(time.time()))

    __table_args__ = (
        UniqueConstraint('space_id', 'matrix_id', name='uq_matrix_member'),
        Index('idx_matrix_members_space', 'space_id'),
        Index('idx_matrix_members_mid', 'matrix_id'),
    )

    def __repr__(self):
        return f"<WebMatrixMember space={self.space_id} user={self.matrix_id}>"


class WebMatrixXpEvent(Base):
    """Per-member XP tracking within a Matrix space."""
    __tablename__ = 'web_matrix_xp_events'

    id = Column(Integer, primary_key=True, autoincrement=True)
    space_id = Column(String(255), nullable=False)
    matrix_id = Column(String(100), nullable=False)
    xp = Column(Integer, nullable=False, default=0)
    level = Column(Integer, nullable=False, default=1)
    last_message_at = Column(BigInteger, nullable=True)

    __table_args__ = (
        UniqueConstraint('space_id', 'matrix_id', name='uq_matrix_xp'),
        Index('idx_matrix_xp_space', 'space_id'),
    )

    def __repr__(self):
        return f"<WebMatrixXpEvent space={self.space_id} user={self.matrix_id} xp={self.xp}>"


class WebMatrixModWarning(Base):
    """Moderation warnings issued in a Matrix space."""
    __tablename__ = 'web_matrix_mod_warnings'

    id = Column(Integer, primary_key=True, autoincrement=True)
    space_id = Column(String(255), nullable=False)
    target_matrix_id = Column(String(100), nullable=False)
    moderator_matrix_id = Column(String(100), nullable=False)
    reason = Column(Text, nullable=False)
    room_id = Column(String(255), nullable=True)
    is_active = Column(SmallInteger, nullable=False, default=1)
    pardoned_by = Column(String(100), nullable=True)
    pardoned_at = Column(BigInteger, nullable=True)
    created_at = Column(BigInteger, nullable=False, default=lambda: int(time.time()))

    __table_args__ = (
        Index('idx_matrix_warn_space', 'space_id'),
        Index('idx_matrix_warn_target', 'space_id', 'target_matrix_id'),
    )

    def __repr__(self):
        return f"<WebMatrixModWarning #{self.id} space={self.space_id} target={self.target_matrix_id}>"


class WebMatrixWelcomeConfig(Base):
    """Welcome/goodbye message configuration for a Matrix space."""
    __tablename__ = 'web_matrix_welcome_config'

    id = Column(Integer, primary_key=True, autoincrement=True)
    space_id = Column(String(255), nullable=False, unique=True)
    enabled = Column(SmallInteger, nullable=False, default=0)
    welcome_room_id = Column(String(255), nullable=True)
    welcome_message = Column(Text, nullable=True)
    welcome_embed_enabled = Column(SmallInteger, nullable=False, default=0)
    welcome_embed_title = Column(String(200), nullable=True)
    welcome_embed_color = Column(String(10), nullable=True)
    dm_enabled = Column(SmallInteger, nullable=False, default=0)
    dm_message = Column(Text, nullable=True)
    goodbye_enabled = Column(SmallInteger, nullable=False, default=0)
    goodbye_room_id = Column(String(255), nullable=True)
    goodbye_message = Column(Text, nullable=True)
    auto_invite_room_ids = Column(Text, nullable=True)
    updated_at = Column(BigInteger, nullable=False, default=lambda: int(time.time()))

    def __repr__(self):
        return f"<WebMatrixWelcomeConfig space={self.space_id} enabled={self.enabled}>"


class WebMatrixRssFeed(Base):
    """RSS feed subscription for a Matrix space."""
    __tablename__ = 'web_matrix_rss_feeds'

    id = Column(Integer, primary_key=True, autoincrement=True)
    space_id = Column(String(255), nullable=False)
    url = Column(String(500), nullable=False)
    label = Column(String(200), nullable=True)
    room_id = Column(String(255), nullable=False)
    room_name = Column(String(100), nullable=True)
    ping_matrix_id = Column(String(100), nullable=True)
    poll_interval_minutes = Column(Integer, nullable=False, default=15)
    max_age_days = Column(Integer, nullable=True)
    last_checked_at = Column(BigInteger, nullable=True)
    last_entry_id = Column(String(200), nullable=True)
    consecutive_failures = Column(Integer, nullable=False, default=0)
    last_error = Column(String(500), nullable=True)
    enabled = Column(Integer, nullable=False, default=1)
    created_at = Column(BigInteger, nullable=False, default=lambda: int(time.time()))

    __table_args__ = (
        Index('idx_matrix_rss_space', 'space_id', 'enabled'),
    )

    def __repr__(self):
        return f"<WebMatrixRssFeed #{self.id} space={self.space_id} url={self.url}>"


class WebMatrixRssArticle(Base):
    """Sent RSS articles for deduplication."""
    __tablename__ = 'web_matrix_rss_articles'

    id = Column(Integer, primary_key=True, autoincrement=True)
    feed_id = Column(Integer, nullable=False)
    space_id = Column(String(255), nullable=False)
    entry_guid = Column(String(500), nullable=False)
    entry_link = Column(String(500), nullable=True)
    entry_title = Column(String(500), nullable=True)
    entry_summary = Column(Text, nullable=True)
    entry_author = Column(String(256), nullable=True)
    entry_thumbnail = Column(String(500), nullable=True)
    published_at = Column(BigInteger, nullable=True)
    posted_at = Column(BigInteger, nullable=False, default=lambda: int(time.time()))

    __table_args__ = (
        UniqueConstraint('feed_id', 'entry_guid', name='uq_matrix_rss_article'),
        Index('idx_matrix_rss_article_space', 'space_id', 'posted_at'),
    )

    def __repr__(self):
        return f"<WebMatrixRssArticle feed={self.feed_id} guid={self.entry_guid[:40]}>"


class WebMatrixGuildAction(Base):
    """Action queue: dashboard requests executed by the bot (kick, ban, set topic, etc.)."""
    __tablename__ = 'web_matrix_guild_actions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    space_id = Column(String(255), nullable=False)
    action_type = Column(String(50), nullable=False)
    payload_json = Column(Text, nullable=False)
    status = Column(String(20), nullable=False, default='pending')
    created_at = Column(BigInteger, nullable=False, default=lambda: int(time.time()))
    processed_at = Column(BigInteger, nullable=True)
    result_json = Column(Text, nullable=True)

    __table_args__ = (
        Index('idx_matrix_action_queue', 'space_id', 'status', 'created_at'),
    )

    def __repr__(self):
        return f"<WebMatrixGuildAction #{self.id} space={self.space_id} type={self.action_type} status={self.status}>"


class WebMatrixPendingDm(Base):
    """Pending DMs for the bot to send (used for account linking verification)."""
    __tablename__ = 'web_matrix_pending_dms'

    id = Column(Integer, primary_key=True, autoincrement=True)
    matrix_id = Column(String(100), nullable=False)
    message = Column(Text, nullable=False)
    status = Column(String(20), nullable=False, default='pending')
    created_at = Column(BigInteger, nullable=False, default=lambda: int(time.time()))
    sent_at = Column(BigInteger, nullable=True)

    __table_args__ = (
        Index('idx_matrix_pending_dm_status', 'status'),
    )

    def __repr__(self):
        return f"<WebMatrixPendingDm #{self.id} to={self.matrix_id} status={self.status}>"


class WebMatrixBanList(Base):
    """Draupnir-style shared ban list for a Matrix space."""
    __tablename__ = 'web_matrix_ban_lists'

    id = Column(Integer, primary_key=True, autoincrement=True)
    space_id = Column(String(255), nullable=False)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    is_subscribed = Column(SmallInteger, nullable=False, default=0)
    sync_paused = Column(SmallInteger, nullable=False, default=0)
    source_room_id = Column(String(255), nullable=True)
    last_synced_at = Column(BigInteger, nullable=True)
    created_at = Column(BigInteger, nullable=False, default=lambda: int(time.time()))

    __table_args__ = (
        Index('idx_matrix_ban_lists_space', 'space_id'),
    )

    def __repr__(self):
        return f"<WebMatrixBanList #{self.id} space={self.space_id} name={self.name}>"


class WebMatrixBanListEntry(Base):
    """Individual entry in a Matrix ban list."""
    __tablename__ = 'web_matrix_ban_list_entries'

    id = Column(Integer, primary_key=True, autoincrement=True)
    list_id = Column(Integer, nullable=False)
    target_matrix_id = Column(String(100), nullable=False)
    reason = Column(Text, nullable=True)
    added_by = Column(String(100), nullable=True)
    created_at = Column(BigInteger, nullable=False, default=lambda: int(time.time()))

    __table_args__ = (
        UniqueConstraint('list_id', 'target_matrix_id', name='uq_matrix_ban_entry'),
        Index('idx_matrix_ban_entry_list', 'list_id'),
    )

    def __repr__(self):
        return f"<WebMatrixBanListEntry list={self.list_id} target={self.target_matrix_id}>"


class WebMatrixLevelRole(Base):
    """Power level to assign when a member reaches a certain XP level."""
    __tablename__ = 'web_matrix_level_roles'

    id = Column(Integer, primary_key=True, autoincrement=True)
    space_id = Column(String(255), nullable=False)
    level = Column(Integer, nullable=False)
    power_level = Column(Integer, nullable=False, default=0)
    label = Column(String(100), nullable=True)
    created_at = Column(BigInteger, nullable=False, default=lambda: int(time.time()))

    __table_args__ = (
        UniqueConstraint('space_id', 'level', name='uq_matrix_level_role'),
        Index('idx_matrix_level_roles_space', 'space_id'),
    )

    def __repr__(self):
        return f"<WebMatrixLevelRole space={self.space_id} level={self.level} pl={self.power_level}>"


class WebMatrixXpBoost(Base):
    """Timed XP multiplier event for a Matrix space."""
    __tablename__ = 'web_matrix_xp_boosts'

    id = Column(Integer, primary_key=True, autoincrement=True)
    space_id = Column(String(255), nullable=False)
    label = Column(String(100), nullable=False)
    multiplier = Column(Float, nullable=False, default=2.0)
    starts_at = Column(BigInteger, nullable=False, default=lambda: int(time.time()))
    ends_at = Column(BigInteger, nullable=False, default=lambda: int(time.time()))
    created_at = Column(BigInteger, nullable=False, default=lambda: int(time.time()))

    __table_args__ = (
        Index('idx_matrix_xp_boost_space', 'space_id', 'ends_at'),
    )

    def __repr__(self):
        return f"<WebMatrixXpBoost #{self.id} space={self.space_id} x{self.multiplier}>"


class WebMatrixAuditLog(Base):
    """Per-event audit log for QuestLogMatrix spaces. Mirrors WardenBot's AuditLog."""
    __tablename__ = 'web_matrix_audit_log'

    id = Column(Integer, primary_key=True, autoincrement=True)
    space_id = Column(String(255), nullable=False, index=True)
    # Event classification
    action = Column(String(50), nullable=False)        # e.g. member_join, room_create
    category = Column(String(20), nullable=True)       # member|room|message|moderation|security
    # Who did it
    actor_matrix_id = Column(String(255), nullable=True)
    actor_display_name = Column(String(200), nullable=True)
    # What was targeted
    target_matrix_id = Column(String(255), nullable=True)
    target_display_name = Column(String(200), nullable=True)
    target_type = Column(String(20), nullable=True)    # user|room|space
    # Room context
    room_id = Column(String(255), nullable=True)
    room_name = Column(String(255), nullable=True)
    # Extra detail
    reason = Column(String(500), nullable=True)
    details = Column(Text, nullable=True)
    # Timestamp
    created_at = Column(BigInteger, nullable=False, default=lambda: int(time.time()), index=True)

    __table_args__ = (
        Index('idx_matrix_audit_space_time', 'space_id', 'created_at'),
        Index('idx_matrix_audit_action', 'space_id', 'action'),
    )

    def __repr__(self):
        return f"<WebMatrixAuditLog #{self.id} space={self.space_id} action={self.action}>"


class WebCustomEmoji(Base):
    """Site-wide custom emoji and stickers. Admin-uploaded, all users can use."""
    __tablename__ = 'web_custom_emoji'

    id = Column(Integer, primary_key=True, autoincrement=True)
    shortcode = Column(String(50), nullable=False, unique=True, index=True)  # e.g. "fireteam"
    image_url = Column(String(500), nullable=False)
    is_animated = Column(Boolean, nullable=False, default=False)
    is_sticker = Column(Boolean, nullable=False, default=False)  # True = sticker (512x512), False = emoji (128x128)
    created_at = Column(BigInteger, nullable=False, default=lambda: int(time.time()))
    created_by = Column(Integer, ForeignKey('web_users.id', ondelete='SET NULL'), nullable=True)

    def __repr__(self):
        return f"<WebCustomEmoji :{self.shortcode}: sticker={self.is_sticker}>"


class Web7dtdCharacterTransfer(Base):
    """Tracks in-transit character state for cross-server transfers.
    Created when player confirms travel. Consumed when they join the destination server.
    in_transit=1 means their character is frozen - deny login on source server."""
    __tablename__ = 'web_7dtd_character_transfers'

    id              = Column(Integer, primary_key=True, autoincrement=True)
    steam_id        = Column(String(32), nullable=False, index=True)
    player_name     = Column(String(64), nullable=False)
    from_server     = Column(String(64), nullable=False)
    to_server       = Column(String(64), nullable=False)
    connect_ip      = Column(String(64), nullable=False)
    zone_id         = Column(String(64), nullable=False)
    in_transit      = Column(Integer, nullable=False, default=1)  # 1=frozen, 0=arrived
    character_state = Column(Text, nullable=True)                 # JSON - Phase 2 (inventory/health/buffs)
    created_at      = Column(BigInteger, nullable=False)
    arrived_at      = Column(BigInteger, nullable=True)

    def __repr__(self):
        return f"<Web7dtdCharacterTransfer steam={self.steam_id} {self.from_server}->{self.to_server} in_transit={self.in_transit}>"


class Web7dtdPendingNotification(Base):
    """Pending Fluxer notifications queued by the C# mod via Django. Bot polls and posts these."""
    __tablename__ = 'web_7dtd_pending_notifications'

    id          = Column(Integer, primary_key=True, autoincrement=True)
    server      = Column(String(64), nullable=False)
    event_type  = Column(String(64), nullable=False)
    payload     = Column(Text, nullable=False)   # JSON - full event data from C# mod
    embed_data  = Column(Text, nullable=True)    # JSON - pre-built embed for bot to post
    channel_id  = Column(String(64), nullable=True)
    sent        = Column(Integer, nullable=False, default=0)
    created_at  = Column(BigInteger, nullable=False)
    sent_at     = Column(BigInteger, nullable=True)

    def __repr__(self):
        return f"<Web7dtdPendingNotification id={self.id} server={self.server} event={self.event_type} sent={self.sent}>"


class Web7dtdArtifactUnlock(Base):
    """Records when a player picks up a SYNAPSE artifact in 7DTD.
    One row per player per artifact. Prevents duplicate unlocks.
    weekly_reset_at is set by cron to allow respawn for other players."""
    __tablename__ = 'web_7dtd_artifact_unlocks'

    id            = Column(Integer, primary_key=True, autoincrement=True)
    steam_id      = Column(String(64), nullable=False)
    player_name   = Column(String(128), nullable=False)
    artifact_id   = Column(String(64), nullable=False)
    server        = Column(String(64), nullable=False)
    web_user_id   = Column(Integer, ForeignKey('web_users.id'), nullable=True)
    unlocked_at   = Column(BigInteger, nullable=False)
    weekly_reset_at = Column(BigInteger, nullable=True)

    __table_args__ = (
        UniqueConstraint('steam_id', 'artifact_id', name='uq_steam_artifact'),
    )

    def __repr__(self):
        return f"<Web7dtdArtifactUnlock steam={self.steam_id} artifact={self.artifact_id}>"


class Web7dtdArtifactLoadout(Base):
    """Tracks which artifact a player has equipped in their single slot.
    slot=1 is the only slot for alpha. slot=2 will be added later.
    Only valid if the player also has a row in web_7dtd_artifact_unlocks for this artifact."""
    __tablename__ = 'web_7dtd_artifact_loadout'

    id          = Column(Integer, primary_key=True, autoincrement=True)
    steam_id    = Column(String(64), nullable=False)
    web_user_id = Column(Integer, ForeignKey('web_users.id'), nullable=True)
    artifact_id = Column(String(64), nullable=False)
    slot        = Column(Integer, nullable=False, default=1)
    server      = Column(String(64), nullable=False)
    equipped_at = Column(BigInteger, nullable=False)

    __table_args__ = (
        UniqueConstraint('steam_id', 'slot', name='uq_loadout_slot'),
    )

    def __repr__(self):
        return f"<Web7dtdArtifactLoadout steam={self.steam_id} slot={self.slot} artifact={self.artifact_id}>"


class WebSynapsePlayer(Base):
    """Per-player SYNAPSE progression state.
    One row per steam_id. Tracks Prototype unlock, slot 2 unlock, and Legacy score."""
    __tablename__ = 'web_synapse_players'

    id                       = Column(Integer, primary_key=True, autoincrement=True)
    steam_id                 = Column(String(64), nullable=False, unique=True)
    web_user_id              = Column(Integer, ForeignKey('web_users.id'), nullable=True)
    prototype_unlocked       = Column(Boolean, nullable=False, default=False)
    prototype_unlocked_at    = Column(BigInteger, nullable=True)
    subclass_slot_2_unlocked = Column(Boolean, nullable=False, default=False)
    slot_2_unlocked_at       = Column(BigInteger, nullable=True)
    legacy_score             = Column(Integer, nullable=False, default=0)
    legacy_tier              = Column(Integer, nullable=False, default=0)
    created_at               = Column(BigInteger, nullable=False)
    updated_at               = Column(BigInteger, nullable=False)

    def __repr__(self):
        return f"<WebSynapsePlayer steam={self.steam_id} legacy={self.legacy_score} prototype={self.prototype_unlocked}>"


class WebSynapseLegacyEvent(Base):
    """War story log - each meaningful Legacy-earning event.
    Never deleted - permanent record of what a player survived."""
    __tablename__ = 'web_synapse_legacy_events'

    id          = Column(Integer, primary_key=True, autoincrement=True)
    steam_id    = Column(String(64), nullable=False, index=True)
    web_user_id = Column(Integer, ForeignKey('web_users.id'), nullable=True)
    event_type  = Column(String(64), nullable=False, index=True)
    points      = Column(Integer, nullable=False)
    server      = Column(String(64), nullable=False)
    earned_at   = Column(BigInteger, nullable=False)

    def __repr__(self):
        return f"<WebSynapseLegacyEvent steam={self.steam_id} type={self.event_type} pts={self.points}>"
