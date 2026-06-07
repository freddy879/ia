// ============================================================
//  AgroNaranjito — Cloudflare Worker (backend seguro)
// ============================================================

const GEMINI_URL =
  "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent";

const PRODUCTOS_TIENDA = [
  "PROMET COBRE 1L","PAMEX 500ML","YARA VITA 1L","INDUCFLOR 500ML","ZEANITRO 1L",
  "QUIMIFOL 600","GREEN MASTER 250ML","SACO FULLCACAO 25K","LABIN LABICUAJE 500G",
  "CABALLO DE TROYA 1L","ANGLO QUAT","KAÑON 250ML","KRE-SAD 500M","FUNGIL FUNGICIDA 400ML",
  "COMBO FLORACION COMPLETO","NAIROBI 250ML","KILLER GALON","OLIGOMIX 100G","BIOBONB GALON",
  "CANECA GLYFOSAD","MOSKITION 100G","LABIN RAIZ","PROMET CALCIO 500ML","HACHA-ROSS 1L",
  "PANTANAL 1L","ATTAMIX 500G","COMBO COMPLEMENTO","ADHESIX 100ML","BASTNATE GALON",
  "PH CHECK 1L","GLYFOSAD 480","CANECA CHACAL","PROMET BORO 250CC","CYTOKIN 1L",
  "KOPERCUP 500G","GATILLER 1L","XSTRATA GOLD FUNGICIDA 250ML","ARRASADOR GALON",
  "INDUCPRO MAGNESIO 1L","METRINEX 50 EQ 1L","RONDO GALON","CUSAMIZN 500ML",
  "FERTI-ORGAN GALON","ESLABON RAIZ 500ML","DOMINAL 500ML","TERIGRAN GALON","MATASEC 500G",
  "LABICUPER-FUNGICIDA 500ML","HIGHP 500ML","MOSKITION 250G","MAIX 1K","GLUFONE 1L",
  "ESLABON RAIZ 1L","RAINBOTURBO 1L","KALEX 1L","GREEN 500ML","GLYFOSAD 480 1L",
  "KING GALON","OLIMPO 1L","GALERNA 1K","SALAM 1L","TRIPLEXAC 1L","ENZIPROM 250CC",
  "LABIOFOL SUGAR K 1L","HERVITAM","FINIDOR 100ML","KMELOT 100G","FLASH 500ML",
  "EXPLORER-HERBICIDA 1L","COMBO SUPER KIT NUTRICIONAL","KALEX 500CC","MIROS 500CC",
  "CUSAMIZN 1L","ZOIL 500ML","ROMEX 1KG","FUNGISEI 500ML","SACO PEPA DE ORO",
  "VIRSANB GALON","CANECA SENATOR","PH CHECK 250ML","SUPER-K60 500G","COMPLEFOL FLORACION 1K",
  "KYLATE 100ML","CLOROTEX 75","SHARIMIDA 250ML","CONFIABLE 500ML","KILLER 500ML",
  "INDUCPRO CALCIO 1L","MULTIFIX 100ML","FUERZA VERDE 1KG","PERMITT-50","CABALLO DE TROYA 500ML",
  "PAMEX 1L","KEEPER 250ML","QUIMIFOL 510","CRISQUAT-D HERBICIDA","INDUCFLOR 1L",
  "COMPLEFOL ENGROSE 1K","CONTACTO 1L","BANALPIX 1L","FILOSO 500ML","BONBA AGROSPRAYER 20L",
  "MOSKITION 500G","NOVAK-700 200KG","BIOBONB 1L","SHY 500ML","CANATREX 1K",
  "ESLABÓN CACAO 1L","ZOIL 1L","SENATOR 1L","GESAPRIM 1K","COMPLEFOL INICIO 1K",
  "MAXICROP 500ML","INDUCPRO ZINC 1L","AGROPEGA 1L","GATILLER 500ML","AGROSTEMIN 200G",
  "COMBIPLUS 1L","SEICAN","AZUFROL-FUNGICIDA 1KG","KILLER 1L","PROMET CALCIO 1L",
  "CPF KONTROL","LEOSIL PREMIUM 1L","DIABOLO 500ML","ESLABÓN CACAO 500ML",
  "COMBO FINALIZADOR AGROPROECO","CUSAMIZN 250ML","VULTUR 500ML","SENATOR GALON",
  "COMBO GROW","ALTERNO 60W 16G","SUGARINE 500 GALON","SACO LEOSIL FINO","MUNDANO-FUNGICIDA 1L",
  "METABOLIK 250ML","RESBACTERS 1L","CONTACTO 500ML","JARUCO FUNGICIDA 250ML",
  "PONCHO DE AGUAS 500G","KEEPER 1L"
];

