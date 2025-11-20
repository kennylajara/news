# Sistema de Clasificación de Entidades Asistido por IA

## Contexto

El sistema ya cuenta con:
1. **Clasificación algorítmica** (`auto-classify`) - Detecta patrones heurísticos simples (iniciales, nombres parciales)
   - Gratis y muy rápido
   - Aprueba casos obvios automáticamente
2. **Clasificación manual** - El usuario revisa y clasifica entidades manualmente
   - Costoso en tiempo
   - Necesario para casos complejos

## Problema a Resolver

La clasificación algorítmica procesa muchas entidades pero **no las aprueba todas**:
- Marca como `last_review_type='algorithmic'`
- Pero deja `is_approved=0` en casos con incertidumbre

**Limitaciones del algoritmo:**
- **No entiende contexto semántico**: "Luis" podría ser "Luis Abinader" o "Luis Rodolfo Abinader"
- **No detecta sinónimos**: "Banco Central" vs "BCRD" (sin iniciales obvias)
- **Casos ambiguos complejos**: "Fernández" podría referirse a 5+ personas diferentes
- **Nombres con variaciones**: "República Dominicana" vs "Rep. Dominicana" vs "RD"

**Resultado:** Miles de entidades clasificadas algorítmicamente pero **sin aprobar** (`is_approved=0`), requiriendo revisión manual costosa.

## Estrategia: Clasificación Híbrida

```
┌─────────────────────────────────────────────────────────────┐
│ 1. NER detecta entidades → CANONICAL (last_review_type=none)│
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. Clasificación ALGORÍTMICA (heurísticas)                  │
│    - Gratis y rápido                                        │
│    - Aprueba casos obvios (is_approved=1)                   │
│    - Deja sin aprobar casos dudosos (is_approved=0)         │
│    → last_review_type='algorithmic'                         │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. Clasificación con IA (solo is_approved=0)                │
│    - Analiza contexto semántico                             │
│    - Agrega precisión donde el algoritmo tiene dudas        │
│    - Costo: ~$0.0004 por entidad                            │
│    → last_review_type='ai-assisted'                         │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. Revisión MANUAL (solo casos muy complejos)               │
│    - Solo entidades que IA no aprobó                        │
│    → last_review_type='manual'                              │
└─────────────────────────────────────────────────────────────┘
```

**Ventaja:** El algoritmo procesa miles de entidades gratis, y la IA solo revisa las que tienen incertidumbre (ahorro de costos).

## Solución Propuesta: Clasificación Asistida por IA

Un proceso batch que usa **modelos de lenguaje (LLM)** para analizar contexto semántico y sugerir clasificaciones inteligentes.

---

## Ventajas del Enfoque con IA

### 1. **Comprensión de Contexto**

El LLM puede leer oraciones completas donde aparecen las entidades:

**Ejemplo:**
```
Entidad evaluada: "Luis"
Candidatos: "Luis Abinader", "Luis Rodolfo Abinader"

Contexto del artículo:
"El presidente Luis anunció hoy..." → "Luis Abinader"
"Luis Rodolfo aseguró que..." → "Luis Rodolfo Abinader"
```

### 2. **Detección de Sinónimos y Variaciones**

El LLM conoce formas comunes de referirse a entidades:

**Ejemplo:**
```
"BCRD" → "Banco Central de la República Dominicana"
"Banco Central" → "Banco Central de la República Dominicana"
"Central de RD" → "Banco Central de la República Dominicana"
```

### 3. **Manejo de Ambigüedad Compleja**

Cuando hay múltiples candidatos igualmente válidos:

**Ejemplo:**
```
Entidad: "Martínez"
Contextos diferentes:
- "El ministro Martínez..." → Pedro Martínez (Ministro de Obras Públicas)
- "El diputado Martínez..." → José Martínez (Diputado PRM)
- "Martínez, del equipo..." → Juan Martínez (Jugador de béisbol)

Decisión: AMBIGUOUS con 3 canonicals
```

### 4. **Confianza Graduada**

El LLM expresa su nivel de certeza y el sistema actúa en consecuencia:

