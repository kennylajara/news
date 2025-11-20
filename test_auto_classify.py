#!/usr/bin/env python3
"""
Script temporal para crear entidades de prueba para el sistema de auto-clasificación.

Este script crea entidades que cubren los 9 casos del flujo de decisiones:
- CASO A: Candidato CANONICAL (A1, A2, A3)
- CASO B: Candidato ALIAS (B1, B2.1, B2.2, B3)
- CASO C: Candidato AMBIGUOUS (C1, C2, C3)

También crea entidades para probar las cascadas.
"""

from db.database import Database
from db.models import NamedEntity, EntityClassification, EntityType
from processors.tokenization import populate_entity_tokens


def create_test_entities():
    """Crear todas las entidades de prueba."""
    db = Database()
    session = db.get_session()

    try:
        print("Creando entidades de prueba...\n")

        # ========================================
        # CASO A: Candidato CANONICAL
        # ========================================

        # A1: Evaluada CANONICAL → Candidato CANONICAL
        # Resultado: Evaluada → ALIAS of Candidato
        print("CASO A1: Evaluada CANONICAL → Candidato CANONICAL")
        a1_candidato = NamedEntity(
            name="Luis Abinader Corona",
            name_length=len("Luis Abinader Corona"),
            entity_type=EntityType.PERSON,
            detected_types=["PERSON"],
            classified_as=EntityClassification.CANONICAL,
            last_review_type='manual',
            is_approved=1,
            article_count=0
        )
        session.add(a1_candidato)
        session.flush()
        populate_entity_tokens(a1_candidato.id, a1_candidato.name, session)

        a1_evaluada = NamedEntity(
            name="Luis Abinader",
            name_length=len("Luis Abinader"),
            entity_type=EntityType.PERSON,
            detected_types=["PERSON"],
            classified_as=EntityClassification.CANONICAL,
            last_review_type='none',
            is_approved=0,
            article_count=0
        )
        session.add(a1_evaluada)
        session.flush()
        populate_entity_tokens(a1_evaluada.id, a1_evaluada.name, session)
        print(f"  ✓ Creada evaluada: {a1_evaluada.name} (id={a1_evaluada.id})")
        print(f"  ✓ Creada candidato: {a1_candidato.name} (id={a1_candidato.id})\n")

        # A2: Evaluada ALIAS → Candidato CANONICAL
        # Resultado: Evaluada → Redirigir a Candidato CANONICAL
        print("CASO A2: Evaluada ALIAS → Candidato CANONICAL")
        a2_canonical_old = NamedEntity(
            name="República Dominicana",
            name_length=len("República Dominicana"),
            entity_type=EntityType.GPE,
            detected_types=["GPE"],
            classified_as=EntityClassification.CANONICAL,
            last_review_type='manual',
            is_approved=1,
            article_count=0
        )
        session.add(a2_canonical_old)
        session.flush()
        populate_entity_tokens(a2_canonical_old.id, a2_canonical_old.name, session)

        a2_candidato = NamedEntity(
            name="República Dominicana Estado",
            name_length=len("República Dominicana Estado"),
            entity_type=EntityType.GPE,
            detected_types=["GPE"],
            classified_as=EntityClassification.CANONICAL,
            last_review_type='manual',
            is_approved=1,
            article_count=0
        )
        session.add(a2_candidato)
        session.flush()
        populate_entity_tokens(a2_candidato.id, a2_candidato.name, session)

        a2_evaluada = NamedEntity(
            name="RD",
            name_length=len("RD"),
            entity_type=EntityType.GPE,
            detected_types=["GPE"],
            classified_as=EntityClassification.ALIAS,
            last_review_type='manual',
            is_approved=1,
            article_count=0
        )
        session.add(a2_evaluada)
        session.flush()
        a2_evaluada.set_as_alias(a2_canonical_old, session)
        populate_entity_tokens(a2_evaluada.id, a2_evaluada.name, session)
        print(f"  ✓ Creada evaluada: {a2_evaluada.name} (id={a2_evaluada.id}) → ALIAS of '{a2_canonical_old.name}'")
        print(f"  ✓ Creada candidato: {a2_candidato.name} (id={a2_candidato.id})\n")

        # A3: Evaluada AMBIGUOUS → Candidato CANONICAL
        # Resultado: Evaluada → Agregar Candidato CANONICAL a lista
        print("CASO A3: Evaluada AMBIGUOUS → Candidato CANONICAL")
        a3_canonical1 = NamedEntity(
            name="Juan Carlos Pérez Martínez",
            name_length=len("Juan Carlos Pérez Martínez"),
            entity_type=EntityType.PERSON,
            detected_types=["PERSON"],
            classified_as=EntityClassification.CANONICAL,
            last_review_type='manual',
            is_approved=1,
            article_count=0
        )
        session.add(a3_canonical1)
        session.flush()
        populate_entity_tokens(a3_canonical1.id, a3_canonical1.name, session)

        a3_canonical2 = NamedEntity(
            name="Juan Carlos Pérez López",
            name_length=len("Juan Carlos Pérez López"),
            entity_type=EntityType.PERSON,
            detected_types=["PERSON"],
            classified_as=EntityClassification.CANONICAL,
            last_review_type='manual',
            is_approved=1,
            article_count=0
        )
        session.add(a3_canonical2)
        session.flush()
        populate_entity_tokens(a3_canonical2.id, a3_canonical2.name, session)

        a3_candidato = NamedEntity(
            name="Juan Carlos Pérez García",
            name_length=len("Juan Carlos Pérez García"),
            entity_type=EntityType.PERSON,
            detected_types=["PERSON"],
            classified_as=EntityClassification.CANONICAL,
            last_review_type='manual',
            is_approved=1,
            article_count=0
        )
        session.add(a3_candidato)
        session.flush()
        populate_entity_tokens(a3_candidato.id, a3_candidato.name, session)

        a3_evaluada = NamedEntity(
            name="Juan Carlos Pérez",
            name_length=len("Juan Carlos Pérez"),
            entity_type=EntityType.PERSON,
            detected_types=["PERSON"],
            classified_as=EntityClassification.AMBIGUOUS,
            last_review_type='manual',
            is_approved=0,
            article_count=0
        )
        session.add(a3_evaluada)
        session.flush()
        a3_evaluada.set_as_ambiguous([a3_canonical1, a3_canonical2], session)
        populate_entity_tokens(a3_evaluada.id, a3_evaluada.name, session)
        print(f"  ✓ Creada evaluada: {a3_evaluada.name} (id={a3_evaluada.id}) → AMBIGUOUS [{a3_canonical1.name}, {a3_canonical2.name}]")
        print(f"  ✓ Creada candidato: {a3_candidato.name} (id={a3_candidato.id})\n")

        # ========================================
        # CASO B: Candidato ALIAS
        # ========================================

        # B1: Evaluada CANONICAL → Candidato ALIAS
        # Resultado: Evaluada → ALIAS of candidato's canonical
        print("CASO B1: Evaluada CANONICAL → Candidato ALIAS")
        b1_ultimate_canonical = NamedEntity(
            name="José Miguel Fernández Rodríguez",
            name_length=len("José Miguel Fernández Rodríguez"),
            entity_type=EntityType.PERSON,
            detected_types=["PERSON"],
            classified_as=EntityClassification.CANONICAL,
            last_review_type='manual',
            is_approved=1,
            article_count=0
        )
        session.add(b1_ultimate_canonical)
        session.flush()
        populate_entity_tokens(b1_ultimate_canonical.id, b1_ultimate_canonical.name, session)

        b1_candidato = NamedEntity(
            name="J.M. Fernández Rodríguez",
            name_length=len("J.M. Fernández Rodríguez"),
            entity_type=EntityType.PERSON,
            detected_types=["PERSON"],
            classified_as=EntityClassification.ALIAS,
            last_review_type='manual',
            is_approved=1,
            article_count=0
        )
        session.add(b1_candidato)
        session.flush()
        b1_candidato.set_as_alias(b1_ultimate_canonical, session)
        populate_entity_tokens(b1_candidato.id, b1_candidato.name, session)

        b1_evaluada = NamedEntity(
            name="J.M. Fernández",
            name_length=len("J.M. Fernández"),
            entity_type=EntityType.PERSON,
            detected_types=["PERSON"],
            classified_as=EntityClassification.CANONICAL,
            last_review_type='none',
            is_approved=0,
            article_count=0
        )
        session.add(b1_evaluada)
        session.flush()
        populate_entity_tokens(b1_evaluada.id, b1_evaluada.name, session)
        print(f"  ✓ Creada evaluada: {b1_evaluada.name} (id={b1_evaluada.id})")
        print(f"  ✓ Creada candidato: {b1_candidato.name} (id={b1_candidato.id}) → ALIAS of '{b1_ultimate_canonical.name}'")
        print(f"  ✓ Creada canonical ultimate: {b1_ultimate_canonical.name} (id={b1_ultimate_canonical.id})\n")

        # B2.1: Evaluada ALIAS → Candidato ALIAS (mismo canonical)
        # Resultado: Confirmar, ambos apuntan al mismo canonical
        print("CASO B2.1: Evaluada ALIAS → Candidato ALIAS (mismo canonical)")
        b2_canonical = NamedEntity(
            name="Banco Central de la República Dominicana",
            name_length=len("Banco Central de la República Dominicana"),
            entity_type=EntityType.ORG,
            detected_types=["ORG"],
            classified_as=EntityClassification.CANONICAL,
            last_review_type='manual',
            is_approved=1,
            article_count=0
        )
        session.add(b2_canonical)
        session.flush()
        populate_entity_tokens(b2_canonical.id, b2_canonical.name, session)

        b2_candidato = NamedEntity(
            name="Banco Central RD",
            name_length=len("Banco Central RD"),
            entity_type=EntityType.ORG,
            detected_types=["ORG"],
            classified_as=EntityClassification.ALIAS,
            last_review_type='manual',
            is_approved=1,
            article_count=0
        )
        session.add(b2_candidato)
        session.flush()
        b2_candidato.set_as_alias(b2_canonical, session)
        populate_entity_tokens(b2_candidato.id, b2_candidato.name, session)

        b2_evaluada = NamedEntity(
            name="Banco Central",
            name_length=len("Banco Central"),
            entity_type=EntityType.ORG,
            detected_types=["ORG"],
            classified_as=EntityClassification.ALIAS,
            last_review_type='none',
            is_approved=0,
            article_count=0
        )
        session.add(b2_evaluada)
        session.flush()
        b2_evaluada.set_as_alias(b2_canonical, session)
        populate_entity_tokens(b2_evaluada.id, b2_evaluada.name, session)
        print(f"  ✓ Creada evaluada: {b2_evaluada.name} (id={b2_evaluada.id}) → ALIAS of '{b2_canonical.name}'")
        print(f"  ✓ Creada candidato: {b2_candidato.name} (id={b2_candidato.id}) → ALIAS of '{b2_canonical.name}'")
        print(f"  ✓ Creada canonical: {b2_canonical.name} (id={b2_canonical.id})\n")

        # B2.2: Evaluada ALIAS → Candidato ALIAS (diferente canonical)
        # Resultado: Evaluada → AMBIGUOUS con ambos canonicals
        print("CASO B2.2: Evaluada ALIAS → Candidato ALIAS (diferente canonical)")
        b2_2_canonical1 = NamedEntity(
            name="Pedro Martínez Sánchez",
            name_length=len("Pedro Martínez Sánchez"),
            entity_type=EntityType.PERSON,
            detected_types=["PERSON"],
            classified_as=EntityClassification.CANONICAL,
            last_review_type='manual',
            is_approved=1,
            article_count=0
        )
        session.add(b2_2_canonical1)
        session.flush()
        populate_entity_tokens(b2_2_canonical1.id, b2_2_canonical1.name, session)

        b2_2_canonical2 = NamedEntity(
            name="Pedro Martínez López",
            name_length=len("Pedro Martínez López"),
            entity_type=EntityType.PERSON,
            detected_types=["PERSON"],
            classified_as=EntityClassification.CANONICAL,
            last_review_type='manual',
            is_approved=1,
            article_count=0
        )
        session.add(b2_2_canonical2)
        session.flush()
        populate_entity_tokens(b2_2_canonical2.id, b2_2_canonical2.name, session)

        b2_2_candidato = NamedEntity(
            name="P. Martínez López",
            name_length=len("P. Martínez López"),
            entity_type=EntityType.PERSON,
            detected_types=["PERSON"],
            classified_as=EntityClassification.ALIAS,
            last_review_type='manual',
            is_approved=1,
            article_count=0
        )
        session.add(b2_2_candidato)
        session.flush()
        b2_2_candidato.set_as_alias(b2_2_canonical2, session)
        populate_entity_tokens(b2_2_candidato.id, b2_2_candidato.name, session)

        b2_2_evaluada = NamedEntity(
            name="P. Martínez",
            name_length=len("P. Martínez"),
            entity_type=EntityType.PERSON,
            detected_types=["PERSON"],
            classified_as=EntityClassification.ALIAS,
            last_review_type='none',
            is_approved=0,
            article_count=0
        )
        session.add(b2_2_evaluada)
        session.flush()
        b2_2_evaluada.set_as_alias(b2_2_canonical1, session)
        populate_entity_tokens(b2_2_evaluada.id, b2_2_evaluada.name, session)
        print(f"  ✓ Creada evaluada: {b2_2_evaluada.name} (id={b2_2_evaluada.id}) → ALIAS of '{b2_2_canonical1.name}'")
        print(f"  ✓ Creada candidato: {b2_2_candidato.name} (id={b2_2_candidato.id}) → ALIAS of '{b2_2_canonical2.name}'")
        print(f"  ✓ Creadas canonicals: {b2_2_canonical1.name} y {b2_2_canonical2.name}\n")

        # B3: Evaluada AMBIGUOUS → Candidato ALIAS
        # Resultado: Evaluada → Agregar canonical del candidato a lista
        print("CASO B3: Evaluada AMBIGUOUS → Candidato ALIAS")
        b3_canonical1 = NamedEntity(
            name="María García Rodríguez",
            name_length=len("María García Rodríguez"),
            entity_type=EntityType.PERSON,
            detected_types=["PERSON"],
            classified_as=EntityClassification.CANONICAL,
            last_review_type='manual',
            is_approved=1,
            article_count=0
        )
        session.add(b3_canonical1)
        session.flush()
        populate_entity_tokens(b3_canonical1.id, b3_canonical1.name, session)

        b3_canonical2 = NamedEntity(
            name="María García Pérez",
            name_length=len("María García Pérez"),
            entity_type=EntityType.PERSON,
            detected_types=["PERSON"],
            classified_as=EntityClassification.CANONICAL,
            last_review_type='manual',
            is_approved=1,
            article_count=0
        )
        session.add(b3_canonical2)
        session.flush()
        populate_entity_tokens(b3_canonical2.id, b3_canonical2.name, session)

        b3_canonical3 = NamedEntity(
            name="María García López",
            name_length=len("María García López"),
            entity_type=EntityType.PERSON,
            detected_types=["PERSON"],
            classified_as=EntityClassification.CANONICAL,
            last_review_type='manual',
            is_approved=1,
            article_count=0
        )
        session.add(b3_canonical3)
        session.flush()
        populate_entity_tokens(b3_canonical3.id, b3_canonical3.name, session)

        b3_candidato = NamedEntity(
            name="M. García Pérez",
            name_length=len("M. García Pérez"),
            entity_type=EntityType.PERSON,
            detected_types=["PERSON"],
            classified_as=EntityClassification.ALIAS,
            last_review_type='manual',
            is_approved=1,
            article_count=0
        )
        session.add(b3_candidato)
        session.flush()
        b3_candidato.set_as_alias(b3_canonical2, session)
        populate_entity_tokens(b3_candidato.id, b3_candidato.name, session)

        b3_evaluada = NamedEntity(
            name="M. García",
            name_length=len("M. García"),
            entity_type=EntityType.PERSON,
            detected_types=["PERSON"],
            classified_as=EntityClassification.AMBIGUOUS,
            last_review_type='none',
            is_approved=0,
            article_count=0
        )
        session.add(b3_evaluada)
        session.flush()
        b3_evaluada.set_as_ambiguous([b3_canonical1, b3_canonical3], session)
        populate_entity_tokens(b3_evaluada.id, b3_evaluada.name, session)
        print(f"  ✓ Creada evaluada: {b3_evaluada.name} (id={b3_evaluada.id}) → AMBIGUOUS [{b3_canonical1.name}, {b3_canonical3.name}]")
        print(f"  ✓ Creada candidato: {b3_candidato.name} (id={b3_candidato.id}) → ALIAS of '{b3_canonical2.name}'")
        print(f"  ✓ Creadas canonicals: {b3_canonical1.name}, {b3_canonical2.name} y {b3_canonical3.name}\n")

        # ========================================
        # CASO C: Candidato AMBIGUOUS
        # ========================================

        # C1: Evaluada CANONICAL → Candidato AMBIGUOUS
        # Resultado: Evaluada → AMBIGUOUS con mismos canonicals que candidato
        print("CASO C1: Evaluada CANONICAL → Candidato AMBIGUOUS")
        c1_canonical1 = NamedEntity(
            name="Ana Martínez González",
            name_length=len("Ana Martínez González"),
            entity_type=EntityType.PERSON,
            detected_types=["PERSON"],
            classified_as=EntityClassification.CANONICAL,
            last_review_type='manual',
            is_approved=1,
            article_count=0
        )
        session.add(c1_canonical1)
        session.flush()
        populate_entity_tokens(c1_canonical1.id, c1_canonical1.name, session)

        c1_canonical2 = NamedEntity(
            name="Ana Martínez Fernández",
            name_length=len("Ana Martínez Fernández"),
            entity_type=EntityType.PERSON,
            detected_types=["PERSON"],
            classified_as=EntityClassification.CANONICAL,
            last_review_type='manual',
            is_approved=1,
            article_count=0
        )
        session.add(c1_canonical2)
        session.flush()
        populate_entity_tokens(c1_canonical2.id, c1_canonical2.name, session)

        c1_candidato = NamedEntity(
            name="Ana Martínez",
            name_length=len("Ana Martínez"),
            entity_type=EntityType.PERSON,
            detected_types=["PERSON"],
            classified_as=EntityClassification.AMBIGUOUS,
            last_review_type='manual',
            is_approved=0,
            article_count=0
        )
        session.add(c1_candidato)
        session.flush()
        c1_candidato.set_as_ambiguous([c1_canonical1, c1_canonical2], session)
        populate_entity_tokens(c1_candidato.id, c1_candidato.name, session)

        c1_evaluada = NamedEntity(
            name="A. Martínez",
            name_length=len("A. Martínez"),
            entity_type=EntityType.PERSON,
            detected_types=["PERSON"],
            classified_as=EntityClassification.CANONICAL,
            last_review_type='none',
            is_approved=0,
            article_count=0
        )
        session.add(c1_evaluada)
        session.flush()
        populate_entity_tokens(c1_evaluada.id, c1_evaluada.name, session)
        print(f"  ✓ Creada evaluada: {c1_evaluada.name} (id={c1_evaluada.id})")
        print(f"  ✓ Creada candidato: {c1_candidato.name} (id={c1_candidato.id}) → AMBIGUOUS [{c1_canonical1.name}, {c1_canonical2.name}]")
        print(f"  ✓ Creadas canonicals: {c1_canonical1.name} y {c1_canonical2.name}\n")

        # C2: Evaluada ALIAS → Candidato AMBIGUOUS
        # Resultado: Evaluada → AMBIGUOUS (canonical actual + canonicals del candidato)
        print("CASO C2: Evaluada ALIAS → Candidato AMBIGUOUS")
        c2_canonical1 = NamedEntity(
            name="Carlos López Martínez",
            name_length=len("Carlos López Martínez"),
            entity_type=EntityType.PERSON,
            detected_types=["PERSON"],
            classified_as=EntityClassification.CANONICAL,
            last_review_type='manual',
            is_approved=1,
            article_count=0
        )
        session.add(c2_canonical1)
        session.flush()
        populate_entity_tokens(c2_canonical1.id, c2_canonical1.name, session)

        c2_canonical2 = NamedEntity(
            name="Carlos López García",
            name_length=len("Carlos López García"),
            entity_type=EntityType.PERSON,
            detected_types=["PERSON"],
            classified_as=EntityClassification.CANONICAL,
            last_review_type='manual',
            is_approved=1,
            article_count=0
        )
        session.add(c2_canonical2)
        session.flush()
        populate_entity_tokens(c2_canonical2.id, c2_canonical2.name, session)

        c2_canonical3 = NamedEntity(
            name="Carlos López Rodríguez",
            name_length=len("Carlos López Rodríguez"),
            entity_type=EntityType.PERSON,
            detected_types=["PERSON"],
            classified_as=EntityClassification.CANONICAL,
            last_review_type='manual',
            is_approved=1,
            article_count=0
        )
        session.add(c2_canonical3)
        session.flush()
        populate_entity_tokens(c2_canonical3.id, c2_canonical3.name, session)

        c2_candidato = NamedEntity(
            name="Carlos López",
            name_length=len("Carlos López"),
            entity_type=EntityType.PERSON,
            detected_types=["PERSON"],
            classified_as=EntityClassification.AMBIGUOUS,
            last_review_type='manual',
            is_approved=0,
            article_count=0
        )
        session.add(c2_candidato)
        session.flush()
        c2_candidato.set_as_ambiguous([c2_canonical2, c2_canonical3], session)
        populate_entity_tokens(c2_candidato.id, c2_candidato.name, session)

        c2_evaluada = NamedEntity(
            name="C. López",
            name_length=len("C. López"),
            entity_type=EntityType.PERSON,
            detected_types=["PERSON"],
            classified_as=EntityClassification.ALIAS,
            last_review_type='none',
            is_approved=0,
            article_count=0
        )
        session.add(c2_evaluada)
        session.flush()
        c2_evaluada.set_as_alias(c2_canonical1, session)
        populate_entity_tokens(c2_evaluada.id, c2_evaluada.name, session)
        print(f"  ✓ Creada evaluada: {c2_evaluada.name} (id={c2_evaluada.id}) → ALIAS of '{c2_canonical1.name}'")
        print(f"  ✓ Creada candidato: {c2_candidato.name} (id={c2_candidato.id}) → AMBIGUOUS [{c2_canonical2.name}, {c2_canonical3.name}]")
        print(f"  ✓ Creadas canonicals: {c2_canonical1.name}, {c2_canonical2.name} y {c2_canonical3.name}\n")

        # C3: Evaluada AMBIGUOUS → Candidato AMBIGUOUS
        # Resultado: Evaluada → Sumar canonicals del candidato a lista de evaluada
        print("CASO C3: Evaluada AMBIGUOUS → Candidato AMBIGUOUS")
        c3_canonical1 = NamedEntity(
            name="Roberto Sánchez Pérez",
            name_length=len("Roberto Sánchez Pérez"),
            entity_type=EntityType.PERSON,
            detected_types=["PERSON"],
            classified_as=EntityClassification.CANONICAL,
            last_review_type='manual',
            is_approved=1,
            article_count=0
        )
        session.add(c3_canonical1)
        session.flush()
        populate_entity_tokens(c3_canonical1.id, c3_canonical1.name, session)

        c3_canonical2 = NamedEntity(
            name="Roberto Sánchez García",
            name_length=len("Roberto Sánchez García"),
            entity_type=EntityType.PERSON,
            detected_types=["PERSON"],
            classified_as=EntityClassification.CANONICAL,
            last_review_type='manual',
            is_approved=1,
            article_count=0
        )
        session.add(c3_canonical2)
        session.flush()
        populate_entity_tokens(c3_canonical2.id, c3_canonical2.name, session)

        c3_canonical3 = NamedEntity(
            name="Roberto Sánchez López",
            name_length=len("Roberto Sánchez López"),
            entity_type=EntityType.PERSON,
            detected_types=["PERSON"],
            classified_as=EntityClassification.CANONICAL,
            last_review_type='manual',
            is_approved=1,
            article_count=0
        )
        session.add(c3_canonical3)
        session.flush()
        populate_entity_tokens(c3_canonical3.id, c3_canonical3.name, session)

        c3_candidato = NamedEntity(
            name="Roberto Sánchez",
            name_length=len("Roberto Sánchez"),
            entity_type=EntityType.PERSON,
            detected_types=["PERSON"],
            classified_as=EntityClassification.AMBIGUOUS,
            last_review_type='manual',
            is_approved=0,
            article_count=0
        )
        session.add(c3_candidato)
        session.flush()
        c3_candidato.set_as_ambiguous([c3_canonical2, c3_canonical3], session)
        populate_entity_tokens(c3_candidato.id, c3_candidato.name, session)

        c3_canonical4 = NamedEntity(
            name="Roberto Sánchez Martínez",
            name_length=len("Roberto Sánchez Martínez"),
            entity_type=EntityType.PERSON,
            detected_types=["PERSON"],
            classified_as=EntityClassification.CANONICAL,
            last_review_type='manual',
            is_approved=1,
            article_count=0
        )
        session.add(c3_canonical4)
        session.flush()
        populate_entity_tokens(c3_canonical4.id, c3_canonical4.name, session)

        c3_evaluada = NamedEntity(
            name="R. Sánchez",
            name_length=len("R. Sánchez"),
            entity_type=EntityType.PERSON,
            detected_types=["PERSON"],
            classified_as=EntityClassification.AMBIGUOUS,
            last_review_type='none',
            is_approved=0,
            article_count=0
        )
        session.add(c3_evaluada)
        session.flush()
        c3_evaluada.set_as_ambiguous([c3_canonical1, c3_canonical4], session)
        populate_entity_tokens(c3_evaluada.id, c3_evaluada.name, session)
        print(f"  ✓ Creada evaluada: {c3_evaluada.name} (id={c3_evaluada.id}) → AMBIGUOUS [{c3_canonical1.name}, {c3_canonical4.name}]")
        print(f"  ✓ Creada candidato: {c3_candidato.name} (id={c3_candidato.id}) → AMBIGUOUS [{c3_canonical2.name}, {c3_canonical3.name}]")
        print(f"  ✓ Creadas canonicals: {c3_canonical1.name}, {c3_canonical2.name}, {c3_canonical3.name} y {c3_canonical4.name}\n")

        # ========================================
        # Entidades para probar CASCADAS
        # ========================================
        print("ENTIDADES PARA PROBAR CASCADAS")

        # Cascade test: CANONICAL con dependientes → ALIAS
        print("\nCASCADA 1: CANONICAL → ALIAS (con dependientes)")
        cascade1_ultimate = NamedEntity(
            name="Ministerio de Hacienda de la República Dominicana",
            name_length=len("Ministerio de Hacienda de la República Dominicana"),
            entity_type=EntityType.ORG,
            detected_types=["ORG"],
            classified_as=EntityClassification.CANONICAL,
            last_review_type='manual',
            is_approved=1,
            article_count=0
        )
        session.add(cascade1_ultimate)
        session.flush()
        populate_entity_tokens(cascade1_ultimate.id, cascade1_ultimate.name, session)

        cascade1_will_become_alias = NamedEntity(
            name="Ministerio de Hacienda",
            name_length=len("Ministerio de Hacienda"),
            entity_type=EntityType.ORG,
            detected_types=["ORG"],
            classified_as=EntityClassification.CANONICAL,
            last_review_type='manual',
            is_approved=1,
            article_count=0
        )
        session.add(cascade1_will_become_alias)
        session.flush()
        populate_entity_tokens(cascade1_will_become_alias.id, cascade1_will_become_alias.name, session)

        # Dependent ALIAS
        cascade1_dependent_alias = NamedEntity(
            name="Min. Hacienda",
            name_length=len("Min. Hacienda"),
            entity_type=EntityType.ORG,
            detected_types=["ORG"],
            classified_as=EntityClassification.ALIAS,
            last_review_type='manual',
            is_approved=1,
            article_count=0
        )
        session.add(cascade1_dependent_alias)
        session.flush()
        cascade1_dependent_alias.set_as_alias(cascade1_will_become_alias, session)
        populate_entity_tokens(cascade1_dependent_alias.id, cascade1_dependent_alias.name, session)

        # Dependent AMBIGUOUS
        cascade1_other_canonical = NamedEntity(
            name="Ministerio de Hacienda y Crédito Público",
            name_length=len("Ministerio de Hacienda y Crédito Público"),
            entity_type=EntityType.ORG,
            detected_types=["ORG"],
            classified_as=EntityClassification.CANONICAL,
            last_review_type='manual',
            is_approved=1,
            article_count=0
        )
        session.add(cascade1_other_canonical)
        session.flush()
        populate_entity_tokens(cascade1_other_canonical.id, cascade1_other_canonical.name, session)

        cascade1_dependent_ambiguous = NamedEntity(
            name="MH",
            name_length=len("MH"),
            entity_type=EntityType.ORG,
            detected_types=["ORG"],
            classified_as=EntityClassification.AMBIGUOUS,
            last_review_type='manual',
            is_approved=0,
            article_count=0
        )
        session.add(cascade1_dependent_ambiguous)
        session.flush()
        cascade1_dependent_ambiguous.set_as_ambiguous([cascade1_will_become_alias, cascade1_other_canonical], session)
        populate_entity_tokens(cascade1_dependent_ambiguous.id, cascade1_dependent_ambiguous.name, session)

        print(f"  ✓ Creada canonical que se convertirá en ALIAS: {cascade1_will_become_alias.name} (id={cascade1_will_become_alias.id})")
        print(f"  ✓ Creada ultimate canonical: {cascade1_ultimate.name} (id={cascade1_ultimate.id})")
        print(f"  ✓ Creada dependent ALIAS: {cascade1_dependent_alias.name} (id={cascade1_dependent_alias.id})")
        print(f"  ✓ Creada dependent AMBIGUOUS: {cascade1_dependent_ambiguous.name} (id={cascade1_dependent_ambiguous.id})")

        # Cascade test: CANONICAL con dependientes → AMBIGUOUS
        print("\nCASCADA 2: CANONICAL → AMBIGUOUS (con dependientes)")
        cascade2_canonical1 = NamedEntity(
            name="Tribunal Superior Electoral Nacional",
            name_length=len("Tribunal Superior Electoral Nacional"),
            entity_type=EntityType.ORG,
            detected_types=["ORG"],
            classified_as=EntityClassification.CANONICAL,
            last_review_type='manual',
            is_approved=1,
            article_count=0
        )
        session.add(cascade2_canonical1)
        session.flush()
        populate_entity_tokens(cascade2_canonical1.id, cascade2_canonical1.name, session)

        cascade2_canonical2 = NamedEntity(
            name="Tribunal Superior Electoral Provincial",
            name_length=len("Tribunal Superior Electoral Provincial"),
            entity_type=EntityType.ORG,
            detected_types=["ORG"],
            classified_as=EntityClassification.CANONICAL,
            last_review_type='manual',
            is_approved=1,
            article_count=0
        )
        session.add(cascade2_canonical2)
        session.flush()
        populate_entity_tokens(cascade2_canonical2.id, cascade2_canonical2.name, session)

        cascade2_will_become_ambiguous = NamedEntity(
            name="Tribunal Superior Electoral",
            name_length=len("Tribunal Superior Electoral"),
            entity_type=EntityType.ORG,
            detected_types=["ORG"],
            classified_as=EntityClassification.CANONICAL,
            last_review_type='manual',
            is_approved=1,
            article_count=0
        )
        session.add(cascade2_will_become_ambiguous)
        session.flush()
        populate_entity_tokens(cascade2_will_become_ambiguous.id, cascade2_will_become_ambiguous.name, session)

        # Dependent ALIAS
        cascade2_dependent_alias = NamedEntity(
            name="TSE",
            name_length=len("TSE"),
            entity_type=EntityType.ORG,
            detected_types=["ORG"],
            classified_as=EntityClassification.ALIAS,
            last_review_type='manual',
            is_approved=1,
            article_count=0
        )
        session.add(cascade2_dependent_alias)
        session.flush()
        cascade2_dependent_alias.set_as_alias(cascade2_will_become_ambiguous, session)
        populate_entity_tokens(cascade2_dependent_alias.id, cascade2_dependent_alias.name, session)

        # Dependent AMBIGUOUS
        cascade2_other_canonical = NamedEntity(
            name="Tribunal Superior Electoral de Recursos",
            name_length=len("Tribunal Superior Electoral de Recursos"),
            entity_type=EntityType.ORG,
            detected_types=["ORG"],
            classified_as=EntityClassification.CANONICAL,
            last_review_type='manual',
            is_approved=1,
            article_count=0
        )
        session.add(cascade2_other_canonical)
        session.flush()
        populate_entity_tokens(cascade2_other_canonical.id, cascade2_other_canonical.name, session)

        cascade2_dependent_ambiguous = NamedEntity(
            name="T.S.E.",
            name_length=len("T.S.E."),
            entity_type=EntityType.ORG,
            detected_types=["ORG"],
            classified_as=EntityClassification.AMBIGUOUS,
            last_review_type='manual',
            is_approved=0,
            article_count=0
        )
        session.add(cascade2_dependent_ambiguous)
        session.flush()
        cascade2_dependent_ambiguous.set_as_ambiguous([cascade2_will_become_ambiguous, cascade2_other_canonical], session)
        populate_entity_tokens(cascade2_dependent_ambiguous.id, cascade2_dependent_ambiguous.name, session)

        print(f"  ✓ Creada canonical que se convertirá en AMBIGUOUS: {cascade2_will_become_ambiguous.name} (id={cascade2_will_become_ambiguous.id})")
        print(f"  ✓ Creadas canonicals de destino: {cascade2_canonical1.name} y {cascade2_canonical2.name}")
        print(f"  ✓ Creada dependent ALIAS: {cascade2_dependent_alias.name} (id={cascade2_dependent_alias.id})")
        print(f"  ✓ Creada dependent AMBIGUOUS: {cascade2_dependent_ambiguous.name} (id={cascade2_dependent_ambiguous.id})")

        session.commit()
        print("\n✅ Todas las entidades de prueba creadas exitosamente")

        # Mostrar resumen
        print("\n" + "="*80)
        print("RESUMEN DE ENTIDADES CREADAS")
        print("="*80)

        total_entities = session.query(NamedEntity).count()
        canonical_count = session.query(NamedEntity).filter_by(classified_as=EntityClassification.CANONICAL).count()
        alias_count = session.query(NamedEntity).filter_by(classified_as=EntityClassification.ALIAS).count()
        ambiguous_count = session.query(NamedEntity).filter_by(classified_as=EntityClassification.AMBIGUOUS).count()

        print(f"Total de entidades: {total_entities}")
        print(f"  CANONICAL: {canonical_count}")
        print(f"  ALIAS: {alias_count}")
        print(f"  AMBIGUOUS: {ambiguous_count}")

        # Entidades pendientes de revisión (last_review_type='none')
        pending_review = session.query(NamedEntity).filter_by(last_review_type='none').count()
        print(f"\nEntidades pendientes de revisión (last_review_type='none'): {pending_review}")

    except Exception as e:
        session.rollback()
        print(f"\n❌ Error: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    create_test_entities()
