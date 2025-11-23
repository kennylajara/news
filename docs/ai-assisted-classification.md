# Sistema de Clasificación de Entidades Asistido por IA (LSH + Pairwise)

## Contexto

El sistema cuenta con:
1. **Extracción de entidades con OpenAI** - Durante `analyze_article`, OpenAI extrae entidades y las auto-aprueba (`is_approved=1`, `last_review_type=ReviewType.AI_ASSISTED`)
2. **Clasificación AI** (`ai-classify`) - LSH + comparación semántica pairwise para encontrar entidades relacionadas
   - Tracking de pares comparados (evita re-testar)
   - Análisis contextual profundo
3. **Clasificación manual** - El usuario puede revisar y reclasificar entidades manualmente si es necesario
   - `last_review_type='manual'`

## Problema a Resolver

Después de la extracción, cientos de entidades quedan duplicadas/no relacionadas:
- **Variantes de nombres**: "Luis" vs "Luis Abinader"
- **Iniciales/Acrónimos**: "JCE" vs "Junta Central Electoral"
- **Nombres parciales**: "Abinader" vs "Luis Abinader"
- **Mismo nombre, tipos diferentes**: "Milicia" (ORG) vs "Milicia" (NORP)

**Resultado**: Miles de entidades sin relacionar, requiriendo revisión manual costosa.

## Estrategia: Clasificación AI con Tracking de Pares

```
┌─────────────────────────────────────────────────────────────┐
│ 1. OpenAI extrae entidades → CANONICAL                      │
│    Durante analyze_article                                  │
│    → is_approved=1, last_review_type='ai-assisted'          │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. Clasificación con IA (ai-classify)                       │
│    - LSH encuentra candidatos similares (O(n) vs O(n²))     │
│    - Comparación semántica 1v1 con OpenAI                   │
│    - Tracking de pares: NO re-testa pares comparados        │
│    - Guarda en entity_pair_comparisons                      │
│    - Costo: ~$0.0001 por comparación                        │
│    → last_review_type='ai-assisted'                         │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. Revisión MANUAL (opcional, solo casos complejos)         │
│    - Solo si necesitas corregir decisiones de IA            │
│    → last_review_type='manual'                              │
└─────────────────────────────────────────────────────────────┘
```

**Ventajas:**
- ✅ No re-testa pares ya comparados (ahorro de costos API)
- ✅ Análisis semántico profundo (entiende contexto)
- ✅ Audit trail completo en `entity_pair_comparisons`
- ✅ Escalable con LSH (no compara todas con todas)

---

## Innovación: LSH + Comparación Pareada (1v1)

### Enfoque Tradicional (Descartado)
- **1 entidad vs N candidatos**: Envía lista de 5-10 candidatos al LLM
- **Problemas:**
  - Prompt largo con muchos candidatos
  - Confusión con demasiadas opciones
  - No escala bien (>10 candidatos)
  - Sesgo de presentación

### Enfoque Actual: LSH + Pairwise
**Locality Sensitive Hashing (LSH)** reduce búsqueda de candidatos de O(n²) a O(n·k):

```python
# 1. Indexar todas las entidades CANONICAL con MinHash
matcher = EntityLSHMatcher(threshold=0.3)
matcher.index_entities(all_canonical_entities)

# 2. Para cada entidad a evaluar, LSH encuentra top-K similares
candidates = matcher.find_candidates(entity, max_candidates=10)
# En lugar de comparar con TODAS (10,000+), solo compara con ~5-10

# 3. Comparación 1v1 con cada candidato
for candidate, jaccard_sim in candidates:
    result = compare_entities_with_ai(entity, candidate, session, jaccard_sim)
    # LLM ve contexto COMPLETO de ambas entidades
    # Puede recomendar acciones para AMBAS (sin sesgo de orden)
```

