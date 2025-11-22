# !/usr/bin/env python3
"""
Batería de pruebas para determinar el threshold óptimo de LSH
para canonicalización y desambiguación de entidades nombradas
en periódicos dominicanos.

Autor: Claude
Caso de uso: NER en periódicos dominicanos
"""

import re
import unicodedata
from dataclasses import dataclass
from typing import List, Tuple, Dict, Set
from collections import defaultdict
import hashlib
import random


# ============================================================================
# CONFIGURACIÓN DE PRUEBAS
# ============================================================================

@dataclass
class TestCase:
    """Representa un caso de prueba para evaluación."""
    mention: str  # Mención encontrada en el texto
    canonical: str  # Forma canónica esperada
    entity_type: str  # PERSON, ORG, LOC, etc.
    difficulty: str  # easy, medium, hard
    description: str  # Descripción del caso


# ============================================================================
# DATASET DE PRUEBAS - CONTEXTO DOMINICANO
# ============================================================================

TEST_CASES: List[TestCase] = [
    # =========== PERSONAS - POLÍTICOS ===========
    # Fácil: Variaciones menores
    TestCase("Luis Abinader", "Luis Rodolfo Abinader Corona", "PERSON", "easy",
             "Nombre común del presidente"),
    TestCase("Luis R. Abinader", "Luis Rodolfo Abinader Corona", "PERSON", "easy",
             "Con inicial del segundo nombre"),
    TestCase("Abinader Corona", "Luis Rodolfo Abinader Corona", "PERSON", "easy",
             "Solo apellidos"),
    TestCase("el presidente Abinader", "Luis Rodolfo Abinader Corona", "PERSON", "medium",
             "Con título"),
    TestCase("Abinader", "Luis Rodolfo Abinader Corona", "PERSON", "medium",
             "Solo apellido paterno"),

    # Medio: Variaciones con títulos y apodos
    TestCase("Leonel Fernández", "Leonel Antonio Fernández Reyna", "PERSON", "easy",
             "Ex presidente - nombre común"),
    TestCase("Leonel", "Leonel Antonio Fernández Reyna", "PERSON", "hard",
             "Solo primer nombre (ambiguo)"),
    TestCase("el expresidente Fernández", "Leonel Antonio Fernández Reyna", "PERSON", "medium",
             "Con título de expresidente"),
    TestCase("Fernández Reyna", "Leonel Antonio Fernández Reyna", "PERSON", "easy",
             "Ambos apellidos"),

    TestCase("Danilo Medina", "Danilo Medina Sánchez", "PERSON", "easy",
             "Ex presidente"),
    TestCase("Medina Sánchez", "Danilo Medina Sánchez", "PERSON", "easy",
             "Solo apellidos"),
    TestCase("el exmandatario Medina", "Danilo Medina Sánchez", "PERSON", "medium",
             "Con título"),

    TestCase("Hipólito Mejía", "Rafael Hipólito Mejía Domínguez", "PERSON", "easy",
             "Ex presidente - nombre conocido"),
    TestCase("Hipólito", "Rafael Hipólito Mejía Domínguez", "PERSON", "hard",
             "Solo nombre (distintivo)"),

    # Difícil: Casos de desambiguación
    TestCase("el senador Fadul", "José Rafael Fadul", "PERSON", "hard",
             "Apellido común - necesita contexto"),
    TestCase("la ministra Cedeño", "Gloria Cecilia Cedeño Caminero", "PERSON", "hard",
             "Apellido común con título femenino"),

    # =========== PERSONAS - DEPORTISTAS ===========
    TestCase("David Ortiz", "David Américo Ortiz Arias", "PERSON", "easy",
             "Big Papi - nombre común"),
    TestCase("Big Papi", "David Américo Ortiz Arias", "PERSON", "medium",
             "Apodo famoso"),
    TestCase("Ortiz", "David Américo Ortiz Arias", "PERSON", "hard",
             "Apellido muy común - ambiguo"),

    TestCase("Juan Soto", "Juan José Soto Pacheco", "PERSON", "easy",
             "Beisbolista - nombre común"),
    TestCase("Soto", "Juan José Soto Pacheco", "PERSON", "hard",
             "Apellido común"),

    TestCase("Pedro Martínez", "Pedro Jaime Martínez", "PERSON", "easy",
             "Pitcher legendario"),
    TestCase("Pedro", "Pedro Jaime Martínez", "PERSON", "hard",
             "Nombre muy común"),

    TestCase("Manny Ramírez", "Manuel Arístides Ramírez Onelcida", "PERSON", "easy",
             "Beisbolista"),
    TestCase("Manny", "Manuel Arístides Ramírez Onelcida", "PERSON", "hard",
             "Apodo/diminutivo"),

    # =========== PERSONAS - ARTISTAS ===========
    TestCase("Juan Luis Guerra", "Juan Luis Guerra Seijas", "PERSON", "easy",
             "Cantante famoso"),
    TestCase("Juan Luis", "Juan Luis Guerra Seijas", "PERSON", "medium",
             "Primer nombre compuesto"),

    TestCase("El Torito", "Héctor Acosta", "PERSON", "hard",
             "Apodo artístico"),
    TestCase("Héctor Acosta El Torito", "Héctor Acosta", "PERSON", "medium",
             "Nombre con apodo"),

    TestCase("Romeo Santos", "Anthony Santos", "PERSON", "hard",
             "Nombre artístico"),

    # =========== ORGANIZACIONES - PARTIDOS POLÍTICOS ===========
    TestCase("PRM", "Partido Revolucionario Moderno", "ORG", "easy",
             "Siglas oficiales"),
    TestCase("el PRM", "Partido Revolucionario Moderno", "ORG", "easy",
             "Siglas con artículo"),
    TestCase("Partido Revolucionario Moderno", "Partido Revolucionario Moderno", "ORG", "easy",
             "Nombre completo"),
    TestCase("los perremeístas", "Partido Revolucionario Moderno", "ORG", "hard",
             "Gentilicio coloquial"),

    TestCase("PLD", "Partido de la Liberación Dominicana", "ORG", "easy",
             "Siglas oficiales"),
    TestCase("Partido de la Liberación", "Partido de la Liberación Dominicana", "ORG", "medium",
             "Nombre parcial"),
    TestCase("los peledeístas", "Partido de la Liberación Dominicana", "ORG", "hard",
             "Gentilicio coloquial"),
    TestCase("el partido morado", "Partido de la Liberación Dominicana", "ORG", "hard",
             "Referencia por color"),

    TestCase("PRD", "Partido Revolucionario Dominicano", "ORG", "easy",
             "Siglas oficiales"),
    TestCase("el PRD", "Partido Revolucionario Dominicano", "ORG", "easy",
             "Con artículo"),

    TestCase("Fuerza del Pueblo", "Fuerza del Pueblo", "ORG", "easy",
             "Nombre completo"),
    TestCase("FP", "Fuerza del Pueblo", "ORG", "easy",
             "Siglas"),

    # =========== ORGANIZACIONES - INSTITUCIONES ===========
    TestCase("la JCE", "Junta Central Electoral", "ORG", "easy",
             "Siglas con artículo"),
    TestCase("Junta Central Electoral", "Junta Central Electoral", "ORG", "easy",
             "Nombre completo"),
    TestCase("la Junta", "Junta Central Electoral", "ORG", "hard",
             "Nombre parcial ambiguo"),

    TestCase("el Banco Central", "Banco Central de la República Dominicana", "ORG", "medium",
             "Nombre parcial"),
    TestCase("BCRD", "Banco Central de la República Dominicana", "ORG", "easy",
             "Siglas"),

    TestCase("la DGII", "Dirección General de Impuestos Internos", "ORG", "easy",
             "Siglas"),
    TestCase("Impuestos Internos", "Dirección General de Impuestos Internos", "ORG", "medium",
             "Nombre parcial"),

    TestCase("UASD", "Universidad Autónoma de Santo Domingo", "ORG", "easy",
             "Siglas universidad"),
    TestCase("la Autónoma", "Universidad Autónoma de Santo Domingo", "ORG", "medium",
             "Nombre coloquial"),

    TestCase("PUCMM", "Pontificia Universidad Católica Madre y Maestra", "ORG", "easy",
             "Siglas"),
    TestCase("la Católica", "Pontificia Universidad Católica Madre y Maestra", "ORG", "hard",
             "Nombre coloquial ambiguo"),
    TestCase("la Madre y Maestra", "Pontificia Universidad Católica Madre y Maestra", "ORG", "medium",
             "Nombre parcial"),

    TestCase("INTEC", "Instituto Tecnológico de Santo Domingo", "ORG", "easy",
             "Siglas conocidas"),

    # =========== ORGANIZACIONES - EMPRESAS ===========
    TestCase("Claro", "Claro Dominicana", "ORG", "easy",
             "Nombre comercial"),
    TestCase("Claro RD", "Claro Dominicana", "ORG", "easy",
             "Con sufijo país"),

    TestCase("Altice", "Altice Dominicana", "ORG", "easy",
             "Telecomunicaciones"),
    TestCase("Orange Dominicana", "Altice Dominicana", "ORG", "hard",
             "Nombre anterior de la empresa"),

    TestCase("Grupo Ramos", "Grupo Ramos", "ORG", "easy",
             "Conglomerado comercial"),
    TestCase("La Sirena", "Grupo Ramos", "ORG", "hard",
             "Subsidiaria del grupo"),

    TestCase("Banco Popular", "Banco Popular Dominicano", "ORG", "medium",
             "Nombre parcial"),
    TestCase("el Popular", "Banco Popular Dominicano", "ORG", "medium",
             "Nombre coloquial"),
    TestCase("BPD", "Banco Popular Dominicano", "ORG", "easy",
             "Siglas"),

    TestCase("Banreservas", "Banco de Reservas de la República Dominicana", "ORG", "easy",
             "Nombre comercial"),
    TestCase("Banco de Reservas", "Banco de Reservas de la República Dominicana", "ORG", "medium",
             "Nombre parcial"),

    # =========== LUGARES - CIUDADES/PROVINCIAS ===========
    TestCase("Santo Domingo", "Santo Domingo de Guzmán", "LOC", "easy",
             "Capital - nombre común"),
    TestCase("la capital", "Santo Domingo de Guzmán", "LOC", "medium",
             "Referencia indirecta"),
    TestCase("SD", "Santo Domingo de Guzmán", "LOC", "medium",
             "Abreviatura"),
    TestCase("SDQ", "Santo Domingo de Guzmán", "LOC", "medium",
             "Código aeropuerto"),

    TestCase("Santiago", "Santiago de los Caballeros", "LOC", "easy",
             "Segunda ciudad"),
    TestCase("Santiago de los Caballeros", "Santiago de los Caballeros", "LOC", "easy",
             "Nombre completo"),
    TestCase("la ciudad corazón", "Santiago de los Caballeros", "LOC", "hard",
             "Apodo de la ciudad"),

    TestCase("Puerto Plata", "San Felipe de Puerto Plata", "LOC", "easy",
             "Nombre común"),
    TestCase("San Felipe de Puerto Plata", "San Felipe de Puerto Plata", "LOC", "easy",
             "Nombre oficial"),
    TestCase("la novia del Atlántico", "San Felipe de Puerto Plata", "LOC", "hard",
             "Apodo turístico"),

    TestCase("La Romana", "La Romana", "LOC", "easy",
             "Provincia/ciudad"),
    TestCase("Higüey", "Salvaleón de Higüey", "LOC", "easy",
             "Nombre común"),
    TestCase("Salvaleón de Higüey", "Salvaleón de Higüey", "LOC", "easy",
             "Nombre oficial"),
    TestCase("la capital del Este", "Salvaleón de Higüey", "LOC", "hard",
             "Referencia regional"),

    TestCase("San Cristóbal", "San Cristóbal", "LOC", "easy",
             "Provincia cuna de constitución"),
    TestCase("la cuna de la Constitución", "San Cristóbal", "LOC", "hard",
             "Apodo histórico"),

    TestCase("Punta Cana", "Punta Cana", "LOC", "easy",
             "Destino turístico"),
    TestCase("Bávaro", "Punta Cana", "LOC", "hard",
             "Zona dentro de Punta Cana"),

    # =========== LUGARES - BARRIOS/SECTORES ===========
    TestCase("la Zona Colonial", "Ciudad Colonial de Santo Domingo", "LOC", "medium",
             "Nombre común"),
    TestCase("Ciudad Colonial", "Ciudad Colonial de Santo Domingo", "LOC", "easy",
             "Nombre turístico"),

    TestCase("Gazcue", "Gazcue", "LOC", "easy",
             "Sector de Santo Domingo"),
    TestCase("Gascue", "Gazcue", "LOC", "easy",
             "Variante ortográfica"),

    TestCase("Los Alcarrizos", "Los Alcarrizos", "LOC", "easy",
             "Municipio"),
    TestCase("Alcarrizos", "Los Alcarrizos", "LOC", "easy",
             "Sin artículo"),

    TestCase("Villa Mella", "Santo Domingo Norte", "LOC", "hard",
             "Nombre histórico del municipio"),
    TestCase("Santo Domingo Norte", "Santo Domingo Norte", "LOC", "easy",
             "Nombre oficial"),

    # =========== CASOS DE NORMALIZACIÓN ORTOGRÁFICA ===========
    TestCase("LUIS ABINADER", "Luis Rodolfo Abinader Corona", "PERSON", "easy",
             "Todo mayúsculas"),
    TestCase("luis abinader", "Luis Rodolfo Abinader Corona", "PERSON", "easy",
             "Todo minúsculas"),
    TestCase("SANTO DOMINGO", "Santo Domingo de Guzmán", "LOC", "easy",
             "Ciudad en mayúsculas"),
    TestCase("Higuey", "Salvaleón de Higüey", "LOC", "easy",
             "Sin diéresis"),
    TestCase("Samana", "Samaná", "LOC", "easy",
             "Sin tilde"),
    TestCase("Barahona", "Barahona", "LOC", "easy",
             "Sin cambios necesarios"),

    # =========== CASOS DE DESAMBIGUACIÓN POR CONTEXTO ===========
    TestCase("el ministro Rodríguez", "AMBIGUOUS_RODRIGUEZ", "PERSON", "hard",
             "Apellido muy común - requiere contexto"),
    TestCase("la diputada Pérez", "AMBIGUOUS_PEREZ", "PERSON", "hard",
             "Apellido muy común - requiere contexto"),
    TestCase("el alcalde García", "AMBIGUOUS_GARCIA", "PERSON", "hard",
             "Apellido muy común - requiere contexto"),

    # =========== ENTIDADES NEGATIVAS (NO DEBEN COINCIDIR) ===========
    # Estos casos son para verificar que el sistema no hace matching incorrecto
]

