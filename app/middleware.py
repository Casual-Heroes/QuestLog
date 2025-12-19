"""
Custom middleware for Casual Heroes Django site
"""
from django.shortcuts import redirect


class DashboardDomainMiddleware:
    """
    Redirect dashboard.casual-heroes.com to the Warden dashboard
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Check if the request is for dashboard subdomain
        host = request.get_host().lower()

        if 'dashboard.casual-heroes.com' in host:
            # If at root path, redirect to warden dashboard
            if request.path == '/':
                return redirect('/questlog/')

        response = self.get_response(request)
        return response
