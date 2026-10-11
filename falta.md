# Guía para el Integrante 2: Motor Paralelo

Este documento explica exactamente qué falta del proyecto, qué archivo crear, qué funciones escribir, qué reciben, qué retornan y cómo comprobar que todo quedó bien conectado con la GUI.

---

## 1. Qué ya existe

| Archivo                 | Estado               | Para qué sirve                                                                 |
| ----------------------- | -------------------- | ------------------------------------------------------------------------------ |
| `secuencial.py`         | Listo (Integrante 1) | Motor secuencial. Funciones `vecincos_vivos(...)` y `regla_actualizacion(...)` |
| `motores.py`            | Listo                | Contrato: busca `paralelo.py` y lo adapta para la GUI                          |
| `gui.py`                | Listo (Integrante 3) | Interfaz: simulación, benchmark y gráficas                                     |
| `benchmark.py`          | Listo                | Mide tiempos, calcula speedup y eficiencia, valida resultados                  |
| `graficas.py`           | Listo                | Genera las gráficas del informe                                                |
| `plantilla_paralelo.py` | Listo                | Esqueleto para copiar                                                          |
| **`paralelo.py`**       | **FALTA (tú)**       | Motor paralelo                                                                 |

No tienes que modificar ningún archivo existente. Solo creas `paralelo.py` en la misma carpeta que `gui.py`. La GUI lo detecta automáticamente al abrirse, o con el botón **Recargar paralelo.py**.

---

## 2. Resumen de lo que te toca

1. Crear `paralelo.py`.
2. Implementar la función `regla_actualizacion_paralela(matriz, filas, columnas, num_hilos)`.
3. (Recomendado) Implementar `iniciar(num_hilos)` y `finalizar()` para crear y cerrar el pool de hilos/procesos.
4. Verificar que el resultado sea idéntico al secuencial (la GUI lo valida sola).
5. Correr el benchmark con 2, 4 y 8 hilos/procesos en 100x100, 500x500 y 1000x1000 y exportar el CSV.
6. Escribir tu sección del informe: estrategia de paralelización, sincronización y comunicación.

---

## 3. El archivo: `paralelo.py`

Punto de partida:

```
cp plantilla_paralelo.py paralelo.py
```

### Estructura que debe tener

```python
import numpy as np
import secuencial          # puedes reutilizar secuencial.vecincos_vivos

NOMBRE = "Paralelo (Multiprocessing)"   # opcional

def iniciar(num_hilos): ...            # opcional, recomendado
def finalizar(): ...                    # opcional, recomendado
def regla_actualizacion_paralela(matriz, filas, columnas, num_hilos): ...   # OBLIGATORIA

# Funciones auxiliares internas (sugeridas, los nombres son libres)
def dividir_filas(filas, num_hilos): ...
def calcular_bloque(matriz, fila_inicio, fila_fin): ...
```

---

## 4. Funciones obligatorias y opcionales

### 4.1 `regla_actualizacion_paralela` (OBLIGATORIA)

```python
def regla_actualizacion_paralela(matriz: np.ndarray, filas: int, columnas: int,
                                 num_hilos: int) -> np.ndarray:
```

**Qué hace:** calcula la generación t+1 del Juego de la Vida repartiendo el trabajo entre `num_hilos` trabajadores (hilos o procesos).

**Parámetros:**

| Parámetro   | Tipo            | Descripción                                                                       |
| ----------- | --------------- | --------------------------------------------------------------------------------- |
| `matriz`    | `np.ndarray` 2D | Estado actual (generación t). Valores 0 (muerta) o 1 (viva). **Solo lectura.**    |
| `filas`     | `int`           | Número de filas de la matriz                                                      |
| `columnas`  | `int`           | Número de columnas de la matriz                                                   |
| `num_hilos` | `int` (>= 1)    | Cantidad de hilos o procesos a usar. Lo elige el usuario en la GUI o el benchmark |

**Retorna:** un `np.ndarray` **nuevo**, de forma `(filas, columnas)`, con 0/1, que representa la generación t+1.

**Reglas obligatorias:**

