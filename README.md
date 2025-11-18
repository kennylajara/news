# News Portal

Portal de resúmenes de noticias que extrae, procesa y almacena artículos de diferentes fuentes.

## Descripción

Este proyecto descarga noticias de diversos medios digitales, extrae su contenido de forma estructurada usando extractores especializados por dominio, y lo almacena en una base de datos SQLite.

## Características

### Extracción y Almacenamiento
- **Extracción automática**: Descarga y limpia HTML de artículos de noticias
- **Caché de URLs**: Sistema de caché persistente para contenido HTML (evita re-descargas)
- **Extractores por dominio**: Cada medio tiene su propio extractor especializado
- **Conversión a Markdown**: El contenido se procesa preservando formato (negritas, enlaces, títulos)
- **Base de datos SQLite**: Almacenamiento estructurado con relaciones (fuentes, artículos, tags)
- **Deduplicación**: No reprocesa artículos ya descargados
- **Detección de cambios**: Compara hashes del HTML limpio para evitar re-enriquecimiento innecesario

### Procesamiento Avanzado con IA
- **Clustering semántico**: Agrupa oraciones por similitud temática (UMAP + HDBSCAN)
- **Flash News automáticas**: LLM genera resúmenes concisos desde clusters core
- **Named Entity Recognition**: Extrae personas, organizaciones, lugares, etc. con spaCy
- **Relevancia ajustada por contexto**: Entidades en clusters importantes reciben mayor peso
- **Embeddings vectoriales**: Permite búsqueda semántica de noticias similares

### Interfaz
- **CLI completo**: Interfaz de línea de comandos con Click
- **Paginación automática**: Para listas largas de resultados
- **Output con colores**: Verde=éxito, rojo=error, amarillo=advertencia

## Estructura del Proyecto

```
news/
├── src/
│   ├── commands/
│   │   ├── __init__.py
│   │   ├── article.py         # Comandos de gestión de artículos
│   │   └── domain.py          # Comandos de gestión de fuentes
│   ├── db/
│   │   ├── __init__.py
│   │   ├── models.py          # Modelos SQLAlchemy (Source, Article, Tag)
│   │   └── database.py        # Clase Database con operaciones CRUD
│   ├── extractors/
│   │   ├── __init__.py
│   │   ├── base.py            # Clase base para extractores
│   │   ├── html_to_markdown.py # Utilidades de conversión HTML→Markdown
│   │   └── {domain}_{ext}.py    # Extractor específico por dominio
│   ├── cli.py                 # CLI principal (Click)
│   └── get_news.py            # Funciones de descarga y extracción
├── pyproject.toml             # Configuración del proyecto y dependencias
└── uv.lock                    # Lock file de dependencias
```

## Instalación

### Prerrequisitos

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (administrador de paquetes rápido)

### Pasos

1. Instalar uv (si no lo tienes):
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

2. Clonar el repositorio:
```bash
git clone https://github.com/kennylajara/news.git
cd news
```

3. Sincronizar dependencias (uv crea automáticamente el entorno virtual):
```bash
uv sync
```

4. Configurar variables de entorno:
```bash
# Copiar template de configuración
cp .env.example .env

# Editar .env y agregar tu OpenAI API key
# OPENAI_API_KEY=tu-api-key-aqui
# OPENAI_MODEL=gpt-5-nano (opcional, ya es el default)
```

5. Descargar modelo de spaCy para español:
```bash
uv run python -m spacy download es_core_news_sm
```

## Uso

El proyecto incluye una CLI completa construida con Click.

### Comandos principales

```bash
uv run news --help              # Ver ayuda general
uv run news article --help      # Ver comandos de artículos
uv run news cache --help        # Ver comandos de caché
uv run news domain --help       # Ver comandos de dominios
```

#### Artículos

```bash
# Descargar artículo individual (usa caché automáticamente)
uv run news article fetch "<URL>"
uv run news article fetch "<URL>" --reindex              # Actualizar si ya existe
uv run news article fetch "<URL>" --reindex --force-enrichment  # Forzar re-enriquecimiento
uv run news article fetch "<URL>" --dont-cache           # No guardar en caché

# Procesar artículos desde caché (sin descargar)
uv run news article fetch-cached                          # Solo nuevos
uv run news article fetch-cached --reindex                # Actualizar existentes
uv run news article fetch-cached --reindex --force-enrichment  # Forzar re-enriquecimiento
uv run news article fetch-cached --domain diariolibre.com # Filtrar dominio
uv run news article fetch-cached --limit 50               # Limitar cantidad

# Listar artículos
uv run news article list                           # Últimos 10
uv run news article list --limit 20                # Con límite
uv run news article list --source diariolibre.com  # Por fuente
uv run news article list --tag "política"          # Por tag
uv run news article list --enriched                # Solo enriquecidos
uv run news article list --pending-enrich          # Pendientes de enriquecer

# Ver artículo
uv run news article show <ID>               # Vista previa
uv run news article show <ID> --full        # Artículo completo
uv run news article show <ID> --entities    # Ver entidades extraídas (NER)
uv run news article show <ID> --clusters    # Ver clustering de oraciones

# Eliminar artículo
uv run news article delete <ID>
```

