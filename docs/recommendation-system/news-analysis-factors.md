# Sistema de Análisis de Noticias para Recomendaciones

## Información a Extraer o Generar por Noticia

### 1. **Metadatos Básicos**

**Título, subtítulo y URL**: Permiten identificar la noticia de forma única y presentarla al usuario. El título es especialmente útil para algoritmos de CTR (Click-Through Rate) prediction.

**Fecha y hora de publicación**: Fundamental para ordenar cronológicamente, detectar noticias frescas vs. evergreen content, y aplicar decaimiento temporal en las recomendaciones (noticias recientes suelen ser más relevantes).

**Fuente/Medio de comunicación**: Permite filtrar por preferencias de fuentes confiables del usuario y aplicar ponderaciones según la autoridad y reputación del medio.

**Autor(es)**: Útil para rastrear periodistas específicos que ciertos usuarios prefieren seguir y para análisis de autoridad/expertise.

**Sección/Categoría editorial**: Clasificación primaria (política, deportes, tecnología, etc.) que facilita el filtrado colaborativo y la segmentación inicial de contenidos.

### 2. **Análisis del Contenido Textual**

**Extracción del cuerpo completo**: El texto íntegro permite análisis profundos de similitud semántica con otras noticias y con los intereses del usuario.

**Resumen automático (abstractive o extractive)**: Genera descripciones concisas que pueden mostrarse al usuario y sirven como representación compacta para cálculos de similitud más eficientes.

**Palabras clave y términos principales (TF-IDF, RAKE, YAKE)**: Identifican los conceptos centrales de la noticia, permitiendo matching rápido con intereses del usuario sin procesar todo el texto.

**Temas y subtemas (Topic Modeling - LDA, NMF, BERTopic)**: Descubre categorías latentes más granulares que las secciones editoriales, capturando matices temáticos que mejoran la precisión de las recomendaciones.

### 3. **Reconocimiento de Entidades (NER)**

**Personas mencionadas**: Permite recomendar noticias sobre figuras públicas, políticos, celebridades o expertos que interesan al usuario.

**Organizaciones y empresas**: Facilita seguimiento de compañías, instituciones, partidos políticos u organizaciones relevantes para el usuario.

**Ubicaciones geográficas**: Esencial para personalizar según intereses locales, regionales o internacionales del usuario (noticias de su ciudad, país, etc.).

**Eventos específicos**: Identifica acontecimientos puntuales (elecciones, catástrofes, eventos deportivos) permitiendo agrupar cobertura relacionada.

**Productos y tecnologías**: Útil para usuarios interesados en lanzamientos, innovaciones o sectores específicos (ej. nuevos iPhone, IA, criptomonedas).

### 4. **Análisis Semántico Avanzado**

**Embeddings de texto (BERT, RoBERTa, Sentence Transformers)**: Representaciones vectoriales densas que capturan el significado profundo del texto, permitiendo búsquedas semánticas y cálculos de similitud precisos entre noticias y perfiles de usuario.

**Conceptos y relaciones semánticas**: Extrae no solo entidades sino las relaciones entre ellas (X causó Y, Z es consecuencia de W), enriqueciendo la comprensión contextual.

**Frames narrativos**: Identifica el enfoque o perspectiva desde la cual se cuenta la historia (económico, social, ético), útil para diversificar recomendaciones y evitar cámaras de eco.

### 5. **Análisis de Sentimiento y Tono**

**Polaridad general (positivo/negativo/neutral)**: Permite balancear el feed de noticias según preferencias del usuario (algunos prefieren noticias positivas, otros quieren estar informados de todo).

**Emociones detectadas (alegría, tristeza, ira, miedo, sorpresa)**: Recomendaciones más sofisticadas pueden ajustarse al estado emocional inferido del usuario o diversificar el impacto emocional del contenido.

**Tono editorial (formal, informal, alarmista, objetivo, opinión)**: Ayuda a distinguir entre periodismo de investigación, opinión, análisis o entretenimiento, adaptándose al tipo de contenido que cada usuario prefiere.

**Grado de controversia o sesgo político**: Detecta si la noticia es polarizante o neutral, permitiendo ofrecer perspectivas balanceadas o, alternativamente, alinear con preferencias ideológicas del usuario.

### 6. **Características de Calidad y Credibilidad**

**Indicadores de calidad periodística**: Presencia de fuentes citadas, datos verificables, autoría clara, corrección gramatical. Útil para priorizar contenido confiable sobre clickbait.

**Nivel de clickbait**: Detecta titulares sensacionalistas o engañosos mediante análisis de patrones lingüísticos, permitiendo penalizar contenido de baja calidad.

**Fact-checking y verificación**: Si la noticia ha sido verificada o desmentida por agencias de fact-checking, crucial para combatir desinformación.

