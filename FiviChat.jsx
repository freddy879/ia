import React, { useState, useRef, useEffect } from 'react';
import { Send, Mic, Square, ChevronDown } from 'lucide-react';

export default function FiviChat() {
  const [messages, setMessages] = useState([
    { role: 'assistant', content: '¡Hola! Soy Fivi 🤖\n\nEscribe algo o presiona el botón "Hablar" para que hable contigo.' }
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [apiUrl, setApiUrl] = useState(localStorage.getItem('FIVI_API_URL') || '');
  const [showUrlInput, setShowUrlInput] = useState(!apiUrl);
  const [isListening, setIsListening] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const messagesEndRef = useRef(null);
  const recognitionRef = useRef(null);
  const synthRef = useRef(window.speechSynthesis);

  // Scroll automático
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Inicializar reconocimiento de voz
  useEffect(() => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRecognition) {
      const recognition = new SpeechRecognition();
      recognition.lang = 'es-ES';
      recognition.continuous = false;
      recognition.interimResults = false;

      recognition.onstart = () => {
        setIsListening(true);
      };

      recognition.onresult = (event) => {
        let transcript = '';
        for (let i = event.resultIndex; i < event.results.length; i++) {
          transcript += event.results[i][0].transcript;
        }
        if (transcript) {
          setInput(transcript.trim());
        }
      };

      recognition.onerror = (event) => {
        console.error('Error en reconocimiento:', event.error);
        setIsListening(false);
      };

      recognition.onend = () => {
        setIsListening(false);
      };

      recognitionRef.current = recognition;
    }
  }, []);

  // Guardar URL de API
  const handleSaveUrl = () => {
    if (apiUrl.trim()) {
      localStorage.setItem('FIVI_API_URL', apiUrl);
      setShowUrlInput(false);
      setMessages([
        { role: 'assistant', content: `✅ Conectado a: ${apiUrl}\n\nAhora puedo acceder a tus datos. ¿Qué necesitas?` }
      ]);
    }
  };

  // Enviar mensaje a Fivi
  const handleSendMessage = async () => {
    if (!input.trim()) return;

    const userMessage = input;
    setInput('');
    setMessages(prev => [...prev, { role: 'user', content: userMessage }]);
    setLoading(true);

    try {
      // Opción 1: Si hay API URL, conectar con backend
      if (apiUrl.trim()) {
        try {
          const response = await fetch(`${apiUrl}/api/procesar`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mensaje: userMessage })
          });

          if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
          }

          const data = await response.json();
          const respuesta = data.respuesta || 'Sin respuesta';
          
          setMessages(prev => [...prev, { 
            role: 'assistant', 
            content: respuesta,
            permitir_voz: data.permitir_voz !== false
          }]);
        } catch (error) {
          console.error('Error conectando con API:', error);
          setMessages(prev => [...prev, { 
            role: 'assistant', 
            content: `⚠️ Error conectando con API:\n${error.message}\n\nVerifica la URL. ¿Está tu Render activo?`
          }]);
        }
      } else {
        // Opción 2: Simulación local (para testing)
        const respuesta = generarRespuestaLocal(userMessage);
        setMessages(prev => [...prev, { 
          role: 'assistant', 
          content: respuesta
        }]);
      }
    } finally {
      setLoading(false);
    }
  };

  // Iniciar reconocimiento de voz (SOLO CUANDO PRESIONA BOTÓN)
  const handleStartListening = () => {
    if (recognitionRef.current) {
      recognitionRef.current.start();
    }
  };

  // Detener escucha
  const handleStopListening = () => {
    if (recognitionRef.current) {
      recognitionRef.current.abort();
      setIsListening(false);
    }
  };

  // Hablar la respuesta (BOTÓN SEPARADO)
  const handleSpeak = async (text) => {
    // Detener si está hablando
    if (isSpeaking) {
      window.speechSynthesis.cancel();
      setIsSpeaking(false);
      return;
    }

    // Limpiar síntesis anterior
    window.speechSynthesis.cancel();

    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = 'es-ES';
    utterance.rate = 0.95;
    utterance.pitch = 1;

    utterance.onstart = () => {
      setIsSpeaking(true);
    };

    utterance.onend = () => {
      setIsSpeaking(false);
    };

    utterance.onerror = () => {
      setIsSpeaking(false);
    };

    window.speechSynthesis.speak(utterance);
  };

  // Respuesta local para testing (sin API)
  const generarRespuestaLocal = (msg) => {
    const m = msg.toLowerCase();
    
    if (m.includes('hola') || m.includes('hi') || m.includes('hey')) {
      return '¡Hola! Soy Fivi 🤖\n\nComo no estoy conectado a una API, no puedo acceder a datos reales. Configura tu URL de Render arriba para que funcione completamente.';
    }
    
    if (m.includes('cómo estás') || m.includes('como estas') || m.includes('qué tal')) {
      return '¡Estoy funcionando perfecto! 💪\n\nMis sistemas están listos para analizar ventas, hacer predicciones y darte estrategias. Pero necesito que configure mi URL de API.';
    }
    
    return 'No entendí bien 🤔\n\nPuedo ayudarte con:\n• Saludos\n• Análisis de ventas\n• Predicciones\n• Recomendaciones\n\nPrimero configura tu API para acceso real.';
  };

  // Limpiar el contenido del mensaje (sin markdown)
  const cleanMessage = (msg) => {
    return msg.replace(/\*\*/g, '').replace(/\*\*/g, '');
  };

  return (
    <div className="flex flex-col h-screen bg-gradient-to-b from-slate-900 via-slate-800 to-slate-900">
      {/* HEADER */}
      <div className="bg-slate-800 border-b border-slate-700 p-4 shadow-lg">
        <div className="max-w-4xl mx-auto">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <div className="text-2xl">🤖</div>
              <div>
                <h1 className="text-white font-bold text-lg">Fivi - IA para Negocios</h1>
                <p className="text-slate-400 text-xs">Tu asistente inteligente de ventas</p>
              </div>
            </div>
            {apiUrl && <span className="text-green-400 text-xs">✅ Conectado</span>}
          </div>

          {/* Configurar URL */}
          {showUrlInput && (
            <div className="bg-slate-700 p-3 rounded-lg">
              <p className="text-slate-300 text-xs mb-2">
                Para acceso completo, configura tu URL de Render:
              </p>
              <div className="flex gap-2">
                <input
                  type="text"
                  placeholder="https://tu-app.onrender.com"
                  value={apiUrl}
                  onChange={(e) => setApiUrl(e.target.value)}
                  className="flex-1 px-3 py-2 bg-slate-600 text-white text-sm rounded border border-slate-500 placeholder-slate-400"
                />
                <button
                  onClick={handleSaveUrl}
                  className="px-4 py-2 bg-green-600 hover:bg-green-700 text-white text-sm rounded font-medium"
                >
                  Guardar
                </button>
              </div>
            </div>
          )}

          {apiUrl && (
            <button
              onClick={() => setShowUrlInput(!showUrlInput)}
              className="text-slate-400 hover:text-slate-300 text-xs flex items-center gap-1"
            >
              <ChevronDown size={12} />
              Cambiar API
            </button>
          )}
        </div>
      </div>

      {/* MESSAGES */}
      <div className="flex-1 overflow-y-auto p-4 max-w-4xl mx-auto w-full">
        <div className="space-y-4">
          {messages.map((msg, idx) => (
            <div key={idx} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div
                className={`max-w-2xl rounded-lg p-4 ${
                  msg.role === 'user'
                    ? 'bg-blue-600 text-white'
                    : 'bg-slate-700 text-slate-100 border border-slate-600'
                }`}
              >
                <p className="whitespace-pre-wrap text-sm leading-relaxed">
                  {cleanMessage(msg.content)}
                </p>

                {/* Botón para hablar la respuesta (SOLO para asistente) */}
                {msg.role === 'assistant' && msg.permitir_voz !== false && (
                  <button
                    onClick={() => handleSpeak(msg.content)}
                    className={`mt-2 flex items-center gap-1 px-3 py-1 text-xs rounded ${
                      isSpeaking
                        ? 'bg-red-500 hover:bg-red-600'
                        : 'bg-slate-600 hover:bg-slate-500'
                    } text-white transition`}
                  >
                    <Mic size={14} />
                    {isSpeaking ? 'Parando...' : 'Hablar'}
                  </button>
                )}
              </div>
            </div>
          ))}

          {loading && (
            <div className="flex justify-start">
              <div className="bg-slate-700 text-slate-100 rounded-lg p-4 border border-slate-600">
                <div className="flex gap-2">
                  <div className="w-2 h-2 bg-slate-400 rounded-full animate-bounce"></div>
                  <div className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: '0.1s' }}></div>
                  <div className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }}></div>
                </div>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* INPUT AREA */}
      <div className="bg-slate-800 border-t border-slate-700 p-4">
        <div className="max-w-4xl mx-auto">
          <div className="flex gap-2">
            {/* Botón para ESCUCHAR (SOLO ENTRADA) */}
            {isListening ? (
              <button
                onClick={handleStopListening}
                className="p-2 bg-red-600 hover:bg-red-700 text-white rounded-lg transition"
                title="Detener escucha"
              >
                <Square size={20} />
              </button>
            ) : (
              <button
                onClick={handleStartListening}
                className="p-2 bg-slate-700 hover:bg-slate-600 text-slate-300 rounded-lg transition"
                title="Presiona para hablar"
              >
                <Mic size={20} />
              </button>
            )}

            {/* Input de texto */}
            <input
              type="text"
              placeholder={isListening ? '🎤 Escuchando...' : 'Escribe algo...'}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && handleSendMessage()}
              disabled={loading || isListening}
              className="flex-1 px-4 py-2 bg-slate-700 text-white rounded-lg border border-slate-600 placeholder-slate-500 focus:outline-none focus:border-blue-500 disabled:opacity-50"
            />

            {/* Botón enviar */}
            <button
              onClick={handleSendMessage}
              disabled={loading || !input.trim()}
              className="p-2 bg-blue-600 hover:bg-blue-700 disabled:bg-slate-600 text-white rounded-lg transition"
              title="Enviar mensaje"
            >
              <Send size={20} />
            </button>
          </div>

          <p className="text-slate-500 text-xs mt-2">
            💡 Presiona el micrófono para hablar, o escribe normalmente. Presiona "Hablar" en las respuestas para escuchar.
          </p>
        </div>
      </div>
    </div>
  );
}
