# ControlPS
Aplicación con interfaz gráfica en tiempo real desarrollada en Python utilizando Qt (PySide) para monitorear y gestionar el estado de batería de controles PlayStation.

# Características
* Soporte para múltiples controles simultáneamente.
* Configuración independiente de alertas para cada control.
* Notificación sonora al conectar o desconectar un control.
* Configuración mediante deslizadores (sliders) del porcentaje mínimo para activar una alerta sonora de batería baja.
* Configuración mediante deslizadores (sliders) del porcentaje máximo para activar una alerta sonora de batería alta.
* Visualización del nombre completo del control conectado.
* Monitoreo en tiempo real del estado de carga de la batería.
* Visualización del porcentaje actual de batería.
* Integración con la bandeja del sistema (system tray) mediante un icono de batería.
* Posibilidad de mostrar u ocultar la ventana principal:
- Desde el menú contextual del icono de la bandeja del sistema.
- Con clic izquierdo o derecho sobre el icono.
- Mediante doble clic izquierdo sobre el icono.

# Funcionalidad
La aplicación permanece ejecutándose en segundo plano y permite supervisar el nivel de batería del control en tiempo real, notificando al usuario mediante alertas sonoras cuando se alcanzan los umbrales configurados.
