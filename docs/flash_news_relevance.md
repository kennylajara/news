# Flash News Relevance System

## Introducción

El sistema de relevancia de flash news determina **cuáles resúmenes deben publicarse** en newsletters o compartirse con usuarios. A diferencia de rankear artículos completos, este sistema se enfoca en rankear los **resúmenes generados automáticamente** desde clusters importantes (CORE o SECONDARY de alto score).

## Contexto

- **1 Artículo** → **N Clusters** → Algunos son **CORE** o **SECONDARY de alto score**
- **1 Cluster elegible** → **1 Flash News** (resumen de 2-3 oraciones generado por LLM)
- **Selección de clusters**: Preferencia por CORE (score >= 0.60), fallback a SECONDARY con score > 0.60
- **Objetivo**: Decidir cuáles flash news publicar en newsletter/plataforma

## Modelo de Datos

### Campos Nuevos en `flash_news`

```sql
ALTER TABLE flash_news ADD COLUMN relevance_score REAL DEFAULT 0.0;
ALTER TABLE flash_news ADD COLUMN relevance_components TEXT;  -- JSON
ALTER TABLE flash_news ADD COLUMN relevance_calculated_at DATETIME;
ALTER TABLE flash_news ADD COLUMN priority TEXT;  -- 'critical', 'high', 'medium', 'low'

CREATE INDEX idx_flash_news_relevance ON flash_news(relevance_score);
CREATE INDEX idx_flash_news_priority ON flash_news(priority);
```

### Campo Opcional en `sources`

```sql
ALTER TABLE sources ADD COLUMN authority_score REAL DEFAULT 0.5;
```

## Fórmula de Relevancia

```python
FlashNews_Relevance = (
    0.45 * entity_importance +        # Entidades VIP en el artículo
    0.25 * temporal_freshness +       # Qué tan reciente es
    0.15 * cluster_quality +          # Qué tan bueno es el cluster CORE
    0.10 * topic_diversity +          # Novedad temática vs otras flash news
    0.05 * source_authority           # Confiabilidad de la fuente
)
```

## Componentes de Relevancia

### 1. Entity Importance (45%)

**Intuición**: Flash news sobre figuras importantes (alto PageRank) son más relevantes.

**Algoritmo**:
```python
# Query top 5 entidades del artículo por relevancia local
top_entities = query(top 5 entities by local_relevance)

# Producto de relevancia local × global (promedio)
avg_score = sum(local * global for each entity) / 5

# BOOST: Si la entidad #1 tiene global_relevance > 0.8 (VIP)
if top_entity.global_relevance > 0.8:
    avg_score *= 1.3  # 30% boost
```

**Ejemplo**:
```
Flash news sobre "Luis Abinader anuncia reforma"
Top entidades:
  - Luis Abinader: local=1.0, global=0.95 → 0.95
  - Ministerio: local=0.76, global=0.62 → 0.47

avg = (0.95 + 0.47) / 2 = 0.71
boost (Abinader global > 0.8) = 0.71 * 1.3 = 0.92
```

### 2. Temporal Freshness (25%)

**Intuición**: Flash news decae agresivamente - las noticias son perecederas.

**Algoritmo**:
```python
hours_old = (now - article.published_date).hours

# Half-life según tipo temporal
if temporal_relevance == 'breaking':
    half_life = 6 hours    # Decay ultra rápido
elif temporal_relevance == 'timely':
    half_life = 12 hours   # Default
elif temporal_relevance == 'evergreen':
    half_life = 48 hours   # Más duradero

# Exponential decay
score = e^(-hours_old / half_life)

# BOOST para breaking news muy recientes (<1 hora)
if hours_old < 1 and temporal_relevance == 'breaking':
    score = 1.0  # Máxima prioridad
```

**Ejemplos** (half_life = 12h):
- Flash news de hace 1 hora: **0.92**
- Flash news de hace 6 horas: **0.71**
- Flash news de hace 12 horas: **0.50**
- Flash news de hace 24 horas: **0.25**
- Flash news de hace 48 horas: **0.06**

### 3. Cluster Quality (15%)

**Intuición**: Flash news de clusters CORE fuertes son mejores resúmenes.

**Algoritmo**:
```python
base_score = cluster.score  # Ya calculado durante clustering (0.0-1.0)

# Ajuste por tamaño del cluster
if cluster.size < 3:
    size_factor = 0.8   # Penalizar clusters muy pequeños
elif cluster.size > 10:
    size_factor = 1.2   # Bonus para clusters robustos
else:
    size_factor = 1.0

final_score = base_score * size_factor
```

