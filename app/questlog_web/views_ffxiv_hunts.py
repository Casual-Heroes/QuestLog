import json
import time
import re
import logging
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
from app.db import get_db_session
from app.questlog_web.models import WebFfxivHuntReport, WebFfxivHuntSub, WebUser, WebNotification
from app.questlog_web.helpers import get_web_user, web_login_required, add_web_user_context, sanitize_text

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Static hunt data - S/A ranks by expansion, notable FATEs, notable NMs
# Respawn windows are minimum_hours to maximum_hours after death.
# S-ranks: 72-120h min/max (community reported - actual window is 72h min)
# A-ranks: 4-6h
# B-ranks: ~5 min - not worth community tracking
# ---------------------------------------------------------------------------

DATA_CENTERS = {
    'NA': ['Aether', 'Crystal', 'Dynamis', 'Primal'],
    'EU': ['Chaos', 'Light'],
    'JP': ['Elemental', 'Gaia', 'Mana', 'Meteor'],
    'OC': ['Materia'],
}

DC_WORLDS = {
    'Aether':    ['Adamantoise','Cactuar','Faerie','Gilgamesh','Jenova','Midgardsormr','Sargatanas','Siren'],
    'Crystal':   ['Balmung','Brynhildr','Coeurl','Diabolos','Goblin','Malboro','Mateus','Zalera'],
    'Dynamis':   ['Halicarnassus','Maduin','Marilith','Seraph','Cuchulainn','Kraken','Rafflesia','Phantom'],
    'Primal':    ['Behemoth','Excalibur','Exodus','Famfrit','Hyperion','Lamia','Leviathan','Ultros'],
    'Chaos':     ['Cerberus','Louisoix','Moogle','Omega','Ragnarok','Sagittarius','Spriggan','Twintania'],
    'Light':     ['Alpha','Lich','Odin','Phoenix','Raiden','Shiva','Zodiark','Twintania'],
    'Elemental': ['Aegis','Atomos','Carbuncle','Garuda','Gungnir','Kujata','Tonberry','Typhon'],
    'Gaia':      ['Alexander','Bahamut','Durandal','Fenrir','Ifrit','Ridill','Tiamat','Ultima'],
    'Mana':      ['Anima','Asura','Chocobo','Hades','Ixion','Masamune','Pandaemonium','Titan'],
    'Meteor':    ['Belias','Mandragora','Ramuh','Shinryu','Unicorn','Valefor','Yojimbo','Zeromus'],
    'Materia':   ['Bismarck','Ravana','Sephirot','Sophia','Zurvan'],
}

# Hunt mark data structure:
# key: unique slug
# name: display name
# rank: S / A
# expansion: ARR / HW / SB / ShB / EW / DT
# zone: zone name
# min_respawn_h: minimum hours after death before it can spawn
# max_respawn_h: rough maximum window
# rewards: what drops / why it matters
# notes: any special mechanics

