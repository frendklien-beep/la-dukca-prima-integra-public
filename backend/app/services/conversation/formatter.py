from __future__ import annotations

from app.domain.conversation import (
    ClarificationPlan,
    HumanContext,
    ResponseSection,
    ServiceRelationshipPlan,
)


class MarkdownFormatter:
    def format(
        self,
        *,
        sections: tuple[ResponseSection, ...],
        greeting_text: str | None,
        empathy_text: str | None,
        overflow_count: int = 0,
        human_context: HumanContext | None = None,
        service_plan: ServiceRelationshipPlan | None = None,
        clarification: ClarificationPlan | None = None,
        privacy_reminder: str | None = None,
    ) -> str:
        parts: list[str] = []
        opening = " ".join(item for item in (greeting_text, empathy_text) if item)
        if opening:
            parts.append(opening)

        if human_context and (
            human_context.sensitivity == "high"
            or human_context.urgency == "high"
            or "multiple_sensitive_circumstances" in human_context.tags
        ):
            context_labels = [
                label
                for tag, label in (
                    ("fire_incident", "dampak kebakaran"),
                    ("disaster_affected", "dampak bencana"),
                    ("displaced_resident", "tempat tinggal sementara setelah kejadian"),
                    ("hospitalized", "kondisi rawat inap"),
                    ("unable_to_attend_in_person", "keterbatasan hadir langsung"),
                    ("accessibility_need", "kebutuhan aksesibilitas"),
                    ("imminent_birth", "waktu persalinan yang dekat"),
                    ("pregnancy", "kehamilan"),
                    ("bereavement", "kondisi keluarga yang sedang berduka"),
                    ("child_protection_sensitive", "kondisi anak yang memerlukan kehati-hatian"),
                    ("safety_risk", "kondisi keamanan dan privasi"),
                    ("different_domicile", "domisili yang berbeda"),
                    ("no_fixed_address", "status alamat yang belum tetap"),
                    ("lost_identity_document", "dokumen identitas yang hilang atau rusak"),
                    ("identity_data_mismatch", "perbedaan data antar dokumen"),
                    ("unregistered_marriage", "pencatatan perkawinan yang perlu diperjelas"),
                )
                if tag in human_context.tags
            ]
            if context_labels:
                parts.append("**Situasi yang saya pahami:** " + ", ".join(context_labels[:4]) + ".")

        if service_plan and service_plan.recommended_order:
            first = service_plan.recommended_order[0]
            if len(sections) > 1 or (human_context and human_context.urgency == "high"):
                parts.append(
                    f"**Prioritas awal:** periksa langkah untuk **{first}** terlebih dahulu, "
                    "tanpa mengartikan urutan ini sebagai jaminan percepatan atau persetujuan."
                )

        multi = len(sections) > 1
        for section in sections:
            heading = (
                f"## {section.sequence}. {section.heading}" if multi else f"## {section.heading}"
            )
            parts.extend((heading, section.body_markdown.strip()))

        if service_plan and service_plan.related_services:
            related = ", ".join(service_plan.related_services)
            parts.append(
                "### Layanan yang mungkin berkaitan\n"
                f"{related} dapat menjadi langkah berikutnya atau perlu diperiksa berdasarkan "
                "kondisi dokumen dan sumber yang tersedia. Ini bukan otomatis persyaratan wajib."
            )
        if service_plan and service_plan.prerequisites:
            prerequisites = ", ".join(service_plan.prerequisites)
            parts.append(
                "### Prasyarat yang didukung sumber\n"
                f"Knowledge Base yang digunakan menunjukkan keterkaitan dengan: {prerequisites}."
            )

        if clarification and clarification.questions:
            questions = "\n".join(
                f"{index}. {question}"
                for index, question in enumerate(clarification.questions, start=1)
            )
            parts.append(f"### Hal yang perlu dikonfirmasi\n{questions}")

        if (service_plan and service_plan.requires_human_verification) or (
            human_context and human_context.requires_human_verification
        ):
            parts.append(
                "**Verifikasi petugas:** beberapa bagian bergantung pada status dokumen, "
                "pencatatan, atau yurisdiksi. Petugas berwenang perlu mengonfirmasi kondisi "
                "spesifik sebelum langkah dianggap pasti."
            )

        if privacy_reminder:
            parts.append(privacy_reminder)

        if overflow_count:
            parts.append(
                f"Catatan: terdapat {overflow_count} layanan tambahan. Silakan pisahkan "
                "pertanyaan agar setiap layanan dapat dijelaskan dengan jelas."
            )
        return "\n\n".join(parts).strip()
