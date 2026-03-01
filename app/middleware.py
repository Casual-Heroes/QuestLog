"""
Custom middleware for Casual Heroes Django site
"""
from django.shortcuts import redirect
from django.conf import settings


class DashboardDomainMiddleware:
    """
    Redirect the dashboard subdomain root to the Warden dashboard.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = request.get_host().lower()

        if settings.DASHBOARD_DOMAIN in host:
            if request.path == '/':
                return redirect('/questlog/')

        response = self.get_response(request)
        return response