HUNT_MARKS = [
    # ── Dawntrail (DT) S-Ranks ──────────────────────────────────────────────
    {'key':'s_vali',                  'name':'Vali',                       'rank':'S','expansion':'DT', 'zone':'Urqopacha',                    'min_respawn_h':72,'max_respawn_h':120,'rewards':'Nuts, Centurio Seals','notes':'Timed spawn'},
    {'key':'s_otis',                  'name':'Otis',                       'rank':'S','expansion':'DT', 'zone':"Kozama'uka",                   'min_respawn_h':72,'max_respawn_h':120,'rewards':'Nuts, Centurio Seals','notes':'Timed spawn'},
    {'key':'s_neyoozoteel',           'name':'Neyoozoteel',                'rank':'S','expansion':'DT', 'zone':"Yak T'el",                     'min_respawn_h':72,'max_respawn_h':120,'rewards':'Nuts, Centurio Seals','notes':'Spawn trigger: discard 50+ Fish Meal in zone'},
    {'key':'s_sansheya',              'name':'Sansheya',                   'rank':'S','expansion':'DT', 'zone':'Shaaloani',                    'min_respawn_h':72,'max_respawn_h':120,'rewards':'Nuts, Centurio Seals','notes':'Spawn trigger: complete "You Are What You Drink" FATE'},
    {'key':'s_atticus',               'name':'Atticus the Primogenitor',   'rank':'S','expansion':'DT', 'zone':'Heritage Found',               'min_respawn_h':72,'max_respawn_h':120,'rewards':'Nuts, Centurio Seals','notes':'Spawn trigger: craft HQ Rroneek Steak in zone'},
    {'key':'s_the_forecaster',        'name':'The Forecaster',             'rank':'S','expansion':'DT', 'zone':'Living Memory',                'min_respawn_h':72,'max_respawn_h':120,'rewards':'Nuts, Centurio Seals','notes':'Spawn trigger: cast Blue Mage Northerlies at spawn point'},
    # ── Dawntrail A-Ranks ────────────────────────────────────────────────────
    {'key':'a_pkuucha',               'name':'Pkuucha',                    'rank':'A','expansion':'DT', 'zone':'Urqopacha',                    'min_respawn_h':4,'max_respawn_h':6,'rewards':'Nuts, Seals','notes':''},
    {'key':'a_sugarra',               'name':'Sugarra',                    'rank':'A','expansion':'DT', 'zone':"Kozama'uka",                   'min_respawn_h':4,'max_respawn_h':6,'rewards':'Nuts, Seals','notes':''},
    {'key':'a_tlacotl',               'name':'Tlacotl',                    'rank':'A','expansion':'DT', 'zone':"Yak T'el",                     'min_respawn_h':4,'max_respawn_h':6,'rewards':'Nuts, Seals','notes':''},
    {'key':'a_keheniheyamewi',        'name':'Keheniheyamewi',             'rank':'A','expansion':'DT', 'zone':'Shaaloani',                    'min_respawn_h':4,'max_respawn_h':6,'rewards':'Nuts, Seals','notes':''},
    {'key':'a_heshuala',              'name':'Heshuala',                   'rank':'A','expansion':'DT', 'zone':'Heritage Found',               'min_respawn_h':4,'max_respawn_h':6,'rewards':'Nuts, Seals','notes':''},
    {'key':'a_starcrier',             'name':'Starcrier',                  'rank':'A','expansion':'DT', 'zone':'Living Memory',                'min_respawn_h':4,'max_respawn_h':6,'rewards':'Nuts, Seals','notes':''},
    # ── Dawntrail SS-Rank (conditional spawn after any DT S-rank) ───────────
    {'key':'ss_dt_arch_aethereater',  'name':'Arch Aethereater',           'rank':'SS','expansion':'DT', 'zone':'Any DT zone',                 'min_respawn_h':0,'max_respawn_h':0,'rewards':'400 Nuts, Tomestones, Novacluster/Prismaticluster','notes':'Kill any DT S-rank -> 4 Crystal Incarnation minions spawn -> kill all 4 within 5 min'},
    # ── Dawntrail B-Ranks (reference only - 5 min respawn, no ToD needed) ───
    {'key':'b_urani',                 'name':'Urani',                      'rank':'B','expansion':'DT', 'zone':'Urqopacha',                    'min_respawn_h':0,'max_respawn_h':0,'rewards':'Nuts','notes':'~5 min respawn - always up'},
    {'key':'b_garudaf',               'name':'Garudaf',                    'rank':'B','expansion':'DT', 'zone':"Kozama'uka",                   'min_respawn_h':0,'max_respawn_h':0,'rewards':'Nuts','notes':'~5 min respawn - always up'},
    {'key':'b_ihnuxokeh',             'name':'Ihnuxokeh',                  'rank':'B','expansion':'DT', 'zone':"Yak T'el",                     'min_respawn_h':0,'max_respawn_h':0,'rewards':'Nuts','notes':'~5 min respawn - always up'},
    {'key':'b_nechuciho',             'name':'Nechuciho',                  'rank':'B','expansion':'DT', 'zone':'Shaaloani',                    'min_respawn_h':0,'max_respawn_h':0,'rewards':'Nuts','notes':'~5 min respawn - always up'},
    {'key':'b_kirlirger',             'name':'Kirlirger the Abhorrent',    'rank':'B','expansion':'DT', 'zone':'Heritage Found',               'min_respawn_h':0,'max_respawn_h':0,'rewards':'Nuts','notes':'~5 min respawn - always up'},
    {'key':'b_arch_aethon',           'name':'Arch Aethon',                'rank':'B','expansion':'DT', 'zone':'Living Memory',                'min_respawn_h':0,'max_respawn_h':0,'rewards':'Nuts','notes':'~5 min respawn - always up'},

    # ── Endwalker (EW) S-Ranks ───────────────────────────────────────────────
    {'key':'s_burfurlur',             'name':'Burfurlur the Canny',        'rank':'S','expansion':'EW', 'zone':'Labyrinthos',                  'min_respawn_h':72,'max_respawn_h':120,'rewards':'Nuts, Seals, EW Hunt currency','notes':''},
    {'key':'s_narrow_nagxia',         'name':'Narrow-eared Nagxia',        'rank':'S','expansion':'EW', 'zone':'Thavnair',                     'min_respawn_h':72,'max_respawn_h':120,'rewards':'Nuts, Seals','notes':''},
    {'key':'s_humus',                 'name':'Humus',                      'rank':'S','expansion':'EW', 'zone':'Garlemald',                    'min_respawn_h':72,'max_respawn_h':120,'rewards':'Nuts, Seals','notes':''},
    {'key':'s_sugriva',               'name':'Sugriva',                    'rank':'S','expansion':'EW', 'zone':'Elpis',                        'min_respawn_h':72,'max_respawn_h':120,'rewards':'Nuts, Seals','notes':''},
    {'key':'s_keraunos',              'name':'Keraunos',                   'rank':'S','expansion':'EW', 'zone':'Ultima Thule',                 'min_respawn_h':72,'max_respawn_h':120,'rewards':'Nuts, Seals','notes':''},
    {'key':'s_sphatika',              'name':'Sphatika',                   'rank':'S','expansion':'EW', 'zone':'Mare Lamentorum',              'min_respawn_h':72,'max_respawn_h':120,'rewards':'Nuts, Seals','notes':''},
    # ── Endwalker A-Ranks ────────────────────────────────────────────────────
    {'key':'a_storsie',               'name':'Storsie',                    'rank':'A','expansion':'EW', 'zone':'Labyrinthos',                  'min_respawn_h':4,'max_respawn_h':6,'rewards':'Nuts, Seals','notes':''},
    {'key':'a_vulpangue',             'name':'Vulpangue',                  'rank':'A','expansion':'EW', 'zone':'Thavnair',                     'min_respawn_h':4,'max_respawn_h':6,'rewards':'Nuts, Seals','notes':''},
    {'key':'a_vochstein',             'name':'Vochstein',                  'rank':'A','expansion':'EW', 'zone':'Garlemald',                    'min_respawn_h':4,'max_respawn_h':6,'rewards':'Nuts, Seals','notes':''},
    {'key':'a_iravati',               'name':'Iravati',                    'rank':'A','expansion':'EW', 'zone':'Thavnair',                     'min_respawn_h':4,'max_respawn_h':6,'rewards':'Nuts, Seals','notes':''},
    {'key':'a_gurangatch',            'name':'Gurangatch',                 'rank':'A','expansion':'EW', 'zone':'Elpis',                        'min_respawn_h':4,'max_respawn_h':6,'rewards':'Nuts, Seals','notes':''},
    {'key':'a_minerva',               'name':'Minerva',                    'rank':'A','expansion':'EW', 'zone':'Ultima Thule',                 'min_respawn_h':4,'max_respawn_h':6,'rewards':'Nuts, Seals','notes':''},
    {'key':'a_lunatender',            'name':'Lunatender Queen',           'rank':'A','expansion':'EW', 'zone':'Mare Lamentorum',              'min_respawn_h':4,'max_respawn_h':6,'rewards':'Nuts, Seals','notes':''},
    # ── Endwalker SS-Rank (conditional spawn after any EW S-rank) ───────────
    {'key':'ss_ew_ker',               'name':'Ker',                        'rank':'SS','expansion':'EW', 'zone':'Any EW zone',                 'min_respawn_h':0,'max_respawn_h':0,'rewards':'400 Nuts, Tomestones, Anthocluster/Dendrocluster','notes':'Kill any EW S-rank -> 4 Ker Shroud minions spawn -> kill all 4 within 5 min'},
    # ── Endwalker B-Ranks ────────────────────────────────────────────────────
    {'key':'b_ew_labyrinthos',        'name':'Ogre Pumpkinhead',           'rank':'B','expansion':'EW', 'zone':'Labyrinthos',                  'min_respawn_h':0,'max_respawn_h':0,'rewards':'Nuts','notes':'~5 min respawn - always up'},
    {'key':'b_ew_thavnair',           'name':'Pisaca',                     'rank':'B','expansion':'EW', 'zone':'Thavnair',                     'min_respawn_h':0,'max_respawn_h':0,'rewards':'Nuts','notes':'~5 min respawn - always up'},
    {'key':'b_ew_garlemald',          'name':'Lympan',                     'rank':'B','expansion':'EW', 'zone':'Garlemald',                    'min_respawn_h':0,'max_respawn_h':0,'rewards':'Nuts','notes':'~5 min respawn - always up'},
    {'key':'b_ew_elpis',              'name':'Petalodus',                  'rank':'B','expansion':'EW', 'zone':'Elpis',                        'min_respawn_h':0,'max_respawn_h':0,'rewards':'Nuts','notes':'~5 min respawn - always up'},
    {'key':'b_ew_ultima',             'name':'Aegeiros',                   'rank':'B','expansion':'EW', 'zone':'Ultima Thule',                 'min_respawn_h':0,'max_respawn_h':0,'rewards':'Nuts','notes':'~5 min respawn - always up'},
    {'key':'b_ew_mare',               'name':'Warped Flesh',               'rank':'B','expansion':'EW', 'zone':'Mare Lamentorum',              'min_respawn_h':0,'max_respawn_h':0,'rewards':'Nuts','notes':'~5 min respawn - always up'},

    # ── Shadowbringers (ShB) S-Ranks ─────────────────────────────────────────
    {'key':'s_forgiven_rebellion',    'name':'Forgiven Rebellion',         'rank':'S','expansion':'ShB','zone':'Lakeland',                     'min_respawn_h':72,'max_respawn_h':120,'rewards':'Nuts, ShB Seals','notes':''},
    {'key':'s_forgiven_obscenity',    'name':'Forgiven Obscenity',         'rank':'S','expansion':'ShB','zone':'Il Mheg',                      'min_respawn_h':72,'max_respawn_h':120,'rewards':'Nuts, ShB Seals','notes':''},
    {'key':'s_forgiven_shame',        'name':'Forgiven Shame',             'rank':'S','expansion':'ShB','zone':"The Rak'tika Greatwood",        'min_respawn_h':72,'max_respawn_h':120,'rewards':'Nuts, ShB Seals','notes':''},
    {'key':'s_forgiven_melancholy',   'name':'Forgiven Melancholy',        'rank':'S','expansion':'ShB','zone':'Amh Araeng',                   'min_respawn_h':72,'max_respawn_h':120,'rewards':'Nuts, ShB Seals','notes':''},
    {'key':'s_la_velue',              'name':'La Velue',                   'rank':'S','expansion':'ShB','zone':'Kholusia',                     'min_respawn_h':72,'max_respawn_h':120,'rewards':'Nuts, ShB Seals','notes':''},
    {'key':'s_tarchia',               'name':'Tarchia',                    'rank':'S','expansion':'ShB','zone':'The Tempest',                  'min_respawn_h':72,'max_respawn_h':120,'rewards':'Nuts, ShB Seals','notes':''},
    # ── Shadowbringers SS-Rank (conditional spawn after any ShB S-rank) ──────
    {'key':'ss_shb_forgiven_rebellion','name':'Forgiven Rebellion (SS)',   'rank':'SS','expansion':'ShB','zone':'Any ShB zone',                'min_respawn_h':0,'max_respawn_h':0,'rewards':'400 Nuts, Tomestones, Planicluster/Stellacluster','notes':'Kill any ShB S-rank -> 4 Forgiven Gossip minions spawn -> kill all 4 within 5 min'},
    # ── Shadowbringers A-Ranks ────────────────────────────────────────────────
    {'key':'a_aqrabuamelu',           'name':'Aqrabuamelu',                'rank':'A','expansion':'ShB','zone':'Lakeland',                     'min_respawn_h':4,'max_respawn_h':6,'rewards':'Nuts, Seals','notes':''},
    {'key':'a_o_parts',               'name':'O Parts',                    'rank':'A','expansion':'ShB','zone':'Il Mheg',                      'min_respawn_h':4,'max_respawn_h':6,'rewards':'Nuts, Seals','notes':''},
    {'key':'a_grassman',              'name':'Grassman',                   'rank':'A','expansion':'ShB','zone':"The Rak'tika Greatwood",        'min_respawn_h':4,'max_respawn_h':6,'rewards':'Nuts, Seals','notes':''},
    {'key':'a_maliktender',           'name':'Maliktender',                'rank':'A','expansion':'ShB','zone':'Amh Araeng',                   'min_respawn_h':4,'max_respawn_h':6,'rewards':'Nuts, Seals','notes':''},
    {'key':'a_quaqua',                'name':'Quaqua',                     'rank':'A','expansion':'ShB','zone':'Kholusia',                     'min_respawn_h':4,'max_respawn_h':6,'rewards':'Nuts, Seals','notes':''},
    {'key':'a_baal',                  'name':'Baal',                       'rank':'A','expansion':'ShB','zone':'The Tempest',                  'min_respawn_h':4,'max_respawn_h':6,'rewards':'Nuts, Seals','notes':''},
    # ── Shadowbringers B-Ranks ────────────────────────────────────────────────
    {'key':'b_shb_lakeland',          'name':'Worm of the Well',           'rank':'B','expansion':'ShB','zone':'Lakeland',                     'min_respawn_h':0,'max_respawn_h':0,'rewards':'Nuts','notes':'~5 min respawn - always up'},
    {'key':'b_shb_ilmheg',            'name':'Wailing Wamura',             'rank':'B','expansion':'ShB','zone':'Il Mheg',                      'min_respawn_h':0,'max_respawn_h':0,'rewards':'Nuts','notes':'~5 min respawn - always up'},
    {'key':'b_shb_raktika',           'name':'Domovoi',                    'rank':'B','expansion':'ShB','zone':"The Rak'tika Greatwood",        'min_respawn_h':0,'max_respawn_h':0,'rewards':'Nuts','notes':'~5 min respawn - always up'},
    {'key':'b_shb_amh',               'name':'Juggler Hecatomb',           'rank':'B','expansion':'ShB','zone':'Amh Araeng',                   'min_respawn_h':0,'max_respawn_h':0,'rewards':'Nuts','notes':'~5 min respawn - always up'},
    {'key':'b_shb_kholusia',          'name':'Coquecigrue',                'rank':'B','expansion':'ShB','zone':'Kholusia',                     'min_respawn_h':0,'max_respawn_h':0,'rewards':'Nuts','notes':'~5 min respawn - always up'},
    {'key':'b_shb_tempest',           'name':'Deacon',                     'rank':'B','expansion':'ShB','zone':'The Tempest',                  'min_respawn_h':0,'max_respawn_h':0,'rewards':'Nuts','notes':'~5 min respawn - always up'},

    # ── Stormblood (SB) S-Ranks ──────────────────────────────────────────────
    {'key':'s_okina',                 'name':'Okina',                      'rank':'S','expansion':'SB', 'zone':'The Fringes',                  'min_respawn_h':72,'max_respawn_h':120,'rewards':'Centurio Seals, SB tokens','notes':''},
    {'key':'s_ose',                   'name':'Ose',                        'rank':'S','expansion':'SB', 'zone':'The Peaks',                    'min_respawn_h':72,'max_respawn_h':120,'rewards':'Centurio Seals, SB tokens','notes':''},
    {'key':'s_luminare',              'name':'Luminare',                   'rank':'S','expansion':'SB', 'zone':'The Lochs',                    'min_respawn_h':72,'max_respawn_h':120,'rewards':'Centurio Seals, SB tokens','notes':''},
    {'key':'s_brontes',               'name':'Brontes',                    'rank':'S','expansion':'SB', 'zone':'The Ruby Sea',                 'min_respawn_h':72,'max_respawn_h':120,'rewards':'Centurio Seals, SB tokens','notes':''},
    {'key':'s_gauki',                 'name':'Gauki Strongblade',          'rank':'S','expansion':'SB', 'zone':'Yanxia',                       'min_respawn_h':72,'max_respawn_h':120,'rewards':'Centurio Seals, SB tokens','notes':''},
    {'key':'s_bone_crawler',          'name':'Bone Crawler',               'rank':'S','expansion':'SB', 'zone':'The Azim Steppe',              'min_respawn_h':72,'max_respawn_h':120,'rewards':'Centurio Seals, SB tokens','notes':''},
    # ── Stormblood A-Ranks ────────────────────────────────────────────────────
    {'key':'a_erle',                  'name':'Erle',                       'rank':'A','expansion':'SB', 'zone':'The Fringes',                  'min_respawn_h':4,'max_respawn_h':6,'rewards':'Seals','notes':''},
    {'key':'a_orcus',                 'name':'Orcus',                      'rank':'A','expansion':'SB', 'zone':'The Peaks',                    'min_respawn_h':4,'max_respawn_h':6,'rewards':'Seals','notes':''},
    {'key':'a_dashu',                 'name':'Dashu',                      'rank':'A','expansion':'SB', 'zone':'The Lochs',                    'min_respawn_h':4,'max_respawn_h':6,'rewards':'Seals','notes':''},
    {'key':'a_angada',                'name':'Angada',                     'rank':'A','expansion':'SB', 'zone':'The Ruby Sea',                 'min_respawn_h':4,'max_respawn_h':6,'rewards':'Seals','notes':''},
    {'key':'a_gajasura',              'name':'Gajasura',                   'rank':'A','expansion':'SB', 'zone':'Yanxia',                       'min_respawn_h':4,'max_respawn_h':6,'rewards':'Seals','notes':''},
    {'key':'a_gyorai',                'name':'Gyorai Quickstrike',         'rank':'A','expansion':'SB', 'zone':'The Azim Steppe',              'min_respawn_h':4,'max_respawn_h':6,'rewards':'Seals','notes':''},
    # ── Stormblood B-Ranks ────────────────────────────────────────────────────
    {'key':'b_sb_fringes',            'name':'Shadow-Eyed Mugin',          'rank':'B','expansion':'SB', 'zone':'The Fringes',                  'min_respawn_h':0,'max_respawn_h':0,'rewards':'Seals','notes':'~5 min respawn - always up'},
    {'key':'b_sb_peaks',              'name':'Gwas-y-neidr',               'rank':'B','expansion':'SB', 'zone':'The Peaks',                    'min_respawn_h':0,'max_respawn_h':0,'rewards':'Seals','notes':'~5 min respawn - always up'},
    {'key':'b_sb_lochs',              'name':'Manes',                      'rank':'B','expansion':'SB', 'zone':'The Lochs',                    'min_respawn_h':0,'max_respawn_h':0,'rewards':'Seals','notes':'~5 min respawn - always up'},
    {'key':'b_sb_rubysea',            'name':'Oni Yumemi',                 'rank':'B','expansion':'SB', 'zone':'The Ruby Sea',                 'min_respawn_h':0,'max_respawn_h':0,'rewards':'Seals','notes':'~5 min respawn - always up'},
    {'key':'b_sb_yanxia',             'name':'Gwas-y-neidr',               'rank':'B','expansion':'SB', 'zone':'Yanxia',                       'min_respawn_h':0,'max_respawn_h':0,'rewards':'Seals','notes':'~5 min respawn - always up'},
    {'key':'b_sb_azim',               'name':'Aswang',                     'rank':'B','expansion':'SB', 'zone':'The Azim Steppe',              'min_respawn_h':0,'max_respawn_h':0,'rewards':'Seals','notes':'~5 min respawn - always up'},

    # ── Heavensward (HW) S-Ranks ─────────────────────────────────────────────
    {'key':'s_leucrotta',             'name':'Leucrotta',                  'rank':'S','expansion':'HW', 'zone':'The Dravanian Forelands',      'min_respawn_h':72,'max_respawn_h':120,'rewards':'Centurio Seals, HW tokens','notes':''},
    {'key':'s_gandarewa',             'name':'Gandarewa',                  'rank':'S','expansion':'HW', 'zone':'The Churning Mists',           'min_respawn_h':72,'max_respawn_h':120,'rewards':'Centurio Seals','notes':''},
    {'key':'s_senmurv',               'name':'Senmurv',                    'rank':'S','expansion':'HW', 'zone':'The Sea of Clouds',            'min_respawn_h':72,'max_respawn_h':120,'rewards':'Centurio Seals','notes':''},
    {'key':'s_bune',                  'name':'Bune',                       'rank':'S','expansion':'HW', 'zone':'The Dravanian Hinterlands',    'min_respawn_h':72,'max_respawn_h':120,'rewards':'Centurio Seals','notes':''},
    {'key':'s_kaiser',                'name':'Kaiser Behemoth',            'rank':'S','expansion':'HW', 'zone':'Coerthas Western Highlands',   'min_respawn_h':72,'max_respawn_h':120,'rewards':'Centurio Seals','notes':''},
    {'key':'s_roc',                   'name':'Roc',                        'rank':'S','expansion':'HW', 'zone':"The Thaliak River",            'min_respawn_h':72,'max_respawn_h':120,'rewards':'Centurio Seals','notes':'Abalathia\'s Spine'},
    # ── Heavensward A-Ranks ────────────────────────────────────────────────────
    {'key':'a_pylraster',             'name':'Pylraster',                  'rank':'A','expansion':'HW', 'zone':'The Dravanian Forelands',      'min_respawn_h':4,'max_respawn_h':6,'rewards':'Seals','notes':''},
    {'key':'a_lord_of_the_wyverns',   'name':'Lord of the Wyverns',        'rank':'A','expansion':'HW', 'zone':'The Churning Mists',           'min_respawn_h':4,'max_respawn_h':6,'rewards':'Seals','notes':''},
    {'key':'a_3_tonze_beast',         'name':'3-Tonze Beast',              'rank':'A','expansion':'HW', 'zone':'The Sea of Clouds',            'min_respawn_h':4,'max_respawn_h':6,'rewards':'Seals','notes':''},
    {'key':'a_lycidas',               'name':'Lycidas',                    'rank':'A','expansion':'HW', 'zone':'The Dravanian Hinterlands',    'min_respawn_h':4,'max_respawn_h':6,'rewards':'Seals','notes':''},
    {'key':'a_mirka',                 'name':'Mirka',                      'rank':'A','expansion':'HW', 'zone':'Coerthas Western Highlands',   'min_respawn_h':4,'max_respawn_h':6,'rewards':'Seals','notes':''},
    {'key':'a_squonk',                'name':'Squonk',                     'rank':'A','expansion':'HW', 'zone':'The Diadem',                   'min_respawn_h':4,'max_respawn_h':6,'rewards':'Seals','notes':'Abalathia\'s Spine'},
    # ── Heavensward B-Ranks ────────────────────────────────────────────────────
    {'key':'b_hw_forelands',          'name':'Pterygotus',                 'rank':'B','expansion':'HW', 'zone':'The Dravanian Forelands',      'min_respawn_h':0,'max_respawn_h':0,'rewards':'Seals','notes':'~5 min respawn - always up'},
    {'key':'b_hw_mists',              'name':'Frostmane',                  'rank':'B','expansion':'HW', 'zone':'The Churning Mists',           'min_respawn_h':0,'max_respawn_h':0,'rewards':'Seals','notes':'~5 min respawn - always up'},
    {'key':'b_hw_clouds',             'name':'Gnath Cometdrone',           'rank':'B','expansion':'HW', 'zone':'The Sea of Clouds',            'min_respawn_h':0,'max_respawn_h':0,'rewards':'Seals','notes':'~5 min respawn - always up'},
    {'key':'b_hw_hinterlands',        'name':'Slipkinx Steeljoints',       'rank':'B','expansion':'HW', 'zone':'The Dravanian Hinterlands',    'min_respawn_h':0,'max_respawn_h':0,'rewards':'Seals','notes':'~5 min respawn - always up'},
    {'key':'b_hw_coerthas',           'name':'Alteci',                     'rank':'B','expansion':'HW', 'zone':'Coerthas Western Highlands',   'min_respawn_h':0,'max_respawn_h':0,'rewards':'Seals','notes':'~5 min respawn - always up'},
    {'key':'b_hw_abalathia',          'name':'Kreutzet',                   'rank':'B','expansion':'HW', 'zone':"The Thaliak River",            'min_respawn_h':0,'max_respawn_h':0,'rewards':'Seals','notes':'~5 min respawn - always up'},

    # ── A Realm Reborn (ARR) S-Ranks ─────────────────────────────────────────
    {'key':'s_croque_mitaine',        'name':'Croque-Mitaine',             'rank':'S','expansion':'ARR','zone':'Central Shroud',               'min_respawn_h':72,'max_respawn_h':120,'rewards':'Centurio Seals','notes':''},
    {'key':'s_bonnacon',              'name':'Bonnacon',                   'rank':'S','expansion':'ARR','zone':'Central Thanalan',             'min_respawn_h':72,'max_respawn_h':120,'rewards':'Centurio Seals','notes':''},
    {'key':'s_laideronnette',         'name':'Laideronnette',              'rank':'S','expansion':'ARR','zone':'South Shroud',                 'min_respawn_h':72,'max_respawn_h':120,'rewards':'Centurio Seals','notes':''},
    {'key':'s_nandi',                 'name':'Nandi',                      'rank':'S','expansion':'ARR','zone':'Southern Thanalan',            'min_respawn_h':72,'max_respawn_h':120,'rewards':'Centurio Seals','notes':''},
    {'key':'s_minhocao',              'name':'Minhocao',                   'rank':'S','expansion':'ARR','zone':'Central La Noscea',            'min_respawn_h':72,'max_respawn_h':120,'rewards':'Centurio Seals','notes':''},
    {'key':'s_safat',                 'name':'Safat',                      'rank':'S','expansion':'ARR','zone':'Eastern La Noscea',            'min_respawn_h':72,'max_respawn_h':120,'rewards':'Centurio Seals','notes':''},
    # ── A Realm Reborn A-Ranks ────────────────────────────────────────────────
    {'key':'a_vogaal_ja',             'name':'Vogaal Ja',                  'rank':'A','expansion':'ARR','zone':'Central Shroud',               'min_respawn_h':4,'max_respawn_h':6,'rewards':'Seals','notes':''},
    {'key':'a_unktehi',               'name':'Unktehi',                    'rank':'A','expansion':'ARR','zone':'Central Thanalan',             'min_respawn_h':4,'max_respawn_h':6,'rewards':'Seals','notes':''},
    {'key':'a_thousand_cast_theda',   'name':'Thousand-Cast Theda',        'rank':'A','expansion':'ARR','zone':'South Shroud',                 'min_respawn_h':4,'max_respawn_h':6,'rewards':'Seals','notes':''},
    {'key':'a_zanig',                 'name':'Zanig\'ohl',                 'rank':'A','expansion':'ARR','zone':'Southern Thanalan',            'min_respawn_h':4,'max_respawn_h':6,'rewards':'Seals','notes':''},
    {'key':'a_garlok',                'name':'Garlok',                     'rank':'A','expansion':'ARR','zone':'Central La Noscea',            'min_respawn_h':4,'max_respawn_h':6,'rewards':'Seals','notes':''},
    {'key':'a_sabotender_bailarina',  'name':'Sabotender Bailarina',       'rank':'A','expansion':'ARR','zone':'Eastern La Noscea',            'min_respawn_h':4,'max_respawn_h':6,'rewards':'Seals','notes':''},
    {'key':'a_cornu',                 'name':'Cornu',                      'rank':'A','expansion':'ARR','zone':'North Shroud',                 'min_respawn_h':4,'max_respawn_h':6,'rewards':'Seals','notes':''},
    {'key':'a_albin_the_ashen',       'name':'Albin the Ashen',            'rank':'A','expansion':'ARR','zone':'Eastern Thanalan',             'min_respawn_h':4,'max_respawn_h':6,'rewards':'Seals','notes':''},
    {'key':'a_hellsclaw',             'name':'Hellsclaw',                  'rank':'A','expansion':'ARR','zone':'Middle La Noscea',             'min_respawn_h':4,'max_respawn_h':6,'rewards':'Seals','notes':''},
    {'key':'a_flame_sergeant_dalvag', 'name':'Flame Sergeant Dalvag',      'rank':'A','expansion':'ARR','zone':'Western Thanalan',             'min_respawn_h':4,'max_respawn_h':6,'rewards':'Seals','notes':''},
    {'key':'a_leech_king',            'name':'Leech King',                 'rank':'A','expansion':'ARR','zone':'Western La Noscea',            'min_respawn_h':4,'max_respawn_h':6,'rewards':'Seals','notes':''},
    {'key':'a_maahes',                'name':'Maahes',                     'rank':'A','expansion':'ARR','zone':'Upper La Noscea',              'min_respawn_h':4,'max_respawn_h':6,'rewards':'Seals','notes':''},
    {'key':'a_naul',                  'name':'Naul',                       'rank':'A','expansion':'ARR','zone':'Outer La Noscea',              'min_respawn_h':4,'max_respawn_h':6,'rewards':'Seals','notes':''},
    {'key':'a_forneus',               'name':'Forneus',                    'rank':'A','expansion':'ARR','zone':'Mor Dhona',                    'min_respawn_h':4,'max_respawn_h':6,'rewards':'Seals','notes':''},
    {'key':'a_ghede_ti_malice',       'name':'Ghede Ti Malice',            'rank':'A','expansion':'ARR','zone':'East Shroud',                  'min_respawn_h':4,'max_respawn_h':6,'rewards':'Seals','notes':''},
    {'key':'a_marraco',               'name':'Marraco',                    'rank':'A','expansion':'ARR','zone':'West Shroud',                  'min_respawn_h':4,'max_respawn_h':6,'rewards':'Seals','notes':''},
    {'key':'a_phecda',                'name':'Phecda',                     'rank':'A','expansion':'ARR','zone':'Coerthas Central Highlands',   'min_respawn_h':4,'max_respawn_h':6,'rewards':'Seals','notes':''},
    {'key':'a_sharp_horned_behemoth', 'name':'Sharp-horned Behemoth',      'rank':'A','expansion':'ARR','zone':'Northern Thanalan',            'min_respawn_h':4,'max_respawn_h':6,'rewards':'Seals','notes':''},
    # ── A Realm Reborn B-Ranks ────────────────────────────────────────────────
    {'key':'b_arr_cshroud',           'name':'Stinging Sophie',            'rank':'B','expansion':'ARR','zone':'Central Shroud',               'min_respawn_h':0,'max_respawn_h':0,'rewards':'Seals','notes':'~5 min respawn - always up'},
    {'key':'b_arr_cthan',             'name':'Alligator',                  'rank':'B','expansion':'ARR','zone':'Central Thanalan',             'min_respawn_h':0,'max_respawn_h':0,'rewards':'Seals','notes':'~5 min respawn - always up'},
    {'key':'b_arr_sshroud',           'name':'Skogs Fru',                  'rank':'B','expansion':'ARR','zone':'South Shroud',                 'min_respawn_h':0,'max_respawn_h':0,'rewards':'Seals','notes':'~5 min respawn - always up'},
    {'key':'b_arr_sthan',             'name':'Sewer Syrup',                'rank':'B','expansion':'ARR','zone':'Southern Thanalan',            'min_respawn_h':0,'max_respawn_h':0,'rewards':'Seals','notes':'~5 min respawn - always up'},
    {'key':'b_arr_clanos',            'name':'Bloody Mary',                'rank':'B','expansion':'ARR','zone':'Central La Noscea',            'min_respawn_h':0,'max_respawn_h':0,'rewards':'Seals','notes':'~5 min respawn - always up'},
    {'key':'b_arr_elanos',            'name':'Dark Helmet',                'rank':'B','expansion':'ARR','zone':'Eastern La Noscea',            'min_respawn_h':0,'max_respawn_h':0,'rewards':'Seals','notes':'~5 min respawn - always up'},
]

