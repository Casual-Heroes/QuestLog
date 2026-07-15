"""
Management command: snapshot_palworld_stats
Runs once daily (via cron). For every configured Palworld instance, parses its
Level.sav world save (via the palsav-flex library - handles Palworld's post-v0.6
Oodle compression and struct-layout changes that the older palworld-save-tools
library can't) and records a daily snapshot: every player's level/guild/captures/
boss-kills, and every owned Pal's species/level/IVs, for the Best Pals Leaderboard
and Community Health dashboard.

Read-only against the save file - only ever opens it in 'rb' mode, never writes
back to it or to AMP's instance directory in any way.

Cron setup (run as www-data or the app user):
    30 4 * * * /srv/ch-webserver/chwebsiteprj/bin/python /srv/ch-webserver/manage.py snapshot_palworld_stats >> /srv/ch-webserver/logs/palworld_snapshot.log 2>&1
"""
import datetime
import glob
import json
import logging
import os
import time

from django.core.management.base import BaseCommand

from app.db import get_engine
from sqlalchemy import text

logger = logging.getLogger(__name__)

# .NET DateTime ticks (100ns intervals since 0001-01-01) -> Unix epoch offset
_DOTNET_EPOCH_TICKS = 621355968000000000


def _ticks_to_unix(ticks) -> int | None:
    if not ticks:
        return None
    try:
        return int((int(ticks) - _DOTNET_EPOCH_TICKS) / 10_000_000)
    except (TypeError, ValueError):
        return None


def _find_palworld_save_dir(instance_root: str) -> str | None:
    """Palworld's save path is <instance_root>/palworld/2394010/Pal/Saved/SaveGames/0/<WorldID>/
    - the WorldID folder name is unpredictable (a hex GUID), so we glob for it."""
    pattern = os.path.join(instance_root, 'palworld', '*', 'Pal', 'Saved', 'SaveGames', '0', '*')
    matches = [m for m in glob.glob(pattern) if os.path.isdir(m)]
    if not matches:
        return None
    # If multiple world folders exist (shouldn't normally happen), take the most
    # recently modified Level.sav as the active one.
    matches.sort(key=lambda p: os.path.getmtime(os.path.join(p, 'Level.sav')) if os.path.exists(os.path.join(p, 'Level.sav')) else 0)
    return matches[-1]


def _parse_sav_properties(sav_path: str) -> dict:
    """Parse any Palworld .sav file using palsav-flex. Returns the raw GVAS
    properties dict. Raises on failure - caller is responsible for catching and
    recording the error rather than crashing the whole run. Read-only: only ever
    opens the file in 'rb' mode, never writes back to it."""
    from palsav.gvas import GvasFile
    from palsav.core import decompress_sav_to_gvas
    from palsav.paltypes import PALWORLD_CUSTOM_PROPERTIES, PALWORLD_TYPE_HINTS

    with open(sav_path, 'rb') as f:
        raw = f.read()
    gvas_data, _save_type = decompress_sav_to_gvas(raw)
    gvas = GvasFile.read(gvas_data, PALWORLD_TYPE_HINTS, PALWORLD_CUSTOM_PROPERTIES, allow_nan=True)
    return gvas.properties


def _get_player_save_data(save_dir: str, player_uid: str) -> dict | None:
    """Parse this player's individual save file (Players/<UID-no-dashes>.sav) once
    and return its full SaveData dict - this is where capture/boss-kill counts,
    tech points, and last-online timestamp live, NONE of which are in Level.sav's
    CharacterSaveParameterMap. Returns None if the file is missing or fails to
    parse (best-effort - one bad player file shouldn't abort the whole instance's
    snapshot, it just means that player's extra fields stay null)."""
    filename = player_uid.replace('-', '').upper() + '.sav'
    player_sav_path = os.path.join(save_dir, 'Players', filename)
    if not os.path.exists(player_sav_path):
        return None
    try:
        properties = _parse_sav_properties(player_sav_path)
        return properties.get('SaveData', {}).get('value', {})
    except Exception as e:
        logger.warning(f'snapshot_palworld_stats: failed to parse player file {player_sav_path}: {e}')
        return None


