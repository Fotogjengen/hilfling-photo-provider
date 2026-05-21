from django import forms

SECURITY_LEVEL_CHOICES = [
    ("ALLE", "Alle"),
    ("FG", "FG"),
    ("HUSFOLK", "Husfolk"),
]


class PhotoUploadForm(forms.Form):
    album = forms.CharField(required=True)
    motive = forms.CharField(required=True)
    date = forms.DateField(required=True, input_formats=["%Y-%m-%d"])
    is_good_picture = forms.BooleanField(required=False)
    media = forms.ImageField(required=True)
    place = forms.CharField(required=True)
    security_level = forms.ChoiceField(required=True, choices=SECURITY_LEVEL_CHOICES)
    category = forms.CharField(required=True)
    tag = forms.CharField(required=False)
    photographer_id = forms.UUIDField(required=True)
    event_owner = forms.CharField(required=True)
