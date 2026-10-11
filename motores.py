"""
motores.py - Contrato entre los motores de cómputo y la GUI / benchmark.

La GUI y el benchmark NUNCA importan secuencial.py o paralelo.py directamente:
solo hablan con objetos `Motor` que este módulo construye. Así, cuando llegue
la versión paralela, basta con crear `paralelo.py` cumpliendo el contrato y la
GUI la detecta sola, sin tocar una línea de gui.py.

------------------------------------------------------------------------------
CONTRATO PARA paralelo.py (Integrante 2)
------------------------------------------------------------------------------
Obligatorio:

    def regla_actualizacion_paralela(matriz, filas, columnas, num_hilos):
        '''
        matriz     : np.ndarray 2D (filas x columnas) con valores 0/1.
                     NO se debe modificar (se lee de t, se escribe en t+1).
        filas      : int
        columnas   : int
        num_hilos  : int >= 1, cantidad de hilos/procesos a usar.
        return     : np.ndarray NUEVO de la misma forma con la generación t+1.
        '''

    Es la misma firma de `regla_actualizacion` de secuencial.py con un
    parámetro extra al final, y debe dar EXACTAMENTE el mismo resultado
    (bordes fijos: fuera de la matriz cuenta como célula muerta).

Opcional:

    NOMBRE = "Paralelo (Threads)"      # texto que muestra la GUI

    def iniciar(num_hilos): ...        # crear pool de hilos/procesos, MPI spawn...
    def finalizar(): ...               # cerrar pool / liberar recursos

    `iniciar` se llama una vez antes de una serie de generaciones y
    `finalizar` una vez al terminar. El tiempo de iniciar/finalizar NO entra
    en las mediciones de rendimiento (solo se mide la llamada a la regla).

Varios motores en un mismo archivo (ej. threads y multiprocessing):

    from motores import Motor
    MOTORES = [Motor(nombre=..., paso=..., es_paralelo=True, ...), ...]

    Si paralelo.py define MOTORES, se usa esa lista en lugar de la función.
------------------------------------------------------------------------------
"""

from __future__ import annotations

import importlib
import sys
import traceback
from dataclasses import dataclass, field
from typing import Callable, Optional

import numpy as np

# Firma uniforme que la GUI usa internamente:
#   paso(matriz, num_hilos) -> nueva_matriz
FuncionPaso = Callable[[np.ndarray, int], np.ndarray]


@dataclass
class Motor:
    nombre: str
    paso: FuncionPaso
    es_paralelo: bool = False
    iniciar: Optional[Callable[[int], None]] = None
    finalizar: Optional[Callable[[], None]] = None
    descripcion: str = ""
    clave: str = field(default="")

    def __post_init__(self):
        if not self.clave:
            self.clave = self.nombre.lower().replace(" ", "_")

    # Helpers usados por la GUI y el benchmark --------------------------------
    def preparar(self, num_hilos: int) -> None:
        if self.iniciar is not None:
            self.iniciar(num_hilos)

    def liberar(self) -> None:
        if self.finalizar is not None:
            self.finalizar()

    def siguiente(self, matriz: np.ndarray, num_hilos: int = 1) -> np.ndarray:
        """Calcula t+1 y valida que el motor respete el contrato."""
        nueva = self.paso(matriz, num_hilos)
        if not isinstance(nueva, np.ndarray):
            raise TypeError(f"[{self.nombre}] debe retornar np.ndarray, retornó {type(nueva).__name__}")
        if nueva.shape != matriz.shape:
            raise ValueError(f"[{self.nombre}] retornó forma {nueva.shape}, se esperaba {matriz.shape}")
        if nueva is matriz:
            raise ValueError(f"[{self.nombre}] retornó la misma matriz de entrada; debe retornar una nueva")
        return nueva


# ---------------------------------------------------------------------------
# Adaptadores
# ---------------------------------------------------------------------------
def _motor_secuencial() -> Motor:
    import secuencial

    def paso(matriz: np.ndarray, _num_hilos: int) -> np.ndarray:
        filas, columnas = matriz.shape
        return secuencial.regla_actualizacion(matriz, filas, columnas)

    return Motor(
        nombre="Secuencial",
        paso=paso,
        es_paralelo=False,
        descripcion="secuencial.regla_actualizacion (baseline)",
        clave="secuencial",
    )


def _motores_paralelos(recargar: bool = False) -> tuple[list[Motor], Optional[str]]:
    """Intenta cargar paralelo.py. Retorna (motores, mensaje_de_error)."""
    try:
        if recargar and "paralelo" in sys.modules:
            mod = importlib.reload(sys.modules["paralelo"])
        else:
            mod = importlib.import_module("paralelo")
    except ModuleNotFoundError as e:
        if e.name == "paralelo":
            return [], None  # todavía no existe: no es un error
        return [], f"paralelo.py importa un módulo que falta: {e.name}"
    except Exception:
        return [], "Error al importar paralelo.py:\n" + traceback.format_exc()

    if hasattr(mod, "MOTORES"):
        motores = list(mod.MOTORES)
        for m in motores:
            if not isinstance(m, Motor):
                return [], "paralelo.MOTORES debe contener objetos motores.Motor"
        return motores, None

    if not hasattr(mod, "regla_actualizacion_paralela"):
        return [], "paralelo.py existe pero no define regla_actualizacion_paralela(matriz, filas, columnas, num_hilos)"

    fn = mod.regla_actualizacion_paralela

    def paso(matriz: np.ndarray, num_hilos: int) -> np.ndarray:
        filas, columnas = matriz.shape
        return fn(matriz, filas, columnas, num_hilos)

    return [
        Motor(
            nombre=getattr(mod, "NOMBRE", "Paralelo"),
            paso=paso,
            es_paralelo=True,
            iniciar=getattr(mod, "iniciar", None),
            finalizar=getattr(mod, "finalizar", None),
            descripcion="paralelo.regla_actualizacion_paralela",
            clave="paralelo",
        )
    ], None


def cargar_motores(recargar: bool = False) -> tuple[list[Motor], Optional[str]]:
    """Retorna la lista de motores disponibles y un aviso (o None).

    recargar=True vuelve a leer paralelo.py del disco (botón "Recargar" de la GUI).
    """
    motores = [_motor_secuencial()]
    paralelos, aviso = _motores_paralelos(recargar)
    motores.extend(paralelos)
    return motores, aviso


def buscar_motor(motores: list[Motor], clave: str) -> Motor:
    for m in motores:
        if m.clave == clave:
            return m
    raise KeyError(f"No existe el motor '{clave}'. Disponibles: {[m.clave for m in motores]}")