# Notable world events worth community tracking
NOTABLE_EVENTS = [
    # ── ARR Notorious Monsters (world bosses) ────────────────────────────────
    {'key':'nm_odin',             'name':'Odin',                          'type':'NM',        'zone':'East / Central Shroud',       'expansion':'ARR',
     'respawn_note':'72h+ after defeat','rewards':'Odin gear, Allagan Tomestones, Dreaming Sheep mount',
     'desc':'The iconic primal world boss. Appears in Central/East Shroud. Deals lethal AoE to all players on the map. Notorious for one-shotting unprepared players.',
     'color':'purple'},
    {'key':'nm_behemoth',         'name':'Behemoth',                      'type':'NM',        'zone':'Coerthas Central Highlands',  'expansion':'ARR',
     'respawn_note':'Timed FATE - ~20 min window','rewards':'Behemoth Horn, Behemoth Heir mount (rare)',
     'desc':'Classic ARR world boss in Coerthas. Multi-phase FATE: defeat Meteor before the enrage. One of the most iconic ARR community events.',
     'color':'red'},
    {'key':'nm_wrath_whorl',      'name':'Wrath of the Whorl',            'type':'NM',        'zone':'Western La Noscea',           'expansion':'ARR',
     'respawn_note':'Timed FATE - repeating','rewards':'Rare crafting materials, Allagan gear',
     'desc':'Massive leviathan FATE in Western La Noscea. Part of the original ARR mega-boss chain.',
     'color':'blue'},
    {'key':'nm_moggle_mog',       'name':'He Comes to Town',              'type':'NM',        'zone':'Central Shroud',              'expansion':'ARR',
     'respawn_note':'Timed FATE - repeating','rewards':'Mog Totem, cosmetics',
     'desc':'King Moggle Mog XII appears in Central Shroud. Popular community FATE for mog-themed cosmetic drops.',
     'color':'pink'},
    {'key':'nm_pazuzu',           'name':'Pazuzu',                        'type':'NM',        'zone':'North Shroud',                'expansion':'ARR',
     'respawn_note':'Timed FATE - repeating','rewards':'Demon Wing mount (rare)',
     'desc':'Rare spawn FATE in North Shroud. The Demon Wing mount is a coveted low-drop-rate reward that drives FATE trains here.',
     'color':'orange'},

    # ── Dawntrail Notable Events ──────────────────────────────────────────────
    {'key':'dt_ttokrrone_fate',    'name':'The Serpentlord Seethes',       'type':'World Boss',  'zone':'Shaaloani',                  'expansion':'DT',
     'respawn_note':'24h+ after chain completes','rewards':'Ttokrrone Scales x12 = Mehwapyarra mount',
     'desc':'5-part FATE chain in Shaaloani. Complete 4 Sandnest Deathmatch FATEs to spawn Ttokrrone. Scales drop from the boss - 12 scales total buys the exclusive Mehwapyarra Whistle mount from Solution Nine.',
     'color':'violet'},
    {'key':'dt_mica_fate',         'name':'Mascot Murder - Mica the Magical Mu','type':'World Boss','zone':'Living Memory',           'expansion':'DT',
     'respawn_note':'36-72h window after maintenance','rewards':'Exclusive achievement, Bicolor Gemstones',
     'desc':'3-part chain FATE in Living Memory. Mica the Magical Mu is a community-favourite boss with limited spawn windows. Comes with a unique achievement.',
     'color':'pink'},
    {'key':'dt_occult_crescent',   'name':'Occult Crescent',               'type':'Field Op',   'zone':'Occult Crescent (72-player)','expansion':'DT',
     'respawn_note':'Always available - Critical Encounters on rotation','rewards':'Phantom Weapons (relic), exclusive mounts, hairstyles, Forked Tower access',
     'desc':'72-player field operation zone. Features Phantom Jobs, Knowledge Level progression, and Critical Encounters. The Forked Tower 48-player raid unlocks here. Best source of DT relic weapons and exclusive cosmetics.',
     'color':'indigo'},
    # ── Eureka Notorious Monsters ─────────────────────────────────────────────
    {'key':'enm_cassie',          'name':'Cassie',                        'type':'Eureka NM', 'zone':'Eureka Anemos',               'expansion':'SB',
     'respawn_note':'~2h after defeat','rewards':'Anemos Crystals, Protean Crystals',
     'desc':'One of the first major Eureka NMs. Required for the Anemos relic weapon grind. Still very active.',
     'color':'cyan'},
    {'key':'enm_king_hazmat',     'name':'King Hazmat',                   'type':'Eureka NM', 'zone':'Eureka Anemos',               'expansion':'SB',
     'respawn_note':'~2h after defeat','rewards':'Anemos Crystals',
     'desc':'Anemos NM spawning in the eastern areas. Part of the full Anemos NM circuit.',
     'color':'cyan'},
    {'key':'enm_serket',          'name':'Serket',                        'type':'Eureka NM', 'zone':'Eureka Anemos',               'expansion':'SB',
     'respawn_note':'~2h after defeat','rewards':'Anemos Crystals, Anemos gear',
     'desc':'Scorpion-type NM in Anemos. Part of the main NM circuit for relic upgrades.',
     'color':'cyan'},
    {'key':'enm_emperor_anemos',  'name':'Emperor of Anemos',             'type':'Eureka NM', 'zone':'Eureka Anemos',               'expansion':'SB',
     'respawn_note':'~2h after defeat','rewards':'Anemos Crystals, Anemos accessories',
     'desc':'Boss-tier Anemos NM. One of the most fought in the original Eureka grind circuit.',
     'color':'cyan'},
    {'key':'enm_louhi',           'name':'Louhi',                         'type':'Eureka NM', 'zone':'Eureka Pagos',                'expansion':'SB',
     'respawn_note':'~2h after defeat','rewards':'Pagos Crystals, Frosted Protean Crystals',
     'desc':'Major Pagos NM for the relic weapon grind. Requires coordinated party to spawn via FATE chain.',
     'color':'sky'},
    {'key':'enm_pagos_chimera',   'name':'Pagos Chimera',                 'type':'Eureka NM', 'zone':'Eureka Pagos',                'expansion':'SB',
     'respawn_note':'~2h after defeat','rewards':'Pagos Crystals',
     'desc':'Early Pagos NM. Requires frost-leveled party members. Classic community challenge.',
     'color':'sky'},
    {'key':'enm_ovni',            'name':'Ovni',                          'type':'Eureka NM', 'zone':'Eureka Pyros',                'expansion':'SB',
     'respawn_note':'~2h after defeat','rewards':'Pyros Crystals, Penthesilea\'s Flame',
     'desc':'Key Pyros NM. Drops materials for the Pyros relic weapon upgrade. Popular community farm.',
     'color':'orange'},
    {'key':'enm_ceto',            'name':'Ceto',                          'type':'Eureka NM', 'zone':'Eureka Hydatos',              'expansion':'SB',
     'respawn_note':'~2h after defeat','rewards':'Hydatos Crystals, Crystalline Scale',
     'desc':'Final tier Eureka NM. Key for Eureka Hydatos weapon completion. Still active due to Physeos weapon path.',
     'color':'teal'},

    # ── Bozja Critical Engagements ────────────────────────────────────────────
    {'key':'ce_beast_court',      'name':'Crimson Beast Court',           'type':'Bozja CE',  'zone':'Bozjan Southern Front',       'expansion':'ShB',
     'respawn_note':'Every ~30 min','rewards':'Bozjan Clusters, Lost Actions, CE coffers',
     'desc':'Popular cluster farm CE in the Southern Front. Great for Lost Action farming.',
     'color':'yellow'},
    {'key':'ce_dr_k',             'name':'Duel: Threefold Ward Plus',     'type':'Bozja CE',  'zone':'Zadnor',                     'expansion':'ShB',
     'respawn_note':'Every ~30 min','rewards':'Bozjan Clusters, CE coffers',
     'desc':'High-value critical engagement in Zadnor. Best cluster income for the effort.',
     'color':'yellow'},
    {'key':'ce_the_shadow',       'name':'The Shadow of Death\'s Door',   'type':'Bozja CE',  'zone':'Bozjan Southern Front',       'expansion':'ShB',
     'respawn_note':'Every ~30 min','rewards':'Bozjan Clusters, Lost Actions',
     'desc':'Recurring CE in the Southern Front. Solid alt-route for cluster farming.',
     'color':'yellow'},
    {'key':'ce_sartauvoir',       'name':'On Serpent\'s Wings',           'type':'Bozja CE',  'zone':'Zadnor',                     'expansion':'ShB',
     'respawn_note':'Every ~30 min','rewards':'Bozjan Clusters, Sartauvoir mount (rare)',
     'desc':'Sartauvoir the Inferno CE in Zadnor. Coveted Sartauvoir mount on very low drop rate.',
     'color':'red'},

    # ── Notable Field FATEs by Expansion ─────────────────────────────────────
    {'key':'fate_carteneau',      'name':'The Battle of Carteneau',       'type':'FATE',      'zone':'Mor Dhona',                  'expansion':'ARR',
     'respawn_note':'Repeating','rewards':'Allagan Tomestones, Alexandrite',
     'desc':'Repeating FATE in Mor Dhona. Good for older relic weapon Alexandrite farming and Atma grind.',
     'color':'gray'},
    {'key':'fate_noctilucale',    'name':'Noctilucale',                   'type':'FATE',      'zone':'Mor Dhona',                  'expansion':'ARR',
     'respawn_note':'Repeating','rewards':'Alexandrite, Allagan gear',
     'desc':'Mor Dhona FATE that drops Alexandrite needed for ARR relic weapon upgrades.',
     'color':'gray'},
    {'key':'fate_hw_nidhogg',     'name':'Greased Lightning',             'type':'FATE',      'zone':'The Dravanian Forelands',    'expansion':'HW',
     'respawn_note':'Timed FATE','rewards':'HW gear, Centurio Seals',
     'desc':'Multi-stage FATE in the Dravanian Forelands. Popular HW-era community event.',
     'color':'green'},
    {'key':'fate_sb_ixion',       'name':'A Horse Outside',               'type':'FATE',      'zone':'The Lochs',                  'expansion':'SB',
     'respawn_note':'~72h after despawn','rewards':'Horn of Ixion (summons Ixion mount)',
     'desc':'Ixion appears in The Lochs after a FATE chain. Drops the Horn of Ixion - one of the most sought-after mounts. Community watch needed.',
     'color':'purple'},
    {'key':'fate_shb_comet',      'name':'Comet\'s Course',               'type':'FATE',      'zone':'Amh Araeng',                 'expansion':'ShB',
     'respawn_note':'Repeating','rewards':'ShB gear, Nuts',
     'desc':'Chain FATE in Amh Araeng tied to the ShB hunt train. Drops useful ShB materials.',
     'color':'blue'},
    {'key':'fate_ew_storm',       'name':'Omicron Recall: Killing Order', 'type':'FATE',      'zone':'Ultima Thule',               'expansion':'EW',
     'respawn_note':'Repeating','rewards':'EW gear, Nuts',
     'desc':'High-value chain FATE in Ultima Thule. Often run in conjunction with the EW hunt train.',
     'color':'indigo'},

    # ── Diadem / Ishgard Restoration ─────────────────────────────────────────
    {'key':'diadem_nms',          'name':'Diadem Notorious Monsters',     'type':'Diadem NM', 'zone':'The Diadem',                 'expansion':'HW',
     'respawn_note':'~20 min rotations','rewards':'Skybuilders Scrips, rare gathering mats',
     'desc':'The 4 Diadem NMs (Strix, Archaeotania, Leucocrotta, Abominant) spawn on rotation. Great for Ishgard Restoration scrip farming.',
     'color':'indigo'},
]