# Casos que NO deben coincidir (para medir falsos positivos)
NEGATIVE_CASES: List[Tuple[str, str, str]] = [
    # (mención1, mención2, razón por la que NO deben coincidir)
    ("Luis Abinader", "Leonel Fernández", "Diferentes presidentes"),
    ("PRM", "PLD", "Partidos opuestos"),
    ("Santo Domingo", "Santiago", "Ciudades diferentes"),
    ("Banco Popular", "Banreservas", "Bancos diferentes"),
    ("Juan Soto", "Juan Luis Guerra", "Personas diferentes con mismo nombre"),
    ("Pedro Martínez", "Danilo Medina", "Personas completamente diferentes"),
    ("UASD", "PUCMM", "Universidades diferentes"),
    ("Claro", "Altice", "Competidores telecomunicaciones"),
    ("el presidente", "el expresidente", "Títulos que implican personas diferentes"),
    ("Puerto Plata", "Punta Cana", "Destinos turísticos diferentes"),
]


# ============================================================================
# IMPLEMENTACIÓN DE LSH
# ============================================================================

def normalize_text(text: str) -> str:
    """Normaliza texto para comparación."""
    # Convertir a minúsculas
    text = text.lower()
    # Remover acentos
    text = unicodedata.normalize('NFD', text)
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    # Remover artículos y preposiciones comunes
    stopwords = {'el', 'la', 'los', 'las', 'de', 'del', 'y', 'e', 'en', 'con', 'por', 'para'}
    words = text.split()
    words = [w for w in words if w not in stopwords]
    # Remover puntuación
    text = ' '.join(words)
    text = re.sub(r'[^\w\s]', '', text)
    return text.strip()


