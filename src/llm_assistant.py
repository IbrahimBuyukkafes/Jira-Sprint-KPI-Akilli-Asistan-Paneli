"""Ollama (yerel) tabanli, GERCEK MCP (Model Context Protocol) araclariyla
calisan "Akilli Asistan" motoru.

Bu modul kendi tool tanimlarini DUPLICE ETMEZ: `src/mcp_server.py`'yi bir alt
surec (subprocess) olarak baslatip, gercek bir MCP istemcisi
(`mcp.ClientSession`) uzerinden 13 araci dinamik olarak kesfeder
(`list_tools`) ve cagirir (`call_tool`). Boylece Claude Desktop gibi bir MCP
istemcisinin gordugu ile Streamlit panosundaki asistanin gordugu ARAC
TANIMLARI birebir aynidir - tek dogruluk kaynagi `mcp_server.py`'dir, LLM
sayilari asla uydurmaz.

GIZLILIK: Bu modul TAMAMEN YEREL calisir - `ollama` Python paketi, bu
makinede (varsayilan `localhost:11434`) calisan bir Ollama servisine baglanir.
Jira/personel verisi (isimler, is yuku, performans metrikleri dahil) HICBIR
ZAMAN bu makinenin disina cikmaz, hicbir buluta/uc taraf API'sine gonderilmez.

ONEMLI TASARIM KURALI: Bu modulun var olus sebebi veri gizliligidir. Bu
yuzden Ollama'ya erisilemezse veya model cekilmemisse, BASKA bir buluta
(orn. Gemini) OTOMATIK/SESSIZ bir fallback YAPILMAZ - sadece acik ve spesifik
bir `AssistantUnavailableError` firlatilir (bkz. `_ensure_ollama_ready`). Bu,
tam olarak onlenmeye calisilan veri sizintisini engellemek icin kritiktir;
bu davranisi degistirmeyin.

Her sohbet turu kendi MCP alt surecini acip kapatir (basitlik/guvenilirlik
icin); bu, her turda ~1-2 saniyelik ek bir baslangic maliyeti getirir ama
zaten LLM cikarimi yaninda ihmal edilebilir duzeydedir.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import ollama
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

__all__ = ["DEFAULT_MODEL", "AssistantUnavailableError", "chat_with_local_model"]

DEFAULT_MODEL = "qwen2.5:3b"

# mcp_server.py bu dosyayla ayni klasorde (src/); PROJECT_ROOT ise onun bir ust klasoru.
MCP_SERVER_SCRIPT = Path(__file__).resolve().parent / "mcp_server.py"
PROJECT_ROOT = MCP_SERVER_SCRIPT.parent.parent

SYSTEM_PROMPT = (
    "Sen, bu Jira sprint/KPI panosuna gomulu, dogal ve sicak bir sohbet akisina "
    "sahip bir asistansin (ChatGPT/Claude/Gemini'deki gibi serbest sohbet edebilirsin: "
    "selamlasma, kisa sohbet, onceki mesajlari hatirlama gibi). Kullanicinin "
    "sorulari genelde bu projedeki sprint/ekip/is verisiyle ilgili olacaktir; boyle "
    "bir soru geldiginde ASLA sayi tahmin etme veya uydurma - once ilgili "
    "araci/araclari (tool) cagir, donen GERCEK sonucu al, sonra bunu kisa, net ve "
    "Turkce bir cevaba donustur. Kullanici belirli bir ay belirtmemisse aracin "
    "'month' parametresini bos birak (tum aylar birlikte degerlendirilir). Veri "
    "iceren cevaplarinda sadece araclardan donen gercek degerleri kullan, kendi "
    "basina hesaplama yapma. Sorunun bu projeyle hicbir ilgisi yoksa (orn. hava "
    "durumu, genel kultur), bunu dogal ve kisa bir sekilde belirtip sohbeti "
    "nazikce projeye geri getir - resmi/robotik bir dille degil, gercek bir "
    "sohbet ortagi gibi konus. Bir aracin TUM parametreleri opsiyonelse (orn. "
    "belirli bir kisi/ay/proje adi ZORUNLU degilse), gereksiz yere kullaniciya "
    "'hangi kisiyi/ayi kastediyorsunuz?' diye sormadan once, once araci "
    "parametresiz/genel haliyle cagirip TUM ekip/tum aylar icin sonucu goster - "
    "sadece kullanici gercekten belirli bir kisiyi/ay'i/projeyi acikca "
    "belirtmisse o parametreyi kullan."
)

# Bir turda en fazla kac kez ardisik tool-calling round'u yapilabilecegini sinirlar.
MAX_TOOL_ROUNDS = 5

_TEMPERATURE = 0.2


class AssistantUnavailableError(RuntimeError):
    """Ollama servisine veya `mcp_server.py` alt sureciyle iletisim kurulamadi."""


async def _ensure_ollama_ready(client: ollama.AsyncClient, model: str) -> None:
    """Ollama servisinin ayakta oldugunu VE `model`in cekilmis oldugunu dogrular.
    Ikisinden biri saglanmiyorsa NET, spesifik bir `AssistantUnavailableError`
    firlatir - bkz. modul basindaki "ONEMLI TASARIM KURALI": bu hata BASKA bir
    buluta sessizce dusmek icin degil, kullaniciyi dogru duzeltici eyleme
    (Ollama'yi baslatmak / modeli cekmek) yonlendirmek icindir."""
    try:
        response = await client.list()
    except Exception as exc:  # noqa: BLE001 - kullaniciya anlasilir bir talimat vermek icin genis yakalama
        raise AssistantUnavailableError(
            "Ollama servisine ulaşılamıyor. Ollama çalışmıyor olabilir - "
            "önce Ollama uygulamasını başlatın (veya `ollama serve` komutunu çalıştırın), "
            f"sonra tekrar deneyin. (Ayrıntı: {exc})"
        ) from exc

    available_models = {m.model for m in response.models}
    if model not in available_models:
        raise AssistantUnavailableError(
            f"'{model}' modeli Ollama'da bulunamadı. Önce şu komutla çekin: `ollama pull {model}`."
        )


def _mcp_tool_to_ollama_tool(tool: Any) -> dict:
    """Bir MCP `Tool` semasini (`inputSchema`) Ollama'nin bekledigi `{"type":
    "function", "function": {"name", "description", "parameters"}}` sozlugune
    cevirir. `file_path` parametresi semadan cikarilir - LLM'e HIC gosterilmez,
    her arac cagrisinda otomatik olarak enjekte edilir (bkz. `_run_tool_loop`).

    `scripts/test_ollama_tool_calling.py`'deki `_mcp_tool_to_ollama_tool` ile
    AYNIDIR (o script uzerinde qwen2.5:3b/7b ile GERCEK MCP araclarina karsi
    DOGRULANMIS) - buraya kopyalanip uretim koduna tasindi.
    """
    schema = dict(tool.inputSchema or {})
    properties = dict(schema.get("properties", {}))
    properties.pop("file_path", None)
    required = [name for name in schema.get("required", []) if name != "file_path"]
    schema["properties"] = properties
    schema["required"] = required

    # Docstring'in sadece ilk paragrafi (ozet cumle) yeterli; "Args:" bolumu
    # (artik gizli olan file_path'i de aciklayan kisim dahil) LLM'e gurultu katar.
    description = (tool.description or "").strip().split("\n\n")[0].strip()

    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": description,
            "parameters": schema,
        },
    }