HUNT_KEY_MAP = {h['key']: h for h in HUNT_MARKS}
EVENT_KEY_MAP = {e['key']: e for e in NOTABLE_EVENTS}


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

@add_web_user_context
def ffxiv_hunt_board(request):
    web_user = get_web_user(request)

    # Load all current ToD reports (one per world per hunt)
    with get_db_session() as db:
        reports = db.query(WebFfxivHuntReport).all()
        reporter_ids = [r.reported_by for r in reports if r.reported_by]
        reporters = {}
        if reporter_ids:
            users = db.query(WebUser.id, WebUser.display_name).filter(WebUser.id.in_(reporter_ids)).all()
            reporters = {u.id: u.display_name for u in users}

        now = int(time.time())
        tod_map = {}  # key: "{hunt_key}:{world}" -> report dict
        for r in reports:
            age_h = (now - r.reported_at) / 3600
            mark = HUNT_KEY_MAP.get(r.hunt_key) or EVENT_KEY_MAP.get(r.hunt_key)
            min_h = mark.get('min_respawn_h', 4) if mark else 4
            max_h = mark.get('max_respawn_h', 6) if mark else 6

            status = 'dead'
            if age_h >= max_h:
                status = 'window'   # definitely up
            elif age_h >= min_h:
                status = 'window'   # in window
            elif age_h >= min_h * 0.75:
                status = 'soon'     # approaching window

            tod_map[f"{r.hunt_key}:{r.world}"] = {
                'reported_at': r.reported_at,
                'event_type': r.event_type,
                'reporter': reporters.get(r.reported_by, 'Unknown'),
                'reporter_id': r.reported_by,
                'notes': r.notes or '',
                'age_h': round(age_h, 1),
                'status': status,
                'world': r.world,
                'dc': r.dc,
            }

    return render(request, 'questlog_web/ffxiv_hunt_board.html', {
        'active_page': 'ffxiv_hunt_board',
        'hunt_marks': HUNT_MARKS,
        'notable_events': NOTABLE_EVENTS,
        'tod_map': tod_map,
        'dc_worlds': DC_WORLDS,
        'data_centers': DATA_CENTERS,
        'is_logged_in': bool(web_user),
        'current_user_id': web_user.id if web_user else None,
        'is_admin': bool(web_user and web_user.is_admin),
        'web_user': web_user,
    })


