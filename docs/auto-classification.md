# Sistema Automático de Clasificación de Entidades

## Contexto Actual

Hoy el sistema:
1. **NER detecta entidades** durante la indexación → las crea automáticamente como `CANONICAL`
2. **Usuario revisa manualmente** y reclasifica (`ALIAS`, `AMBIGUOUS`, `NOT_AN_ENTITY`)
3. El sistema tiene ya toda la infraestructura para desambiguación

## Problema a Resolver

Miles de entidades quedan sin clasificar (`needs_review=1`), especialmente:
- **Iniciales/Acrónimos**: "JCE" vs "Junta Central Electoral"
- **Apellidos**: "Fernández" vs "Leonel Fernández"
- **Nombres cortos de instituciones**: "Junta Central" vs "Junta Central Electoral"

## Solución Propuesta: Batch Auto-Classification

Un nuevo proceso batch que detecta **patrones heurísticos** y sugiere/aplica clasificaciones automáticas.

---

## Optimización: Reverse Index y Ordenamiento por Longitud

### Nueva Tabla: `entity_tokens`

Para evitar comparaciones O(n²) entre todas las entidades, usamos un **reverse index** que mapea tokens individuales a las entidades que los contienen.

**Esquema de la tabla:**

| Campo | Tipo | Descripción | Ejemplo |
|-------|------|-------------|---------|
| `id` | INTEGER | ID único del token | 1, 2, 3... |
| `entity_id` | INTEGER | Referencia a `named_entities.id` | 123 → "Junta Central Electoral" |
| `token` | VARCHAR(100) | Token original con formato | "J.C.E.", "Junta", "de" |
| `token_normalized` | VARCHAR(100) | Token normalizado (sin acentos, lowercase, sin puntos) | "jce", "junta", "de" |
| `position` | INTEGER | Posición del token en el nombre (0-indexed) | 0, 1, 2... |
| `is_stopword` | INTEGER | 1 si es stopword, 0 si no | 0 (Junta), 1 (de) |
| `seems_like_initials` | INTEGER | 1 si parece iniciales/acrónimo, 0 si no | 1 (JCE), 0 (Junta) |
| `created_at` | DATETIME | Timestamp de creación | 2025-01-15 10:30:00 |

**Relaciones:**
- `entity_id` → `named_entities(id)` con `ON DELETE CASCADE`

**Índices para búsquedas rápidas:**

| Índice | Campos | Propósito |
|--------|--------|-----------|
| `idx_entity_tokens_normalized` | `token_normalized` | Buscar entidades por token normalizado |
| `idx_entity_tokens_entity` | `entity_id` | Buscar todos los tokens de una entidad |
| `idx_entity_tokens_composite` | `token_normalized, entity_id` | Búsquedas combinadas optimizadas |
| `idx_entity_tokens_initials` | `seems_like_initials` | Filtrar rápidamente iniciales/acrónimos |

**Características:**
- Se puebla automáticamente cuando NER detecta una nueva entidad
- Permite búsquedas O(log n) por token en lugar de O(n) comparaciones completas
- Almacena versión normalizada (sin acentos, lowercase) para matching flexible
- Marca stopwords para poder excluirlas en búsquedas si es necesario
- Mantiene posición para validar orden de palabras
- Detecta tokens que parecen iniciales/acrónimos para optimizar búsquedas

**Campo `seems_like_initials`:**

Se marca como `1` (True) cuando se cumplen **TODAS** estas condiciones:
1. El token está completamente en mayúsculas (ej: "JCE", "FBI", "USA")
2. El nombre de la entidad está compuesto por un solo token no-stopword
3. El token es idéntico al nombre de la entidad después de remover puntos finales de ambos

**Ejemplos:**

| Entidad | Token | `seems_like_initials` | Razón |
|---------|-------|-----------------------|-------|
| "J.C.E." | "J.C.E." | `1` ✅ | Mayúsculas, 1 token, "JCE" == "JCE" (sin puntos) |
| "JCE" | "JCE" | `1` ✅ | Mayúsculas, 1 token, "JCE" == "JCE" |
| "FBI" | "FBI" | `1` ✅ | Mayúsculas, 1 token, "FBI" == "FBI" |
| "Jce" | "Jce" | `0` ❌ | No está completamente en mayúsculas |
| "J.C.E. Dominicana" | "J.C.E." | `0` ❌ | La entidad tiene más de 1 token no-stopword |
| "Junta Central" | "Junta" | `0` ❌ | No está en mayúsculas |

**Uso en búsquedas:**

| Caso de Uso | Filtro | Resultado |
|-------------|--------|-----------|
| Buscar solo iniciales/acrónimos | `seems_like_initials = 1` | "JCE", "FBI", "USA" |
| Excluir iniciales/acrónimos | `seems_like_initials = 0` | "Junta Central", "Federal Bureau" |
| Optimizar matching de nombres largos | `seems_like_initials = 1` | Candidatos rápidos para expansión |

**Tokenización**

Para el proceso de tokenización, cada token es una palabra. El separador es cualquier
carácter distinto de letras (mayúsculas o minúsculas) o números. Hay un caso especial:
el punto. El punto NO es considerado un separador si el carácter inmediatamente anterior
y el carácter inmediatamente siguiente son letras o números (Por ejemplo: en "J.C.E."
los dos primeros puntos NO son considerados separadores porque tienen letras a ambos lados
pero el último sí lo es).