def _content_from_history(history: list[dict], user_message: str) -> list[dict]:
    """Onceki turlardan kalan `history`'yi + yeni `user_message`'i, Ollama'nin
    duz mesaj formatina (`[{"role": ..., "content": ...}, ...]`) cevirir;
    `SYSTEM_PROMPT` ilk mesaj (`role="system"`) olarak eklenir."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend({"role": msg["role"], "content": msg["content"]} for msg in history)
    messages.append({"role": "user", "content": user_message})
    return messages


async def _run_tool_loop(
    client: ollama.AsyncClient,
    session: ClientSession,
    tool_names: set[str],
    ollama_tools: list[dict],
    file_path: str,
    history: list[dict],
    user_message: str,
    model: str,
) -> tuple[str, list[dict]]:
    """Ollama <-> MCP arac-cagirma dongusunun tamami; `session` acikken calisir.
    `scripts/test_ollama_tool_calling.py`'deki (qwen2.5:3b/7b ile GERCEK 13
    MCP aracina karsi DOGRULANMIS) donguyle AYNI mantik - buraya tasindi."""
    messages = _content_from_history(history, user_message)

    for _ in range(MAX_TOOL_ROUNDS):
        response = await client.chat(
            model=model, messages=messages, tools=ollama_tools, options={"temperature": _TEMPERATURE}
        )
        message = response.message
        tool_calls = message.tool_calls or []

        if not tool_calls:
            final_text = message.content or "Bir cevap üretemedim."
            new_history = [*history, {"role": "user", "content": user_message}, {"role": "assistant", "content": final_text}]
            return final_text, new_history

        messages.append(
            {
                "role": "assistant",
                "content": message.content or "",
                "tool_calls": [
                    {"function": {"name": tc.function.name, "arguments": dict(tc.function.arguments or {})}}
                    for tc in tool_calls
                ],
            }
        )

        for call in tool_calls:
            fn_name = call.function.name
            fn_args = dict(call.function.arguments or {})

            if fn_name in tool_names:
                fn_args["file_path"] = file_path  # LLM'in doldurmasina izin verilmez, gercek yol enjekte edilir
                try:
                    result = await session.call_tool(fn_name, fn_args)
                    text = "\n".join(c.text for c in result.content if hasattr(c, "text")) or "{}"
                except Exception as exc:  # noqa: BLE001 - arac hatasini modele geri bildir, sureci durdurma
                    text = json.dumps({"hata": str(exc)}, ensure_ascii=False)
            else:
                text = json.dumps({"hata": f"Bilinmeyen araç: {fn_name}"}, ensure_ascii=False)

            messages.append({"role": "tool", "content": text, "tool_name": fn_name})

    final_text = (
        "Çok fazla araç çağrısı gerekti, net bir cevap üretemedim. "
        "Sorunuzu daha spesifik sorabilir misiniz?"
    )
    new_history = [*history, {"role": "user", "content": user_message}, {"role": "assistant", "content": final_text}]
    return final_text, new_history


async def _chat_turn_async(
    file_path: str, history: list[dict], user_message: str, model: str
) -> tuple[str, list[dict]]:
    """Once Ollama'nin hazir oldugunu dogrular, sonra `mcp_server.py`'yi bir alt
    surec olarak baslatip bu turun tum tool-calling dongusunu calistirir, sonra
    sureci kapatir.

    Olusan HERHANGI bir hata (Ollama veya MCP tarafinda), `async with` bloklari
    TEMIZ sekilde kapandiktan SONRA yeniden firlatilir - `mcp.ClientSession`in
    kendi ic gorev grubu (TaskGroup) acikken bir istisna firlatilirsa, anyio bunu
    okunmasi zor bir `ExceptionGroup`'a sarar; bu yuzden istisna burada once
    yakalanip saklanir, sync context'ler kapandiktan sonra duz bir
    `AssistantUnavailableError` olarak tekrar firlatilir.
    """
    error: Exception | None = None
    result: tuple[str, list[dict]] | None = None

    client = ollama.AsyncClient()
    await _ensure_ollama_ready(client, model)

    server_params = StdioServerParameters(
        command=sys.executable, args=[str(MCP_SERVER_SCRIPT)], cwd=str(PROJECT_ROOT)
    )

    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                mcp_tools = (await session.list_tools()).tools
                tool_names = {t.name for t in mcp_tools}
                ollama_tools = [_mcp_tool_to_ollama_tool(t) for t in mcp_tools]

                try:
                    result = await _run_tool_loop(
                        client, session, tool_names, ollama_tools, file_path, history, user_message, model
                    )
                except Exception as exc:  # noqa: BLE001 - bkz. yukaridaki docstring
                    error = exc
    except Exception as exc:  # noqa: BLE001 - MCP alt sureci baslatilamadi/coktu
        error = exc

    if error is not None:
        raise AssistantUnavailableError(
            f"Ollama'ya veya mcp_server.py alt süreciyle iletişim kurulamadı ({error}). "
            "Ollama'nın çalışır durumda olduğundan ve `src/mcp_server.py`'nin hatasız "
            "başlayabildiğinden emin olun."
        ) from error

    assert result is not None
    return result


def chat_with_local_model(
    file_path: str,
    history: list[dict],
    user_message: str,
    model: str = DEFAULT_MODEL,
) -> tuple[str, list[dict]]:
    """Kullanicinin mesajini, `mcp_server.py`'nin 13 GERCEK MCP aracini bir alt
    surec uzerinden cagirarak, TAMAMEN YEREL calisan Ollama uzerinden yanitlatir
    - hicbir veri/soru bu makinenin disina cikmaz (bkz. modul basi dokumantasyonu).

    `file_path`, yuklenen Jira raporunun DISKTEKI yoludur (MCP araclari dosyayi
    kendi surecinde diskten okur; bkz. `app/new_dashboard.py`'deki kalici
    gecici dosya yonetimi). `history`, onceki turlardan kalan
    `{"role": "user"/"assistant", "content": str}` sozluklerinden olusan
    listedir - tool-calling'in ara adimlari (arac cagrilari/sonuclari) sonraki
    turlara TASINMAZ, her tur kendi MCP oturumunu ve tool-calling dongusunu
    sifirdan calistirir.

    Donen deger: `(asistanin_nihai_metin_cevabi, guncellenmis_history)`.

    Raises:
        AssistantUnavailableError: Ollama servisi calismiyorsa/erisilemiyorsa,
            `model` cekilmemisse veya `mcp_server.py` alt sureci
            baslatilamadiginda/coktuğunde. BASKA bir buluta OTOMATIK fallback
            YAPILMAZ (bkz. modul basi "ONEMLI TASARIM KURALI").
    """
    return asyncio.run(_chat_turn_async(str(file_path), history, user_message, model))
