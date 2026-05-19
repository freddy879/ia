"""
NEXUS FIVI v2 - Brain Mejorado (FIXED)
=====================================
✅ Se conecta con Render
✅ Entiende saludos simples
✅ Voz solo con botón
✅ Mejor manejo de errores
"""

import json
import math
import os
import re
import sqlite3
import threading
import calendar
import requests
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict
import random


def _db_path() -> str:
    custom = os.environ.get("NEXUS_DB_PATH", "").strip()
    if custom:
        Path(custom).parent.mkdir(parents=True, exist_ok=True)
        return custom
    base = Path(__file__).parent
    db = base / "nexus.db"
    return str(db)


# ════════════════════════════════════════════════════════════════════════════════
# CONECTADOR A RENDER (NUEVO)
# ════════════════════════════════════════════════════════════════════════════════

class ConectorRender:
    """
    Se conecta con tu API en Render.
    Obtiene datos reales de ventas.
    """
    
    def __init__(self, url_render: str = None, api_key: str = None):
        self.url = (url_render or os.environ.get("RENDER_URL", "")).strip()
        self.api_key = (api_key or os.environ.get("RENDER_API_KEY", "")).strip()
        self.timeout = 10
        self.activo = bool(self.url)
    
    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h
    
    def obtener_ventas(self) -> list:
        """Obtiene ventas de Render"""
        if not self.activo:
            return []
        
        try:
            endpoint = f"{self.url}/api/ventas"
            resp = requests.get(endpoint, headers=self._headers(), timeout=self.timeout)
            resp.raise_for_status()
            datos = resp.json()
            
            # Normalizar respuesta
            if isinstance(datos, dict):
                datos = datos.get("data", datos.get("ventas", []))
            
            if not isinstance(datos, list):
                datos = [datos]
            
            return datos
        except requests.exceptions.Timeout:
            print(f"⚠️ RENDER: Timeout después de {self.timeout}s")
            return []
        except requests.exceptions.ConnectionError:
            print("⚠️ RENDER: No hay conexión (¿servicio caído?)")
            return []
        except requests.exceptions.HTTPError as e:
            print(f"⚠️ RENDER HTTP Error: {e.response.status_code}")
            return []
        except Exception as e:
            print(f"⚠️ RENDER Error: {str(e)}")
            return []
    
    def agregar_venta_remota(self, venta: dict) -> bool:
        """Envía una venta a Render"""
        if not self.activo:
            return False
        
        try:
            endpoint = f"{self.url}/api/ventas"
            resp = requests.post(
                endpoint,
                headers=self._headers(),
                json=venta,
                timeout=self.timeout
            )
            resp.raise_for_status()
            return True
        except Exception as e:
            print(f"⚠️ Error enviando venta a Render: {str(e)}")
            return False
    
    def obtener_config_remota(self) -> dict:
        """Obtiene configuración desde Render"""
        if not self.activo:
            return {}
        
        try:
            endpoint = f"{self.url}/api/config"
            resp = requests.get(endpoint, headers=self._headers(), timeout=self.timeout)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            print(f"⚠️ No se pudo obtener config de Render: {str(e)}")
            return {}


# ════════════════════════════════════════════════════════════════════════════════
# MEMORIA (mejorada con Render)
# ════════════════════════════════════════════════════════════════════════════════