Finalmente, se revisa si el token tiene puntos en su interior y si lo tiene se le agrega
uno al final ("J.C.E" es reconstruido como "J.C.E.")

Ejemplo:

```python
# Entidad: "Junta Central Electoral" (ID: 123)
# Tokens generados: (entity_id, token, token_normalized, position, is_stopword, seems_like_initials)
[
    (123, "Junta", "junta", 0, False, False),
    (123, "Central", "central", 1, False, False),
    (123, "Electoral", "electoral", 2, False, False)
]

# Entidad: "Banco Central de la República Dominicana" (ID: 456)
# Tokens generados (con stopwords):
[
    (456, "Banco", "banco", 0, False, False),
    (456, "Central", "central", 1, False, False),
    (456, "de", "de", 2, True, False),          # Stopword
    (456, "la", "la", 3, True, False),          # Stopword
    (456, "República", "republica", 4, False, False),
    (456, "Dominicana", "dominicana", 5, False, False)
]

# Entidad: "J.C.E." (ID: 789) - con punto final, parece iniciales
# Tokens generados:
[
    (789, "J.C.E.", "jce", 0, False, True),  # ✅ seems_like_initials=True
]

# Entidad: "JCE" (ID: 321) - sin puntos, parece iniciales
# Tokens generados:
[
    (321, "JCE", "jce", 0, False, True),  # ✅ seems_like_initials=True
]

# Entidad: "FBI" (ID: 999) - parece iniciales
# Tokens generados:
[
    (999, "FBI", "fbi", 0, False, True),  # ✅ seems_like_initials=True
]
```

### Nuevo Campo: `name_length` en `named_entities`

**Modificaciones a la tabla:**

| Campo | Tipo | Constraint | Descripción |
|-------|------|-----------|-------------|
| `name_length` | INTEGER | `CHECK(name_length >= 0 AND name_length <= 255)` | Longitud del nombre de la entidad |

**Índice:**
- `idx_named_entities_name_length` en `name_length ASC` (más cortas primero)

**Propósito:**
- Almacena `len(entity.name)` al crear/actualizar la entidad
- Permite ordenar entidades por longitud de nombre (más cortas primero)
- Optimiza queries sin necesidad de calcular `LENGTH(name)` dinámicamente
- Rango de 0-255 caracteres (suficiente para nombres de entidades)

**Ejemplo de ordenamiento:**

| Entity ID | Nombre | `name_length` | Orden de procesamiento |
|-----------|--------|---------------|------------------------|
| 789 | "JCE" | 3 | 1º (más corta - evaluada) |
| 456 | "Junta Central" | 14 | 2º |
| 123 | "Junta Central Electoral" | 24 | 3º (más larga - candidato) |

**¿Por qué procesar las cortas primero?**
- La búsqueda en el reverse index está diseñada para que **entidades cortas** encuentren **candidatos largos**
- Entidades cortas son **siempre las evaluadas**
- Entidades largas son **siempre los candidatos**
- El algoritmo modifica la entidad evaluada (la corta), convirtiéndola en ALIAS de la candidata (la larga)

### Refactorización: `needs_review` → Dos Campos Separados

**Campos actuales:**

| Campo | Tipo | Default | Descripción |
|-------|------|---------|-------------|
| `needs_review` | INTEGER | 1 | 1=necesita revisión, 0=revisado |
| `last_review` | DATETIME | NULL | Timestamp de última revisión |

**Campos nuevos:**

| Campo | Tipo | Default | Constraint | Descripción |
|-------|------|---------|-----------|-------------|
| `last_review_type` | VARCHAR(20) | 'none' | `CHECK(last_review_type IN ('none', 'algorithmic', 'ai-assisted', 'manual'))` | Método de revisión |
| `is_approved` | INTEGER | 0 | - | 0=no aprobada, 1=aprobada |
| `last_review` | DATETIME | NULL | - | **MANTENER** - Timestamp de última revisión |

**Índices nuevos:**

| Índice | Campos | Propósito |
|--------|--------|-----------|
| `idx_named_entities_review_type` | `last_review_type` | Filtrar por método de revisión |
| `idx_named_entities_approved` | `is_approved` | Filtrar aprobadas/no aprobadas |
| `idx_named_entities_review_status` | `last_review_type, is_approved` | Búsquedas combinadas eficientes |

**Separación de Responsabilidades:**

| Campo | Propósito | Valores |
|-------|-----------|---------|
| `last_review_type` | ¿Cómo fue revisada? | `none`, `algorithmic`, `ai-assisted`, `manual` |
| `is_approved` | ¿Fue aprobada? | `0` (no), `1` (sí) |
| `last_review` | ¿Cuándo fue revisada? | DATETIME o NULL |

**Valores de `last_review_type`:**

| Valor | Descripción                                       | Cuándo se asigna                        |
|-------|---------------------------------------------------|-----------------------------------------|
| `none` | Sin revisar (recién creada o actualizada por NER) | Default al crear o actualizar entidad   |
| `algorithmic` | Revisada por heurísticas automáticas              | Después de `auto-classify`              |
| `ai-assisted` | Revisada con asistencia de IA/LLM                 | **Uso futuro** - validación con GPT     |
| `manual` | Revisada manualmente por humano                   | Cuando usuario clasifica explícitamente |

