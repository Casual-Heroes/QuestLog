"""
Seed: ERR new Spirit Ash full detail (fills the 8 stub rows from the system seed).
Source: err.fandom.com individual Spirit Ash pages, pasted directly by user.

Run: chwebsiteprj/bin/python3 seed_soulslike_err_spirit_ash_detail.py
"""
import django
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()

# (name, fp_cost, enrage_cost, description, passive_behavior/info, acquisition_detail)
SPIRIT_ASHES = {
    'Blaidd': {
        'fp_cost': '740',
        'enrage_cost': '1480',
        'description': (
            "Legendary ashen remains. Use to summon the spirit of Blaidd the Half-Wolf. Blaidd shadowed "
            "the Empyrean Ranni, his loyalty unwavering to the bitter end. The ashen wolf still rages on "
            "into eternity even after his death, his peerless strength brought to bear against man and "
            "god alike, all for the sake of Lady Ranni."
        ),
        'passive_behavior': (
            "Has two Crimson Flasks, inflicts Frostbite, and is generally an incredibly powerful summon - "
            "but has an extremely high Enrage cost (1480 FP)."
        ),
        'acquisition_detail': "Found at the top of Ranni's Rise after completing Blaidd/Ranni's questline.",
    },
    'Glintstone Miner Ashes': {
        'fp_cost': '520',
        'enrage_cost': '1040',
        'description': (
            "Ashes in which spirits still dwell. Use to summon the spirits of two Glintstone Miners - a "
            "hulking figure capable of Stonedigger sorcery, and a frail caster slinging faux sorceries "
            "from the back. Ceaseless toil around glintstone has left these former students overgrown "
            "with crystal, eyes replaced with gems not unlike those of the Academy's glintstone crowns."
        ),
        'passive_behavior': (
            "One miner is aggressive and uses Rock Blaster; the other is a caster who stays back and "
            "launches Glintstone Scraps. When Enraged, the caster miner buffs its summoner with "
            "Starlight, slightly restoring FP and granting clear vision in dark tunnels."
        ),
        'acquisition_detail': "Found inside the Altus Tunnel.",
    },
    'Lazuli Sorcerer': {
        'fp_cost': None,
        'enrage_cost': None,
        'description': None,
        'passive_behavior': None,
        'acquisition_detail': None,
        '_skip': True,  # not pasted yet - leave as stub
    },
    'Grand Inquisitor Eli': {
        'fp_cost': '980',
        'enrage_cost': '1960',
        'description': (
            "Legendary ashen remains. Use to summon the spirits of Grand Inquisitor Eli and four "
            "Hornsent Inquisitors. Transgressions against the Hornsent faith were investigated through "
            "coercive torture - just the sound of the Grand Inquisitor's momentous footsteps was enough "
            "for common folk to confess to any misdeed, the fear of her questioning exceeding that of "
            "her punishment."
        ),
        'passive_behavior': "Summons Grand Inquisitor Eli alongside four Hornsent Inquisitors.",
        'acquisition_detail': (
            "Acquired by trading Elder Inquisitor Jori's Remembrance with Finger Reader Enia at "
            "Roundtable Hold."
        ),
    },
    'Latenna and Lobo': {
        'fp_cost': '770',
        'enrage_cost': '1540',
        'description': (
            "Ashen remains in which spirits yet dwell. Use to summon the spirits of Latenna and Lobo - a "
            "rare case of those who chose to become a spirit voluntarily. Latenna was renowned as a deft "
            "magic archer; now reunited with her beloved wolf companion, she continues in your service as "
            "a brilliant and agile huntress, as she was in life."
        ),
        'passive_behavior': None,
        'acquisition_detail': "Found at the end of Latenna's questline in Apostate Derelict.",
    },
    'Ringmaster Ophidion': {
        'fp_cost': '630',
        'enrage_cost': '1260',
        'description': (
            "Ashen remains in which spirits yet dwell. Use to summon the spirit of Ringmaster Ophidion. "
            "Uses the model and a similar moveset to Duelist enemies. Though expected to fight in the "
            "role of a deceitful and insidious villain, Ophidion's body was marked with the lashes earned "
            "through defiance and mercy - this sight intrigued a young lord, who recruited the gladiator "
            "into his service."
        ),
        'passive_behavior': "Necessary in order to acquire the Coilheart weapon.",
        'acquisition_detail': (
            "Found in the Serpentine Depths, guarded by a Colossal Fingercreeper (not necessary to defeat "
            "it to acquire the ashes). Requires Favor of the Devoured for limited magma immunity to reach "
            "the area. From the Serpentine Depths Site of Grace: drop down to the northeast into the "
            "cavern, walk to the precipice edge and go down the column into the next cavern, head straight "
            "toward the magma and turn left following the path to a patch of glowing solidified magma, "
            "then take the west path to an illusory wall. Behind the wall is a large dark cavern containing "
            "the spirit ashes (and the Colossal Fingercreeper underneath)."
        ),
    },
    'Starcaller Ashes': {
        'fp_cost': '340',
        'enrage_cost': '680',
        'description': (
            "Ashen remains in which spirits yet dwell. Use to summon the spirits of two Starcallers. So "
            "obsessed are these kindred spirits with their quest for otherworldly powers from beyond the "
            "veil that they've barely taken notice of their untimely deaths to starvation and exposure."
        ),
        'passive_behavior': "One prefers throwing Gravity Stones, the other prefers melee attacks.",
        'acquisition_detail': "Found inside the Sellia Crystal Tunnel.",
    },
    'Zamor Knight Lyedna': {
        'fp_cost': '700',
        'enrage_cost': '1400',
        'description': (
            "Legendary ashen remains. Use to summon the spirit of Zamor Knight Lyedna. Though sworn by "
            "ancient oaths to a life of silence, Lyedna has proven many times that words aren't necessary "
            "to be a stalwart companion in war, and a loyal friend in peace."
        ),
        'passive_behavior': "Uses Zamor Phase 1 AI while Passive, switches to Phase 2 AI when Enraged.",
        'acquisition_detail': (
            "Found inside the cellar of Zamor Ruins, Mountaintops of the Giants, after activating all the sigils."
        ),
    },
}


def run():
    with engine.connect() as conn:
        updated = 0
        skipped = 0
        for name, detail in SPIRIT_ASHES.items():
            if detail.get('_skip'):
                print(f'  SKIPPED (no data yet): {name}')
                skipped += 1
                continue

            result = conn.execute(text("""
                UPDATE sl_spirit_ashes
                SET fp_cost = :fp, enrage_fp_cost = :enrage, description = :desc,
                    passive_behavior = :passive, acquisition_detail = :acq
                WHERE name = :name AND game = 'err'
            """), {
                'fp': detail['fp_cost'],
                'enrage': detail['enrage_cost'],
                'desc': detail['description'],
                'passive': detail['passive_behavior'],
                'acq': detail['acquisition_detail'],
                'name': name,
            })
            if result.rowcount:
                updated += 1
                print(f'  Updated: {name}')
            else:
                print(f'  NOT FOUND: {name}')
        conn.commit()
        print(f'\n{updated} Spirit Ashes updated, {skipped} skipped (awaiting data).')

        total_detailed = conn.execute(text(
            "SELECT COUNT(*) FROM sl_spirit_ashes WHERE game='err' AND is_new_to_err=1 AND description IS NOT NULL"
        )).scalar()
        print(f'New ERR Spirit Ashes with full detail: {total_detailed}/8')


if __name__ == '__main__':
    run()