@require_POST
@web_login_required
def api_ffxiv_hunt_report(request):
    import json
    web_user = get_web_user(request)
    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    hunt_key = body.get('hunt_key', '').strip()
    world    = body.get('world', '').strip()
    dc       = body.get('dc', '').strip()
    event_type = body.get('event_type', 'kill').strip()
    notes    = sanitize_text(body.get('notes', '').strip())[:200]

    if not hunt_key or not world or not dc:
        return JsonResponse({'error': 'hunt_key, world and dc required'}, status=400)
    if not re.match(r'^[a-z0-9_]{1,64}$', hunt_key):
        return JsonResponse({'error': 'Invalid hunt key'}, status=400)
    if hunt_key not in HUNT_KEY_MAP and hunt_key not in EVENT_KEY_MAP:
        return JsonResponse({'error': 'Unknown hunt'}, status=400)
    if event_type not in ('kill', 'sight', 'pull'):
        event_type = 'kill'

    # Validate world is real
    valid_worlds = [w for worlds in DC_WORLDS.values() for w in worlds]
    if world not in valid_worlds:
        return JsonResponse({'error': 'Invalid world'}, status=400)

    now = int(time.time())
    with get_db_session() as db:
        existing = db.query(WebFfxivHuntReport).filter_by(hunt_key=hunt_key, world=world).first()
        if existing:
            existing.reported_by  = web_user.id
            existing.dc           = dc
            existing.event_type   = event_type
            existing.reported_at  = now
            existing.notes        = notes or None
        else:
            db.add(WebFfxivHuntReport(
                hunt_key=hunt_key, reported_by=web_user.id,
                dc=dc, world=world, event_type=event_type,
                reported_at=now, notes=notes or None,
            ))
        db.commit()

    mark = HUNT_KEY_MAP.get(hunt_key) or EVENT_KEY_MAP.get(hunt_key, {})
    mark_name = mark.get('name', hunt_key)
    rank = mark.get('rank') or mark.get('type', '')

    # Fire notifications to subscribers
    _fire_hunt_notifications(hunt_key, rank, mark_name, world, dc, event_type, web_user.display_name, now, reporter_id=web_user.id)

    return JsonResponse({
        'ok': True,
        'hunt_key': hunt_key,
        'world': world,
        'reported_at': now,
        'reporter': web_user.display_name,
        'mark_name': mark_name,
    })