**Ejemplo**:
```
Cluster CORE: score=0.75, size=8
final = 0.75 * 1.2 = 0.90
```

### 4. Topic Diversity (10%)

**Intuición**: Flash news sobre temas nuevos/diversos son más interesantes.

**Algoritmo**:
```python
# Buscar otras flash news recientes (últimas 24h)
recent_flash_news = query(created_at > now - 24h)

if not recent_flash_news:
    return 1.0  # Primera del día, máxima novedad

# Calcular similitud coseno con embeddings
similarities = [cosine_sim(this_embedding, other_embedding)
                for other in recent_flash_news]

max_sim = max(similarities)
diversity_score = 1 - max_sim

# BOOST si es completamente única (max_sim < 0.3)
if max_sim < 0.3:
    diversity_score = 1.0
```

**Ejemplo**:
```
Flash news sobre "Luis Abinader reforma"
Ya hay una flash news hace 2h sobre "Abinader presupuesto" (sim=0.75)
diversity = 1 - 0.75 = 0.25 (baja prioridad, tema repetido)

Flash news sobre "Huracán aproximándose"
No hay flash news recientes similares (max_sim=0.2)
diversity = 1.0 (alta prioridad, tema nuevo)
```

### 5. Source Authority (5%)

**Intuición**: Fuentes confiables producen flash news más relevantes.

**Algoritmo**:
```python
return source.authority_score or 0.5  # Default neutral
```

**Nota**: `authority_score` se puede calcular basándose en:
- Domain authority (herramientas externas)
- Historial de calidad de artículos
- Engagement promedio de sus artículos

## Prioridades

El score numérico se traduce a prioridades:

| Score | Priority | Acción |
|-------|----------|--------|
| ≥ 0.75 | **CRITICAL** | Publicar inmediatamente |
| ≥ 0.55 | **HIGH** | Publicar en próximo batch |
| ≥ 0.35 | **MEDIUM** | Considerar si hay espacio |
| < 0.35 | **LOW** | No publicar, archivar |

## Comandos CLI

### Calcular Relevancia

```bash
# Calcular para todas las flash news sin score
uv run news flash calculate-relevance

# Recalcular todas (incluso las que ya tienen score)
uv run news flash calculate-relevance --recalculate-all

# Calcular para una flash news específica
uv run news flash calculate-relevance --flash-id 1

# Ajustar ventana de tiempo para topic diversity
uv run news flash calculate-relevance --time-window 48

# Mostrar estadísticas detalladas
uv run news flash calculate-relevance --show-stats
```

**Output esperado**:
```
🔄 Calculating flash news relevance...

✅ Relevance calculation complete!

  Flash news processed: 25
  Processing time: 3.42s

📊 By Priority:
  CRITICAL: 3
  HIGH: 8
  MEDIUM: 10
  LOW: 4

💡 View results with:
  news flash list --priority critical
  news flash list --priority high
  news flash show <id>
```

### Seleccionar para Newsletter

```bash
# Preview sin marcar como publicadas (dry run)
uv run news flash select-for-newsletter --dry-run

# Seleccionar con configuración default (10 flash news, min_score=0.35)
uv run news flash select-for-newsletter

# Ajustar parámetros
uv run news flash select-for-newsletter --max-count 15 --min-score 0.5

# Diversificación (max 3 flash news por fuente)
uv run news flash select-for-newsletter --max-per-source 3

# Marcar como publicadas automáticamente
uv run news flash select-for-newsletter --mark-published
```

**Output esperado**:
```
📬 Selecting flash news for newsletter...

✅ Selected 10 flash news for newsletter:

[CRITICAL]
  [3] 0.8542 | diariolibre.com
      Luis Abinader anuncia nueva reforma tributaria que entrará en vigor...
  [7] 0.7891 | listindiario.com
      Huracán categoría 4 se aproxima a la costa este, autoridades emite...

[HIGH]
  [12] 0.6543 | hoy.com.do
      Congreso aprueba presupuesto 2025 con aumento del 15% para educaci...
  [15] 0.5987 | diariolibre.com
      Ministerio de Salud reporta brote de dengue en tres provincias del...

[MEDIUM]
  [21] 0.4523 | eldia.com.do
      Banco Central mantiene tasa de interés en 8.5% por tercer mes cons...

📊 Distribution by source:
  diariolibre.com: 2 flash news
  listindiario.com: 2 flash news
  hoy.com.do: 2 flash news
  eldia.com.do: 2 flash news
  elnacional.com.do: 2 flash news

💡 To mark as published, add --mark-published flag
```

### Listar con Filtros de Relevancia