| Confianza | ¿Aplicar clasificación? | ¿Aprobar? | Ejemplo |
|-----------|-------------------------|-----------|---------|
| **90-100%** | ✅ Sí | ✅ Sí (`is_approved=1`) | "JCE" → "Junta Central Electoral" (contexto muy claro) |
| **70-89%** | ✅ Sí | ❌ No (`is_approved=0`) | "Luis" → "Luis Abinader" (probable pero verificar después) |
| **50-69%** | ❌ No | ❌ No | "Martínez" → ambiguo entre 3 personas (solo guardar sugerencia) |
| **<50%** | ❌ No | ❌ No | Insuficiente información (solo guardar sugerencia) |

**Diferencia entre "Aplicar" y "Guardar Sugerencia":**

**APLICAR (confianza ≥70%):**
- Cambia la clasificación de la entidad **inmediatamente** en la base de datos
- La entidad queda clasificada (ALIAS, AMBIGUOUS, etc.) y puede ser usada por el sistema
- Se marca como `last_review_type='ai-assisted'`
- Ejemplo: "Luis" pasa de CANONICAL → ALIAS de "Luis Abinader" **ahora mismo**

**GUARDAR SUGERENCIA (confianza <70%):**
- **NO cambia** la clasificación de la entidad
- Solo guarda la recomendación del LLM en `entity_classification_suggestions`
- La entidad mantiene su clasificación actual
- Un humano debe revisar y decidir manualmente si aplicarla
- Campo `applied=0` en la tabla de sugerencias

**Diferencia con "Aprobar":**

- **Aprobar** (`is_approved=1`) = Marcar como confiable para producción (no necesita revisión)
- Se puede aplicar SIN aprobar (confianza 70-89%): está en la DB pero necesita QA

**Ejemplo comparativo:**

| Confianza | Acción | Estado en DB | `applied` | `is_approved` |
|-----------|--------|--------------|-----------|---------------|
| **95%** | Aplicar + Aprobar | ALIAS en DB ✅ | 1 | 1 |
| **75%** | Aplicar sin aprobar | ALIAS en DB ⚠️ | 1 | 0 |
| **55%** | Solo guardar sugerencia | CANONICAL (sin cambios) 💾 | 0 | 0 |

**¿Por qué esta estrategia?**

- **Confianza ≥90%:** Casos obvios → aplicar y aprobar completamente
- **Confianza 70-89%:** Casos probables → aplicar para avanzar, pero flaggear para revisión
- **Confianza <70%:** Casos dudosos → no arriesgarse, solo guardar sugerencia

---

## Arquitectura del Sistema

### Flujo General

```
1. Filtrar entidades que necesitan precisión de IA
   └─> last_review_type = 'algorithmic' (ya procesadas por heurísticas)
   └─> is_approved = 0 (el algoritmo no las aprobó)
   └─> Ordenar por: article_count DESC (más contexto primero),
                     name_length ASC (aliases primero)

2. Por cada entidad (batch de 100):
   ├─> Buscar candidatos (reverse index)
   ├─> Obtener contexto de artículos
   ├─> Preparar datos para LLM
   ├─> Llamar API de OpenAI
   ├─> Procesar respuesta estructurada
   ├─> Aplicar clasificación según confianza
   └─> Marcar como last_review_type='ai-assisted'

3. Generar reporte de clasificaciones
   ├─> Auto-aprobadas (confianza ≥90%)
   ├─> Aplicadas sin aprobar (confianza 70-89%)
   └─> Solo sugeridas (confianza <70%)
```

**Nota importante:** La IA NO procesa entidades con `last_review_type='none'`. Primero debe ejecutarse la clasificación algorítmica para ahorrar costos.

### Componentes Clave

#### 1. Pre-filtrado con Reverse Index

Antes de llamar al LLM, usamos el **reverse index** (`entity_tokens`) para:
- Encontrar candidatos potenciales (solo entidades más largas con tokens coincidentes)
- Reducir de miles de entidades a 5-10 candidatos por evaluada
- **Ahorrar costos** de API al no enviar todo al LLM

**Beneficio:** En lugar de enviar 1000 entidades al LLM, enviamos solo los 5 candidatos más relevantes.

#### 2. Extracción de Contexto

Para cada entidad evaluada, se extrae:

| Dato | Fuente | Propósito |
|------|--------|-----------|
| **Menciones** | `article_entities.mentions` | Frecuencia de aparición |
| **Oraciones de contexto** | `article_entities.context_sentences` | Cómo se usa la entidad |
| **Artículos compartidos** | `article_entities` JOIN | ¿Candidato y evaluada aparecen juntos? |
| **Tipo detectado** | `named_entities.entity_type` | PERSON, ORG, GPE, etc. |
| **Relevancia** | `article_entities.relevance` | Importancia en el artículo |

**Ejemplo de contexto extraído:**
```json
{
  "entity_name": "Luis",
  "entity_type": "PERSON",
  "total_mentions": 45,
  "context_samples": [
    "El presidente Luis anunció hoy una nueva medida económica",
    "Luis afirmó que el gobierno continuará con las reformas"
  ],
  "candidates": [
    {
      "name": "Luis Abinader",
      "type": "PERSON",
      "shared_articles": 42,
      "context_overlap": "presidente, gobierno, reformas"
    },
    {
      "name": "Luis Rodolfo Abinader",
      "type": "PERSON",
      "shared_articles": 3,
      "context_overlap": "reformas"
    }
  ]
}
```

#### 3. Prompt Engineering

El sistema usa **templates Jinja2** para construir prompts estructurados:

**Sistema (`entity_classification_system_prompt.md.jinja`):**
```
Eres un experto en desambiguación de entidades para un portal de noticias
dominicano. Tu tarea es analizar menciones de entidades y determinar si
deben clasificarse como:

- CANONICAL: Entidad principal (ya existe o es nueva)
- ALIAS: Variante de otra entidad (ej: "JCE" → "Junta Central Electoral")
- AMBIGUOUS: Puede referirse a múltiples entidades (ej: "Martínez")
- NOT_AN_ENTITY: No es realmente una entidad (error de NER)

Considera:
- Contexto semántico de las oraciones
- Frecuencia de co-ocurrencia con candidatos
- Convenciones dominicanas (ej: "BCRD" = Banco Central)
- Coherencia con tipos detectados (PERSON, ORG, etc.)
```

**Usuario (`entity_classification_user_prompt.md.jinja`):**
```
Entidad a clasificar: {{ entity_name }}
Tipo detectado: {{ entity_type }}
Menciones totales: {{ total_mentions }}

Contexto de uso:
{% for sentence in context_samples %}
- {{ sentence }}
{% endfor %}

Candidatos encontrados:
{% for candidate in candidates %}
{{ loop.index }}. {{ candidate.name }} ({{ candidate.type }})
   - Artículos compartidos: {{ candidate.shared_articles }}
   - Contexto: {{ candidate.context_overlap }}
{% endfor %}

¿Cómo debe clasificarse "{{ entity_name }}"?
```

#### 4. Respuesta Estructurada (Pydantic)

El LLM devuelve una respuesta JSON validada:

**Schema (`src/llm/prompts/entity_classification.py`):**
```python
from pydantic import BaseModel, Field
from typing import Literal, Optional, List

class StructuredOutput(BaseModel):
    classification: Literal['canonical', 'alias', 'ambiguous', 'not_an_entity'] = Field(
        description="Clasificación recomendada para la entidad"
    )

    canonical_ids: Optional[List[int]] = Field(
        default=None,
        description="IDs de entidades canónicas (para ALIAS o AMBIGUOUS)"
    )

    confidence: float = Field(
        ge=0.0, le=1.0,
        description="Confianza de 0.0 a 1.0"
    )

    reasoning: str = Field(
        description="Explicación breve de la decisión (1-2 frases)"
    )
```

**Ejemplo de respuesta:**
```json
{
  "classification": "alias",
  "canonical_ids": [123],
  "confidence": 0.92,
  "reasoning": "Contexto indica que 'Luis' se refiere al presidente Luis Abinader. Aparecen juntos en 42 de 45 artículos con términos como 'presidente' y 'gobierno'."
}
```

---

## Lógica de Aplicación de Clasificaciones

### Reglas de Auto-aprobación

