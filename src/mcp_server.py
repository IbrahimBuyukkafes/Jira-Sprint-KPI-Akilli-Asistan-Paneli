"""Jira Sprint Analyzer icin MCP (Model Context Protocol) sunucusu.

`processor.py` (veri isleme/KPI) ve `reporter.py` (Excel raporlama) modullerini,
bir LLM istemcisinin (Claude Desktop, vb.) `stdio` uzerinden cagirabilecegi
`analyze_sprint`, `create_sprint_excel`, `get_assignee_performance`,
`get_status_breakdown`, `get_sprint_trends`, `search_issues_by_query`,
`get_bottlenecks_report`, `get_estimation_accuracy_report`,
`get_core_5_kpis_report`, `get_project_subject_analysis`,
`get_assignee_details_tool`, `query_sprint_data_natural` ve
`get_advanced_bottlenecks_report` araclari (tools) olarak disa acar.
"""

from __future__ import annotations

import sys
from pathlib import Path

# processor.py ve reporter.py bu dosyayla aynı klasörde (src/) olduğu için doğrudan import ediyoruz.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcp.server.fastmcp import FastMCP

from processor import (
    analyze_advanced_bottlenecks,
    analyze_estimation_accuracy,
    analyze_projects_by_subject,
    answer_dashboard_query,
    calculate_assignee_metrics,
    calculate_status_breakdown,
    compare_multi_sprints,
    detect_bottlenecks,
    get_assignee_deep_dive,
    process_sprint_report,
    read_sprint_report,
    run_core_5_kpi_analyses,
    standardize_dataframe,
)
from processor import search_issues_by_query as _search_issues_by_query
from reporter import create_excel_report

# MCP istemcisi sunucuyu farkli bir calisma dizininden baslatabilir; bu yuzden
# goreli dosya yollarini proje kokune gore cozumluyoruz.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

mcp = FastMCP("JiraSprintAnalyzer")


def _resolve_path(path: str) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


@mcp.tool()
def analyze_sprint(file_path: str, month: str | None = None) -> dict:
    """Bir Jira sprint/iterasyon raporunu (HTML/CSV/XLSX) isler ve KPI ozetini doner.

    Args:
        file_path: Jira'dan disa aktarilmis rapor dosyasinin yolu - .html/.htm,
            .csv veya .xlsx olabilir (goreli yollar proje koku baz alinarak
            cozumlenir).
        month: Analiz edilecek ay (orn. "Temmuz" veya "Temmuz 2026"). Verilmezse
            veride bulunan en guncel ay kullanilir.
    """
    result = process_sprint_report(_resolve_path(file_path), target_month=month)
    summary = result["summary"]

    return {
        "ay": result["target_month"],
        "taahhut_edilen_sp": summary["committed_sp"],
        "gerceklesen_sp": summary["completed_sp"],
        "plan_disi_sp": summary["out_of_plan_sp"],
        "toplam_tamamlanan_sp": summary["total_completed_sp"],
        "tamamlanma_orani_yuzde": summary["completion_rate"],
        "plan_disi_orani_yuzde": summary["out_of_plan_rate"],
        "planlanan_is_sayisi": summary["planned_issue_count"],
        "tamamlanan_is_sayisi": summary["completed_issue_count"],
        "plan_disi_is_sayisi": summary["out_of_plan_issue_count"],
        "toplam_is_sayisi": summary["total_issue_count"],
        "planlanan_is_listesi_ornek": result["planned_issues"].head(5).to_dict(orient="records"),
        "plan_disi_is_listesi_ornek": result["out_of_plan_issues"].head(5).to_dict(orient="records"),
    }


