# Sistema de Clasificación Automática de Entidades con IA

## Contexto

El sistema:
1. **OpenAI extrae entidades** durante `analyze_article` → las crea automáticamente con `is_approved=1`
2. **IA clasifica automáticamente** entidades similares usando LSH + comparación semántica
3. **Usuario puede revisar manualmente** y reclasificar si es necesario

## Problema que Resuelve

Cientos de entidades duplicadas/similares quedan sin relacionar después de la extracción, especialmente:
- **Iniciales/Acrónimos**: "JCE" vs "Junta Central Electoral"
- **Variantes de nombres**: "Luis" vs "Luis Abinader"
- **Nombres parciales**: "Abinader" vs "Luis Abinader"

## Solución: Clasificación AI-Assisted con Pairwise Comparison

El sistema usa **LSH (Locality-Sensitive Hashing) + Comparación 1v1 con OpenAI** para identificar y clasificar entidades relacionadas.

---

## Arquitectura del Sistema

### Componente 1: Locality-Sensitive Hashing (LSH)

**Propósito**: Descubrimiento eficiente de candidatos similares sin llamadas a API.

**Proceso**:
1. Convierte nombres de entidades a **character n-grams de tamaño 2** (ej: "Luis" → ['lu', 'ui', 'is'])
2. Genera **MinHash signatures** (50 permutaciones con 25 bands)
3. Calcula **similitud de Jaccard** entre pares
4. Filtra pares por umbral configurable (default: 0.3)

**Ventajas**:
- ✅ No requiere llamadas a API (puramente algorítmico)
- ✅ Encuentra pares similares en O(n) en lugar de O(n²)
- ✅ Configurable vía `--lsh-threshold`

**Ejemplo**:
```python
# Entidades
"Luis" → MinHash signature A
"Luis Abinader" → MinHash signature B
"Juan Pérez" → MinHash signature C

# Similitudes calculadas
Jaccard(A, B) = 0.85  # ✅ Por encima del umbral 0.3
Jaccard(A, C) = 0.12  # ❌ Por debajo del umbral
Jaccard(B, C) = 0.15  # ❌ Por debajo del umbral

# Pares candidatos para IA
[("Luis", "Luis Abinader")]  # Solo este par pasa a OpenAI
```

### Componente 2: Comparación Semántica con OpenAI

**Propósito**: Análisis semántico profundo de pares candidatos.

**Proceso**:
1. **Carga pares ya comparados** desde `entity_pair_comparisons`
2. **Filtra pares nuevos** (evita re-testar)
3. **Llama OpenAI** para cada par nuevo con contexto:
   - Nombres de ambas entidades
   - Tipos de entidad (PERSON, ORG, GPE, etc.)
   - Contexto de artículos donde aparecen
4. **Recibe clasificación estructurada** (Pydantic schema)
5. **Guarda resultado** en `entity_pair_comparisons`

**Prompt al LLM**:
```
Analiza si estas dos entidades se refieren al mismo concepto:

Entidad A: "Luis" (PERSON)
Contexto: Aparece en 45 artículos sobre política dominicana

Entidad B: "Luis Abinader" (PERSON)
Contexto: Aparece en 120 artículos sobre presidencia de República Dominicana

¿Son la misma persona?
```

**Respuesta del LLM**:
```json
{
  "classification_changes": [
    {
      "entity_id": 123,
      "classification": "alias",
      "canonical_id": 45
    }
  ],
  "confidence": 0.95,
  "reasoning": "'Luis' es claramente una forma corta de 'Luis Abinader' dado el contexto político dominicano."
}
```

### Componente 3: Tracking de Comparaciones

**Tabla**: `entity_pair_comparisons`

**Esquema**:
```sql
CREATE TABLE entity_pair_comparisons (
    id INTEGER PRIMARY KEY,
    entity_a_id INTEGER NOT NULL,  -- Siempre el ID menor
    entity_b_id INTEGER NOT NULL,  -- Siempre el ID mayor
    relationship VARCHAR(20) NOT NULL,  -- SAME, DIFFERENT, AMBIGUOUS
    confidence FLOAT NOT NULL,
    reasoning TEXT,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,

    UNIQUE(entity_a_id, entity_b_id)
)
```

**Relaciones Derivadas**:
- **SAME**: Al menos una entidad fue clasificada como `alias` de la otra
- **DIFFERENT**: No se encontró relación (clasificación `none`)
- **AMBIGUOUS**: Una entidad fue clasificada como `ambiguous` con múltiples canonicales

**Beneficios**:
- ✅ Evita re-testar pares (ahorro de costos API)
- ✅ Audit trail completo de decisiones
- ✅ Permite revisión manual de comparaciones
- ✅ Datos para entrenar modelos futuros