| Clasificación | Confianza | Acción | `is_approved` |
|---------------|-----------|--------|---------------|
| `alias` | ≥ 90% | Auto-aprobar | `1` ✅ |
| `alias` | 70-89% | Aplicar pero no aprobar | `0` ⚠️ |
| `alias` | < 70% | No aplicar (manual) | - |
| `ambiguous` | ≥ 80% | Auto-aprobar | `1` ✅ |
| `ambiguous` | 50-79% | Aplicar pero no aprobar | `0` ⚠️ |
| `ambiguous` | < 50% | No aplicar (manual) | - |
| `canonical` | Cualquiera | Mantener como está | - |
| `not_an_entity` | ≥ 85% | Auto-aprobar | `1` ✅ |

### Marcado de Revisión

**Todas las entidades procesadas se marcan:**
```python
entity.last_review_type = 'ai-assisted'
entity.last_review = datetime.utcnow()
# is_approved según tabla anterior
```

### Manejo de Conflictos

Si el algoritmo heurístico ya clasificó una entidad como `last_review_type='algorithmic'`:

**Regla:** El LLM puede **sobrescribir** si:
- Confianza del LLM ≥ 85%
- Clasificación del LLM difiere de la algorítmica

**Ejemplo:**
```
Estado actual:
- Entidad: "BC"
- classified_as: ALIAS → "Banco Central"
- last_review_type: 'algorithmic'
- is_approved: 1

LLM sugiere:
- classification: 'ambiguous'
- canonical_ids: [45, 67]  # "Banco Central" y "Barcelona FC"
- confidence: 0.88

Acción:
- Convertir a AMBIGUOUS
- Actualizar canonical_refs
- last_review_type = 'ai-assisted'
- is_approved = 0  (requiere confirmación humana por cambio)
```

---

## Integración con Sistema Existente

### Reutilización de Componentes

| Componente | Origen | Uso en IA-Assisted |
|------------|--------|-------------------|
| `entity_tokens` | Auto-classification | Pre-filtrado de candidatos |
| `openai_structured_output()` | Flash News generation | Llamada genérica a LLM |
| Prompt templates (Jinja2) | Core clustering | Sistema de prompts |
| `set_as_alias()` / `set_as_ambiguous()` | Entity models | Aplicar clasificaciones |
| Batch processing | Article enrichment | Procesar en lotes con logs |
| Cascade updates | Auto-classification | Actualizar dependientes |

### Nueva Tabla: `entity_classification_suggestions`

Para auditoría y revisión manual posterior:

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `id` | INTEGER | ID único |
| `entity_id` | INTEGER | Entidad evaluada |
| `suggested_classification` | VARCHAR(20) | 'alias', 'ambiguous', 'not_an_entity' |
| `suggested_canonical_ids` | JSON | IDs sugeridos (array) |
| `confidence` | FLOAT | 0.0 - 1.0 |
| `reasoning` | TEXT | Explicación del LLM |
| `applied` | INTEGER | 0 = sugerencia, 1 = aplicada |
| `approved_by_user` | INTEGER | NULL, 0 = rechazada, 1 = aprobada |
| `created_at` | DATETIME | Timestamp |

**Propósito:**
- Auditar todas las sugerencias del LLM
- Permitir revisión manual de sugerencias de baja confianza
- Mejorar el sistema con feedback humano

---

## Workflow de Uso

### Flujo Completo Recomendado

```bash
# PASO 1: Ejecutar clasificación algorítmica primero (gratis y rápido)
uv run news entity auto-classify

# Resultado:
# - Casos obvios: aprobados automáticamente (is_approved=1)
# - Casos dudosos: clasificados pero sin aprobar (is_approved=0)

# PASO 2: Ejecutar clasificación con IA para casos dudosos
uv run news entity ai-classify --min-confidence 0.70

# Resultado:
# - Confianza ≥90%: aprobados automáticamente
# - Confianza 70-89%: aplicados pero para revisión
# - Confianza <70%: solo guardados como sugerencias

# PASO 3: Revisar manualmente casos que IA no aprobó
uv run news entity suggestions list --pending-approval
```

### 1. Ejecutar Clasificación IA

```bash
# Dry-run para previsualizar (recomendado primero)
uv run news entity ai-classify --dry-run

# Aplicar clasificaciones con confianza alta (≥90% = auto-aprobar)
uv run news entity ai-classify --min-confidence 0.90

# Aplicar todas las sugerencias (≥70% = aplicar pero revisar después)
uv run news entity ai-classify --min-confidence 0.70

# Procesar solo un tipo de entidad
uv run news entity ai-classify --type person --min-confidence 0.85

# Limitar cantidad de entidades a procesar
uv run news entity ai-classify --limit 100
```

