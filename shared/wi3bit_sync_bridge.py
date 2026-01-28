import datetime
import json
import time
import requests
from django.conf import settings

from shared.models import AttendanceData, BridgeTokens
import logging
logger = logging.getLogger("debug_logger")


class Wi3bitSyncBridge:
    def __init__(self):
        self.username = settings.LOCAL_SERVER_USER
        self.password = settings.LOCAL_SERVER_PASS
        self.area_id = None
        self.dept_id = None
        self.local_users = None
        self.cloud_users = None

        self.token = self.get_token()
        self.area_dept_verification()

    def get_token(self, renew=False):
        if renew:
            BridgeTokens.objects.all().delete()
        token_inst = BridgeTokens.objects.filter(expired=False).last()
        if token_inst:
            logger.info("Using token from DB:")
            return token_inst.token
        logger.info("Getting new token from Local Server:")
        url = f"{settings.LOCAL_SERVER}/jwt-api-token-auth/"
        headers = {"Content-Type": "application/json"}
        data = {"username": self.username, "password": self.password}
        response = requests.post(url, data=json.dumps(data), headers=headers, timeout=5)
        if response.status_code == 400:
            logger.info(f"Token api failed, Status: {response.status_code}, Response: {response.text}")
            raise Exception('Invalid credentials or Local server not running')

        token = response.json()['token']
        BridgeTokens.objects.create(token=token)
        return token

    def get_local_users(self):
        logger.info("Getting local users")
        if self.local_users:
            logger.info("Returned users from cache:")
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
        logger.info("Getting cloud users")
        if self.cloud_users:
            logger.info("Returned users from cache:")
            return self.cloud_users
        headers = {"Content-Type": "application/json"}
        page_number = 1
        cloud_users = []

        current_loop, max_loops = 1, 15
        while current_loop <= max_loops:
            url = f"{settings.CLOUD_SERVER}/zkteco/sync/bridge/users/?token={settings.CLOUD_API_TOKEN}&per_page=100&page={page_number}"
            logger.info(f"Cloud users url: {url}")
            response = requests.get(url, headers=headers, timeout=20)
            logger.info(f"Got response from cloud API, Status: {response.status_code}, Response: {response.text}")
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

    def update_local_attendance(self, start_time=None):
        logger.info(f"Updating local attendance, {start_time}")
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
                logger.info(f"Attendance data created: user: {data['emp_code']}, timestamp: {timestamp}")
        if new_attn:
            self.update_cloud_attendance()

    def update_cloud_attendance(self):
        logger.info("Uploading attendance data to cloud:")
        pending_attn_data = AttendanceData.objects.filter(synced=False)
        if not pending_attn_data.exists():
            logger.info("No pending attendance data to sync, exiting")
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
        logger.info(f"Got response from cloud attn update api, status: {response.status_code}, response: {response.text}")
        if response.status_code == 201:
            pending_attn_data.update(synced=True)
        logger.info("Attendance Synced Successfully!")

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
        logger.info("Users Synced Successfully!")

    def create_user(self, cloud_user):
        logger.info(f"Creating new user: {cloud_user}")
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
        logger.info(f"User Created: {cloud_user['name']}")

    def update_user(self, local_user_id, cloud_user):
        logger.info(f"Updating user, local user id: {local_user_id}, cloud user: {cloud_user}")
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
        logger.info(f"User Updated: {cloud_user['name']}")

    def delete_user(self, local_user_id):
        logger.info(f"Deleting user, local user id: {local_user_id}")
        response = self.local_api_call(
            url=f"{settings.LOCAL_SERVER}/personnel/api/employees/{local_user_id}/",
            method="delete"
        )
        if not (200 <= response.status_code <= 299):
            raise Exception(f"User Deletion Failed \n {response.text}")
        # time.sleep(0.5)
        logger.info(f"User Deleted: {local_user_id}")

    def delete_attn_data(self, attn_id):
        logger.info(f"Deleting attendance data, attn id: {attn_id}")
        response = self.local_api_call(
            url=f"{settings.LOCAL_SERVER}/iclock/api/transactions/{attn_id}/",
            method="delete"
        )
        # time.sleep(0.2)

    def area_dept_verification(self):
        logger.info("Verifying Area and Dept")
        # Area
        response = self.local_api_call(url=f"{settings.LOCAL_SERVER}/personnel/api/areas/")
        if not response.status_code == 200:
            logger.info(f"Area API Failed, Status: {response.status_code}, Response: {response.text}")

        for area in response.json()['data']:
            if area['area_code'] == "wi3bit":
                self.area_id = area['id']
                break

        if not self.area_id:
            logger.info("Area not found, creating new area")
            post_res = self.local_api_call(
                url=f"{settings.LOCAL_SERVER}/personnel/api/areas/",
                method="post",
                data={"area_code": "wi3bit", "area_name": f"Wi3bit (Don't Delete)"}
            )
            if not(200 <= post_res.status_code <= 299):
                raise Exception(f"Area validation failed \n {post_res.text}")
            self.area_id = post_res.json()['id']
            logger.info("Area created successfully")

        # Dept
        response = self.local_api_call(url=f"{settings.LOCAL_SERVER}/personnel/api/departments/")
        if not response.status_code == 200:
            logger.info(f"Dept API Failed, Status: {response.status_code}, Response: {response.text}")

        for dept in response.json()['data']:
            if dept['dept_code'] == "wi3bit":
                self.dept_id = dept['id']
                break

        if not self.dept_id:
            logger.info("Dept not found, creating new dept")
            post_res = self.local_api_call(
                url=f"{settings.LOCAL_SERVER}/personnel/api/departments/",
                method="post",
                data={"dept_code": "wi3bit", "dept_name": "Wi3bit (Don't Delete)",}
            )
            if not(200 <= post_res.status_code <= 299):
                raise Exception(f"Dept validation failed \n {post_res.text}")
            self.dept_id = post_res.json()['id']
            logger.info("Dept created successfully")
        logger.info("Area and Dept verified successfully")

        # logger.info("Verifying devices")
        # response = self.local_api_call(url=f"{settings.LOCAL_SERVER}/iclock/api/terminals/")
        # for device in response.json()['data']:
        #     if device["area"] != self.area_id:
        #         logger.info(f"Device: {device['sn']} is not in wi3bit area, updating it")
        #         post_res = self.local_api_call(
        #             url=f"{settings.LOCAL_SERVER}/iclock/api/terminals/{device['id']}/",
        #             method="put",
        #             data={
        #                 "sn": device['sn'],
        #                 "alias": device['alias'],
        #                 "ip_address": device['ip_address'],
        #                 "area": self.area_id
        #             }
        #         )
        #         if 200 <= response.status_code <= 299:
        #             logger.info(f"Device: {device['sn']} updated successfully")

    def local_api_call(self, url, method='get', data=None, timeout=5, retry=True):
        logger.info(f"Local API Calling: {url} with method: {method}, data: {data}, timeout: {timeout}, token: {self.token}")
        def get_response():
            headers = {"Content-Type": "application/json", "Authorization": f"JWT {self.token}"}
            if method.lower() == "get":
                return requests.get(url, headers=headers, timeout=timeout)
            elif method.lower() == "post":
                return requests.post(url, data=json.dumps(data or {}), headers=headers, timeout=timeout)
            elif method.lower() == "put":
                return requests.put(url, data=json.dumps(data or {}), headers=headers, timeout=timeout)
            elif method.lower() == "delete":
                return requests.delete(url, headers=headers, timeout=timeout)
            logger.info(f"Invalid method: {method}")
            raise Exception(f"Invalid method: {method}")

        response = get_response()
        logger.info(f"Local API Responded: {response.status_code}, Response: {response.text[:100]}... {len(response.text) > 100 and '...' or ''}")
        if retry and response.status_code == 400:
            logger.info("Got 400 status code, getting new token and retrying")
            self.token = self.get_token(renew=True)
            response = get_response()
            if not (200 <= response.status_code <= 299):
                logger.info(f"Got new token but failed again, exiting with error: {response.text}")
                raise Exception(response.text)
        return response
