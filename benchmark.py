from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

import numpy as np

from motores import Motor, cargar_motores

COLUMNAS_CSV = [
    "tamanio", "filas", "columnas", "motor", "hilos", "generaciones",
    "repeticiones", "tiempo_total_s", "tiempo_gen_ms", "desviacion_s",
    "speedup", "eficiencia", "valido",
]


@dataclass
class Config:
    tamanios: list[int] = field(default_factory=lambda: [100, 500, 1000])
    hilos: list[int] = field(default_factory=lambda: [2, 4, 8])
    generaciones: int = 5
    repeticiones: int = 1
    motores: Optional[list[str]] = None  # claves; None = todos los paralelos
    semilla: int = 42
    densidad: float = 0.5


def matriz_inicial(n: int, semilla: int, densidad: float) -> np.ndarray:
    rng = np.random.default_rng(semilla)
    return (rng.random((n, n)) < densidad).astype(np.uint8)


def _medir(motor: Motor, inicial: np.ndarray, hilos: int, generaciones: int, repeticiones: int):
    tiempos = []
    final = None
    motor.preparar(hilos)
    try:
        for _ in range(repeticiones):
            m = inicial.copy()
            t0 = time.perf_counter()
            for _ in range(generaciones):
                m = motor.siguiente(m, hilos)
            tiempos.append(time.perf_counter() - t0)
            final = m
    finally:
        motor.liberar()
    desv = statistics.stdev(tiempos) if len(tiempos) > 1 else 0.0
    return statistics.mean(tiempos), desv, final


def correr_benchmark(cfg: Config, callback: Callable[[dict], None] = lambda e: None) -> list[dict]:
    """Ejecuta el benchmark. `callback` recibe eventos {'tipo': ..., ...}."""
    motores, aviso = cargar_motores()
    if aviso:
        callback({"tipo": "aviso", "mensaje": aviso})

    secuencial = motores[0]
    paralelos = [m for m in motores if m.es_paralelo]
    if cfg.motores is not None:
        paralelos = [m for m in paralelos if m.clave in cfg.motores]

    tareas = len(cfg.tamanios) * (1 + len(paralelos) * len(cfg.hilos))
    hechas = 0
    resultados: list[dict] = []

    for n in cfg.tamanios:
        inicial = matriz_inicial(n, cfg.semilla, cfg.densidad)

        def fila(motor, hilos, t, desv, speedup, valido):
            return {
                "tamanio": f"{n}x{n}", "filas": n, "columnas": n,
                "motor": motor.nombre, "hilos": hilos,
                "generaciones": cfg.generaciones, "repeticiones": cfg.repeticiones,
                "tiempo_total_s": t, "tiempo_gen_ms": t / cfg.generaciones * 1000,
                "desviacion_s": desv, "speedup": speedup,
                "eficiencia": speedup / hilos, "valido": valido,
            }

        callback({"tipo": "progreso", "hechas": hechas, "total": tareas,
                  "mensaje": f"{n}x{n} - {secuencial.nombre}"})
        t_seq, desv, ref = _medir(secuencial, inicial, 1, cfg.generaciones, cfg.repeticiones)
        r = fila(secuencial, 1, t_seq, desv, 1.0, True)
        resultados.append(r)
        hechas += 1
        callback({"tipo": "resultado", "fila": r, "hechas": hechas, "total": tareas})

        for motor in paralelos:
            for h in cfg.hilos:
                callback({"tipo": "progreso", "hechas": hechas, "total": tareas,
                          "mensaje": f"{n}x{n} - {motor.nombre} - {h} hilos"})
                try:
                    t, desv, final = _medir(motor, inicial, h, cfg.generaciones, cfg.repeticiones)
                    r = fila(motor, h, t, desv, t_seq / t if t > 0 else 0.0,
                             bool(np.array_equal(final, ref)))
                    resultados.append(r)
                    callback({"tipo": "resultado", "fila": r, "hechas": hechas + 1, "total": tareas})
                except Exception as e:  # un motor roto no tumba el benchmark
                    callback({"tipo": "error", "mensaje": f"{motor.nombre} ({h} hilos, {n}x{n}): {e!r}"})
                hechas += 1

    callback({"tipo": "fin", "hechas": hechas, "total": tareas})
    return resultados

# CSV
def guardar_csv(resultados: list[dict], ruta: str) -> None:
    with open(ruta, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNAS_CSV)
        w.writeheader()
        for r in resultados:
            w.writerow({k: r.get(k) for k in COLUMNAS_CSV})


def cargar_csv(ruta: str) -> list[dict]:
    enteros = {"filas", "columnas", "hilos", "generaciones", "repeticiones"}
    reales = {"tiempo_total_s", "tiempo_gen_ms", "desviacion_s", "speedup", "eficiencia"}
    filas = []
    with open(ruta, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            for k in enteros & r.keys():
                r[k] = int(r[k])
            for k in reales & r.keys():
                r[k] = float(r[k])
            r["valido"] = str(r.get("valido", "True")).lower() in ("true", "1", "si", "sí")
            filas.append(r)
    return filas


# CLI
def main(argv=None) -> None:
    p = argparse.ArgumentParser(description="Benchmark Juego de la Vida")
    p.add_argument("--tamanios", type=int, nargs="+", default=[100, 500, 1000])
    p.add_argument("--hilos", type=int, nargs="+", default=[2, 4, 8])
    p.add_argument("--generaciones", type=int, default=5)
    p.add_argument("--repeticiones", type=int, default=1)
    p.add_argument("--motores", nargs="*", default=None, help="claves de motores paralelos")
    p.add_argument("--semilla", type=int, default=42)
    p.add_argument("--densidad", type=float, default=0.5)
    p.add_argument("--salida", default="resultados.csv")
    p.add_argument("--jsonl", action="store_true", help="eventos JSON por stdout (lo usa la GUI)")
    a = p.parse_args(argv)

    cfg = Config(a.tamanios, a.hilos, a.generaciones, a.repeticiones,
                 a.motores, a.semilla, a.densidad)

    def cb(ev):
        if a.jsonl:
            print(json.dumps(ev), flush=True)
        elif ev["tipo"] == "resultado":
            r = ev["fila"]
            print(f"{r['tamanio']:<10} {r['motor']:<22} hilos={r['hilos']:<3} "
                  f"total={r['tiempo_total_s']:.4f}s  gen={r['tiempo_gen_ms']:.2f}ms  "
                  f"S={r['speedup']:.2f}  E={r['eficiencia']:.2f}  "
                  f"{'OK' if r['valido'] else 'RESULTADO DISTINTO'}")
        elif ev["tipo"] in ("aviso", "error"):
            print(f"[{ev['tipo']}] {ev['mensaje']}", file=sys.stderr)

    resultados = correr_benchmark(cfg, cb)
    if a.salida:
        guardar_csv(resultados, a.salida)
        if not a.jsonl:
            print(f"\nResultados guardados en {a.salida}")


if __name__ == "__main__":
    main()
