from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure

import graficas
from benchmark import cargar_csv, guardar_csv
from motores import Motor, cargar_motores

DIR = os.path.dirname(os.path.abspath(__file__))

FONDO_CANVAS = "#14171c"
COLOR_MUERTA = np.array([0x1c, 0x20, 0x26], dtype=np.uint8)
COLOR_VIVA = np.array([0x4c, 0xd6, 0x9b], dtype=np.uint8)
COLOR_REJILLA = np.array([0x2a, 0x2f, 0x37], dtype=np.uint8)

PLANEADOR = [(0, 1), (1, 2), (2, 0), (2, 1), (2, 2)]
R_PENTOMINO = [(0, 1), (0, 2), (1, 0), (1, 1), (2, 1)]
CANION_GOSPER = [
    (5, 1), (5, 2), (6, 1), (6, 2), (5, 11), (6, 11), (7, 11), (4, 12), (8, 12),
    (3, 13), (9, 13), (3, 14), (9, 14), (6, 15), (4, 16), (8, 16), (5, 17), (6, 17),
    (7, 17), (6, 18), (3, 21), (4, 21), (5, 21), (3, 22), (4, 22), (5, 22), (2, 23),
    (6, 23), (1, 25), (2, 25), (6, 25), (7, 25), (3, 35), (4, 35), (3, 36), (4, 36),
]


def _pulsar():
    celdas = set()
    for a in (0, 5, 7, 12):
        for b in (2, 3, 4, 8, 9, 10):
            celdas.add((a, b))
            celdas.add((b, a))
    return sorted(celdas)


PATRONES = ["Aleatorio", "Vacío", "Planeador", "R-pentomino", "Pulsar", "Cañón de Gosper"]
TAMANIOS_SIM = ["50", "100", "200", "500", "1000"]


def crear_matriz(n: int, patron: str, densidad: float, semilla=None) -> np.ndarray:
    m = np.zeros((n, n), dtype=np.uint8)
    if patron == "Aleatorio":
        rng = np.random.default_rng(semilla)
        return (rng.random((n, n)) < densidad).astype(np.uint8)
    celdas = {
        "Planeador": PLANEADOR, "R-pentomino": R_PENTOMINO,
        "Pulsar": _pulsar(), "Cañón de Gosper": CANION_GOSPER,
    }.get(patron, [])
    if not celdas:
        return m
    alto = max(r for r, _ in celdas) + 1
    ancho = max(c for _, c in celdas) + 1
    if alto > n or ancho > n:
        raise ValueError(f"El patrón '{patron}' necesita al menos {max(alto, ancho)}x{max(alto, ancho)}")
    if patron in ("Cañón de Gosper", "Planeador"):
        r0, c0 = min(2, n - alto), min(2, n - ancho)
    else:
        r0, c0 = (n - alto) // 2, (n - ancho) // 2
    for r, c in celdas:
        m[r0 + r, c0 + c] = 1
    return m


def matriz_a_ppm(m: np.ndarray, ancho: int, alto: int, rejilla: bool):
    """Escala la matriz al tamaño del lienzo (vecino más cercano) y la codifica PPM.

    Retorna (bytes_ppm, x0, y0, px_por_celda_x, px_por_celda_y).
    """
    filas, cols = m.shape
    celda = min(ancho / cols, alto / filas)
    w = max(1, int(cols * celda))
    h = max(1, int(filas * celda))
    ri = (np.arange(h) * filas) // h
    ci = (np.arange(w) * cols) // w
    vis = m[np.ix_(ri, ci)].astype(bool)
    rgb = np.where(vis[..., None], COLOR_VIVA, COLOR_MUERTA)
    if rejilla and celda >= 6:
        bordes_f = np.flatnonzero(np.diff(ri, prepend=-1))
        bordes_c = np.flatnonzero(np.diff(ci, prepend=-1))
        rgb[bordes_f, :, :] = COLOR_REJILLA
        rgb[:, bordes_c, :] = COLOR_REJILLA
    datos = f"P6 {w} {h} 255\n".encode() + np.ascontiguousarray(rgb, dtype=np.uint8).tobytes()
    return datos, (ancho - w) // 2, (alto - h) // 2, w / cols, h / filas


