# Referencia de Comandos CLI

Referencia completa de todos los comandos disponibles en el CLI de News Portal.

## Paginación

Todos los comandos que listan resultados utilizan paginación automática cuando hay más de 20 elementos:
- La paginación usa el pager del sistema (generalmente `less`)
- Puedes desactivar la paginación con `--no-pager`
- Navegación: usa flechas, espacio, `q` para salir
- También funciona redirigiendo a archivo: `uv run news entity list > output.txt`

## Artículos

### `news article fetch <URL>`

Descarga y extrae un artículo desde una URL.

**Ejemplo:**
```bash
uv run news article fetch "https://www.diariolibre.com/actualidad/..."
```

### `news article list`

Lista artículos de la base de datos.

**Opciones:**
- `-l, --limit`: Número de artículos a mostrar (default: 10)
- `-s, --source`: Filtrar por dominio de fuente
- `-t, --tag`: Filtrar por tag
- `--preprocessed`: Mostrar solo artículos preprocesados
- `--pending-preprocess`: Mostrar solo artículos pendientes de preprocesar
- `--no-pager`: Desactivar paginación

**Ejemplos:**
```bash
uv run news article list
uv run news article list --limit 20
uv run news article list --source diariolibre.com
uv run news article list --tag "política"
uv run news article list --preprocessed
uv run news article list --pending-preprocess
uv run news article list --source diariolibre.com --preprocessed
```

### `news article show <ID>`

Muestra detalles de un artículo específico.

**Opciones:**
- `-f, --full`: Mostrar contenido completo del artículo
- `-e, --entities`: Mostrar entidades extraídas (NER)

**Ejemplos:**
```bash
uv run news article show 1
uv run news article show 1 --full
uv run news article show 1 --entities
uv run news article show 1 --full --entities
```

**Información mostrada:**
- Metadatos (título, autor, fecha, ubicación, fuente, categoría)
- Estado de preprocesamiento
- Tags
- Entidades extraídas (si `--entities` y artículo preprocesado)
  - Nombre, tipo, número de menciones, relevancia
- Contenido (preview o completo según `--full`)

### `news article delete <ID>`

Elimina un artículo de la base de datos.

**Ejemplo:**
```bash
uv run news article delete 1
```

---

## Dominios/Fuentes

### `news domain list`

Lista todas las fuentes registradas.

**Ejemplo:**
```bash
uv run news domain list
```

### `news domain show <dominio>`

Muestra detalles de una fuente específica.

**Ejemplo:**
```bash
uv run news domain show diariolibre.com
```

### `news domain add <dominio>`

Agrega manualmente una fuente a la base de datos.

**Opciones:**
- `-n, --name`: Nombre descriptivo de la fuente

**Ejemplo:**
```bash
uv run news domain add example.com --name "Example News"
```

### `news domain delete <dominio>`

Elimina una fuente y todos sus artículos.

**Ejemplo:**
```bash
uv run news domain delete example.com
```

### `news domain stats`

Muestra estadísticas sobre todas las fuentes.

**Ejemplo:**
```bash
uv run news domain stats
```

**Información mostrada:**
- Total de artículos por fuente
- Artículos preprocesados por fuente
- Artículos pendientes de preprocesar por fuente
- Totales globales

---

## Procesamiento de Batches

### `news domain process start`

Crea y ejecuta un batch de procesamiento.

**Opciones:**
- `-d, --domain`: Dominio a procesar (requerido)
- `-t, --type`: Tipo de procesamiento (requerido)
  - `pre_process_articles`: Pre-procesamiento con NER
- `-s, --size`: Tamaño del batch (default: 10)

**Ejemplo:**
```bash
uv run news domain process start -d diariolibre.com -t pre_process_articles -s 10
```

### `news domain process list`

Lista batches de procesamiento con filtros.

**Opciones:**
- `-l, --limit`: Número de batches a mostrar (default: 20)
- `-s, --status`: Filtrar por estado (pending, processing, completed, failed)
- `-d, --domain`: Filtrar por dominio
- `--no-pager`: Desactivar paginación

**Ejemplos:**
```bash
uv run news domain process list
uv run news domain process list --limit 50
uv run news domain process list --status completed
uv run news domain process list --domain diariolibre.com
uv run news domain process list --domain diariolibre.com --status failed
```

### `news domain process show <batch_id>`

Muestra información detallada de un batch.

**Opciones:**
- `-i, --item`: ID de item específico para ver logs detallados

**Ejemplos:**
```bash
uv run news domain process show 1
uv run news domain process show 1 --item 5
```

**Información mostrada (batch):**
- Metadatos (fuente, tipo, estado)
- Progreso (total, procesados, exitosos, fallidos)
- Estadísticas agregadas (entidades encontradas, nuevas, existentes)
- Tiempos de ejecución y duración
- Resumen de items por estado
- Primeros 5 items fallidos con errores

