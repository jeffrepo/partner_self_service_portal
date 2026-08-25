# Partner Self-Service Portal para Odoo 18

`partner_self_service_portal` amplía el portal estándar de Odoo para que los usuarios externos trabajen con la información de su compañía cliente y con el inventario de un almacén asignado.

## Funcionalidad

- Permite clasificar cada contacto con acceso al portal como usuario **Proyecto**
  o **Oficina**.
- El usuario Proyecto solo ve solicitudes de compra: puede crearlas, editar sus
  propios borradores y consultar si Oficina ya las confirmó, pero no puede
  confirmarlas ni acceder a ventas, facturas, pagos o inventario.
- El usuario Oficina conserva el portal completo y puede autorizar solicitudes.
- Muestra el logo y nombre de la compañía cliente en el portal.
- Conserva las páginas estándar de órdenes de venta y facturas de Odoo para
  usuarios Oficina.
- Muestra el estado del documento FEL en la lista y en el detalle de la factura.
  Cuando `infilefel` completa `fel_documento_certificado` con una URL HTTPS de
  Feel, permite abrirla; si está vacío, informa que la factura aún no ha sido
  certificada.
- Muestra la serie y el número FEL en la lista de facturas.
- Muestra los pagos de cliente en estado **En proceso** o **Pagado**.
- Muestra en tiempo real el inventario libre del almacén asignado: existencia física menos cantidades reservadas.
- Permite crear y editar solicitudes de compra con correlativo `SPR/AÑO/#####`.
- Usa el campo **Proyecto** en la solicitud y permite descargarla en PDF.
- Conserva la cantidad original de cada línea y muestra **Pendiente** como la
  diferencia positiva entre la cantidad original y la cantidad actual.
- Solo permite solicitar productos almacenables, vendibles y con inventario libre.
- Al confirmar una solicitud:
  - solicita la clave personal del contacto que inició sesión;
  - permite escribir una nota de autorización que solo se registra en la orden de
    venta cuando la clave es correcta y la confirmación finaliza correctamente;
  - vuelve a validar el inventario;
  - crea una orden de venta para la compañía cliente;
  - asigna el almacén de la compañía cliente;
  - confirma la orden de venta;
  - genera, reserva y valida automáticamente las operaciones de salida según la
    configuración nativa del almacén;
  - notifica por correo y actividad a los usuarios internos configurados.
- Muestra Proyecto, Solicitado por y Autorizado por en las órdenes de venta creadas
  por una solicitud del portal.
- Añade el botón **Pagar** en las órdenes confirmadas del portal.
- En la lista de órdenes permite seleccionar varias ventas y enviar un único
  comprobante para todas ellas, antes de facturar.
- Permite imprimir un estado de cuenta PDF que contiene únicamente las órdenes
  seleccionadas.
- El botón acepta JPG, PNG, WEBP o PDF de hasta 10 MB y registra un comprobante separado.
- El comprobante **no crea un `account.payment`**. Se adjunta al chatter de la orden y
  también al correo enviado a los usuarios internos configurados.

## Instalación

1. Copia este repositorio en una ruta incluida en `addons_path`.
2. Actualiza la lista de aplicaciones.
3. Instala **Partner Self-Service Portal**.

Dependencias instaladas automáticamente: `account`, `infilefel`, `portal`,
`sale_management`, `sale_stock` y `website`.

## Configuración

### 1. Compañía y almacén del cliente

1. Abre **Contactos**.
2. Crea o abre el contacto padre de tipo **Compañía**.
3. En **Almacén del portal**, selecciona el almacén correspondiente.
4. Los usuarios externos deben estar asociados a contactos hijos de esa compañía.

El campo del almacén solo es visible para administradores de Inventario.

### 2. Usuarios internos a notificar

1. Ve a **Contabilidad/Facturación → Configuración → Ajustes**.
2. En **Pagos de clientes**, localiza **Notificaciones del portal de clientes**.
3. Selecciona uno o varios usuarios internos.

