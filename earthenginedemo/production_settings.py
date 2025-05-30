from .settings import *

# Security settings
DEBUG = False
# Change this to a secure random string
SECRET_KEY = "django-insecure-w6&eotxq2uehi(@z922^l54-ic80@$a@fbaqf00ws81u=+0)y$"

# Set your domain name
ALLOWED_HOSTS = ['zix035.pythonanywhere.com']

# Static files configuration
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATIC_URL = '/static/'

# HTTPS settings
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