@mcp.tool()
def create_sprint_excel(
    file_path: str,
    month: str | None = None,
    output_path: str = "outputs/sprint_raporu.xlsx",
) -> str:
    """Jira sprint raporunu isleyip tek sayfali, bicimlendirilmis bir Excel raporu olusturur.

    Args:
        file_path: Jira'dan disa aktarilmis rapor dosyasinin yolu - .html/.htm,
            .csv veya .xlsx olabilir (goreli yollar proje koku baz alinarak
            cozumlenir).
        month: Raporlanacak ay (orn. "Temmuz" veya "Temmuz 2026"). Verilmezse
            veride bulunan en guncel ay kullanilir.
        output_path: Uretilecek .xlsx dosyasinin yolu (goreli yollar proje koku
            baz alinarak cozumlenir).
    """
    result = process_sprint_report(_resolve_path(file_path), target_month=month)
    written_path = create_excel_report(result, _resolve_path(output_path), target_month=month)
    return f"Excel raporu basariyla olusturuldu: {written_path.resolve()}"


@mcp.tool()
def get_assignee_performance(file_path: str, month: str | None = None) -> dict:
    """Sorumlu (assignee) bazinda is yuku ve performans tablosunu doner.

    Args:
        file_path: Jira'dan disa aktarilmis rapor dosyasinin yolu - .html/.htm,
            .csv veya .xlsx olabilir (goreli yollar proje koku baz alinarak
            cozumlenir).
        month: Filtrelenecek ay (orn. "Temmuz" veya "Temmuz 2026"). Verilmezse
            veride bulunan tum aylar birlikte degerlendirilir.
    """
    df = standardize_dataframe(read_sprint_report(_resolve_path(file_path)))
    metrics = calculate_assignee_metrics(df, target_month=month)

    return {
        "ay": month or "Tüm aylar",
        "sorumlu_sayisi": int(len(metrics)),
        "kisi_bazli_performans": metrics.to_dict(orient="records"),
    }


@mcp.tool()
def get_status_breakdown(file_path: str, month: str | None = None) -> dict:
    """Islerin statu (durum/asama) bazinda dagilim ozetini doner.

    Args:
        file_path: Jira'dan disa aktarilmis rapor dosyasinin yolu - .html/.htm,
            .csv veya .xlsx olabilir (goreli yollar proje koku baz alinarak
            cozumlenir).
        month: Filtrelenecek ay (orn. "Temmuz" veya "Temmuz 2026"). Verilmezse
            veride bulunan tum aylar birlikte degerlendirilir.
    """
    df = standardize_dataframe(read_sprint_report(_resolve_path(file_path)))
    breakdown = calculate_status_breakdown(df, target_month=month)

    return {
        "ay": month or "Tüm aylar",
        "statu_sayisi": int(len(breakdown)),
        "statu_dagilimi": breakdown.to_dict(orient="records"),
    }


@mcp.tool()
def get_sprint_trends(file_path: str, last_n_months: int | None = None) -> dict:
    """Birden fazla ayin (iterasyonun) KPI'larini yan yana karsilastirarak trend analizi sunar.

    Ornegin "Mayıs'tan Temmuz'a plan dışı iş oranımız nasıl değişmiş?" gibi sorulari
    yanitlamak icin, her metrigin (Taahhüt Edilen SP, Gerçekleşen SP, Plan Dışı SP,
    Toplam Tamamlanan SP, Tamamlanma Oranı, Plan Dışı Oranı) aylara gore degisimini
    tek bir satirdan okunabilir sekilde doner.

    Args:
        file_path: Jira'dan disa aktarilmis rapor dosyasinin yolu - .html/.htm,
            .csv veya .xlsx olabilir (goreli yollar proje koku baz alinarak
            cozumlenir).
        last_n_months: Karsilastirmaya dahil edilecek en guncel ay sayisi. Verilmezse
            veride bulunan tum aylar (eskiden yeniye) dahil edilir.
    """
    df = standardize_dataframe(read_sprint_report(_resolve_path(file_path)))
    comparison = compare_multi_sprints(df, last_n_months=last_n_months)

    if comparison.empty:
        return {
            "aylar": [],
            "metrik_bazli_trend": {},
            "not": "Veride 'Created' tarihi bulunamadi veya parse edilemedi; aylik karsilastirma yapilamiyor.",
        }

    return {
        "aylar": list(comparison.columns),
        "metrik_bazli_trend": comparison.to_dict(orient="index"),
    }