```bash
# Ver flash news por prioridad
uv run news flash list --priority critical
uv run news flash list --priority high

# Ver todas ordenadas por relevancia
uv run news flash list --unpublished

# Combinar filtros
uv run news flash list --domain diariolibre.com --priority critical
```

### Ver Detalles de Relevancia

```bash
uv run news flash show 1
```

**Output incluye**:
```
=== Flash News #1 ===

Status: UNPUBLISHED
Created: 2025-01-15 14:23:45

Summary:
Luis Abinader anuncia nueva reforma tributaria que entrará en vigor
el próximo trimestre, incluyendo reducción del ITBIS para productos
de primera necesidad.

Relevance Information:
  Score: 0.8542
  Priority: CRITICAL
  Calculated: 2025-01-15 14:30:12

  Component Breakdown:
    entity_importance: 0.9200
    temporal_freshness: 0.9521
    cluster_quality: 0.8800
    topic_diversity: 0.7500
    source_authority: 0.7000
```

## Workflow Completo

### Flujo Diario para Newsletter

```bash
# 1. Procesar artículos nuevos (ya existente)
uv run news article fetch-cached --limit 50
uv run news process start -t enrich_article -s 50
uv run news process start -t analyze_article -s 50
uv run news process start -t generate_flash_news -s 50

# 2. Calcular relevancia de flash news nuevas
uv run news flash calculate-relevance

# 3. Preview selección
uv run news flash select-for-newsletter --dry-run

# 4. Aprobar y marcar como publicadas
uv run news flash select-for-newsletter --mark-published

# 5. (Opcional) Exportar para newsletter
# TODO: Comando para exportar flash news seleccionadas a formato email/HTML
```

### Recálculo Periódico

```bash
# Recalcular todas las flash news cada semana
# (útil si cambió PageRank de entidades)
uv run news flash calculate-relevance --recalculate-all
```

## Ejemplos de Scoring

### Ejemplo 1: Flash News VIP + Breaking

```
Flash news: "Luis Abinader anuncia reforma tributaria"
- Artículo publicado hace 2 horas
- Entidad top: Luis Abinader (global=0.95, local=1.0)
- Cluster CORE: score=0.82, size=9
- temporal_relevance: breaking
- No hay flash news similares hoy

Componentes:
  entity_importance: 0.95 * 1.3 = 1.0 (capped) × 0.45 = 0.450
  temporal_freshness: 0.87 × 0.25 = 0.218
  cluster_quality: 0.82 × 1.2 = 0.98 × 0.15 = 0.147
  topic_diversity: 1.0 × 0.10 = 0.100
  source_authority: 0.8 × 0.05 = 0.040

TOTAL: 0.955 → CRITICAL PRIORITY ✅ PUBLICAR
```

### Ejemplo 2: Flash News Repetitiva

```
Flash news: "Congreso discute presupuesto"
- Artículo publicado hace 18 horas
- Entidad top: Congreso (global=0.42, local=0.76)
- Cluster CORE: score=0.65, size=6
- Ya hay 2 flash news sobre presupuesto hoy (sim=0.78)

Componentes:
  entity_importance: 0.42 * 0.76 = 0.32 × 0.45 = 0.144
  temporal_freshness: 0.23 × 0.25 = 0.058
  cluster_quality: 0.65 × 0.15 = 0.098
  topic_diversity: (1-0.78) = 0.22 × 0.10 = 0.022
  source_authority: 0.7 × 0.05 = 0.035

TOTAL: 0.357 → MEDIUM PRIORITY ⚠️ BORDERLINE
```

### Ejemplo 3: Flash News Evergreen Alta Calidad

```
Flash news: "Descubren nueva especie endémica"
- Artículo publicado hace 6 horas
- Entidad top: Universidad (global=0.58, local=0.88)
- Cluster CORE: score=0.91, size=12
- temporal_relevance: evergreen
- Tema único (diversity=0.95)

Componentes:
  entity_importance: 0.58 * 0.88 = 0.51 × 0.45 = 0.230
  temporal_freshness: 0.71 × 0.25 = 0.178
  cluster_quality: 0.91 × 1.2 = 1.0 × 0.15 = 0.150
  topic_diversity: 0.95 × 0.10 = 0.095
  source_authority: 0.75 × 0.05 = 0.038

TOTAL: 0.691 → HIGH PRIORITY ✅ PUBLICAR
```

## Estrategia de Selección

### Criterios

1. **Relevance ≥ min_score** (default: 0.35)
2. **No publicadas** (`published=0`)
3. **Ordenar por relevance DESC**
4. **Máximo max_count** items (default: 10)
5. **Diversificar**: No más de `max_per_source` por fuente (default: 2)