def get_ngrams(text: str, n: int = 3) -> Set[str]:
    """Genera n-gramas de caracteres."""
    text = normalize_text(text)
    # Agregar padding para capturar inicio y fin
    text = f"$${text}$$"
    ngrams = set()
    for i in range(len(text) - n + 1):
        ngrams.add(text[i:i + n])
    return ngrams


def get_word_ngrams(text: str, n: int = 2) -> Set[str]:
    """Genera n-gramas de palabras."""
    text = normalize_text(text)
    words = text.split()
    if len(words) < n:
        return {text}
    ngrams = set()
    for i in range(len(words) - n + 1):
        ngrams.add(' '.join(words[i:i + n]))
    # También agregar palabras individuales
    ngrams.update(words)
    return ngrams


def jaccard_similarity(set1: Set[str], set2: Set[str]) -> float:
    """Calcula similitud de Jaccard entre dos conjuntos."""
    if not set1 or not set2:
        return 0.0
    intersection = len(set1 & set2)
    union = len(set1 | set2)
    return intersection / union if union > 0 else 0.0


def minhash_signature(ngrams: Set[str], num_hashes: int = 100) -> List[int]:
    """Genera firma MinHash para un conjunto de n-gramas."""
    signature = []
    for i in range(num_hashes):
        min_hash = float('inf')
        for ngram in ngrams:
            # Crear hash único para cada función hash
            h = int(hashlib.md5(f"{i}:{ngram}".encode()).hexdigest(), 16)
            min_hash = min(min_hash, h)
        signature.append(min_hash if min_hash != float('inf') else 0)
    return signature


