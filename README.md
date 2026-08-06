# Partner Self-Service Portal para Odoo 18

`partner_self_service_portal` amplía el portal estándar de Odoo para que los usuarios externos trabajen con la información de su compañía cliente y con el inventario de un almacén asignado.

## Funcionalidad

- Conserva las páginas estándar de órdenes de venta y facturas de Odoo.
- Muestra **Ver documento FEL** en la factura del portal cuando `infilefel` ha
  completado `fel_documento_certificado` con una URL HTTPS de Feel.
- Muestra los pagos de cliente en estado **En proceso** o **Pagado**.
- Muestra en tiempo real el inventario libre del almacén asignado: existencia física menos cantidades reservadas.
- Permite crear y editar solicitudes de compra con correlativo `SPR/AÑO/#####`.
- Solo permite solicitar productos almacenables, vendibles y con inventario libre.
- Al confirmar una solicitud:
  - vuelve a validar el inventario;
  - crea una orden de venta para la compañía cliente;
  - asigna el almacén de la compañía cliente;
  - confirma la orden de venta;
  - genera, reserva y valida automáticamente las operaciones de salida según la
    configuración nativa del almacén;
  - notifica por correo y actividad a los usuarios internos configurados.
- Añade el botón **Pagar** en las órdenes confirmadas del portal.
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

## Flujo de inventario

La confirmación de la solicitud crea y confirma la orden de venta con su `warehouse_id`.
Después, el módulo reserva y valida automáticamente cada transferencia de la cadena
definida por el almacén, incluyendo flujos de una, dos o tres etapas.

La operación completa es transaccional. Si una transferencia requiere intervención
manual —por ejemplo, por inventario no reservable, lotes/series incompletos o una ruta
bloqueada— Odoo muestra el error y la solicitud permanece en borrador. No queda una
orden de venta parcialmente procesada.

Al quedar las transferencias en estado **Hecho**, el inventario físico del almacén se
reduce inmediatamente.

## Seguridad

- Las rutas del portal requieren un usuario autenticado.
- Cada consulta y escritura comprueba el `commercial_partner_id` del usuario.
- Los controladores con `sudo()` siempre aplican primero un dominio explícito por compañía cliente.
- Las solicitudes y los comprobantes también tienen reglas de registro para el grupo Portal.
- Los archivos se validan por contenido, tipo MIME y tamaño.
- Todas las operaciones `POST` conservan la protección CSRF de Odoo.
- Los comprobantes no se publican ni se exponen mediante una ruta pública de descarga.

## Alcance contable

La página **Pagos registrados** lista pagos entrantes de cliente (`account.payment`) que estén en proceso o pagados. El comprobante enviado con **Pagar** es únicamente una notificación documental: un usuario interno debe revisar y registrar o conciliar el pago mediante el flujo normal de Contabilidad.

## Pruebas

El addon incluye pruebas de modelo para:

- creación y confirmación de solicitudes;
- asignación correcta del almacén a la orden de venta;
- rechazo por inventario insuficiente;
- aislamiento de solicitudes entre compañías cliente;
- registro de comprobantes sin crear pagos contables.

Para ejecutarlas en una instalación de Odoo 18:

```bash
odoo-bin -d <base_de_pruebas> \
  -i partner_self_service_portal \
  --test-enable \
  --test-tags /partner_self_service_portal \
  --stop-after-init
```