### Diversificación de Fuentes

El sistema automáticamente distribuye las flash news para evitar monopolio de una fuente:

```python
# Ejemplo con max_per_source=2
Flash news seleccionadas:
  diariolibre.com: 2 ✅ (límite alcanzado)
  listindiario.com: 2 ✅
  hoy.com.do: 2 ✅
  eldia.com.do: 2 ✅
  elnacional.com.do: 2 ✅

Total: 10 flash news de 5 fuentes diferentes
```

## Ventajas del Sistema

1. ✅ **Foco correcto**: Rankea lo que realmente compartes (flash news)
2. ✅ **Temporal awareness**: Decay agresivo para contenido fresco
3. ✅ **Anti-repetición**: Topic diversity evita spam temático
4. ✅ **Diversificación**: No más de N flash news por fuente
5. ✅ **VIP boost**: Noticias de figuras importantes priorizadas
6. ✅ **Transparente**: `relevance_components` permite debugging
7. ✅ **Configurable**: Pesos ajustables según audiencia

## Queries SQL Útiles

### Top flash news por relevancia

```sql
SELECT
    fn.id,
    fn.relevance_score,
    fn.priority,
    a.title,
    s.domain
FROM flash_news fn
JOIN article_clusters ac ON fn.cluster_id = ac.id
JOIN articles a ON ac.article_id = a.id
JOIN sources s ON a.source_id = s.id
WHERE fn.published = 0
  AND fn.relevance_score IS NOT NULL
ORDER BY fn.relevance_score DESC
LIMIT 20;
```

### Flash news por prioridad y fuente

```sql
SELECT
    fn.priority,
    s.domain,
    COUNT(*) as count,
    AVG(fn.relevance_score) as avg_score
FROM flash_news fn
JOIN article_clusters ac ON fn.cluster_id = ac.id
JOIN articles a ON ac.article_id = a.id
JOIN sources s ON a.source_id = s.id
WHERE fn.published = 0
  AND fn.priority IS NOT NULL
GROUP BY fn.priority, s.domain
ORDER BY fn.priority, avg_score DESC;
```

### Distribución de scores

```sql
SELECT
    CASE
        WHEN relevance_score >= 0.75 THEN 'CRITICAL'
        WHEN relevance_score >= 0.55 THEN 'HIGH'
        WHEN relevance_score >= 0.35 THEN 'MEDIUM'
        ELSE 'LOW'
    END as priority_tier,
    COUNT(*) as count,
    AVG(relevance_score) as avg_score,
    MIN(relevance_score) as min_score,
    MAX(relevance_score) as max_score
FROM flash_news
WHERE relevance_score IS NOT NULL
GROUP BY priority_tier
ORDER BY avg_score DESC;
```

## Ajuste de Pesos

Si necesitas ajustar los pesos para tu caso de uso:

```python
# En src/domain/calculate_flash_news_relevance.py
FLASH_NEWS_RELEVANCE_WEIGHTS = {
    'entity_importance': 0.45,    # Aumentar si quieres priorizar VIPs
    'temporal_freshness': 0.25,   # Aumentar si quieres noticias más frescas
    'cluster_quality': 0.15,      # Aumentar si calidad del resumen es crítica
    'topic_diversity': 0.10,      # Aumentar si quieres evitar repetición
    'source_authority': 0.05      # Aumentar si confiabilidad es importante
}
```

**Ejemplo de ajuste para audiencia política**:
```python
FLASH_NEWS_RELEVANCE_WEIGHTS = {
    'entity_importance': 0.55,    # +10% - Priorizar figuras políticas
    'temporal_freshness': 0.30,   # +5% - Breaking news crítico
    'cluster_quality': 0.10,      # -5%
    'topic_diversity': 0.05,      # -5% - Permitir más cobertura del mismo tema
    'source_authority': 0.00      # Sin importancia
}
```

## Próximos Pasos (Roadmap)

1. **Exportación a formato email/HTML**
   - Comando para generar newsletter HTML
   - Templates personalizables

2. **API REST para flash news**
   - Endpoint `/flash-news/top`
   - Filtros por relevancia/prioridad

3. **Feedback loop de usuarios**
   - Tracking de clicks en flash news publicadas
   - Ajuste automático de pesos basado en engagement

4. **Scheduler automático**
   - Calcular relevancia automáticamente cada hora
   - Newsletter diario automático

5. **A/B Testing de pesos**
   - Experimentar con diferentes configuraciones
   - Medir engagement por variante