class Simulador(threading.Thread):
    """Calcula generaciones con un Motor y las envía a la GUI por una cola.

    Trabaja en lockstep con la GUI: calcula una generación, la entrega y espera
    a que la GUI la dibuje y cumpla el retardo antes de calcular la siguiente.
    Solo la llamada al motor se cronometra.
    """

    def __init__(self, motor: Motor, hilos: int, matriz: np.ndarray, salida: queue.Queue, max_gen=None):
        super().__init__(daemon=True)
        self.motor, self.hilos, self.matriz = motor, hilos, matriz.copy()
        self.salida, self.max_gen = salida, max_gen
        self.continuar = threading.Event()
        self.continuar.set()
        self.detener = threading.Event()

    def run(self):
        try:
            self.motor.preparar(self.hilos)
        except Exception as e:
            self.salida.put(("error", f"iniciar() de {self.motor.nombre} falló:\n{e!r}"))
            self.salida.put(("fin", None))
            return
        hechas = 0
        try:
            while not self.detener.is_set():
                self.continuar.wait()
                if self.detener.is_set():
                    break
                self.continuar.clear()
                t0 = time.perf_counter()
                self.matriz = self.motor.siguiente(self.matriz, self.hilos)
                dt = time.perf_counter() - t0
                self.salida.put(("generacion", (self.matriz, dt)))
                hechas += 1
                if self.max_gen is not None and hechas >= self.max_gen:
                    break
        except Exception as e:
            self.salida.put(("error", f"{self.motor.nombre} falló calculando la generación:\n{e!r}"))
        finally:
            try:
                self.motor.liberar()
            except Exception as e:
                self.salida.put(("error", f"finalizar() de {self.motor.nombre} falló:\n{e!r}"))
            self.salida.put(("fin", None))

    def parar(self):
        self.detener.set()
        self.continuar.set()


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Juego de la Vida - Infraestructuras Paralelas y Distribuidas")
        self.geometry("1200x820")
        self.minsize(980, 640)
        ttk.Style(self).theme_use("clam")

        self.motores: list[Motor] = []
        self.matriz = crear_matriz(100, "Aleatorio", 0.3)
        self.generacion = 0
        self.tiempos_gen: list[float] = []
        self.sim: Simulador | None = None
        self.cola_sim: queue.Queue = queue.Queue()
        self._ultimo_frame = time.perf_counter()
        self._fps = 0.0
        self._foto = None
        self._geom = (0, 0, 1.0, 1.0)

        self.resultados: list[dict] = []
        self.proc: subprocess.Popen | None = None
        self.cola_bench: queue.Queue = queue.Queue()

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True)
        self.tab_sim = ttk.Frame(nb, padding=8)
        self.tab_bench = ttk.Frame(nb, padding=8)
        self.tab_graf = ttk.Frame(nb, padding=8)
        nb.add(self.tab_sim, text="  Simulación  ")
        nb.add(self.tab_bench, text="  Benchmark  ")
        nb.add(self.tab_graf, text="  Gráficas  ")

        self._construir_simulacion()
        self._construir_benchmark()
        self._construir_graficas()
        self.recargar_motores(inicial=True)

        self.after(15, self._atender_colas)
        self.protocol("WM_DELETE_WINDOW", self._cerrar)

    def recargar_motores(self, inicial=False):
        self.motores, aviso = cargar_motores(recargar=not inicial)
        nombres = [m.nombre for m in self.motores]
        self.cb_motor["values"] = nombres
        if self.var_motor.get() not in nombres:
            self.var_motor.set(nombres[0])
        self._al_cambiar_motor()

        paralelos = [m for m in self.motores if m.es_paralelo]
        if paralelos:
            self.lbl_motores.config(text="Paralelos detectados: " + ", ".join(m.nombre for m in paralelos),
                                    foreground="#1e7a4f")
        else:
            self.lbl_motores.config(text="Sin motor paralelo (falta paralelo.py)", foreground="#a06000")
        self._refrescar_checks_motores()
        if aviso:
            self._log(aviso)
            if not inicial:
                messagebox.showwarning("paralelo.py", aviso)

    def motor_actual(self) -> Motor:
        return next(m for m in self.motores if m.nombre == self.var_motor.get())

    def _construir_simulacion(self):
        t = self.tab_sim
        t.columnconfigure(0, weight=1)
        t.rowconfigure(0, weight=1)

        self.canvas = tk.Canvas(t, bg=FONDO_CANVAS, highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.canvas.bind("<Configure>", lambda e: self._dibujar())
        for ev, val in (("<Button-1>", 1), ("<B1-Motion>", 1), ("<Button-3>", 0), ("<B3-Motion>", 0)):
            self.canvas.bind(ev, lambda e, v=val: self._editar_celda(e, v))

        p = ttk.Frame(t, padding=(12, 0, 0, 0))
        p.grid(row=0, column=1, sticky="ns")

        f = ttk.LabelFrame(p, text="Motor", padding=8)
        f.pack(fill="x", pady=(0, 6))
        self.var_motor = tk.StringVar()
        self.cb_motor = ttk.Combobox(f, textvariable=self.var_motor, state="readonly", width=26)
        self.cb_motor.pack(fill="x")
        self.cb_motor.bind("<<ComboboxSelected>>", lambda e: self._al_cambiar_motor())
        fh = ttk.Frame(f)
        fh.pack(fill="x", pady=(6, 0))
        ttk.Label(fh, text="Hilos / procesos:").pack(side="left")
        self.var_hilos = tk.IntVar(value=min(4, os.cpu_count() or 1))
        self.sp_hilos = ttk.Spinbox(fh, from_=1, to=128, textvariable=self.var_hilos, width=5)
        self.sp_hilos.pack(side="right")
        self.lbl_motores = ttk.Label(f, text="", wraplength=220, font=("TkDefaultFont", 8))
        self.lbl_motores.pack(fill="x", pady=(6, 0))
        self.btn_recargar = ttk.Button(f, text="Recargar paralelo.py", command=self.recargar_motores)
        self.btn_recargar.pack(fill="x", pady=(4, 0))

        f = ttk.LabelFrame(p, text="Tablero", padding=8)
        f.pack(fill="x", pady=(0, 6))
        f.columnconfigure(1, weight=1)
        ttk.Label(f, text="Tamaño (n x n):").grid(row=0, column=0, sticky="w")
        self.var_tam = tk.StringVar(value="100")
        self.cb_tam = ttk.Combobox(f, textvariable=self.var_tam, values=TAMANIOS_SIM, width=8)
        self.cb_tam.grid(row=0, column=1, sticky="e")
        ttk.Label(f, text="Patrón inicial:").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.var_patron = tk.StringVar(value="Aleatorio")
        self.cb_patron = ttk.Combobox(f, textvariable=self.var_patron, values=PATRONES,
                                      state="readonly", width=15)
        self.cb_patron.grid(row=1, column=1, sticky="e", pady=(6, 0))
        ttk.Label(f, text="Densidad aleatoria:").grid(row=2, column=0, sticky="w", pady=(6, 0))
        self.var_dens = tk.DoubleVar(value=0.30)
        self.lbl_dens = ttk.Label(f, text="30 %")
        self.lbl_dens.grid(row=2, column=1, sticky="e", pady=(6, 0))
        ttk.Scale(f, from_=0.05, to=0.9, variable=self.var_dens,
                  command=lambda v: self.lbl_dens.config(text=f"{float(v) * 100:.0f} %")
                  ).grid(row=3, column=0, columnspan=2, sticky="ew")
        self.btn_aplicar = ttk.Button(f, text="Generar tablero", command=self.reiniciar)
        self.btn_aplicar.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        self.var_rejilla = tk.BooleanVar(value=True)
        ttk.Checkbutton(f, text="Mostrar rejilla (tableros pequeños)", variable=self.var_rejilla,
                        command=self._dibujar).grid(row=5, column=0, columnspan=2, sticky="w", pady=(6, 0))
        ttk.Label(f, text="Clic izq.: revivir  |  Clic der.: matar\n(con la simulación en pausa)",
                  font=("TkDefaultFont", 8), foreground="#666").grid(row=6, column=0, columnspan=2,
                                                                      sticky="w", pady=(4, 0))

        f = ttk.LabelFrame(p, text="Control", padding=8)
        f.pack(fill="x", pady=(0, 6))
        fb = ttk.Frame(f)
        fb.pack(fill="x")
        self.btn_play = ttk.Button(fb, text="Iniciar", command=self.alternar)
        self.btn_play.pack(side="left", expand=True, fill="x")
        self.btn_paso = ttk.Button(fb, text="Paso", command=self.un_paso)
        self.btn_paso.pack(side="left", expand=True, fill="x", padx=4)
        self.btn_limpiar = ttk.Button(fb, text="Limpiar", command=self.limpiar)
        self.btn_limpiar.pack(side="left", expand=True, fill="x")
        ttk.Label(f, text="Retardo entre generaciones:").pack(anchor="w", pady=(8, 0))
        self.var_retardo = tk.IntVar(value=100)
        self.lbl_ret = ttk.Label(f, text="100 ms")
        self.lbl_ret.pack(anchor="e")
        ttk.Scale(f, from_=0, to=1000, variable=self.var_retardo,
                  command=lambda v: self.lbl_ret.config(text=f"{int(float(v))} ms")).pack(fill="x")

        # Estadísticas
        f = ttk.LabelFrame(p, text="Estadísticas", padding=8)
        f.pack(fill="x")
        self.stats = {}
        for i, (k, et) in enumerate([("gen", "Generación"), ("vivas", "Células vivas"),
                                     ("t_ult", "Cómputo última gen."), ("t_prom", "Cómputo promedio"),
                                     ("fps", "Generaciones / s")]):
            ttk.Label(f, text=et + ":").grid(row=i, column=0, sticky="w")
            self.stats[k] = ttk.Label(f, text="-", font=("TkFixedFont", 10))
            self.stats[k].grid(row=i, column=1, sticky="e", padx=(12, 0))
        ttk.Label(f, text="Tiempos referenciales; para medir use\nla pestaña Benchmark.",
                  font=("TkDefaultFont", 8), foreground="#666").grid(row=5, column=0, columnspan=2,
                                                                      sticky="w", pady=(4, 0))
        self._actualizar_stats()

    def _al_cambiar_motor(self):
        if not self.motores:
            return
        self.sp_hilos.config(state="normal" if self.motor_actual().es_paralelo else "disabled")

    def _hilos(self) -> int:
        try:
            return max(1, int(self.var_hilos.get()))
        except (tk.TclError, ValueError):
            return 1

    def _bloquear_controles(self, ocupado: bool):
        estado = "disabled" if ocupado else "normal"
        for w in (self.btn_aplicar, self.btn_paso, self.btn_limpiar, self.btn_recargar, self.cb_tam):
            w.config(state=estado)
        self.cb_motor.config(state="disabled" if ocupado else "readonly")
        self.cb_patron.config(state="disabled" if ocupado else "readonly")
        if ocupado:
            self.sp_hilos.config(state="disabled")
        else:
            self._al_cambiar_motor()

    # ---------------------------------------------------------------- acciones
    def reiniciar(self):
        try:
            n = int(self.var_tam.get())
            if not 5 <= n <= 3000:
                raise ValueError("El tamaño debe estar entre 5 y 3000")
            self.matriz = crear_matriz(n, self.var_patron.get(), float(self.var_dens.get()))
        except ValueError as e:
            messagebox.showerror("Tablero", str(e))
            return
        self.generacion = 0
        self.tiempos_gen.clear()
        self._fps = 0.0
        self._dibujar()
        self._actualizar_stats()

    def limpiar(self):
        self.matriz = np.zeros_like(self.matriz)
        self.generacion = 0
        self.tiempos_gen.clear()
        self._dibujar()
        self._actualizar_stats()

    def alternar(self):
        if self.sim is not None:
            self.sim.parar()
            self.btn_play.config(text="Deteniendo...", state="disabled")
        else:
            self._lanzar(max_gen=None)

    def un_paso(self):
        if self.sim is None:
            self._lanzar(max_gen=1)

    def _lanzar(self, max_gen):
        self.sim = Simulador(self.motor_actual(), self._hilos(), self.matriz, self.cola_sim, max_gen)
        self._bloquear_controles(True)
        if max_gen is None:
            self.btn_play.config(text="Pausar")
        else:
            self.btn_play.config(state="disabled")
        self._ultimo_frame = time.perf_counter()
        self.sim.start()

    def _editar_celda(self, evento, valor):
        if self.sim is not None:
            return
        x0, y0, cw, ch = self._geom
        j = int((evento.x - x0) // cw)
        i = int((evento.y - y0) // ch)
        filas, cols = self.matriz.shape
        if 0 <= i < filas and 0 <= j < cols and self.matriz[i, j] != valor:
            self.matriz[i, j] = valor
            self._dibujar()
            self._actualizar_stats()

    # ---------------------------------------------------------------- render
    def _dibujar(self):
        w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
        if w < 10 or h < 10:
            return
        datos, x0, y0, cw, ch = matriz_a_ppm(self.matriz, w, h, self.var_rejilla.get())
        self._foto = tk.PhotoImage(data=datos, format="PPM")
        self._geom = (x0, y0, cw, ch)
        self.canvas.delete("all")
        self.canvas.create_image(x0, y0, image=self._foto, anchor="nw")

    def _actualizar_stats(self):
        s = self.stats
        n_f, n_c = self.matriz.shape
        s["gen"].config(text=f"{self.generacion}")
        vivas = int(self.matriz.sum())
        s["vivas"].config(text=f"{vivas:,} ({vivas / self.matriz.size * 100:.1f} %)")
        if self.tiempos_gen:
            s["t_ult"].config(text=f"{self.tiempos_gen[-1] * 1000:,.2f} ms")
            s["t_prom"].config(text=f"{np.mean(self.tiempos_gen) * 1000:,.2f} ms")
        else:
            s["t_ult"].config(text="-")
            s["t_prom"].config(text="-")
        s["fps"].config(text=f"{self._fps:.1f}" if self._fps else "-")

    # ================================================================== BENCHMARK
    def _construir_benchmark(self):
        t = self.tab_bench
        t.columnconfigure(1, weight=1)
        t.rowconfigure(0, weight=1)

        izq = ttk.Frame(t)
        izq.grid(row=0, column=0, sticky="ns", padx=(0, 10))

        f = ttk.LabelFrame(izq, text="Configuración", padding=8)
        f.pack(fill="x")
        self.b_vars = {}
        campos = [
            ("tamanios", "Tamaños (n):", "100 500 1000"),
            ("hilos", "Hilos / procesos:", "2 4 8"),
            ("generaciones", "Generaciones:", "5"),
            ("repeticiones", "Repeticiones:", "1"),
            ("semilla", "Semilla:", "42"),
        ]
        for i, (k, et, val) in enumerate(campos):
            ttk.Label(f, text=et).grid(row=i, column=0, sticky="w", pady=2)
            v = tk.StringVar(value=val)
            ttk.Entry(f, textvariable=v, width=16).grid(row=i, column=1, sticky="e", pady=2)
            self.b_vars[k] = v
        ttk.Label(f, text="Listas separadas por espacio o coma.", font=("TkDefaultFont", 8),
                  foreground="#666").grid(row=len(campos), column=0, columnspan=2, sticky="w")

        self.f_checks = ttk.LabelFrame(izq, text="Motores paralelos a medir", padding=8)
        self.f_checks.pack(fill="x", pady=8)
        self.checks_motores: dict[str, tk.BooleanVar] = {}

        f = ttk.Frame(izq)
        f.pack(fill="x")
        self.btn_bench = ttk.Button(f, text="Ejecutar benchmark", command=self.ejecutar_benchmark)
        self.btn_bench.pack(fill="x")
        self.btn_cancelar = ttk.Button(f, text="Cancelar", command=self.cancelar_benchmark, state="disabled")
        self.btn_cancelar.pack(fill="x", pady=(4, 12))
        ttk.Button(f, text="Importar CSV...", command=self.importar_csv).pack(fill="x")
        ttk.Button(f, text="Exportar CSV...", command=self.exportar_csv).pack(fill="x", pady=4)
        ttk.Button(f, text="Limpiar resultados", command=self.limpiar_resultados).pack(fill="x")

        der = ttk.Frame(t)
        der.grid(row=0, column=1, sticky="nsew")
        der.columnconfigure(0, weight=1)
        der.rowconfigure(1, weight=1)

        fp = ttk.Frame(der)
        fp.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        fp.columnconfigure(0, weight=1)
        self.progreso = ttk.Progressbar(fp, mode="determinate")
        self.progreso.grid(row=0, column=0, sticky="ew")
        self.lbl_estado = ttk.Label(fp, text="Listo.", width=46, anchor="w")
        self.lbl_estado.grid(row=0, column=1, padx=(8, 0))

        cols = [("tamanio", "Tamaño", 80), ("motor", "Motor", 170), ("hilos", "Hilos", 55),
                ("tiempo_total_s", "Total (s)", 90), ("tiempo_gen_ms", "Por gen. (ms)", 100),
                ("speedup", "Speedup", 75), ("eficiencia", "Eficiencia", 80), ("valido", "Válido", 65)]
        self.tree = ttk.Treeview(der, columns=[c[0] for c in cols], show="headings")
        for k, et, ancho in cols:
            self.tree.heading(k, text=et)
            self.tree.column(k, width=ancho, anchor={"motor": "w", "valido": "center"}.get(k, "e"))
        self.tree.tag_configure("invalido", background="#f8d7da")
        self.tree.tag_configure("secuencial", background="#eef1f5")
        sb = ttk.Scrollbar(der, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.grid(row=1, column=0, sticky="nsew")
        sb.grid(row=1, column=1, sticky="ns")

        ttk.Label(der, text="Registro:").grid(row=2, column=0, sticky="w", pady=(8, 0))
        self.txt_log = tk.Text(der, height=6, font=("TkFixedFont", 9), wrap="word")
        self.txt_log.grid(row=3, column=0, columnspan=2, sticky="ew")

    def _refrescar_checks_motores(self):
        for w in self.f_checks.winfo_children():
            w.destroy()
        paralelos = [m for m in self.motores if m.es_paralelo]
        previos = self.checks_motores
        self.checks_motores = {}
        ttk.Label(self.f_checks, text="Secuencial (baseline, siempre)").pack(anchor="w")
        for m in paralelos:
            v = tk.BooleanVar(value=previos[m.clave].get() if m.clave in previos else True)
            ttk.Checkbutton(self.f_checks, text=m.nombre, variable=v).pack(anchor="w")
            self.checks_motores[m.clave] = v
        if not paralelos:
            ttk.Label(self.f_checks, text="Ninguno detectado todavía.",
                      foreground="#a06000").pack(anchor="w")

    def _log(self, texto):
        self.txt_log.insert("end", time.strftime("[%H:%M:%S] ") + texto.rstrip() + "\n")
        self.txt_log.see("end")

    @staticmethod
    def _lista_enteros(texto, nombre):
        try:
            vals = [int(x) for x in texto.replace(",", " ").split()]
        except ValueError:
            raise ValueError(f"'{nombre}' debe ser una lista de enteros")
        if not vals or min(vals) < 1:
            raise ValueError(f"'{nombre}' debe tener valores >= 1")
        return vals

    def ejecutar_benchmark(self):
        if self.proc is not None:
            return
        v = self.b_vars
        try:
            tam = self._lista_enteros(v["tamanios"].get(), "Tamaños")
            hilos = self._lista_enteros(v["hilos"].get(), "Hilos")
            gens = self._lista_enteros(v["generaciones"].get(), "Generaciones")[0]
            reps = self._lista_enteros(v["repeticiones"].get(), "Repeticiones")[0]
            semilla = int(v["semilla"].get())
        except ValueError as e:
            messagebox.showerror("Benchmark", str(e))
            return

        claves = [k for k, var in self.checks_motores.items() if var.get()]
        cmd = [sys.executable, "-u", os.path.join(DIR, "benchmark.py"), "--jsonl", "--salida", "",
               "--tamanios", *map(str, tam), "--hilos", *map(str, hilos),
               "--generaciones", str(gens), "--repeticiones", str(reps),
               "--semilla", str(semilla), "--motores", *claves]
        if max(tam) >= 1000:
            self._log("Aviso: la versión secuencial en 1000x1000 puede tardar varios segundos por generación.")
        self._log("Ejecutando: benchmark.py " + " ".join(cmd[4:]))

        try:
            self.proc = subprocess.Popen(cmd, cwd=DIR, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                         text=True, encoding="utf-8")
        except OSError as e:
            messagebox.showerror("Benchmark", f"No se pudo lanzar el benchmark:\n{e}")
            self.proc = None
            return

        def leer(flujo, tipo):
            for linea in flujo:
                self.cola_bench.put((tipo, linea))
            if tipo == "stdout":
                self.cola_bench.put(("salio", None))

        threading.Thread(target=leer, args=(self.proc.stdout, "stdout"), daemon=True).start()
        threading.Thread(target=leer, args=(self.proc.stderr, "stderr"), daemon=True).start()
        self.btn_bench.config(state="disabled")
        self.btn_cancelar.config(state="normal")
        self.progreso.config(value=0, maximum=1)
        self.lbl_estado.config(text="Iniciando...")

    def cancelar_benchmark(self):
        if self.proc is not None:
            self.proc.terminate()
            self._log("Benchmark cancelado por el usuario.")

    def _evento_benchmark(self, ev):
        tipo = ev.get("tipo")
        if tipo == "progreso":
            self.progreso.config(maximum=ev["total"], value=ev["hechas"])
            self.lbl_estado.config(text=f"[{ev['hechas'] + 1}/{ev['total']}] {ev['mensaje']}")
        elif tipo == "resultado":
            self.progreso.config(maximum=ev["total"], value=ev["hechas"])
            self._agregar_resultado(ev["fila"])
        elif tipo in ("aviso", "error"):
            self._log(f"{tipo.upper()}: {ev['mensaje']}")
        elif tipo == "fin":
            self.progreso.config(maximum=max(ev["total"], 1), value=ev["total"])
            self.lbl_estado.config(text=f"Terminado ({ev['hechas']}/{ev['total']}).")

    def _benchmark_terminado(self):
        if self.proc is None:
            return
        codigo = self.proc.wait()
        self.proc = None
        self.btn_bench.config(state="normal")
        self.btn_cancelar.config(state="disabled")
        if codigo != 0:
            self.lbl_estado.config(text=f"Proceso terminó con código {codigo}.")
        self.actualizar_graficas()

    # ---------------------------------------------------------------- resultados
    def _agregar_resultado(self, r, redibujar=False):
        clave = (r["filas"], r["motor"], r["hilos"])
        self.resultados = [x for x in self.resultados if (x["filas"], x["motor"], x["hilos"]) != clave]
        self.resultados.append(r)
        self._refrescar_tabla()
        if redibujar:
            self.actualizar_graficas()

    def _refrescar_tabla(self):
        self.tree.delete(*self.tree.get_children())
        orden = sorted(self.resultados, key=lambda r: (r["filas"], r["motor"] != "Secuencial",
                                                       r["motor"], r["hilos"]))
        for r in orden:
            tags = ()
            if not r["valido"]:
                tags = ("invalido",)
            elif r["motor"] == "Secuencial":
                tags = ("secuencial",)
            self.tree.insert("", "end", tags=tags, values=(
                r["tamanio"], r["motor"], r["hilos"], f"{r['tiempo_total_s']:.4f}",
                f"{r['tiempo_gen_ms']:.2f}", f"{r['speedup']:.2f}", f"{r['eficiencia']:.2f}",
                "Sí" if r["valido"] else "NO"))

    def importar_csv(self):
        ruta = filedialog.askopenfilename(title="Importar resultados", initialdir=DIR,
                                          filetypes=[("CSV", "*.csv"), ("Todos", "*.*")])
        if not ruta:
            return
        try:
            filas = cargar_csv(ruta)
        except Exception as e:
            messagebox.showerror("Importar CSV", f"No se pudo leer el archivo:\n{e}")
            return
        for r in filas:
            self._agregar_resultado(r)
        self.actualizar_graficas()
        self._log(f"Importadas {len(filas)} filas desde {os.path.basename(ruta)}")

    def exportar_csv(self):
        if not self.resultados:
            messagebox.showinfo("Exportar CSV", "No hay resultados todavía.")
            return
        ruta = filedialog.asksaveasfilename(title="Exportar resultados", initialdir=DIR,
                                            initialfile="resultados.csv", defaultextension=".csv",
                                            filetypes=[("CSV", "*.csv")])
        if ruta:
            guardar_csv(self.resultados, ruta)
            self._log(f"Resultados guardados en {ruta}")

    def limpiar_resultados(self):
        self.resultados.clear()
        self._refrescar_tabla()
        self.actualizar_graficas()

    # =================================================================== GRÁFICAS
    def _construir_graficas(self):
        t = self.tab_graf
        barra = ttk.Frame(t)
        barra.pack(fill="x", pady=(0, 6))
        ttk.Label(barra, text="Gráfica:").pack(side="left")
        self.var_graf = tk.StringVar(value="Tiempo vs. tamaño de matriz")
        self._mapa_graf = {
            "Tiempo vs. tamaño de matriz": "tiempo_vs_tamanio",
            "Speedup vs. número de hilos": "speedup_vs_hilos",
            "Eficiencia vs. número de hilos": "eficiencia_vs_hilos",
            "Las tres": "todas",
        }
        cb = ttk.Combobox(barra, textvariable=self.var_graf, values=list(self._mapa_graf),
                          state="readonly", width=30)
        cb.pack(side="left", padx=6)
        cb.bind("<<ComboboxSelected>>", lambda e: self.actualizar_graficas())
        self.var_log = tk.BooleanVar(value=True)
        ttk.Checkbutton(barra, text="Tiempo en escala logarítmica", variable=self.var_log,
                        command=self.actualizar_graficas).pack(side="left", padx=12)
        ttk.Button(barra, text="Exportar PNG (las tres)...", command=self.exportar_png).pack(side="right")

        self.fig = Figure(figsize=(8, 5), dpi=100)
        self.canvas_fig = FigureCanvasTkAgg(self.fig, master=t)
        NavigationToolbar2Tk(self.canvas_fig, t).pack(side="bottom", fill="x")
        self.canvas_fig.get_tk_widget().pack(fill="both", expand=True)
        self.actualizar_graficas()

    def actualizar_graficas(self):
        self.fig.clear()
        sel = self._mapa_graf[self.var_graf.get()]
        if not self.resultados:
            ax = self.fig.add_subplot(111)
            ax.axis("off")
            ax.text(0.5, 0.5, "Ejecute un benchmark o importe un CSV para ver las gráficas",
                    ha="center", va="center", color="#888888", fontsize=12)
        elif sel == "todas":
            axs = [self.fig.add_subplot(1, 3, i) for i in (1, 2, 3)]
            graficas.grafica_tiempo(axs[0], self.resultados, log=self.var_log.get())
            graficas.grafica_speedup(axs[1], self.resultados)
            graficas.grafica_eficiencia(axs[2], self.resultados)
            for ax in axs:
                ax.title.set_fontsize(9)
        elif sel == "tiempo_vs_tamanio":
            graficas.grafica_tiempo(self.fig.add_subplot(111), self.resultados, log=self.var_log.get())
        else:
            graficas.GRAFICAS[sel](self.fig.add_subplot(111), self.resultados)
        self.fig.tight_layout()
        self.canvas_fig.draw_idle()

    def exportar_png(self):
        if not self.resultados:
            messagebox.showinfo("Exportar PNG", "No hay resultados todavía.")
            return
        carpeta = filedialog.askdirectory(title="Carpeta destino", initialdir=DIR)
        if carpeta:
            rutas = graficas.exportar_png(self.resultados, carpeta)
            self._log("Gráficas guardadas: " + ", ".join(os.path.basename(r) for r in rutas))
            messagebox.showinfo("Exportar PNG", f"Se guardaron {len(rutas)} imágenes en:\n{carpeta}")

    # ================================================================ bucle de eventos
    def _atender_colas(self):
        # Simulación: como mucho un frame por ciclo
        try:
            tipo, dato = self.cola_sim.get_nowait()
        except queue.Empty:
            tipo = None
        if tipo == "generacion":
            self.matriz, dt = dato
            self.generacion += 1
            self.tiempos_gen.append(dt)
            ahora = time.perf_counter()
            inst = 1.0 / max(ahora - self._ultimo_frame, 1e-6)
            self._fps = inst if not self._fps else 0.8 * self._fps + 0.2 * inst
            self._ultimo_frame = ahora
            self._dibujar()
            self._actualizar_stats()
            sim = self.sim
            if sim is not None:
                self.after(int(self.var_retardo.get()), sim.continuar.set)
        elif tipo == "error":
            messagebox.showerror("Error del motor", dato)
        elif tipo == "fin":
            self.sim = None
            self.btn_play.config(text="Iniciar", state="normal")
            self._bloquear_controles(False)

        for _ in range(50):
            try:
                tipo, dato = self.cola_bench.get_nowait()
            except queue.Empty:
                break
            if tipo == "stdout":
                try:
                    self._evento_benchmark(json.loads(dato))
                except json.JSONDecodeError:
                    self._log(dato)  # print() suelto del motor paralelo
            elif tipo == "stderr":
                self._log(dato)
            elif tipo == "salio":
                self._benchmark_terminado()

        self.after(15, self._atender_colas)

    def _cerrar(self):
        if self.sim is not None:
            self.sim.parar()
        if self.proc is not None:
            self.proc.terminate()
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
