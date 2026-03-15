# QuestLog Bot for Fluxer - Complete Guide

Everything you need to know to get the most out of QuestLog Bot on your Fluxer server. Every feature can be configured from the [web dashboard](https://casual-heroes.com/ql/dashboard/fluxer/) - no slash commands required.

---

## Table of Contents

- [Getting Started](#getting-started)
- [XP & Leveling](#xp-leveling)
- [Looking for Group (LFG)](#looking-for-group-lfg)
- [Welcome & Goodbye Messages](#welcome-goodbye-messages)
- [Moderation](#moderation)
- [RSS Feeds](#rss-feeds)
- [Live Stream Alerts](#live-stream-alerts)
- [Reaction Roles](#reaction-roles)
- [Channel Stat Trackers](#channel-stat-trackers)
- [Game Discovery](#game-discovery)
- [Flairs & Ranks](#flairs-ranks)
- [Chat Bridge](#chat-bridge)
- [Early Access Invites](#early-access-invites)
- [QuestLog Network Integration](#questlog-network-integration)
- [Bot Commands Reference](#bot-commands-reference)

---

## Getting Started

### Add the Bot

1. Click **[Add to Fluxer](https://web.fluxer.app/oauth2/authorize?client_id=1478501650237887115&scope=bot&permissions=6756638430588119)**
2. Select your server and approve the permissions
3. The bot will sync your channels, roles, and members automatically within a few seconds

### Access the Dashboard

Go to **[casual-heroes.com/ql/dashboard/fluxer/](https://casual-heroes.com/ql/dashboard/fluxer/)** - you'll be prompted to authenticate with Fluxer (no QuestLog account required). Once logged in, you'll see all servers you own.

### Required Permissions

The bot needs the following permissions to function fully:

| Permission | Used for |
|---|---|
| Manage Roles | Auto-roles, level roles, flair roles |
| Manage Channels | Channel stat trackers |
| Kick/Ban Members | Moderation commands |
| Send Messages | XP level-up, LFG, alerts, welcome |
| Embed Links | Rich embeds for all features |
| Read Message History | Bridge relay, moderation |
| Add Reactions | Bridge reaction relay |

---

## XP & Leveling

Members earn XP by being active in your server. XP accumulates into levels. You configure the rates - the bot handles the rest.

### How XP is Earned

| Activity | Default XP | Cooldown |
|---|---|---|
| Sending a message | 2 XP | 60 seconds |
| Posting media/images | Multiplier on message XP | 60 seconds |
| Voice chat | Configurable per interval | Per interval |
| Reactions | Configurable | Per reaction |

### Configuration (Dashboard)

Go to **Dashboard > XP & Leveling** to configure:

- **XP per message** - How much XP each message earns (default: 2)
- **Cooldown** - Seconds between XP-eligible messages per user (default: 60)
- **Level-up messages** - Enable/disable and customize the message sent when someone levels up
- **Level-up channel** - Where to post level-up announcements. Leave blank to post in the channel where the message was sent
- **Level-up message template** - Customize the text using variables:
  - `{user}` - Mentions the user
  - `{username}` - Display name only
  - `{level}` - The new level reached
  - `{server}` - Server name
- **Ignored channels** - Channels where messages earn no XP
- **Level roles** - Automatically assign a role when a member reaches a specific level

### XP Boost Events

Run time-limited XP multipliers for events, game launches, or community milestones.

1. Go to **Dashboard > XP & Leveling > Boost Events**
2. Set a name, multiplier (e.g. 2x), start time, and end time
3. The boost activates automatically and expires on schedule

Multiple active boosts stack additively: a 2x boost + another 2x boost = 3x total.

### Leaderboard

Members can view the server XP leaderboard at **casual-heroes.com/ql/fluxer/[server-id]/**.

---

## Looking for Group (LFG)

Let members post and find group sessions for any game directly in your server.

### Setup

1. Go to **Dashboard > LFG**
2. Set the **LFG announcement channel** - where new groups get posted
3. Configure whether members can delete their own groups

### Creating a Group

Members create LFG groups from the QuestLog web portal at **casual-heroes.com/ql/fluxer/[server-id]/lfg/browse/**. The bot automatically posts the announcement to your LFG channel.

Alternatively, admins can use `!setup lfg #channel-name` to set the channel via bot command.

### Bot Commands

| Command | Description |
|---|---|
| `!lfg` | Link to this server's LFG page |
| `!lfglist` | Show currently active groups |
| `!lfgjoin <id>` | Get the join link for a specific group |
| `!lfgql` | Link to the QuestLog Network-wide LFG browser |
| `!lfg delete <id>` | Delete a group (your own, or any if you're an admin) |

### LFG Announcements

When a group is created on the website, the bot picks it up within 5 seconds and posts a formatted embed to your LFG channel showing:

- Game name and cover art
- Group size and current members
- Description
- Direct join link

---

## Welcome & Goodbye Messages

Greet new members automatically and say goodbye when they leave.

### Setup

Go to **Dashboard > Welcome Messages** to configure all options.

### Welcome Channel Message

Post a message or embed to a channel when someone joins.

**Available variables:**

| Variable | Value |
|---|---|
| `{user}` | @mention of the new member |
| `{username}` | Display name |
| `{server}` | Server name |
| `{member_count}` | Approximate member count |
| `{member_count_ord}` | Ordinal (e.g. "42nd member") |

### Welcome DM

Send a private message directly to the new member. Supports the same variables. Good for rules, getting-started links, or invite codes.

### Auto-Role

Automatically assign a role to every new member on join. Set this to your default "member" role to grant access to the server.

### Goodbye Messages

Post to a channel when a member leaves or is kicked/banned. Supports `{username}` and `{server}` variables.

### Role Persistence

When a member leaves and rejoins, the bot can restore their previous roles automatically. Dangerous permission roles (admin, ban, kick, manage server) are never restored.

---

## Moderation

Basic moderation commands for server management.

### Commands

| Command | Permission Required | Description |
|---|---|---|
| `!ban @user [reason]` | Ban Members | Permanently ban a member |
| `!tempban @user <hours> [reason]` | Ban Members | Temporarily ban for N hours |
| `!kick @user [reason]` | Kick Members | Kick a member from the server |
| `!timeout @user <minutes> [reason]` | Moderate Members | Mute a member for N minutes |

All moderation actions are logged to the bot's internal audit trail and visible in the dashboard.

### Dashboard Moderation

Go to **Dashboard > Moderation** to:

- View all warnings issued to members
- Pardon (clear) a warning
- Configure which roles have moderation permissions on the web dashboard

---

## RSS Feeds

Subscribe to any RSS or Atom feed and automatically post new articles to a channel.

### Setup

1. Go to **Dashboard > Discovery > RSS Feeds**
2. Click **Add Feed**
3. Enter the feed URL and select a channel
4. Set the poll interval (how often to check for new articles)

### What Gets Posted

For each new article, the bot posts a rich embed with:

- Article title
- Description/summary
- Link to the full article
- Thumbnail (if the feed provides one)
- Publication date

### Security

The bot blocks feeds that point to internal/private IP addresses to prevent SSRF attacks. Public RSS feeds from news sites, blogs, YouTube channels, Twitch, and game stores all work fine.

### Force Check

Server admins can run `!checkrss` to immediately trigger a feed check instead of waiting for the next poll cycle.

---

## Live Stream Alerts

Get notified in a channel when your streamers go live on Twitch or YouTube.

### Setup

1. Go to **Dashboard > Live Alerts**
2. Set the **alert channel** where notifications will be posted
3. Add streamers by their Twitch username or YouTube @handle/channel ID

### How it Works

The bot checks every 60 seconds. When a streamer goes live, it posts an embed with:

- Stream title
- Viewer count
- Game being played
- Stream thumbnail
- Direct link to the stream

The bot tracks live status so it won't re-alert for the same ongoing stream. A new alert fires when they go offline and come back live again.

### Supported Platforms

| Platform | How to Add |
|---|---|
| Twitch | Enter their Twitch username |
| YouTube | Enter their @handle or channel ID (UCxxxxxxxx) |

---

## Reaction Roles

Let members self-assign roles by reacting to a message with a specific emoji.

### Setup

1. Go to **Dashboard > Reaction Roles**
2. Create a new reaction role message
3. Add emoji + role pairs
4. The bot will watch that message for reactions

When a member adds a reaction, the bot assigns the corresponding role. When they remove the reaction, the role is removed.

---

## Channel Stat Trackers

Display live stats in channel names or topics - like a live member count that updates automatically.

### Setup

1. Go to **Dashboard > Trackers**
2. Click **Add Tracker**
3. Select the channel to update, the role to count, a label, and an optional emoji

### How it Works

Every 60 seconds the bot updates the channel topic with the current count of members holding the specified role. Format: `{emoji} {label}: {count} members`

Example: `🎮 Active Members: 142 members`

You can force a refresh with `!refreshtrackers` (server owner only).

---

## Game Discovery

Automatically discover and announce new upcoming games that match your community's interests.

### Setup

1. Go to **Dashboard > Discovery**
2. Enable game discovery and set an announcement channel
3. Add one or more **search configs** - each config defines a set of filters

### Search Config Filters

| Filter | Description |
|---|---|
| Genres | RPG, FPS, Strategy, etc. |
| Themes | Fantasy, Sci-Fi, Horror, etc. |
| Keywords | Specific keywords from game descriptions |
| Game modes | Single player, Co-op, Multiplayer |
| Platforms | PC, PlayStation, Xbox, etc. |
| Min hype score | Minimum IGDB hype rating |
| Min rating | Minimum IGDB user rating |
| Release window | How many days ahead to look |

### How it Works

Every 15 minutes (configurable), the bot searches IGDB for games matching your filters that haven't been announced yet. New matches are posted to your discovery channel and saved to the member portal.

Run `!checkgames` to trigger an immediate check (server owner/admin only).

---

## Flairs & Ranks

Members earn cosmetic flairs and rank titles as they level up. These sync with the QuestLog site flair shop.

### How it Works

- Members earn flairs automatically by reaching XP/level milestones
- Flairs can also be purchased with Hero Points in the QuestLog flair shop
- When a member equips a flair on the website, the bot automatically creates and assigns a corresponding Fluxer role named `Flair: {emoji} {name}`
- Only one flair role is active at a time - the bot removes old ones when a new one is equipped

### Dashboard

Go to **Dashboard > Flairs** to create server-specific flairs. Set a name, emoji, Hero Point cost, and the level required to unlock it.

---

## Chat Bridge

Relay messages between your Fluxer server and Discord or Matrix channels in real time.

### Setup

1. Go to **Dashboard > Bridge**
2. Add a bridge configuration
3. Select the Fluxer channel on your end
4. The other side (Discord/Matrix) is set up by the respective bot

### What Gets Relayed

- Text messages
- Replies (shown as quoted context)
- Attachments (linked, not re-uploaded)
- Reactions (unicode emoji only; custom emoji appear as `:name:`)
- Message deletions

### Message Format

Bridged messages appear prefixed with the platform source:

- `**[D] Username:** message` - from Discord
- `**[F] Username:** message` - from Fluxer
- `**[M] Username:** message` - from Matrix

The bridge will never relay its own messages to prevent loops.

---

## Early Access Invites

Generate QuestLog early-access invite codes directly from Fluxer.

### Command

```
!invite
```

The bot DMs you a personal invite code for QuestLog. Codes are 10 characters, alphanumeric. Each user gets a unique code and can request a new one every hour.

Only works in servers that have been whitelisted for early access by the QuestLog team.

---

## QuestLog Network Integration

Connecting your Fluxer server to the QuestLog Network unlocks cross-platform features.

### What You Get

- Members' Fluxer XP flows into their **unified QuestLog profile** alongside Discord and site activity
- **One leaderboard** across all platforms - Fluxer + Discord + QuestLog site
- Your server gets a **public community profile** in the QuestLog community directory
- Members can view unified stats at **casual-heroes.com/ql/**

### How to Join

1. Create a QuestLog account at **casual-heroes.com/ql/register/**
2. Link your Fluxer account in **Settings > Linked Accounts**
3. Apply at **casual-heroes.com/ql/communities/register/**
4. Once approved, link the Fluxer server in your community settings

### Member Linking

Members link their own Fluxer accounts in **casual-heroes.com/ql/settings/** under "Linked Accounts". Once linked, their XP automatically unifies. No bot command needed.

---

## Bot Commands Reference

| Command | Permission | Description |
|---|---|---|
| `!lfg` | Everyone | Link to server LFG page |
| `!lfglist` | Everyone | List active LFG groups |
| `!lfgjoin <id>` | Everyone | Get join link for a group |
| `!lfgql` | Everyone | Link to QuestLog Network LFG |
| `!lfg delete <id>` | Group owner / Admin | Delete an LFG group |
| `!setup lfg #channel` | Admin | Set LFG announcement channel |
| `!setup status` | Admin | Show current bot configuration |
| `!checkrss` | Admin | Force immediate RSS feed check |
| `!checkgames` | Admin | Force immediate game discovery check |
| `!refreshtrackers` | Owner | Force update channel stat trackers |
| `!invite` | Everyone (whitelisted servers) | Get a QuestLog early access code |
| `!ban @user [reason]` | Ban Members | Permanently ban a member |
| `!tempban @user <hours> [reason]` | Ban Members | Temporarily ban a member |
| `!kick @user [reason]` | Kick Members | Kick a member |
| `!timeout @user <minutes> [reason]` | Moderate Members | Timeout a member |