def lsh_similarity(sig1: List[int], sig2: List[int], bands: int, rows: int) -> float:
    """
    Estima similitud usando LSH con bandas.
    Retorna 1 si hay match en alguna banda, 0 si no.
    """
    assert len(sig1) == len(sig2) == bands * rows

    for b in range(bands):
        start = b * rows
        end = start + rows
        if sig1[start:end] == sig2[start:end]:
            return 1.0
    return 0.0


def estimated_similarity(sig1: List[int], sig2: List[int]) -> float:
    """Estima similitud Jaccard desde firmas MinHash."""
    if len(sig1) != len(sig2):
        return 0.0
    matches = sum(1 for a, b in zip(sig1, sig2) if a == b)
    return matches / len(sig1)


class LSHIndex:
    """Índice LSH para búsqueda de entidades similares."""

    def __init__(self, num_hashes: int = 100, bands: int = 20,
                 char_ngram: int = 3, word_ngram: int = 2,
                 use_word_ngrams: bool = True):
        self.num_hashes = num_hashes
        self.bands = bands
        self.rows = num_hashes // bands
        self.char_ngram = char_ngram
        self.word_ngram = word_ngram
        self.use_word_ngrams = use_word_ngrams

        # Almacenamiento
        self.entities: Dict[str, str] = {}  # id -> canonical form
        self.signatures: Dict[str, List[int]] = {}  # id -> minhash signature
        self.ngrams_cache: Dict[str, Set[str]] = {}  # id -> ngrams
        self.buckets: Dict[int, Dict[int, Set[str]]] = defaultdict(lambda: defaultdict(set))

    def _get_ngrams(self, text: str) -> Set[str]:
        """Obtiene n-gramas combinados."""
        char_ng = get_ngrams(text, self.char_ngram)
        if self.use_word_ngrams:
            word_ng = get_word_ngrams(text, self.word_ngram)
            return char_ng | word_ng
        return char_ng

    def add_entity(self, entity_id: str, text: str):
        """Agrega una entidad al índice."""
        self.entities[entity_id] = text
        ngrams = self._get_ngrams(text)
        self.ngrams_cache[entity_id] = ngrams
        signature = minhash_signature(ngrams, self.num_hashes)
        self.signatures[entity_id] = signature

        # Agregar a buckets LSH
        for b in range(self.bands):
            start = b * self.rows
            end = start + self.rows
            band_hash = hash(tuple(signature[start:end]))
            self.buckets[b][band_hash].add(entity_id)

    def query(self, text: str, threshold: float = 0.5) -> List[Tuple[str, str, float]]:
        """
        Busca entidades similares.
        Retorna lista de (entity_id, canonical_form, similarity_score).
        """
        ngrams = self._get_ngrams(text)
        signature = minhash_signature(ngrams, self.num_hashes)

        # Encontrar candidatos en buckets
        candidates = set()
        for b in range(self.bands):
            start = b * self.rows
            end = start + self.rows
            band_hash = hash(tuple(signature[start:end]))
            candidates.update(self.buckets[b].get(band_hash, set()))

        # Calcular similitud real para candidatos
        results = []
        for cand_id in candidates:
            # Usar similitud Jaccard real, no estimada
            sim = jaccard_similarity(ngrams, self.ngrams_cache[cand_id])
            if sim >= threshold:
                results.append((cand_id, self.entities[cand_id], sim))

        # Ordenar por similitud descendente
        results.sort(key=lambda x: x[2], reverse=True)
        return results

    def query_estimated(self, text: str, threshold: float = 0.5) -> List[Tuple[str, str, float]]:
        """
        Busca usando similitud estimada (más rápido pero menos preciso).
        """
        ngrams = self._get_ngrams(text)
        signature = minhash_signature(ngrams, self.num_hashes)

        candidates = set()
        for b in range(self.bands):
            start = b * self.rows
            end = start + self.rows
            band_hash = hash(tuple(signature[start:end]))
            candidates.update(self.buckets[b].get(band_hash, set()))

        results = []
        for cand_id in candidates:
            sim = estimated_similarity(signature, self.signatures[cand_id])
            if sim >= threshold:
                results.append((cand_id, self.entities[cand_id], sim))

        results.sort(key=lambda x: x[2], reverse=True)
        return results