**Ventajas del LSH + 1v1:**
1. **Escalabilidad**: De 50,000,000 comparaciones a 50,000 (reducción de 1000x)
2. **Sin sesgo de orden**: Ambas entidades pueden cambiar clasificación
3. **Contexto completo**: LLM ve toda la información de ambas entidades
4. **Decisiones simétricas**: "Luis" puede ser alias de "Luis Abinader" Y viceversa

### MinHash y Shingles

**Shingles** = Fragmentos de texto para comparación:
- **Character n-grams**: Fragmentos de 2 caracteres (`["lu", "ui", "is", "s ", " a", "ab", ...]`)
- Word shingles están deshabilitados por defecto (mejora recall)

**MinHash** = Firma compacta de shingles (50 permutaciones con 25 bands):
```python
shingles = {"lu", "ui", "is", " a", "ab", "bi", ...}
minhash = MinHash(num_perm=50)
for s in shingles:
    minhash.update(s.encode('utf8'))
```

**Similitud de Jaccard** entre dos entidades:
```python
jaccard = len(shingles_a & shingles_b) / len(shingles_a | shingles_b)
# Ejemplo: "Luis Abinader" vs "Luis" → ~0.6 (60% similitud)
```

---

## Arquitectura del Sistema

### Módulos

#### 1. `processors/entity_lsh_matcher.py`
**Búsqueda eficiente de candidatos con LSH**

```python
from processors.entity_lsh_matcher import EntityLSHMatcher

# Crear índice LSH
matcher = EntityLSHMatcher(
    threshold=0.3,           # Umbral de similitud Jaccard (30%)
    num_perm=50,             # Permutaciones MinHash
    char_ngram_size=2,       # Tamaño de character n-grams
    use_word_shingles=False  # No usar tokens de palabras
)

# Indexar entidades CANONICAL
matcher.index_entities(canonical_entities)

# Buscar candidatos similares
candidates = matcher.find_candidates(
    entity,
    max_candidates=10,
    exclude_self=True
)
# Retorna: [(candidate_entity, jaccard_similarity), ...]
```

**Funciones helper:**
- `normalize_text(text)` - Normaliza texto (lowercase, sin acentos, sin puntuación)
- `text_to_shingles(text)` - Convierte texto a shingles (words + char n-grams)
- `create_minhash(shingles)` - Crea firma MinHash
- `build_lsh_index_for_type(session, entity_type)` - Construye índice para un tipo

#### 2. `processors/entity_ai_classification.py`
**Clasificación con IA usando comparaciones 1v1**

```python
from processors.entity_ai_classification import (
    classify_entity_with_ai,
    batch_classify_entities
)

# Clasificar una entidad
status, result, error = classify_entity_with_ai(
    entity=entity,
    session=session,
    lsh_matcher=matcher,  # Opcional: reusar índice
    min_confidence=0.70,
    max_candidates=10,
    dry_run=False
)

# Clasificar batch
stats = batch_classify_entities(
    session=session,
    entity_type='person',
    limit=100,
    min_confidence=0.70,
    max_candidates=10,
    dry_run=False
)
```

**Funciones principales:**
- `extract_pairwise_context()` - Extrae contexto de ambas entidades
- `compare_entities_with_ai()` - Comparación 1v1 con LLM
- `classify_entity_with_ai()` - Clasifica entidad con LSH + comparaciones
- `batch_classify_entities()` - Procesa múltiples entidades

#### 3. Prompts y Schema

**Archivos:**
- `llm/prompts/entity_pairwise_classification.py` - Schema Pydantic
- `llm/prompts/entity_pairwise_classification_system_prompt.md.jinja` - Instrucciones para LLM
- `llm/prompts/entity_pairwise_classification_user_prompt.md.jinja` - Datos de contexto

**Schema de respuesta:**
```python
class StructuredOutput(BaseModel):
    classification_changes: List[ClassificationChange]  # Cambios a aplicar
    confidence: float  # 0.0-1.0
    reasoning: str

class ClassificationChange(BaseModel):
    entity_id: int
    classification: Literal['alias', 'ambiguous', 'not_an_entity', 'none']
    canonical_id: Optional[int]  # Para ALIAS
    canonical_ids: Optional[List[int]]  # Para AMBIGUOUS
```

