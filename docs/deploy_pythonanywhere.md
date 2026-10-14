# Deploying PPR on PythonAnywhere (MySQL)

The examples use the account name `yourusername`. Replace it everywhere.

## 1. Before you deploy (on your PC)

```powershell
.venv\Scripts\python manage.py tailwind build      # theme/static/css/dist/styles.css
.venv\Scripts\python scripts\i18n.py compile        # locale/ar/LC_MESSAGES/django.mo
.venv\Scripts\python -m pytest
git add -A; git commit -m "Release"; git push
```

The built CSS and the compiled `.mo` file are committed, so the server needs neither Node.js nor gettext.

## 2. Code and virtualenv (Bash console on PythonAnywhere)

```bash
git clone https://github.com/<you>/ppr.git ~/ppr
cd ~/ppr
mkvirtualenv --python=python3.12 ppr
pip install -r requirements/production.txt
```

## 3. MySQL database

In the **Databases** tab, set a MySQL password and create a database called `ppr`.
Its full name will be `yourusername$ppr`, on host `yourusername.mysql.pythonanywhere-services.com`.

## 4. Environment file

Create `~/ppr/.env`:

```ini
SECRET_KEY=<a long random string>
ALLOWED_HOSTS=yourusername.pythonanywhere.com
DB_NAME=yourusername$ppr
DB_USER=yourusername
DB_PASSWORD=<your MySQL password>
DB_HOST=yourusername.mysql.pythonanywhere-services.com
MEDIA_ROOT=/home/yourusername/ppr_private_media
# Email (optional)
EMAIL_HOST=smtp.example.com
EMAIL_HOST_USER=...
EMAIL_HOST_PASSWORD=...
DEFAULT_FROM_EMAIL=PPR <no-reply@example.com>
```

Generate a secret key with `python -c "import secrets; print(secrets.token_urlsafe(50))"`.

## 5. Migrate and collect static files

```bash
cd ~/ppr
export DJANGO_SETTINGS_MODULE=config.settings.production
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py createsuperuser
python manage.py check --deploy
```

`check --deploy` will warn about HSTS subdomains and preload. That is expected on a shared `pythonanywhere.com`
subdomain. Use a custom domain if you need them.

## 6. Web app

In the **Web** tab, add a new web app → *Manual configuration* → Python 3.12.

* **Virtualenv:** `/home/yourusername/.virtualenvs/ppr`
* **Source code:** `/home/yourusername/ppr`
* **WSGI file**: replace its contents with:

```python
import os
import sys

path = "/home/yourusername/ppr"
if path not in sys.path:
    sys.path.insert(0, path)

os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.production"

from django.core.wsgi import get_wsgi_application  # noqa: E402

application = get_wsgi_application()
```

* **Static files:** URL `/static/` → directory `/home/yourusername/ppr/staticfiles`
* **Do not** add a mapping for media. Dossiers are private and are served only through permission-checked views.
* Turn on **Force HTTPS**, then click **Reload**.

## 7. Limits and validation on PythonAnywhere

* Validation runs synchronously during the upload/submit request. Keep `ECTD_MAX_UPLOAD_MB` within your plan's
  request limits. For large dossiers, upgrade the plan or run `python manage.py validate_sequence <id>`
  from a scheduled task.
* Uploaded zips and extracted accepted sequences live under `MEDIA_ROOT`. Watch your disk quota.

## Updating

```bash
cd ~/ppr && git pull
workon ppr
pip install -r requirements/production.txt
export DJANGO_SETTINGS_MODULE=config.settings.production
python manage.py migrate
python manage.py collectstatic --noinput
```

Then click **Reload** in the Web tab.