#### Caché

```bash
# Ver estadísticas de caché
uv run news cache stats
uv run news cache stats --domain diariolibre.com

# Listar dominios en caché
uv run news cache domains

# Listar URLs cacheadas
uv run news cache list
uv run news cache list --domain diariolibre.com
uv run news cache list --limit 50

# Ver detalles de un URL específico
uv run news cache show "<URL>"
uv run news cache show <hash>

# Limpiar caché
uv run news cache clear --domain diariolibre.com   # Solo un dominio
uv run news cache clear --article "<URL>"          # Un artículo específico
uv run news cache clear                            # Todo (requiere confirmación)
```

### Fuentes

```bash
# Listar fuentes
uv run news domain list
uv run news domain show <dominio>
uv run news domain stats

# Agregar fuente
uv run news domain add <dominio> --name "Nombre"

# Eliminar fuente
uv run news domain delete <dominio>

# Procesar artículos (NER con spaCy)
uv run news domain process start -d <dominio> -t pre_process_articles -s 10
uv run news domain process list                      # Ver batches
uv run news domain process list --status completed   # Filtrar por estado
uv run news domain process show <batch_id>           # Ver detalles de batch
uv run news domain process show <batch_id> --item <item_id>  # Ver logs de item específico
```

### Entidades

```bash
# Listar entidades
uv run news entity list                              # Top 20 por relevancia
uv run news entity list --limit 50                   # Con límite
uv run news entity list --type person                # Filtrar por tipo
uv run news entity list --min-relevance 10           # Filtrar por relevancia mínima

# Ver entidad y artículos que la mencionan
uv run news entity show "Luis Abinader"
uv run news entity show "Policía" --limit 20

# Buscar entidades
uv run news entity search "Luis"
```

## Tecnologías

### Core
- **Python 3.12+**
- **uv**: Gestor de paquetes rápido
- **Click**: Framework para CLI
- **SQLAlchemy**: ORM para SQLite

### Extracción y Procesamiento
- **BeautifulSoup4 + lxml**: Parsing de HTML
- **Requests**: Descarga HTTP
- **spaCy**: Named Entity Recognition (NER)
- **sentence-transformers**: Embeddings semánticos para clustering y búsqueda

### LLM y Generación de Contenido
- **OpenAI API**: Generación de flash news con Structured Outputs
- **Pydantic**: Validación de schemas JSON
- **Jinja2**: Templates para prompts
- **python-dotenv**: Gestión de variables de entorno

## Documentación

- **[Referencia de Comandos](docs/commands.md)** - Documentación completa de todos los comandos CLI
- **[Arquitectura](docs/architecture.md)** - Flujo de componentes, pipeline, patrones
- **[Base de Datos](docs/database.md)** - Esquema, operaciones CRUD, deduplicación
- **[Caché de URLs](docs/cache.md)** - Sistema de caché persistente para desarrollo
- **[Crear Extractores](docs/extractors.md)** - Guía completa con templates y ejemplos
- **[Procesamiento](docs/processing.md)** - Sistema de batches y NER con spaCy

## Fuentes Soportadas

- [x] diariolibre.com
- [ ] listindiario.com
- [ ] hoy.com.do 
- [ ] elcaribe.com.do
- [ ] elnacional.com.do
- [ ] eldia.com.do
- [ ] elnuevodiario.com.do
- [ ] eldinero.com.do

## Roadmap

- NER puede crear alias de nombres de personas y organizaciones automáticamente (nombres, apellidos e iniciales).
- Forzar NER a detectar referencias aprobadas
- Hacer que la IA pueda revisar hacer review de las entidades (con flag --auto-accept)
- Calcular relevancia de las noticias antes de publicar
- API REST para consulta de artículos
- Frontend para visualización
- Comentarios por entidades
- Sistema de publicación automática
- Descarga asíncrona con aiohttp
- Validar calidad de la información extraída (validar el JSON tras extracción)
- Entidades canónicas (unir 2 entidades) 
- Desambiguación de entidades (una entidad puede referenciar a más de 2)
- Relevancia por categoria
- Reconocer monedas como un tipo de entidad (dólar, los dólares canadiense, peso, peso dominicano), diferenciarlo de MONEY (100 dólares, un peso, 100 pesos dominicanos)
- Crear batches en el pagerank y guardar el motivo de finalización del cálculo (max iter, timeout, convergencia)
- limpiar prints