**Combinaciones posibles:**

| `last_review_type` | `is_approved` | Significado                                                           |
|-------------------|---------------|-----------------------------------------------------------------------|
| `none` | `0` | Sin revisar (NER creó o actualizó una entidad)                        |
| `algorithmic` | `1` | ✅ Auto-aprobada (**SOLO cuando es ALIAS**)                            |
| `algorithmic` | `0` | ⚠️ Revisada algorítmicamente pero NO aprobada (AMBIGUOUS o sin match) |
| `ai-assisted` | `1` | ✅ IA sugirió y aprobó                                                 |
| `ai-assisted` | `0` | ⚠️ IA sugirió pero no aprobó                                          |
| `manual` | `1` | ✅ Usuario aprobó manualmente                                          |
| `manual` | `0` | ⚠️ Usuario revisó pero no aprobó (ej: marcó NOT_AN_ENTITY)            |

**IMPORTANTE - Relación Evaluada/Candidato**:
- **Entidades EVALUADAS**: Las más cortas, procesadas en orden `name_length ASC` (cortas → largas)
- **Entidades CANDIDATOS**: Las más largas, encontradas vía reverse index
- El algoritmo **siempre modifica SOLO la entidad EVALUADA (la corta)**
- Los **CANDIDATOS NUNCA se modifican** (ni clasificación, ni `is_approved`, ni `last_review_type`)
- La entidad EVALUADA puede convertirse en ALIAS o AMBIGUOUS según el estado del candidato

**Reglas de aprobación**:
- El proceso `auto-classify` marca **TODAS** las entidades evaluadas como `last_review_type='algorithmic'`
- Solo aprueba (`is_approved=1`) en estos casos:
  - A1: Evaluada CANONICAL → ALIAS de candidato CANONICAL
  - B1: Evaluada CANONICAL → ALIAS de canonical del candidato ALIAS
  - B2.1: Evaluada ALIAS, candidato ALIAS, mismo canonical (confirma relación)
- Todos los demás casos: `is_approved` NO se modifica (mantiene valor original)

## Estrategia de Implementación

### 1. Detección de posibles candidatos para comparación

Todas las detecciones usan el **reverse index (`entity_tokens`)** para búsquedas eficientes.

Buscan en el índice invertido candidatos con los cuales compararse. Son entidades con nombres que cumplan con una de estas características:
- Todos los tokens que componen el nombre de la entidad examinada (excepto stop words) forman parte del nombre del candidato
- Entidades que "parezcan iniciales" y su `token_normalized` coincida con lo que resultaría de tomar el nombre de la entidad evaluada, remover stopwords, combinar las iniciales y poner en minúsculas.
  - Nota 1: Este criterio no se usa en la búsqueda de candidatos para entidades siendo evaluadas cuyo nombre tenga un solo token que no sea stopword.
  - Nota 2: Este criterio no se usa en la búsqueda de candidatos para entidades siendo evaluadas que parezcan iniciales ellas mismas.
  - Nota 3: Cuando se encuentran es necesario confirmarlas encontrando un artículo en el que aparezcan ambas (Por ejemplo: Si "JCE" coincide con "Junta Católica Ecuménica" y con "Junta Central Electoral", pero no podemos encontrar ningún artículo en el que se mencione "JCE" y "Junta Católica Ecuménica", pero sí "JCE" y "Junta Central Electoral", "JCE" pasa a ser alias de "Junta Central Electoral" pero no de "Junta Católica Ecuménica").

### 2. Detección de Patrones

#### A. Iniciales/Acrónimos (PERSON, ORG)

**Detección:**

Posibles resultados en el paso de la detección:

```
"J.C.E." está contenido en "Junta Central Electoral"
"JCE" está contenido en "J.C.E."
"LF" está contenido en "Leonel Fernandez"
```

**Pasos del matching para cada candidato:**
- Obtener iniciales de la evaluada ("J.C.E." → "JCE")
- Obtener iniciales del candidato ("Junta Central Electoral" → "JCE")
- Comparar iniciales ("JCE" == "JCE")
- Si coinciden: marcar la evaluada como alias del candidato ("J.C.E." → ALIAS de "Junta Central Electoral")
- Si no hay match y la entidad evaluada es de tipo PERSON (ejemplo: "J.M. Fernández" evaluada, "José Miguel Fernández" candidato)
  - Por cada palabra en el nombre del candidato, iterar y expandir:
    - Convertir palabra de la iteración en inicial (primera iteración: "José" → "J"; segunda iteración: "Miguel" → "M")
    - Remover puntos, espacios y comparar (primera iteración: "JMFernández" != "JMiguelFernández"; segunda iteración: "JMFernández" == "JMFernández")
    - Si hay match: establecer la evaluada ("J. M. Fernández") como ALIAS del candidato ("José Miguel Fernández") 

**Casos según clasificación de evaluada y candidato:**

**EVALUADA es CANONICAL:**