1. **No modificar `matriz`.** Todas las células de t+1 se calculan leyendo el estado t. Si escribes sobre `matriz` mientras otros trabajadores leen, aparecen condiciones de carrera y el resultado cambia.
2. **Retornar una matriz nueva**, no la misma de entrada. La GUI lanza error si retornas el mismo objeto.
3. **Misma forma que la entrada.** Si retornas `(999, 1000)` en vez de `(1000, 1000)`, la GUI lanza error.
4. **Mismo resultado exacto que `secuencial.regla_actualizacion`.** Bordes fijos: lo que está fuera de la matriz cuenta como célula muerta (no es un toroide).
5. **No retorna hasta que todos los trabajadores terminaron.** Esa es la barrera entre generaciones: ningún hilo puede empezar la generación t+2 mientras otro sigue en t+1.

**Reglas del juego (para recordar):**

| Estado actual | Vecinos vivos | Siguiente estado       |
| ------------- | ------------- | ---------------------- |
| Viva          | < 2           | Muere (soledad)        |
| Viva          | 2 o 3         | Sobrevive              |
| Viva          | > 3           | Muere (sobrepoblación) |
| Muerta        | exactamente 3 | Nace                   |
| Muerta        | otro valor    | Sigue muerta           |

### 4.2 `iniciar` (opcional, recomendada)

```python
def iniciar(num_hilos: int) -> None:
```

**Qué hace:** prepara los recursos una sola vez antes de una serie de generaciones: crear el `Pool` de procesos, el `ThreadPoolExecutor`, o hacer el `Spawn` de MPI.

**Retorna:** nada.

**Por qué importa:** crear un pool de procesos tarda decenas o cientos de milisegundos. Si lo creas dentro de `regla_actualizacion_paralela`, ese costo se paga en cada generación y el speedup se arruina. El benchmark y la GUI llaman `iniciar` antes de medir, y **ese tiempo no se cuenta**.

**Cuándo la llaman:** la GUI al pulsar Iniciar o Paso; el benchmark antes de cada combinación (tamaño, hilos).

### 4.3 `finalizar` (opcional, recomendada)

```python
def finalizar() -> None:
```

**Qué hace:** libera lo que creó `iniciar`: `pool.close()` + `pool.join()`, `executor.shutdown()` o `comm.Disconnect()`.

**Retorna:** nada.

**Cuándo la llaman:** al pausar la simulación o al terminar cada combinación del benchmark. Se llama siempre, incluso si hubo un error.

### 4.4 `NOMBRE` (opcional)

```python
NOMBRE = "Paralelo (Multiprocessing)"
```

Texto que aparece en el selector de motor y en la tabla y gráficas del benchmark. Si no lo defines, aparece "Paralelo".

---

## 5. Funciones auxiliares sugeridas

No son parte del contrato (la GUI no las llama), pero ordenan el código y son fáciles de explicar en la sustentación.

### 5.1 `dividir_filas`

```python
def dividir_filas(filas: int, num_hilos: int) -> list[tuple[int, int]]:
```

**Qué hace:** reparte las filas en `num_hilos` bloques contiguos lo más parejos posible.

**Retorna:** lista de tuplas `(fila_inicio, fila_fin)`, con `fila_fin` excluida.

**Ejemplo:** `dividir_filas(10, 3)` -> `[(0, 3), (3, 6), (6, 10)]`

**Fórmula útil:** el bloque `k` va de `k * filas // num_hilos` a `(k + 1) * filas // num_hilos`. Así no se pierde ninguna fila aunque la división no sea exacta.

### 5.2 `calcular_bloque`

```python
def calcular_bloque(matriz: np.ndarray, fila_inicio: int, fila_fin: int) -> np.ndarray:
```

**Qué hace:** aplica las reglas del juego solo a las filas `[fila_inicio, fila_fin)`, leyendo de `matriz` completa (porque las filas del borde del bloque necesitan ver la fila de arriba y la de abajo).

**Retorna:** un arreglo de forma `(fila_fin - fila_inicio, columnas)` con el nuevo estado de ese bloque.

**Cómo hacerlo:** recorrer `i` en el rango del bloque y `j` en todas las columnas; contar vecinos con `secuencial.vecincos_vivos(matriz, i, j, filas, columnas)` y aplicar la tabla de reglas. Escribir en `resultado[i - fila_inicio, j]`.

