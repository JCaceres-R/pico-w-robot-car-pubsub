"""
Cliente Pub/Sub para Raspberry Pi Pico W
Recibe comandos JSON del broker y controla el carro + brazo
Implementa cinemática diferencial para movimientos suaves
MicroPython
"""

import network
import socket
import json
import time
import _thread
from machine import Pin, PWM


# ==================== CONFIGURACIÓN WIFI MEJORADA ====================
def connect_wifi(ssid, password, timeout=30):
    """Conexión WiFi robusta con diagnóstico"""
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    
    # Desconectar si ya estaba conectado
    if wlan.isconnected():
        print('[WiFi] Ya conectado, desconectando...')
        wlan.disconnect()
        time.sleep(1)
    
    print('[WiFi] Escaneando redes disponibles...')
    time.sleep(2)
    networks = wlan.scan()
    print(f'[WiFi] Redes encontradas: {len(networks)}')
    
    target_found = False
    for net in networks:
        ssid_found = net[0].decode()
        rssi = net[3]
        channel = net[2]
        print(f'  SSID: {ssid_found}, Señal: {rssi} dBm, Canal: {channel}')
        if ssid_found == ssid:
            target_found = True
            print(f'  >>> RED OBJETIVO ENCONTRADA <<<')
    
    if not target_found:
        print(f'[WiFi] ERROR: No se encontro la red {ssid}')
        print('[WiFi] Verifica que el hotspot este activo y en 2.4 GHz')
        return None
    
    print(f'[WiFi] Conectando a: {ssid}')
    wlan.connect(ssid, password)
    
    # Esperar conexion con timeout
    start = time.time()
    while not wlan.isconnected():
        elapsed = time.time() - start
        if elapsed > timeout:
            print('[WiFi] ERROR: Timeout - No se pudo conectar')
            status = wlan.status()
            print(f'[WiFi] Codigo de estado: {status}')
            if status == 2:
                print('[WiFi] Razon: Contraseña incorrecta')
            elif status == 3:
                print('[WiFi] Razon: No se encontro el AP')
            else:
                print('[WiFi] Razon: Fallo de conexion')
            return None
        
        if int(elapsed) % 2 == 0:
            print('.', end='')
        time.sleep(0.5)
    
    print('\n[WiFi] ✅ WiFi conectado exitosamente!')
    config = wlan.ifconfig()
    print(f'[WiFi] IP: {config[0]}')
    print(f'[WiFi] Mascara: {config[1]}')
    print(f'[WiFi] Gateway: {config[2]}')
    print(f'[WiFi] DNS: {config[3]}')
    return config[0]


# Conectar a WiFi
print('\n' + '='*60)
print('🤖 INICIANDO CLIENTE PUB/SUB - CARRO ROBOTICO')
print('='*60 + '\n')

ip_local = connect_wifi("Ejemplo", "12345678")

if not ip_local:
    print('[MAIN] ❌ No se pudo conectar al WiFi. Deteniendo...')
    raise SystemExit

print(f"[CLIENTE] IP local: {ip_local}")