1. **Candidato es CANONICAL** (Caso A1) → hacer evaluada ALIAS del candidato ✅
   ```python
   # "JCE" (evaluada) es CANONICAL
   # "Junta Central Electoral" (candidato) es CANONICAL
   # Acción: Hacer "JCE" ALIAS de "Junta Central Electoral"
   jce.set_as_alias(junta_central_electoral, session)
   jce.last_review_type = 'algorithmic'
   jce.is_approved = 1  # ← ✅ Auto-aprobada
   jce.last_review = datetime.now()
   ```

2. **Candidato es ALIAS** (Caso B1) → hacer evaluada ALIAS del canonical del candidato ✅
   ```python
   # "JCE" (evaluada) es CANONICAL
   # "Junta Central" (candidato) es ALIAS de "Junta Central Electoral" (ID: 123)
   # Acción: Hacer "JCE" ALIAS de "Junta Central Electoral"
   jce.set_as_alias(junta_central_electoral, session)  # candidato.canonical_ref
   jce.last_review_type = 'algorithmic'
   jce.is_approved = 1  # ← ✅ Auto-aprobada
   jce.last_review = datetime.now()
   ```

3. **Candidato es AMBIGUOUS** (Caso C1) → hacer evaluada AMBIGUOUS heredando canonicals
   ```python
   # "JCE" (evaluada) es CANONICAL
   # "Junta Central Electoral" (candidato) es AMBIGUOUS → [org1, org2]
   # Acción: Hacer "JCE" AMBIGUOUS agregando las canonicals del candidato
   jce.set_as_ambiguous([org1, org2], session)  # candidato.canonicals
   jce.last_review_type = 'algorithmic'
   # is_approved NO se modifica (mantiene el valor original)
   jce.last_review = datetime.now()
   ```

**EVALUADA es ALIAS:**

4. **Candidato es CANONICAL** (Caso A2) → convertir evaluada a AMBIGUOUS
   ```python
   # "JCE" (evaluada) es ALIAS de "Junta Católica Ecuménica" (ID: 500)
   # "Junta Central Electoral" (candidato, ID: 123) es CANONICAL
   # Acción: Convertir "JCE" a AMBIGUOUS con ambas canonicals
   jce.set_as_ambiguous([junta_catolica, junta_central], session)
   jce.last_review_type = 'algorithmic'
   # is_approved NO se modifica (mantiene el valor original)
   jce.last_review = datetime.now()
   ```

5. **Candidato es ALIAS** (Casos B2.1 y B2.2):
   - **Mismo canonical** (B2.1) → confirmar relación ✅
     ```python
     # "JCE" (evaluada) es ALIAS de "Junta Central Electoral" (ID: 123)
     # "Junta Central" (candidato) es ALIAS de "Junta Central Electoral" (ID: 123)
     # Acción: No cambiar clasificación, solo marcar como revisada
     jce.last_review_type = 'algorithmic'
     jce.is_approved = 1  # ← ✅ Auto-aprobada (confirma)
     jce.last_review = datetime.now()
     ```
   - **Distinto canonical** (B2.2) → convertir evaluada a AMBIGUOUS
     ```python
     # "JCE" (evaluada) es ALIAS de "Junta Católica Ecuménica" (ID: 500)
     # "Junta Central" (candidato) es ALIAS de "Junta Central Electoral" (ID: 123)
     # Acción: Convertir "JCE" a AMBIGUOUS con ambas canonicals
     jce.set_as_ambiguous([junta_catolica, junta_central_electoral], session)
     jce.last_review_type = 'algorithmic'
     # is_approved NO se modifica (mantiene el valor original)
     jce.last_review = datetime.now()
     ```

6. **Candidato es AMBIGUOUS** (Caso C2) → sumar canonicals del candidato
   ```python
   # "JCE" (evaluada) es ALIAS de "Junta Católica Ecuménica" (ID: 500)
   # "Junta Central Electoral" (candidato) es AMBIGUOUS → [org1, org2]
   # Acción: Hacer "JCE" AMBIGUOUS sumando canonicals
   jce.set_as_ambiguous([junta_catolica] + [org1, org2], session)
   jce.last_review_type = 'algorithmic'
   # is_approved NO se modifica (mantiene el valor original)
   jce.last_review = datetime.now()
   ```

**EVALUADA es AMBIGUOUS:**

7. **Candidato es CANONICAL** (Caso A3) → sumar candidato a canonicals
   ```python
   # "JCE" (evaluada) es AMBIGUOUS → [org1, org2]
   # "Junta Central Electoral" (candidato, ID: 123) es CANONICAL
   # Acción: Agregar candidato a lista de canonicals
   jce.set_as_ambiguous([org1, org2, junta_central], session)
   jce.last_review_type = 'algorithmic'
   # is_approved NO se modifica (mantiene el valor original)
   jce.last_review = datetime.now()
   ```

8. **Candidato es ALIAS** (Caso B3) → sumar canonical del candidato si no está
   ```python
   # "JCE" (evaluada) es AMBIGUOUS → [org1, org2]
   # "Junta Central" (candidato) es ALIAS de "Junta Central Electoral" (ID: 123)
   # Acción: Agregar canonical del candidato si no está en la lista
   if junta_central_electoral not in jce.canonical_refs:
       jce.set_as_ambiguous([org1, org2, junta_central_electoral], session)
       jce.last_review_type = 'algorithmic'
       # is_approved NO se modifica (mantiene el valor original)
       jce.last_review = datetime.now()
   ```