@mcp.tool()
def search_issues_by_query(file_path: str, query_text: str, month: str | None = None) -> dict:
    """Dogal dilde verilen bir sorgu metnini kartlarin metin alanlarinda arayip
    eslesen kartlari doner (orn. "Kullanıcı A'nın Analiz isleri", "XL BLOCK olan kartlar").

    Args:
        file_path: Jira'dan disa aktarilmis rapor dosyasinin yolu - .html/.htm,
            .csv veya .xlsx olabilir (goreli yollar proje koku baz alinarak
            cozumlenir).
        query_text: Aranacak serbest metin (orn. "Kullanıcı A Analiz" veya "XL BLOCK").
            Bosluk ile ayrilan her kelime, kartin talep tipi/is listesi/sorumlu/statu/
            etiket alanlarinin birlesiminde (buyuk/kucuk harf duyarsiz) aranir; bir
            kartin eslesmesi icin tum kelimelerin gecmesi gerekir (AND mantigi).
        month: Filtrelenecek ay (orn. "Temmuz" veya "Temmuz 2026"). Verilmezse
            veride bulunan tum aylar icinde aranir.
    """
    df = standardize_dataframe(read_sprint_report(_resolve_path(file_path)))
    matches = _search_issues_by_query(df, query_text, target_month=month)

    return {
        "sorgu": query_text,
        "ay": month or "Tüm aylar",
        "eslesen_kart_sayisi": int(len(matches)),
        "kartlar": matches.to_dict(orient="records"),
    }


@mcp.tool()
def get_bottlenecks_report(file_path: str, month: str | None = None) -> dict:
    """Takimin is akisindaki tikanikliklari/darbogazlari tespit edip ozet bir metin
    ve detayli tablolarla raporlar (henuz Done olmayan, iptal edilmemis, "blocked/hold/
    bekle" gibi statulerde veya yuksek SP'li aktif isler).

    Args:
        file_path: Jira'dan disa aktarilmis rapor dosyasinin yolu - .html/.htm,
            .csv veya .xlsx olabilir (goreli yollar proje koku baz alinarak
            cozumlenir).
        month: Filtrelenecek ay (orn. "Temmuz" veya "Temmuz 2026"). Verilmezse
            veride bulunan tum aylar birlikte degerlendirilir.
    """
    df = standardize_dataframe(read_sprint_report(_resolve_path(file_path)))
    report = detect_bottlenecks(df, target_month=month)
    critical = report["kritik_isler"]
    top_critical = critical.head(10)

    if top_critical.empty:
        ozet_metni = "Şu an sistemde tıkanan veya kritik seviyede bekleyen bir iş bulunmuyor."
    else:
        satirlar = [
            f"- {row['İş Listesi']} ({row['Statü']}, {row['Büyüklük (Sp)']:.0f} SP, "
            f"Sorumlu: {row['Sorumlu'] or 'Atanmamış'})"
            for _, row in top_critical.iterrows()
        ]
        ozet_metni = "Şu an sistemde tıkanan veya uzun süredir bitmeyen kritik işler şunlardır:\n" + "\n".join(
            satirlar
        )

    return {
        "ay": month or "Tüm aylar",
        "aktif_is_sayisi": report["aktif_is_sayisi"],
        "toplam_aktif_sp": report["toplam_aktif_sp"],
        "ozet_metni": ozet_metni,
        "statu_ozeti": report["status_ozeti"].to_dict(orient="records"),
        "kritik_isler": critical.to_dict(orient="records"),
    }


