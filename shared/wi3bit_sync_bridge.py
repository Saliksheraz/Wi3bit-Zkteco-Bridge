import datetime
import json
import time
import requests
from django.conf import settings
from shared.models import AttendanceData, BridgeTokens


class Wi3bitSyncBridge:
    def __init__(self):
        self.username = settings.LOCAL_SERVER_USER
        self.password = settings.LOCAL_SERVER_PASS
        self.area_id = 1
        self.dept_id = 1
        self.local_users = None
        self.cloud_users = None

        self.token = self.get_token()
        # self.area_dept_verification()

    def get_token(self, renew=False):
        if renew:
            BridgeTokens.objects.all().delete()
        token_inst = BridgeTokens.objects.filter(expired=False).last()
        if token_inst:
            return token_inst.token

        url = f"{settings.LOCAL_SERVER}/jwt-api-token-auth/"
        headers = {"Content-Type": "application/json"}
        data = {"username": self.username, "password": self.password}
        response = requests.post(url, data=json.dumps(data), headers=headers, timeout=5)
        if response.status_code == 400:
            raise Exception('Invalid credentials or Local server not running')

        token = response.json()['token']
        BridgeTokens.objects.create(token=token)
        return token

    def get_local_users(self):
        if self.local_users:
            return self.local_users
        page_number = 1
        local_users = []
        while page_number:
            response = self.local_api_call(
                url= f"{settings.LOCAL_SERVER}/personnel/api/employees/?page_size=500&page={page_number}"
            )
            response_json = response.json()
            local_users.extend(response_json['data'])
            if not response_json['next']:
                break
            page_number += 1
            # time.sleep(0.5)
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
            if not response.status_code == 200:
                raise Exception(f"Invalid response from cloud API:\n {response.text}")
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
        attendance_data = []
        page_number = 1
        while page_number:
            response = self.local_api_call(url=f"{url}&page={page_number}")
            response_json = response.json()
            attendance_data.extend(response_json['data'])
            if not response_json['next']:
                break
            page_number += 1
            # time.sleep(0.5)

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
            timeout=10,
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
        response = self.local_api_call(
            url= f"{settings.LOCAL_SERVER}/personnel/api/employees/",
            method="post",
            data={
                "emp_code": cloud_user["id"],
                "department": self.dept_id,
                "area": [self.area_id],
                "first_name": f"{cloud_user['unique_id']} {cloud_user['name']}",
                # "card_no": cloud_user['rfid_number'],
            },
        )
        if not (200 <= response.status_code <= 299):
            raise Exception(f"User Creation Failed \n {response.text}")
        # time.sleep(0.5)
        print("User Created:", cloud_user['name'])

    def update_user(self, local_user_id, cloud_user):
        response = self.local_api_call(
            url=f"{settings.LOCAL_SERVER}/personnel/api/employees/{local_user_id}/",
            method="put",
            data={
                "emp_code": cloud_user["id"],
                "area": [self.area_id],
                "department": self.dept_id,
                "first_name": f"{cloud_user['unique_id']} {cloud_user['name']}",
            },
        )
        if not (200 <= response.status_code <= 299):
            raise Exception(f"User Update Failed \n {response.text}")
        # time.sleep(0.5)
        print("User Updated:", cloud_user['name'])

    def delete_user(self, local_user_id):
        response = self.local_api_call(
            url=f"{settings.LOCAL_SERVER}/personnel/api/employees/{local_user_id}/",
            method="delete"
        )
        if not (200 <= response.status_code <= 299):
            raise Exception(f"User Deletion Failed \n {response.text}")
        # time.sleep(0.5)
        print("User Deleted:", local_user_id)

    def delete_attn_data(self, attn_id):
        response = self.local_api_call(
            url=f"{settings.LOCAL_SERVER}/iclock/api/transactions/{attn_id}/",
            method="delete"
        )
        # time.sleep(0.2)

    def area_dept_verification(self):
        # Area
        response = self.local_api_call(url=f"{settings.LOCAL_SERVER}/personnel/api/areas/{self.area_id}/")
        if response.status_code == 404:
            post_res = self.local_api_call(
                url=f"{settings.LOCAL_SERVER}/personnel/api/areas/",
                method="post",
                data={"area_code": self.area_id, "area_name": f"Auto Defined (Don't Delete)"}
            )
            if not(200 <= post_res.status_code <= 299):
                raise Exception(f"Area validation failed \n {post_res.text}")
        # Dept
        response = self.local_api_call(url=f"{settings.LOCAL_SERVER}/personnel/api/departments/{self.dept_id}/")
        if response.status_code == 404:
            post_res = self.local_api_call(
                url=f"{settings.LOCAL_SERVER}/personnel/api/departments/",
                method="post",
                data={"dept_code": self.dept_id, "dept_name": "Auto Defined (Don't Delete)",}
            )
            if not(200 <= post_res.status_code <= 299):
                raise Exception(f"Dept validation failed \n {post_res.text}")

    def local_api_call(self, url, method='get', data=None, timeout=5, retry=True):
        def get_response():
            headers = {"Content-Type": "application/json", "Authorization": f"JWT {self.token}"}
            if method.lower() == "get":
                response = requests.get(url, headers=headers, timeout=timeout)
            elif method.lower() == "post":
                response = requests.post(url, data=json.dumps(data or {}), headers=headers, timeout=timeout)
            elif method.lower() == "put":
                response = requests.put(url, data=json.dumps(data or {}), headers=headers, timeout=timeout)
            elif method.lower() == "delete":
                response = requests.delete(url, headers=headers, timeout=timeout)
            else:
                raise Exception(f"Invalid method: {method}")
            return response

        response = get_response()
        if retry and response.status_code == 400:
            self.token = self.get_token(renew=True)
            response = get_response()
            if not (200 <= response.status_code <= 299):
                raise Exception(response.text)
        return response
