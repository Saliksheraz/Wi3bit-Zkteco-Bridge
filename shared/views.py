import os

from django.conf import settings
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
from django.http import JsonResponse
from django.shortcuts import render



def server_error_logs(request):
    requestType = request.GET.get("requestType")
    if requestType == "get_logs_data":
        log_path = getattr(settings, "ERROR_LOG_FILE_PATH", None)
        if not log_path or not os.path.exists(log_path):
            return JsonResponse({"message": "Error Log File Not Found"}, status=404)
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except UnicodeDecodeError:
            with open(log_path, "r", encoding="latin-1") as f:
                lines = f.readlines()
        lines = [line.rstrip("\n") for line in lines]
        lines.reverse()
        paginator = Paginator(lines, 60)
        page = request.GET.get("page", 1)
        try:
            page_obj = paginator.page(page)
        except PageNotAnInteger:
            page_obj = paginator.page(1)
        except EmptyPage:
            page_obj = paginator.page(paginator.num_pages)
        return JsonResponse({
            "total_lines": paginator.count,
            "num_pages": paginator.num_pages,
            "current_page": page_obj.number,
            "has_more": page_obj.has_next(),
            "logs": page_obj.object_list,
        })
    return render(request, 'shared/server_error_logs.html')
