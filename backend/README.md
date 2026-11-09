# EDGE-LATAM backend

API mínima con FastAPI.

## Ejecutar

Desde este directorio, instala las dependencias y arranca el servidor:

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

El endpoint de comprobación está disponible en `http://127.0.0.1:8000/health`.