# ============================================================================
# EVALUACIÓN Y MÉTRICAS
# ============================================================================

@dataclass
class EvaluationResult:
    """Resultados de evaluación para un threshold."""
    threshold: float
    true_positives: int
    false_positives: int
    false_negatives: int
    true_negatives: int
    precision: float
    recall: float
    f1_score: float
    accuracy: float

    # Desglose por dificultad
    recall_easy: float
    recall_medium: float
    recall_hard: float

    # Desglose por tipo de entidad
    recall_person: float
    recall_org: float
    recall_loc: float


def evaluate_threshold(index: LSHIndex, test_cases: List[TestCase],
                       negative_cases: List[Tuple[str, str, str]],
                       threshold: float) -> EvaluationResult:
    """Evalúa el rendimiento para un threshold específico."""

    tp = fp = fn = tn = 0

    # Contadores por categoría
    results_by_difficulty = {'easy': {'correct': 0, 'total': 0},
                             'medium': {'correct': 0, 'total': 0},
                             'hard': {'correct': 0, 'total': 0}}

    results_by_type = {'PERSON': {'correct': 0, 'total': 0},
                       'ORG': {'correct': 0, 'total': 0},
                       'LOC': {'correct': 0, 'total': 0}}

    # Evaluar casos positivos
    for tc in test_cases:
        if tc.canonical.startswith("AMBIGUOUS"):
            continue  # Saltar casos ambiguos para esta evaluación

        results = index.query(tc.mention, threshold)

        results_by_difficulty[tc.difficulty]['total'] += 1
        if tc.entity_type in results_by_type:
            results_by_type[tc.entity_type]['total'] += 1

        # Verificar si encontró la forma canónica correcta
        found_correct = False
        for entity_id, canonical, sim in results:
            if canonical == tc.canonical:
                found_correct = True
                break

        if found_correct:
            tp += 1
            results_by_difficulty[tc.difficulty]['correct'] += 1
            if tc.entity_type in results_by_type:
                results_by_type[tc.entity_type]['correct'] += 1
        else:
            fn += 1
            # Si devolvió resultados incorrectos, también cuenta como FP
            if results:
                fp += len(results)

    # Evaluar casos negativos
    for mention1, mention2, reason in negative_cases:
        # Estos pares NO deben ser marcados como similares
        ngrams1 = index._get_ngrams(mention1)
        ngrams2 = index._get_ngrams(mention2)
        sim = jaccard_similarity(ngrams1, ngrams2)

        if sim >= threshold:
            fp += 1  # Falso positivo: los marcó como similares cuando no lo son
        else:
            tn += 1  # Verdadero negativo: correctamente los identificó como diferentes

    # Calcular métricas
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    accuracy = (tp + tn) / (tp + tn + fp + fn) if (tp + tn + fp + fn) > 0 else 0.0

    # Recall por dificultad
    def calc_recall(stats):
        return stats['correct'] / stats['total'] if stats['total'] > 0 else 0.0

    return EvaluationResult(
        threshold=threshold,
        true_positives=tp,
        false_positives=fp,
        false_negatives=fn,
        true_negatives=tn,
        precision=precision,
        recall=recall,
        f1_score=f1,
        accuracy=accuracy,
        recall_easy=calc_recall(results_by_difficulty['easy']),
        recall_medium=calc_recall(results_by_difficulty['medium']),
        recall_hard=calc_recall(results_by_difficulty['hard']),
        recall_person=calc_recall(results_by_type['PERSON']),
        recall_org=calc_recall(results_by_type['ORG']),
        recall_loc=calc_recall(results_by_type['LOC'])
    )


