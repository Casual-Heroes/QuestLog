# QuestLog Bot for Discord - Complete Guide

Everything you need to know to get the most out of QuestLog Bot on your Discord server. Every feature can be configured from the [web dashboard](https://casual-heroes.com/ql/dashboard/discord/) - no slash commands required for most settings.

---

## Table of Contents

- [Getting Started](#getting-started)
- [XP & Leveling](#xp-leveling)
- [Looking for Group (LFG)](#looking-for-group-lfg)
- [Welcome & Goodbye Messages](#welcome-goodbye-messages)
- [Verification](#verification)
- [Moderation & Auto-Mod](#moderation-auto-mod)
- [Reaction Roles](#reaction-roles)
- [Role Management](#role-management)
- [RSS Feeds](#rss-feeds)
- [Live Stream Alerts](#live-stream-alerts)
- [Raffles](#raffles)
- [Scheduled Messages](#scheduled-messages)
- [Audit Logging](#audit-logging)
- [Channel Management](#channel-management)
- [Flairs & Ranks](#flairs-ranks)
- [QuestLog Network Integration](#questlog-network-integration)
- [Slash Commands Reference](#slash-commands-reference)

---

## Getting Started

### Add the Bot

1. Click **[Add to Discord](https://discord.com/oauth2/authorize?client_id=YOUR_ID&scope=bot+applications.commands&permissions=8)**
2. Select your server and approve the permissions
3. Run `/questlog sync` once to register all slash commands in your server

### Access the Dashboard

Go to **[casual-heroes.com/ql/dashboard/discord/](https://casual-heroes.com/ql/dashboard/discord/)** - you'll be prompted to authenticate with Discord. Once logged in, you'll see all servers you manage.

### Required Permissions

| Permission | Used for |
|---|---|
| Administrator | Full feature access (recommended) |
| Manage Roles | Auto-roles, level roles, verification, reaction roles |
| Manage Channels | Channel management, stat trackers |
| Kick/Ban Members | Moderation commands |
| Moderate Members | Timeout command |
| Send Messages | All bot responses and announcements |
| Embed Links | Rich embeds for all features |
| Read Message History | Audit logging, moderation |
| Add Reactions | Reaction role setup |
| Use Application Commands | Slash commands |

---

## XP & Leveling

Members earn XP through activity across multiple sources. XP accumulates into levels with configurable rewards.

### XP Sources

| Source | Default | Cooldown | Notes |
|---|---|---|---|
| Messages | 2 XP | 60 sec | Per channel, per user |
| Media/Images | Multiplier | 60 sec | Applied on top of message XP |
| Voice chat | Configurable | Per interval | While connected and not muted |
| Reactions | Configurable | Per reaction | Given to the reactor |
| Slash commands | Configurable | Configurable | Any command usage |
| Gaming activity | Configurable | Per interval | Discord presence/activity detection |
| Invites | Configurable | Per invite | When someone joins via your invite link |

### Configuration (Dashboard)

Go to **Dashboard > XP & Leveling** to configure:

- **Enable/disable XP** - Toggle the whole system on or off
- **Per-source rates** - Set XP amounts individually for each source
- **Cooldowns** - Control how often each source can earn XP per user
- **Media multiplier** - Bonus multiplier when a message includes an image or attachment
- **Max level** - Cap progression (default: 99)
- **Level-up messages** - Announce when someone levels up
- **Excluded channels/roles** - Channels or roles that earn no XP

### Level Formula

XP required for each level uses a progressive curve: `level_xp = 7 * (level + 1)^1.5`

This means early levels are quick, later levels take more time - rewarding long-term active members.

### Level Roles

Automatically assign roles at milestone levels:

1. Go to **Dashboard > XP & Leveling > Level Roles**
2. Add a role and the level required to earn it
3. The bot assigns the role automatically when a member hits that level

### XP Boost Events

Run time-limited multipliers for game launches, events, or milestones:

1. Go to **Dashboard > XP & Leveling > Boost Events**
2. Set a name, multiplier, start time, and end time
3. The boost activates and expires automatically

Multiple active boosts stack additively: 2x + 2x = 3x total.

### Hero Tokens

Alongside XP, members earn Hero Tokens used across the QuestLog economy:
- Active XP sources (messages, voice, reactions): 15 tokens per 100 XP
- Passive XP sources (gaming activity): 5 tokens per 100 XP

Tokens are spent on raffles, flair purchases, and featured pool entries.

---

## Looking for Group (LFG)

A full group-finding system for any game. Members create posts, others join, threads keep communication organized.

### Setup

1. Go to **Dashboard > LFG**
2. Enable LFG and set the announcement channel
3. Configure optional settings: threads, attendance tracking, group expiry

### Creating a Group

Members use `/lfg create` in Discord or create groups from the QuestLog web portal. When created, the bot:

1. Posts a formatted embed in your LFG channel
2. Creates a dedicated thread for group discussion (if enabled)
3. Lists the group in the web portal's LFG browser

### Slash Commands

| Command | Description |
|---|---|
| `/lfg create` | Create a new group |
| `/lfg list` | Browse active groups |
| `/lfg join <id>` | Join a group |
| `/lfg leave` | Leave your current group |
| `/lfg delete` | Delete your group (admins can delete any) |

### Game Search

When creating a group, the bot searches IGDB for the game name you type. It returns the canonical name and cover art to use in the LFG embed. You can also use custom games defined by your server admins.

### Roles (Game-Specific)

For games with structured roles (Tank/Healer/DPS, etc.), members can specify which role they're filling. Your server can configure custom role systems for your specific games.

### Threads

When thread mode is enabled, the bot creates a dedicated thread for each group. It cleans up the automatic "X joined the thread" system messages to keep things tidy.

### Attendance Tracking

With attendance tracking enabled, the bot records who attended each session. Members can see their attendance stats and admins can view session history in the dashboard.

---

## Welcome & Goodbye Messages

Fully customizable messages when members join or leave.

### Setup

Go to **Dashboard > Welcome** to configure all options.

### Welcome Channel Message

Post to a public channel when someone joins. Supports text or a full embed (title, description, color, thumbnail, footer).

**Available variables:**

| Variable | Value |
|---|---|
| `{user}` | @mention of the new member |
| `{username}` | Display name |
| `{discriminator}` | User discriminator (#0000) |
| `{user_id}` | Discord user ID |
| `{server}` | Server name |
| `{member_count}` | Total member count |
| `{member_count_ord}` | Ordinal (e.g. "42nd") |
| `{join_number}` | Which join this is (your server's sequence) |
| `{join_number_ord}` | Ordinal form of join number |
| `{created_at}` | When their Discord account was created |
| `{avatar_url}` | Link to their profile picture |

### Welcome DM

Send a private welcome message directly to the new member. Same variables supported. Good for rules, invite links, or getting-started guides.

### Goodbye Messages

Announce when a member leaves. Supports `{username}` and `{server}`. Set a separate channel from welcome if preferred.

### Auto-Role

Assign one or more roles automatically when a member joins. Use this for your default "member" role, verified role, or any role all members should have.

---

## Verification

Gate new members behind a verification step before they can access your server.

### Setup

1. Go to **Dashboard > Verification**
2. Choose a verification type
3. Set quarantine and verified role IDs
4. Configure timeout (auto-kick if unverified after N minutes)

### Verification Types

| Type | Description | Best For |
|---|---|---|
| **None** | No verification - all members get access instantly | Small, trusted servers |
| **Button** | Member clicks an "I agree" button | Simple rules acceptance |
| **Captcha** | Member solves an image CAPTCHA (6 characters) | Blocking basic bot attacks |
| **Account Age** | Auto-verify if account is older than X days | Filtering brand-new accounts |
| **Multi-Step** | Combination of steps + intro message | High-security servers |

### How the Quarantine Works

Unverified members:
- Are assigned the **quarantine role** (no channel access)
- Can only see the verification channel
- Have N minutes to complete verification before being auto-kicked

Once verified:
- Quarantine role is removed
- Verified role is assigned
- Full server access granted

### CAPTCHA Details

The captcha is a server-side image challenge:
- 6 random characters displayed in a distorted image
- 5-minute expiry
- Member types the code in a modal
- Incorrect answers prompt them to try again

---

## Moderation & Auto-Mod

Manual moderation tools plus automatic detection of harmful content.

### Manual Commands

| Command | Permission | Description |
|---|---|---|
| `/mod warn <user> [reason]` | Manage Messages | Issue a formal warning |
| `/mod timeout <user> <duration> [reason]` | Moderate Members | Temporarily mute |
| `/mod kick <user> [reason]` | Kick Members | Remove from server |
| `/mod ban <user> [reason]` | Ban Members | Permanently ban |
| `/mod jail <user> [reason]` | Manage Roles | Restrict all channel access |
| `/mod mute <user> [reason]` | Manage Roles | Block send message permission |

### Auto-Moderation

Enable auto-mod from **Dashboard > Moderation > Auto-Mod**.

**What it detects:**
- Racist and xenophobic slurs
- Homophobic slurs
- Ableist slurs
- Hate speech and suicide baiting

**Escalation system:**
- 3 warnings in 30 days - automatic timeout
- 5 warnings in 30 days - automatic jail (restricted access)
- The bot will **never** automatically ban - that always requires a human decision

**Warning Decay:** Warnings older than 30 days don't count toward escalation thresholds.

**Strict Mode:** Enable an additional set of lower-confidence patterns for servers that want more aggressive filtering.

### Dashboard

Go to **Dashboard > Moderation** to:
- View all warnings for every member
- Pardon individual warnings
- Configure the jail role and muted role
- Set escalation thresholds

---

## Reaction Roles

Members self-assign roles by reacting to a message with a specific emoji.

### Setup

1. Go to **Dashboard > Reaction Roles**
2. Add a new reaction role setup - paste the message ID and channel
3. Map emoji to roles
4. Save - the bot starts watching that message immediately

### How it Works

- Member adds a reaction: bot assigns the corresponding role
- Member removes the reaction: bot removes the role
- Works with both Unicode emoji and custom server emoji

---

## Role Management

Tools for managing roles at scale.

### Features

| Feature | Description |
|---|---|
| **Role Templates** | Save a role configuration and reapply it to create consistent roles |
| **Mass Operations** | Add or remove a role from multiple members at once |
| **Temp Roles** | Assign a role for a limited time - auto-expires |
| **Role Requests** | Members request specific roles; mods approve or deny |
| **Level Roles** | Auto-assign roles at XP level milestones |
| **Access Audit** | Export a CSV of which members hold which roles |

### Safety

The bot flags and blocks operations on roles with dangerous permissions:
- Administrator
- Ban/Kick Members
- Manage Guild, Roles, or Channels
- Manage Webhooks or Messages
- Mention @everyone

These will never be mass-assigned or included in templates.

---

## RSS Feeds

Subscribe to any RSS or Atom feed and post new articles to a channel automatically.

### Setup

1. Go to **Dashboard > Discovery > RSS Feeds** (or use `/rss add <url>`)
2. Enter the feed URL and select a channel
3. Set the poll interval

### Feed Limits

| Plan | Max Feeds |
|---|---|
| Free | 3 feeds |
| Premium+ | Unlimited |

### How it Works

The bot checks feeds on your configured interval (5, 10, 15, 30, or 60 minutes). New entries are posted as embeds with title, description, link, thumbnail, and publish date.

To prevent duplicate posts across restarts, the bot tracks all posted entries in the database.

### Security

Feeds pointing to private IP ranges, localhost, or internal domains are blocked to prevent SSRF attacks. All standard public RSS feeds (news, blogs, YouTube, game stores) work fine.

### Backoff

If a feed returns errors repeatedly, the bot backs off exponentially up to 60 minutes between checks to avoid hammering a down server.

---

## Live Stream Alerts

Notify your server when streamers go live.

### Setup

1. Go to **Dashboard > Live Alerts**
2. Set the alert channel and optional role ping
3. Add streamers by their platform handle

### Supported Platforms

| Platform | How to Add |
|---|---|
| Twitch | Enter their Twitch username |
| YouTube | Enter their @handle or channel ID |

### How it Works

The bot checks every 3 minutes. When a streamer goes live, it posts an embed with stream title, viewer count, game, thumbnail, and a direct link.

Live status is tracked in the database - the bot won't re-alert for the same ongoing stream session. A new alert fires when they start a new stream.

---

## Raffles

Run giveaways with ticket-based entry.

### Setup

1. Go to **Dashboard > Raffles**
2. Create a new raffle with a title, entry cost (Hero Tokens), end time, and number of winners
3. The bot announces the raffle in your configured channel

### How Members Enter

Members enter via the web portal or the bot's raffle command. They can spend Hero Tokens on extra tickets for better odds.

### Winner Selection

Winners are selected using a cryptographically random weighted draw based on ticket count. Multiple winners are drawn without replacement.

### Templates

Customize announcement and winner messages using variables:

**Announcement:** `{title}`, `{cost}`, `{end}`, `{role}`, `{guild}`

**Winner:** `{user}`, `{title}`, `{guild}`

---

## Scheduled Messages

Post recurring announcements automatically.

### Setup

1. Go to **Dashboard > Messages > Scheduled**
2. Create a message with content, target channel, and schedule
3. The bot posts on schedule without any manual intervention

Good for: daily reminders, weekly event announcements, rotating tips, server rules refreshers.

---

## Audit Logging

Comprehensive logging of all server events.

### What Gets Logged

| Category | Events |
|---|---|
| Members | Join, leave, ban, unban, kick, timeout, nickname change |
| Roles | Add, remove, create, delete, update |
| Channels | Create, delete, update |
| Messages | Delete, bulk delete |
| Server | Settings changes, permission updates |
| Security | Raid detection, lockdowns, verification passes/fails |

### Log Retention

| Plan | Retention |
|---|---|
| Free | 7 days |
| Premium | 30 days |
| Pro | 90 days |

### Viewing Logs

Go to **Dashboard > Audit** to browse, filter, and search logs by action type, user, or date range. Logs can be exported as CSV.

---

## Channel Management

Tools for managing channels at scale.

### Features

| Feature | Description |
|---|---|
| **Channel Templates** | Save a channel's permission and settings config to reuse |
| **Template Application** | Create a new channel from a saved template |
| **Bulk Slowmode** | Apply slowmode to multiple channels at once |
| **Permission Audit** | Verify what a role or member can actually do in each channel |
| **Channel Archival** | Archive old channels instead of deleting them |

### Setup

Use `/channels save-template [#channel]` to capture a channel's current settings as a template.

---

## Flairs & Ranks

Cosmetic rewards that members earn as they level up.

### How it Works

- Members earn **rank titles** at level milestones (e.g. "Adventurer", "Champion", "Legend")
- **Flairs** are emoji badges earned or purchased with Hero Tokens in the flair shop
- Equipped flairs appear beside usernames in posts and on member profiles
- The bot assigns a corresponding Discord role named `Flair: {emoji} {name}` when a flair is equipped
- Only one flair role is active at a time

### Configuration

Go to **Dashboard > Flairs** to create server-specific flairs with custom names, emoji, Hero Token costs, and level requirements.

Go to **Dashboard > XP > Rank Titles** to create and order the rank titles members progress through.

---

## QuestLog Network Integration

Connect your server to the QuestLog Network for cross-platform features.

### What You Get

- Members' Discord XP flows into their **unified QuestLog profile** alongside Fluxer and site activity
- **One leaderboard** across all platforms
- Your server gets a **public community profile** in the QuestLog community directory
- Members can view stats and their social profile at **casual-heroes.com/ql/**

### How to Join

1. Create a QuestLog account at **casual-heroes.com/ql/register/**
2. Link your Discord account in **Settings > Linked Accounts**
3. Apply at **casual-heroes.com/ql/communities/register/**
4. Once approved, your server is part of the network

### Member Linking

Each member links their own Discord account at **casual-heroes.com/ql/settings/** under "Linked Accounts". Once linked, their XP unifies automatically. No bot action required.

---

## Slash Commands Reference

| Command | Permission | Description |
|---|---|---|
| `/questlog setup` | Admin | Initial bot configuration wizard |
| `/questlog sync` | Admin | Sync slash commands to this server |
| `/lfg create` | Everyone | Create an LFG group |
| `/lfg list` | Everyone | Browse active groups |
| `/lfg join <id>` | Everyone | Join a group |
| `/lfg leave` | Everyone | Leave your group |
| `/lfg delete` | Group owner / Admin | Delete a group |
| `/lfg setup` | Admin | Configure LFG settings |
| `/mod warn <user>` | Manage Messages | Issue a warning |
| `/mod timeout <user> <duration>` | Moderate Members | Timeout a member |
| `/mod kick <user>` | Kick Members | Kick a member |
| `/mod ban <user>` | Ban Members | Ban a member |
| `/mod jail <user>` | Manage Roles | Jail a member |
| `/mod mute <user>` | Manage Roles | Mute a member |
| `/automod config` | Admin | Configure auto-moderation |
| `/verification setup` | Admin | Configure member verification |
| `/welcome setup` | Admin | Configure welcome messages |
| `/rss add <url>` | Admin | Add an RSS feed |
| `/roles templates` | Admin | Manage role templates |
| `/channels save-template` | Admin | Save a channel config as template |
| `/audit logs` | Admin | View audit log |
| `/emergency lockdown` | Admin | Restrict server to mods only |
| `/emergency unlock` | Admin | Restore normal permissions |
| `/admin setup` | Admin | Server-wide admin settings |