**Información mostrada (item con `--item`):**
- Metadatos (batch, artículo, estado)
- Estadísticas del procesamiento
- Tiempos de ejecución y duración
- Mensaje de error (si falló)
- Logs completos del procesamiento

---

## Entidades

### `news entity list`

Lista entidades nombradas extraídas.

**Opciones:**
- `-l, --limit`: Número de entidades a mostrar (default: 20)
- `-t, --type`: Filtrar por tipo de entidad
  - Tipos válidos: person, norp, fac, org, gpe, loc, product, event, work_of_art, law, language, date, time, percent, money, quantity, ordinal, cardinal
- `-r, --min-relevance`: Relevancia global mínima
- `--no-pager`: Desactivar paginación

**Ejemplos:**
```bash
uv run news entity list
uv run news entity list --limit 50
uv run news entity list --type person
uv run news entity list --min-relevance 5
uv run news entity list --type org --min-relevance 10
```

**Información mostrada:**
- Nombre de la entidad
- Tipo
- Relevancia global (número de artículos que la mencionan)
- Número de artículos donde aparece
- Descripción (si existe)

### `news entity show <nombre>`

Muestra detalles de una entidad y artículos que la mencionan.

**Opciones:**
- `-l, --limit`: Número de artículos a mostrar (default: 10)
- `--no-pager`: Desactivar paginación

**Ejemplos:**
```bash
uv run news entity show "Luis Abinader"
uv run news entity show "Policía" --limit 20
```

**Información mostrada:**
- Metadatos de la entidad (ID, tipo, relevancia, trend)
- Descripción y foto (si existen)
- Fechas de creación y actualización
- Lista de artículos que la mencionan (ordenados por relevancia)
  - Título del artículo
  - Fecha de publicación
  - Número de menciones en ese artículo
  - Relevancia en ese artículo

### `news entity search <query>`

Busca entidades por nombre (coincidencia parcial).

**Opciones:**
- `-l, --limit`: Número de resultados a mostrar (default: 10)
- `--no-pager`: Desactivar paginación

**Ejemplos:**
```bash
uv run news entity search "Luis"
uv run news entity search "Policía" --limit 5
```

**Información mostrada:**
- Nombre de la entidad
- Tipo
- Relevancia global
- Número de artículos donde aparece

---

## Tipos de Entidades

Los siguientes tipos de entidades son reconocidos por el sistema NER (basados en spaCy):

| Tipo | Descripción |
|------|-------------|
| person | Personas, incluyendo ficticias |
| norp | Nacionalidades, grupos religiosos o políticos |
| fac | Edificios, aeropuertos, autopistas, puentes |
| org | Compañías, agencias, instituciones |
| gpe | Países, ciudades, estados |
| loc | Ubicaciones no-GPE, cordilleras, cuerpos de agua |
| product | Objetos, vehículos, alimentos |
| event | Huracanes, batallas, guerras, eventos deportivos |
| work_of_art | Títulos de libros, canciones |
| law | Documentos convertidos en leyes |
| language | Idiomas nombrados |
| date | Fechas absolutas o relativas |
| time | Tiempos menores a un día |
| percent | Porcentajes |
| money | Valores monetarios |
| quantity | Medidas de peso o distancia |
| ordinal | "primero", "segundo", etc. |
| cardinal | Numerales |

---

## Flujos de Trabajo Comunes

### Agregar y procesar artículos de un nuevo dominio

```bash
# 1. Agregar la fuente
uv run news domain add example.com --name "Example News"

# 2. Descargar artículos
uv run news article fetch "https://example.com/article1"
uv run news article fetch "https://example.com/article2"

# 3. Verificar artículos pendientes
uv run news article list --source example.com --pending-preprocess

# 4. Procesar artículos con NER
uv run news domain process start -d example.com -t pre_process_articles -s 10

# 5. Ver progreso del batch
uv run news domain process list --domain example.com

# 6. Ver estadísticas actualizadas
uv run news domain stats
```

### Analizar entidades extraídas

```bash
# 1. Ver top entidades
uv run news entity list --limit 30

# 2. Ver solo personas relevantes
uv run news entity list --type person --min-relevance 5

# 3. Ver detalles de una entidad específica
uv run news entity show "Luis Abinader"

# 4. Buscar entidades relacionadas
uv run news entity search "Luis"

# 5. Ver artículo con sus entidades
uv run news article show 1 --entities
```

### Monitorear procesamiento

```bash
# 1. Ver batches recientes
uv run news domain process list --limit 10

# 2. Ver batches fallidos
uv run news domain process list --status failed

# 3. Ver detalles de batch específico
uv run news domain process show 5

# 4. Ver logs de item fallido
uv run news domain process show 5 --item 12
```