La configuración es independiente por compañía de Odoo.
Odoo debe tener un servidor de correo saliente operativo; los mensajes se crean en la cola
de correo estándar para conservar la trazabilidad y los reintentos normales del sistema.

### 3. Usuario del portal

1. Abre el contacto hijo de la compañía cliente.
2. Concédele acceso al portal mediante la función estándar de Odoo.
3. Verifica que el contacto mantenga como padre la compañía que tiene el almacén asignado.
4. Selecciona **Tipo de usuario del portal**:
   - **Proyecto** para crear y consultar solicitudes sin autorizarlas.
   - **Oficina** para el acceso completo y la autorización de solicitudes.
5. Para un usuario Oficina, pulsa **Configurar clave del portal** e ingresa una
   clave de al menos 6 caracteres.

La clave pertenece al contacto, no a la compañía. Se almacena como un hash PBKDF2 y
no puede recuperarse ni mostrarse; si se olvida, un usuario interno debe reemplazarla.
Después de cinco intentos incorrectos queda bloqueada durante 15 minutos.

### 4. Serie y número FEL

La lista detecta los campos FEL de `infilefel` por sus nombres técnicos habituales y
por su descripción. Si una instalación personalizada usa nombres diferentes, se pueden
agregar en las listas `_PORTAL_FEL_SERIES_FIELDS` y `_PORTAL_FEL_NUMBER_FIELDS` de
`models/account_move.py`.

## Flujo de inventario

La confirmación de la solicitud crea y confirma la orden de venta con su `warehouse_id`.
Después, el módulo reserva y valida automáticamente cada transferencia de la cadena
definida por el almacén, incluyendo flujos de una, dos o tres etapas.

La operación completa es transaccional. Si una transferencia requiere intervención
manual —por ejemplo, por inventario no reservable o una ruta
bloqueada— Odoo muestra el error y la solicitud permanece en borrador. No queda una
orden de venta parcialmente procesada.

Al quedar las transferencias en estado **Hecho**, el inventario físico del almacén se
reduce inmediatamente.

## Seguridad

- Las rutas del portal requieren un usuario autenticado.
- Cada consulta y escritura comprueba el `commercial_partner_id` del usuario.
- Los controladores con `sudo()` siempre aplican primero un dominio explícito por compañía cliente.
- Las solicitudes y los comprobantes también tienen reglas de registro para el grupo Portal.
- Las reglas de registro impiden que un usuario Proyecto lea órdenes de venta,
  líneas de venta, facturas, líneas de factura o comprobantes aunque intente entrar
  por una URL directa.
- Los archivos se validan por contenido, tipo MIME y tamaño.
- Todas las operaciones `POST` conservan la protección CSRF de Odoo.
- La confirmación del portal exige la clave personal del contacto, limita intentos y
  bloquea temporalmente los ataques repetidos.
- Los comprobantes no se publican ni se exponen mediante una ruta pública de descarga.

## Alcance contable

La página **Pagos registrados** lista pagos entrantes de cliente (`account.payment`) que estén en proceso o pagados. El comprobante enviado con **Pagar** es únicamente una notificación documental: un usuario interno debe revisar y registrar o conciliar el pago mediante el flujo normal de Contabilidad.

## Pruebas

El addon incluye pruebas de modelo para:

- creación y confirmación de solicitudes;
- asignación correcta del almacén a la orden de venta;
- rechazo por inventario insuficiente;
- aislamiento de solicitudes entre compañías cliente;
- registro de comprobantes sin crear pagos contables;
- protección, hash y bloqueo temporal de la clave de confirmación;
- comprobantes asociados a varias órdenes de venta;
- visibilidad restringida de ventas y facturas para usuarios Proyecto.

Para ejecutarlas en una instalación de Odoo 18:

```bash
odoo-bin -d <base_de_pruebas> \
  -i partner_self_service_portal \
  --test-enable \
  --test-tags /partner_self_service_portal \
  --stop-after-init
```
