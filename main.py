"""
BANCRIPFUTBOT PRO - Main Entry Point Simplificado
"""
import os
import sys

# Agregar carpeta bots al path
sys.path.append(os.path.join(os.path.dirname(__file__), 'bots'))

def main():
    print("=" * 50)
    print("🚀 BANCRIPFUTBOT PRO - Sistema de Señales")
    print("=" * 50)
    print("📡 Servidor webhook: http://0.0.0.0:5000")
    print("📊 Endpoints disponibles:")
    print("   • /          - Estado del sistema")
    print("   • /webhook   - Señales TradingView")
    print("   • /signals   - Historial de señales")
    print("=" * 50)
    
    # Importar y ejecutar servidor
    from webhook_server import app
    app.run(host="0.0.0.0", port=5000, debug=False)

if __name__ == "__main__":
    main()