# ==================== CAPA 3: HARDWARE ====================
class ControladorHardware:
    """Control de motores DC y servos"""
    
    def __init__(self):
        print("[HARDWARE] Inicializando...")
        
        # Motores DC - Ruedas
        # Motor izquierdo
        self.motor_izq_fwd = PWM(Pin(20), freq=2000)  # B1
        self.motor_izq_bwd = PWM(Pin(21), freq=2000)  # B2
        # Motor derecho
        self.motor_der_bwd = PWM(Pin(18), freq=2000)  # A1
        self.motor_der_fwd = PWM(Pin(19), freq=2000)  # A2
        
        # Servos
        self.base = PWM(Pin(6))
        self.hombro = PWM(Pin(5))
        self.codo = PWM(Pin(7))
        self.base.freq(50)
        self.hombro.freq(50)
        self.codo.freq(50)
        
        # Calibración servos
        self.calibracion = {
            'base': (11111, 1500000),
            'hombro': (-11111, 1750000),
            'codo': (10556, 450000)
        }
        
        # Rangos válidos
        self.rangos = {
            'base': (-90, 90),
            'hombro': (-70, 150),
            'codo': (10, 150)
        }
        
        # Posición actual
        self.angulos_actuales = {'base': 0, 'hombro': 20, 'codo': 55}
        
        print("[HARDWARE] ✅ Inicializado")
    
    # ========== MOTORES - CONTROL DIFERENCIAL ==========
    def set_motor_speeds(self, pwm_izquierdo, pwm_derecho):
        """
        Establece la velocidad de los motores usando PWM signed.
        
        PWM positivo = adelante
        PWM negativo = atrás
        Rango típico: -65535 a 65535
        """
        # Motor izquierdo
        if pwm_izquierdo > 0:
            self.motor_izq_fwd.duty_u16(int(pwm_izquierdo))
            self.motor_izq_bwd.duty_u16(0)
        else:
            self.motor_izq_fwd.duty_u16(0)
            self.motor_izq_bwd.duty_u16(int(abs(pwm_izquierdo)))
        
        # Motor derecho
        if pwm_derecho > 0:
            self.motor_der_fwd.duty_u16(int(pwm_derecho))
            self.motor_der_bwd.duty_u16(0)
        else:
            self.motor_der_fwd.duty_u16(0)
            self.motor_der_bwd.duty_u16(int(abs(pwm_derecho*0.85)))
        
        print(f"[MOTOR] PWM -> Izq: {int(pwm_izquierdo):6d}, Der: {int(pwm_derecho):6d}")
    
    def detener_motores(self):
        """Detiene todos los motores DC"""
        self.motor_izq_fwd.duty_u16(0)
        self.motor_izq_bwd.duty_u16(0)
        self.motor_der_fwd.duty_u16(0)
        self.motor_der_bwd.duty_u16(0)
        print("[MOTOR] Detenido")
    
    # ========== SERVOS ==========
    def _angulo_a_duty_ns(self, servo_nombre, angulo):
        m, b = self.calibracion[servo_nombre]
        return int(m * angulo + b)
    
    def _validar_angulo(self, servo, angulo):
        if servo not in self.rangos:
            return True
        min_ang, max_ang = self.rangos[servo]
        if min_ang <= angulo <= max_ang:
            return True
        else:
            print(f"[SERVO] ⚠️ {servo} {angulo}° fuera de rango [{min_ang}, {max_ang}]")
            return False
    
    def mover_brazo_directo(self, base, hombro, codo):
        """Mueve los servos a los ángulos especificados"""
        print(f"[SERVO] 📍 Moviendo brazo a: B={base}°, H={hombro}°, C={codo}°")
        
        # Mover base
        if self._validar_angulo('base', base):
            duty_b = self._angulo_a_duty_ns('base', base)
            self.base.duty_ns(duty_b)
            self.angulos_actuales['base'] = float(base)
        
        # Mover hombro
        if self._validar_angulo('hombro', hombro):
            duty_h = self._angulo_a_duty_ns('hombro', hombro)
            self.hombro.duty_ns(duty_h)
            self.angulos_actuales['hombro'] = float(hombro)
        
        # Mover codo
        if self._validar_angulo('codo', codo):
            duty_c = self._angulo_a_duty_ns('codo', codo)
            self.codo.duty_ns(duty_c)
            self.angulos_actuales['codo'] = float(codo)
            
        print(f"[SERVO] ✅ Brazo movido")


