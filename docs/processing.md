# Procesamiento de Artículos

## Introducción

El sistema de procesamiento por lotes permite ejecutar diferentes tipos de procesamiento sobre artículos de forma eficiente y trazable.

## Tipos de Procesamiento

### Pre-procesamiento de Artículos (`pre_process_articles`)

Extrae entidades nombradas (NER - Named Entity Recognition) de los artículos usando spaCy.

**Características**:
- Modelo: `es_core_news_sm` (español)
- Extrae 18 tipos de entidades (personas, organizaciones, lugares, etc.)
- Asocia entidades a artículos
- Calcula relevancia basada en menciones
- Guarda logs detallados del procesamiento

## Comando CLI

```bash
uv run news domain process -d <dominio> -t <tipo> -s <tamaño>
```

**Parámetros**:
- `-d, --domain`: Dominio a procesar (requerido)
- `-t, --type`: Tipo de procesamiento (requerido)
  - `pre_process_articles`: Pre-procesamiento con NER
- `-s, --size`: Tamaño del batch (default: 10)

**Ejemplo**:
```bash
uv run news domain process -d diariolibre.com -t pre_process_articles -s 10
```

## Flujo de Procesamiento

1. **Selección de artículos**: Se seleccionan artículos no procesados (`processed_at IS NULL`)
2. **Creación de batch**: Se crea un registro en `processing_batches`
3. **Creación de items**: Se crean registros en `batch_items` para cada artículo
4. **Procesamiento**:
   - Por cada artículo:
     - Se extrae el texto (título + contenido)
     - Se ejecuta NER con spaCy
     - Se crean/actualizan entidades en `named_entities`
     - Se marca el artículo como procesado (`processed_at`)
     - Se guardan logs y estadísticas
5. **Finalización**: Se actualiza el batch con estadísticas finales

## Entidades Extraídas

Las entidades se clasifican en 18 tipos según las etiquetas de spaCy:

| Tipo | Descripción |
|------|-------------|
| PERSON | Personas, incluyendo ficticias |
| NORP | Nacionalidades, grupos religiosos o políticos |
| FAC | Edificios, aeropuertos, autopistas, puentes |
| ORG | Compañías, agencias, instituciones |
| GPE | Países, ciudades, estados |
| LOC | Ubicaciones no-GPE, cordilleras, cuerpos de agua |
| PRODUCT | Objetos, vehículos, alimentos |
| EVENT | Huracanes, batallas, guerras, eventos deportivos |
| WORK_OF_ART | Títulos de libros, canciones |
| LAW | Documentos convertidos en leyes |
| LANGUAGE | Idiomas nombrados |
| DATE | Fechas absolutas o relativas |
| TIME | Tiempos menores a un día |
| PERCENT | Porcentajes |
| MONEY | Valores monetarios |
| QUANTITY | Medidas de peso o distancia |
| ORDINAL | "primero", "segundo", etc. |
| CARDINAL | Numerales |

## Campos de Seguimiento

### ProcessingBatch

- `status`: pending, processing, completed, failed
- `total_items`: Total de artículos en el batch
- `processed_items`: Artículos procesados (exitosos + fallidos)
- `successful_items`: Artículos exitosos
- `failed_items`: Artículos fallidos
- `stats` (JSON): Estadísticas agregadas del batch
- `started_at`, `completed_at`: Timestamps de ejecución

### BatchItem

- `status`: pending, processing, completed, failed, skipped
- `logs` (TEXT): Logs detallados del procesamiento
- `stats` (JSON): Estadísticas del item individual
  - `entities_found`: Total de entidades encontradas
  - `entities_new`: Entidades nuevas creadas
  - `entities_existing`: Entidades existentes actualizadas
  - `processing_time`: Tiempo de procesamiento en segundos
- `error_message`: Mensaje de error si falló
- `started_at`, `completed_at`: Timestamps

## Relevancia de Entidades

El campo `relevance` en `named_entities` se incrementa cada vez que una entidad es mencionada:
- Primera mención: `relevance = 1`
- Segunda mención: `relevance = 2`
- Y así sucesivamente

Esto permite identificar las entidades más relevantes del corpus.

## Consultas Útiles

**Ver batches recientes**:
```sql
SELECT id, source_id, process_type, status, total_items, successful_items, failed_items
FROM processing_batches
ORDER BY created_at DESC
LIMIT 10;
```

**Ver items de un batch**:
```sql
SELECT id, article_id, status, error_message
FROM batch_items
WHERE batch_id = 1;
```

**Ver logs de un item**:
```sql
SELECT logs FROM batch_items WHERE id = 1;
```

**Entidades más relevantes**:
```sql
SELECT name, entity_type, relevance
FROM named_entities
ORDER BY relevance DESC
LIMIT 20;
```

**Artículos procesados**:
```sql
SELECT COUNT(*) FROM articles WHERE processed_at IS NOT NULL;
```

**Artículos pendientes de procesamiento**:
```sql
SELECT COUNT(*) FROM articles WHERE processed_at IS NULL;
```