Luego `regla_actualizacion_paralela` junta los bloques en orden con `np.vstack(lista_de_bloques)`.

---

## 6. Estrategia de paralelización recomendada

**División por filas (bloques horizontales).** Cada trabajador calcula un rango de filas.

```
matriz (t)                      nueva (t+1)
+------------------+            +------------------+
| filas 0..249     |  hilo 0 -> | filas 0..249     |
| filas 250..499   |  hilo 1 -> | filas 250..499   |
| filas 500..749   |  hilo 2 -> | filas 500..749   |
| filas 750..999   |  hilo 3 -> | filas 750..999   |
+------------------+            +------------------+
   solo lectura                   cada hilo escribe
                                  SOLO sus filas
```

Por qué funciona sin locks:

- **Lectura:** todos leen de `matriz` (estado t), que nadie modifica.
- **Escritura:** cada trabajador escribe en un rango de filas distinto, así que no hay dos trabajadores escribiendo la misma celda.
- **Barrera:** `pool.map(...)` o `concurrent.futures.wait(...)` no retornan hasta que todos terminan. Eso garantiza que la generación t+1 está completa antes de empezar la t+2.

Esto es la técnica de doble buffer: `matriz` (t) y `nueva` (t+1) son memorias separadas.

---

## 7. Qué tecnología usar

### Opción A: `multiprocessing` (RECOMENDADA)

Cada trabajador es un proceso con su propio intérprete, así que sí usa varios núcleos a la vez. Es la opción con la que se ve un speedup real en Python.

Puntos a tener en cuenta:

- La función que ejecuta cada proceso (`calcular_bloque` o un envoltorio) debe estar definida **a nivel de módulo** (no dentro de otra función ni como lambda), porque `multiprocessing` la envía a los procesos serializándola con pickle.
- **Nunca crear el `Pool` al importar el módulo** (fuera de una función). En Windows y macOS los procesos hijos vuelven a importar `paralelo.py` y se crearían pools en cadena. Crearlo solo dentro de `iniciar`.
- `pool.map` recibe una lista de argumentos, uno por bloque. Como `map` pasa un solo argumento, envolver: `def _trabajo(args): return calcular_bloque(*args)`.
- Si `regla_actualizacion_paralela` se llama sin haber pasado por `iniciar` (por ejemplo, desde una prueba propia), conviene crear el pool ahí como respaldo.
- Costo de comunicación: en cada generación la matriz se copia a cada proceso. Para 1000x1000 de `uint8` es 1 MB por proceso, aceptable. Si quieren optimizar, pueden usar `multiprocessing.shared_memory`, pero no es obligatorio. Este costo es buen tema para el informe (por qué 100x100 casi no acelera).

Esqueleto:

```python
import numpy as np
from multiprocessing import Pool
import secuencial

NOMBRE = "Paralelo (Multiprocessing)"

_pool = None          # pool global, lo crea iniciar()
_num = 0              # número de procesos del pool actual


def dividir_filas(filas, num_hilos):
    # TODO: retornar [(inicio, fin), ...] usando k*filas//num_hilos
    ...


def calcular_bloque(matriz, fila_inicio, fila_fin):
    # TODO: aplicar reglas a filas [fila_inicio, fila_fin), retornar el bloque nuevo
    ...


def _trabajo(args):
    return calcular_bloque(*args)


def iniciar(num_hilos):
    global _pool, _num
    # TODO: crear Pool(num_hilos) y guardar num_hilos en _num


def finalizar():
    global _pool
    # TODO: si _pool existe: close(), join(), dejarlo en None


def regla_actualizacion_paralela(matriz, filas, columnas, num_hilos):
    # 1. Si no hay pool (o tiene otro tamaño), crearlo
    # 2. Armar tareas = [(matriz, inicio, fin) for (inicio, fin) in dividir_filas(...)]
    # 3. bloques = _pool.map(_trabajo, tareas)       <- barrera implícita
    # 4. return np.vstack(bloques)
    ...
```

### Opción B: `threading` / `ThreadPoolExecutor`

