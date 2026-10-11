"""
plantilla_paralelo.py - Punto de partida para el motor paralelo (Integrante 2).

PASOS:
  1. Copiar este archivo como  paralelo.py  (mismo directorio que gui.py).
  2. Implementar regla_actualizacion_paralela (y opcionalmente iniciar/finalizar).
  3. Abrir la GUI (o pulsar "Recargar paralelo.py"): el motor aparece solo en
     la lista de la pestaña Simulación y en la pestaña Benchmark.

La GUI valida automáticamente que el resultado sea idéntico al secuencial;
si no lo es, la fila sale marcada en rojo como "Válido: NO".

Ver el contrato completo en motores.py / README.md.
"""

import numpy as np

# Opcional: nombre que aparece en la GUI
NOMBRE = "Paralelo (Threads)"


def iniciar(num_hilos: int) -> None:
    """Opcional. Se llama una vez antes de una serie de generaciones.

    Lugar para crear el pool de hilos/procesos (o hacer MPI Spawn) y no pagar
    ese costo en cada generación. Su tiempo NO se incluye en las mediciones.
    """
    pass


def finalizar() -> None:
    """Opcional. Se llama una vez al terminar. Cerrar pool / liberar recursos."""
    pass


def regla_actualizacion_paralela(matriz: np.ndarray, filas: int, columnas: int,
                                 num_hilos: int) -> np.ndarray:
    """Calcula la generación t+1 repartiendo el trabajo entre `num_hilos`.

    - NO modificar `matriz` (es el estado t, solo lectura).
    - Retornar una matriz NUEVA (filas x columnas) con valores 0/1.
    - Bordes fijos: fuera de la matriz cuenta como célula muerta
      (igual que secuencial.vecincos_vivos).

    Idea de división por filas:
        bloque k -> filas [k*filas//num_hilos, (k+1)*filas//num_hilos)
    Cada trabajador lee de `matriz` y escribe solo sus filas en `nueva`,
    así no hay escrituras compartidas. La barrera entre generaciones es
    implícita: esta función no retorna hasta que todos terminaron.
    """
    raise NotImplementedError("Implementar la versión paralela")