#### 4. Tracking de Pares Comparados

**Tabla**: `entity_pair_comparisons`

**Propósito**: Guardar historial de todas las comparaciones para **no re-testar** pares ya analizados.

**Schema**:
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

**Flujo de tracking**:
```python
# Antes de comparar par con IA, verificar si ya existe
min_id = min(entity_a.id, entity_b.id)
max_id = max(entity_a.id, entity_b.id)

existing = session.query(EntityPairComparison).filter_by(
    entity_a_id=min_id,
    entity_b_id=max_id
).first()

if existing:
    # ✅ Par ya comparado, skip
    continue

# ❌ Par nuevo, comparar con IA
result = compare_entities_with_ai(entity_a, entity_b, session)

# Derivar relación de clasificaciones
relationship = "DIFFERENT"  # Default
for change in result.classification_changes:
    if change.classification == 'alias':
        relationship = "SAME"
        break
    elif change.classification == 'ambiguous':
        relationship = "AMBIGUOUS"
        break

# Guardar comparación
pair = EntityPairComparison(
    entity_a_id=min_id,
    entity_b_id=max_id,
    relationship=relationship,
    confidence=result.confidence,
    reasoning=result.reasoning
)
session.add(pair)
session.flush()
```

**Beneficios**:
- ✅ No re-testa pares (ahorro de costos API)
- ✅ Audit trail completo de decisiones
- ✅ Permite revisión manual de comparaciones
- ✅ Datos para análisis y mejora del sistema

**Queries útiles**:
```sql
-- Ver todas las comparaciones
SELECT * FROM entity_pair_comparisons ORDER BY created_at DESC;

-- Ver solo pares considerados iguales
SELECT * FROM entity_pair_comparisons WHERE relationship = 'SAME';

-- Ver comparaciones con baja confianza (revisar manualmente)
SELECT * FROM entity_pair_comparisons WHERE confidence < 0.7;

-- Ver estadísticas por relación
SELECT relationship, COUNT(*), AVG(confidence)
FROM entity_pair_comparisons
GROUP BY relationship;
```

---

## Flujo de Clasificación

### Caso de Uso: "Luis" vs "Luis Abinader"

```python
# 1. LSH encuentra candidatos
candidates = lsh_matcher.find_candidates("Luis", max_candidates=10)
# Retorna: [("Luis Abinader", 0.65), ("Luis Gil", 0.60), ...]

# 2. Para cada candidato, comparación 1v1
result = compare_entities_with_ai(
    entity_a="Luis",
    entity_b="Luis Abinader",
    jaccard_similarity=0.65
)

# 3. LLM analiza contexto de AMBAS entidades:
context = {
    'entity_a_name': 'Luis',
    'entity_a_mentions': 45,
    'entity_a_context': [
        "El presidente Luis anunció hoy...",
        "Luis visitó la provincia...",
    ],
    'entity_b_name': 'Luis Abinader',
    'entity_b_mentions': 120,
    'entity_b_context': [
        "Luis Abinader firmó el decreto...",
        "El mandatario Luis Abinader...",
    ],
    'shared_articles': 30,  # Aparecen juntos en 30 artículos
    'jaccard_similarity': 0.65,
    'cooccurrence_sentences': [
        "El presidente Luis Abinader, a quien también llaman Luis..."
    ]
}

# 4. LLM responde:
{
    'relationship': 'same_entity',
    'entity_a_action': 'make_alias',      # "Luis" → ALIAS
    'entity_b_action': 'no_change',       # "Luis Abinader" sigue CANONICAL
    'confidence': 0.92,
    'reasoning': 'Alta co-ocurrencia (30 artículos) y contexto presidencial compartido.'
}

# 5. Aplicar acciones (si confidence ≥0.70):
# - "Luis" se convierte en ALIAS de "Luis Abinader"
# - Ambas entidades marcadas como last_review_type='ai-assisted'
# - Ambas aprobadas (is_approved=1) porque confidence ≥0.90
```