Más simple (los hilos comparten memoria, no hay que copiar la matriz), pero en Python estándar el **GIL** solo deja ejecutar código Python en un hilo a la vez. Como `vecincos_vivos` es Python puro, el speedup va a salir cercano a 1 o incluso menor.

Si la eligen igual, es válido, pero deben explicarlo en el informe como hallazgo (el speedup bajo es un resultado, no un error). Una buena idea es implementar **ambas** opciones y comparar (ver sección 8).

Esqueleto:

```python
from concurrent.futures import ThreadPoolExecutor

_executor = None

def iniciar(num_hilos):
    # TODO: _executor = ThreadPoolExecutor(max_workers=num_hilos)

def finalizar():
    # TODO: _executor.shutdown(wait=True); _executor = None

def regla_actualizacion_paralela(matriz, filas, columnas, num_hilos):
    # nueva = np.empty_like(matriz)
    # cada tarea: calcula su bloque y lo escribe en nueva[inicio:fin]  (filas distintas -> sin lock)
    # futuros = [_executor.submit(...) for ...]
    # for f in futuros: f.result()     <- barrera + propaga excepciones
    # return nueva
    ...
```

### Opción C: MPI (`mpi4py`)

La GUI llama a tu función desde **un solo proceso**, así que el programa no se lanza con `mpirun`. La forma compatible con el contrato es crear los procesos desde `iniciar`:

- `iniciar(n)`: `comm = MPI.COMM_SELF.Spawn(sys.executable, args=["trabajador_mpi.py"], maxprocs=n)`.
- `regla_actualizacion_paralela`: enviar a cada trabajador su bloque de filas **más una fila fantasma arriba y una abajo** (ghost rows), recibir los bloques calculados y unirlos.
- `finalizar()`: enviar una señal de fin y hacer `comm.Disconnect()`.
- Necesitan un archivo extra `trabajador_mpi.py` con el bucle del trabajador.

Es la opción más compleja. Solo vale la pena si el profesor la valora más o si quieren hablar de comunicación de bordes en la sustentación.

---

## 8. (Opcional) Varios motores en un mismo archivo

Si implementan threads y multiprocessing para compararlos, en vez de la función única definan la lista `MOTORES`:

```python
from motores import Motor

MOTORES = [
    Motor(nombre="Paralelo (Threads)", paso=paso_threads, es_paralelo=True,
          iniciar=iniciar_threads, finalizar=finalizar_threads, clave="threads"),
    Motor(nombre="Paralelo (Procesos)", paso=paso_procesos, es_paralelo=True,
          iniciar=iniciar_procesos, finalizar=finalizar_procesos, clave="procesos"),
]
```

Ojo: en este formato `paso` recibe solo dos argumentos, `paso(matriz, num_hilos)`. Las filas y columnas se sacan con `matriz.shape`.

Ambos motores aparecen en la GUI y en el benchmark, y las gráficas los comparan automáticamente.

---

## 9. Cómo probar que quedó bien

### 9.1 Prueba rápida por consola

Crear `probar_paralelo.py` (no se entrega, es solo para ti):

```python
import numpy as np
import secuencial
import paralelo

rng = np.random.default_rng(0)
for n in (10, 37, 100):
    m = (rng.random((n, n)) < 0.4).astype(np.uint8)
    copia = m.copy()
    esperado = secuencial.regla_actualizacion(m, n, n)
    for h in (1, 2, 3, 4, 8):
        if hasattr(paralelo, "iniciar"):
            paralelo.iniciar(h)
        obtenido = paralelo.regla_actualizacion_paralela(m, n, n, h)
        if hasattr(paralelo, "finalizar"):
            paralelo.finalizar()
        assert np.array_equal(m, copia), "Se modificó la matriz de entrada"
        assert obtenido.shape == m.shape, f"Forma incorrecta {obtenido.shape}"
        assert np.array_equal(obtenido, esperado), f"Resultado distinto n={n} hilos={h}"
print("Todo OK")
```

Si usan `multiprocessing`, agregar `if __name__ == "__main__":` alrededor del bucle (obligatorio en Windows).

Prueben tamaños que no se dividan exacto entre los hilos (como 37 con 4 o 10 con 3): ahí aparecen los errores de filas perdidas.

