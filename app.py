"""
BACKEND FLASK para Fivi
- Conecta con Render para obtener datos reales
- Expone API REST para el frontend
- Maneja todas las operaciones de Fivi
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import sys
from datetime import datetime

# Importar el módulo Fivi
sys.path.insert(0, os.path.dirname(__file__))
from nexus_fivi_v2_fixed import Memoria, Fivi, GeneradorTexto

# ════════════════════════════════════════════════════════════════════════════════
# INICIALIZACIÓN
# ════════════════════════════════════════════════════════════════════════════════

app = Flask(__name__)
CORS(app)

# Variables globales
memoria = None
fivi = None
generador = GeneradorTexto()

def inicializar():
    """Inicializa Fivi con conexión a Render"""
    global memoria, fivi
    
    render_url = os.environ.get("RENDER_URL", "").strip()
    render_api_key = os.environ.get("RENDER_API_KEY", "").strip()
    
    print(f"🚀 Inicializando Fivi...")
    print(f"📍 RENDER_URL: {render_url if render_url else '(no configurada)'}")
    print(f"🔑 API Key: {'✅ configurada' if render_api_key else '❌ no configurada'}")
    
    memoria = Memoria(render_url=render_url, render_api_key=render_api_key)
    fivi = Fivi(memoria)
    
    print(f"✅ Fivi listo")
    return True

# Inicializar al arrancar
try:
    inicializar()
except Exception as e:
    print(f"❌ Error inicializando: {str(e)}")
    sys.exit(1)


# ════════════════════════════════════════════════════════════════════════════════
# RUTAS API
# ════════════════════════════════════════════════════════════════════════════════

@app.route('/health', methods=['GET'])
def health():
    """Health check"""
    return jsonify({
        "status": "ok",
        "fivi": "activo" if fivi else "inactivo",
        "timestamp": datetime.now().isoformat(),
        "render_conectado": memoria.render.activo if memoria else False
    }), 200


@app.route('/api/procesar', methods=['POST'])
def procesar_mensaje():
    """
    Procesa un mensaje con Fivi
    
    Body: { "mensaje": "tu mensaje aquí" }
    Response: { "respuesta": "...", "tipo": "...", "confianza": 95, ... }
    """
    try:
        if not fivi or not memoria:
            return jsonify({
                "error": "Fivi no está inicializado",
                "respuesta": "⚠️ Error: Fivi no está disponible. Intenta recargar la página."
            }), 503

        data = request.get_json() or {}
        mensaje = str(data.get("mensaje", "")).strip()

        if not mensaje:
            return jsonify({
                "error": "Mensaje vacío",
                "respuesta": "Necesitas escribir algo para que pueda ayudarte."
            }), 400

        # Procesar con Fivi
        resultado = fivi.procesar(mensaje)

        # Registrar en conversaciones
        try:
            memoria.agregar_conversacion(
                pregunta=mensaje,
                respuesta=resultado.get("respuesta", ""),
                categoria=resultado.get("tipo", "general")
            )
        except Exception as e:
            print(f"⚠️ Error registrando conversación: {str(e)}")

        return jsonify(resultado), 200

    except Exception as e:
        print(f"❌ Error procesando: {str(e)}")
        return jsonify({
            "error": str(e),
            "respuesta": f"❌ Error: {str(e)}"
        }), 500


@app.route('/api/ventas', methods=['GET'])
def get_ventas():
    """Obtiene las ventas registradas"""
    try:
        if not memoria:
            return jsonify({"error": "Memoria no disponible"}), 503

        dias = request.args.get("dias", default=30, type=int)
        ventas = memoria.get_ventas(dias=dias)

        return jsonify({
            "data": ventas,
            "total": len(ventas),
            "sumatoria": sum(v["total"] for v in ventas)
        }), 200

    except Exception as e:
        print(f"❌ Error obteniendo ventas: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/ventas', methods=['POST'])
def agregar_venta():
    """
    Agrega una venta
    
    Body: {
        "fecha": "2024-01-15",
        "total": 1500.50,
        "cliente": "Juan",
        "metodo_pago": "efectivo",
        "productos": [
            {"nombre": "Producto 1", "precio": 100, "costo": 60, "cantidad": 5},
            ...
        ]
    }
    """
    try:
        if not memoria:
            return jsonify({"error": "Memoria no disponible"}), 503

        data = request.get_json() or {}
        venta_id = memoria.agregar_venta(data)

        return jsonify({
            "success": True,
            "venta_id": venta_id,
            "mensaje": "✅ Venta registrada correctamente"
        }), 201

    except ValueError as e:
        return jsonify({
            "error": str(e),
            "mensaje": f"❌ Error: {str(e)}"
        }), 400

    except Exception as e:
        print(f"❌ Error agregando venta: {str(e)}")
        return jsonify({
            "error": str(e),
            "mensaje": f"❌ Error: {str(e)}"
        }), 500


@app.route('/api/config', methods=['GET'])
def get_config():
    """Obtiene la configuración"""
    try:
        if not memoria:
            return jsonify({"error": "Memoria no disponible"}), 503

        config = memoria.get_config()
        return jsonify(config), 200

    except Exception as e:
        print(f"❌ Error obteniendo config: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/config', methods=['PUT'])
def actualizar_config():
    """Actualiza la configuración"""
    try:
        if not memoria:
            return jsonify({"error": "Memoria no disponible"}), 503

        data = request.get_json() or {}
        memoria.actualizar_config(data)

        return jsonify({
            "success": True,
            "mensaje": "✅ Configuración actualizada",
            "config": memoria.get_config()
        }), 200

    except Exception as e:
        print(f"❌ Error actualizando config: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/metricas', methods=['GET'])
def get_metricas():
    """Obtiene métricas de la IA"""
    try:
        if not memoria:
            return jsonify({"error": "Memoria no disponible"}), 503

        metricas = memoria.get_metricas_ia()
        total_decisiones = int(metricas.get("total_decisiones", 0))
        correctas = int(metricas.get("decisiones_correctas", 0))
        accuracy = (correctas / total_decisiones * 100) if total_decisiones > 0 else 0

        return jsonify({
            "total_decisiones": total_decisiones,
            "decisiones_correctas": correctas,
            "accuracy_pct": round(accuracy, 1)
        }), 200

    except Exception as e:
        print(f"❌ Error obteniendo métricas: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/conversaciones', methods=['GET'])
def get_conversaciones():
    """Obtiene el historial de conversaciones"""
    try:
        if not memoria:
            return jsonify({"error": "Memoria no disponible"}), 503

        limit = request.args.get("limit", default=50, type=int)
        conversaciones = memoria.get_conversaciones(limit=limit)

        return jsonify({
            "data": conversaciones,
            "total": len(conversaciones)
        }), 200

    except Exception as e:
        print(f"❌ Error obteniendo conversaciones: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/feedback', methods=['POST'])
def registrar_feedback():
    """
    Registra feedback sobre una respuesta
    
    Body: { "pregunta": "...", "util": true/false }
    """
    try:
        if not memoria:
            return jsonify({"error": "Memoria no disponible"}), 503

        data = request.get_json() or {}
        pregunta = str(data.get("pregunta", "")).strip()
        util = bool(data.get("util", False))

        if not pregunta:
            return jsonify({"error": "Pregunta vacía"}), 400

        memoria.registrar_feedback(pregunta, util)

        return jsonify({
            "success": True,
            "mensaje": "✅ Gracias por tu feedback"
        }), 201

    except Exception as e:
        print(f"❌ Error registrando feedback: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/status', methods=['GET'])
def get_status():
    """Estado general del sistema"""
    try:
        if not fivi or not memoria:
            return jsonify({
                "status": "error",
                "fivi": "no disponible"
            }), 503

        total_ventas = memoria.total_ventas()
        metricas = memoria.get_metricas_ia()
        config = memoria.get_config()

        return jsonify({
            "status": "ok",
            "fivi": "activo",
            "render_conectado": memoria.render.activo,
            "total_ventas": total_ventas,
            "negocio": config.get("nombre_negocio", "Sin nombre"),
            "moneda": config.get("moneda", "USD"),
            "metricas": {
                "total_decisiones": int(metricas.get("total_decisiones", 0)),
                "decisiones_correctas": int(metricas.get("decisiones_correctas", 0))
            }
        }), 200

    except Exception as e:
        print(f"❌ Error obteniendo status: {str(e)}")
        return jsonify({"error": str(e)}), 500


# ════════════════════════════════════════════════════════════════════════════════
# MANEJO DE ERRORES
# ════════════════════════════════════════════════════════════════════════════════

@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Ruta no encontrada"}), 404


@app.errorhandler(500)
def internal_error(error):
    return jsonify({"error": "Error interno del servidor"}), 500


# ════════════════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_ENV", "production") == "development"

    print(f"\n{'='*60}")
    print(f"🚀 Iniciando servidor Fivi en puerto {port}")
    print(f"{'='*60}\n")

    app.run(host='0.0.0.0', port=port, debug=debug)
