🌍 FinTrip - Travel Recommendation & ChatBot

🚀 Giới thiệu

FinTrip là một nền tảng thông minh giúp bạn khám phá các điểm du lịch phù hợp với sở thích cá nhân và cung cấp trợ lý ảo ChatBot hỗ trợ mọi thông tin liên quan đến du lịch.

📌 Yêu cầu hệ thống

Python 3.11.0

Django (Phiên bản mới nhất)

Cơ sở dữ liệu: SQLite, PostgreSQL, hoặc MySQL

🛠 Cài đặt & Khởi chạy

## Getting Started

1. **Clone the repository**:
```bash
    git clone https://github.com/FinTrip/AI.git
```

cd AI

2. **Create and activate virtual environment**:
```commandline
    python -m venv venv
```
#### Đối với macOS/Linux
```commandline
    source venv/bin/activate
```
#### Đối với Windows
```commandline
    venv\Scripts\activate
```

3. **Install requirements**:
```commandline
    pip install -r requirements.txt
```

4. **Set up the Django project**:
- **Make database migrations**:
```commandline
    python manage.py migrate
```

5. **Run the Django development server**:
```commandline
    python manage.py runserver
```

💡 Truy cập ứng dụng tại: http://127.0.0.1:8000/

📂 Cấu trúc thư mục
```commandline
fintrip/
│-- manage.py
│-- requirements.txt
│-- readme.MD
│-- recommendations/
│   -- data/
│       │-- food.csv
│       │-- hotels.csv
│       │-- hotels_data.csv
│       │-- place.csv
│       │-- place2.xlsx
│   │-- .env
│   │-- _init_.py
│   │-- CheckException.py
│   │-- flight.py
│   │-- hotel.py
│   │-- processed.py
│   │-- tests.py
│   │-- views.py
│   │-- models.py
│   │-- urls.py
│   │-- admin.py
│   │-- apps.py
│-- chatbot/
│   -- model/
│    │-- views.py
│   │-- _init_.py
│   │-- admin.py
│   │-- app.py
│   │-- chatbot_model.py
│   │-- views.py
│   │-- utils.py
│   │-- models.py
│   │-- urls.py
│-- FinTrip/
    │-- settings.py
    │-- urls.py
    │-- wsgi.py
│-- static
│   -- css/
│   -- img/

```