### 2. Revisar Sugerencias de Baja Confianza

```bash
# Ver sugerencias no aplicadas (confianza < umbral)
uv run news entity suggestions list --not-applied

# Ver sugerencias aplicadas pero no aprobadas
uv run news entity suggestions list --pending-approval

# Aprobar una sugerencia específica
uv run news entity suggestions approve <suggestion_id>

# Rechazar una sugerencia
uv run news entity suggestions reject <suggestion_id>
```

### 3. Generar Reportes

```bash
# Reporte de clasificaciones del último batch
uv run news entity ai-classify --report

# Estadísticas de accuracy
uv run news entity suggestions stats
```

**Salida esperada:**
```
📊 Reporte de Clasificación Asistida por IA

Entidades procesadas: 250
├─ Auto-aprobadas (confianza ≥90%): 180 (72%)
│  ├─ ALIAS: 120
│  ├─ AMBIGUOUS: 50
│  └─ NOT_AN_ENTITY: 10
├─ Aplicadas sin aprobar (70-89%): 45 (18%)
└─ Sugeridas para revisión manual (<70%): 25 (10%)

Tiempo promedio por entidad: 2.3 segundos
Costo estimado (API): $0.08
```

---

## Consideraciones Técnicas

### 1. Costos de API

**Estimación por entidad:**
- Tokens de entrada: ~500-800 (contexto + candidatos)
- Tokens de salida: ~100-150 (respuesta estructurada)
- Costo por entidad: **$0.0003 - $0.0005** (con GPT-5-nano)

**Para 10,000 entidades:** $3 - $5 USD

**Optimizaciones:**
- Pre-filtrar con reverse index (reduce candidatos enviados)
- Procesar en batch (compartir contexto común)
- Usar modelo más económico para casos simples (GPT-5-nano)
- Cachear resultados de entidades similares

### 2. Velocidad de Procesamiento

| Paso | Tiempo | Cuello de botella |
|------|--------|-------------------|
| Filtrado de candidatos | <1ms | Reverse index (indexado) |
| Extracción de contexto | 10-50ms | Queries SQL |
| Llamada a LLM | 1-3s | API de OpenAI |
| Aplicación de clasificación | <10ms | Updates SQL |
| **Total por entidad** | **~2-4s** | **LLM API** |

**Paralelización:**
- Procesar 10 entidades en paralelo → 10,000 entidades en ~30-60 minutos

### 3. Manejo de Errores

**Estrategia resiliente:**

```python
def classify_entity_with_ai(entity, session):
    try:
        # 1. Pre-filtrado
        candidates = find_candidates_via_index(entity)

        # 2. Extraer contexto
        context = extract_entity_context(entity, candidates, session)

        # 3. Llamar LLM con retry
        result = openai_structured_output(
            'entity_classification',
            context,
            max_retries=3
        )

        # 4. Validar respuesta
        if result.confidence < MIN_CONFIDENCE:
            log_suggestion(entity, result, applied=False)
            return ('skipped', 'low_confidence')

        # 5. Aplicar clasificación
        apply_classification(entity, result, session)
        log_suggestion(entity, result, applied=True)

        return ('success', result.classification)

    except OpenAIError as e:
        log_error(entity, e)
        return ('error', 'api_failure')

    except Exception as e:
        log_error(entity, e)
        return ('error', 'unexpected')
```

**Ventajas:**
- Un error no detiene el batch completo
- Logs detallados por entidad
- Retry automático de llamadas fallidas
- Sugerencias guardadas incluso si no se aplican

---

## Mejora Continua

### Feedback Loop

El sistema aprende de correcciones humanas:

**Proceso:**
1. Usuario revisa sugerencias de IA
2. Aprueba o rechaza vía comando CLI
3. Sistema registra feedback en `entity_classification_suggestions.approved_by_user`
4. **Futuro:** Reentrenar o ajustar prompts según feedback

