"""Small code-backed additions to the database boss registry.

The database remains the canonical catalog.  Entries live here only when the
desktop tracker has learned about a boss before the deployed registry data has
been updated.  Every caller de-duplicates these entries by boss key, so a later
database catalog update can safely take over without creating duplicates.
"""


_SUPPLEMENTAL_BOSSES = {
    ('elden_ring', 'err'): (
        {
            'key': 'Alabaster Lord (East of the Church of the Plague)',
            'name': 'Alabaster Lord',
            'location': 'East of the Church of the Plague',
            'region': 'Caelid',
            'tier': 'great_enemy',
        },
        {
            'key': 'Leonine Misbegotten (War-Dead Catacombs)',
            'name': 'Leonine Misbegotten',
            'location': 'War-Dead Catacombs',
            'region': 'Caelid',
            'tier': 'great_enemy',
        },
    ),
}


def _normalized_game_mode(game, game_mode):
    """Return the registry's canonical game/mode pair for older ERR runs."""
    if game == 'err':
        return 'elden_ring', 'err'
    return game or 'elden_ring', game_mode or 'vanilla'


def supplemental_bosses(game, game_mode):
    """Return defensive copies of supplemental bosses for a game and mode."""
    key = _normalized_game_mode(game, game_mode)
    return [dict(boss) for boss in _SUPPLEMENTAL_BOSSES.get(key, ())]


def find_supplemental_boss(game, game_mode, boss_key):
    """Find a supplemental boss by the same unique key used by EldenTracker."""
    for boss in supplemental_bosses(game, game_mode):
        if boss['key'] == boss_key:
            return boss
    return None
