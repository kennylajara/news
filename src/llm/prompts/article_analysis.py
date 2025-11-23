"""
Pydantic schema for deep article analysis structured output.

This schema captures multiple dimensions of news articles for the recommendation system:
- Semantic concepts
- Narrative frames and perspectives
- Editorial tone and style
- Controversy and political bias indicators
- Journalistic quality metrics
- Audience targeting signals
- Industry/sector implications
- Geographic perspectives
"""

from typing import List, Optional
from pydantic import BaseModel, Field
from enum import Enum


class NarrativeFrame(str, Enum):
    """Narrative frames/perspectives used in the article."""
    ECONOMIC = "economic"           # Economic impact, costs, financial implications
    SOCIAL = "social"               # Social impact, community effects
    POLITICAL = "political"         # Political implications, power dynamics
    ETHICAL = "ethical"             # Moral/ethical considerations
    LEGAL = "legal"                 # Legal aspects, regulations, rights
    ENVIRONMENTAL = "environmental" # Environmental impact
    HEALTH = "health"               # Health/medical perspective
    SECURITY = "security"           # Security, safety concerns
    TECHNOLOGICAL = "technological" # Tech innovation, digital aspects
    CULTURAL = "cultural"           # Cultural significance, traditions
    HUMAN_INTEREST = "human_interest"  # Personal stories, emotional appeal


class EditorialTone(str, Enum):
    """Editorial tone of the article."""
    OBJECTIVE = "objective"         # Neutral, fact-based reporting
    ANALYTICAL = "analytical"       # In-depth analysis with interpretation
    OPINION = "opinion"             # Clear editorial stance
    INVESTIGATIVE = "investigative" # Exposé, uncovering facts
    SENSATIONALIST = "sensationalist"  # Dramatic, attention-grabbing
    INFORMATIVE = "informative"     # Educational, explanatory
    CRITICAL = "critical"           # Questioning, skeptical


class ContentFormat(str, Enum):
    """Format/type of content."""
    NEWS = "news"                   # Standard short/medium news article
    FEATURE = "feature"             # Deep reportage, investigation, profile (>1500 words)
    OPINION = "opinion"             # Opinion column
    ANALYSIS = "analysis"           # Expert analysis
    INTERVIEW = "interview"         # Interview format
    LISTICLE = "listicle"           # List/ranking format


class TemporalRelevance(str, Enum):
    """How quickly the article loses relevance."""
    BREAKING = "breaking"           # Relevance: hours/days (breaking news)
    TIMELY = "timely"               # Relevance: weeks/months (election analysis)
    EVERGREEN = "evergreen"         # Relevance: years (how-to guides)


class AudienceEducationLevel(str, Enum):
    """Required education/expertise level."""
    GENERAL = "general"             # General public, no expertise needed
    INFORMED = "informed"           # Some familiarity with topic helpful
    SPECIALIZED = "specialized"     # Requires domain knowledge


class AgeRange(str, Enum):
    """Target age range for the content."""
    YOUNG = "18-35"                 # Young adults
    MIDDLE = "35-55"                # Middle-aged
    MATURE = "55+"                  # Mature/senior
    ALL = "all"                     # All ages


class Profession(str, Enum):
    """Professional sectors that would find this relevant."""
    GENERAL = "general"             # General public, no specific profession
    LEGAL = "legal"                 # Lawyers, judges
    BUSINESS = "business"           # Business owners, executives
    MEDICAL = "medical"             # Doctors, healthcare professionals
    EDUCATION = "education"         # Teachers, educators
    TECHNOLOGY = "technology"       # Engineers, IT professionals
    FINANCE = "finance"             # Bankers, accountants, investors
    GOVERNMENT = "government"       # Public officials, civil servants
    JOURNALISM = "journalism"       # Journalists, media professionals
    AGRICULTURE = "agriculture"     # Farmers, agricultural professionals


class Industry(str, Enum):
    """Industries/sectors with direct implications."""
    GENERAL = "general"             # No specific industry focus
    TOURISM = "tourism"
    AGRICULTURE = "agriculture"
    TECHNOLOGY = "technology"
    FINANCE = "finance"
    HEALTHCARE = "healthcare"
    EDUCATION = "education"
    ENERGY = "energy"
    CONSTRUCTION = "construction"
    RETAIL = "retail"
    MANUFACTURING = "manufacturing"
    TELECOMMUNICATIONS = "telecommunications"
    TRANSPORTATION = "transportation"


class GeographicScope(str, Enum):
    """Geographic scope of the news."""
    LOCAL = "local"                 # City/municipality level
    NATIONAL = "national"           # Country level
    REGIONAL = "regional"           # Caribbean/Latin America
    INTERNATIONAL = "international" # Global/multiple continents


# COMMENTED OUT - Removed to reduce token consumption and processing time
# class SemanticRelation(BaseModel):
#     """A semantic relationship between concepts in the article."""
#     subject: str = Field(
#         description="Entidad o concepto que realiza la acción",
#         max_length=50
#     )
#     predicate: str = Field(
#         description="Acción que conecta subject con object. Preferiblemente un verbo en pasado, "
#                     "pero puede incluir complemento si es necesario. Máximo 4 palabras.",
#         max_length=40
#     )
#     object: str = Field(
#         description="Entidad, concepto o término que recibe la acción. "
#                     "Debe tener significado por sí solo, sin depender del contexto. Máximo 7 palabras.",
#         max_length=70
#     )


