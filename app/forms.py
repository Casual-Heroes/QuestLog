#forms.py

from django import forms

ROLE_CHOICES = [
("Casual gamer", "Casual gamer"),
("Serious/competitive gamer", "Serious/competitive gamer"),
("Twitch streamer", "Twitch streamer"),
("YouTube streamer", "YouTube streamer"),
("Multi-platform streamer", "Multi-platform streamer"),
("Server admin/owner", "Server admin/owner"),
("Content creator (non-streaming)", "Content creator (non-streaming)"),
("Game developer", "Game developer"),
("Other", "Other")
]


GENRE_CHOICES = [
("Survival games", "Survival games"),
("ARPG", "ARPG"),
("RPG", "RPG"),
("MMORPG", "MMORPG"),
("FPS/Shooter", "FPS/Shooter"),
("Battle Royale", "Battle Royale"),
("Strategy", "Strategy"),
("Indie", "Indie"),
("Other", "Other")
]


EXPERIENCE_CHOICES = [
("<1", "Less than 1 year"),
("1-3", "1-3 years"),
("3-5", "3-5 years"),
("5+", "5+ years")
]

class SurveyForm(forms.Form):
    roles = forms.MultipleChoiceField(choices=ROLE_CHOICES, widget=forms.CheckboxSelectMultiple, required=False)
    genres = forms.MultipleChoiceField(choices=GENRE_CHOICES, widget=forms.CheckboxSelectMultiple, required=False)
    experience = forms.ChoiceField(choices=EXPERIENCE_CHOICES, widget=forms.RadioSelect, required=False)


    survival_frustrations_ranked = forms.CharField(widget=forms.Textarea, required=False)
    arpg_rpg_bothers_ranked = forms.CharField(widget=forms.Textarea, required=False)
    discovery_channels = forms.CharField(required=False)


    creation_time_sinks_ranked = forms.CharField(widget=forms.Textarea, required=False)
    discoverability_challenge = forms.CharField(required=False)
    go_live_notify_methods = forms.CharField(required=False)
    go_live_effectiveness = forms.CharField(required=False)
    engagement_needs = forms.MultipleChoiceField(choices=[], widget=forms.CheckboxSelectMultiple, required=False)


    tools_in_use = forms.MultipleChoiceField(choices=[], widget=forms.CheckboxSelectMultiple, required=False)
    missing_from_setup = forms.CharField(widget=forms.Textarea, required=False)
    one_automation = forms.CharField(widget=forms.Textarea, required=False)
    monthly_willing_to_pay = forms.CharField(required=False)


    admin_time_consumers = forms.CharField(required=False)
    player_churn_causes = forms.CharField(required=False)
    server_mgmt_needs = forms.CharField(required=False)


    biggest_unsolved = forms.CharField(widget=forms.Textarea, required=False)
    magic_wand = forms.CharField(widget=forms.Textarea, required=False)
    referral_drivers = forms.CharField(widget=forms.Textarea, required=False)
    other_thoughts = forms.CharField(widget=forms.Textarea, required=False)


    email = forms.EmailField(required=False)
    discord = forms.CharField(required=False)
    platform = forms.CharField(required=False)
    consent = forms.BooleanField(required=False)