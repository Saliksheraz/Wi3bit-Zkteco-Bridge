from django.db import models


class AttendanceData(models.Model):
    user_id = models.IntegerField(null=True, blank=True)
    timestamp = models.DateTimeField(null=True, blank=True)
    attn_id = models.IntegerField(null=True, blank=True)
    synced = models.BooleanField(null=True, default=False)


class BridgeTokens(models.Model):
    token = models.TextField(null=True, blank=True)
    expired = models.BooleanField(null=True, default=False)
    created_at = models.DateTimeField(auto_now_add=True, null=True)