class EntityTypeEnum(str, Enum):
    """Types of named entities for recommendation systems."""
    PERSON = "PERSON"       # Nicolás Maduro, Donald Trump - Usuario sigue personas específicas
    ORG = "ORG"             # PSUV, EE.UU. (gobierno), VTV, Apple - Usuario sigue empresas/instituciones
    GPE = "GPE"             # Venezuela, Caracas, Estados Unidos - Filtrado geográfico del feed
    EVENT = "EVENT"         # Elecciones 2024, Copa Mundial, COP28 - Agrupar cobertura de un evento
    PRODUCT = "PRODUCT"     # iPhone 16, ChatGPT, Tesla Model 3 - Usuarios interesados en productos/tech
    NORP = "NORP"           # Evangélicos, republicanos, chavistas - Grupos políticos/religiosos/étnicos
    FAC = "FAC"             # Aeropuerto Las Américas, Autopista Duarte, Puente Juan Bosch - Edificios, infraestructura
    LOC = "LOC"             # Cordillera Central, Mar Caribe, Río Ozama - Ubicaciones no-GPE, accidentes geográficos


class ExtractedEntity(BaseModel):
    """A named entity extracted from the article."""
    text: str = Field(
        description="Texto exacto de la entidad tal como aparece en el artículo. "
                    "Usar la forma más completa encontrada (ej: 'Nicolás Maduro' no 'Maduro').",
        max_length=100
    )
    type: EntityTypeEnum = Field(
        description="Tipo de entidad."
    )


class SourceVoice(BaseModel):
    """A source/voice represented in the article."""
    type: str = Field(description="Tipo de fuente (ej: 'gobierno', 'experto', 'ciudadano', 'empresa', 'ONG')")
    stance: Optional[str] = Field(default=None, description="Postura de la fuente si es identificable (ej: 'a favor', 'en contra', 'neutral')")


class StructuredOutput(BaseModel):
    """
    Deep analysis of a news article for recommendation system matching.

    All fields are in Spanish to match the source content language.
    """

    # 0. Named entities extracted from the article
    entities: List[ExtractedEntity] = Field(
        description="Lista de entidades nombradas extraídas del artículo. "
                    "Incluir solo entidades relevantes y bien formadas. "
                    "Evitar entidades ambiguas o demasiado genéricas.",
        max_length=30
    )

    # 1. Key concepts extracted from the article
    key_concepts: List[str] = Field(
        description="Lista de 2-3 conceptos clave del artículo (más allá de entidades nombradas). "
                    "Incluye temas abstractos, problemáticas, fenómenos discutidos.",
        min_length=1,
        max_length=5
    )

    # 2. Semantic relationships - COMMENTED OUT to reduce token consumption
    # semantic_relations: List[SemanticRelation] = Field(
    #     description="Lista de 2-5 relaciones semánticas importantes entre entidades o conceptos.",
    #     min_length=1,
    #     max_length=7
    # )

    # 3. Narrative frames used
    narrative_frames: List[NarrativeFrame] = Field(
        description="Frames narrativos predominantes desde los cuales se cuenta la historia. "
                    "Ordenados por predominancia (máximo 3).",
        min_length=1,
        max_length=3
    )

    # 4. Editorial tone
    editorial_tone: EditorialTone = Field(
        description="Tono editorial predominante del artículo."
    )

    # 5. Writing style descriptors - COMMENTED OUT to reduce complexity
    # style_descriptors: List[str] = Field(
    #     description="2-4 adjetivos que describen el estilo narrativo.",
    #     min_length=2,
    #     max_length=4
    # )

    # 6. Controversy score (0-100)
    controversy_score: int = Field(
        description="Grado de controversia del tema (0=nada controversial, 100=altamente polarizante). "
                    "Considera si el tema divide opiniones públicas.",
        ge=0,
        le=100
    )

    # 7. Political bias indicator (-100 to 100)
    political_bias: int = Field(
        description="Sesgo político percibido (-100=extrema izquierda, 0=neutral, 100=extrema derecha). "
                    "Basado en lenguaje, fuentes citadas, y encuadre de temas.",
        ge=-100,
        le=100
    )

    # 8. Journalistic quality - COMMENTED OUT (can be inferred from other factors)
    # has_named_sources: bool = Field(...)  # COMMENTED OUT
    # has_data_or_statistics: bool = Field(...)  # COMMENTED OUT
    # has_multiple_perspectives: bool = Field(...)  # COMMENTED OUT
    # quality_score: int = Field(...)  # COMMENTED OUT

    # 9. Content format and temporal relevance
    content_format: ContentFormat = Field(
        description="Formato del contenido."
    )
    temporal_relevance: TemporalRelevance = Field(
        description="Qué tan rápido pierde relevancia el artículo."
    )

    # 10. Target audience indicators
    audience_education: AudienceEducationLevel = Field(
        description="Nivel de educación/expertise requerido para comprender el artículo."
    )
    target_age_range: AgeRange = Field(
        description="Rango de edad de la audiencia objetivo."
    )
    # target_professions: List[Profession] = Field(...)  # COMMENTED OUT to reduce complexity

    # 11. Required prior interests - COMMENTED OUT to reduce complexity
    # required_interests: List[str] = Field(...)

    # 12. Industries/sectors with implications
    relevant_industries: List[Industry] = Field(
        description="Industrias o sectores económicos con implicaciones directas.",
        max_length=3
    )

    # 13. Geographic perspective
    geographic_scope: GeographicScope = Field(
        description="Alcance geográfico de la noticia."
    )
    # cultural_context: str = Field(...)  # COMMENTED OUT - redundant with geographic_scope

    # 14. Source diversity - COMMENTED OUT to reduce complexity
    # voices_represented: List[SourceVoice] = Field(...)  # COMMENTED OUT
    # source_diversity_score: int = Field(...)  # COMMENTED OUT