def run_benchmark(thresholds: List[float] = None,
                  num_hashes: int = 100,
                  bands: int = 20,
                  char_ngram: int = 3,
                  word_ngram: int = 2,
                  use_word_ngrams: bool = True,
                  verbose: bool = True) -> List[EvaluationResult]:
    """
    Ejecuta la batería de pruebas completa.
    """
    if thresholds is None:
        thresholds = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]

    # Crear índice
    index = LSHIndex(
        num_hashes=num_hashes,
        bands=bands,
        char_ngram=char_ngram,
        word_ngram=word_ngram,
        use_word_ngrams=use_word_ngrams
    )

    # Indexar formas canónicas únicas
    canonical_forms = set()
    for tc in TEST_CASES:
        if not tc.canonical.startswith("AMBIGUOUS"):
            canonical_forms.add(tc.canonical)

    if verbose:
        print(f"Indexando {len(canonical_forms)} formas canónicas...")

    for i, canonical in enumerate(canonical_forms):
        index.add_entity(f"entity_{i}", canonical)

    # Evaluar cada threshold
    results = []
    for thresh in thresholds:
        if verbose:
            print(f"Evaluando threshold {thresh}...")
        result = evaluate_threshold(index, TEST_CASES, NEGATIVE_CASES, thresh)
        results.append(result)

    return results


def print_results(results: List[EvaluationResult]):
    """Imprime resultados formateados."""

    print("\n" + "=" * 100)
    print("RESULTADOS DE LA BATERÍA DE PRUEBAS - LSH PARA ENTIDADES DOMINICANAS")
    print("=" * 100)

    # Tabla principal
    print("\n📊 MÉTRICAS PRINCIPALES POR THRESHOLD")
    print("-" * 90)
    print(
        f"{'Threshold':^10} | {'Precision':^10} | {'Recall':^10} | {'F1 Score':^10} | {'Accuracy':^10} | {'TP':^6} | {'FP':^6} | {'FN':^6}")
    print("-" * 90)

    best_f1 = max(results, key=lambda x: x.f1_score)

    for r in results:
        marker = " ⭐" if r.threshold == best_f1.threshold else ""
        print(
            f"{r.threshold:^10.2f} | {r.precision:^10.3f} | {r.recall:^10.3f} | {r.f1_score:^10.3f} | {r.accuracy:^10.3f} | {r.true_positives:^6} | {r.false_positives:^6} | {r.false_negatives:^6}{marker}")

    print("-" * 90)
    print(f"⭐ Mejor F1 Score: {best_f1.f1_score:.3f} con threshold {best_f1.threshold}")

    # Desglose por dificultad
    print("\n📈 RECALL POR NIVEL DE DIFICULTAD")
    print("-" * 70)
    print(f"{'Threshold':^10} | {'Fácil':^15} | {'Medio':^15} | {'Difícil':^15}")
    print("-" * 70)

    for r in results:
        print(f"{r.threshold:^10.2f} | {r.recall_easy:^15.3f} | {r.recall_medium:^15.3f} | {r.recall_hard:^15.3f}")

    # Desglose por tipo de entidad
    print("\n🏷️  RECALL POR TIPO DE ENTIDAD")
    print("-" * 70)
    print(f"{'Threshold':^10} | {'PERSON':^15} | {'ORG':^15} | {'LOC':^15}")
    print("-" * 70)

    for r in results:
        print(f"{r.threshold:^10.2f} | {r.recall_person:^15.3f} | {r.recall_org:^15.3f} | {r.recall_loc:^15.3f}")

    # Recomendaciones
    print("\n" + "=" * 100)
    print("💡 RECOMENDACIONES")
    print("=" * 100)

    # Encontrar threshold óptimo para diferentes escenarios
    best_precision = max(results, key=lambda x: x.precision if x.recall > 0.3 else 0)
    best_recall = max(results, key=lambda x: x.recall if x.precision > 0.3 else 0)
    best_balanced = max(results, key=lambda x: x.f1_score)

    print(f"""
    Basado en los resultados de la evaluación:

    1. 🎯 MÁXIMA PRECISIÓN (minimizar falsos positivos):
       Threshold recomendado: {best_precision.threshold}
       Precision: {best_precision.precision:.3f}, Recall: {best_precision.recall:.3f}
       Útil cuando: Es crítico evitar fusionar entidades diferentes

    2. 🔍 MÁXIMO RECALL (capturar todas las variantes):
       Threshold recomendado: {best_recall.threshold}
       Precision: {best_recall.precision:.3f}, Recall: {best_recall.recall:.3f}
       Útil cuando: Es más importante encontrar todas las menciones

    3. ⚖️  MEJOR BALANCE (F1 óptimo):
       Threshold recomendado: {best_balanced.threshold}
       Precision: {best_balanced.precision:.3f}, Recall: {best_balanced.recall:.3f}, F1: {best_balanced.f1_score:.3f}
       Útil para: Uso general en producción

    📝 NOTAS ADICIONALES:

    - Para periódicos dominicanos, considerar que:
      * Los nombres de políticos tienen muchas variantes (títulos, apodos)
      * Las siglas de partidos (PRM, PLD, PRD) son muy distintivas
      * Los lugares tienen tanto nombres oficiales como coloquiales

    - Si el recall en casos "difíciles" es bajo, considerar:
      * Agregar reglas específicas para apodos conocidos
      * Crear un diccionario de alias para entidades frecuentes
      * Usar un modelo híbrido: LSH para candidatos + clasificador para decisión final
    """)


