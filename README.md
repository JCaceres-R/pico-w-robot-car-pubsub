# 🤖 Robot Car Control System - Raspberry Pi Pico W

Sistema de control remoto para carro robótico con brazo mecánico mediante arquitectura Pub/Sub sobre TCP/IP. Implementa cinemática diferencial para movimientos suaves y control preciso de servomotores.

## 📋 Características

- ✅ **Control diferencial de motores DC** con velocidades lineales y angulares
- ✅ **Control de brazo robótico** de 3 grados de libertad (base, hombro, codo)
- ✅ **Arquitectura Pub/Sub** mediante TCP/IP
- ✅ **Ejecución de secuencias** predefinidas de movimientos
- ✅ **Conexión WiFi robusta** con diagnóstico de redes
- ✅ **Sistema multi-capa** (Hardware, Intérprete, Cliente)

## 🛠️ Hardware Requerido

- **Microcontrolador**: Raspberry Pi Pico W
- **Motores DC**: 2 motores para tracción diferencial
- **Servomotores**: 3 servos (base, hombro, codo)
- **Driver de motores**: L298N o similar
- **Fuente de alimentación**: 5-12V para motores

### Conexiones de Pines

#### Motores DC
- **Motor Izquierdo**: GP20 (adelante), GP21 (atrás)
- **Motor Derecho**: GP18 (atrás), GP19 (adelante)

#### Servomotores
- **Base**: GP6
- **Hombro**: GP5
- **Codo**: GP7

## 📦 Instalación

1. **Instalar MicroPython en Raspberry Pi Pico W**
   - Descarga el firmware desde [micropython.org](https://micropython.org/download/rp2-pico-w/)
   - Flashea el firmware usando Thonny o rshell

2. **Configurar WiFi**
   ```python
   # Edita estas líneas en el código:
   ip_local = connect_wifi("TU_SSID", "TU_PASSWORD")
   ```

3. **Configurar IP del Broker**
   ```python
   # Línea 372 - Cambia a la IP de tu servidor:
   cliente = ClienteCarro("192.168.1.101", 5051, interprete)
   ```

4. **Subir el código**
   - Copia el archivo `main.py` a la Pico W usando Thonny
   - El código se ejecutará automáticamente al encender

## 🚀 Uso

### Formato de Mensajes JSON

#### Comando de Estado Inmediato
```json
{
  "topic": "UDFJC/emb1/robot6/RPi/state",
  "data": {
    "v": 5.0,          // Velocidad lineal (-10 a 10)
    "w": 2.0,          // Velocidad angular (-10 a 10)
    "alfa0": 0,        // Ángulo base (-90° a 90°)
    "alfa1": 50,       // Ángulo hombro (-70° a 150°)
    "alfa2": 110,      // Ángulo codo (10° a 150°)
    "duration": 2.0    // Duración del movimiento en segundos
  }
}
```

#### Crear Secuencia
```json
{
  "topic": "UDFJC/emb1/robot6/RPi/sequence",
  "data": {
    "action": "create",
    "sequence": {
      "name": "mi_rutina",
      "states": [
        {"v": 10, "w": 0, "alfa0": 0, "alfa1": 50, "alfa2": 110, "duration": 2.0},
        {"v": 0, "w": 5, "alfa0": 45, "alfa1": 70, "alfa2": 90, "duration": 1.5}
      ]
    }
  }
}
```

#### Ejecutar Secuencia
```json
{
  "topic": "UDFJC/emb1/robot6/RPi/sequence",
  "data": {
    "action": "execute_now",
    "name": "mi_rutina"
  }
}
```

### Cinemática Diferencial

El sistema convierte velocidad lineal (`v`) y angular (`w`) en velocidades de motor:

```
PWM_izquierdo = v + w
PWM_derecho = v - w
```

**Ejemplos de movimiento:**
- `v=10, w=0` → Adelante recto (máxima velocidad)
- `v=0, w=10` → Giro en su lugar (derecha)
- `v=5, w=2` → Curva suave a la derecha
- `v=-10, w=0` → Retroceso recto

## 🏗️ Arquitectura

```
┌─────────────────────────────────────┐
│   CAPA 1: Cliente TCP/IP            │
│   - Conexión al broker              │
│   - Suscripción a topics            │
│   - Recepción de mensajes           │
└──────────────┬──────────────────────┘
               │ JSON
┌──────────────▼──────────────────────┐
│   CAPA 2: Intérprete                │
│   - Parser de comandos JSON         │
│   - Cinemática diferencial          │
│   - Gestión de secuencias           │
└──────────────┬──────────────────────┘
               │ Comandos
┌──────────────▼──────────────────────┐
│   CAPA 3: Controlador Hardware      │
│   - Control PWM de motores DC       │
│   - Control de servomotores         │
│   - Calibración y validación        │
└─────────────────────────────────────┘
```

## 🔧 Calibración de Servos

Los servos están calibrados con las siguientes ecuaciones:

```python
calibracion = {
    'base': (11111, 1500000),      # y = 11111x + 1500000
    'hombro': (-11111, 1750000),   # y = -11111x + 1750000
    'codo': (10556, 450000)        # y = 10556x + 450000
}
```

Para recalibrar, ajusta estos valores según tu hardware específico.

## 📝 Tópicos MQTT

- `UDFJC/emb1/robot6/RPi/state` - Comandos de estado inmediatos
- `UDFJC/emb1/robot6/RPi/sequence` - Gestión de secuencias
- `UDFJC/emb1/+/RPi/state` - Comandos broadcast a todos los robots
- `UDFJC/emb1/+/RPi/sequence` - Secuencias broadcast

## 🐛 Diagnóstico

El sistema imprime mensajes detallados en la consola:

```
[WiFi] ✅ WiFi conectado exitosamente!
[CLIENTE] ✅ Conectado a 192.168.1.101:5051
[MOTOR] PWM -> Izq: 50000, Der: 30000
[SERVO] 📍 Moviendo brazo a: B=45°, H=70°, C=90°
```

## ⚠️ Notas Importantes

- La red WiFi debe ser **2.4 GHz** (Pico W no soporta 5 GHz)
- El código incluye **reintentos automáticos** de conexión
- Los motores se detienen automáticamente después de cada comando
- Los ángulos fuera de rango son validados y rechazados



---

**Proyecto desarrollado para control de robots móviles con manipulador en aplicaciones de robótica educativa e investigación.**
