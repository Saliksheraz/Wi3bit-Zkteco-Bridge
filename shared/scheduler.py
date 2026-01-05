import datetime
from datetime import timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from django.conf import settings

from shared.models import AttendanceData, BridgeTokens
from shared.wi3bit_sync_bridge import Wi3bitSyncBridge


def start():
    scheduler = BackgroundScheduler()
    scheduler.add_job(attn_heartbeat, 'interval', seconds=3)
    scheduler.add_job(attn_heartbeat_1, 'interval', minutes=30)
    scheduler.add_job(attn_heartbeat_2, 'interval', hours=6)
    scheduler.add_job(attn_heartbeat_3, 'interval', hours=12)
    scheduler.add_job(attn_heartbeat_4, 'interval', days=1)

    scheduler.add_job(update_cloud_attendance, 'interval', minutes=1)
    scheduler.add_job(users_updator, 'interval', minutes=10)

    scheduler.add_job(delete_old_data, 'interval', hours=6)

    scheduler.start()


def attn_heartbeat():
    latest_log = AttendanceData.objects.order_by('-timestamp').first()
    start_time = latest_log.timestamp if latest_log else datetime.datetime.now() - timedelta(hours=6)
    inst = Wi3bitSyncBridge(settings.LOCAL_SERVER_USER, settings.LOCAL_SERVER_PASS)
    inst.update_local_attendance(start_time)


def attn_heartbeat_1():
    start_time = datetime.datetime.now() - timedelta(minutes=35)
    inst = Wi3bitSyncBridge(settings.LOCAL_SERVER_USER, settings.LOCAL_SERVER_PASS)
    inst.update_local_attendance(start_time)


def attn_heartbeat_2():
    start_time = datetime.datetime.now() - timedelta(hours=7)
    inst = Wi3bitSyncBridge(settings.LOCAL_SERVER_USER, settings.LOCAL_SERVER_PASS)
    inst.update_local_attendance(start_time)


def attn_heartbeat_3():
    start_time = datetime.datetime.now() - timedelta(hours=13)
    inst = Wi3bitSyncBridge(settings.LOCAL_SERVER_USER, settings.LOCAL_SERVER_PASS)
    inst.update_local_attendance(start_time)


def attn_heartbeat_4():
    start_time = datetime.datetime.now() - timedelta(days=10)
    inst = Wi3bitSyncBridge(settings.LOCAL_SERVER_USER, settings.LOCAL_SERVER_PASS)
    inst.update_local_attendance(start_time)


def users_updator():
    inst = Wi3bitSyncBridge(settings.LOCAL_SERVER_USER, settings.LOCAL_SERVER_PASS)
    inst.update_users()


def update_cloud_attendance():
    inst = Wi3bitSyncBridge(settings.LOCAL_SERVER_USER, settings.LOCAL_SERVER_PASS)
    inst.update_cloud_attendance()


def delete_old_data():
    # inst = Wi3bitSyncBridge(settings.LOCAL_SERVER_USER, settings.LOCAL_SERVER_PASS)
    attn_data = AttendanceData.objects.filter(timestamp__lte=datetime.datetime.now() - timedelta(days=10),
                                              synced=True)
    # for data in attn_data:
    #     inst.delete_attn_data(data.attn_id)
    #     data.delete()
    attn_data.delete()
    BridgeTokens.objects.filter(expired=True).delete()