**Métricas de Accuracy:**
```sql
-- Precisión del sistema
SELECT
  suggested_classification,
  COUNT(*) as total,
  SUM(CASE WHEN approved_by_user = 1 THEN 1 ELSE 0 END) as approved,
  ROUND(AVG(confidence), 2) as avg_confidence
FROM entity_classification_suggestions
WHERE applied = 1
GROUP BY suggested_classification;
```

**Output esperado:**
```
classification | total | approved | avg_confidence
---------------|-------|----------|---------------
alias          | 450   | 425      | 0.89
ambiguous      | 180   | 165      | 0.78
not_an_entity  | 35    | 32       | 0.91
```

### Ajuste de Umbrales

Según resultados de producción, ajustar:

| Parámetro | Actual | Ajuste Posible |
|-----------|--------|----------------|
| `MIN_CONFIDENCE_AUTO_APPROVE` | 0.90 | 0.85 si accuracy >95% |
| `MIN_CONFIDENCE_APPLY` | 0.70 | 0.75 si muchos falsos positivos |
| `MAX_CANDIDATES_TO_LLM` | 5 | 10 si se pierden matches |

---

## Comparación: Algoritmo vs IA

| Aspecto | Clasificación Algorítmica | Clasificación con IA |
|---------|---------------------------|----------------------|
| **Velocidad** | Instantánea (~1ms) | 2-4 segundos por entidad |
| **Costo** | $0 | ~$0.0004 por entidad |
| **Precisión** | 75-85% (casos simples) | 90-95% (casos complejos) |
| **Casos soportados** | Iniciales, nombres parciales | Sinónimos, contexto, ambigüedad |
| **Explainability** | Reglas fijas | Razonamiento del LLM |
| **Escalabilidad** | Miles/minuto | Cientos/minuto |
| **Mejor para** | Casos obvios (JCE → Junta) | Casos ambiguos (Luis → ¿quién?) |

**Estrategia recomendada (flujo híbrido):**
1. **Clasificación algorítmica primero** (gratis, rápida, procesa miles)
   - Aprueba casos obvios (`is_approved=1`)
   - Clasifica pero no aprueba casos dudosos (`is_approved=0`)
2. **IA para casos no aprobados** (costo bajo, agrega precisión)
   - Solo procesa `last_review_type='algorithmic'` + `is_approved=0`
   - Ahorro: solo paga por entidades que realmente necesitan IA
3. **Revisión manual** solo para casos extremadamente ambiguos
   - Solo entidades que IA tampoco aprobó

**Ejemplo de ahorro:**
- 10,000 entidades detectadas por NER
- Algoritmo procesa 10,000 (gratis) → aprueba 7,000, deja 3,000 sin aprobar
- IA procesa solo 3,000 ($1.20) → aprueba 2,500, deja 500 para manual
- Manual: solo 500 entidades (5% del total)
- **Ahorro vs procesar todo con IA:** $3 (70% menos costo)

---

## Próximos Pasos

### Fase 1: Implementación Base ✅ (Planeada)
- [x] Diseño de arquitectura
- [ ] Implementar `entity_classification.py` (processor)
- [ ] Crear prompts (system + user)
- [ ] Schema Pydantic para respuesta estructurada
- [ ] Comando CLI `entity ai-classify`

### Fase 2: Optimizaciones
- [ ] Batch processing con paralelización
- [ ] Sistema de sugerencias (`entity_classification_suggestions`)
- [ ] Comando de revisión (`entity suggestions`)
- [ ] Métricas y reportes

### Fase 3: Mejora Continua
- [ ] Feedback loop (aprender de correcciones)
- [ ] A/B testing de prompts
- [ ] Fine-tuning de umbrales de confianza
- [ ] Integración con UI web para revisión

---

## Conclusión

La clasificación asistida por IA complementa el sistema algorítmico existente, permitiendo:
- **Mayor precisión** en casos ambiguos
- **Comprensión semántica** del contexto
- **Reducción de trabajo manual** del 60-80%
- **Auditoría completa** de decisiones

El sistema está diseñado para ser:
- **Eficiente**: Pre-filtrado con reverse index
- **Económico**: ~$0.0004 por entidad
- **Seguro**: Sugerencias auditadas + umbrales de confianza
- **Escalable**: Procesamiento en batch + paralelización