class Memoria:
    _lock = threading.Lock()
    CONFIG_DEFAULTS = {
        "nombre_negocio":   "Mi Negocio",
        "moneda":           "USD",
        "objetivo_diario":  "1000.0",
        "objetivo_mensual": "30000.0",
        "categoria_principal": "general",
        "margen_minimo":    "15.0",
        "temporada_alta":   "[]",
        "dias_operacion":   '["lun","mar","mie","jue","vie","sab"]',
    }

    def __init__(self, render_url: str = None, render_api_key: str = None):
        self._ruta = _db_path()
        self._conn = sqlite3.connect(self._ruta, check_same_thread=False, timeout=30)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        
        # Conectador a Render
        self.render = ConectorRender(render_url, render_api_key)
        
        self._crear_tablas()
        self._seed_config()
        self._sincronizar_render()

    def _crear_tablas(self):
        with self._lock:
            self._conn.executescript("""
                CREATE TABLE IF NOT EXISTS ventas (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    fecha       TEXT    NOT NULL,
                    total       REAL    NOT NULL,
                    cliente     TEXT    DEFAULT '',
                    metodo_pago TEXT    DEFAULT 'efectivo',
                    notas       TEXT    DEFAULT '',
                    productos   TEXT    DEFAULT '[]',
                    timestamp   TEXT    NOT NULL,
                    remota      INTEGER DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_ventas_fecha ON ventas(fecha);

                CREATE TABLE IF NOT EXISTS conversaciones (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    pregunta  TEXT,
                    respuesta TEXT,
                    categoria TEXT,
                    timestamp TEXT
                );

                CREATE TABLE IF NOT EXISTS feedback (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    pregunta  TEXT,
                    util      INTEGER,
                    timestamp TEXT
                );

                CREATE TABLE IF NOT EXISTS config (
                    clave TEXT PRIMARY KEY,
                    valor TEXT
                );

                CREATE TABLE IF NOT EXISTS metricas_ia (
                    clave TEXT PRIMARY KEY,
                    valor TEXT
                );

                CREATE TABLE IF NOT EXISTS insights (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    tipo      TEXT,
                    contenido TEXT,
                    fecha     TEXT,
                    confianza INTEGER
                );
            """)
            self._conn.commit()

    def _seed_config(self):
        with self._lock:
            for k, v in self.CONFIG_DEFAULTS.items():
                self._conn.execute(
                    "INSERT OR IGNORE INTO config(clave,valor) VALUES(?,?)", (k, v)
                )
            for k, v in [("total_decisiones", "0"), ("decisiones_correctas", "0")]:
                self._conn.execute(
                    "INSERT OR IGNORE INTO metricas_ia(clave,valor) VALUES(?,?)", (k, v)
                )
            self._conn.commit()

    def _sincronizar_render(self):
        """Trae ventas de Render si está conectado"""
        if not self.render.activo:
            return
        
        print("🔄 Sincronizando con Render...")
        ventas_render = self.render.obtener_ventas()
        
        if ventas_render:
            print(f"✅ Obtenidas {len(ventas_render)} ventas de Render")
            for venta in ventas_render:
                self._agregar_venta_directo(venta, remota=True)
        else:
            print("ℹ️ No hay ventas en Render o no está conectado")

    def _agregar_venta_directo(self, venta: dict, remota: bool = False):
        """Agrega venta directamente sin validaciones extras"""
        fecha = str(venta.get("fecha", datetime.now().strftime("%Y-%m-%d")))[:10]
        total = float(venta.get("total", 0))
        
        if total <= 0:
            return
        
        prods = venta.get("productos", [])
        if isinstance(prods, str):
            try:
                prods = json.loads(prods)
            except Exception:
                prods = []
        
        prods_json = json.dumps(prods, ensure_ascii=False)
        
        with self._lock:
            self._conn.execute(
                """INSERT INTO ventas(fecha,total,cliente,metodo_pago,notas,productos,timestamp,remota)
                   VALUES(?,?,?,?,?,?,?,?)""",
                (
                    fecha, total,
                    str(venta.get("cliente", "")),
                    str(venta.get("metodo_pago", "efectivo")),
                    str(venta.get("notas", "")),
                    prods_json,
                    datetime.now().isoformat(),
                    1 if remota else 0,
                )
            )
            self._conn.commit()

    @staticmethod
    def _normalizar_producto(p: dict) -> dict:
        precio = float(p.get("precio", p.get("price", 0)) or 0)
        costo  = float(p.get("costo",  p.get("cost",  precio * 0.6)) or precio * 0.6)
        return {
            "nombre":   str(p.get("nombre", p.get("name", "Sin nombre"))).strip(),
            "precio":   precio,
            "costo":    costo,
            "cantidad": int(p.get("cantidad", p.get("qty", p.get("quantity", 1))) or 1),
        }

    def agregar_venta(self, venta: dict) -> int:
        fecha = str(venta.get("fecha", datetime.now().strftime("%Y-%m-%d")))[:10]
        total = float(venta.get("total", 0))
        if total <= 0:
            raise ValueError("El total debe ser mayor a 0")

        prods = venta.get("productos", [])
        if isinstance(prods, str):
            try:
                prods = json.loads(prods)
            except Exception:
                prods = []
        prods_json = json.dumps(
            [self._normalizar_producto(p) for p in prods if isinstance(p, dict)],
            ensure_ascii=False
        )

        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO ventas(fecha,total,cliente,metodo_pago,notas,productos,timestamp,remota)
                   VALUES(?,?,?,?,?,?,?,?)""",
                (
                    fecha, total,
                    str(venta.get("cliente", "")),
                    str(venta.get("metodo_pago", "efectivo")),
                    str(venta.get("notas", "")),
                    prods_json,
                    datetime.now().isoformat(),
                    0,
                )
            )
            self._conn.commit()
            
            # Enviar a Render si está conectado
            if self.render.activo:
                self.render.agregar_venta_remota(venta)
            
            return cur.lastrowid

    def get_ventas(self, dias: int = None) -> list:
        if dias is not None:
            desde = (datetime.now().date() - timedelta(days=dias)).strftime("%Y-%m-%d")
            rows = self._conn.execute(
                "SELECT * FROM ventas WHERE fecha >= ? ORDER BY fecha ASC", (desde,)
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM ventas ORDER BY fecha ASC"
            ).fetchall()

        result = []
        for r in rows:
            d = dict(r)
            try:
                d["productos"] = json.loads(d.get("productos") or "[]")
            except Exception:
                d["productos"] = []
            result.append(d)
        return result

    def total_ventas(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM ventas").fetchone()[0]

    def agregar_conversacion(self, pregunta: str, respuesta: str, categoria: str):
        with self._lock:
            self._conn.execute(
                "INSERT INTO conversaciones(pregunta,respuesta,categoria,timestamp) VALUES(?,?,?,?)",
                (pregunta, respuesta[:400], categoria, datetime.now().isoformat())
            )
            self._conn.execute(
                "UPDATE metricas_ia SET valor=CAST(CAST(valor AS INTEGER)+1 AS TEXT) WHERE clave='total_decisiones'"
            )
            self._conn.commit()

    def get_conversaciones(self, limit: int = 50) -> list:
        rows = self._conn.execute(
            "SELECT * FROM conversaciones ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def registrar_feedback(self, pregunta: str, util: bool):
        with self._lock:
            self._conn.execute(
                "INSERT INTO feedback(pregunta,util,timestamp) VALUES(?,?,?)",
                (pregunta, 1 if util else 0, datetime.now().isoformat())
            )
            if util:
                self._conn.execute(
                    "UPDATE metricas_ia SET valor=CAST(CAST(valor AS INTEGER)+1 AS TEXT) WHERE clave='decisiones_correctas'"
                )
            self._conn.commit()

    def get_feedback(self) -> list:
        return [dict(r) for r in self._conn.execute("SELECT * FROM feedback").fetchall()]

    def get_config(self) -> dict:
        rows = self._conn.execute("SELECT clave,valor FROM config").fetchall()
        cfg = {}
        for r in rows:
            val = r["valor"]
            try:
                cfg[r["clave"]] = json.loads(val)
            except Exception:
                try:
                    cfg[r["clave"]] = float(val) if "." in val else int(val)
                except Exception:
                    cfg[r["clave"]] = val
        return cfg

    def actualizar_config(self, nueva: dict):
        with self._lock:
            for k, v in nueva.items():
                if isinstance(v, (list, dict)):
                    v = json.dumps(v, ensure_ascii=False)
                self._conn.execute(
                    "INSERT OR REPLACE INTO config(clave,valor) VALUES(?,?)", (k, str(v))
                )
            self._conn.commit()

    def get_metricas_ia(self) -> dict:
        rows = self._conn.execute("SELECT clave,valor FROM metricas_ia").fetchall()
        return {r["clave"]: r["valor"] for r in rows}


# ════════════════════════════════════════════════════════════════════════════════
# ANALIZADOR PROFUNDO
# ════════════════════════════════════════════════════════════════════════════════

class AnalizadorExperto:
    """Análisis estadístico avanzado"""

    @staticmethod
    def promedio(vals: list) -> float:
        return sum(vals) / len(vals) if vals else 0.0

    @staticmethod
    def mediana(vals: list) -> float:
        if not vals:
            return 0.0
        s = sorted(vals)
        n = len(s)
        return (s[n // 2] + s[(n - 1) // 2]) / 2

    @staticmethod
    def desviacion(vals: list) -> float:
        if len(vals) < 2:
            return 0.0
        prom = sum(vals) / len(vals)
        return math.sqrt(sum((x - prom) ** 2 for x in vals) / (len(vals) - 1))

    @staticmethod
    def percentil(vals: list, p: float) -> float:
        if not vals:
            return 0.0
        s = sorted(vals)
        idx = (p / 100) * (len(s) - 1)
        lo = int(idx)
        hi = min(lo + 1, len(s) - 1)
        return s[lo] + (idx - lo) * (s[hi] - s[lo])

    def coeficiente_variacion(self, vals: list) -> float:
        prom = self.promedio(vals)
        if prom == 0:
            return 0.0
        desv = self.desviacion(vals)
        return round((desv / prom) * 100, 2) if prom else 0.0

    def tendencia(self, vals: list) -> tuple:
        n = len(vals)
        if n < 3:
            return "sin datos", 0.0
        xs = list(range(n))
        sx = sum(xs); sy = sum(vals)
        sxy = sum(x * y for x, y in zip(xs, vals))
        sxx = sum(x * x for x in xs)
        denom = n * sxx - sx * sx
        if denom == 0:
            return "estable", 0.0
        pend = (n * sxy - sx * sy) / denom
        base = abs(self.promedio(vals)) or 1
        pct  = round((pend / base) * 100, 1)
        if pct > 3:
            return "📈 creciendo", pct
        elif pct < -3:
            return "📉 cayendo", abs(pct)
        return "➡️ estable", abs(pct)

    def detectar_anomalias(self, vals: list, umbral_z: float = 2.0) -> list:
        if len(vals) < 4:
            return []
        prom = self.promedio(vals)
        desv = self.desviacion(vals)
        if desv == 0:
            return []
        result = []
        for i, v in enumerate(vals):
            z = abs((v - prom) / desv)
            if z >= umbral_z:
                result.append({
                    "indice":  i,
                    "valor":   round(v, 2),
                    "z_score": round(z, 2),
                    "tipo":    "pico" if v > prom else "caida",
                })
        return sorted(result, key=lambda x: x["z_score"], reverse=True)

    def detectar_estancamiento(self, vals: list, umbral_pct: float = 5.0) -> bool:
        if len(vals) < 7:
            return False
        prom = self.promedio(vals[-7:])
        cv = self.coeficiente_variacion(vals[-7:])
        return cv < umbral_pct and prom > 0

    def detectar_decadencia(self, vals: list) -> float:
        if len(vals) < 30:
            return 0.0
        p1 = self.promedio(vals[-30:-15])
        p2 = self.promedio(vals[-15:])
        if p1 == 0:
            return 0.0
        return round(((p2 - p1) / p1) * 100, 1)


# ════════════════════════════════════════════════════════════════════════════════
# PREDICTOR INTELIGENTE
# ════════════════════════════════════════════════════════════════════════════════

class PredictorInteligente:
    NOMBRES_DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]

    def __init__(self, memoria: Memoria):
        self.mem = memoria
        self.an  = AnalizadorExperto()

    def _serie_diaria(self, dias: int = 30) -> dict:
        hoy   = datetime.now().date()
        serie = {
            (hoy - timedelta(days=d)).strftime("%Y-%m-%d"): 0.0
            for d in range(dias)
        }
        for v in self.mem.get_ventas(dias=dias):
            f = str(v.get("fecha", ""))[:10]
            if f in serie:
                serie[f] = round(serie[f] + float(v.get("total", 0)), 2)
        return serie

    def _vals_cronologicos(self, dias: int = 90) -> list:
        s = self._serie_diaria(dias=dias)
        return [s[k] for k in sorted(s)]

    def _mmp(self, vals: list, ventana: int = 14) -> float:
        if not vals:
            return 0.0
        rec   = vals[-ventana:]
        pesos = list(range(1, len(rec) + 1))
        sp    = sum(pesos)
        return sum(v * p for v, p in zip(rec, pesos)) / sp if sp else 0.0

    def _holt(self, vals: list, alpha: float = 0.4, beta: float = 0.15):
        if len(vals) < 2:
            return (vals[0] if vals else 0.0), 0.0
        nivel = vals[0]
        tend  = vals[1] - vals[0]
        for v in vals[1:]:
            n_ant = nivel
            nivel = alpha * v + (1 - alpha) * (nivel + tend)
            tend  = beta * (nivel - n_ant) + (1 - beta) * tend
        return nivel, tend

    def _factores_semana(self) -> dict:
        por_dia: dict = defaultdict(list)
        for v in self.mem.get_ventas():
            try:
                dia = datetime.fromisoformat(str(v["fecha"])[:10]).weekday()
                por_dia[dia].append(float(v["total"]))
            except Exception:
                continue
        if not por_dia:
            return {i: 1.0 for i in range(7)}
        promedios = {d: self.an.promedio(vs) for d, vs in por_dia.items()}
        base      = self.an.promedio(list(promedios.values())) or 1.0
        return {i: promedios.get(i, base) / base for i in range(7)}

    def predecir_proximos_dias(self, dias: int = 7) -> dict:
        vals_all = self._vals_cronologicos(dias=90)
        vals_pos = [v for v in vals_all if v > 0]

        if len(vals_pos) < 3:
            return {
                "predicciones": [],
                "confianza": 0,
                "mensaje": "Necesito más datos para predecir acertadamente.",
                "metodo": "insuficiente",
            }

        mmp_val        = self._mmp(vals_pos, ventana=min(14, len(vals_pos)))
        nivel, tendencia = self._holt(vals_pos)
        factores       = self._factores_semana()
        desv           = self.an.desviacion(vals_pos[-21:] if len(vals_pos) >= 21 else vals_pos)
        hoy            = datetime.now().date()
        preds          = []

        for i in range(1, dias + 1):
            fecha      = hoy + timedelta(days=i)
            dia_idx    = fecha.weekday()
            factor     = factores.get(dia_idx, 1.0)
            base_holt  = max(0.0, nivel + tendencia * i)
            base       = max(0.0, (0.35 * mmp_val + 0.65 * base_holt) * factor)
            margen     = desv * math.sqrt(i) * 0.45

            preds.append({
                "fecha":             fecha.strftime("%Y-%m-%d"),
                "dia_semana":        self.NOMBRES_DIAS[dia_idx],
                "prediccion":        round(base, 2),
                "minimo":            round(max(0.0, base - margen), 2),
                "maximo":            round(base + margen, 2),
                "factor_estacional": round(factor, 3),
            })

        n    = len(vals_pos)
        cv   = (self.an.desviacion(vals_pos) / self.an.promedio(vals_pos)) if self.an.promedio(vals_pos) > 0 else 1.0
        conf = min(95, max(10, int((1 - min(cv, 1)) * 55 + min(n / 45, 1) * 40)))
        t_l, t_p = self.an.tendencia(vals_pos)

        return {
            "predicciones":            preds,
            "confianza":               conf,
            "tendencia_actual":        t_l,
            "cambio_tendencia_pct":    t_p,
            "metodo":                  "ensemble_holt+mmp+estacionalidad",
            "datos_usados":            n,
            "total_predicho":          round(sum(p["prediccion"] for p in preds), 2),
            "promedio_diario_predicho": round(self.an.promedio([p["prediccion"] for p in preds]), 2),
        }

    def ranking_productos(self) -> list:
        acum: dict = {}
        for v in self.mem.get_ventas():
            for p in v.get("productos", []):
                if not isinstance(p, dict):
                    continue
                nombre  = str(p.get("nombre", "Sin nombre")).strip()
                precio  = float(p.get("precio", 0) or 0)
                costo   = float(p.get("costo", precio * 0.6) or precio * 0.6)
                qty     = int(p.get("cantidad", 1) or 1)
                fecha   = str(v.get("fecha", ""))[:10]

                if nombre not in acum:
                    acum[nombre] = {
                        "ventas_total": 0.0, "costo_total": 0.0,
                        "unidades": 0, "apariciones": 0, "fechas": [],
                    }
                acum[nombre]["ventas_total"] += precio * qty
                acum[nombre]["costo_total"]  += costo  * qty
                acum[nombre]["unidades"]     += qty
                acum[nombre]["apariciones"]  += 1
                acum[nombre]["fechas"].append(fecha)

        result = []
        for nombre, d in acum.items():
            gan   = d["ventas_total"] - d["costo_total"]
            margen = (gan / d["ventas_total"] * 100) if d["ventas_total"] > 0 else 0.0
            d_u   = len(set(d["fechas"])) or 1
            result.append({
                "nombre":          nombre,
                "ventas_total":    round(d["ventas_total"], 2),
                "ganancia":        round(gan, 2),
                "margen_pct":      round(margen, 1),
                "unidades":        d["unidades"],
                "velocidad_diaria": round(d["unidades"] / d_u, 2),
                "ticket_promedio": round(d["ventas_total"] / d["apariciones"], 2) if d["apariciones"] else 0,
            })
        return sorted(result, key=lambda x: x["ganancia"], reverse=True)

    def mejor_producto(self) -> list:
        return self.ranking_productos()


# ════════════════════════════════════════════════════════════════════════════════
# FIVI - EL AGENTE IA (MEJORADO CON SALUDOS)
# ════════════════════════════════════════════════════════════════════════════════

class Fivi:
    """
    Fivi - Tu asistente IA inteligente.
    - Entiende saludos simples ✅
    - Piensa por sí solo
    - Actúa sin que le pidas
    - Es Data Scientist + Business Manager
    """

    def __init__(self, memoria: Memoria):
        self.mem = memoria
        self.an  = AnalizadorExperto()
        self.pred = PredictorInteligente(memoria)
        self.cfg = memoria.get_config()
        self.mon = str(self.cfg.get("moneda", "USD"))
        
        # Palabras clave para detección mejorada
        self.saludos = [
            "hola", "hi", "hey", "ey", "buenos", "buenas",
            "qué tal", "que tal", "cómo estás", "como estas",
            "how are", "how you", "whats up", "what's up"
        ]
        
        self.preguntas_estado = [
            "cómo estás", "como estas", "how are you", "que tal",
            "qué tal", "estás bien", "estas bien", "ok", "okay"
        ]

    def procesar(self, mensaje: str) -> dict:
        """Procesa cualquier mensaje y responde inteligentemente"""
        m = mensaje.lower().strip()
        
        # ✅ NUEVO: Detectar saludos simples
        if self._es_saludo(m):
            return self._saludo_activacion()
        
        if self._es_pregunta_estado(m):
            return self._responder_estado()
        
        # Detectar si es "hola fivi" o similar
        if any(x in m for x in ["hola fivi", "hi fivi", "oye fivi", "ey fivi"]):
            return self._saludo_activacion()
        
        # Detectar intención
        if any(x in m for x in ["ventas ayer", "ayer", "que vendi ayer", "qué vendí ayer"]):
            return self._analizar_ayer()
        
        if any(x in m for x in ["cuantos productos", "cuántos productos", "cuantos items", "total productos"]):
            return self._contar_productos()
        
        if any(x in m for x in ["predice", "predicción", "próximos días", "pronostico"]):
            return self._predecir_inteligente(mensaje)
        
        if any(x in m for x in ["que hago", "qué hago", "consejos", "recomendaciones", "estrategia"]):
            return self._dar_recomendaciones_profundas()
        
        if any(x in m for x in ["ventas", "venta", "cuanto vendi", "cuánto vendí", "reporte"]):
            return self._analizar_ventas_general(mensaje)
        
        if any(x in m for x in ["producto", "ranking", "mejor", "peor"]):
            return self._analizar_productos()
        
        if any(x in m for x in ["adios", "adiós", "bye", "hasta", "chao"]):
            return self._despedida()
        
        # Si no reconoce, dar sugerencias
        return self._respuesta_inteligente(mensaje)

    # ──────────────────────────────────────────────────────────────────────────
    # NUEVOS MÉTODOS DE DETECCIÓN
    # ──────────────────────────────────────────────────────────────────────────

    def _es_saludo(self, mensaje: str) -> bool:
        """Detecta si es un saludo simple"""
        palabras = mensaje.split()
        return any(saludo in m for m in palabras for saludo in self.saludos)

    def _es_pregunta_estado(self, mensaje: str) -> bool:
        """Detecta preguntas sobre cómo está Fivi"""
        return any(x in mensaje for x in self.preguntas_estado)

    def _responder_estado(self) -> dict:
        """Responde cómo está Fivi"""
        txt = "¡Estoy funcionando perfecto! 🤖\n\n"
        txt += "Mis sistemas están listos para:\n"
        txt += "📊 Analizar tus ventas\n"
        txt += "🔮 Hacer predicciones\n"
        txt += "💰 Revisar productos\n"
        txt += "🎯 Darte estrategias\n\n"
        txt += "¿Qué necesitas hoy?"
        
        return {
            "respuesta": txt,
            "tipo": "estado",
            "confianza": 99,
            "permitir_voz": False,
        }

    # ──────────────────────────────────────────────────────────────────────────
    # MÉTODOS ORIGINALES (igual que antes)
    # ──────────────────────────────────────────────────────────────────────────

    def _saludo_activacion(self) -> dict:
        """Saludo especial de activación"""
        hoy = datetime.now()
        h = hoy.hour
        saludo = "Buenos días" if h < 12 else ("Buenas tardes" if h < 18 else "Buenas noches")
        
        ventas_hoy = self._ventas_del_dia(hoy)
        total_ventas = self.mem.total_ventas()
        nombre_neg = self.cfg.get("nombre_negocio", "tu negocio")
        
        serie7 = self.pred._serie_diaria(7)
        vals7 = [serie7[k] for k in sorted(serie7)]
        tend, pct = self.an.tendencia(vals7) if len(vals7) > 2 else ("sin datos", 0)
        
        txt = f"{saludo}! Soy **Fivi**, tu asistente de negocios con IA 🤖\n\n"
        txt += f"📊 **Dashboard rápido de {nombre_neg}:**\n"
        txt += f"• Ventas hoy: **${ventas_hoy:,.2f}**\n"
        txt += f"• Total registrado: {total_ventas} transacciones\n"
        txt += f"• Tendencia semanal: {tend} {pct:.1f}%\n\n"
        
        insight = self._generar_insight_automatico()
        if insight:
            txt += f"💡 **Mi recomendación hoy:** {insight}\n\n"
        
        txt += "¿Qué necesitas? Puedo:\n"
        txt += "📈 Analizar tus ventas\n"
        txt += "🔮 Predecir el futuro\n"
        txt += "💰 Revisar productos\n"
        txt += "🎯 Darte estrategia\n"
        
        return {
            "respuesta": txt,
            "tipo": "activacion",
            "confianza": 99,
            "permitir_voz": False,
            "datos": {
                "ventas_hoy": ventas_hoy,
                "total_ventas": total_ventas,
                "tendencia": tend,
            }
        }

    def _analizar_ayer(self) -> dict:
        """Analiza qué se vendió ayer"""
        ayer = datetime.now().date() - timedelta(days=1)
        ayer_str = ayer.strftime("%Y-%m-%d")
        
        ventas_ayer = [v for v in self.mem.get_ventas(dias=2) if str(v["fecha"])[:10] == ayer_str]
        total_ayer = sum(v["total"] for v in ventas_ayer)
        
        txt = f"📅 **Resumen de ayer ({ayer_str})**\n\n"
        txt += f"💰 Total vendido: **${total_ayer:,.2f}**\n"
        txt += f"🧾 Transacciones: {len(ventas_ayer)}\n"
        
        if len(ventas_ayer) > 0:
            ticket = total_ayer / len(ventas_ayer)
            txt += f"🎟️ Ticket promedio: ${ticket:,.2f}\n"
        
        serie7 = self.pred._serie_diaria(7)
        vals7 = [v for v in serie7.values() if v > 0]
        prom7 = self.an.promedio(vals7) if vals7 else 0
        
        if prom7 > 0:
            pct_dif = ((total_ayer - prom7) / prom7) * 100
            if pct_dif > 10:
                txt += f"\n📈 **¡Ayer fue {pct_dif:.0f}% mejor que el promedio!**"
            elif pct_dif < -10:
                txt += f"\n📉 Ayer estuvo {abs(pct_dif):.0f}% por debajo del promedio."
            else:
                txt += f"\n➡️ Ayer fue un día promedio."
        
        return {
            "respuesta": txt,
            "tipo": "analisis_ayer",
            "confianza": 95,
            "permitir_voz": False,
            "datos": {
                "total": total_ayer,
                "transacciones": len(ventas_ayer),
                "fecha": ayer_str,
            }
        }

    def _contar_productos(self) -> dict:
        """Cuenta cuántos productos diferentes tienes"""
        prods = self.pred.ranking_productos()
        
        txt = f"📦 **Tu catálogo:**\n\n"
        txt += f"Tienes **{len(prods)} productos diferentes** registrados:\n\n"
        
        for i, p in enumerate(prods, 1):
            txt += f"{i}. {p['nombre']} - ${p['precio']:.2f}\n"
            txt += f"   └─ ${p['ganancia']:,.2f} ganancia | {p['margen_pct']:.0f}% margen\n"
        
        if len(prods) > 0:
            mejor = max(prods, key=lambda x: x["ganancia"])
            txt += f"\n⭐ **Estrella:** {mejor['nombre']} (${mejor['ganancia']:,.2f} ganancia)"
        
        return {
            "respuesta": txt,
            "tipo": "productos",
            "confianza": 98,
            "permitir_voz": False,
            "datos": {
                "total_productos": len(prods),
                "productos": prods,
            }
        }

    def _predecir_inteligente(self, mensaje: str) -> dict:
        """Predice ventas de forma inteligente"""
        dias = 7
        if "mañana" in mensaje.lower():
            dias = 1
        
        res = self.pred.predecir_proximos_dias(dias)
        preds = res.get("predicciones", [])
        
        if not preds:
            return {
                "respuesta": "No tengo suficientes datos para predecir todavía.",
                "confianza": 20,
                "permitir_voz": False,
            }
        
        txt = f"🔮 **Predicción para los próximos {dias} día(s)**\n\n"
        txt += f"Total estimado: **${res['total_predicho']:,.2f}**\n"
        txt += f"Promedio diario: **${res['promedio_diario_predicho']:,.2f}**\n"
        txt += f"Confianza: **{res['confianza']}%**\n\n"
        
        txt += "Desglose día a día:\n"
        for p in preds:
            txt += f"• {p['dia_semana']} ({p['fecha']}): ${p['prediccion']:,.2f}\n"
        
        return {
            "respuesta": txt,
            "tipo": "prediccion",
            "confianza": res["confianza"],
            "permitir_voz": False,
            "datos": res,
        }

    def _dar_recomendaciones_profundas(self) -> dict:
        """Da recomendaciones estratégicas"""
        serie30 = self.pred._serie_diaria(30)
        vals30 = list(serie30.values())
        prods = self.pred.ranking_productos()
        
        tend, pct = self.an.tendencia(vals30)
        cv = self.an.coeficiente_variacion(vals30)
        decadencia = self.an.detectar_decadencia(vals30)
        estancado = self.an.detectar_estancamiento(vals30)
        
        recom = []
        
        if "creciendo" in tend:
            recom.append(f"✅ **Vas bien:** tus ventas crecen {pct}% mes a mes. Mantén el ritmo.")
        elif "cayendo" in tend:
            recom.append(f"⚠️ **ATENCIÓN:** ventas cayendo {pct}%. Revisa: precios, competencia, publicidad.")
        elif estancado:
            recom.append(f"➡️ **Estancamiento:** Las ventas son estables pero no crecen. Es hora de innovar.")
        
        if cv > 50:
            recom.append(f"📊 **Alta volatilidad ({cv:.0f}%):** tus ventas varían mucho. Implementa ofertas regulares.")
        elif cv < 10:
            recom.append(f"🔄 **Muy predecible:** tu negocio es estable. Aprovecha para planificar mejor.")
        
        if prods:
            estrellas = [p for p in prods if p["margen_pct"] >= 30]
            criticos = [p for p in prods if p["margen_pct"] < 10]
            
            if estrellas:
                nombres = ", ".join([p["nombre"] for p in estrellas[:2]])
                recom.append(f"⭐ **Productos estrella:** {nombres}. Promuévelos más.")
            
            if criticos:
                nombres = ", ".join([p["nombre"] for p in criticos[:2]])
                recom.append(f"🔴 **En riesgo:** {nombres} tienen margen crítico. Sube precio o baja costo.")
        
        txt = "💡 **Mis recomendaciones estratégicas:**\n\n"
        for rec in recom:
            txt += f"{rec}\n\n"
        
        return {
            "respuesta": txt,
            "tipo": "recomendaciones",
            "confianza": 85,
            "permitir_voz": False,
        }

    def _analizar_ventas_general(self, mensaje: str) -> dict:
        """Analiza ventas en general"""
        if "semana" in mensaje.lower():
            dias = 7
            periodo = "semana"
        elif "mes" in mensaje.lower():
            dias = 30
            periodo = "mes"
        else:
            dias = 7
            periodo = "semana"
        
        serie = self.pred._serie_diaria(dias)
        vals = list(serie.values())
        
        total = sum(vals)
        prom = self.an.promedio(vals)
        maximo = max(vals) if vals else 0
        minimo = min((v for v in vals if v > 0), default=0)
        tend, pct = self.an.tendencia(vals) if len(vals) > 2 else ("sin datos", 0)
        
        txt = f"📊 **Ventas de esta {periodo}**\n\n"
        txt += f"💰 Total: **${total:,.2f}**\n"
        txt += f"📈 Promedio diario: ${prom:,.2f}\n"
        txt += f"🔝 Mejor día: ${maximo:,.2f}\n"
        txt += f"🔻 Peor día: ${minimo:,.2f}\n"
        txt += f"📊 Tendencia: {tend} ({pct}%)\n"
        
        return {
            "respuesta": txt,
            "tipo": "analisis",
            "confianza": 90,
            "permitir_voz": False,
            "datos": {
                "total": total,
                "promedio": prom,
                "tendencia": tend,
            }
        }

    def _analizar_productos(self) -> dict:
        """Analiza el rendimiento de productos"""
        prods = self.pred.ranking_productos()
        
        if not prods:
            return {
                "respuesta": "Aún no tienes productos registrados. Comienza a registrar ventas con productos.",
                "confianza": 70,
                "permitir_voz": False,
            }
        
        txt = "🏆 **Ranking de Productos**\n\n"
        for i, p in enumerate(prods[:5], 1):
            txt += f"**{i}. {p['nombre']}**\n"
            txt += f"   Ganancia: ${p['ganancia']:,.2f} | Margen: {p['margen_pct']:.0f}%\n"
        
        mejor = prods[0]
        txt += f"\n⭐ **Tu mejor producto:** {mejor['nombre']}\n"
        txt += f"   Ganancia acumulada: ${mejor['ganancia']:,.2f}\n"
        
        return {
            "respuesta": txt,
            "tipo": "productos",
            "confianza": 95,
            "permitir_voz": False,
            "datos": {"productos": prods}
        }

    def _generar_insight_automatico(self) -> str:
        """Genera un insight inteligente basado en datos"""
        serie7 = self.pred._serie_diaria(7)
        vals7 = list(serie7.values())
        prods = self.pred.ranking_productos()
        
        insights = []
        
        tend, pct = self.an.tendencia(vals7) if len(vals7) > 2 else ("sin datos", 0)
        if "creciendo" in tend and pct > 15:
            insights.append(f"📈 ¡Excelente! Crecimiento del {pct}% esta semana")
        elif "cayendo" in tend:
            insights.append(f"📉 Ventas bajando {pct}%. Hora de activar estrategias")
        
        if prods and len(prods) > 1:
            mejor = prods[0]
            peor = prods[-1]
            if mejor["margen_pct"] > 40 and peor["margen_pct"] < 10:
                insights.append(f"💡 {mejor['nombre']} te da 4x más ganancia que {peor['nombre']}")
        
        return insights[0] if insights else "Registra más ventas para análisis mejores"

    def _respuesta_inteligente(self, mensaje: str) -> dict:
        """Respuesta general inteligente"""
        txt = "Hmm, no entendí bien 🤔\n\n"
        txt += "Puedes preguntarme:\n"
        txt += "• 'Hola' o 'Cómo estás'\n"
        txt += "• 'Ventas ayer'\n"
        txt += "• 'Cuántos productos tengo'\n"
        txt += "• 'Predice próximos días'\n"
        txt += "• 'Dame recomendaciones'\n"
        txt += "• 'Analiza mis ventas'\n"
        
        return {
            "respuesta": txt,
            "confianza": 40,
            "permitir_voz": False,
        }

    def _despedida(self) -> dict:
        return {
            "respuesta": "¡Hasta luego! 👋 Sigue registrando ventas para que sea cada vez más inteligente.",
            "confianza": 99,
            "permitir_voz": False,
        }

    def _ventas_del_dia(self, fecha) -> float:
        fecha_str = fecha.strftime("%Y-%m-%d")
        return sum(v["total"] for v in self.mem.get_ventas(dias=1) if str(v["fecha"])[:10] == fecha_str)


# ════════════════════════════════════════════════════════════════════════════════
# GENERADOR DE TEXTO
# ════════════════════════════════════════════════════════════════════════════════

class GeneradorTexto:
    def formatear(self, resultado: dict) -> str:
        return resultado.get("respuesta", "Sin respuesta.").strip()


# ════════════════════════════════════════════════════════════════════════════════
# EJEMPLO DE USO
# ════════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Inicializar con Render
    render_url = os.environ.get("RENDER_URL")
    render_api_key = os.environ.get("RENDER_API_KEY")
    
    mem = Memoria(render_url=render_url, render_api_key=render_api_key)
    fivi = Fivi(mem)
    
    # Test
    print(fivi.procesar("hola"))
    print("\n---\n")
    print(fivi.procesar("cómo estás"))
    print("\n---\n")
    print(fivi.procesar("qué tal"))