const SYSTEM_PROMPT = `Eres un agrónomo experto en cultivos tropicales de Ecuador (cacao, banano, maíz, palma, café, etc.).
Analiza la imagen o descripción y responde ÚNICAMENTE con un JSON válido, sin texto adicional ni markdown.

Estructura requerida:
{
  "planta": "cultivo o planta identificada",
  "condicion": "resumen en menos de 8 palabras",
  "severidad": 50,
  "diagnostico": "Explicación clara de 3-4 oraciones: qué problema tiene, qué lo causa, cómo progresa y qué puede pasar si no se trata.",
  "productos_recomendados": [
    {"nombre": "NOMBRE EXACTO DE LA LISTA", "razon": "por qué ayuda en este caso específico"},
    {"nombre": "OTRO PRODUCTO", "razon": "razón"}
  ],
  "consejos": ["paso 1 de aplicación", "consejo 2", "medida preventiva"],
  "estado_icono": "⚠️"
}

Reglas:
- severidad: número 0-100 (0=sana, 100=crítica)
- estado_icono: 🚨 si severidad>=65, ⚠️ si 30-64, ✅ si <30
- productos_recomendados: máximo 4, SOLO nombres de esta lista exacta:
${PRODUCTOS_TIENDA.join(", ")}
- Si la planta está sana, recomienda fertilizantes o preventivos de la lista
- Responde en español`;

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

export default {
  async fetch(request, env) {
    // ⬆️ La API key viene de Variables de entorno de Cloudflare (Settings → Variables)
    const GEMINI_API_KEY = env.GEMINI_API_KEY;

    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: CORS });
    }

    if (request.method !== "POST") {
      return new Response("Method not allowed", { status: 405, headers: CORS });
    }

    try {
      const body = await request.json();
      const { type, imageBase64, mimeType, text } = body;

      let parts = [];

      if (type === "image" && imageBase64) {
        parts.push({
          inlineData: {
            mimeType: mimeType || "image/jpeg",
            data: imageBase64,
          },
        });
        parts.push({ text: "Analiza esta imagen de cultivo. " + SYSTEM_PROMPT });
      } else if (type === "text" && text) {
        parts.push({
          text: `El agricultor describe estos síntomas:\n"${text}"\n\n${SYSTEM_PROMPT}`,
        });
      } else {
        return new Response(
          JSON.stringify({ error: "Parámetros inválidos" }),
          { status: 400, headers: { ...CORS, "Content-Type": "application/json" } }
        );
      }

      const geminiRes = await fetch(`${GEMINI_URL}?key=${GEMINI_API_KEY}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          contents: [{ parts }],
          generationConfig: {
            temperature: 0.4,
            maxOutputTokens: 1024,
          },
        }),
      });

      if (!geminiRes.ok) {
        const err = await geminiRes.text();
        console.error("Gemini error:", err);
        return new Response(
          JSON.stringify({ error: "Error en servicio de IA", detail: err }),
          { status: 502, headers: { ...CORS, "Content-Type": "application/json" } }
        );
      }

      const geminiData = await geminiRes.json();
      const rawText =
        geminiData?.candidates?.[0]?.content?.parts?.[0]?.text || "";

      const clean = rawText.replace(/```json|```/g, "").trim();

      let parsed;
      try {
        parsed = JSON.parse(clean);
      } catch {
        const match = clean.match(/\{[\s\S]*\}/);
        if (match) {
          parsed = JSON.parse(match[0]);
        } else {
          throw new Error("No se pudo parsear respuesta de Gemini");
        }
      }

      return new Response(JSON.stringify(parsed), {
        status: 200,
        headers: { ...CORS, "Content-Type": "application/json" },
      });
    } catch (err) {
      console.error("Worker error:", err);
      return new Response(
        JSON.stringify({ error: "Error interno", detail: err.message }),
        { status: 500, headers: { ...CORS, "Content-Type": "application/json" } }
      );
    }
  },
};