9. **Candidato es AMBIGUOUS** (Caso C3) → sumar canonicals del candidato que no estén
   ```python
   # "JCE" (evaluada) es AMBIGUOUS → [org1, org2]
   # "Junta Central Electoral" (candidato) es AMBIGUOUS → [org2, org3]
   # Acción: Agregar solo canonicals nuevas del candidato
   nuevas = [c for c in candidato.canonical_refs if c not in jce.canonical_refs]
   if nuevas:
       jce.set_as_ambiguous([org1, org2] + nuevas, session)
       jce.last_review_type = 'algorithmic'
       # is_approved NO se modifica (mantiene el valor original)
       jce.last_review = datetime.now()
   ```

#### B. Nombres Parciales de Personas y Organizaciones (PERSON, ORG)

**Detección:**
```
"José Paliza" contenido en "José Antonio Paliza"
"Leonel Fernandez" contenido en "Leonel Fernandez Reyna"
"Abinader" contenido en "Luís Abinader"
```

**Pasos del matching:**
- La evaluada es siempre la más corta (ej: "José Paliza")
- El candidato es siempre el más largo (ej: "José Antonio Paliza")
- Buscar cada palabra de la evaluada en el candidato ("José" ⊂ "José Antonio Paliza") AND ("Paliza" ⊂ "José Antonio Paliza")
- Validar orden de palabras en el candidato: ("José Antonio Paliza".find("José") < "José Antonio Paliza".find("Paliza"))
- Crear alias: evaluada → ALIAS del candidato ("José Paliza" → "José Antonio Paliza")

**Casos según clasificación de evaluada y candidato:**

Los mismos 9 casos documentados en la sección A (Iniciales/Acrónimos) aplican aquí.
Ver casos completos en líneas 279-397.

---

### 2. Nuevo Comando CLI

```bash
# Ejecutar auto-clasificación (dry-run por defecto)
# IMPORTANTE: Solo procesa entidades con last_review_type='none'
uv run news entity auto-classify --type person --dry-run
uv run news entity auto-classify --type org --limit 100

# Solo ver qué habría pasado sin hacerlo
uv run news entity auto-classify --dry-run

# Aplicar solo iniciales/acrónimos
uv run news entity auto-classify --pattern acronyms --apply
```

**Parámetros:**

| Parámetro | Tipo | Default | Descripción |
|-----------|------|---------|-------------|
| `--type` | choice | all | Filtrar por tipo: `person`, `org`, `all` |
| `--dry-run` | flag | True | Solo mostrar sugerencias, no aplicar |
| `--pattern` | choice | all | Patrones: `acronyms`, `partial-names`, `all` |
| `--limit` | int | None | Limitar número de entidades procesadas |
| `--domain` | str | None | Filtrar entidades por dominio (vía artículos) |

**Filtro automático:**
- **Solo procesa entidades con `last_review_type='none'`**
- Ignora entidades ya revisadas (`algorithmic`, `ai-assisted`, `manual`)
- Esto previene reclasificar entidades ya procesadas o validadas manualmente

---

### 3. Casos Edge y Validaciones

#### A. Conflictos de clasificación (Conversión automática a AMBIGUOUS)

**Escenario 1: Alias existente + nuevo match**
```
"JCE" ya es ALIAS de "Junta Católica Ecuménica" (ID: 500)
Sistema detecta: "JCE" también coincide con "Junta Central Electoral" (ID: 123)
```

**Acción automática:**
```python
# Convertir a AMBIGUOUS con ambas canonicals
jce.set_as_ambiguous([junta_catolica, junta_central], session)
jce.last_review_type = 'algorithmic'
# is_approved NO se modifica (mantiene el valor original)
jce.last_review = datetime.now()
```

**Output:**
```
⚠️  [456] "JCE" → AMBIGUOUS (upgraded from ALIAS)
   Canonical refs: ["Junta Católica Ecuménica" [500], "Junta Central Electoral" [123]]
   Review: algorithmic, Approved: No (requires manual validation)
   Reason: Conflicting aliases detected
```

**Escenario 2: Entidad larga es AMBIGUOUS**
```
"Leonel Fernández Reyna" es AMBIGUOUS → [político DR, empresario MX]
Sistema detecta: "Fernández" coincide con "Leonel Fernández Reyna"
```

**Acción automática:**
```python
# Hacer "Fernández" AMBIGUOUS agregándole las canonicals de "Leonel Fernández Reyna" a "Fernández"
fernandez.set_as_ambiguous([politico_dr, empresario_mx], session)
fernandez.last_review_type = 'algorithmic'
# is_approved NO se modifica (mantiene el valor original)
fernandez.last_review = datetime.now()
```

**Output:**
```
⚠️  [789] "Fernández" → AMBIGUOUS (inherited from longer match)
   Canonical refs: ["Leonel Fernández (político DR)" [100], "Leonel Fernández (empresario MX)" [200]]
   Review: algorithmic, Approved: No (inherited ambiguity)
   Reason: Matched AMBIGUOUS entity
```

#### B. Clasificaciones aprobadas automáticamente (ALIAS de CANONICAL)