@require_POST
@web_login_required
def api_ffxiv_hunt_clear(request):
    """Clear a ToD report (mark as no longer tracked)."""
    import json
    web_user = get_web_user(request)
    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    hunt_key = body.get('hunt_key', '').strip()
    world    = body.get('world', '').strip()

    if not hunt_key or not world:
        return JsonResponse({'error': 'Missing fields'}, status=400)

    with get_db_session() as db:
        report = db.query(WebFfxivHuntReport).filter_by(hunt_key=hunt_key, world=world).first()
        if report:
            # Only reporter or admin can clear
            if report.reported_by != web_user.id and not web_user.is_admin:
                return JsonResponse({'error': 'Not authorized'}, status=403)
            db.delete(report)
            db.commit()

    return JsonResponse({'ok': True})


@require_POST
def api_ffxiv_hunt_clear_all(request):
    """Admin-only: clear all ToD reports for a hunt_key across all worlds."""
    import json
    web_user = get_web_user(request)
    if not web_user or not web_user.is_admin:
        return JsonResponse({'error': 'Admin only'}, status=403)
    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    hunt_key = body.get('hunt_key', '').strip()
    if not hunt_key:
        return JsonResponse({'error': 'hunt_key required'}, status=400)

    with get_db_session() as db:
        deleted = db.query(WebFfxivHuntReport).filter_by(hunt_key=hunt_key).delete()
        db.commit()

    return JsonResponse({'ok': True, 'deleted': deleted})


