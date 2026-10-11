# Juego de la Vida - Parcial I (Infraestructuras Paralelas y Distribuidas)

## Archivos

| Archivo | Responsable | Qué hace |
|---|---|---|
| `secuencial.py` | Integrante 1 | Motor secuencial (sin cambios) |
| `paralelo.py` | Integrante 2 | Motor paralelo (**por crear**, partir de `plantilla_paralelo.py`) |
| `motores.py` | GUI | Contrato: adapta cada motor a una interfaz común |
| `gui.py` | Integrante 3 | Interfaz gráfica (simulación, benchmark, gráficas) |
| `benchmark.py` | GUI / todos | Medición estandarizada y cálculo de speedup/eficiencia |
| `graficas.py` | Integrante 3 | Gráficas de rendimiento (en la GUI o como PNG) |

## Requisitos

```
pip install numpy matplotlib
```
Tkinter viene con Python en Windows/macOS. En Linux: `sudo pacman -S tk` (Arch) o `sudo apt install python3-tk` (Debian/Ubuntu).

## Uso

```
python gui.py                                    # interfaz completa
python benchmark.py --tamanios 100 500 1000 --hilos 2 4 8 --generaciones 5
python graficas.py resultados.csv --carpeta graficas   # PNG para el informe
```

- **Simulación**: elegir motor, hilos, tamaño y patrón; Iniciar / Pausar / Paso / Limpiar; retardo ajustable; clic izquierdo/derecho edita células en pausa.
- **Benchmark**: corre en un proceso aparte, así el renderizado no altera las mediciones. Todos los motores parten de la misma matriz (semilla fija), solo se cronometra el bucle de generaciones, y cada resultado paralelo se compara contra el secuencial (columna *Válido*).
- **Gráficas**: tiempo vs. tamaño, speedup vs. hilos y eficiencia vs. hilos, con línea ideal. Exportables a PNG.
- Los CSV se pueden importar y combinar (por ejemplo, corridas hechas en distintos equipos).

---

## Contrato para el motor paralelo (Integrante 2)

Crear `paralelo.py` en la misma carpeta. La GUI lo detecta sola (o con el botón **Recargar paralelo.py**).

### Obligatorio

```python
def regla_actualizacion_paralela(matriz, filas, columnas, num_hilos) -> np.ndarray:
```

- Misma firma que `secuencial.regla_actualizacion` más `num_hilos`.
- `matriz`: `np.ndarray` 2D de 0/1. **No modificarla**.
- Retornar una matriz **nueva** con la misma forma y la generación t+1.
- Mismo resultado exacto que la versión secuencial (bordes fijos: fuera de la matriz = muerta).

### Opcional

```python
NOMBRE = "Paralelo (Threads)"   # nombre en la GUI
def iniciar(num_hilos): ...     # crear pool / MPI Spawn, una vez antes de correr
def finalizar(): ...            # cerrar pool, una vez al terminar
```

El tiempo de `iniciar`/`finalizar` no se cuenta en las mediciones.

### Varios motores (ej. threads y procesos)

```python
from motores import Motor
MOTORES = [
    Motor(nombre="Threads", paso=lambda m, h: con_threads(m, h), es_paralelo=True, clave="threads"),
    Motor(nombre="Procesos", paso=lambda m, h: con_procesos(m, h), es_paralelo=True,
          iniciar=crear_pool, finalizar=cerrar_pool, clave="procesos"),
]
```

`paso(matriz, num_hilos)` recibe solo la matriz y los hilos.

### Validaciones automáticas

Si el motor retorna algo que no es `np.ndarray`, con otra forma, o la misma matriz de entrada, la GUI muestra el error. Si el resultado difiere del secuencial, la fila del benchmark sale en rojo con *Válido: NO*.

### Si usan MPI

La GUI llama la función desde un solo proceso, así que no se lanza con `mpirun`. Opción compatible con el contrato: en `iniciar(n)` hacer `MPI.COMM_SELF.Spawn(...)` de `n` trabajadores, en la función repartir filas (con filas fantasma de los bordes) y recoger con `gather`, y en `finalizar()` desconectar.