@mcp.tool()
def get_estimation_accuracy_report(file_path: str, month: str | None = None) -> dict:
    """Talep tipine (Task, Bug, Story vb.) gore tahmin (Estimate/SP) dogruluğunu ve
    sapmasini analiz eder; sprint planlamasini iyilestirmek icin hangi talep
    tipinde tahminlerin en cok saptigini yorumlanabilir bir formatta sunar.

    Args:
        file_path: Jira'dan disa aktarilmis rapor dosyasinin yolu - .html/.htm,
            .csv veya .xlsx olabilir (goreli yollar proje koku baz alinarak
            cozumlenir).
        month: Filtrelenecek ay (orn. "Temmuz" veya "Temmuz 2026"). Verilmezse
            veride bulunan tum aylar birlikte degerlendirilir.
    """
    df = standardize_dataframe(read_sprint_report(_resolve_path(file_path)))
    accuracy = analyze_estimation_accuracy(df, target_month=month)

    if accuracy.empty:
        return {
            "ay": month or "Tüm aylar",
            "ozet_metni": "Analiz edilecek veri bulunamadı.",
            "talep_tipi_bazli_analiz": [],
        }

    en_sapmali = accuracy.iloc[0]
    en_tutarli = accuracy.iloc[-1]

    satirlar = [
        f"- {row['Talep Tipi']}: Hedeflenen {row['Hedeflenen SP']:.0f} SP, "
        f"Gerçekleşen {row['Gerçekleşen SP']:.0f} SP, Tahmin Doğruluğu %{row['Tahmin Doğruluk Oranı (%)']:.1f}, "
        f"Sapma %{row['Sapma Oranı (%)']:.1f}"
        for _, row in accuracy.iterrows()
    ]
    ozet_metni = (
        f"En yüksek tahmin sapması '{en_sapmali['Talep Tipi']}' talep tipinde "
        f"(sapma oranı %{en_sapmali['Sapma Oranı (%)']:.1f}); en tutarlı tahminler "
        f"'{en_tutarli['Talep Tipi']}' talep tipinde (sapma oranı %{en_tutarli['Sapma Oranı (%)']:.1f}).\n"
        + "\n".join(satirlar)
    )

    return {
        "ay": month or "Tüm aylar",
        "ozet_metni": ozet_metni,
        "en_yuksek_sapmali_talep_tipi": en_sapmali["Talep Tipi"],
        "en_tutarli_talep_tipi": en_tutarli["Talep Tipi"],
        "talep_tipi_bazli_analiz": accuracy.to_dict(orient="records"),
    }