---

## Niveles de Confianza y Auto-Aprobación

### Confianza por Tipo de Relación

| Relación | Umbral Auto-Aprobación | Ejemplo |
|----------|------------------------|---------|
| `same_entity` | ≥ 0.90 | "Luis" → "Luis Abinader" (clara evidencia) |
| `different_entities` | ≥ 0.80 | "Luis Abinader" vs "Luis Gil" (distintos) |
| `ambiguous_usage` | ≥ 0.85 | "Luis" puede ser varios (conservador) |

### Acciones según Confianza

**Confianza ≥ 70%:**
- ✅ **APLICAR** cambios en clasificación de ambas entidades
- 📝 Guardar sugerencia con `applied=1`
- 🔍 Aprobar automáticamente si confianza supera umbral específico

**Confianza < 70%:**
- ❌ **NO APLICAR** cambios
- 📝 Guardar solo como sugerencia (`applied=0`)
- 👤 Requiere revisión manual

**SIEMPRE (todos los casos):**
- Marcar ambas entidades como `last_review_type='ai-assisted'`
- Guardar en `entity_classification_suggestions` para auditoría

---

## Diferencias Clave: "Aplicar" vs "Guardar Sugerencia"

### APLICAR (confianza ≥70%)
- **Cambia la clasificación inmediatamente** en la base de datos
- La entidad queda clasificada (ALIAS, CANONICAL, etc.) y puede ser usada por el sistema
- Se marca como `last_review_type='ai-assisted'`
- Campo `applied=1` en la tabla de sugerencias
- **Ejemplo:** "Luis" pasa de CANONICAL → ALIAS de "Luis Abinader"

### GUARDAR SUGERENCIA (confianza <70%)
- **NO cambia** la clasificación de la entidad
- Solo guarda la recomendación del LLM en `entity_classification_suggestions`
- La entidad mantiene su clasificación actual
- Un humano debe revisar y decidir manualmente si aplicarla
- Campo `applied=0` en la tabla de sugerencias
- **Ejemplo:** "Luis" permanece CANONICAL, pero hay una sugerencia pendiente

### Tabla Comparativa

| Confianza | Relación | Aplicar | Aprobar | Estado Final |
|-----------|----------|---------|---------|--------------|
| 95% | same_entity | ✅ Sí | ✅ Sí | ALIAS aplicado + aprobado |
| 75% | same_entity | ✅ Sí | ❌ No | ALIAS aplicado + no aprobado (revisar) |
| 55% | same_entity | ❌ No | ❌ No | Sugerencia guardada (no aplicada) |

---

## Acciones Bidireccionales

A diferencia del enfoque batch (1 vs N), **ambas entidades pueden cambiar**:

### Ejemplo 1: Alias Simple
```
Entity A: "Luis" (CANONICAL)
Entity B: "Luis Abinader" (CANONICAL)

LLM decide:
- entity_a_action: 'make_alias'
- entity_b_action: 'no_change'

Resultado:
- "Luis" → ALIAS de "Luis Abinader"
- "Luis Abinader" → Permanece CANONICAL
```

### Ejemplo 2: Ambos son Aliases (caso raro)
```
Entity A: "BCRD" (CANONICAL)
Entity B: "Banco Central RD" (CANONICAL)

LLM decide:
- entity_a_action: 'make_alias'
- entity_b_action: 'make_alias'

Problema: No se puede aplicar (ambos quieren ser alias)
Solución: Retorna False, no aplica cambios
```

### Ejemplo 3: Error de NER
```
Entity A: "Ayer" (CANONICAL, GPE) ← Error del NER
Entity B: "Ayerbe" (CANONICAL, PERSON)

LLM decide:
- entity_a_action: 'make_not_an_entity'  ← Detecta error
- entity_b_action: 'no_change'

Resultado:
- "Ayer" → NOT_AN_ENTITY (limpia error)
- "Ayerbe" → Permanece CANONICAL
```

---

## Comando CLI

