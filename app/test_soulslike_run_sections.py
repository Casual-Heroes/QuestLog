from pathlib import Path
from unittest import TestCase


ROOT = Path(__file__).parent
TEMPLATES = ROOT / 'questlog_web/templates/questlog_web'
VIEWS = ROOT / 'questlog_web/views_soulslike.py'


class SoulslikeRunSectionTests(TestCase):
    def test_personal_runs_are_grouped_by_state(self):
        source = (TEMPLATES / 'sl_runs.html').read_text(encoding='utf-8')

        self.assertIn('Active Runs', source)
        self.assertIn('Ready to Run', source)
        self.assertIn('Completed Runs', source)
        self.assertIn(
            'partials/sl_personal_run_card.html',
            source,
        )

    def test_community_runs_are_grouped_by_state(self):
        source = (
            TEMPLATES / 'sl_community_runs.html'
        ).read_text(encoding='utf-8')

        self.assertIn('Active Public Runs', source)
        self.assertIn('Ready to Run', source)
        self.assertIn('Recently Completed', source)
        self.assertIn(
            'partials/sl_community_run_card.html',
            source,
        )

    def test_community_ready_builds_require_public_visibility(self):
        source = VIEWS.read_text(encoding='utf-8')
        community_start = source.index('def sl_community_runs(request):')
        community_end = source.index(
            'def sl_leaderboards(request):',
            community_start,
        )
        community_source = source[community_start:community_end]

        self.assertIn('FROM sl_er_builds b', community_source)
        self.assertIn('FROM sl_err_builds b', community_source)
        self.assertGreaterEqual(
            community_source.count(
                'WHERE b.is_public=1 AND u.is_banned=0'
            ),
            2,
        )
        self.assertIn(
            "active_runs = [run for run in runs if run['is_active']]",
            community_source,
        )
        self.assertIn(
            "completed_runs = [run for run in runs if not run['is_active']]",
            community_source,
        )