@mcp.tool()
def get_core_5_kpis_report(
    file_path: str,
    month: str | None = None,
    assignee: str | None = None,
    project: str | None = None,
) -> dict:
    """5 temel/profesyonel KPI analiz metodunu (Velocity & Predictability,
    Scope Stability/Creep Ratio, Workload Equity & Burnout Risk, Flow Efficiency &
    Bottlenecks, Estimation Accuracy & Variance) tek seferde calistirip
    yorumlanabilir bir ozet metin ve yapilandirilmis verilerle sunar. `assignee`
    ve/veya `project` verilerek takim genelinden kisi/proje bazina inilebilir.

    Args:
        file_path: Jira'dan disa aktarilmis rapor dosyasinin yolu - .html/.htm,
            .csv veya .xlsx olabilir (goreli yollar proje koku baz alinarak
            cozumlenir).
        month: Filtrelenecek ay (orn. "Temmuz" veya "Temmuz 2026"). Verilmezse
            veride bulunan tum aylar birlikte degerlendirilir. 1. metodun aylik
            trend kismi bu parametreden bagimsiz olarak her zaman son 3 ayi kapsar.
        assignee: Belirli bir kisiye (sorumlu) gore filtreler, kismi/buyuk-kucuk
            harf duyarsiz eslesir (orn. "Kullanıcı A"). Verilirse 3. metot, takim ici
            esitsizlik yerine o kisinin aylar arasi is yuku TUTARLILIGINI olcer
            (cunku "esitsizlik" kavrami tek bir kisi icin anlamsizdir). Eslesen
            kimse bulunamazsa tum metotlar bos/sifir sonuc doner.
        project: Belirli bir projeye gore filtreler (orn. "Money Stalkers").
            `assignee` ile birlikte verilirse ikisi de uygulanir (o projede o
            kisinin isleri).
    """
    df = standardize_dataframe(read_sprint_report(_resolve_path(file_path)))
    analyses = run_core_5_kpi_analyses(df, target_month=month, assignee=assignee, project=project)

    velocity = analyses["1_velocity_predictability"]
    scope = analyses["2_scope_stability"]
    workload = analyses["3_workload_equity"]
    flow = analyses["4_flow_efficiency"]
    estimation = analyses["5_estimation_accuracy"]["talep_tipi_bazli_analiz"]

    en_sapmali_tip = estimation.iloc[0]["Talep Tipi"] if not estimation.empty else "veri yok"

    if assignee:
        workload_metni = (
            f"3) Workload Consistency: Toplam yük {workload['toplam_yuk_sp']:.0f} SP, aylar arası "
            f"tutarlılık katsayısı {workload['tutarlilik_katsayisi']:.2f} (düşük = düzenli/istikrarlı "
            f"yük, yüksek = dalgalı/riskli yük)."
        )
        workload_json = {
            "toplam_yuk_sp": workload["toplam_yuk_sp"],
            "tutarlilik_katsayisi": workload["tutarlilik_katsayisi"],
            "aylik_yuk": workload["aylik_yuk"].to_dict(orient="records"),
        }
    else:
        riskli = workload["tukenmislik_riski_tasiyanlar"]
        riskli_isimler = ", ".join(riskli["Sorumlu"]) if not riskli.empty else "yok"
        workload_metni = (
            f"3) Workload Equity: Ortalama kişi yükü {workload['ortalama_yuk_sp']:.1f} SP, eşitsizlik "
            f"katsayısı {workload['esitsizlik_katsayisi']:.2f}; tükenmişlik riski taşıyanlar: "
            f"{riskli_isimler}."
        )
        workload_json = {
            "ortalama_yuk_sp": workload["ortalama_yuk_sp"],
            "esitsizlik_katsayisi": workload["esitsizlik_katsayisi"],
            "kisi_bazli_yuk": workload["kisi_bazli_yuk"].to_dict(orient="records"),
            "tukenmislik_riski_tasiyanlar": riskli.to_dict(orient="records"),
        }

    kapsam = [parca for parca in (f"Sorumlu: {assignee}" if assignee else None,
                                   f"Proje: {project}" if project else None) if parca]
    kapsam_onek = f"Kapsam ({', '.join(kapsam)}):\n" if kapsam else ""

    ozet_metni = kapsam_onek + (
        f"1) Velocity & Predictability: Taahhüt {velocity['taahhut_edilen_sp']:.0f} SP, "
        f"Gerçekleşen {velocity['gerceklesen_sp']:.0f} SP, Tamamlanma Oranı "
        f"%{velocity['tamamlanma_orani_yuzde']:.1f}.\n"
        f"2) Scope Stability: Plan dışı iş, toplam yükün %{scope['scope_creep_orani_yuzde']:.1f}'ini "
        f"oluşturuyor ({scope['plan_disi_sp']:.0f} SP).\n"
        f"{workload_metni}\n"
        f"4) Flow Efficiency: {flow['aktif_is_sayisi']} aktif iş, toplam {flow['toplam_aktif_sp']:.0f} SP; "
        f"{len(flow['kritik_isler'])} kritik/tıkanmış iş tespit edildi.\n"
        f"5) Estimation Accuracy: En yüksek tahmin sapması '{en_sapmali_tip}' talep tipinde."
    )

    return {
        "ay": month or "Tüm aylar",
        "sorumlu": assignee or "Tüm ekip",
        "proje": project or "Tüm projeler",
        "ozet_metni": ozet_metni,
        "1_velocity_predictability": {
            "taahhut_edilen_sp": velocity["taahhut_edilen_sp"],
            "gerceklesen_sp": velocity["gerceklesen_sp"],
            "tamamlanma_orani_yuzde": velocity["tamamlanma_orani_yuzde"],
            "aylik_trend": velocity["aylik_trend"].to_dict(orient="index"),
        },
        "2_scope_stability": scope,
        "3_workload_equity": workload_json,
        "4_flow_efficiency": {
            "statu_dagilimi": flow["statu_dagilimi"].to_dict(orient="records"),
            "aktif_is_sayisi": flow["aktif_is_sayisi"],
            "toplam_aktif_sp": flow["toplam_aktif_sp"],
            "kritik_isler": flow["kritik_isler"].to_dict(orient="records"),
        },
        "5_estimation_accuracy": {
            "talep_tipi_bazli_analiz": estimation.to_dict(orient="records"),
        },
    }