def _extract_guild_membership(world_save_data: dict) -> dict[str, tuple[str, str, int]]:
    """Returns {player_uid: (guild_id, guild_name, base_camp_level)} by scanning
    GroupSaveDataMap for Guild-type groups and their player rosters."""
    membership: dict[str, tuple[str, str, int]] = {}
    groups = world_save_data.get('GroupSaveDataMap', {}).get('value', [])
    for group in groups:
        raw_data = group.get('value', {}).get('RawData', {}).get('value', {})
        if raw_data.get('group_type') != 'EPalGroupType::Guild':
            continue
        guild_id = str(raw_data.get('group_id', '') or '')
        guild_name = raw_data.get('guild_name', '') or ''
        base_camp_level = raw_data.get('base_camp_level', 0) or 0
        for player in raw_data.get('players', []):
            # palsav-flex returns GUID-typed fields as Python UUID objects, not
            # strings - normalize immediately so dict keys/DB values/filename
            # construction downstream all see a consistent plain string.
            player_uid = str(player.get('player_uid', '') or '')
            if player_uid:
                membership[player_uid] = (guild_id, guild_name, base_camp_level)
    return membership


def _extract_player_records(sp: dict) -> list[str]:
    """Given RecordData's 'value' dict, extract counts we care about. Returns
    (total_captures, species_discovered, boss_kills, favorite_species)."""
    total_captures = 0
    species_discovered = 0
    boss_kills = 0
    favorite_species = None

    pal_capture_count = sp.get('PalCaptureCount', {}).get('value', [])
    if isinstance(pal_capture_count, list):
        best_count = -1
        for entry in pal_capture_count:
            count = entry.get('value', 0) or 0
            total_captures += count
            if count > best_count:
                best_count = count
                favorite_species = entry.get('key')

    paldeck = sp.get('PaldeckUnlockFlag', {}).get('value', [])
    if isinstance(paldeck, list):
        species_discovered = sum(1 for e in paldeck if e.get('value'))

    boss_flags = sp.get('NormalBossDefeatFlag', {}).get('value', [])
    if isinstance(boss_flags, list):
        boss_kills = sum(1 for e in boss_flags if e.get('value'))

    return total_captures, species_discovered, boss_kills, favorite_species


