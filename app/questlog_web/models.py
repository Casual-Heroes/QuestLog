# QuestLog Web Models - Web-native user and community models
# These are separate from Discord-based models to allow standalone web usage

from sqlalchemy import (
    Column, Integer, BigInteger, String, Text, Boolean, Enum, ForeignKey,
    UniqueConstraint, Index, and_, or_
)
from sqlalchemy.orm import relationship
from app.models import Base  # Base is defined in models.py
import enum
import time
import hashlib
import hmac
import secrets


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
    twitch_id = Column(String(50), unique=True, nullable=True, index=True)
    twitch_username = Column(String(100), nullable=True)
    youtube_channel_id = Column(String(100), nullable=True)
    youtube_channel_name = Column(String(100), nullable=True)

    # Contact (optional)
    email = Column(String(255), unique=True, nullable=True, index=True)
    email_verified = Column(Boolean, default=False)

    # Web XP system (separate from Discord XP)
    web_xp = Column(Integer, default=0)
    web_level = Column(Integer, default=1)
    hero_points = Column(Integer, default=0)
    active_flair_id = Column(Integer, ForeignKey('web_flairs.id'), nullable=True)

    # Steam tracking opt-ins (both default off — fully user-controlled)
    track_achievements = Column(Boolean, default=False)
    track_hours_played = Column(Boolean, default=False)
    steam_achievements_total = Column(Integer, default=0)  # last known total for delta
    steam_hours_total = Column(Integer, default=0)         # last known minutes for delta
    show_playing_status = Column(Boolean, default=False)   # Show currently-playing game on profile/posts
    current_game = Column(String(255), nullable=True)      # Name of game being played right now (null = not playing)

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
    notify_giveaways = Column(Boolean, default=True)      # New giveaway launched
    notify_lfg_join = Column(Boolean, default=True)       # Someone joins my LFG group
    notify_lfg_leave = Column(Boolean, default=True)      # Someone leaves my LFG group
    notify_lfg_full = Column(Boolean, default=True)       # My LFG group is full
    notify_community_join = Column(Boolean, default=False) # New member joins my community

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

    # Admin flags
    is_vip = Column(Boolean, default=False)    # Early tester / VIP status
    is_admin = Column(Boolean, default=False)  # Site admin
    admin_pin_hash = Column(String(256), nullable=True)  # bcrypt hash of admin PIN
    admin_pin_set_at = Column(BigInteger, nullable=True)  # When PIN was last set
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
    owned_communities = relationship("WebCommunity", back_populates="owner")
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
    owner = relationship("WebUser", back_populates="owned_communities")

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

    # Stats (updated periodically)
    member_count = Column(Integer, default=0)
    online_count = Column(Integer, default=0)
    activity_level = Column(String(20), default='unknown')  # low, medium, high, very_high

    # QuestLog Network membership
    network_member = Column(Boolean, default=False)
    network_approved_at = Column(BigInteger, nullable=True)
    network_status = Column(String(20), default='none')  # none, pending, approved, denied, banned

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

    # Scheduling
    scheduled_time = Column(BigInteger, nullable=True)  # Unix timestamp
    duration_hours = Column(Integer, nullable=True)
    timezone = Column(String(50), nullable=True)

    # Platform for voice/communication
    voice_platform = Column(String(50), nullable=True)  # discord, teamspeak, etc.
    voice_link = Column(String(500), nullable=True)  # Invite link

    # Status
    status = Column(String(20), default='open')  # open, full, started, completed, cancelled

    # Discovery
    allow_network_discovery = Column(Boolean, default=True)  # Show in QuestLog Network

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
    instagram_url = Column(String(500), nullable=True)
    bluesky_url = Column(String(500), nullable=True)
    website_url = Column(String(500), nullable=True)
    discord_url = Column(String(500), nullable=True)
    matrix_url = Column(String(500), nullable=True)       # Matrix room/space
    valor_url = Column(String(500), nullable=True)         # Valor chat
    fluxer_url = Column(String(500), nullable=True)        # Fluxer
    kloak_url = Column(String(500), nullable=True)         # Kloak
    teamspeak_url = Column(String(500), nullable=True)     # TeamSpeak
    revolt_url = Column(String(500), nullable=True)        # Stoat (formerly Revolt)

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

    # Flags
    is_pinned = Column(Boolean, default=False)
    is_deleted = Column(Boolean, default=False)
    is_hidden = Column(Boolean, default=False)  # Admin-hidden

    # Denormalized counters
    like_count = Column(Integer, default=0)
    comment_count = Column(Integer, default=0)
    repost_count = Column(Integer, default=0)

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


class WebFlair(Base):
    """Admin-created cosmetic flair that users can purchase with Hero Points."""
    __tablename__ = 'web_flairs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    emoji = Column(String(20), default='')
    description = Column(String(300), nullable=True)
    flair_type = Column(Enum('normal', 'seasonal', 'exclusive'), default='normal')
    hp_cost = Column(Integer, default=0)
    enabled = Column(Boolean, default=True)
    display_order = Column(Integer, default=0)
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

