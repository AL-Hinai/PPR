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

## 7. Validation worker (always-on task)

In production (`VALIDATION_MODE=queue`, the default in `config/settings/production.py`) a submit only queues
the validation; a background worker validates the sequence, moves the workflow and extracts the dossier text.
Without the worker, submissions stay "Validation in progress".

On the **Tasks** tab, create an **always-on task** with this command:

```bash
cd ~/ppr && DJANGO_SETTINGS_MODULE=config.settings.production ~/.virtualenvs/ppr/bin/python manage.py run_validation_worker
```

* The task log shows `Validation worker started`, then one line whenever jobs run.
* A job that crashes is retried up to 3 times; after that it is marked failed and the HOD and administrators are
  notified. A job whose worker stopped mid-run is retried after 30 minutes. Jobs are in Django admin
  (*Validation jobs*).
* Restart the task after every update (it keeps running the old code otherwise).
* If always-on tasks are not available, a scheduled task running `manage.py run_validation_worker --once`
  every hour works, with slower results. `VALIDATION_MODE=sync` validates during the request instead, which
  only suits small dossiers.

## 8. Limits on PythonAnywhere

* Upload size: the upload itself still goes through a web request. Test the largest expected dossier on your
  plan and keep `ECTD_MAX_UPLOAD_MB` below what succeeds; the default is 500.
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

Then click **Reload** in the Web tab and restart the validation worker task.
