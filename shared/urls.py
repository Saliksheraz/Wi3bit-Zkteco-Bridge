from django.urls import path
from . import views

urlpatterns = [
    path("logs/", views.server_error_logs, name="server_error_logs"),
    path("update/users/", views.updateUsers, name="updateUsers"),
    path("update/local/attn/", views.updateLocalAttn, name="updateLocalAttn"),
    path("update/cloud/attn/", views.updateCloudAttn, name="updateCloudAttn"),
]