@mcp.tool()
def get_project_subject_analysis(file_path: str, month: str | None = None) -> dict:
    """Jira kartlarini dogrudan Component alanina gore gruplayip (bos olanlar
    "Component Yok" grubunda) her grubun kaynak tuketimini (SP) ve
    tamamlanma oranini raporlar - "Hangi proje/konu ne kadar kaynak tüketti ve
    ne kadar tamamlandı?" sorusunu yanitlar.

    Args:
        file_path: Jira'dan disa aktarilmis rapor dosyasinin yolu - .html/.htm,
            .csv veya .xlsx olabilir (goreli yollar proje koku baz alinarak
            cozumlenir).
        month: Filtrelenecek ay (orn. "Temmuz" veya "Temmuz 2026"). Verilmezse
            veride bulunan tum aylar birlikte degerlendirilir.
    """
    df = standardize_dataframe(read_sprint_report(_resolve_path(file_path)))
    analysis = analyze_projects_by_subject(df, target_month=month)

    if analysis.empty:
        return {
            "ay": month or "Tüm aylar",
            "ozet_metni": "Analiz edilecek veri bulunamadı.",
            "proje_konu_bazli_analiz": [],
        }

    en_yuklu = analysis.iloc[0]
    satirlar = [
        f"- {row['Proje/Konu']}: {row['Toplam İş Sayısı']} iş, {row['Toplam SP']:.0f} SP "
        f"({row['Tamamlanan SP']:.0f} SP tamamlandı, %{row['Tamamlanma Oranı (%)']:.1f})"
        for _, row in analysis.head(10).iterrows()
    ]
    ozet_metni = (
        f"En çok kaynak tüketen proje/konu '{en_yuklu['Proje/Konu']}' "
        f"({en_yuklu['Toplam SP']:.0f} SP, %{en_yuklu['Tamamlanma Oranı (%)']:.1f} tamamlandı).\n"
        + "\n".join(satirlar)
    )

    return {
        "ay": month or "Tüm aylar",
        "proje_konu_sayisi": int(len(analysis)),
        "ozet_metni": ozet_metni,
        "proje_konu_bazli_analiz": analysis.to_dict(orient="records"),
    }


@mcp.tool()
def get_assignee_details_tool(
    file_path: str, assignee_name: str, month: str | None = None
) -> dict:
    """Belirli bir kisinin (sorumlu) tum gorevlerine ve performans detaylarina
    "drill-down" erisim saglar - dashboard'da bir kisiye tiklandiginda gosterilecek
    tam detay raporunu (toplam is sayisi, toplam/tamamlanan SP, tamamlanma orani
    ve gorev listesi) uretir.

    Args:
        file_path: Jira'dan disa aktarilmis rapor dosyasinin yolu - .html/.htm,
            .csv veya .xlsx olabilir (goreli yollar proje koku baz alinarak
            cozumlenir).
        assignee_name: Detaylarina inilecek kisi (kismi, buyuk/kucuk harf duyarsiz
            eslesir, orn. "Kullanıcı A"). Eslesen kimse bulunamazsa `bulundu=False` doner.
        month: Filtrelenecek ay (orn. "Temmuz" veya "Temmuz 2026"). Verilmezse
            kisinin tum aylardaki kartlari dahil edilir.
    """
    df = standardize_dataframe(read_sprint_report(_resolve_path(file_path)))
    detay = get_assignee_deep_dive(df, assignee_name, target_month=month)

    if not detay["bulundu"]:
        return {
            "sorumlu": assignee_name,
            "ay": month or "Tüm aylar",
            "bulundu": False,
            "ozet_metni": f"'{assignee_name}' adına/eşleşen bir sorumlu bulunamadı.",
            "gorev_listesi": [],
        }

    ozet_metni = (
        f"{detay['sorumlu']}: {detay['toplam_is_sayisi']} iş, {detay['toplam_sp']:.0f} SP "
        f"({detay['tamamlanan_sp']:.0f} SP tamamlandı, %{detay['tamamlanma_orani_yuzde']:.1f})."
    )

    return {
        "sorumlu": assignee_name,
        "ay": month or "Tüm aylar",
        "bulundu": True,
        "toplam_is_sayisi": detay["toplam_is_sayisi"],
        "toplam_sp": detay["toplam_sp"],
        "tamamlanan_sp": detay["tamamlanan_sp"],
        "tamamlanma_orani_yuzde": detay["tamamlanma_orani_yuzde"],
        "ozet_metni": ozet_metni,
        "gorev_listesi": detay["gorev_listesi"].to_dict(orient="records"),
    }