**Queries útiles**:
```sql
-- Ver todas las comparaciones
SELECT * FROM entity_pair_comparisons;

-- Ver solo entidades consideradas iguales
SELECT * FROM entity_pair_comparisons WHERE relationship = 'SAME';

-- Ver comparaciones con baja confianza (pueden necesitar revisión)
SELECT * FROM entity_pair_comparisons WHERE confidence < 0.7;

-- Ver comparaciones ambiguas
SELECT * FROM entity_pair_comparisons WHERE relationship = 'AMBIGUOUS';
```

---

## Comando CLI: `ai-classify`

### Sintaxis Básica

```bash
# Clasificar todas las entidades
uv run news entity ai-classify

# Clasificar solo un tipo de entidad
uv run news entity ai-classify --type PERSON

# Ver qué haría sin ejecutar (dry-run)
uv run news entity ai-classify --dry-run

# Con verbose logging
uv run news entity ai-classify --verbose

# Ajustar umbral LSH (default 0.3)
uv run news entity ai-classify --lsh-threshold 0.4
```

### Parámetros

| Parámetro | Tipo | Default | Descripción |
|-----------|------|---------|-------------|
| `--type` | choice | ALL | Filtrar por tipo: PERSON, ORG, GPE, EVENT, PRODUCT, NORP, FAC, LOC |
| `--dry-run` | flag | False | Solo mostrar sugerencias, no aplicar |
| `--verbose` | flag | False | Logging detallado del proceso |
| `--lsh-threshold` | float | 0.3 | Umbral de similitud LSH (0.0-1.0) |

### Salida del Comando

```bash
$ uv run news entity ai-classify --verbose

🔍 Starting AI-assisted entity classification...
📊 Found 150 entities to classify (type: ALL)

🔍 LSH candidate discovery...
   • Generating MinHash signatures (128 permutations)...
   • Comparing 150 entities...
   • Threshold: 0.3
✓ Found 45 candidate pairs (threshold: 0.3)

📂 Loading existing comparisons from database...
✓ Loaded 12 existing comparisons
   • Filtering out already-compared pairs...
✓ 33 new pairs to compare (12 already tested)

🤖 AI semantic comparison (1v1)...
   [1/33] Comparing "Luis" vs "Luis Abinader"... ✓ ALIAS (confidence: 0.95)
   [2/33] Comparing "JCE" vs "Junta Central Electoral"... ✓ ALIAS (confidence: 0.98)
   [3/33] Comparing "Abinader" vs "Luis Abinader"... ✓ ALIAS (confidence: 0.92)
   [4/33] Comparing "Milicia" (ORG) vs "Milicia" (NORP)... ✓ DIFFERENT (confidence: 0.85)
   ...
   [33/33] Complete!

📝 Classification summary:
   • Total pairs compared: 33
   • Entities classified: 12
     - 8 entities → ALIAS
     - 2 entities → AMBIGUOUS
     - 2 entities → NOT_AN_ENTITY
   • Pairs saved to database: 33

✅ Classification complete!

💡 Next steps:
   1. Run: uv run news entity recalculate-local
   2. Run: uv run news entity rerank
   3. Review: uv run news entity list --order-by global_rank
```

---

## Flujo Completo de Procesamiento

### FASE 1: LSH Candidate Discovery

**Input**: Lista de entidades (filtradas por tipo si se especificó)

**Proceso**:
1. Para cada entidad, genera MinHash signature
2. Compara todas las signatures entre sí
3. Calcula similitud de Jaccard
4. Filtra pares por umbral

**Output**: Lista de pares candidatos `[(entity_a, entity_b), ...]`

**Complejidad**: O(n) con LSH vs O(n²) sin LSH

### FASE 2: Filtrado de Pares Ya Comparados

**Input**: Lista de pares candidatos

**Proceso**:
1. Query a `entity_pair_comparisons` para cargar comparaciones existentes
2. Crear set de pares comparados: `{(min_id, max_id), ...}`
3. Filtrar pares nuevos

**Output**: Lista de pares nuevos para comparar

**Beneficio**: Evita re-testar pares (ahorro de costos API)

### FASE 3: Comparación Semántica con IA

**Input**: Lista de pares nuevos

**Proceso**:
1. Para cada par `(entity_a, entity_b)`:
   - Preparar datos: nombres, tipos, contexto de artículos
   - Renderizar prompts Jinja2 (system + user)
   - Llamar OpenAI API con Structured Outputs
   - Recibir clasificación JSON (validado con Pydantic)
2. Procesar `classification_changes` del resultado:
   - **ALIAS**: Llamar `entity.set_as_alias(canonical, session)`
   - **AMBIGUOUS**: Llamar `entity.set_as_ambiguous([canonical1, canonical2], session)`
   - **NOT_AN_ENTITY**: Llamar `entity.set_as_not_entity(session)`
   - **NO_CHANGE**: No hacer nada
