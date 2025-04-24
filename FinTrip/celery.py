import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'FinTrip.settings')

app = Celery('FinTrip')

app.config_from_object('django.conf:settings', namespace='CELERY')

# Debug: Kiểm tra trước khi autodiscover
print("Before autodiscover_tasks")
app.autodiscover_tasks(['Recommend'])
print("After autodiscover_tasks")

# Debug: Kiểm tra danh sách tác vụ đã đăng ký
print("Registered tasks:", app.tasks)