# ==================== CAPA 2: INTÉRPRETE JSON ====================
class InterpreteCarro:
    """Parsea comandos JSON del broker"""
    
    MAX_PWM = 65535  # Máximo valor de PWM para duty_u16
    
    def __init__(self, hardware):
        self.hw = hardware
        self.secuencias = {}
        print("[INTÉRPRETE] Inicializado")
    
    def procesar_mensaje(self, mensaje):
        """Procesa mensaje recibido del broker"""
        try:
            topic = mensaje.get("topic", "")
            data = mensaje.get("data", {})
            
            print(f"[INTÉRPRETE] Topic: {topic}")
            print(f"[INTÉRPRETE] Data: {data}")
            
            if "state" in topic:
                self._ejecutar_estado(data)
            elif "sequence" in topic:
                action = data.get("action", "")
                if action == "create":
                    self._crear_secuencia(data.get("sequence", {}))
                elif action == "execute_now":
                    self._ejecutar_secuencia(data.get("name", ""))
        
        except Exception as e:
            print(f"[INTÉRPRETE] ❌ Error: {e}")
    
    def _ejecutar_estado(self, data):
        """Ejecuta comando de estado inmediato - SIN MODIFICACIONES DE ÁNGULOS"""
        v = data.get("v", 0.0)
        w = data.get("w", 0.0)
        alfa0 = data.get("alfa0", 0)
        alfa1 = data.get("alfa1", 50)
        alfa2 = data.get("alfa2", 110)
        duracion = data.get("duration", 1.0)
        
        print(f"[ESTADO] v={v}, w={w}, alfas=[{alfa0},{alfa1},{alfa2}], dur={duracion}s")
        
        # Mover brazo - USA LOS ÁNGULOS TAL COMO VIENEN
        print("[ESTADO] 🔧 Ejecutando movimiento de brazo...")
        self.hw.mover_brazo_directo(alfa0, (alfa1-50), (alfa2+60))
        time.sleep(0.1)

        # Interpretar movimiento con cinemática diferencial
        print("[ESTADO] 🚗 Ejecutando movimiento de motores...")
        self._interpretar_movimiento(v, w, duracion)
    
    def _interpretar_movimiento(self, v, w, duracion):
        """
        Convierte v (velocidad lineal) y w (velocidad angular)
        en velocidades de motor usando cinemática diferencial.
        
        RANGO: -10 a 10 (10 = PWM máximo)
        
        Fórmulas:
        PWM_izquierdo = v + w
        PWM_derecho = v - w
        
        Ejemplos:
        - v=10, w=0     -> Adelante recto (máxima velocidad)
        - v=0, w=10     -> Giro estático
        - v=5, w=2      -> Curva suave a la derecha
        - v=-10, w=0    -> Atrás recto
        """
        # Convertir v y w a rango PWM (escala -10 a 10)
        pwm_v = v * (abs(self.MAX_PWM * 0.95) / 10.0) if v != 0 else 0
        pwm_w = w * (abs(self.MAX_PWM * 0.95) / 10.0) if w != 0 else 0
        
        # Aplicar cinemática diferencial
        pwm_izquierdo = pwm_v + pwm_w
        pwm_derecho = pwm_v - pwm_w
        
        # Saturar (limitar) valores
        pwm_izquierdo = max(min(pwm_izquierdo, self.MAX_PWM), -self.MAX_PWM)
        pwm_derecho = max(min(pwm_derecho, self.MAX_PWM), -self.MAX_PWM)
        
        print(f"[MOVIMIENTO] v={v}, w={w} -> PWM_L={int(pwm_izquierdo)}, PWM_R={int(pwm_derecho)}")
        
        # Enviar al hardware
        self.hw.set_motor_speeds(round(pwm_izquierdo*0.85), pwm_derecho)
        
        # Mantener movimiento por la duración
        time.sleep(duracion)
        self.hw.detener_motores()
    
    def _crear_secuencia(self, seq_data):
        """Crea y guarda una secuencia"""
        nombre = seq_data.get("name", "sin_nombre")
        estados = seq_data.get("states", [])
        self.secuencias[nombre] = estados
        print(f"[SECUENCIA] ✅ Creada: '{nombre}' con {len(estados)} estados")
    
    def _ejecutar_secuencia(self, nombre):
        """Ejecuta una secuencia guardada"""
        if nombre not in self.secuencias:
            print(f"[SECUENCIA] ❌ No existe: '{nombre}'")
            return
        
        estados = self.secuencias[nombre]
        print(f"[SECUENCIA] 🎬 Ejecutando '{nombre}' ({len(estados)} estados)...")
        
        for i, estado in enumerate(estados):
            print(f"[SECUENCIA] Estado {i+1}/{len(estados)}")
            self._ejecutar_estado(estado)
            #time.sleep(0.5)
        
        print(f"[SECUENCIA] ✅ Completada: '{nombre}'")


