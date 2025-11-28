# Email System Module

Sistema completo de envío de correos electrónicos con soporte SMTP, templates Jinja2 y logging en base de datos.

## Características

- ✅ **Cliente SMTP configurable** - Soporte para TLS/SSL
- ✅ **Templates Jinja2** - Versiones TXT y HTML
- ✅ **Almacenamiento en DB** - Templates y logs persistentes
- ✅ **Logging automático** - Tracking de todos los correos enviados
- ✅ **CLI integrado** - Comandos para gestión completa

## Configuración

### Variables de entorno (.env)

```env
# SMTP Configuration
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-password-here
SMTP_FROM_EMAIL=your-email@gmail.com
SMTP_FROM_NAME=News Portal
SMTP_USE_TLS=True
SMTP_USE_SSL=False
SMTP_TIMEOUT=30

# Templates Directory
EMAIL_TEMPLATES_DIR=src/email_system/templates
```

### Gmail Setup

Para usar Gmail, necesitas crear una "App Password":
1. Ir a Google Account → Security
2. Habilitar 2-Step Verification
3. Ir a "App passwords"
4. Crear password para "Mail"
5. Usar ese password en `SMTP_PASSWORD`

## Uso desde CLI

### Comandos disponibles

```bash
# Ver ayuda
uv run news email --help

# Probar conexión SMTP
uv run news email test

# Listar templates disponibles
uv run news email list-templates

# Enviar email simple
uv run news email send -r user@example.com -s "Test" -m "Hello World"

# Enviar email HTML
uv run news email send -r user@example.com -s "Test" -m "<h1>Hello</h1>" --html

# Enviar con template de archivo
uv run news email send-template -t test -r user@example.com -s "Welcome" \\
    -v title="Hello" -v message="Welcome to our platform" -v name="John"

# Ver logs de envío
uv run news email logs
uv run news email logs --status failed
uv run news email logs --recipient user@example.com

# Crear template en base de datos
uv run news email create-template -n welcome_email -s "Welcome!" -t html \\
    -f src/email_system/templates/test.html.jinja -d "Welcome email template"
```

## Uso desde Python

### Enviar email simple

```python
from email_system.service import EmailService

service = EmailService()

# Enviar texto plano
service.send_email(
    to="user@example.com",
    subject="Test Email",
    text_content="Hello World!"
)

# Enviar HTML + texto
service.send_email(
    to="user@example.com",
    subject="Newsletter",
    html_content="<h1>Hello</h1><p>Welcome!</p>",
    text_content="Hello\n\nWelcome!"
)
```

### Enviar con template de archivo

```python
from email_system.service import EmailService
from datetime import datetime

service = EmailService()

# Template: test.html.jinja + test.txt.jinja
service.send_with_file_template(
    template_name='test',
    recipient='user@example.com',
    subject='Welcome!',
    context={
        'title': 'Welcome to News Portal',
        'message': 'Thanks for signing up!',
        'name': 'John Doe',
        'button_text': 'Get Started',
        'button_url': 'https://example.com/start',
        'current_year': datetime.now().year
    }
)
```

### Enviar newsletter con artículos

```python
from email_system.service import EmailService
from db import Database
from db.models import Article
from datetime import datetime

db = Database()
session = db.get_session()

try:
    # Obtener artículos recientes
    articles = session.query(Article)\\
        .order_by(Article.published_date.desc())\\
        .limit(5)\\
        .all()

    # Preparar contexto
    context = {
        'subscriber_name': 'John Doe',
        'date': datetime.now(),
        'articles': [
            {
                'title': article.title,
                'subtitle': article.subtitle,
                'source': article.source.name,
                'published_date': article.published_date,
                'url': article.url,
                'summary': article.content[:200]
            }
            for article in articles
        ],
        'unsubscribe_url': 'https://example.com/unsubscribe',
        'current_year': datetime.now().year
    }

    # Enviar newsletter
    service = EmailService()
    log = service.send_with_file_template(
        template_name='newsletter',
        recipient='user@example.com',
        subject='Daily Newsletter',
        context=context
    )

    print(f"Newsletter sent! Log ID: {log.id}")

finally:
    session.close()
```

### Enviar con template de base de datos

```python
from email_system.service import EmailService

service = EmailService()

# Template almacenado en DB (EmailTemplate)
service.send_with_db_template(
    template_name='flash_news_alert',
    recipient='user@example.com',
    context={
        'news_title': 'Breaking News',
        'news_content': 'Important update...',
        'news_url': 'https://example.com/news/123'
    }
)
```

## Estructura de Templates

### Template de archivo (Jinja2)

Los templates se guardan en `src/email_system/templates/` con extensión `.jinja`:

**test.html.jinja** (versión HTML):
```html
<!DOCTYPE html>
<html>
<head>
    <title>{{ title }}</title>
</head>
<body>
    <h1>{{ title }}</h1>
    <p>Hola {{ name }},</p>
    <p>{{ message }}</p>
    {% if button_text and button_url %}
    <a href="{{ button_url }}">{{ button_text }}</a>
    {% endif %}
</body>
</html>
```