**Escenario:**
```
"Junta Central Electoral" es CANONICAL
Sistema detecta: "JCE" coincide con "Junta Central Electoral"
```

**Acción automática:**
```python
# Hacer "JCE" ALIAS de "Junta Central Electoral"
jce.set_as_alias(junta_central_electoral, session)
jce.last_review_type = 'algorithmic'
jce.is_approved = 1  # ✅ Auto-aprobada
jce.last_review = datetime.now()
```

**Output:**
```
✅ [456] "JCE" → ALIAS of "Junta Central Electoral" [123]
   Review: algorithmic, Approved: Yes ✅
   Confidence: high (acronym pattern match)
```

#### C. Entidades que permanecen CANONICAL (sin match)

**Escenario:**
```
"Fernández" no coincide con ninguna entidad más larga
```

**Acción automática:**
```python
# Dejar como CANONICAL pero marcar como revisada
entity.last_review_type = 'algorithmic'
entity.last_review = datetime.now()
# is_approved NO se modifica (mantiene el valor original)
```

**Output:**
```
ℹ️  [789] "Fernández" → CANONICAL (no matches found)
   Review: algorithmic, Approved: No (potential generic surname, needs manual review)
   Action: Reviewed but not classified (no pattern matched)
```

---

## Reglas de Aprobación Automática

### Matriz de Clasificación y Estados

| Acción | Clasificación | `last_review_type` | `is_approved` | Caso | Razón |
|--------|--------------|-------------------|---------------|------|-------|
| Evaluada CANONICAL → ALIAS de candidato CANONICAL | `ALIAS` | `algorithmic` | `1` ✅ | A1 | Auto-aprobada |
| Evaluada CANONICAL → ALIAS de canonical del candidato ALIAS | `ALIAS` | `algorithmic` | `1` ✅ | B1 | Auto-aprobada |
| Evaluada ALIAS, candidato ALIAS, mismo canonical | Sin cambio | `algorithmic` | `1` ✅ | B2.1 | Confirma relación existente |
| Evaluada ALIAS → AMBIGUOUS (candidato CANONICAL diferente) | `AMBIGUOUS` | `algorithmic` | Sin cambio ⚠️ | A2 | Conflicto detectado |
| Evaluada ALIAS → AMBIGUOUS (candidato ALIAS diferente) | `AMBIGUOUS` | `algorithmic` | Sin cambio ⚠️ | B2.2 | Conflicto detectado |
| Evaluada CANONICAL → AMBIGUOUS (candidato AMBIGUOUS) | `AMBIGUOUS` | `algorithmic` | Sin cambio ⚠️ | C1 | Hereda ambigüedad |
| Evaluada ALIAS → AMBIGUOUS (candidato AMBIGUOUS) | `AMBIGUOUS` | `algorithmic` | Sin cambio ⚠️ | C2 | Hereda y suma ambigüedad |
| Evaluada AMBIGUOUS + candidato cualquiera | `AMBIGUOUS` | `algorithmic` | Sin cambio ⚠️ | A3/B3/C3 | Suma canonicals |
| Sin match encontrado | `CANONICAL` | `algorithmic` | Sin cambio ⚠️ | - | Revisada sin cambios |

**Reglas clave de aprobación**:

| Acción del Proceso | Modifica `is_approved` | Cuándo |
|-------------------|----------------------|--------|
| Crear **ALIAS** desde CANONICAL | ✅ SÍ → `1` | Casos A1 y B1 |
| Confirmar ALIAS existente | ✅ SÍ → `1` | Caso B2.1 (mismo canonical) |
| Crear/modificar AMBIGUOUS | ❌ NO | Todos los casos C, A2, A3, B2.2, B3 |
| Sin match (CANONICAL) | ❌ NO | Cuando no encuentra candidatos |

**Aclaraciones importantes**:
- El proceso aprueba (`is_approved = 1`) en **exactamente 3 casos**: A1, B1, B2.1
- El proceso **NUNCA modifica `is_approved`** en otros casos (mantiene valor original)
- El proceso **NUNCA rechaza** entidades
- **TODAS** las entidades procesadas se marcan como `last_review_type='algorithmic'`

### Flujo de Decisiones