# ==================== CAPA 1: CLIENTE SOCKET ====================
class ClienteCarro:
    """Cliente TCP que se conecta al broker"""
    
    def __init__(self, broker_ip, broker_port, interprete):
        self.broker_ip = broker_ip
        self.broker_port = broker_port
        self.sock = None
        self.running = False
        self.interprete = interprete
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 5
        print(f"[CLIENTE] Configurado para {broker_ip}:{broker_port}")
    
    def conectar(self):
        """Conecta al broker con reintentos"""
        while self.reconnect_attempts < self.max_reconnect_attempts:
            try:
                print(f"[CLIENTE] Intento de conexión {self.reconnect_attempts + 1}/{self.max_reconnect_attempts}...")
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.settimeout(10.0)
                self.sock.connect((self.broker_ip, self.broker_port))
                self.running = True
                self.reconnect_attempts = 0
                print(f"[CLIENTE] ✅ Conectado a {self.broker_ip}:{self.broker_port}")
                return True
            except OSError as e:
                self.reconnect_attempts += 1
                print(f"[CLIENTE] ❌ Error conectando (intento {self.reconnect_attempts}): {e}")
                if self.reconnect_attempts < self.max_reconnect_attempts:
                    print(f"[CLIENTE] Reintentando en 3 segundos...")
                    time.sleep(3)
                else:
                    print(f"[CLIENTE] ❌ Máximo de reintentos alcanzado")
                    return False
        return False
    
    def suscribirse(self, topic):
        """Se suscribe a un tópico"""
        try:
            pkt = {"action": "SUB", "topic": topic}
            data = json.dumps(pkt) + "\n"
            self.sock.send(data.encode("utf-8"))
            print(f"[CLIENTE] → Suscrito a: {topic}")
        except Exception as e:
            print(f"[CLIENTE] ❌ Error suscribiendo: {e}")
    
    def escuchar_mensajes(self):
        """Loop de escucha en thread separado"""
        buf = b""
        self.sock.settimeout(1.0)
        
        while self.running:
            try:
                data = self.sock.recv(1024)
                if not data:
                    print("[CLIENTE] ❌ Conexión cerrada por broker")
                    break
                
                buf += data
                while b"\n" in buf:
                    linea, buf = buf.split(b"\n", 1)
                    texto = linea.decode("utf-8").strip()
                    if not texto:
                        continue
                    
                    try:
                        mensaje = json.loads(texto)
                        print(f"[CLIENTE] ← Recibido: {mensaje}")
                        self.interprete.procesar_mensaje(mensaje)
                    except Exception as e:
                        print(f"[CLIENTE] ❌ JSON inválido: {e}")
            
            except OSError as e:
                if e.args[0] in (110, 116, 11):
                    continue
                else:
                    print(f"[CLIENTE] ❌ Error de socket: {e}")
                    break
            except Exception as e:
                print(f"[CLIENTE] ❌ Error escuchando: {e}")
                break
        
        self.running = False
        self.desconectar()
    
    def desconectar(self):
        """Desconecta del broker"""
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            except:
                pass
        print("[CLIENTE] ❌ Desconectado")
    
    def iniciar_escucha_thread(self):
        """Inicia escucha en thread"""
        _thread.start_new_thread(self.escuchar_mensajes, ())


# ==================== MAIN ====================
def main():
    # Crear capas
    hardware = ControladorHardware()
    interprete = InterpreteCarro(hardware)
    
    # CAMBIAR ESTA IP A LA DE TU BROKER (PC)
    cliente = ClienteCarro("192.168.1.101", 5051, interprete)
    
    # Conectar
    if not cliente.conectar():
        print("[MAIN] ❌ No se pudo conectar al broker")
        return
    
    # Suscribirse a tópicos
    cliente.suscribirse("UDFJC/emb1/robot6/RPi/state")
    cliente.suscribirse("UDFJC/emb1/robot6/RPi/sequence")
    cliente.suscribirse("UDFJC/emb1/+/RPi/state")
    cliente.suscribirse("UDFJC/emb1/+/RPi/sequence")
    
    # Iniciar escucha en thread
    cliente.iniciar_escucha_thread()
    
    print("[MAIN] ✅ Cliente esperando comandos...")
    print("[MAIN] Presiona Ctrl+C para detener\n")
    
    try:
        while cliente.running:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[MAIN] Deteniendo...")
        hardware.detener_motores()
        cliente.desconectar()


if __name__ == "__main__":
    main()