def analyze_errors(index: LSHIndex, test_cases: List[TestCase], threshold: float):
    """Analiza errores específicos para un threshold."""

    print(f"\n🔬 ANÁLISIS DE ERRORES (threshold={threshold})")
    print("=" * 80)

    false_negatives = []
    false_positives = []

    for tc in test_cases:
        if tc.canonical.startswith("AMBIGUOUS"):
            continue

        results = index.query(tc.mention, threshold)
        found_correct = any(canonical == tc.canonical for _, canonical, _ in results)

        if not found_correct:
            false_negatives.append(tc)
        elif len(results) > 1:
            # Encontró el correcto pero también otros
            wrong_matches = [(c, s) for _, c, s in results if c != tc.canonical]
            if wrong_matches:
                false_positives.append((tc, wrong_matches))

    if false_negatives:
        print(f"\n❌ FALSOS NEGATIVOS ({len(false_negatives)} casos):")
        print("-" * 80)
        for tc in false_negatives[:10]:  # Mostrar primeros 10
            print(f"  Mención: '{tc.mention}'")
            print(f"  Esperado: '{tc.canonical}'")
            print(f"  Tipo: {tc.entity_type}, Dificultad: {tc.difficulty}")
            print(f"  Descripción: {tc.description}")
            # Mostrar qué sí encontró
            results = index.query(tc.mention, threshold)
            if results:
                print(f"  Encontró: {[f'{c} ({s:.2f})' for _, c, s in results[:3]]}")
            else:
                print(f"  Encontró: (nada)")
            print()

    if false_positives:
        print(f"\n⚠️  MATCHES INCORRECTOS ADICIONALES ({len(false_positives)} casos):")
        print("-" * 80)
        for tc, wrong in false_positives[:5]:
            print(f"  Mención: '{tc.mention}'")
            print(f"  Correcto: '{tc.canonical}'")
            print(f"  También matcheó: {wrong[:3]}")
            print()

    return false_negatives, false_positives


# ============================================================================
# PRUEBAS DE PARÁMETROS LSH
# ============================================================================

def grid_search_lsh_params(verbose: bool = True):
    """
    Búsqueda de grilla para encontrar mejores parámetros LSH.
    """
    print("\n🔎 BÚSQUEDA DE PARÁMETROS ÓPTIMOS LSH")
    print("=" * 80)

    param_grid = {
        'num_hashes': [50, 100, 200],
        'bands': [10, 20, 25],
        'char_ngram': [2, 3, 4],
        'use_word_ngrams': [True, False]
    }

    best_config = None
    best_f1 = 0
    all_results = []

    # Generar combinaciones
    from itertools import product
    configs = list(product(
        param_grid['num_hashes'],
        param_grid['bands'],
        param_grid['char_ngram'],
        param_grid['use_word_ngrams']
    ))

    print(f"Probando {len(configs)} configuraciones...\n")

    for i, (num_hashes, bands, char_ngram, use_word) in enumerate(configs):
        # Verificar que bands divida a num_hashes
        if num_hashes % bands != 0:
            continue

        if verbose:
            print(f"[{i + 1}/{len(configs)}] hashes={num_hashes}, bands={bands}, "
                  f"char_ng={char_ngram}, word_ng={use_word}")

        results = run_benchmark(
            thresholds=[0.3, 0.4, 0.5, 0.6],
            num_hashes=num_hashes,
            bands=bands,
            char_ngram=char_ngram,
            use_word_ngrams=use_word,
            verbose=False
        )

        best_for_config = max(results, key=lambda x: x.f1_score)

        config_result = {
            'num_hashes': num_hashes,
            'bands': bands,
            'char_ngram': char_ngram,
            'use_word_ngrams': use_word,
            'best_threshold': best_for_config.threshold,
            'best_f1': best_for_config.f1_score,
            'precision': best_for_config.precision,
            'recall': best_for_config.recall
        }
        all_results.append(config_result)

        if best_for_config.f1_score > best_f1:
            best_f1 = best_for_config.f1_score
            best_config = config_result
            if verbose:
                print(f"  ⭐ Nuevo mejor F1: {best_f1:.3f}")

    # Mostrar mejores configuraciones
    print("\n📊 TOP 5 CONFIGURACIONES:")
    print("-" * 80)
    all_results.sort(key=lambda x: x['best_f1'], reverse=True)

    for i, cfg in enumerate(all_results[:5]):
        print(f"\n{i + 1}. F1={cfg['best_f1']:.3f} (P={cfg['precision']:.3f}, R={cfg['recall']:.3f})")
        print(f"   num_hashes={cfg['num_hashes']}, bands={cfg['bands']}, "
              f"char_ngram={cfg['char_ngram']}, word_ngrams={cfg['use_word_ngrams']}")
        print(f"   Threshold óptimo: {cfg['best_threshold']}")

    return best_config, all_results


