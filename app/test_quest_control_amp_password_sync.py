from types import SimpleNamespace

from django.test import SimpleTestCase

from app.questlog_web.views_admin import (
    _qc_client_config,
    _qc_extract_amp_server_password,
)


class QuestControlAmpPasswordSyncTests(SimpleTestCase):
    def test_extracts_the_generic_module_server_password(self):
        setting = {
            'node': 'Meta.GenericModule.ServerPassword',
            'name': 'Server Password',
            'input_type': 'password',
            'current_value': 'correct-horse-battery-staple',
        }

        self.assertEqual(
            _qc_extract_amp_server_password(setting),
            'correct-horse-battery-staple',
        )

    def test_empty_amp_password_is_authoritative(self):
        setting = {
            'node': 'Meta.GenericModule.ServerPassword',
            'input_type': 'password',
            'current_value': '',
        }

        self.assertEqual(_qc_extract_amp_server_password(setting), '')
        self.assertEqual(_qc_extract_amp_server_password(SimpleNamespace(
            node='Meta.GenericModule.ServerPassword',
            input_type='password',
            current_value=None,
        )), '')

    def test_ignores_unrecognized_amp_responses(self):
        self.assertIsNone(_qc_extract_amp_server_password('NotFound'))
        self.assertIsNone(_qc_extract_amp_server_password({
            'node': 'GenericModule.App.RemoteAdminPassword',
            'input_type': 'password',
            'current_value': 'not-the-player-password',
        }))

    def test_browser_config_redacts_plaintext_but_keeps_toggle(self):
        config = {
            'instance_name': 'CH-HeroesofPalpagos02',
            'server_password': 'do-not-render-this',
            'show_password': 1,
        }

        public_config = _qc_client_config(config)

        self.assertNotIn('server_password', public_config)
        self.assertEqual(public_config['show_password'], 1)
        self.assertIn('server_password', config)