```
Entidad EVALUADA (corta, last_review_type='none')
        ↓
Buscar CANDIDATOS (largos) en reverse index
        ↓
¿Encontró candidato que coincida?
        ↓
     ┌──┴────────────────────────────┐
     ↓                               ↓
   [NO]                            [SÍ]
     ↓                               ↓
MARCAR evaluada:                     |
last_review_type                     |
='algorithmic'                       |
     ↓                               |
is_approved NO                       |
se modifica                          |
     ↓                               |
    FIN                              |
                                     ↓
                       ¿Clasificación del CANDIDATO?
                                     ↓
                    ┌────────────────┼────────────────┐
                    ↓                ↓                ↓
                CANONICAL          ALIAS          AMBIGUOUS
                    ↓                ↓                ↓
                 Caso A            Caso B           Caso C

═══════════════════════════════════════════════════════════════
CASO A: CANDIDATO es CANONICAL
═══════════════════════════════════════════════════════════════
    ¿Clasificación de la EVALUADA?
        ↓
    ┌───┼────┐
    ↓   ↓    ↓
  CANON ALIAS AMBI
    ↓   ↓    ↓
   A1   A2   A3

    A1. Evaluada es CANONICAL:
        set_as_alias(candidato)
        last_review_type='algorithmic'
        is_approved=1 ← ✅ APROBADO
        FIN

    A2. Evaluada es ALIAS:
        set_as_ambiguous([canonical_vieja, candidato])
        last_review_type='algorithmic'
        is_approved NO se modifica
        FIN

    A3. Evaluada es AMBIGUOUS:
        set_as_ambiguous(evaluada.canonicals + [candidato])
        last_review_type='algorithmic'
        is_approved NO se modifica
        FIN

═══════════════════════════════════════════════════════════════
CASO B: CANDIDATO es ALIAS
═══════════════════════════════════════════════════════════════
    ¿Clasificación de la EVALUADA?
        ↓
    ┌───┼────┐
    ↓   ↓    ↓
  CANON ALIAS AMBI
    ↓   ↓    ↓
   B1   B2   B3

    B1. Evaluada es CANONICAL:
        set_as_alias(candidato.canonical_ref)
        last_review_type='algorithmic'
        is_approved=1 ← ✅ APROBADO
        FIN

    B2. Evaluada es ALIAS:
        ¿Apuntan al mismo canonical?
            ↓
        ┌───┴───┐
        ↓       ↓
       SÍ      NO
        ↓       ↓
     [B2.1]  [B2.2]

        B2.1. Mismo canonical:
            # No cambiar clasificación (ya correcta)
            last_review_type='algorithmic'
            is_approved=1 ← ✅ APROBADO
            FIN

        B2.2. Distinto canonical:
            set_as_ambiguous([canonical_vieja, candidato.canonical_ref])
            last_review_type='algorithmic'
            is_approved NO se modifica
            FIN

    B3. Evaluada es AMBIGUOUS:
        ¿candidato.canonical_ref ya está en evaluada.canonicals?
            ↓
        ┌───┴───┐
        ↓       ↓
       SÍ      NO
        ↓       ↓
     [B3.1]  [B3.2]

        B3.1. Ya está incluido:
            # No cambiar canonicals (ya correcta)
            last_review_type='algorithmic'
            is_approved NO se modifica
            FIN

        B3.2. No está incluido:
            set_as_ambiguous(evaluada.canonicals + [candidato.canonical_ref])
            last_review_type='algorithmic'
            is_approved NO se modifica
            FIN

═══════════════════════════════════════════════════════════════
CASO C: CANDIDATO es AMBIGUOUS
═══════════════════════════════════════════════════════════════
    ¿Clasificación de la EVALUADA?
        ↓
    ┌───┼────┐
    ↓   ↓    ↓
  CANON ALIAS AMBI
    ↓   ↓    ↓
   C1   C2   C3

    C1. Evaluada es CANONICAL:
        ¿evaluada ya está en candidato.canonicals?
            ↓
        ┌───┴───┐
        ↓       ↓
       SÍ      NO
        ↓       ↓
     [C1.1]  [C1.2]

        C1.1. Ya está incluida:
            # No cambiar canonicals (ya correcta)
            last_review_type='algorithmic'
            is_approved NO se modifica
            FIN

        C1.2. No está incluida:
            set_as_ambiguous(candidato.canonicals + [evaluada])
            last_review_type='algorithmic'
            is_approved NO se modifica
            FIN

    C2. Evaluada es ALIAS:
        ¿canonical_vieja ya está en candidato.canonicals?
            ↓
        ┌───┴───┐
        ↓       ↓
       SÍ      NO
        ↓       ↓
     [C2.1]  [C2.2]

        C2.1. Ya está incluida:
            set_as_ambiguous(candidato.canonicals)
            last_review_type='algorithmic'
            is_approved NO se modifica
            FIN

        C2.2. No está incluida:
            set_as_ambiguous([canonical_vieja] + candidato.canonicals)
            last_review_type='algorithmic'
            is_approved NO se modifica
            FIN

    C3. Evaluada es AMBIGUOUS:
        nuevas_canonicals = candidato.canonicals - evaluada.canonicals
        ¿Hay alguna canonical nueva que necesite agrgarse?
            ↓
        ┌───┴───┐
        ↓       ↓
       NO      SÍ
        ↓       ↓
     [C3.1]  [C3.2]

        C3.1. Sin nuevas:
            # No cambiar canonicals (ya correcta)
            last_review_type='algorithmic'
            is_approved NO se modifica
            FIN

        C3.2. Hay nuevas:
            set_as_ambiguous(evaluada.canonicals + nuevas_canonicals)
            last_review_type='algorithmic'
            is_approved NO se modifica
            FIN

═══════════════════════════════════════════════════════════════
ACTUALIZACIÓN EN CASCADA: Cuando CANONICAL cambia clasificación
═══════════════════════════════════════════════════════════════

Cuando una entidad CANONICAL se convierte en ALIAS o AMBIGUOUS, todas
las entidades que apuntaban a ella deben actualizarse:

┌─────────────────────────────────────────────────────────────┐
│ CASO: Ex-CANONICAL se convirtió en ALIAS                    │
└─────────────────────────────────────────────────────────────┘

Para cada entidad dependiente que apuntaba a la ex-CANONICAL:

    1. Dependiente es ALIAS:
       - Redirigir al nuevo canonical de la ex-CANONICAL
       - Ejemplo:
         • "Paliza" era ALIAS de "José Paliza" (ex-CANONICAL)
         • "José Paliza" ahora es ALIAS de "José Antonio Paliza"
         → "Paliza" debe ser ALIAS de "José Antonio Paliza"

    2. Dependiente es AMBIGUOUS (tiene ex-CANONICAL en su lista):
       - Reemplazar ex-CANONICAL con su nuevo canonical en la lista
       - Ejemplo:
         • "JP" era AMBIGUOUS → ["José Paliza", "Juan Pérez"]
         • "José Paliza" ahora es ALIAS de "José Antonio Paliza"
         → "JP" debe ser AMBIGUOUS → ["José Antonio Paliza", "Juan Pérez"]

┌─────────────────────────────────────────────────────────────┐
│ CASO: Ex-CANONICAL se convirtió en AMBIGUOUS                │
└─────────────────────────────────────────────────────────────┘

Para cada entidad dependiente que apuntaba a la ex-CANONICAL:

    1. Dependiente es ALIAS:
       - Convertir a AMBIGUOUS heredando las canonicals de ex-CANONICAL
       - Ejemplo:
         • "Paliza" era ALIAS de "José Paliza" (ex-CANONICAL)
         • "José Paliza" ahora es AMBIGUOUS → [persona1, persona2]
         → "Paliza" debe ser AMBIGUOUS → [persona1, persona2]

    2. Dependiente es AMBIGUOUS (tiene ex-CANONICAL en su lista):
       - Reemplazar ex-CANONICAL con sus canonicals en la lista
       - Ejemplo:
         • "JP" era AMBIGUOUS → ["José Paliza", "Juan Pérez"]
         • "José Paliza" ahora es AMBIGUOUS → [persona1, persona2]
         → "JP" debe ser AMBIGUOUS → [persona1, persona2, "Juan Pérez"]

**IMPORTANTE:**
- Estas actualizaciones deben hacerse ANTES de cambiar la clasificación
  de la ex-CANONICAL
- Todas las dependientes heredan `last_review_type='algorithmic'`
- `is_approved` NO se modifica en las dependientes (mantienen valor)

═══════════════════════════════════════════════════════════════
REGLAS CLAVE:
═══════════════════════════════════════════════════════════════
• Entidades procesadas de corta → larga (name_length ASC)
• Entidad EVALUADA = siempre la corta
• Entidad CANDIDATO = siempre la larga (del reverse index)
• Los CANDIDATOS pueden ser CANONICAL, ALIAS o AMBIGUOUS
• TODAS las evaluadas → last_review_type='algorithmic'
• Se aprueban (is_approved=1) en estos casos:
  - A1: Evaluada CANONICAL → ALIAS de candidato CANONICAL
  - B1: Evaluada CANONICAL → ALIAS de canonical del candidato ALIAS
  - B2.1: Evaluada ALIAS, candidato ALIAS, mismo canonical (confirma)
• TODO lo demás → is_approved NO se modifica (sin aprobar)
• Cuando CANONICAL cambia: actualizar en cascada sus dependientes
```

