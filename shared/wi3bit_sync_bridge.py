import datetime
import json
import time

import requests
from django.conf import settings

from shared.models import AttendanceData, BridgeTokens


class Wi3bitSyncBridge:
    def __init__(self, username, password):
        self.token = self.get_token(username, password)
        self.local_users = None
        self.cloud_users = None

    def get_token(self, username, password):
        token_inst = BridgeTokens.objects.filter(expired=False).order_by('-id').first()
        if token_inst:
            return token_inst.token

        url = f"{settings.LOCAL_SERVER}/jwt-api-token-auth/"
        headers = {"Content-Type": "application/json"}
        data = {"username": username, "password": password}
        response = requests.post(url, data=json.dumps(data), headers=headers, timeout=5)
        token = response.json()['token']
        BridgeTokens.objects.create(token=token)
        return token

    def get_local_users(self):
        if self.local_users:
            return self.local_users
        headers = {"Content-Type": "application/json", "Authorization": f"JWT {self.token}"}
        page_number = 1
        local_users = []
        while page_number:
            url = f"{settings.LOCAL_SERVER}/personnel/api/employees/?page_size=500&page={page_number}"
            response = requests.get(url, headers=headers, timeout=20)
            if not (200 <= response.status_code <= 299):
                BridgeTokens.objects.all().update(expired=True)
                return self.get_local_users()
            response_json = response.json()
            local_users.extend(response_json['data'])
            if not response_json['next']:
                break
            page_number += 1
            time.sleep(0.5)
        self.local_users = local_users
        return local_users

    def get_cloud_users(self):
        if self.cloud_users:
            return self.cloud_users
        headers = {"Content-Type": "application/json"}
        page_number = 1
        cloud_users = []
        while page_number:
            url = f"{settings.CLOUD_SERVER}/zkteco/sync/bridge/users/?token={settings.CLOUD_API_TOKEN}&per_page=100&page={page_number}"
            response = requests.get(url, headers=headers, timeout=20)
            if not (200 <= response.status_code <= 299):
                BridgeTokens.objects.all().update(expired=True)
                return self.get_cloud_users()
            response_json = response.json()
            cloud_users.extend(response_json['data'])
            if not response_json['has_more']:
                break
            page_number += 1
            time.sleep(1)
        self.cloud_users = cloud_users
        return cloud_users

    def get_cloud_user_by_local(self, local_user):
        for cloud_user in self.get_cloud_users():
            if int(cloud_user['id']) == int(local_user['emp_code']):
                return cloud_user

    def get_local_user_by_cloud(self):
        return

    def update_rfid_number_on_cloud(self):
        local_users = self.get_local_users()
        cloud_users = self.get_cloud_users()
        for local_user in local_users:
            cloud_user = self.get_cloud_user_by_local(local_user)
            card_no = local_user["card_no"]
            card_no = int(card_no) if card_no and card_no.isdigit() else 0
            # if card_no > 1 and card_no != cloud_user['rfid_number']:
            #     print("Updated", card_no, cloud_user['rfid_number'])
            print(local_user['first_name'], local_user['update_time'])

    def update_local_attendance(self, start_time=None):
        if start_time and isinstance(start_time, str):
            start_time = start_time.strftime('%Y-%m-%d %H:%M:%S')
        url = f"{settings.LOCAL_SERVER}/iclock/api/transactions/?start_time={start_time or ''}"
        headers = {"Content-Type": "application/json", "Authorization": f"JWT {self.token}"}
        attendance_data = []
        page_number = 1
        while page_number:
            response = requests.get(f"{url}&page={page_number}", headers=headers, timeout=5)
            if not (200 <= response.status_code <= 299):
                BridgeTokens.objects.all().update(expired=True)
                return self.update_local_attendance(start_time)
            response_json = response.json()
            attendance_data.extend(response_json['data'])
            if not response_json['next']:
                break
            page_number += 1
            time.sleep(0.5)

        new_attn = False
        for data in attendance_data:
            if not AttendanceData.objects.filter(attn_id=data['id']).exists():
                new_attn = True
                timestamp = datetime.datetime.strptime(data['punch_time'], "%Y-%m-%d %H:%M:%S")
                AttendanceData.objects.create(user_id=data['emp_code'], timestamp=timestamp, attn_id=data['id'])
        if new_attn:
            self.update_cloud_attendance()

    def update_cloud_attendance(self):
        pending_attn_data = AttendanceData.objects.filter(synced=False)
        if not pending_attn_data.exists():
            return
        pay_load = [{
            "user_id": data.user_id,
            "timestamp": data.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
        } for data in pending_attn_data]
        response = requests.post(
            f"{settings.CLOUD_SERVER}/zkteco/sync/bridge/attendance_data/?token={settings.CLOUD_API_TOKEN}",
            json=pay_load,
            timeout=10
        )
        if response.status_code == 201:
            pending_attn_data.update(synced=True)
        print("Attendance Synced Successfully!")

    def update_users(self):
        local_users = self.get_local_users()
        cloud_users = self.get_cloud_users()
        for cloud_user in cloud_users:
            user_found = False
            for local_user in local_users:
                if int(cloud_user['id']) == int(local_user['emp_code']):
                    user_found = True
                    if local_user['first_name'] != f"{cloud_user['unique_id']} {cloud_user['name']}":
                        self.update_user(local_user['id'], cloud_user)
            if not user_found:
                self.create_user(cloud_user)

        cloud_ids = {u["id"] for u in cloud_users}
        for local_user in local_users:
            if int(local_user['emp_code']) not in cloud_ids:
                self.delete_user(local_user['id'])
        print("Users Synced Successfully!")

    def create_user(self, cloud_user):
        url = f"{settings.LOCAL_SERVER}/personnel/api/employees/"
        headers = {"Content-Type": "application/json", "Authorization": f"JWT {self.token}"}
        data = {
            "emp_code": cloud_user["id"],
            "department": 2,
            "area": [2],
            "first_name": f"{cloud_user['unique_id']} {cloud_user['name']}",
            # "card_no": cloud_user['rfid_number'],
        }
        response = requests.post(url, data=json.dumps(data), headers=headers, timeout=5)
        if not (200 <= response.status_code <= 299):
            BridgeTokens.objects.all().update(expired=True)
            return self.create_user(cloud_user)

        time.sleep(0.5)
        print("User Created:", cloud_user['name'])

    def update_user(self, local_user_id, cloud_user):
        url = f"{settings.LOCAL_SERVER}/personnel/api/employees/{local_user_id}/"
        headers = {"Content-Type": "application/json", "Authorization": f"JWT {self.token}"}
        data = {
            "emp_code": cloud_user["id"],
            "department": 2,
            "area": [2],
            "first_name": f"{cloud_user['unique_id']} {cloud_user['name']}",
        }
        response = requests.put(url, data=json.dumps(data), headers=headers, timeout=5)
        if not (200 <= response.status_code <= 299):
            BridgeTokens.objects.all().update(expired=True)
            return self.update_user(local_user_id, cloud_user)
        time.sleep(0.5)
        print("User Updated:", cloud_user['name'])

    def delete_user(self, local_user_id):
        url = f"{settings.LOCAL_SERVER}/personnel/api/employees/{local_user_id}/"
        headers = {"Content-Type": "application/json", "Authorization": f"JWT {self.token}"}
        response = requests.delete(url, headers=headers, timeout=5)
        time.sleep(0.5)
        print("User Deleted:", local_user_id)

    def delete_attn_data(self, attn_id):
        url = f"{settings.LOCAL_SERVER}/iclock/api/transactions/{attn_id}/"
        headers = {"Content-Type": "application/json", "Authorization": f"JWT {self.token}"}
        response = requests.delete(url, headers=headers, timeout=5)
        time.sleep(0.2)