class Command(BaseCommand):
    help = 'Parse each configured Palworld instance\'s Level.sav and record a daily player/pal stats snapshot.'

    def handle(self, *args, **options):
        engine = get_engine()
        today = datetime.date.today()
        now = int(time.time())

        with engine.connect() as conn:
            instances = conn.execute(text(
                "SELECT instance_name, amp_log_dir FROM gamebot_configs "
                "WHERE game_type LIKE '%Palworld%' AND configured = 1 AND amp_log_dir IS NOT NULL"
            )).fetchall()

        if not instances:
            logger.info('snapshot_palworld_stats: no configured Palworld instances found, nothing to do')
            return

        for instance_name, amp_log_dir in instances:
            instance_root = os.path.dirname(amp_log_dir)  # AMP_Logs is a sibling of the game's own root
            try:
                self._snapshot_instance(engine, instance_name, instance_root, today, now)
            except Exception as e:
                logger.error(f'snapshot_palworld_stats: unhandled error for {instance_name}: {e}')
                self._record_failed_snapshot(engine, instance_name, today, now, str(e))

    def _record_failed_snapshot(self, engine, instance_name: str, today, now: int, error_message: str):
        try:
            with engine.connect() as conn:
                conn.execute(text(
                    "INSERT INTO palworld_snapshots "
                    "(instance_name, snapshot_date, taken_at, parse_ok, error_message) "
                    "VALUES (:inst, :date, :now, 0, :err) "
                    "ON DUPLICATE KEY UPDATE parse_ok = 0, error_message = :err, taken_at = :now"
                ), {'inst': instance_name, 'date': today, 'now': now, 'err': error_message[:2000]})
                conn.commit()
        except Exception as e:
            logger.error(f'snapshot_palworld_stats: could not even record failure for {instance_name}: {e}')

    def _snapshot_instance(self, engine, instance_name: str, instance_root: str, today, now: int):
        save_dir = _find_palworld_save_dir(instance_root)
        if not save_dir:
            logger.warning(f'snapshot_palworld_stats: no Palworld save directory found under {instance_root} for {instance_name}')
            self._record_failed_snapshot(engine, instance_name, today, now, 'No Palworld save directory found')
            return

        level_sav = os.path.join(save_dir, 'Level.sav')
        if not os.path.exists(level_sav):
            logger.warning(f'snapshot_palworld_stats: {level_sav} does not exist for {instance_name}')
            self._record_failed_snapshot(engine, instance_name, today, now, f'{level_sav} does not exist')
            return

        logger.info(f'snapshot_palworld_stats: parsing {level_sav} for {instance_name}')
        try:
            properties = _parse_sav_properties(level_sav)
        except Exception as e:
            logger.error(f'snapshot_palworld_stats: failed to parse {level_sav} for {instance_name}: {e}')
            self._record_failed_snapshot(engine, instance_name, today, now, f'Parse failed: {e}')
            return

        world_save_data = properties.get('worldSaveData', {}).get('value', {})
        char_map = world_save_data.get('CharacterSaveParameterMap', {}).get('value', [])
        guild_membership = _extract_guild_membership(world_save_data)

        player_rows = []
        pal_rows = []

        for entry in char_map:
            key = entry.get('key', {})
            raw_data = entry.get('value', {}).get('RawData', {}).get('value', {})
            sp = raw_data.get('object', {}).get('SaveParameter', {}).get('value')
            if not sp:
                continue  # unparseable/unknown entry (e.g. an egg) - skip, don't crash

            is_player = bool(sp.get('IsPlayer', {}).get('value'))
            player_uid = str(key.get('PlayerUId', {}).get('value', '') or '')

            if is_player:
                level = (sp.get('Level', {}).get('value') or {}).get('value', 0)
                name = sp.get('NickName', {}).get('value') or 'Unknown'
                guild_id, guild_name, base_camp_level = guild_membership.get(player_uid, (None, None, None))

                # Captures/boss-kills/tech-points/last-online aren't in Level.sav's
                # CharacterSaveParameterMap - they only live in each player's own
                # individual save file. Best-effort: a missing/corrupt player file
                # just means those specific fields stay null, it doesn't block the
                # player's level/guild (already known from Level.sav) from being recorded.
                total_captures = species_discovered = boss_kills = None
                favorite_species = None
                last_online_at = tech_points = boss_tech_points = None
                player_save_data = _get_player_save_data(save_dir, player_uid)
                if player_save_data:
                    record_data = player_save_data.get('RecordData', {}).get('value')
                    if record_data:
                        total_captures, species_discovered, boss_kills, favorite_species = _extract_player_records(record_data)
                    last_online_at = _ticks_to_unix((player_save_data.get('LastOnlineDateTime', {}) or {}).get('value'))
                    tech_points = (player_save_data.get('TechnologyPoint', {}) or {}).get('value')
                    boss_tech_points = (player_save_data.get('bossTechnologyPoint', {}) or {}).get('value')

                player_rows.append({
                    'player_uid': player_uid,
                    'player_name': name,
                    'level': level,
                    'guild_id': guild_id,
                    'guild_name': guild_name,
                    'base_camp_level': base_camp_level,
                    'last_online_at': last_online_at,
                    'tech_points': tech_points,
                    'boss_tech_points': boss_tech_points,
                    'total_captures': total_captures,
                    'species_discovered': species_discovered,
                    'boss_kills': boss_kills,
                    'favorite_species': favorite_species,
                })
            else:
                character_id = sp.get('CharacterID', {}).get('value')
                if not character_id:
                    continue
                level = (sp.get('Level', {}).get('value') or {}).get('value', 0)
                talent_hp = (sp.get('Talent_HP', {}).get('value') or {}).get('value', 0)
                talent_shot = (sp.get('Talent_Shot', {}).get('value') or {}).get('value', 0)
                talent_defense = (sp.get('Talent_Defense', {}).get('value') or {}).get('value', 0)
                gender_raw = (sp.get('Gender', {}).get('value') or {}).get('value', '')
                gender = gender_raw.rsplit('::', 1)[-1] if gender_raw else ''
                passive_skills = (sp.get('PassiveSkillList', {}).get('value') or {}).get('values', [])
                owned_since = _ticks_to_unix((sp.get('OwnedTime', {}) or {}).get('value'))
                is_rare_pal = bool(sp.get('IsRarePal', {}).get('value'))
                owner_uid_raw = sp.get('OwnerPlayerUId', {}).get('value')
                pal_rows.append({
                    'pal_instance_id': str(key.get('InstanceId', {}).get('value', '') or ''),
                    'owner_player_uid': str(owner_uid_raw) if owner_uid_raw else None,
                    'species': character_id,
                    'level': level,
                    'gender': gender,
                    'talent_hp': talent_hp,
                    'talent_shot': talent_shot,
                    'talent_defense': talent_defense,
                    'iv_total': talent_hp + talent_shot + talent_defense,
                    'passive_skills': json.dumps(passive_skills),
                    'owned_since': owned_since,
                    'is_rare_pal': is_rare_pal,
                })

        total_guilds = len({v[0] for v in guild_membership.values() if v[0]})

        with engine.connect() as conn:
            conn.execute(text(
                "INSERT INTO palworld_snapshots "
                "(instance_name, snapshot_date, taken_at, total_players, total_pals, total_guilds, parse_ok) "
                "VALUES (:inst, :date, :now, :players, :pals, :guilds, 1) "
                "ON DUPLICATE KEY UPDATE taken_at = :now, total_players = :players, "
                "total_pals = :pals, total_guilds = :guilds, parse_ok = 1, error_message = NULL"
            ), {
                'inst': instance_name, 'date': today, 'now': now,
                'players': len(player_rows), 'pals': len(pal_rows), 'guilds': total_guilds,
            })
            snapshot_id = conn.execute(text(
                "SELECT id FROM palworld_snapshots WHERE instance_name = :inst AND snapshot_date = :date"
            ), {'inst': instance_name, 'date': today}).scalar()

            # Clear any prior rows for this snapshot (re-run safety - ON DUPLICATE
            # KEY above already handles the parent row, but child rows would
            # otherwise duplicate on a same-day re-run).
            conn.execute(text("DELETE FROM palworld_player_snapshots WHERE snapshot_id = :sid"), {'sid': snapshot_id})
            conn.execute(text("DELETE FROM palworld_pal_snapshots WHERE snapshot_id = :sid"), {'sid': snapshot_id})

            for p in player_rows:
                conn.execute(text(
                    "INSERT INTO palworld_player_snapshots "
                    "(snapshot_id, player_uid, player_name, level, guild_id, guild_name, base_camp_level, "
                    " last_online_at, tech_points, boss_tech_points, total_captures, species_discovered, "
                    " boss_kills, favorite_species) "
                    "VALUES (:sid, :uid, :name, :level, :gid, :gname, :bcl, "
                    " :last_online, :tech, :boss_tech, :captures, :species, :bosses, :fav)"
                ), {
                    'sid': snapshot_id, 'uid': p['player_uid'], 'name': p['player_name'],
                    'level': p['level'], 'gid': p['guild_id'], 'gname': p['guild_name'],
                    'bcl': p['base_camp_level'], 'last_online': p['last_online_at'],
                    'tech': p['tech_points'], 'boss_tech': p['boss_tech_points'],
                    'captures': p['total_captures'], 'species': p['species_discovered'],
                    'bosses': p['boss_kills'], 'fav': p['favorite_species'],
                })

            for pal in pal_rows:
                conn.execute(text(
                    "INSERT INTO palworld_pal_snapshots "
                    "(snapshot_id, pal_instance_id, owner_player_uid, species, level, gender, "
                    " talent_hp, talent_shot, talent_defense, iv_total, passive_skills, owned_since, is_rare_pal) "
                    "VALUES (:sid, :pid, :owner, :species, :level, :gender, "
                    " :thp, :tshot, :tdef, :ivtotal, :skills, :owned, :rare)"
                ), {
                    'sid': snapshot_id, 'pid': pal['pal_instance_id'], 'owner': pal['owner_player_uid'],
                    'species': pal['species'], 'level': pal['level'], 'gender': pal['gender'],
                    'thp': pal['talent_hp'], 'tshot': pal['talent_shot'], 'tdef': pal['talent_defense'],
                    'ivtotal': pal['iv_total'], 'skills': pal['passive_skills'], 'owned': pal['owned_since'],
                    'rare': pal['is_rare_pal'],
                })

            conn.commit()

        logger.info(
            f'snapshot_palworld_stats: {instance_name} snapshot complete - '
            f'{len(player_rows)} players, {len(pal_rows)} pals, {total_guilds} guilds'
        )