---

## Mantenimiento del Reverse Index

### Actualización Automática

El reverse index (`entity_tokens`) se mantiene automáticamente durante:

**Operaciones y mantenimiento:**

| Operación | Momento | Acción en `entity_tokens` | Responsable |
|-----------|---------|--------------------------|-------------|
| **Crear entidad** | NER detecta nueva entidad | Tokenizar nombre y poblar tabla | `populate_entity_tokens()` |
| **Actualizar nombre** | Usuario edita nombre | Borrar tokens viejos + crear nuevos | `update_entity_name()` |
| **Eliminar entidad** | Usuario borra entidad | **Automático** (CASCADE) | Base de datos |

**Flujo de creación:**

```
1. NER detecta "Junta Central Electoral"
   ↓
2. Crear registro en named_entities
   - name = "Junta Central Electoral"
   - entity_type = "ORG"
   - name_length = 24
   ↓
3. Tokenizar y crear registros en entity_tokens:
   [
     (entity_id=123, token="Junta", token_normalized="junta", position=0, is_stopword=0),
     (entity_id=123, token="Central", token_normalized="central", position=1, is_stopword=0),
     (entity_id=123, token="Electoral", token_normalized="electoral", position=2, is_stopword=0)
   ]
```

**Flujo de actualización:**

```
1. Usuario cambia nombre: "Junta Central Electoral" → "JCE"
   ↓
2. Eliminar tokens existentes de entity_id=123
   ↓
3. Actualizar named_entities:
   - name = "JCE"
   - name_length = 3
   ↓
4. Re-tokenizar y crear nuevo registro:
   [(entity_id=123, token="JCE", token_normalized="jce", position=0, is_stopword=0, seems_like_initials=1)]
```

**Flujo de eliminación:**

```
Usuario elimina entidad ID=123
   ↓
DELETE FROM named_entities WHERE id = 123
   ↓
[CASCADE automático] → DELETE FROM entity_tokens WHERE entity_id = 123
```
