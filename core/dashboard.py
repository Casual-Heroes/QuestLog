from admin_tools.dashboard import modules, Dashboard
from admin_tools.dashboard.modules import LinkList

class ExternalLinkList(LinkList):
    def render(self, request, context):
        """
        Override to add target="_blank" to external links.
        """
        for link in self.children:
            if isinstance(link, dict) and link.get('external', False):
                link['attrs'] = {
                    'target': '_blank',
                    'rel': 'noopener noreferrer'
                }
        return super().render(request, context)

class CustomIndexDashboard(Dashboard):
    def init_with_context(self, context):
        self.children.append(ExternalLinkList(
            'Quick Links',
    children=[
        {'title': 'Main Website', 'url': 'https://casual-heroes.com', 'external': True},
        {'title': 'Games We Play', 'url': 'https://casual-heroes.com/gamesweplay', 'external': True},
        {'title': 'About Us', 'url': 'https://casual-heroes.com/aboutus', 'external': True},
        {'title': 'Privacy Policy', 'url': 'https://casual-heroes.com/privacy', 'external': True},
        {'title': 'Terms of Service', 'url': 'https://casual-heroes.com/terms', 'external': True},
        {'title': 'Contact Us', 'url': 'https://casual-heroes.com/contactus', 'external': True},
        {'title': 'FAQ', 'url': 'https://casual-heroes.com/faq', 'external': True},
        {'title': 'Guides', 'url': 'https://casual-heroes.com/guides', 'external': True},
        {'title': 'Reviews', 'url': 'https://casual-heroes.com/reviews', 'external': True},
        {'title': 'ArkQuest', 'url': 'https://ark.casual-heroes.com', 'external': True},
        {'title': 'ExliesQuest', 'url': 'https://conancommand.casual-heroes.com', 'external': True},
        {'title': 'ShroudQuest', 'url': 'https://shroudquest.casual-heroes.com', 'external': True},
        {'title': 'VQuest', 'url': 'https://VQuest.casual-heroes.com', 'external': True},
        {'title': 'Analytics Panel', 'url': 'https://casual-heroes.com/admin/analytics', 'external': True},
    ]
        ))


        self.children.append(modules.ModelList(
            'User Management',
            models=('django.contrib.auth.models.User',),
        ))

        self.children.append(modules.RecentActions(
            'Recent Activity',
            limit=10,
        ))

        self.children.append(modules.Feed(
            'Casual Heroes Blog Updates',
            feed_url='https://casual-heroes.com/feed/',
            limit=3
        ))