**test.txt.jinja** (versión texto):
```text
{{ title }}
================

Hola {{ name }},

{{ message }}

{% if button_text and button_url %}
{{ button_text }}: {{ button_url }}
{% endif %}
```

### Variables disponibles

Templates incluyen filtros personalizados:

- `{{ date|datetimeformat('%d/%m/%Y') }}` - Formateo de fechas
- Variables comunes: `current_year`, `sender_name`, etc.

## Arquitectura

```
src/email_system/
├── __init__.py
├── client.py          # EmailClient - Cliente SMTP
├── renderer.py        # EmailRenderer - Renderizado Jinja2
├── service.py         # EmailService - Lógica de negocio
└── templates/         # Templates Jinja2
    ├── test.html.jinja
    ├── test.txt.jinja
    ├── newsletter.html.jinja
    └── newsletter.txt.jinja
```

### Clases principales

#### EmailClient
Cliente SMTP para envío de correos.

```python
from email_system.client import EmailClient

client = EmailClient()  # Usa configuración de settings.py
client.send_email(
    to="user@example.com",
    subject="Test",
    html_content="<h1>Hello</h1>"
)
```

#### EmailRenderer
Renderizador de templates Jinja2.

```python
from email_system.renderer import EmailRenderer

renderer = EmailRenderer()

# Desde archivo
html = renderer.render_file('test.html.jinja', {'name': 'John'})

# Desde string
html = renderer.render_string('<h1>Hello {{ name }}</h1>', {'name': 'John'})

# Desde base de datos
result = renderer.render_from_db('welcome_email', {'name': 'John'})
# result = {'subject': '...', 'html': '...', 'text': '...'}
```

#### EmailService
Servicio de alto nivel que integra cliente, renderer y logging.

```python
from email_system.service import EmailService

service = EmailService()

# Todas las operaciones incluyen logging automático
log = service.send_email(...)
print(f"Email sent! Status: {log.status.value}")
```

## Base de Datos

### Modelos

**EmailTemplate** - Templates almacenados en DB:
- `name`: Nombre único del template
- `subject`: Asunto del correo
- `template_type`: `EmailTemplateType.HTML` o `EmailTemplateType.TXT`
- `content`: Contenido Jinja2
- `description`: Descripción opcional

**EmailLog** - Logs de correos enviados:
- `recipient`: Destinatario
- `subject`: Asunto
- `status`: `EmailStatus.PENDING|SENT|FAILED`
- `template_id`: FK a EmailTemplate (opcional)
- `context_data`: Variables usadas (JSON)
- `sent_at`: Timestamp de envío
- `error_message`: Error si falló

### Queries útiles

```python
from db import Database
from db.models import EmailLog, EmailStatus

db = Database()
session = db.get_session()

# Correos fallidos recientes
failed = session.query(EmailLog)\\
    .filter(EmailLog.status == EmailStatus.FAILED)\\
    .order_by(EmailLog.created_at.desc())\\
    .limit(10)\\
    .all()

# Estadísticas de envío
from sqlalchemy import func

stats = session.query(
    EmailLog.status,
    func.count(EmailLog.id)
).group_by(EmailLog.status).all()
```

## Patrones y Buenas Prácticas

### 1. Siempre enviar TXT + HTML

Los clientes de correo varían, siempre enviar ambas versiones:

```python
service.send_with_file_template(
    template_name='newsletter',  # Busca newsletter.html.jinja y newsletter.txt.jinja
    ...
)
```

### 2. Validar contexto de templates

Asegurarse de que todas las variables requeridas estén presentes:

```python
context = {
    'name': user.name or 'Usuario',  # Fallback si falta
    'current_year': datetime.now().year
}
```

### 3. Manejar errores gracefully

```python
try:
    log = service.send_email(...)
    if log.status == EmailStatus.SENT:
        print("✓ Email sent")
    else:
        print(f"✗ Failed: {log.error_message}")
except EmailServiceError as e:
    print(f"Error: {e}")
```

### 4. Testing sin envío real

Para testing, configurar SMTP a un servidor local o usar print:

```python
# En desarrollo, ver templates sin enviar
renderer = EmailRenderer()
html = renderer.render_file('test.html.jinja', context)
print(html)  # Revisar output
```

### 5. Rate limiting

Para envío masivo, implementar delays:

```python
import time

for user in users:
    service.send_email(...)
    time.sleep(0.5)  # Evitar rate limits
```

## Troubleshooting

### Error: "SMTP authentication failed"
- Verificar `SMTP_USERNAME` y `SMTP_PASSWORD`
- Gmail: Usar "App Password", no password normal
- Verificar que 2FA esté habilitado en Gmail

### Error: "Template not found"
- Verificar que el archivo exista en `EMAIL_TEMPLATES_DIR`
- Verificar extensión `.jinja`
- Usar `list-templates` para ver disponibles

### Emails no llegan
- Verificar spam folder
- Verificar `SMTP_FROM_EMAIL` esté verificado en el servidor
- Probar conexión con `uv run news email test`

### Rendering errors
- Verificar sintaxis Jinja2
- Verificar que todas las variables estén en contexto
- Usar `{{ variable|default('fallback') }}` para opcionales