@mcp.tool()
def query_sprint_data_natural(file_path: str, query: str, month: str | None = None) -> str:
    """Dashboard'daki soru çubuğuna yazılan doğal dil sorularını (örn. "Kimin
    üzerinde kaç iş var?", "Hangi işler bloklu?", "En çok kim yükleniyor?")
    işleyip anlaşılır bir Türkçe metin/cümle olarak yanıtlar.

    Sorgu; içinde geçen bir kişi adi, darboğaz/tıkanıklık, tahmin sapması,
    proje/konu, aylık trend, statü dağılımı veya kişi bazlı yük gibi anahtar
    kelimelere göre en uygun analize yönlendirilir; hiçbiri eşleşmezse serbest
    metin araması yapılır, o da sonuç vermezse genel bir sprint özeti döner
    (fonksiyon her zaman anlamlı bir metin döner, asla hata fırlatmaz).

    Args:
        file_path: Jira'dan disa aktarilmis rapor dosyasinin yolu - .html/.htm,
            .csv veya .xlsx olabilir (goreli yollar proje koku baz alinarak
            cozumlenir).
        query: Doğal dilde soru (orn. "Kimin üzerinde kaç iş var?", "Hangi işler
            bloklu?", "Kullanıcı A'nın işleri neler?", "Tahmin sapmamız nasıl?").
        month: Filtrelenecek ay (orn. "Temmuz" veya "Temmuz 2026"). Verilmezse
            ilgili alt analiz veride bulunan tüm ayları birlikte değerlendirir.
    """
    df = standardize_dataframe(read_sprint_report(_resolve_path(file_path)))
    return answer_dashboard_query(df, query, target_month=month)


