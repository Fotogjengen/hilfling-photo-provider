from django.db import models


class SecurityLevel(models.TextChoices):
    ALLE = "ALLE", "Alle"
    FG = "FG", "FG"
    HUSFOLK = "HUSFOLK", "Husfolk"


# User content is visible to everyone or members only, never husfolk-only
USER_UPLOAD_LEVELS = [SecurityLevel.ALLE, SecurityLevel.FG]
