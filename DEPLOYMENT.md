# Production Deployment Guide: LearnPro CRM / LMS

This guide provides end-to-end instructions for deploying LearnPro to production. It covers:
1. [PythonAnywhere Deployment](#1-pythonanywhere-deployment-step-by-step)
2. [Linux VPS Deployment (Ubuntu / Nginx / Gunicorn / Systemd)](#2-linux-vps-deployment-ubuntu--nginx--gunicorn)
3. [Docker Compose Deployment](#3-docker-compose-production-deployment)
4. [Storage Backend Setup (Google Drive / S3 / Local)](#4-storage-configuration-google-drive--s3)
5. [Database Engine (PostgreSQL / SQLite / MongoDB Atlas)](#5-database-engine-configuration)
6. [Pre-Flight Security Checklist](#6-pre-flight-security-checklist)

---

## 1. PythonAnywhere Deployment (Step-by-Step)

[PythonAnywhere](https://www.pythonanywhere.com/) provides an easy and affordable way to host Django applications with automatic SSL (`https://<username>.pythonanywhere.com`).

### Step 1: Create an Account & Open a Bash Console
1. Register or log in at [pythonanywhere.com](https://www.pythonanywhere.com/).
2. Navigate to the **Consoles** tab and open a **Bash console**.

### Step 2: Clone the Repository
In your Bash console, clone your repository into your home directory:
```bash
cd ~
git clone https://github.com/<your-username>/<repo-name>.git CRM
cd ~/CRM
```

### Step 3: Create & Activate Virtual Environment
Use Python 3.11 or 3.12 (matches PythonAnywhere supported versions):
```bash
mkvirtualenv --python=/usr/bin/python3.11 crm-env
# or if using virtualenvwrapper:
workon crm-env

# Upgrade pip and install dependencies
pip install --upgrade pip
pip install -r requirements/production.txt
```

### Step 4: Configure Environment Variables (`.env`)
Create your production `.env` file in the project root (`~/CRM/.env`):
```bash
nano ~/CRM/.env
```

Paste and customize the following settings:
```ini
# Core Django
SECRET_KEY=generate-a-strong-random-key-here-minimum-50-chars
DEBUG=False
ALLOWED_HOSTS=yourusername.pythonanywhere.com,www.yourdomain.com

# Base URL & Security
BASE_URL=https://yourusername.pythonanywhere.com
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
CSRF_TRUSTED_ORIGINS=https://yourusername.pythonanywhere.com

# Database (Default SQLite on PythonAnywhere, or external Postgres/MySQL)
DATABASE_ENGINE=sql
# If using PythonAnywhere MySQL (set up in the "Databases" tab):
# DATABASE_URL=mysql://yourusername:yourdbpassword@yourusername.mysql.pythonanywhere-services.com/yourusername$crm

# MongoDB (Optional: e.g. MongoDB Atlas free cluster)
# MONGODB_URI=mongodb+srv://<user>:<password>@cluster0.mongodb.net/crm_prod?retryWrites=true&w=majority
# MONGODB_DATABASE=crm_prod

# Storage: Local or Google Drive
STORAGE_BACKEND=local
# If using Google Drive:
# STORAGE_BACKEND=gdrive
# GDRIVE_SERVICE_ACCOUNT_JSON_PATH=/home/yourusername/CRM/credentials/google_service_account.json
# GDRIVE_ROOT_FOLDER_ID=1a2b3c4d5e6f7g8h9i0j

# Email (SMTP e.g. SendGrid / Gmail app password)
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@example.com
EMAIL_HOST_PASSWORD=your-app-password
DEFAULT_FROM_EMAIL=LearnPro <noreply@yourdomain.com>
```
Press `Ctrl + O`, `Enter` to save, and `Ctrl + X` to exit `nano`.

### Step 5: Run Migrations & Collect Static Files
In the Bash console:
```bash
cd ~/CRM
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py createsuperuser
```

### Step 6: Configure the PythonAnywhere Web Tab
1. Click the **Web** tab at the top of the PythonAnywhere dashboard.
2. Click **Add a new web app**.
3. Choose **Manual configuration** (NOT the automated "Django" option, since we already have a codebase and virtualenv).
4. Select **Python 3.11**.
5. Once created:
   - **Virtualenv section**: Enter the path:
     `/home/<yourusername>/.virtualenvs/crm-env`
   - **Code section**:
     - Source code: `/home/<yourusername>/CRM`
     - Working directory: `/home/<yourusername>/CRM`

### Step 7: Configure the WSGI Configuration File
In the **Web** tab, click on the **WSGI configuration file** link (typically `/var/www/<yourusername>_pythonanywhere_com_wsgi.py`).

Replace the file contents entirely with:
```python
import os
import sys
from pathlib import Path
from decouple import Config, RepositoryEnv

# 1. Project directory
path = '/home/<yourusername>/CRM'
if path not in sys.path:
    sys.path.insert(0, path)

# 2. Load .env file explicitly
env_path = Path(path) / '.env'
if env_path.exists():
    env_config = Config(RepositoryEnv(str(env_path)))
    for key, value in env_config.repository.data.items():
        os.environ.setdefault(key, value)

# 3. Set production settings module
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings.production'

# 4. Initialize WSGI application
from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
```
*(Replace `<yourusername>` with your actual PythonAnywhere username)*. Click **Save** in the top right.

### Step 8: Set Up Static & Media Mappings
Scroll down to the **Static files** section of the **Web** tab and add two entries:

| URL | Directory |
|---|---|
| `/static/` | `/home/<yourusername>/CRM/staticfiles` |
| `/media/` | `/home/<yourusername>/CRM/media` |

### Step 9: Reload Web App & Verify
1. Click the green **Reload <yourusername>.pythonanywhere.com** button at the top of the Web tab.
2. Visit `https://<yourusername>.pythonanywhere.com/`.
3. Log in to the Admin Dashboard at `https://<yourusername>.pythonanywhere.com/dashboard/admin/`.
4. If you encounter any issue, inspect the **Error log** link under the Web tab.

### Step 10: Scheduled Tasks on PythonAnywhere (Optional)
Since Celery workers require persistent background processes (available on paid plans), you can automate routine tasks on PythonAnywhere using the **Tasks** tab:
- Add a daily task at `02:00`:
  ```bash
  /home/<yourusername>/.virtualenvs/crm-env/bin/python /home/<yourusername>/CRM/manage.py clearsessions
  ```

---

## 2. Linux VPS Deployment (Ubuntu / Nginx / Gunicorn)

For full control, custom domains, automated Celery workers, and high traffic, deploy on an Ubuntu 22.04 / 24.04 LTS VPS (DigitalOcean, AWS EC2, Linode, Hetzner).

### Step 1: Server Provisioning & Packages
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-pip python3-venv python3-dev build-essential \
                    libpq-dev nginx curl git certbot python3-certbot-nginx redis-server
sudo systemctl enable redis-server
sudo systemctl start redis-server
```

### Step 2: User & Directory Setup
```bash
sudo adduser --disabled-password --gecos "" lms
sudo usermod -aG sudo lms
sudo su - lms

git clone https://github.com/<your-username>/<repo-name>.git /home/lms/CRM
cd /home/lms/CRM
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements/production.txt
```

### Step 3: Environment Setup
```bash
cp .env.example .env
nano .env
# Set DEBUG=False, ALLOWED_HOSTS, DATABASE_URL, REDIS_URL, etc.
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py createsuperuser
```

### Step 4: Gunicorn Systemd Service
Create `/etc/systemd/system/gunicorn.service`:
```ini
[Unit]
Description=Gunicorn daemon for LearnPro LMS
After=network.target

[Service]
User=lms
Group=www-data
WorkingDirectory=/home/lms/CRM
ExecStart=/home/lms/CRM/venv/bin/gunicorn \
          --access-logfile /home/lms/CRM/logs/gunicorn_access.log \
          --error-logfile /home/lms/CRM/logs/gunicorn_error.log \
          --workers 3 \
          --bind unix:/run/gunicorn.sock \
          config.wsgi:application

Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```
Enable and start Gunicorn:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now gunicorn
sudo systemctl status gunicorn
```

### Step 5: Celery Worker & Beat Services
Create `/etc/systemd/system/celery.service`:
```ini
[Unit]
Description=Celery Worker for LearnPro
After=network.target redis-server.service

[Service]
Type=forking
User=lms
Group=www-data
WorkingDirectory=/home/lms/CRM
ExecStart=/home/lms/CRM/venv/bin/celery -A config worker --loglevel=INFO --detach --pidfile=/run/celery.pid --logfile=/home/lms/CRM/logs/celery.log
Restart=always

[Install]
WantedBy=multi-user.target
```
Enable Celery:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now celery
```

### Step 6: Nginx Reverse Proxy Configuration
Create `/etc/nginx/sites-available/lms`:
```nginx
server {
    server_name yourdomain.com www.yourdomain.com;

    client_max_body_size 100M;

    location = /favicon.ico { access_log off; log_not_found off; }

    # Static files served directly by Nginx
    location /static/ {
        alias /home/lms/CRM/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, max-age=2592000";
    }

    # Media files
    location /media/ {
        alias /home/lms/CRM/media/;
        expires 7d;
    }

    # Proxy to Gunicorn
    location / {
        include proxy_params;
        proxy_pass http://unix:/run/gunicorn.sock;
    }
}
```
Enable the site and configure SSL:
```bash
sudo ln -s /etc/nginx/sites-available/lms /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx

# Install free Let's Encrypt SSL certificate
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com
```

---

## 3. Docker Compose Production Deployment

A complete containerized stack with Django, Gunicorn, PostgreSQL, Redis, Celery, and Nginx.

### Step 1: Create `.env` in Project Root
```bash
cp .env.example .env
# Fill in production values
```

### Step 2: Build & Start Containers
```bash
# Build and launch all services in background
docker compose -f docker-compose.yml up -d --build

# Run database migrations inside web container
docker compose exec web python manage.py migrate

# Collect static files
docker compose exec web python manage.py collectstatic --noinput

# Create admin user
docker compose exec web python manage.py createsuperuser
```

### Step 3: Monitor Logs & Manage
```bash
# Check service logs
docker compose logs -f web

# Restart stack
docker compose restart
```

---

## 4. Storage Configuration (Google Drive / S3)

LearnPro supports swappable backend storage via the `STORAGE_BACKEND` setting.

### Setting Up Google Drive Storage (`STORAGE_BACKEND=gdrive`)
1. Go to [Google Cloud Console](https://console.cloud.google.com/).
2. Create a project and enable the **Google Drive API**.
3. Create a **Service Account** under **IAM & Admin > Service Accounts**.
4. Create and download a **JSON Key** for the service account.
5. In Google Drive, create a folder (e.g. `LearnPro_Uploads`). Share this folder with the service account email (giving **Editor** permissions).
6. Copy the Folder ID from the URL (`https://drive.google.com/drive/folders/<FOLDER_ID>`).
7. In your `.env`:
   ```ini
   STORAGE_BACKEND=gdrive
   GDRIVE_SERVICE_ACCOUNT_JSON_PATH=/path/to/service_account.json
   # Or paste the entire JSON string directly:
   # GDRIVE_SERVICE_ACCOUNT_JSON={"type": "service_account", ...}
   GDRIVE_ROOT_FOLDER_ID=1a2b3c4d5e6f7g8h9i0j
   ```

### Setting Up AWS S3 / MinIO (`STORAGE_BACKEND=s3` or `minio`)
```ini
STORAGE_BACKEND=s3
AWS_ACCESS_KEY_ID=your-aws-access-key
AWS_SECRET_ACCESS_KEY=your-aws-secret-key
AWS_STORAGE_BUCKET_NAME=your-bucket-name
AWS_S3_REGION_NAME=us-east-1
```

---

## 5. Database Engine Configuration

### Multi-Database Support (PostgreSQL / MongoDB)
- **Django Auth, Sessions, Orders, and Admin** are always stored in your relational database (`db.sqlite3` or PostgreSQL).
- **Course catalogs and progress data** can seamlessly synchronize to MongoDB when `DATABASE_ENGINE=mongodb` is set:

```ini
DATABASE_ENGINE=mongodb
MONGODB_URI=mongodb+srv://<username>:<password>@cluster0.abcde.mongodb.net/?retryWrites=true&w=majority
MONGODB_DATABASE=learnpro_crm
```

To run initial synchronizations:
```bash
python manage.py verify_arch
```

---

## 6. Pre-Flight Security Checklist

Before directing real traffic to your production deployment, verify all items below:

- [ ] `DEBUG=False` in `.env`
- [ ] `SECRET_KEY` is set to a secure, randomly generated 50+ character string
- [ ] `ALLOWED_HOSTS` only contains your actual domain names / subdomains
- [ ] `CSRF_TRUSTED_ORIGINS` includes `https://yourdomain.com`
- [ ] HTTPS / SSL is active and redirects HTTP requests (`SECURE_SSL_REDIRECT=True`)
- [ ] `python manage.py check --deploy` passes without critical warnings
- [ ] `python manage.py migrate` has run all pending migrations
- [ ] Automated daily database backup is configured
- [ ] Default admin credentials have been changed
- [ ] Google Drive / S3 storage credentials are valid and tested

---

*For further assistance or issue reports, check server logs in `logs/` or run `pytest` to verify system health.*