```bash
# Clasificar todas las entidades algorítmicas no aprobadas
uv run news entity ai-classify

# Filtrar por tipo
uv run news entity ai-classify --type person
uv run news entity ai-classify --type org

# Limitar cantidad
uv run news entity ai-classify --limit 100

# Ajustar confianza mínima (default: 0.70)
uv run news entity ai-classify --min-confidence 0.80

# Ajustar máximo de candidatos por entidad (default: 10)
uv run news entity ai-classify --max-candidates 5

# Dry-run (simular sin aplicar cambios)
uv run news entity ai-classify --dry-run

# Combinar opciones
uv run news entity ai-classify --type person --limit 50 --min-confidence 0.75
```

**Output:**
```
🤖 Clasificando entidades con IA...

📊 Estadísticas:
   Procesadas:               100
   Éxitos:                   75
   Aplicadas:                60
   Auto-aprobadas:           45
   Confianza baja:           20
   Sin candidatos:           3
   Errores:                  2

✅ Clasificación completada
```

---

## Optimizaciones de Rendimiento

### 1. LSH Reduce Complejidad
- **Sin LSH (naive)**: O(n²) comparaciones
  - 10,000 entidades = 50,000,000 comparaciones = $20,000
- **Con LSH**: O(n·k) donde k ≈ 5-10
  - 10,000 entidades × 5 candidatos = 50,000 comparaciones = $20
  - **Reducción de 1000x**

### 2. Índice Reutilizable
```python
# Construir índice una vez
lsh_matcher = build_lsh_index_for_type(session, 'person', threshold=0.3)

# Reusar para múltiples entidades
for entity in entities:
    candidates = lsh_matcher.find_candidates(entity)
    # No reconstruye el índice cada vez
```

### 3. Agrupación por Tipo
El batch agrupa entidades por tipo y construye un índice LSH por tipo:
```python
# En lugar de:
# - Procesar 1000 PERSON → construir índice 1000 veces
# Hace:
# - Construir índice PERSON una vez
# - Procesar 1000 PERSON con mismo índice
```

### 4. Threshold Configurable
```python
# Threshold bajo = más candidatos (más recall, menos precision)
matcher = EntityLSHMatcher(threshold=0.3)  # 30% similitud

# Threshold alto = menos candidatos (más precision, menos recall)
matcher = EntityLSHMatcher(threshold=0.6)  # 60% similitud

# Balance recomendado: 0.4 (40%)
```

---

## Costos Estimados

### Por Comparación
- **Tokens de entrada**: ~800 tokens (contexto de ambas entidades)
- **Tokens de salida**: ~100 tokens (respuesta estructurada)
- **Costo con gpt-5-nano**: ~$0.0004 por comparación

### Ejemplo Real
- **1,000 entidades algorítmicas sin aprobar**
- **5 candidatos promedio por entidad** (gracias a LSH)
- **5,000 comparaciones totales**
- **Costo total: $2.00**

### Comparación sin LSH
- **1,000 entidades**
- **100 candidatos promedio** (comparar con todas las CANONICAL)
- **100,000 comparaciones totales**
- **Costo total: $40.00**
- **Ahorro con LSH: $38.00 (95%)**

---

## Tabla de Base de Datos

### `entity_classification_suggestions`

Almacena todas las sugerencias del LLM para auditoría y feedback:

```sql
CREATE TABLE entity_classification_suggestions (
    id INTEGER PRIMARY KEY,
    entity_id INTEGER NOT NULL,  -- FK a named_entities

    -- Sugerencia del LLM
    suggested_classification VARCHAR(20) NOT NULL,  -- "pairwise:same_entity"
    suggested_canonical_ids JSON,                   -- [entity_b_id]
    confidence FLOAT NOT NULL,
    reasoning TEXT NOT NULL,

    -- Alternativa (si confianza no es muy alta)
    alternative_classification VARCHAR(20),
    alternative_confidence FLOAT,

    -- Estado de aplicación
    applied INTEGER NOT NULL DEFAULT 0,        -- 0=solo sugerencia, 1=aplicado
    approved_by_user INTEGER,                  -- NULL=pendiente, 0=rechazado, 1=aprobado

    created_at DATETIME NOT NULL,

    FOREIGN KEY (entity_id) REFERENCES named_entities(id) ON DELETE CASCADE
);
```