### 9.2 Prueba en la GUI

1. `python gui.py`
2. En **Simulación**, el texto verde debe decir "Paralelos detectados: <tu NOMBRE>".
3. Elegir tu motor, poner 4 hilos, patrón "Cañón de Gosper", tamaño 60 e Iniciar. Debe verse igual que con Secuencial (los planeadores salen del cañón cada 30 generaciones).
4. Si algo falla, aparece un mensaje con el error. Corriges `paralelo.py` y pulsas **Recargar paralelo.py** sin cerrar la ventana.

### 9.3 Benchmark

En la pestaña **Benchmark**: tamaños `100 500 1000`, hilos `2 4 8`, generaciones `5`, Ejecutar. Revisar que la columna **Válido** diga "Sí" en todas las filas (si dice "NO" y la fila sale en rojo, el resultado no coincide con el secuencial).

Por consola equivale a:

```
python benchmark.py --tamanios 100 500 1000 --hilos 2 4 8 --generaciones 5 --salida resultados.csv
```

Exportar el CSV y pasárselo al Integrante 3 para las gráficas del informe. Ejecutar con el equipo conectado a la corriente y con pocos programas abiertos, porque afecta los tiempos.

---

## 10. Errores comunes

| Síntoma                                               | Causa probable                                                                                           |
| ----------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| "Válido: NO" en el benchmark                          | Se escribe sobre `matriz` en vez de en una matriz nueva, o se pierden/duplican filas al dividir          |
| Error "retornó forma (...)"                           | `np.vstack` con bloques mal cortados, o falta el último bloque                                           |
| Error "retornó la misma matriz de entrada"            | Se hace `return matriz` después de modificarla                                                           |
| `PicklingError` / `Can't pickle local object`         | La función del pool está definida dentro de otra función o es una lambda                                 |
| La GUI se abre varias veces o el equipo se pone lento | El `Pool` se crea al importar el módulo en vez de en `iniciar`                                           |
| Speedup cercano a 1 con threads                       | Es el GIL, no un error. Explicarlo en el informe o usar `multiprocessing`                                |
| Speedup menor a 1 en 100x100                          | El costo de repartir el trabajo supera al de calcular. Es esperable y es buen análisis                   |
| La simulación no avanza / se cuelga                   | Falta una barrera, o un trabajador lanzó una excepción que no se propaga (usar `.result()` o `pool.map`) |

---

## 11. Tu parte del informe

Temas que debes cubrir (el Integrante 3 se encarga de las gráficas y conclusiones):

1. **Estrategia de paralelización:** división por filas, cómo se calculan los rangos, por qué filas y no columnas o bloques (en NumPy las filas son contiguas en memoria, así que cortar por filas es más barato).
2. **Sincronización:** doble buffer (t se lee, t+1 se escribe), escrituras en rangos disjuntos (sin locks), barrera implícita de `pool.map` / `.result()`.
3. **Condiciones de carrera:** qué pasaría si se actualizara la matriz en sitio (una célula vería vecinos ya actualizados de t+1 mezclados con los de t).
4. **Comunicación:** en `multiprocessing`, el costo de copiar la matriz a cada proceso; en MPI, el intercambio de filas fantasma.
5. **Métricas:** fórmulas de speedup `S = T_secuencial / T_paralelo` y eficiencia `E = S / p`, y la tabla de resultados del benchmark.

---

## 12. Checklist final

- [ ] Existe `paralelo.py` en la misma carpeta que `gui.py`
- [ ] Define `regla_actualizacion_paralela(matriz, filas, columnas, num_hilos)`
- [ ] No modifica `matriz` y retorna una matriz nueva de la misma forma
- [ ] El pool se crea en `iniciar` y se cierra en `finalizar` (no al importar)
- [ ] `probar_paralelo.py` imprime "Todo OK" con tamaños que no se dividen exacto
- [ ] La GUI muestra el motor y la simulación se ve igual que la secuencial
- [ ] Benchmark con 2, 4 y 8 hilos en 100, 500 y 1000: todas las filas "Válido: Sí"
- [ ] CSV exportado y enviado al Integrante 3
- [ ] Sección del informe redactada