**Profundidad del análisis**: Distingue entre noticias breaking (cortas, urgentes) y artículos de investigación (largos, profundos), adaptándose al tiempo y preferencias del usuario.

### 7. **Análisis Multimedia**

**Imágenes principales y sus características**: Extrae imágenes, analiza su contenido con computer vision (objetos, escenas, personas), genera embeddings visuales que complementan el análisis textual.

**Calidad visual**: Resolución, composición profesional vs. amateur, lo que indica la seriedad de la publicación.

**Videos embebidos**: Detecta presencia de videos, su duración y tema, ya que algunos usuarios prefieren contenido multimedia.

**Infografías y gráficos**: Identifica contenido visual informativo que puede ser preferido por usuarios que valoran datos presentados visualmente.

### 8. **Características de Engagement y Viralidad**

**Métricas sociales iniciales**: Shares, likes, comentarios en redes sociales (si están disponibles), que predicen el interés general y pueden usarse como señal de calidad o relevancia.

**Tasa de crecimiento del engagement**: La velocidad con que una noticia gana tracción indica si es trending, útil para surfear olas de interés.

**Predicción de viralidad**: Modelos ML entrenados que predicen si una noticia tiene potencial de volverse viral, permitiendo adelantarse a tendencias.

### 9. **Características Temporales y de Actualidad**

**Frescura (recency)**: Tiempo transcurrido desde publicación, con decaimiento exponencial para priorizar lo más nuevo en temas de actualidad.

**Tipo de temporalidad**: Distingue entre breaking news (urgente), noticias de actualidad (días), features (semanas) y evergreen (atemporal), aplicando estrategias de recomendación diferenciadas.

**Eventos relacionados en el tiempo**: Conexión con noticias previas o posteriores sobre el mismo tema (seguimiento de historias en desarrollo).

**Ciclo de vida de la noticia**: Predicción de cuánto tiempo permanecerá relevante, útil para decidir cuándo dejar de recomendarla.

### 10. **Relaciones y Conexiones**

**Similaridad con otras noticias**: Cálculo de similitud coseno entre embeddings, permitiendo recomendar noticias relacionadas o evitar duplicados.

**Clusters temáticos**: Agrupación de noticias similares que cubren el mismo evento desde diferentes ángulos, útil para ofrecer perspectivas múltiples.

**Cadenas de historias**: Identificación de secuencias narrativas (historia en desarrollo) para recomendar updates a usuarios que leyeron la historia original.

**Noticias complementarias**: Detección de artículos que proveen contexto o background necesario para entender la noticia actual.

### 11. **Características de Audiencia Target**

**Nivel de complejidad/legibilidad**: Métricas como Flesch-Kincaid que indican si el texto es accesible o requiere conocimiento especializado, permitiendo ajustar a nivel educativo del usuario.

**Audiencia demográfica implícita**: Inferencia sobre qué segmentos demográficos probablemente se interesen (edad, educación, profesión), basado en lenguaje y contenido.

**Intereses específicos requeridos**: Identifica si la noticia requiere interés previo en temas nicho (ej. finanzas cuantitativas, astrofísica) vs. interés general.

### 12. **Metadatos de Consumo**

**Tiempo estimado de lectura**: Calculado por número de palabras, útil para recomendar contenido apropiado según el tiempo disponible del usuario.

**Dificultad de lectura**: Combinación de complejidad sintáctica y vocabulario técnico, para ajustar a capacidades del usuario.

**Formato de presentación**: Artículo tradicional, listicle, Q&A, entrevista, crónica narrativa, cada uno apela a diferentes preferencias de consumo.

### 13. **Contexto Económico y Comercial**

**Industrias/sectores mencionados**: Permite recomendaciones especializadas para profesionales de sectores específicos.

**Implicaciones financieras**: Detecta noticias que pueden afectar mercados, útil para inversores o profesionales de finanzas.

**Relevancia regional económica**: Impacto en economías locales vs. globales.

### 14. **Características de Diversidad**

**Perspectiva cultural/geográfica**: Desde qué punto de vista cultural se narra la historia, útil para ofrecer perspectivas diversas.

**Voces representadas**: Diversidad de fuentes citadas (género, etnias, posiciones), indicador de cobertura balanceada.

**Originalidad**: Grado de originalidad vs. contenido agregado o republicado, priorizando reportajes originales.

### 15. **Metadatos Técnicos para Optimización**

**Vector de características completo**: Consolidación de todos los features anteriores en una representación unificada para modelos de ML.

**Índices de búsqueda**: Tokens y n-gramas indexados para búsquedas rápidas.

**Hash de contenido**: Para deduplicación eficiente de noticias idénticas o casi idénticas.

**Versión y updates**: Tracking de ediciones y actualizaciones de la noticia, útil para re-rankear contenido actualizado.