# ---------------------------------------------------------------------------
# Notification firing
# ---------------------------------------------------------------------------

def _fire_hunt_notifications(hunt_key, rank, mark_name, world, dc, event_type, reporter_name, now, reporter_id=None):
    """
    Find all subscribers matching this hunt/event report and:
    1. Create site WebNotification for notify_site=True subscribers
    2. Queue a Fluxer embed for the configured ffxiv_hunt channel
    """
    event_label = {'kill': 'killed', 'sight': 'spotted', 'pull': 'pulled'}.get(event_type, event_type)
    msg = f"{mark_name} {event_label} on {world} - reported by {reporter_name}"

    # Keys that match this report: the specific hunt_key, the rank tier (S/A/B),
    # 'all_events' if it's a FATE/NM, and 'all' as a catch-all
    is_event = hunt_key in EVENT_KEY_MAP
    match_keys = {hunt_key, rank, 'all'}
    if is_event:
        match_keys.add('all_events')

    try:
        with get_db_session() as db:
            subs = db.query(WebFfxivHuntSub).filter(
                WebFfxivHuntSub.watch_key.in_(match_keys)
            ).all()

            site_user_ids = []
            fluxer_needed = False

            for sub in subs:
                # Check world filter - empty means all worlds
                if sub.worlds:
                    allowed = [w.strip() for w in sub.worlds.split(',') if w.strip()]
                    if world not in allowed:
                        continue

                if sub.notify_site:
                    site_user_ids.append(sub.user_id)
                if sub.notify_fluxer:
                    fluxer_needed = True

            # Create site notifications (deduplicated by user)
            seen = set()
            actor = reporter_id or 1
            for uid in site_user_ids:
                if uid in seen:
                    continue
                seen.add(uid)
                db.add(WebNotification(
                    user_id=uid,
                    actor_id=actor,
                    notification_type='hunt_alert',
                    target_type='hunt',
                    message=msg,
                    created_at=now,
                    is_read=False,
                ))
            if seen:
                db.commit()

        # Queue Fluxer embed regardless of per-user fluxer prefs -
        # the channel ping goes to the configured role, not individuals
        _queue_hunt_fluxer_embed(mark_name, rank, world, dc, event_type, reporter_name, now)

    except Exception as e:
        logger.error('Hunt notification error: %s', e)


