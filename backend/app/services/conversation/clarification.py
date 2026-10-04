from __future__ import annotations

import re

from app.domain.conversation import (
    ClarificationPlan,
    HumanContext,
    IntentDetectionResult,
)


class ClarificationPlanner:
    """Ask only facts that materially change safe service guidance."""

    def build(
        self,
        *,
        message: str,
        detection: IntentDetectionResult,
        human_context: HumanContext,
    ) -> ClarificationPlan:
        normalized = message.casefold()
        missing: list[str] = []
        questions: list[str] = []
        reasons: list[str] = []
        blocks = False

        if detection.low_confidence_candidates and not detection.intents:
            labels = ", ".join(
                item.canonical_label for item in detection.low_confidence_candidates[:3]
            )
            missing.append("layanan_yang_dimaksud")
            questions.append(
                f"Layanan yang Anda maksud apakah terkait {labels}, atau layanan Dukcapil lainnya?"
            )
            reasons.append("intent_confidence_below_threshold")
            blocks = True

        if not detection.intents and detection.is_domain and not questions:
            missing.append("layanan_yang_dimaksud")
            questions.append(
                "Layanan Dukcapil apa yang ingin diurus, misalnya KTP Elektronik, "
                "Kartu Keluarga, Akta Kelahiran, atau layanan pindah domisili?"
            )
            reasons.append("service_not_identified")
            blocks = True

        intent_ids = {item.intent_id for item in detection.intents}

        if "unregistered_marriage" in human_context.tags and (
            "akta_kelahiran" in intent_ids or "pregnancy" in human_context.tags
        ):
            missing.append("status_pencatatan_perkawinan")
            questions.append(
                "Apakah perkawinan sudah memiliki dokumen pencatatan resmi, atau baru "
                "dilaksanakan secara agama/adat?"
            )
            reasons.append("birth_guidance_depends_on_marriage_record_context")

        if "different_domicile" in human_context.tags:
            if not re.search(r"\b(sementara|menetap|permanen)\b", normalized):
                missing.append("jenis_domisili")
                questions.append("Perpindahan tersebut untuk menetap atau hanya tinggal sementara?")
            if not re.search(r"\b(dari|asal|tujuan|ke)\s+[a-z]", normalized):
                missing.append("daerah_asal_dan_tujuan")
                questions.append(
                    "Apakah prosesnya pindah keluar dari daerah asal, pindah datang ke "
                    "Tomohon, atau keduanya?"
                )
            reasons.append("jurisdiction_and_transfer_direction_affect_process")

        if "lost_identity_document" in human_context.tags:
            if not re.search(r"\b(hilang|rusak|salah|koreksi|dicuri)\b", normalized):
                missing.append("kondisi_dokumen")
                questions.append("Dokumennya hilang, rusak, atau datanya perlu diperbaiki?")
                reasons.append("replacement_and_correction_have_different_workflows")

        if "akta_kematian" in intent_ids and "bereavement" in human_context.tags:
            if not re.search(
                r"\b(akta kematian|sudah dicatat|belum dicatat|surat kematian)\b",
                normalized,
            ):
                missing.append("status_pencatatan_kematian")
                questions.append(
                    "Apakah kematian sudah dilaporkan atau sudah memiliki surat keterangan "
                    "kematian dari pihak yang berwenang?"
                )
                reasons.append("death_record_status_changes_next_step")

        if "kartu_keluarga" in intent_ids and (
            "newborn_child" in human_context.tags or "minor_or_child" in human_context.tags
        ):
            if not re.search(
                r"\b(sudah|belum)\s+(masuk|tercantum|ada)\b"
                r".{0,20}\b(kk|kartu keluarga)\b",
                normalized,
            ):
                missing.append("status_anak_dalam_kk")
                questions.append("Apakah anak sudah tercantum dalam Kartu Keluarga atau belum?")
                reasons.append("family_card_state_affects_update_guidance")

        if "ktp_el" in intent_ids and re.search(
            r"\b(belum punya|belum memiliki|pertama kali)\b",
            normalized,
        ):
            if not re.search(r"\b(rekam|perekaman|biometrik)\b", normalized):
                missing.append("status_perekaman_biometrik")
                questions.append(
                    "Apakah sudah pernah melakukan perekaman biometrik KTP Elektronik?"
                )
                reasons.append("first_issuance_depends_on_recording_status")

        if "emergency_document_recovery" in human_context.tags:
            if not re.search(r"\b(ktp|kk|kartu keluarga|akta|kia|dokumen apa)\b", normalized):
                missing.append("dokumen_yang_terdampak")
                questions.append(
                    "Dokumen kependudukan apa saja yang hilang atau rusak akibat kejadian tersebut?"
                )
                reasons.append("document_recovery_depends_on_explicit_document_type")
            if "displaced_resident" in human_context.tags and not re.search(
                r"\b(posko|pengungsian|sementara tinggal|tinggal sementara|alamat sementara)\b",
                normalized,
            ):
                missing.append("status_tempat_tinggal_sementara")
                questions.append(
                    "Apakah saat ini Anda tinggal sementara di pengungsian/kerabat, "
                    "atau sudah menetap di alamat lain?"
                )
                reasons.append("displacement_may_affect_jurisdiction_and_contact_path")

        if {"hospitalized", "bedridden", "unable_to_attend_in_person"}.intersection(
            human_context.tags
        ):
            if not re.search(
                r"\b(dibantu|didampingi|pengasuh|keluarga yang mengurus)\b",
                normalized,
            ):
                missing.append("bantuan_pengurusan")
                questions.append(
                    "Apakah ada keluarga atau pendamping yang membantu menanyakan layanan ini?"
                )
                reasons.append("attendance_restriction_may_require_supported_assistance_option")

        if "guardian_context" in human_context.tags or "caregiver_context" in human_context.tags:
            if not re.search(
                r"\b(orang tua|wali|kakek|nenek|pengasuh|orang tua asuh)\b",
                normalized,
            ):
                missing.append("hubungan_dengan_anak")
                questions.append(
                    "Apa hubungan orang yang mengurus dokumen dengan anak, tanpa "
                    "menyebutkan identitas lengkap?"
                )
                reasons.append("caregiver_and_legal_guardian_must_not_be_assumed_equivalent")

        if {"safety_risk", "document_withheld", "unsafe_household"}.intersection(
            human_context.tags
        ):
            if "document_withheld" in human_context.tags and not re.search(
                r"\b(ktp|kk|kartu keluarga|akta|dokumen identitas)\b", normalized
            ):
                missing.append("dokumen_yang_tidak_dapat_diakses")
                questions.append("Dokumen kependudukan apa yang saat ini tidak dapat Anda akses?")
                reasons.append("safe_guidance_depends_on_document_type_not_traumatic_detail")

        if {"no_fixed_address", "housing_instability", "address_uncertain"}.intersection(
            human_context.tags
        ):
            if not re.search(
                r"\b(posko|shelter|kerabat|saudara|alamat sementara|tanpa alamat)\b",
                normalized,
            ):
                missing.append("status_alamat_saat_ini")
                questions.append(
                    "Apakah saat ini Anda memiliki alamat sementara yang dapat dijelaskan "
                    "secara umum, tanpa menuliskan alamat lengkap?"
                )
                reasons.append("address_status_materially_affects_domicile_guidance")

        if (
            "identity_data_mismatch" in human_context.tags
            or "biodata_conflict" in human_context.tags
        ):
            if not re.search(
                r"\b(nama|tanggal lahir|tempat lahir|status perkawinan|"
                r"jenis kelamin|nik)\b",
                normalized,
            ):
                missing.append("jenis_perbedaan_data")
                questions.append(
                    "Bagian data apa yang berbeda, misalnya nama, tanggal lahir, atau status "
                    "pencatatan, tanpa menuliskan nomor identitas?"
                )
                reasons.append("manual_verification_requires_the_type_of_data_conflict")

        if "jurisdiction_uncertain" in human_context.tags and not re.search(
            r"\b(tomohon|luar negeri|luar indonesia|luar daerah|kota|kabupaten|provinsi)\b",
            normalized,
        ):
            missing.append("cakupan_lokasi")
            questions.append(
                "Apakah lokasi Anda saat ini masih di Indonesia, di daerah lain, "
                "atau di luar negeri?"
            )
            reasons.append("jurisdiction_is_uncertain")

        # Keep the highest-value questions and never request identifiers.
        safe_questions = tuple(
            question
            for question in dict.fromkeys(questions)
            if not re.search(r"\b(nik|nomor kk|password|otp|pin|api key)\b", question, re.I)
        )[:3]
        selected_missing = tuple(dict.fromkeys(missing))[: len(safe_questions)]
        needs = bool(safe_questions)
        return ClarificationPlan(
            needs_clarification=needs,
            missing_information=selected_missing,
            questions=safe_questions,
            reason=";".join(dict.fromkeys(reasons)),
            blocks_generation=blocks,
        )
