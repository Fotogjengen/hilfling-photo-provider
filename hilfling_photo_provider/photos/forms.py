from django import forms

from hilfling_photo_provider.utils.security_level import USER_UPLOAD_LEVELS, SecurityLevel


class PhotoUploadForm(forms.Form):
    motive_id = forms.UUIDField(required=True)
    gang_id = forms.UUIDField(required=False)
    date = forms.DateField(required=True, input_formats=["%Y-%m-%d"])
    good_picture = forms.BooleanField(required=False)
    media_id = forms.UUIDField(required=True)
    media = forms.ImageField(required=True)
    security_level = forms.ChoiceField(required=True, choices=SecurityLevel.choices)


class UserUploadForm(forms.Form):
    media = forms.ImageField(required=True)
    security_level = forms.ChoiceField(
        required=True,
        choices=[(level.value, level.label) for level in USER_UPLOAD_LEVELS],
    )
