# Destrox

Aplicación web simple para gestionar la venta de cuentas de plataformas de streaming con panel de clientes y administradores.

## Requisitos

- Python 3.10+
- pip

## Instalación

```bash
python -m venv .venv
source .venv/bin/activate  # En Windows usa .venv\\Scripts\\activate
pip install -r requirements.txt
```

## Configuración

Las variables de entorno disponibles son:

- `SECRET_KEY`: clave para las sesiones de Flask.
- `DATABASE_URL`: ruta alternativa para la base de datos (por defecto `sqlite:///app.db`).
- `ADMIN_PASSWORD`: contraseña del panel de administrador (por defecto `admin123`).
- `SUBSCRIPTION_DAYS`: días que dura una cuenta asignada (por defecto `30`).
- `PAYMENT_QR_URL`: URL de la imagen QR que se muestra a los clientes.
- `PAYMENT_INSTRUCTIONS`: texto que aparece junto a los datos de pago.
- `PAYMENT_ACCOUNTS`: lista (separada por saltos de línea) de cuentas bancarias o números de pago.
- `ADMIN_NOTIFICATION_EMAIL`: correo que recibirá las notificaciones de nuevos pedidos.
- `SMTP_SERVER`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`: datos para el envío de correos.
- `SUPPORT_WHATSAPP`: número de WhatsApp para el botón flotante (por defecto `51987654321`).

## Uso

1. Inicializa la base de datos ejecutando la aplicación por primera vez.
2. Ingresa al panel de administrador (`/admin/login`) con la contraseña configurada.
3. Carga tus cuentas en el almacén y gestiona los pedidos desde el panel.

Ejecuta el servidor de desarrollo con:

```bash
flask --app app run --debug
```

## Licencia

MIT
