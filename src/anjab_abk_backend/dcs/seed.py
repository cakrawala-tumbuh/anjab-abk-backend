"""Data master DCS: 3 sub-skala × 14 item = 42 item.

Sumber: 07_DCS_Screening — Paket Instrumen Kajian Anjab_ABK (CF-3.0 Bagian VIII).
Berdasarkan model Karasek (1979) & Johnson & Hall (1988).
Data ini statis dan di-seed sekali saat startup; tidak diubah lewat API.
"""

from __future__ import annotations

# (kode, nama, urutan)
SUB_SKALA: list[tuple[str, str, int]] = [
    ("DEMAND", "Demand (Tuntutan Kerja)", 1),
    ("CONTROL", "Control (Kendali Kerja)", 2),
    ("SUPPORT", "Support (Dukungan Kerja)", 3),
]

# (item_id, subskala_kode, sub_dimensi, pernyataan, arah, urutan)
# arah: "F" (Favorable, skor langsung) | "UF" (Unfavorable, reverse: 6 - raw)
ITEM: list[tuple[str, str, str, str, str, int]] = [
    # --- DEMAND ---
    (
        "D1a",
        "DEMAND",
        "Volume",
        "Saya harus menyelesaikan banyak tugas dalam waktu yang sangat terbatas.",
        "UF",
        1,
    ),
    (
        "D1b",
        "DEMAND",
        "Volume",
        "Jumlah tugas yang saya tangani masih dalam batas yang bisa saya kelola dengan baik.",
        "F",
        2,
    ),
    (
        "D2a",
        "DEMAND",
        "Speed",
        "Pekerjaan saya menuntut saya bekerja sangat cepat.",
        "UF",
        3,
    ),
    (
        "D2b",
        "DEMAND",
        "Speed",
        "Saya memiliki cukup waktu untuk menyelesaikan setiap tugas dengan kualitas yang baik.",
        "F",
        4,
    ),
    (
        "D3a",
        "DEMAND",
        "Unpredictability",
        "Saya sering mendapat tugas mendadak di luar rencana yang sudah dibuat.",
        "UF",
        5,
    ),
    (
        "D3b",
        "DEMAND",
        "Unpredictability",
        "Prioritas kerja saya sering berubah sehingga sulit merencanakan kegiatan"
        " secara konsisten.",
        "UF",
        6,
    ),
    (
        "D4",
        "DEMAND",
        "Peak",
        "Pada periode tertentu dalam setahun akademik (misal: pembagian rapor, PPDB, pementasan"
        " akhir tahun, atau akreditasi), jam kerja saya melonjak sangat drastis"
        " di luar jam normal.",
        "UF",
        7,
    ),
    (
        "D5a",
        "DEMAND",
        "Admin burden",
        "Tugas di luar kegiatan inti jabatan saya (misalnya: administrasi, dokumentasi, atau"
        " pelaporan) menyerap waktu yang seharusnya untuk tugas utama saya.",
        "UF",
        8,
    ),
    (
        "D5b",
        "DEMAND",
        "Admin burden",
        "Waktu yang saya habiskan untuk administrasi dan pelaporan terasa tidak proporsional"
        " dibandingkan tugas inti saya.",
        "UF",
        9,
    ),
    (
        "D6a",
        "DEMAND",
        "Role overload",
        "Saya mengerjakan tugas yang bukan tanggung jawab utama jabatan saya.",
        "UF",
        10,
    ),
    (
        "D6b",
        "DEMAND",
        "Role overload",
        "Saya sering diminta menggantikan peran rekan yang berhalangan di luar"
        " deskripsi tugas saya.",
        "UF",
        11,
    ),
    (
        "D7a",
        "DEMAND",
        "Emotional",
        "Tuntutan emosional pekerjaan saya (misalnya: menangani murid yang memerlukan perhatian"
        " khusus, komunikasi dengan orang tua yang menantang, atau situasi konflik) cukup berat.",
        "UF",
        12,
    ),
    (
        "D7b",
        "DEMAND",
        "Emotional",
        "Saya merasa terkuras secara emosional di akhir hari kerja karena tuntutan interaksi"
        " dengan berbagai pihak.",
        "UF",
        13,
    ),
    (
        "D8",
        "DEMAND",
        "Recovery",
        "Saya sulit menemukan waktu untuk istirahat yang cukup selama jam kerja.",
        "UF",
        14,
    ),
    # --- CONTROL ---
    (
        "C1a",
        "CONTROL",
        "Method",
        "Saya bisa mengatur sendiri cara dan urutan pekerjaan saya.",
        "F",
        15,
    ),
    (
        "C1b",
        "CONTROL",
        "Method",
        "Cara saya menyelesaikan pekerjaan sebagian besar sudah ditentukan oleh prosedur baku"
        " yang tidak bisa saya ubah.",
        "UF",
        16,
    ),
    (
        "C2a",
        "CONTROL",
        "Decision",
        "Saya memiliki cukup wewenang untuk mengambil keputusan dalam lingkup kerja saya.",
        "F",
        17,
    ),
    (
        "C2b",
        "CONTROL",
        "Decision",
        "Keputusan penting terkait pekerjaan saya diambil oleh pihak lain tanpa melibatkan saya.",
        "UF",
        18,
    ),
    (
        "C3a",
        "CONTROL",
        "Schedule",
        "Jadwal kerja saya cukup fleksibel untuk menyesuaikan dengan kebutuhan profesional dan"
        " personal yang wajar.",
        "F",
        19,
    ),
    (
        "C3b",
        "CONTROL",
        "Schedule",
        "Saya tidak memiliki keleluasaan untuk menyesuaikan jadwal kerja saya meskipun ada"
        " kebutuhan mendesak.",
        "UF",
        20,
    ),
    (
        "C4a",
        "CONTROL",
        "Resources",
        "Saya memiliki akses yang cukup ke alat dan sistem yang dibutuhkan.",
        "F",
        21,
    ),
    (
        "C4b",
        "CONTROL",
        "Resources",
        "Saya mendapatkan informasi yang cukup dan tepat waktu untuk menjalankan tugas saya.",
        "F",
        22,
    ),
    (
        "C5a",
        "CONTROL",
        "Influence",
        "Saya bisa memengaruhi keputusan yang berdampak pada pekerjaan saya.",
        "F",
        23,
    ),
    (
        "C5b",
        "CONTROL",
        "Influence",
        "Masukan saya dipertimbangkan dalam perencanaan program atau kebijakan di unit saya.",
        "F",
        24,
    ),
    (
        "C6",
        "CONTROL",
        "Skill development",
        "Saya memiliki kesempatan untuk mengembangkan keterampilan baru dalam pekerjaan.",
        "F",
        25,
    ),
    (
        "C7",
        "CONTROL",
        "Skill variety",
        "Pekerjaan saya memungkinkan saya menggunakan berbagai keterampilan yang saya miliki.",
        "F",
        26,
    ),
    (
        "C8a",
        "CONTROL",
        "Predictability",
        "Saya bisa memprediksi beban kerja saya dari minggu ke minggu.",
        "F",
        27,
    ),
    (
        "C8b",
        "CONTROL",
        "Predictability",
        "Saya sering tidak tahu tugas apa yang akan datang hingga mendekati tenggat waktunya.",
        "UF",
        28,
    ),
    # --- SUPPORT ---
    (
        "S1a",
        "SUPPORT",
        "Supervisor - difficulty",
        "Atasan langsung saya memberikan dukungan yang memadai saat saya menghadapi kesulitan.",
        "F",
        29,
    ),
    (
        "S1b",
        "SUPPORT",
        "Supervisor - difficulty",
        "Atasan langsung saya sulit dihubungi saat saya membutuhkan arahan atau bantuan.",
        "UF",
        30,
    ),
    (
        "S2a",
        "SUPPORT",
        "Supervisor - feedback",
        "Atasan langsung saya memberikan umpan balik yang membantu saya berkembang.",
        "F",
        31,
    ),
    (
        "S2b",
        "SUPPORT",
        "Supervisor - feedback",
        "Atasan langsung saya menghargai usaha saya, tidak hanya hasil akhirnya.",
        "F",
        32,
    ),
    (
        "S3a",
        "SUPPORT",
        "Peer - help",
        "Rekan kerja saya saling membantu ketika ada yang kesulitan.",
        "F",
        33,
    ),
    (
        "S3b",
        "SUPPORT",
        "Peer - help",
        "Saya merasa harus menyelesaikan sendiri masalah pekerjaan tanpa bisa mengandalkan"
        " rekan kerja.",
        "UF",
        34,
    ),
    (
        "S4",
        "SUPPORT",
        "Peer - collaboration",
        "Ada budaya kolaborasi dan berbagi pengetahuan di unit saya.",
        "F",
        35,
    ),
    (
        "S5",
        "SUPPORT",
        "Admin",
        "Ada staf admin yang membantu mengurangi beban administratif saya.",
        "F",
        36,
    ),
    (
        "S6a",
        "SUPPORT",
        "Training",
        "Saya mendapat pelatihan yang cukup untuk menjalankan tugas-tugas baru.",
        "F",
        37,
    ),
    (
        "S6b",
        "SUPPORT",
        "Training",
        "Pelatihan yang saya terima relevan dan langsung bisa diterapkan dalam pekerjaan saya.",
        "F",
        38,
    ),
    (
        "S7",
        "SUPPORT",
        "Peak support",
        "Ada mekanisme bantuan atau pengurangan beban saat periode sibuk (misalnya: bantuan tenaga"
        " temporer, penundaan laporan non-esensial, atau penyederhanaan prosedur).",
        "F",
        39,
    ),
    (
        "S8a",
        "SUPPORT",
        "Organizational",
        "Organisasi menyediakan sumber daya yang memadai untuk saya bekerja.",
        "F",
        40,
    ),
    (
        "S8b",
        "SUPPORT",
        "Organizational",
        "Saya merasa organisasi tidak menyediakan dukungan yang memadai ketika beban kerja"
        " meningkat.",
        "UF",
        41,
    ),
    (
        "S9",
        "SUPPORT",
        "Recognition",
        "Saya merasa dihargai atas kontribusi saya di sekolah ini.",
        "F",
        42,
    ),
]
