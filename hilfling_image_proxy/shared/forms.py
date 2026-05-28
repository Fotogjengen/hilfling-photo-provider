from django import forms

SECURITY_LEVEL_CHOICES = [
    ("ALLE", "Alle"),
    ("FG", "FG"),
    ("HUSFOLK", "Husfolk"),
]


class PhotoUploadForm(forms.Form):
    motive_id = forms.UUIDField(required=True)
    gang_id = forms.UUIDField(required=False)
    date = forms.DateField(required=True, input_formats=["%Y-%m-%d"])
    good_picture = forms.BooleanField(required=False)
    analog = forms.BooleanField(required=False)
    media = forms.ImageField(required=True)
    security_level = forms.ChoiceField(required=True, choices=SECURITY_LEVEL_CHOICES)