**Ejemplo de registro:**
```json
{
    "id": 123,
    "entity_id": 456,
    "suggested_classification": "pairwise:same_entity",
    "suggested_canonical_ids": [789],
    "confidence": 0.92,
    "reasoning": "vs Luis Abinader: Alta co-ocurrencia (30 artículos) y contexto presidencial compartido.",
    "applied": 1,
    "approved_by_user": null,
    "created_at": "2025-01-20 15:30:00"
}
```

---

## Testing y Validación

### Dry-Run Mode
```bash
# Simular sin aplicar cambios
uv run news entity ai-classify --dry-run --limit 10
```

Esto:
- ✅ Llama al LLM
- ✅ Calcula confianza
- ✅ Muestra decisiones
- ❌ NO modifica entidades
- ❌ NO guarda sugerencias

### Validar Resultados
```python
# Revisar sugerencias guardadas
from db.models import EntityClassificationSuggestion

suggestions = session.query(EntityClassificationSuggestion).filter(
    EntityClassificationSuggestion.applied == 1,
    EntityClassificationSuggestion.confidence >= 0.90
).all()

for s in suggestions:
    print(f"Entity {s.entity_id}: {s.suggested_classification} ({s.confidence:.2f})")
    print(f"  Reasoning: {s.reasoning}")
```

---

## Mejoras Futuras

### 1. Comando para Revisar Sugerencias
```bash
uv run news entity suggestions list
uv run news entity suggestions apply <suggestion_id>
uv run news entity suggestions reject <suggestion_id>
```

### 2. Feedback Loop
- Usuarios aprueban/rechazan sugerencias
- Sistema aprende de feedback
- Ajusta thresholds automáticamente

### 3. Métricas de Calidad
```python
# Precision: % de sugerencias aplicadas que fueron correctas
# Recall: % de relaciones correctas que fueron detectadas
# F1-score: Balance entre precision y recall
```

### 4. Paralelización
```python
# Procesar comparaciones en paralelo
from concurrent.futures import ThreadPoolExecutor

with ThreadPoolExecutor(max_workers=10) as executor:
    futures = [
        executor.submit(compare_entities_with_ai, entity, candidate, ...)
        for candidate in candidates
    ]
    results = [f.result() for f in futures]
```

### 5. Cache de Comparaciones
```python
# Evitar re-comparar los mismos pares
cache_key = f"{min(entity_a_id, entity_b_id)}:{max(entity_a_id, entity_b_id)}"
if cache_key in comparison_cache:
    return comparison_cache[cache_key]
```

---

## Referencias

- **LSH explicado**: https://en.wikipedia.org/wiki/Locality-sensitive_hashing
- **MinHash**: https://en.wikipedia.org/wiki/MinHash
- **Datasketch library**: https://github.com/ekzhu/datasketch
- **Structured Outputs (OpenAI)**: https://platform.openai.com/docs/guides/structured-outputs

---

## Notas Importantes

1. **LSH no es determinístico**: Puede encontrar candidatos ligeramente diferentes en ejecuciones distintas (depende de random seeds en MinHash)

2. **Threshold es crítico**:
   - Muy bajo (0.2) → Demasiados candidatos (lento, costoso)
   - Muy alto (0.7) → Pocos candidatos (pierde matches)
   - Recomendado: **0.4** (40% similitud)

3. **Solo compara con CANONICAL**: LSH solo indexa entidades ya marcadas como CANONICAL para evitar alias-alias comparisons

4. **Sesgo geográfico**: Los prompts incluyen convenciones dominicanas específicas (partidos políticos, lugares, nombres comunes)

5. **No sustituye revisión manual**: El sistema ayuda, pero casos muy complejos aún requieren juicio humano
