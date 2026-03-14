"""
Management command: rotate_featured_creators

Runs weekly for COTW (every Monday) and monthly for COTM (1st of month).
Calls the same rotation logic used by the admin panel auto-rotate buttons.

Cron setup:
    0 0 * * 1 /srv/ch-webserver/chwebsiteprj/bin/python /srv/ch-webserver/manage.py rotate_featured_creators --cotw >> /srv/ch-webserver/logs/rotate_creators.log 2>&1
    0 0 1 * * /srv/ch-webserver/chwebsiteprj/bin/python /srv/ch-webserver/manage.py rotate_featured_creators --cotm >> /srv/ch-webserver/logs/rotate_creators.log 2>&1
"""
from django.core.management.base import BaseCommand
from app.db import get_db_session
from app.questlog_web.views_admin import _do_rotate_cotw, _do_rotate_cotm


class Command(BaseCommand):
    help = 'Auto-rotate Creator of the Week and/or Creator of the Month.'

    def add_arguments(self, parser):
        parser.add_argument('--cotw', action='store_true', help='Rotate COTW')
        parser.add_argument('--cotm', action='store_true', help='Rotate COTM')

    def handle(self, *args, **options):
        if not options['cotw'] and not options['cotm']:
            self.stdout.write('No flags given. Use --cotw and/or --cotm.')
            return

        with get_db_session() as db:
            if options['cotw']:
                result = _do_rotate_cotw(db)
                if result:
                    self.stdout.write(f'COTW rotated to: {result.get("display_name", result.get("id"))}')
                else:
                    self.stdout.write('COTW: no eligible creators or cooldown active, skipped.')

            if options['cotm']:
                result = _do_rotate_cotm(db)
                if result:
                    self.stdout.write(f'COTM rotated to: {result.get("display_name", result.get("id"))}')
                else:
                    self.stdout.write('COTM: no eligible creators or cooldown active, skipped.')