def _queue_hunt_fluxer_embed(mark_name, rank, world, dc, event_type, reporter_name, now):
    """Queue a Fluxer channel embed for the ffxiv_hunt event type."""
    try:
        from app.questlog_web.fluxer_webhooks import _queue_notification
        from sqlalchemy import text as sa_text

        event_label = {'kill': 'Killed', 'sight': 'Spotted', 'pull': 'Being Pulled'}.get(event_type, event_type.title())
        rank_colors = {'S': 0xF43F5E, 'A': 0xFB923C, 'B': 0x60A5FA}
        color = rank_colors.get(rank, 0x14B8A6)  # teal default for events

        rank_label = f"{rank} Rank" if rank in ('S', 'A', 'B') else (rank or 'Event')

        embed = {
            'title': f"{rank_label} Hunt Alert - {mark_name}",
            'url': 'https://questlog.casual-heroes.com/ffxiv/tools/hunt-board/',
            'description': f"**{mark_name}** has been **{event_label.lower()}** on **{world}** ({dc})",
            'color': color,
            'fields': [
                {'name': 'World', 'value': world, 'inline': True},
                {'name': 'Data Center', 'value': dc, 'inline': True},
                {'name': 'Status', 'value': event_label, 'inline': True},
                {'name': 'Reported By', 'value': reporter_name, 'inline': True},
            ],
            'footer': 'QuestLog Hunt Board',
            'timestamp': _iso_now(now),
        }

        _queue_hunt_with_mention(embed, color)

    except Exception as e:
        logger.error('Hunt Fluxer embed error: %s', e)


def _queue_hunt_with_mention(embed, color):
    """Queue the hunt embed to Fluxer and fire Discord webhook if configured."""
    try:
        from app.questlog_web.fluxer_webhooks import _hex_to_int
        from app.questlog_web.models import WebFluxerWebhookConfig
        from sqlalchemy import text as sa_text

        with get_db_session() as db:
            cfg = db.query(WebFluxerWebhookConfig).filter_by(
                event_type='ffxiv_hunt', is_enabled=True
            ).first()
            if not cfg:
                return

            embed['color'] = _hex_to_int(cfg.embed_color, color)

            # -- Fluxer channel --
            if cfg.channel_id:
                payload = dict(embed)
                if cfg.mention_role_id:
                    payload['content'] = f'<@&{cfg.mention_role_id}>'
                db.execute(sa_text("""
                    INSERT INTO fluxer_pending_broadcasts
                        (guild_id, channel_id, payload, created_at)
                    VALUES (:guild_id, :channel_id, :payload, :now)
                """), {
                    'guild_id':   int(cfg.guild_id) if cfg.guild_id else 0,
                    'channel_id': int(cfg.channel_id),
                    'payload':    json.dumps(payload),
                    'now':        int(time.time()),
                })
                db.commit()

            # -- Discord webhook --
            if cfg.discord_webhook_url:
                _fire_discord_webhook(cfg.discord_webhook_url, embed)

    except Exception as e:
        logger.error('Hunt Fluxer queue error: %s', e)


def _fire_discord_webhook(webhook_url, embed):
    """POST an embed dict to a Discord webhook URL (sync, fire-and-forget)."""
    import urllib.request as _req
    import urllib.error as _err
    try:
        data = json.dumps({'embeds': [embed]}).encode()
        req = _req.Request(
            webhook_url, data=data,
            headers={'Content-Type': 'application/json', 'User-Agent': 'QuestLog/1.0'},
        )
        with _req.urlopen(req, timeout=10):
            pass
    except Exception as e:
        logger.warning('Hunt Discord webhook failed: %s', e)


def _iso_now(ts):
    from datetime import datetime, timezone
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# API: manage hunt subscriptions
# ---------------------------------------------------------------------------

@require_GET
@web_login_required
def api_hunt_subs_list(request):
    """Return current user's hunt subscriptions."""
    web_user = get_web_user(request)
    with get_db_session() as db:
        subs = db.query(WebFfxivHuntSub).filter_by(user_id=web_user.id).all()
        return JsonResponse({'subs': [
            {
                'id':            s.id,
                'watch_key':     s.watch_key,
                'worlds':        s.worlds or '',
                'notify_site':   s.notify_site,
                'notify_fluxer': s.notify_fluxer,
            }
            for s in subs
        ]})


@require_POST
@web_login_required
def api_hunt_sub_save(request):
    """Create or update a hunt subscription."""
    web_user = get_web_user(request)
    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    watch_key     = body.get('watch_key', '').strip()[:128]
    worlds_raw    = body.get('worlds', '')
    notify_site   = bool(body.get('notify_site', True))
    notify_fluxer = bool(body.get('notify_fluxer', False))

    # Validate watch_key
    valid_tier_keys = {'S', 'A', 'B', 'all', 'all_events'}
    valid_hunt_keys = set(HUNT_KEY_MAP.keys()) | set(EVENT_KEY_MAP.keys())
    if watch_key not in valid_tier_keys and watch_key not in valid_hunt_keys:
        return JsonResponse({'error': 'Invalid watch_key'}, status=400)

    # Validate worlds
    valid_world_set = {w for worlds in DC_WORLDS.values() for w in worlds}
    if worlds_raw:
        worlds_list = [w.strip() for w in worlds_raw.split(',') if w.strip()]
        bad = [w for w in worlds_list if w not in valid_world_set]
        if bad:
            return JsonResponse({'error': 'One or more worlds are not recognized'}, status=400)
        worlds_clean = ','.join(worlds_list)
    else:
        worlds_clean = None

    if not notify_site and not notify_fluxer:
        return JsonResponse({'error': 'Enable at least one notification channel'}, status=400)

    now = int(time.time())
    with get_db_session() as db:
        # Max 50 subs per user
        existing = db.query(WebFfxivHuntSub).filter_by(user_id=web_user.id, watch_key=watch_key).first()
        if existing:
            existing.worlds        = worlds_clean
            existing.notify_site   = notify_site
            existing.notify_fluxer = notify_fluxer
        else:
            count = db.query(WebFfxivHuntSub).filter_by(user_id=web_user.id).count()
            if count >= 50:
                return JsonResponse({'error': 'Maximum 50 subscriptions'}, status=400)
            db.add(WebFfxivHuntSub(
                user_id=web_user.id,
                watch_key=watch_key,
                worlds=worlds_clean,
                notify_site=notify_site,
                notify_fluxer=notify_fluxer,
                created_at=now,
            ))
        db.commit()

    return JsonResponse({'ok': True, 'watch_key': watch_key})


@require_POST
@web_login_required
def api_hunt_sub_delete(request):
    """Remove a hunt subscription."""
    web_user = get_web_user(request)
    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    watch_key = body.get('watch_key', '').strip()
    if not watch_key:
        return JsonResponse({'error': 'watch_key required'}, status=400)

    with get_db_session() as db:
        sub = db.query(WebFfxivHuntSub).filter_by(user_id=web_user.id, watch_key=watch_key).first()
        if sub:
            db.delete(sub)
            db.commit()

    return JsonResponse({'ok': True})