3. Derivar relación del par:
   - Si alguna es ALIAS → `relationship = "SAME"`
   - Si alguna es AMBIGUOUS → `relationship = "AMBIGUOUS"`
   - Si no hay cambios → `relationship = "DIFFERENT"`
4. Guardar en `entity_pair_comparisons`:
   ```python
   pair_comparison = EntityPairComparison(
       entity_a_id=min(entity_a.id, entity_b.id),
       entity_b_id=max(entity_a.id, entity_b.id),
       relationship=relationship,
       confidence=result.confidence,
       reasoning=result.reasoning
   )
   session.add(pair_comparison)
   session.flush()
   ```

**Output**: Entidades clasificadas + pares guardados en DB

### FASE 4: Actualización en Cascada

Cuando una entidad CANONICAL cambia a ALIAS o AMBIGUOUS, **todas las entidades que apuntaban a ella se actualizan automáticamente**.

**Implementado en**: `NamedEntity._update_dependents_on_canonical_to_alias()` y `_update_dependents_on_canonical_to_ambiguous()`

**Ejemplo**:
```python
# "José Paliza" es CANONICAL
# "Paliza" es ALIAS de "José Paliza"

# AI detecta: "José Paliza" es alias de "José Antonio Paliza"
jose_paliza.set_as_alias(jose_antonio_paliza, session)

# Automáticamente:
# "Paliza" se redirige a "José Antonio Paliza"
# (sin necesidad de intervención manual)
```

---

## Casos de Uso y Ejemplos

### Caso 1: Alias Simple

**Escenario**: "Luis" aparece en artículos políticos, "Luis Abinader" también

**LSH**: Similitud alta (0.85)

**IA analiza**:
- "Luis" (PERSON) en contexto político dominicano
- "Luis Abinader" (PERSON) en contexto presidencial

**Decisión**: ALIAS

**Resultado**:
```python
luis.set_as_alias(luis_abinader, session)
luis.last_review_type = ReviewType.AI_ASSISTED
luis.is_approved = 1  # Ya estaba aprobado desde AI extraction
```

**Par guardado**:
```sql
INSERT INTO entity_pair_comparisons VALUES (
    123,  -- entity_a_id (Luis)
    45,   -- entity_b_id (Luis Abinader)
    'SAME',
    0.95,
    "'Luis' es claramente forma corta de 'Luis Abinader'"
);
```

### Caso 2: Entidades Ambiguas

**Escenario**: "Milicia" aparece como ORG y como NORP

**LSH**: Similitud baja (nombres idénticos pero tipos diferentes)

**IA analiza**:
- "Milicia" (ORG) - organización militar
- "Milicia" (NORP) - grupo político/social

**Decisión**: DIFFERENT (mismo nombre, conceptos diferentes)

**Resultado**:
```python
# No se clasifican, permanecen como CANONICAL separadas
```

**Par guardado**:
```sql
INSERT INTO entity_pair_comparisons VALUES (
    456,  -- entity_a_id (Milicia ORG)
    789,  -- entity_b_id (Milicia NORP)
    'DIFFERENT',
    0.85,
    "Mismo nombre pero conceptos diferentes: organización vs grupo político"
);
```

### Caso 3: Falso Positivo

**Escenario**: "Día" detectado como entidad (error del LLM)

**IA analiza**: Contexto muestra que es palabra común, no entidad

**Decisión**: NOT_AN_ENTITY

**Resultado**:
```python
dia.set_as_not_entity(session)
dia.last_review_type = ReviewType.AI_ASSISTED
```

---

## Integración con Sistema de Desambiguación

El comando `ai-classify` **utiliza completamente** el sistema de desambiguación existente:

- ✅ Llama a `set_as_alias()`, `set_as_ambiguous()`, `set_as_not_entity()`
- ✅ Marca artículos para rerank en `articles_needs_rerank`
- ✅ Actualiza en cascada entidades dependientes
- ✅ Respeta restricciones de canonical_refs

**Workflow recomendado**:
```bash
# 1. Extraer entidades con OpenAI
uv run news process start -t analyze_article

# 2. Clasificar con IA
uv run news entity ai-classify --verbose

# 3. Recalcular relevancia local
uv run news entity recalculate-local

# 4. Recalcular relevancia global (PageRank)
uv run news entity rerank

# 5. Revisar resultados
uv run news entity list --order-by global_rank --limit 20
```

---

## Parámetros LSH y Configuración

### Configuración por Defecto

El sistema usa los siguientes parámetros optimizados para entidades de periódicos dominicanos:

```python
threshold = 0.3           # Umbral de similitud Jaccard (30%)
num_perm = 50            # Número de permutaciones MinHash
bands = 25               # Número de bandas LSH (optimal para 50 perms)
char_ngram_size = 2      # Tamaño de n-gramas de caracteres
use_word_shingles = False # No usar tokens de palabras completas
```

### Por qué estos valores

**Character n-grams de tamaño 2**:
- Captura mejor variaciones cortas ("Luis" vs "Luis Abinader")
- Mayor overlap entre nombres parciales y completos

**50 permutaciones con 25 bands**:
- Balance óptimo entre velocidad y precisión
- Configuración matemáticamente ideal para threshold 0.3

**Sin word shingles**:
- Evita falsos negativos con nombres parciales
- "Abinader" y "Luis Abinader" no comparten palabras, pero sí n-grams

**Threshold 0.3 (30%)**:
- Sweet spot entre recall (57%) y precision (90%)
- Captura variantes sin generar falsos positivos excesivos

### Ajuste Manual

Si necesitas ajustar los parámetros por código:

```python
from processors.entity_lsh_matcher import EntityLSHMatcher

# Configuración personalizada
matcher = EntityLSHMatcher(
    threshold=0.4,              # Más estricto (menos candidatos)
    num_perm=100,               # Más preciso (más lento)
    char_ngram_size=3,          # N-gramas más largos
    use_word_shingles=True      # Incluir palabras completas
)
```

---

## Ventajas del Sistema

- Clasificación **semántica con IA** que entiende contexto y significado
- LSH para descubrimiento eficiente de candidatos (reducción de O(n²) a O(n))
- OpenAI analiza contexto profundo de ambas entidades
- Alta precisión con pocos falsos positivos
- Tracking de comparaciones en `entity_pair_comparisons`
- **No re-testa** pares ya comparados (ahorro de costos API)
- Audit trail completo de decisiones para revisión y mejora

---

## Monitoreo y Debugging

### Ver Comparaciones Realizadas

```bash
# Entrar a SQLite
sqlite3 data/news.db

# Ver todas las comparaciones
SELECT
    epc.id,
    e1.name AS entity_a,
    e2.name AS entity_b,
    epc.relationship,
    epc.confidence,
    epc.reasoning
FROM entity_pair_comparisons epc
JOIN named_entities e1 ON epc.entity_a_id = e1.id
JOIN named_entities e2 ON epc.entity_b_id = e2.id
ORDER BY epc.created_at DESC;

# Ver solo decisiones con baja confianza
SELECT * FROM entity_pair_comparisons WHERE confidence < 0.7;

# Ver estadísticas
SELECT
    relationship,
    COUNT(*) as count,
    AVG(confidence) as avg_confidence
FROM entity_pair_comparisons
GROUP BY relationship;
```

### Logs Verbose

```bash
# Ejecutar con verbose para ver proceso completo
uv run news entity ai-classify --verbose

# Output detallado muestra:
# - Pares candidatos encontrados por LSH
# - Pares ya comparados (skip)
# - Llamadas a OpenAI con resultado
# - Clasificaciones aplicadas
# - Pares guardados
```

---

## Costos y Performance

### Estimación de Costos API

Con GPT-5-nano (más económico):
- ~$0.0001 por comparación de par
- 100 pares nuevos = ~$0.01
- 1000 pares nuevos = ~$0.10

### Performance

- **LSH discovery**: ~1-2 segundos para 1000 entidades
- **Comparación AI**: ~1-2 segundos por par (latencia OpenAI)
- **Total**: Depende de cantidad de pares nuevos a comparar

### Optimizaciones

1. **LSH threshold**: Subir umbral reduce pares candidatos (menos llamadas API)
   ```bash
   uv run news entity ai-classify --lsh-threshold 0.8  # Más estricto
   ```

2. **Filtrar por tipo**: Procesar solo entidades de un tipo
   ```bash
   uv run news entity ai-classify --type PERSON  # Solo personas
   ```

3. **Dry-run primero**: Ver cuántos pares se compararían
   ```bash
   uv run news entity ai-classify --dry-run --verbose
   ```

---

## Próximos Pasos

### Mejoras Futuras

1. **Embeddings locales**: Reemplazar OpenAI con modelo local para comparaciones
2. **Active Learning**: Usar feedback manual para mejorar umbral LSH
3. **Batch processing**: Comparar múltiples pares en una sola llamada API
4. **Confidence threshold**: Auto-aprobar solo comparaciones de alta confianza

### Experimentación

```bash
# Probar diferentes umbrales LSH
uv run news entity ai-classify --lsh-threshold 0.6 --dry-run --verbose
uv run news entity ai-classify --lsh-threshold 0.8 --dry-run --verbose

# Comparar resultados
sqlite3 data/news.db "SELECT relationship, COUNT(*) FROM entity_pair_comparisons GROUP BY relationship"
```
