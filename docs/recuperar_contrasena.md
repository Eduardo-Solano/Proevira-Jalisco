# Recuperar contraseña con un código por correo

El login incluye **¿Olvidaste tu contraseña?**. El flujo tiene tres pasos:

1. Escribir el correo de la cuenta y solicitar un código.
2. Escribir en la web el código de seis dígitos recibido por correo.
3. Elegir y confirmar una contraseña nueva; regresar al login.

El correo ya no incluye enlaces. Puede abrirse desde otro dispositivo: el usuario
copia el código en la web donde inició la recuperación. No se necesita
`PASSWORD_RESET_WEB_URL`. Los enlaces de correos antiguos abren la solicitud de código.

## Configuración

Configurar en `.env` del backend, nunca en `.env.example` con credenciales reales:

- `SMTP_HOST`, `SMTP_PORT`, `SMTP_FROM_EMAIL`: servidor y remitente autorizado.
- `SMTP_USERNAME`, `SMTP_PASSWORD`: credenciales SMTP del proveedor.
- Puerto 587: `SMTP_STARTTLS=true`, `SMTP_USE_SSL=false`.
- Puerto 465: `SMTP_USE_SSL=true`, `SMTP_STARTTLS=false`.
- `PASSWORD_RESET_CODE_EXPIRE_MINUTES=10`: vigencia del código.
- `PASSWORD_RESET_COOLDOWN_SECONDS=60`: espera entre envíos, mínimo un minuto.

Reiniciar el backend para cargar la configuración y crear la tabla
`password_recovery_codes`. Las contraseñas existentes no se modifican.
Las antiguas variables `PASSWORD_RESET_WEB_URL` y `PASSWORD_RESET_EXPIRE_MINUTES`
ya no se utilizan; pueden eliminarse de `.env`.

## API y comportamiento

- `POST /api/v1/auth/forgot-password`: `{"email": "usuario@example.com"}`.
  Confirma «Código de recuperación enviado» con respuesta uniforme para cuentas
  existentes, desconocidas y solicitudes durante la espera. El correo se procesa
  después de responder: la aceptación no garantiza entrega del proveedor SMTP.
- `POST /api/v1/auth/verify-recovery-code`: `{"email": "usuario@example.com", "code": "012345"}`.
  Permite hasta cinco intentos por código. Devuelve un permiso aleatorio de cambio
  de contraseña, conservado internamente en la sesión de la web, con vigencia de cinco minutos.
- `POST /api/v1/auth/reset-password`: `{"token": "permiso-temporal", "password": "contraseña-nueva"}`.
  Exige al menos ocho caracteres y un máximo de 72 bytes UTF-8 por el límite de bcrypt.

El código se almacena con HMAC ligado al usuario y a la clave secreta del servidor.
Los intentos se cuentan de forma atómica, incluso con solicitudes simultáneas.
Al validarlo queda inutilizado. Un reenvío después de la espera reemplaza el código
anterior y anula permisos de cambio anteriores. Antes de la espera se conserva el
código anterior. Ni los códigos ni los permisos sirven como JWT de acceso.

Se mantiene la configuración SMTP existente. Ante fallos se registra un mensaje sin
credenciales, correos ni códigos. El cambio afecta contraseñas locales, no Firebase;
los JWT emitidos en otras sesiones conservan su vigencia configurada.

## Validación

```bash
python -m unittest tests.test_password_recovery tests.test_web_password_recovery tests.test_web_errors tests.test_web_views
```

Las pruebas sustituyen SMTP y no envían correos reales. Incluyen códigos vencidos,
intentos agotados, reenvío, reutilización y login con la nueva contraseña.