# ============================================================================
# MAIN
# ============================================================================

def main():
    """Función principal."""
    print("""
    ╔═══════════════════════════════════════════════════════════════════════════╗
    ║     BENCHMARK LSH - CANONICALIZACIÓN DE ENTIDADES DOMINICANAS            ║
    ╠═══════════════════════════════════════════════════════════════════════════╣
    ║  Este benchmark evalúa diferentes thresholds de LSH para determinar      ║
    ║  el valor óptimo en la tarea de canonicalización y desambiguación        ║
    ║  de entidades nombradas en periódicos dominicanos.                       ║
    ╚═══════════════════════════════════════════════════════════════════════════╝
    """)

    print(f"📚 Dataset: {len(TEST_CASES)} casos de prueba positivos")
    print(f"📚 Casos negativos: {len(NEGATIVE_CASES)} pares que no deben coincidir")

    # Desglose del dataset
    by_type = defaultdict(int)
    by_diff = defaultdict(int)
    for tc in TEST_CASES:
        by_type[tc.entity_type] += 1
        by_diff[tc.difficulty] += 1

    print(f"\n📊 Distribución por tipo: {dict(by_type)}")
    print(f"📊 Distribución por dificultad: {dict(by_diff)}")

    # Ejecutar benchmark principal
    print("\n" + "=" * 80)
    print("EJECUTANDO BENCHMARK PRINCIPAL...")
    print("=" * 80)

    results = run_benchmark(
        thresholds=[0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8],
        num_hashes=100,
        bands=20,
        char_ngram=3,
        word_ngram=2,
        use_word_ngrams=True
    )

    print_results(results)

    # Análisis de errores para el mejor threshold
    best_result = max(results, key=lambda x: x.f1_score)

    # Recrear índice para análisis
    index = LSHIndex(num_hashes=100, bands=20, char_ngram=3, word_ngram=2, use_word_ngrams=True)
    canonical_forms = set(tc.canonical for tc in TEST_CASES if not tc.canonical.startswith("AMBIGUOUS"))
    for i, canonical in enumerate(canonical_forms):
        index.add_entity(f"entity_{i}", canonical)

    analyze_errors(index, TEST_CASES, best_result.threshold)

    # Búsqueda de parámetros óptimos
    print("\n" + "=" * 80)
    print("BÚSQUEDA DE PARÁMETROS ÓPTIMOS (puede tomar unos minutos)...")
    print("=" * 80)

    best_config, all_configs = grid_search_lsh_params(verbose=True)

    # Resumen final
    print("\n" + "=" * 100)
    print("🎯 RESUMEN FINAL Y RECOMENDACIÓN")
    print("=" * 100)
    print(f"""
    Para tu caso de uso de canonicalización de entidades en periódicos dominicanos,
    la configuración recomendada es:

    ┌─────────────────────────────────────────────────────────────────┐
    │  THRESHOLD RECOMENDADO: {best_result.threshold:.2f}                                   │
    │                                                                 │
    │  Parámetros LSH:                                               │
    │    - num_hashes: {best_config['num_hashes']}                                           │
    │    - bands: {best_config['bands']}                                               │
    │    - char_ngram: {best_config['char_ngram']}                                            │
    │    - use_word_ngrams: {best_config['use_word_ngrams']}                                     │
    │                                                                 │
    │  Métricas esperadas:                                           │
    │    - Precision: {best_config['precision']:.3f}                                        │
    │    - Recall: {best_config['recall']:.3f}                                           │
    │    - F1 Score: {best_config['best_f1']:.3f}                                         │
    └─────────────────────────────────────────────────────────────────┘

    CONSIDERACIONES ADICIONALES:

    1. Este threshold es un punto de partida. Ajústalo según:
       - Si tienes muchos falsos positivos → sube el threshold
       - Si pierdes muchas menciones válidas → baja el threshold

    2. Para mejorar resultados en casos difíciles, considera:
       - Crear un diccionario de alias para entidades frecuentes
       - Usar reglas específicas para partidos políticos (PRM, PLD, etc.)
       - Entrenar un clasificador secundario para casos ambiguos

    3. Monitorea el rendimiento en producción y ajusta según sea necesario.
    """)


if __name__ == "__main__":
    main()