@mcp.tool()
def get_advanced_bottlenecks_report(file_path: str, month: str | None = None) -> dict:
    """Takimin gizli tikanikliklarini ve surec verimsizliklerini acmak icin 5 ileri
    duzey darbogaz/akis metrigini (WIP Aging, Blocker & Hold, Assignee Bouncing,
    Reopen Orani, Flow Load vs. Capacity) tek raporda sunar.

    Jira export'unda el degistirme (handoff) gecmisi veya `Resolved` tarihi
    bulunmuyorsa (cogu export'ta boyle), ilgili metotlar bunu acikca belirterek
    (raporda `not`/`yontem`/`aciklama` alanlariyla) makul bir proxy'ye duser.

    Args:
        file_path: Jira'dan disa aktarilmis rapor dosyasinin yolu - .html/.htm,
            .csv veya .xlsx olabilir (goreli yollar proje koku baz alinarak
            cozumlenir).
        month: Filtrelenecek ay (orn. "Temmuz" veya "Temmuz 2026"). Verilmezse
            veride bulunan tum aylar birlikte degerlendirilir.
    """
    df = standardize_dataframe(read_sprint_report(_resolve_path(file_path)))
    rapor = analyze_advanced_bottlenecks(df, target_month=month)

    wip = rapor["1_wip_aging"]
    blocker = rapor["2_blocker_hold"]
    bouncing = rapor["3_assignee_bouncing"]
    reopen = rapor["4_reopen_rate"]
    flow = rapor["5_flow_load_capacity"]

    ozet_metni = (
        f"1) WIP Aging: {wip['aktif_is_sayisi']} aktif iş, ortalama {wip['ortalama_yas_gun']:.1f} gündür "
        f"açık; {wip['onceki_ay']['is_sayisi']} iş bir önceki aydan kalma, "
        f"{wip['uc_aylik']['is_sayisi']} iş 2-3 ay önce açılmış, "
        f"{wip['alti_aylik']['is_sayisi']} iş 6+ aydır açık (uzun süreli).\n"
        f"2) Blocker & Hold: {blocker['tikali_is_sayisi']} iş (%{blocker['tikali_is_orani_yuzde']:.1f}) "
        f"tıkanmış durumda, bu da {blocker['tikali_sp']:.0f} SP'lik (%{blocker['tikali_sp_orani_yuzde']:.1f}) "
        f"bir maliyete karşılık geliyor.\n"
        f"3) Assignee Bouncing (proxy): En yüklü %20'lik dilim toplam yükün "
        f"%{bouncing['yogunlasma_orani_yuzde']:.1f}'ini taşıyor; en yüklü kişi "
        f"'{bouncing['en_yuklu_kisi']}'.\n"
        f"4) Reopen Oranı ({reopen['yontem']}): %{reopen['reopen_orani_yuzde']:.1f} "
        f"({reopen['reopen_is_sayisi']} iş) - {reopen['aciklama']}\n"
        f"5) Flow Load vs. Capacity: İşler {len(flow['asama_dagilimi'])} akış aşamasına dağılmış "
        f"durumda; en yoğun aşama detay tablosunda görülebilir."
    )

    return {
        "ay": month or "Tüm aylar",
        "ozet_metni": ozet_metni,
        "1_wip_aging": {
            "aktif_is_sayisi": wip["aktif_is_sayisi"],
            "ortalama_yas_gun": wip["ortalama_yas_gun"],
            "yaslanma_ozeti": wip["yaslanma_ozeti"].to_dict(orient="records"),
            "onceki_ay": {
                "is_sayisi": wip["onceki_ay"]["is_sayisi"],
                "toplam_sp": wip["onceki_ay"]["toplam_sp"],
                "kartlar": wip["onceki_ay"]["kartlar"].to_dict(orient="records"),
            },
            "uc_aylik": {
                "is_sayisi": wip["uc_aylik"]["is_sayisi"],
                "toplam_sp": wip["uc_aylik"]["toplam_sp"],
                "kartlar": wip["uc_aylik"]["kartlar"].to_dict(orient="records"),
            },
            "alti_aylik": {
                "is_sayisi": wip["alti_aylik"]["is_sayisi"],
                "toplam_sp": wip["alti_aylik"]["toplam_sp"],
                "kartlar": wip["alti_aylik"]["kartlar"].to_dict(orient="records"),
            },
        },
        "2_blocker_hold": {
            "tikali_is_sayisi": blocker["tikali_is_sayisi"],
            "tikali_is_orani_yuzde": blocker["tikali_is_orani_yuzde"],
            "tikali_sp": blocker["tikali_sp"],
            "tikali_sp_orani_yuzde": blocker["tikali_sp_orani_yuzde"],
            "tikali_isler": blocker["tikali_isler"].to_dict(orient="records"),
        },
        "3_assignee_bouncing": {
            "kisi_sayisi": bouncing["kisi_sayisi"],
            "yogunlasma_orani_yuzde": bouncing["yogunlasma_orani_yuzde"],
            "en_yuklu_kisi": bouncing["en_yuklu_kisi"],
            "kisi_bazli_yuk": bouncing["kisi_bazli_yuk"].to_dict(orient="records"),
            "not": bouncing["not"],
        },
        "4_reopen_rate": {
            "yontem": reopen["yontem"],
            "aciklama": reopen["aciklama"],
            "reopen_is_sayisi": reopen["reopen_is_sayisi"],
            "reopen_orani_yuzde": reopen["reopen_orani_yuzde"],
            "detay_isler": reopen["detay_isler"].to_dict(orient="records"),
        },
        "5_flow_load_capacity": {
            "asama_dagilimi": flow["asama_dagilimi"].to_dict(orient="records"),
        },
    }


if __name__ == "__main__":
    mcp.run()