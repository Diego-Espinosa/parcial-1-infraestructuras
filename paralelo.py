import numpy as np
from multiprocessing import Pool
import secuencial

# Nombre que aparecerá automáticamente en la Interfaz Gráfica y el Benchmark
NOMBRE = "Paralelo (Multiprocessing)"

_pool = None
_num = 0

def dividir_filas(filas: int, num_hilos: int) -> list[tuple[int, int]]:
    """Reparte las filas en bloques contiguos lo más parejos posible."""
    bloques = []
    for k in range(num_hilos):
        inicio = k * filas // num_hilos
        fin = (k + 1) * filas // num_hilos
        bloques.append((inicio, fin))
    return bloques

def calcular_bloque(matriz: np.ndarray, fila_inicio: int, fila_fin: int) -> np.ndarray:
    """Aplica las reglas del juego a un rango específico de filas."""
    filas_totales, columnas = matriz.shape
    # Se crea una sub-matriz (buffer) solo para el rango de este proceso
    nuevo_bloque = np.zeros((fila_fin - fila_inicio, columnas), dtype=np.uint8)
    
    for i in range(fila_inicio, fila_fin):
        for j in range(columnas):
            # Usamos la función original de Integrante 1 (notar el nombre vecincos_vivos)
            v_vivos = secuencial.vecincos_vivos(matriz, i, j, filas_totales, columnas)
            
            # Reglas de supervivencia y nacimiento
            if matriz[i, j] == 1 and (v_vivos == 2 or v_vivos == 3):
                nuevo_bloque[i - fila_inicio, j] = 1
            elif matriz[i, j] == 0 and v_vivos == 3:
                nuevo_bloque[i - fila_inicio, j] = 1
            # Muertes por soledad o sobrepoblación quedan en 0 por defecto
            
    return nuevo_bloque

def _trabajo(args):
    """Envoltorio para que pool.map pueda pasar los 3 argumentos."""
    return calcular_bloque(*args)

def iniciar(num_hilos: int) -> None:
    """Crea el pool de procesos una sola vez para no afectar el rendimiento en cada generación."""
    global _pool, _num
    if _pool is None or _num != num_hilos:
        finalizar()
        _pool = Pool(num_hilos)
        _num = num_hilos

def finalizar() -> None:
    """Libera la memoria y cierra los procesos."""
    global _pool
    if _pool is not None:
        _pool.close()
        _pool.join()
        _pool = None

def regla_actualizacion_paralela(matriz: np.ndarray, filas: int, columnas: int, num_hilos: int) -> np.ndarray:
    """Calcula la generación t+1 repartiendo el trabajo."""
    global _pool
    
    # Respaldo por si se llama a la función sin pasar por iniciar()
    pool_local = False
    if _pool is None:
        _pool = Pool(num_hilos)
        pool_local = True

    # 1. División del trabajo
    rangos = dividir_filas(filas, num_hilos)
    tareas = [(matriz, inicio, fin) for inicio, fin in rangos]

    # 2. Sincronización y Barrera implícita
    # map() no retorna hasta que todos los subprocesos terminen la iteración actual
    bloques = _pool.map(_trabajo, tareas)

    # 3. Ensamblaje de la matriz resultante
    nueva_matriz = np.vstack(bloques)

    if pool_local:
        _pool.close()
        _pool.join()
        _pool = None

    return nueva_matriz