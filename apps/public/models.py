from django.db import models


class Lead(models.Model):
    """A prospective-investor contact request submitted from the public landing page."""

    class Status(models.TextChoices):
        NEW = "new", "New"
        CONTACTED = "contacted", "Contacted"
        CONVERTED = "converted", "Converted"
        DISMISSED = "dismissed", "Dismissed"

    name = models.CharField(max_length=120)
    email = models.EmailField()
    contact = models.CharField(max_length=120, blank=True, default="")
    message = models.TextField(blank=True, default="")
    locale = models.CharField(max_length=8, blank=True, default="")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.NEW)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} <{self.email}> [{self.status}]"
